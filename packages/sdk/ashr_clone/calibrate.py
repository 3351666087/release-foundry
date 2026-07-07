from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
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
PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION = "ashr.clone.api_probe_batch_plan.v1"
PLAN_BATCH_QUOTA_GATE_VALIDATION_SCHEMA_VERSION = "ashr.clone.api_probe_gate_validation.v1"
PLAN_BATCH_QUOTA_GATE_DECISIONS = {"go", "stop", "wait"}
CALIBRATION_QUOTA_GATE_TARGET_OPERATION = "create-request"
DEFAULT_QUOTA_GATE_TTL_SECONDS = 24 * 60 * 60
MIN_QUOTA_OVERRIDE_REASON_CHARS = 12
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
    quota_gate_record: str | None = None
    quota_gate_ttl_seconds: int = DEFAULT_QUOTA_GATE_TTL_SECONDS
    allow_quota_override: bool = False
    quota_override_reason: str | None = None


@dataclass(slots=True)
class CalibrationStep:
    step_id: str
    kind: str
    estimated_calls: int
    purpose: str
    run: Callable[[AshrApiClient, bool, str, CalibrationArgs], JsonDict]
    modality: str | None = None


def run_calibration(args: CalibrationArgs, *, env: Mapping[str, str] | None = None, client: AshrApiClient | None = None) -> JsonDict:
    validate_calibration_guards(args)
    quota_gate_summary = enforce_mutating_quota_gate(args)
    env_map = env or os.environ
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
        record_needs_write = False
        try:
            record = step.run(client, dry_run, output_path, args)
        except Exception as exc:  # noqa: BLE001 - calibration must preserve controlled failure evidence.
            record = error_step_record(step, exc, dry_run, output_path)
            record_needs_write = True
        if step.kind == "mutate" and quota_gate_summary is not None:
            record = attach_quota_gate_evidence(record, quota_gate_summary)
            record_needs_write = True
        if record_needs_write:
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
                "mutating_execute_requires_quota_gate": True,
                "max_retries_for_execute": args.max_retries if args.execute else None,
                "raw_records_private": True,
                "quota_gate": quota_gate_summary,
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
    accepted_inputs = {
        part: {"enabled": part == modality or part == "text"}
        for part in (*CALIBRATION_MODALITIES, "conversation")
    }
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
                    "parameters": {
                        "type": "object",
                        "required": ["summary"],
                        "properties": {"summary": {"type": "string"}},
                    },
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


def attach_quota_gate_evidence(record: Mapping[str, Any], quota_gate_summary: Mapping[str, Any]) -> JsonDict:
    updated = redact_sensitive(dict(record))
    gate = redact_sensitive(dict(quota_gate_summary))
    updated["quota_gate"] = gate
    request = updated.get("request")
    if isinstance(request, dict):
        preflight = request.setdefault("preflight", {})
        if isinstance(preflight, dict):
            preflight["quota_gate"] = {
                "decision": gate.get("decision"),
                "gate_decision": gate.get("gate_decision"),
                "source": gate.get("source"),
                "override_used": gate.get("override", {}).get("used") if isinstance(gate.get("override"), Mapping) else None,
            }
    return redact_sensitive(updated)


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
    if mutating_quota_gate_required(args) and not args.quota_gate_record and not args.allow_quota_override:
        raise CalibrationUsageError("mutating real API calibration requires --quota-gate-record from plan-batch or --allow-quota-override with an audit reason")
    if mutating_quota_gate_required(args) and args.allow_quota_override and not valid_quota_override_reason(args.quota_override_reason):
        raise CalibrationUsageError("--allow-quota-override requires --quota-override-reason with at least 12 characters")


def mutating_quota_gate_required(args: CalibrationArgs) -> bool:
    return args.execute and args.include_mutating


def valid_quota_override_reason(reason: str | None) -> bool:
    return len(str(reason or "").strip()) >= MIN_QUOTA_OVERRIDE_REASON_CHARS


def enforce_mutating_quota_gate(args: CalibrationArgs) -> JsonDict | None:
    if not mutating_quota_gate_required(args):
        return None
    override_reason = str(args.quota_override_reason or "").strip()
    if not args.quota_gate_record:
        return redact_sensitive(
            {
                "decision": "override",
                "gate_decision": None,
                "source": "audited-override",
                "record": None,
                "override": {"used": True, "reason": override_reason},
            }
        )
    record = load_json_object(args.quota_gate_record, "--quota-gate-record")
    validation = validate_quota_gate_record(
        record,
        args,
        target_operation=CALIBRATION_QUOTA_GATE_TARGET_OPERATION,
        ttl_seconds=args.quota_gate_ttl_seconds,
    )
    if not validation["valid"]:
        raise CalibrationUsageError(quota_gate_validation_error_message(validation))
    gate = validation["gate"]
    decision = gate["decision"]
    summary = quota_gate_summary(record, gate, args.quota_gate_record, validation)
    if decision == "go":
        summary["decision"] = "go"
        summary["override"] = {"used": False, "reason": None}
        return redact_sensitive(summary)
    if args.allow_quota_override:
        summary["decision"] = "override"
        summary["override"] = {"used": True, "reason": override_reason}
        return redact_sensitive(summary)
    raise CalibrationUsageError(f"mutating real API calibration blocked by quota gate decision={decision}; rerun after reset evidence or pass --allow-quota-override with --quota-override-reason")


def extract_plan_batch_quota_gate(record: Mapping[str, Any], path: str) -> tuple[JsonDict, JsonDict]:
    response = record.get("response") if isinstance(record.get("response"), Mapping) else {}
    plan = response.get("plan") if isinstance(response.get("plan"), Mapping) else {}
    record_schema = record.get("schema_version")
    plan_schema = plan.get("schema_version")
    if record.get("function") != "plan_batch" or PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION not in {record_schema, plan_schema}:
        raise CalibrationUsageError(f"{redact_sensitive(path)} must be a plan-batch quota gate record with schema_version {PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION} and function plan_batch")
    gate = plan.get("quota_stop_go") if isinstance(plan.get("quota_stop_go"), Mapping) else None
    if not isinstance(gate, Mapping):
        raise CalibrationUsageError(f"{redact_sensitive(path)} must include response.plan.quota_stop_go.decision")
    decision = gate.get("decision")
    if decision not in PLAN_BATCH_QUOTA_GATE_DECISIONS:
        raise CalibrationUsageError(f"{redact_sensitive(path)} has unsupported quota gate decision={redact_sensitive(str(decision))}")
    return redact_sensitive(dict(plan)), redact_sensitive(dict(gate))


def validate_quota_gate_record(record: Mapping[str, Any], args: CalibrationArgs, *, target_operation: str, ttl_seconds: int, now: datetime | None = None) -> JsonDict:
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds < 0:
        raise CalibrationUsageError("--quota-gate-ttl-seconds must be an integer >= 0")

    plan, gate = extract_plan_batch_quota_gate(record, args.quota_gate_record or "--quota-gate-record")
    issues: list[JsonDict] = []

    plan_target = plan.get("target_operation")
    if plan_target != target_operation:
        issues.append({"code": "target_operation_mismatch", "message": f"quota gate target_operation={plan_target!r} does not match requested operation={target_operation!r}"})

    created_at = plan.get("created_at")
    created_dt: datetime | None = None
    age_seconds: int | None = None
    if isinstance(created_at, str):
        created_dt = parse_utc_datetime(created_at)
        if created_dt is None:
            issues.append({"code": "invalid_created_at", "message": "quota gate plan.created_at is not a valid ISO timestamp"})
    elif ttl_seconds:
        issues.append({"code": "missing_created_at", "message": "quota gate plan.created_at is required when TTL validation is enabled"})

    if created_dt is not None:
        current = now or datetime.now(timezone.utc)
        age_seconds = max(0, int((current - created_dt).total_seconds()))
        if ttl_seconds and age_seconds > ttl_seconds:
            issues.append({"code": "stale_gate", "message": f"quota gate is stale: age_seconds={age_seconds} exceeds ttl_seconds={ttl_seconds}"})

    if gate.get("decision") == "go":
        try:
            validate_quota_go_gate(gate)
        except CalibrationUsageError as exc:
            issues.append({"code": "go_without_quota_evidence", "message": str(exc)})

    binding = quota_gate_plan_binding(plan, args, issues)
    return redact_sensitive(
        {
            "valid": not issues,
            "schema_version": PLAN_BATCH_QUOTA_GATE_VALIDATION_SCHEMA_VERSION,
            "gate": gate,
            "target_operation": plan_target,
            "expected_target_operation": target_operation,
            "created_at": created_at if isinstance(created_at, str) else None,
            "age_seconds": age_seconds,
            "ttl_seconds": ttl_seconds,
            **binding,
            "issues": issues,
        }
    )


def quota_gate_summary(record: Mapping[str, Any], gate: Mapping[str, Any], path: str, validation: Mapping[str, Any]) -> JsonDict:
    quota = gate.get("quota") if isinstance(gate.get("quota"), Mapping) else {}
    return redact_sensitive(
        {
            "decision": gate.get("decision"),
            "gate_decision": gate.get("decision"),
            "source": gate.get("source"),
            "can_enter_small_batch": gate.get("can_enter_small_batch") if isinstance(gate.get("can_enter_small_batch"), bool) else None,
            "can_enter_batch": gate.get("can_enter_batch") if isinstance(gate.get("can_enter_batch"), bool) else None,
            "record": {
                "path": path,
                "schema_version": record.get("schema_version"),
                "function": record.get("function"),
            },
            "validation": validation,
            "quota": {
                "blocked": quota.get("blocked") is True,
                "quota_keys": sorted(str(key) for key in quota.keys()),
                "resource": quota.get("resource") if isinstance(quota.get("resource"), str) else None,
            }
            if quota
            else None,
        }
    )


def validate_quota_go_gate(gate: Mapping[str, Any]) -> None:
    reset = gate.get("reset") if isinstance(gate.get("reset"), Mapping) else {}
    header_keys = reset.get("header_keys") if isinstance(reset.get("header_keys"), list) else []
    evidence_present = gate.get("quota_or_reset_evidence_present") is True or isinstance(gate.get("quota"), Mapping) or bool(header_keys)
    if gate.get("source") == "not-provided" or not evidence_present:
        raise CalibrationUsageError("quota gate decision=go requires reviewed quota/reset evidence; rerun plan-batch with --quota-record or use an audited override")


def quota_gate_validation_error_message(validation: Mapping[str, Any]) -> str:
    issues = validation.get("issues") if isinstance(validation.get("issues"), list) else []
    messages = [
        str(issue.get("message"))
        for issue in issues
        if isinstance(issue, Mapping) and isinstance(issue.get("message"), str) and issue.get("message")
    ]
    return f"quota gate validation failed: {'; '.join(messages) if messages else 'unknown quota gate validation issue'}"


def quota_gate_plan_binding(plan: Mapping[str, Any], args: CalibrationArgs, issues: list[JsonDict]) -> JsonDict:
    binding: JsonDict = {}
    expected_modalities = expected_calibration_gate_modalities(args)
    plan_modalities, modalities_source = extract_plan_modalities(plan, issues)
    if plan_modalities is not None:
        binding["modalities"] = list(plan_modalities)
        binding["expected_modalities"] = list(expected_modalities)
        binding["modalities_source"] = modalities_source
        if plan_modalities != expected_modalities:
            issues.append({"code": "modalities_mismatch", "message": f"quota gate modalities={list(plan_modalities)!r} do not match requested modalities={list(expected_modalities)!r}"})

    if "request_fingerprint" in plan:
        binding.update(validate_request_fingerprint_binding(plan.get("request_fingerprint"), args, issues))
    return binding


def extract_plan_modalities(plan: Mapping[str, Any], issues: list[JsonDict]) -> tuple[tuple[str, ...] | None, str | None]:
    if "modalities" in plan:
        return normalize_modality_binding(plan.get("modalities"), "response.plan.modalities", issues), "response.plan.modalities"

    if "modality_sequence" in plan:
        sequence = plan.get("modality_sequence")
        if not isinstance(sequence, list):
            issues.append({"code": "invalid_modalities_binding", "message": "quota gate response.plan.modality_sequence must be an array when present"})
            return None, "response.plan.modality_sequence"
        values: list[str] = []
        for index, item in enumerate(sequence):
            if not isinstance(item, Mapping) or not isinstance(item.get("modality"), str):
                issues.append({"code": "invalid_modalities_binding", "message": f"quota gate response.plan.modality_sequence[{index}].modality must be a string"})
                continue
            values.append(str(item["modality"]))
        return normalize_modalities(values), "response.plan.modality_sequence"

    phases = plan.get("phases")
    if phases is None:
        return None, None
    if not isinstance(phases, list):
        issues.append({"code": "invalid_modalities_binding", "message": "quota gate response.plan.phases must be an array when modality binding is present"})
        return None, "response.plan.phases"
    values = []
    saw_modalities = False
    for index, phase in enumerate(phases):
        if not isinstance(phase, Mapping):
            issues.append({"code": "invalid_modalities_binding", "message": f"quota gate response.plan.phases[{index}] must be an object"})
            continue
        if "modalities" not in phase:
            continue
        saw_modalities = True
        phase_modalities = phase.get("modalities")
        if not isinstance(phase_modalities, list) or not all(isinstance(item, str) for item in phase_modalities):
            issues.append({"code": "invalid_modalities_binding", "message": f"quota gate response.plan.phases[{index}].modalities must be an array of strings"})
            continue
        values.extend(str(item) for item in phase_modalities)
    return (normalize_modalities(values), "response.plan.phases[].modalities") if saw_modalities else (None, None)


def normalize_modality_binding(value: Any, path: str, issues: list[JsonDict]) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        issues.append({"code": "invalid_modalities_binding", "message": f"quota gate {path} must be an array of strings when present"})
        return None
    return normalize_modalities(str(item) for item in value)


def normalize_modalities(values: Sequence[str] | Any) -> tuple[str, ...]:
    unique = {str(value) for value in values if str(value)}
    ordered = [modality for modality in CALIBRATION_MODALITIES if modality in unique]
    ordered.extend(sorted(value for value in unique if value not in CALIBRATION_MODALITIES))
    return tuple(ordered)


def expected_calibration_gate_modalities(args: CalibrationArgs) -> tuple[str, ...]:
    selected = set(selected_calibration_modalities(args))
    selected.add("text")
    return tuple(modality for modality in CALIBRATION_MODALITIES if modality in selected)


def validate_request_fingerprint_binding(value: Any, args: CalibrationArgs, issues: list[JsonDict]) -> JsonDict:
    expected = calibration_request_fingerprints(args)
    binding: JsonDict = {"request_fingerprint": value, "expected_request_fingerprints": expected}
    expected_values = set(expected.values())
    if isinstance(value, str):
        if len(expected_values) != 1:
            issues.append({"code": "request_fingerprint_mismatch", "message": "quota gate request_fingerprint must bind every selected calibrator modality when more than one request shape is selected"})
        elif value not in expected_values:
            issues.append({"code": "request_fingerprint_mismatch", "message": "quota gate request_fingerprint does not match the selected calibrator request shape"})
        return redact_sensitive(binding)
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            issues.append({"code": "invalid_request_fingerprint", "message": "quota gate request_fingerprint array must contain only strings"})
        elif set(value) != expected_values:
            issues.append({"code": "request_fingerprint_mismatch", "message": "quota gate request_fingerprint array does not match selected calibrator request shapes"})
        return redact_sensitive(binding)
    if isinstance(value, Mapping):
        normalized = {str(key): item for key, item in value.items()}
        if not all(isinstance(item, str) for item in normalized.values()):
            issues.append({"code": "invalid_request_fingerprint", "message": "quota gate request_fingerprint map values must be strings"})
        elif normalized != expected:
            issues.append({"code": "request_fingerprint_mismatch", "message": "quota gate request_fingerprint map does not match selected calibrator request shapes"})
        return redact_sensitive(binding)

    issues.append({"code": "invalid_request_fingerprint", "message": "quota gate request_fingerprint must be a string, array, or modality map when present"})
    return redact_sensitive(binding)


def calibration_request_fingerprints(args: CalibrationArgs) -> JsonDict:
    return {modality: calibration_request_fingerprint(modality) for modality in selected_calibration_modalities(args)}


def calibration_request_fingerprint(modality: str) -> str:
    payload = json.dumps(request_for_modality(modality), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_utc_datetime(value: str) -> datetime | None:
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_json_object(path: str, label: str) -> JsonDict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationUsageError(f"{label} {redact_sensitive(path)} could not be read as a JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise CalibrationUsageError(f"{label} {redact_sensitive(path)} must contain a JSON object")
    return value


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
    parser.add_argument("--quota-gate-record", help="Required for mutating --execute unless --allow-quota-override is used. Must be a plan-batch record.")
    parser.add_argument("--quota-gate-ttl-seconds", type=non_negative_int, default=DEFAULT_QUOTA_GATE_TTL_SECONDS, help=f"Maximum age for a plan-batch quota gate. Default {DEFAULT_QUOTA_GATE_TTL_SECONDS}; 0 disables.")
    parser.add_argument("--allow-quota-override", action="store_true", help="Allow mutating --execute without a go quota gate. Requires --quota-override-reason.")
    parser.add_argument("--quota-override-reason", help="Audit reason for bypassing a missing, stop, or wait quota gate.")
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
        quota_gate_record=ns.quota_gate_record,
        quota_gate_ttl_seconds=ns.quota_gate_ttl_seconds,
        allow_quota_override=ns.allow_quota_override,
        quota_override_reason=ns.quota_override_reason,
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
