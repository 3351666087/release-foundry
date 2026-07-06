from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .api_client import (
    AGENT_INPUT_PART_TYPES,
    ASHR_API_ENV_VAR,
    ASHR_API_FIELD_MAP_VERSION,
    ASHR_DEFAULT_BASE_URL,
    ASHR_LABS_API_ENV_VAR,
    ASHR_LABS_BASE_URL_ENV_VAR,
    AshrApiClient,
    AshrApiError,
    JsonDict,
    MissingAshrApiKeyError,
    elapsed_ms,
    redact_sensitive,
    summarize_quota_error,
    utc_now,
)

CALIBRATION_MANIFEST_SCHEMA_VERSION = "ashr.clone.api_calibration_manifest.v1"
CALIBRATION_MODALITIES = AGENT_INPUT_PART_TYPES


class CalibrationUsageError(ValueError):
    pass


@dataclass(slots=True)
class CalibrationArgs:
    execute: bool = False
    small_batch: bool = False
    include_mutating: bool = False
    allow_paid_media: bool = False
    output: str | None = None
    base_url: str | None = None
    timeout: int = 30
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    limit: int = 2
    modalities: tuple[str, ...] = ()
    print_record: bool = False


@dataclass(slots=True)
class CalibrationStep:
    step_id: str
    kind: str
    estimated_calls: int
    purpose: str
    run: Callable[[AshrApiClient, bool, str, CalibrationArgs], JsonDict]
    modality: str | None = None


def run_calibration(args: CalibrationArgs, *, env: Mapping[str, str] | None = None, client: AshrApiClient | None = None) -> JsonDict:
    env_map = env or os.environ
    validate_calibration_guards(args)
    dry_run = not args.execute
    manifest_path = args.output or default_output_path(args.execute)
    client = client or AshrApiClient(
        api_key=env_map.get(ASHR_API_ENV_VAR) or env_map.get(ASHR_LABS_API_ENV_VAR),
        base_url=args.base_url or env_map.get(ASHR_LABS_BASE_URL_ENV_VAR, ASHR_DEFAULT_BASE_URL),
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_backoff_seconds=args.retry_backoff_seconds,
    )
    steps = calibration_steps(args)
    if not args.include_mutating:
        steps = [step for step in steps if step.kind != "mutate"]

    started_at = utc_now()
    start_ms = __import__("time").monotonic()
    step_results: list[JsonDict] = []
    errors: list[JsonDict] = []

    for step in steps:
        output_path = step_output_path(manifest_path, step.step_id, dry_run)
        try:
            record = step.run(client, dry_run, output_path, args)
        except Exception as exc:  # noqa: BLE001 - calibration must preserve controlled failure evidence.
            record = error_step_record(step, exc, dry_run, output_path)
            write_json(output_path, record)
        summary = summarize_step(step, record, output_path)
        step_results.append(summary)
        if summary.get("status") == "error" or summary.get("quota", {}).get("blocked") is True:
            errors.append(
                {
                    "step_id": step.step_id,
                    "status": summary.get("status"),
                    "status_code": summary.get("status_code"),
                    "error_kind": summary.get("error_kind"),
                    "error_keys": summary.get("error_keys", []),
                    "quota": summary.get("quota"),
                }
            )
            if step.kind == "mutate":
                break

    ok_count = sum(1 for step in step_results if step.get("status") in {"ok", "planned"})
    status = "planned" if dry_run and not errors else "ok" if not errors else "partial" if ok_count else "error"
    manifest = redact_sensitive(
        {
            "schema_version": CALIBRATION_MANIFEST_SCHEMA_VERSION,
            "mode": "dry-run" if dry_run else "small-batch",
            "dry_run": dry_run,
            "status": status,
            "started_at": started_at,
            "ended_at": utc_now(),
            "duration_ms": elapsed_ms(start_ms),
            "field_map_version": ASHR_API_FIELD_MAP_VERSION,
            "env": {
                "auth_env_present": [name for name in (ASHR_API_ENV_VAR, ASHR_LABS_API_ENV_VAR) if env_map.get(name)],
                "base_url": client.base_url,
            },
            "guardrails": {
                "execute_requires_small_batch": True,
                "mutating_requires_include_mutating": True,
                "paid_media_requires_allow_paid_media": True,
                "max_retries_for_execute": args.max_retries if args.execute else None,
                "raw_records_private": True,
            },
            "summary": {
                "total_steps": len(step_results),
                "read_steps": sum(1 for step in step_results if step.get("kind") == "read"),
                "mutating_steps": sum(1 for step in step_results if step.get("kind") == "mutate"),
                "ok_or_planned_steps": ok_count,
                "error_steps": len(errors),
                "estimated_calls": sum(step.estimated_calls for step in steps),
                "modalities": sorted({step["modality"] for step in step_results if step.get("modality")}),
                "quota_block_count": sum(1 for step in step_results if step.get("quota", {}).get("blocked") is True),
            },
            "steps": step_results,
            "errors": errors,
        }
    )
    write_json(manifest_path, manifest)
    return manifest


def calibration_steps(args: CalibrationArgs) -> list[CalibrationStep]:
    limit = min(max(1, int(args.limit)), 5)
    steps = [
        CalibrationStep("init", "read", 1, "Resolve Ashr session context and tenant/user/features shape", lambda client, dry, output, _args: client.init(dry_run=dry, output_path=output)),
        CalibrationStep("health-check", "read", 1, "Check Ashr API reachability and keep_alive shape", lambda client, dry, output, _args: client.health_check(dry_run=dry, output_path=output)),
        CalibrationStep("list-agents", "read", 1, "List tenant agent fields for SDK adapter parity", lambda client, dry, output, _args: client.list_agents(dry_run=dry, output_path=output)),
        CalibrationStep("list-datasets", "read", 2, "List dataset fields, pagination, and dataset_source envelopes", lambda client, dry, output, _args: client.list_datasets(dry_run=dry, output_path=output, limit=limit)),
        CalibrationStep("list-requests", "read", 2, "List request fields, failure envelopes, and pagination", lambda client, dry, output, _args: client.list_requests(dry_run=dry, output_path=output, limit=limit)),
    ]
    steps.extend(create_request_step(modality) for modality in selected_calibration_modalities(args))
    return steps


def create_request_step(modality: str) -> CalibrationStep:
    def run(client: AshrApiClient, dry: bool, output: str, args: CalibrationArgs) -> JsonDict:
        request = request_for_modality(modality)
        return client.create_request(
            dry_run=dry,
            output_path=output,
            request_name=f"A1 {modality} API calibration {'dry run' if dry else 'small batch'}",
            request=request,
            allow_media_generation=args.allow_paid_media,
            allow_non_text_inputs=True,
            max_request_variations=1,
        )

    return CalibrationStep(
        step_id=f"create-request-{modality}",
        kind="mutate",
        modality=modality,
        estimated_calls=2,
        purpose=f"Create a tiny {modality} calibration request with first-class AgentInput envelope",
        run=run,
    )


def request_for_modality(modality: str) -> JsonDict:
    generation_options: JsonDict = {
        "generate_audio": modality == "audio",
        "generate_files": modality == "file",
        "generate_images": modality == "image",
        "generate_videos": modality == "video",
        "generate_simulations": False,
    }
    accepted_inputs = {part: {"enabled": part == modality or part == "text"} for part in (*CALIBRATION_MODALITIES, "conversation")}
    return {
        "agent": {
            "name": f"A1 {modality} calibration agent",
            "description": f"Synthetic non-sensitive {modality} API calibration agent.",
            "accepted_inputs": accepted_inputs,
            "output_format": {"type": "text"},
            "tools": [
                {
                    "name": "inspect_input",
                    "description": f"Inspect synthetic {modality} input without external side effects.",
                    "parameters": {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string"}}},
                }
            ],
        },
        "context": {"domain": "api calibration", "use_case": f"Validate {modality} request shape and paid generation guardrails.", "scenario_context": "Use tiny synthetic non-sensitive data only."},
        "metadata": {"dataset_name": f"A1 {modality} API calibration", "description": "Generated by A1 env-gated calibration harness.", "local_secret_policy": "ASHR_API_KEY read from environment only; no key is logged or stored."},
        "test_config": {"strategy": "focused", "num_variations": 1, "coverage": {"happy_path": True, "edge_cases": False, "error_handling": False}},
        "generation_options": generation_options,
    }


def summarize_step(step: CalibrationStep, record: Mapping[str, Any], output_path: str) -> JsonDict:
    response = record.get("response") if isinstance(record.get("response"), Mapping) else {}
    error = record.get("error") if isinstance(record.get("error"), Mapping) else {}
    response_headers = record.get("response_headers") if isinstance(record.get("response_headers"), Mapping) else {}
    summary: JsonDict = {
        "step_id": step.step_id,
        "kind": step.kind,
        "modality": step.modality,
        "function": record.get("function"),
        "purpose": step.purpose,
        "dry_run": record.get("dry_run"),
        "status": record.get("status"),
        "status_code": record.get("status_code"),
        "attempts": record.get("attempts"),
        "estimated_calls": step.estimated_calls,
        "response_keys": sorted(str(key) for key in response.keys()),
        "response_status": response.get("status") if isinstance(response.get("status"), str) else None,
        "response_headers_keys": sorted(str(key) for key in response_headers.keys()),
        "response_summary_keys": sorted(str(key) for key in record.get("response_summary", {}).keys()) if isinstance(record.get("response_summary"), Mapping) else [],
        "top_counts": {key: len(response[key]) for key in ("agents", "datasets", "requests", "runs") if isinstance(response.get(key), list)},
        "next_cursor": response.get("next_cursor"),
        "error_keys": sorted(str(key) for key in error.keys()),
        "error_kind": error.get("error_kind") if isinstance(error.get("error_kind"), str) else None,
        "private_record_path": output_path,
    }
    quota = summarize_quota_error(record)
    if quota:
        summary["quota"] = quota
    return redact_sensitive(summary)


def error_step_record(step: CalibrationStep, error: Exception, dry_run: bool, output_path: str) -> JsonDict:
    if isinstance(error, AshrApiError) and isinstance(error.response, Mapping) and is_call_record(error.response):
        record = redact_sensitive(dict(error.response))
        record["output_path"] = output_path
        return record
    now = utc_now()
    status_code = error.status_code if isinstance(error, AshrApiError) else None
    error_payload = error.to_dict() if isinstance(error, AshrApiError) else {"message": str(error), "status_code": status_code, "error_kind": "auth" if isinstance(error, MissingAshrApiKeyError) else "client"}
    return redact_sensitive(
        {
            "function": step.step_id,
            "dry_run": dry_run,
            "purpose": step.purpose,
            "started_at": now,
            "ended_at": now,
            "duration_ms": 0,
            "attempts": 0,
            "status": "error",
            "status_code": status_code,
            "request": {"function": step.step_id, "params": {}, "estimated_calls": step.estimated_calls, "mutates": step.kind == "mutate"},
            "response_headers": error.response_headers if isinstance(error, AshrApiError) else {},
            "error": error_payload,
            "output_path": output_path,
            "field_map_version": ASHR_API_FIELD_MAP_VERSION,
        }
    )


def is_call_record(value: Mapping[str, Any]) -> bool:
    return isinstance(value.get("function"), str) and isinstance(value.get("dry_run"), bool) and value.get("field_map_version") == ASHR_API_FIELD_MAP_VERSION


def selected_calibration_modalities(args: CalibrationArgs) -> tuple[str, ...]:
    selected = args.modalities or CALIBRATION_MODALITIES
    ordered: list[str] = []
    for modality in CALIBRATION_MODALITIES:
        if modality in selected and modality not in ordered:
            ordered.append(modality)
    return tuple(ordered)


def validate_calibration_guards(args: CalibrationArgs) -> None:
    if args.execute and not args.small_batch:
        raise CalibrationUsageError("real API calibration requires --small-batch before --execute")
    if args.execute and args.max_retries != 0:
        raise CalibrationUsageError("real API calibration requires --max-retries 0 to avoid duplicate paid calls")
    paid_modalities = [modality for modality in selected_calibration_modalities(args) if modality != "text"]
    if args.include_mutating and paid_modalities and not args.allow_paid_media:
        raise CalibrationUsageError("non-text media calibration requires --allow-paid-media after reviewing cost risk")


def step_output_path(manifest_path: str, step_id: str, dry_run: bool) -> str:
    suffix = "dry_run" if dry_run else "real"
    return str(Path(manifest_path).resolve().parent / f"a1_python_api_calibration_{step_id}_{suffix}.json")


def default_output_path(execute: bool) -> str:
    return f"docs/evidence/private_refs/a1_python_api_calibration_manifest_{'real' if execute else 'dry_run'}.json"


def write_json(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(redact_sensitive(dict(value)), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> CalibrationArgs:
    parser = argparse.ArgumentParser(description="Run Ashr clone Python SDK real API calibration with safe private evidence records.")
    parser.add_argument("--execute", action="store_true", help="Call the real Ashr API. Requires --small-batch and --max-retries 0.")
    parser.add_argument("--small-batch", action="store_true", help="Acknowledge bounded API execution.")
    parser.add_argument("--include-mutating", action="store_true", help="Include create_request calibration steps after read-only steps.")
    parser.add_argument("--allow-paid-media", action="store_true", help="Allow non-text media request calibration when mutating steps are selected.")
    parser.add_argument("--output")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=positive_int, default=30)
    parser.add_argument("--max-retries", type=non_negative_int, default=2)
    parser.add_argument("--retry-backoff-seconds", type=non_negative_float, default=0.5)
    parser.add_argument("--limit", type=positive_int, default=2)
    parser.add_argument("--modality", action="append", default=[], help="Comma-separated modality list: text,image,audio,file,video")
    parser.add_argument("--print-record", action="store_true")
    ns = parser.parse_args(argv)
    modalities = parse_modalities(ns.modality)
    args = CalibrationArgs(
        execute=ns.execute,
        small_batch=ns.small_batch,
        include_mutating=ns.include_mutating,
        allow_paid_media=ns.allow_paid_media,
        output=ns.output,
        base_url=ns.base_url,
        timeout=ns.timeout,
        max_retries=ns.max_retries,
        retry_backoff_seconds=ns.retry_backoff_seconds,
        limit=ns.limit,
        modalities=modalities,
        print_record=ns.print_record,
    )
    try:
        validate_calibration_guards(args)
    except CalibrationUsageError as exc:
        parser.error(str(exc))
    return args


def parse_modalities(values: Sequence[str]) -> tuple[str, ...]:
    parsed: list[str] = []
    for value in values:
        for item in value.split(","):
            modality = item.strip()
            if not modality:
                continue
            if modality not in CALIBRATION_MODALITIES:
                raise CalibrationUsageError(f"unsupported modality: {modality}")
            if modality not in parsed:
                parsed.append(modality)
    return tuple(parsed)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        manifest = run_calibration(args)
    except CalibrationUsageError as exc:
        print(f"calibration usage error: {exc}")
        return 2
    except MissingAshrApiKeyError as exc:
        print(f"calibration auth error: {exc}")
        return 2
    if args.print_record:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(json.dumps({"status": manifest["status"], "output": args.output or default_output_path(args.execute), "summary": manifest["summary"]}, indent=2, sort_keys=True))
    return 0 if manifest.get("status") in {"ok", "planned"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
