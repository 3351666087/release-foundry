from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SDK_PATH = Path(__file__).resolve().parents[2] / "packages" / "sdk"
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from ashr_clone.api_client import (  # noqa: E402
    ASHR_API_ENV_VAR,
    ASHR_API_FIELD_MAP_VERSION,
    ASHR_LABS_API_ENV_VAR,
    AshrApiClient,
    AshrApiError,
    MissingAshrApiKeyError,
    enforce_create_request_preflight,
    redact_sensitive,
    summarize_generation_request,
    summarize_quota_error,
    utc_now,
)

API_OPERATIONS = [
    "init",
    "health-check",
    "list-datasets",
    "get-dataset",
    "list-runs",
    "get-run",
    "poll-run",
    "list-requests",
    "list-agents",
    "get-request",
    "poll-request",
    "create-request",
    "create-run",
]
API_PROBE_BATCH_PLAN_SCHEMA_VERSION = "ashr.clone.api_probe_batch_plan.v1"
MODALITY_SEQUENCE_ORDER = ("text", "image", "audio", "file", "video", "conversation", "simulation")
MEDIA_GENERATION_TO_MODALITY = {"audio": "audio", "files": "file", "images": "image", "videos": "video", "simulations": "simulation"}
OPERATION_ESTIMATED_CALLS = {
    "init": 1,
    "health-check": 1,
    "list-datasets": 2,
    "get-dataset": 1,
    "list-runs": 2,
    "get-run": 1,
    "poll-run": 1,
    "list-requests": 2,
    "list-agents": 1,
    "get-request": 1,
    "poll-request": 1,
    "create-request": 2,
    "create-run": 2,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quota-safe Ashr API calibration probe.")
    parser.add_argument("operation", choices=[*API_OPERATIONS, "plan-batch"])
    parser.add_argument("--target-operation", choices=API_OPERATIONS, default="create-request", help="Operation to batch-plan when operation=plan-batch.")
    parser.add_argument("--execute", action="store_true", help="Perform the real API call. Omit for dry-run planning.")
    parser.add_argument("--allow-mutate", action="store_true", help="Required with --execute for create-run and create-request.")
    parser.add_argument("--output", help="JSON output path. Defaults to docs/evidence/private_refs.")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--dataset-id", type=int)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--request-id", type=int)
    parser.add_argument("--result-file", help="Run result JSON for create-run.")
    parser.add_argument("--request-name", help="Request name for create-request.")
    parser.add_argument("--request-file", help="Generation request config JSON for create-request.")
    parser.add_argument("--request-schema-file", help="Optional request input schema JSON for create-request.")
    parser.add_argument("--allow-media-generation", action="store_true", help="Allow create-request configs that enable audio, file, image, video, or simulation generation.")
    parser.add_argument("--allow-non-text-inputs", action="store_true", help="Allow create-request configs whose accepted_inputs include audio, files, images, videos, or conversations.")
    parser.add_argument("--max-request-variations", type=int, default=1, help="Maximum known num_variations allowed for create-request execution.")
    parser.add_argument("--small-batch-size", type=int, default=1, help="Real-call size for the first bounded phase in plan-batch output.")
    parser.add_argument("--batch-size", type=int, help="Target larger batch size for plan-batch output. Defaults to the request variation count when known.")
    parser.add_argument("--quota-record", help="Optional previous private API probe record JSON with quota or reset headers.")
    parser.add_argument("--quota-gate-record", help="Required for mutating --execute unless --allow-quota-override is used. Must be a plan-batch record with response.plan.quota_stop_go.")
    parser.add_argument("--allow-quota-override", action="store_true", help="Allow mutating --execute without a go quota gate. Requires --quota-override-reason.")
    parser.add_argument("--quota-override-reason", help="Audit reason for bypassing a missing, stop, or wait quota gate.")
    parser.add_argument("--poll-timeout", type=int, default=300)
    parser.add_argument("--poll-interval", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dry_run = not args.execute
    output = Path(args.output) if args.output else default_output_path(args.operation, dry_run=dry_run)

    try:
        if args.operation == "plan-batch":
            if args.execute:
                raise ValueError("plan-batch is planning-only; omit --execute")
            record = run_operation(None, args, output=output, dry_run=True)
            print("{mode} {operation}: status={status} attempts={attempts} output={output}".format(mode="planned", operation=args.operation, status=record["status"], attempts=record["attempts"], output=output))
            return 0
        if args.execute and args.operation in MUTATING_OPERATIONS and not args.allow_mutate:
            raise ValueError(f"{args.operation} is mutating; rerun with --allow-mutate after reviewing the dry-run plan")
        if args.execute and args.operation in MUTATING_OPERATIONS and args.max_retries != 0:
            raise ValueError(f"{args.operation} execution requires --max-retries 0 to avoid duplicate mutation on retry")
        args.quota_gate_summary = enforce_mutating_quota_gate(args) if args.execute and args.operation in MUTATING_OPERATIONS else None
        client_kwargs: dict[str, Any] = {"timeout": args.timeout, "max_retries": args.max_retries}
        if args.base_url:
            client_kwargs["base_url"] = args.base_url
        client = AshrApiClient.from_env(required=args.execute, **client_kwargs)
        record = run_operation(client, args, output=output, dry_run=dry_run)
        print("{mode} {operation}: status={status} attempts={attempts} output={output}".format(mode="executed" if args.execute else "planned", operation=args.operation, status=record["status"], attempts=record["attempts"], output=output))
        return 0
    except MissingAshrApiKeyError as exc:
        print(f"api probe error: {exc}", file=sys.stderr)
        print(f"hint: set {ASHR_API_ENV_VAR} or {ASHR_LABS_API_ENV_VAR} in the current process", file=sys.stderr)
        return 2
    except (AshrApiError, RuntimeError, TimeoutError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"api probe error: {exc}", file=sys.stderr)
        return 2


def run_operation(client: AshrApiClient | None, args: argparse.Namespace, *, output: Path, dry_run: bool) -> dict[str, Any]:
    if args.operation == "plan-batch":
        return run_batch_plan(args, output=output)
    require(client, "client is required for API probe operations")
    if args.operation == "init":
        return client.init(output_path=output, dry_run=dry_run)
    if args.operation == "health-check":
        return client.health_check(output_path=output, dry_run=dry_run)
    if args.operation == "list-datasets":
        return client.list_datasets(limit=args.limit, output_path=output, dry_run=dry_run)
    if args.operation == "get-dataset":
        require(args.dataset_id, "--dataset-id is required for get-dataset")
        return client.get_dataset(args.dataset_id, output_path=output, dry_run=dry_run)
    if args.operation == "list-runs":
        return client.list_runs(dataset_id=args.dataset_id, limit=args.limit, output_path=output, dry_run=dry_run)
    if args.operation == "get-run":
        require(args.run_id, "--run-id is required for get-run")
        return client.get_run(args.run_id, output_path=output, dry_run=dry_run)
    if args.operation == "poll-run":
        require(args.run_id, "--run-id is required for poll-run")
        return client.poll_run(run_id=args.run_id, timeout_seconds=args.poll_timeout, poll_interval_seconds=args.poll_interval, output_path=output, dry_run=dry_run)
    if args.operation == "list-requests":
        return client.list_requests(limit=args.limit, output_path=output, dry_run=dry_run)
    if args.operation == "list-agents":
        return client.list_agents(output_path=output, dry_run=dry_run)
    if args.operation == "get-request":
        require(args.request_id, "--request-id is required for get-request")
        return client.get_request(args.request_id, output_path=output, dry_run=dry_run)
    if args.operation == "poll-request":
        require(args.request_id, "--request-id is required for poll-request")
        return client.poll_request(request_id=args.request_id, timeout_seconds=args.poll_timeout, poll_interval_seconds=args.poll_interval, output_path=output, dry_run=dry_run)
    if args.operation == "create-request":
        require(args.request_name, "--request-name is required for create-request")
        require(args.request_file, "--request-file is required for create-request")
        request = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
        request_schema = json.loads(Path(args.request_schema_file).read_text(encoding="utf-8")) if args.request_schema_file else None
        preflight = summarize_generation_request(request)
        preflight["request_input_schema_source"] = "file" if request_schema is not None else "client_default"
        if getattr(args, "quota_gate_summary", None):
            preflight["quota_gate"] = args.quota_gate_summary
        if not dry_run:
            enforce_create_request_preflight(
                preflight,
                allow_media_generation=args.allow_media_generation,
                allow_non_text_inputs=args.allow_non_text_inputs,
                max_request_variations=args.max_request_variations,
            )
        record = client.create_request(
            request_name=args.request_name,
            request=request,
            request_input_schema=request_schema,
            output_path=output,
            dry_run=dry_run,
            allow_media_generation=args.allow_media_generation,
            allow_non_text_inputs=args.allow_non_text_inputs,
            max_request_variations=args.max_request_variations,
        )
        record = attach_quota_gate(record, getattr(args, "quota_gate_summary", None), output)
        if dry_run:
            batch_plan = build_api_probe_batch_plan(
                target_operation="create-request",
                output=output,
                request=request,
                request_input_schema_source=preflight["request_input_schema_source"],
                allow_media_generation=args.allow_media_generation,
                allow_non_text_inputs=args.allow_non_text_inputs,
                max_request_variations=args.max_request_variations,
                small_batch_size=getattr(args, "small_batch_size", 1),
                batch_size=getattr(args, "batch_size", None),
                quota_record=load_optional_json(getattr(args, "quota_record", None)),
            )
            attach_batch_plan(record, batch_plan, output)
        return record
    if args.operation == "create-run":
        require(args.dataset_id, "--dataset-id is required for create-run")
        require(args.result_file, "--result-file is required for create-run")
        result = json.loads(Path(args.result_file).read_text(encoding="utf-8"))
        record = client.create_run(dataset_id=args.dataset_id, result=result, output_path=output, dry_run=dry_run)
        return attach_quota_gate(record, getattr(args, "quota_gate_summary", None), output)
    raise ValueError(f"unsupported operation: {args.operation}")


def run_batch_plan(args: argparse.Namespace, *, output: Path) -> dict[str, Any]:
    request: dict[str, Any] | None = None
    request_schema_source = "not_applicable"
    if args.target_operation == "create-request":
        require(args.request_file, "--request-file is required for plan-batch --target-operation create-request")
        request = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
        request_schema_source = "file" if args.request_schema_file else "client_default"
    plan = build_api_probe_batch_plan(
        target_operation=args.target_operation,
        output=output,
        request=request,
        request_input_schema_source=request_schema_source,
        allow_media_generation=getattr(args, "allow_media_generation", False),
        allow_non_text_inputs=getattr(args, "allow_non_text_inputs", False),
        max_request_variations=getattr(args, "max_request_variations", 1),
        small_batch_size=getattr(args, "small_batch_size", 1),
        batch_size=getattr(args, "batch_size", None),
        quota_record=load_optional_json(getattr(args, "quota_record", None)),
    )
    now = utc_now()
    record = redact_sensitive(
        {
            "schema_version": API_PROBE_BATCH_PLAN_SCHEMA_VERSION,
            "function": "plan_batch",
            "dry_run": True,
            "purpose": "Plan quota-safe Ashr API probe phases before real execution",
            "started_at": now,
            "ended_at": now,
            "duration_ms": 0,
            "attempts": 0,
            "status": "planned" if plan["quota_stop_go"]["decision"] == "go" else "blocked",
            "status_code": None,
            "request": {
                "function": "plan_batch",
                "params": {
                    "target_operation": args.target_operation,
                    "small_batch_size": _positive_count(getattr(args, "small_batch_size", 1), "small_batch_size"),
                    "batch_size": plan["batch_size"],
                    "quota_record": str(getattr(args, "quota_record", None)) if getattr(args, "quota_record", None) else None,
                },
                "estimated_calls": 0,
                "mutates": False,
            },
            "response": {"plan": plan},
            "response_headers": {},
            "output_path": str(output),
            "field_map_version": ASHR_API_FIELD_MAP_VERSION,
        }
    )
    write_json(output, record)
    return record


def build_api_probe_batch_plan(
    *,
    target_operation: str,
    output: Path | None = None,
    request: dict[str, Any] | None = None,
    request_input_schema_source: str = "not_applicable",
    allow_media_generation: bool = False,
    allow_non_text_inputs: bool = False,
    max_request_variations: Any = 1,
    small_batch_size: int = 1,
    batch_size: int | None = None,
    quota_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    small_count = _positive_count(small_batch_size, "small_batch_size")
    preflight = summarize_generation_request(request) if request is not None else None
    if preflight is not None:
        preflight["request_input_schema_source"] = request_input_schema_source
    inferred_batch_size = _inferred_batch_size(preflight, small_count, batch_size)
    quota_stop_go = build_quota_stop_go(quota_record)
    modality_sequence = build_modality_sequence(preflight)
    plan = {
        "schema_version": API_PROBE_BATCH_PLAN_SCHEMA_VERSION,
        "target_operation": target_operation,
        "created_at": utc_now(),
        "output_path": str(output) if output is not None else None,
        "phase_order": ["dry-run", "small-batch", "batch"],
        "small_batch_size": small_count,
        "batch_size": inferred_batch_size,
        "operation_mutates": target_operation in MUTATING_OPERATIONS,
        "preflight": preflight,
        "modality_sequence": modality_sequence,
        "quota_stop_go": quota_stop_go,
        "phases": build_phase_plan(
            target_operation,
            small_batch_size=small_count,
            batch_size=inferred_batch_size,
            modality_sequence=modality_sequence,
            allow_media_generation=allow_media_generation,
            allow_non_text_inputs=allow_non_text_inputs,
            max_request_variations=max_request_variations,
        ),
        "guardrails": {
            "dry_run_first": True,
            "real_mutations_require_allow_mutate": target_operation in MUTATING_OPERATIONS,
            "real_mutations_require_max_retries_zero": target_operation in MUTATING_OPERATIONS,
            "batch_waits_for_quota_go": True,
            "media_after_text_small_batch": any(item["kind"] == "media" for item in modality_sequence),
            "raw_request_not_recorded": True,
            "sensitive_values_not_recorded": True,
        },
    }
    return redact_sensitive(plan)


def build_phase_plan(
    target_operation: str,
    *,
    small_batch_size: int,
    batch_size: int,
    modality_sequence: list[dict[str, Any]],
    allow_media_generation: bool,
    allow_non_text_inputs: bool,
    max_request_variations: Any,
) -> list[dict[str, Any]]:
    estimated_calls = OPERATION_ESTIMATED_CALLS.get(target_operation, 1)
    mutates = target_operation in MUTATING_OPERATIONS
    common_stop_conditions = [
        "quota_stop_go.decision is stop",
        "latest real record status is error or timeout",
        "retry-after or x-ratelimit reset metadata says wait",
    ]
    return [
        {
            "phase": "dry-run",
            "order": 0,
            "execute": False,
            "estimated_real_api_calls": 0,
            "batch_size": 0,
            "modalities": [item["modality"] for item in modality_sequence if item["modality"] == "text"],
            "go_to_next_when": ["record.status is planned", "preflight reviewed", "raw request contains no secrets"],
            "stop_conditions": ["dry-run preflight is unsupported", *common_stop_conditions],
        },
        {
            "phase": "small-batch",
            "order": 1,
            "execute": True,
            "estimated_real_api_calls": estimated_calls,
            "batch_size": small_batch_size,
            "modalities": [item["modality"] for item in modality_sequence if item["modality"] == "text"],
            "requires": _phase_requirements(mutates, allow_media_generation=False, allow_non_text_inputs=False, max_request_variations=small_batch_size),
            "go_to_next_when": ["record.status is ok", "quota_stop_go.decision is go", "no retry/reset wait is active"],
            "stop_conditions": common_stop_conditions,
        },
        {
            "phase": "batch",
            "order": 2,
            "execute": True,
            "estimated_real_api_calls": estimated_calls,
            "batch_size": batch_size,
            "modalities": [item["modality"] for item in modality_sequence],
            "requires": _phase_requirements(mutates, allow_media_generation=allow_media_generation, allow_non_text_inputs=allow_non_text_inputs, max_request_variations=max_request_variations),
            "go_to_next_when": ["batch record.status is ok", "private evidence record is saved"],
            "stop_conditions": common_stop_conditions,
        },
    ]


def build_modality_sequence(preflight: dict[str, Any] | None) -> list[dict[str, Any]]:
    if preflight is None:
        enabled_modalities = {"text": {"accepted_inputs"}}
    else:
        enabled_modalities: dict[str, set[str]] = {}
        accepted_flags = preflight.get("accepted_input_flags") if isinstance(preflight.get("accepted_input_flags"), dict) else {}
        for modality in ("text", "image", "audio", "file", "video", "conversation"):
            if accepted_flags.get(modality):
                enabled_modalities.setdefault(modality, set()).add("accepted_inputs")
        media_generation = preflight.get("media_generation") if isinstance(preflight.get("media_generation"), dict) else {}
        for generated_name, modality in MEDIA_GENERATION_TO_MODALITY.items():
            if media_generation.get(generated_name):
                enabled_modalities.setdefault(modality, set()).add("media_generation")
        if not enabled_modalities:
            enabled_modalities["text"] = {"default"}

    sequence: list[dict[str, Any]] = []
    for modality in MODALITY_SEQUENCE_ORDER:
        sources = enabled_modalities.get(modality)
        if not sources:
            continue
        sequence.append(
            {
                "order": len(sequence),
                "modality": modality,
                "kind": "text" if modality == "text" else "media" if modality in {"image", "audio", "file", "video", "simulation"} else "conversation",
                "sources": sorted(sources),
                "phase_gate": "small-batch must pass with text before media/conversation batch execution" if modality != "text" else "first dry-run and small-batch modality",
                "requires_allowance": modality not in {"text"} and ("accepted_inputs" in sources or "media_generation" in sources),
            }
        )
    return sequence


def build_quota_stop_go(quota_record: dict[str, Any] | None) -> dict[str, Any]:
    quota = summarize_quota_error(quota_record) if quota_record else None
    headers = _quota_headers(quota_record)
    reset = _reset_metadata(headers)
    evidence_present = bool(quota_record)
    quota_or_reset_evidence_present = bool(quota or headers)
    decision = "wait"
    if not evidence_present:
        decision = "wait"
    elif quota and quota.get("blocked") is True:
        decision = "stop"
    elif reset["wait_hint_present"]:
        decision = "wait"
    elif quota_or_reset_evidence_present:
        decision = "go"
    return redact_sensitive(
        {
            "decision": decision,
            "source": "quota-record" if quota_record else "not-provided",
            "evidence_present": evidence_present,
            "quota_or_reset_evidence_present": quota_or_reset_evidence_present,
            "quota": quota,
            "reset": reset,
            "go_conditions": [
                "latest private record includes quota or rate-limit header evidence",
                "no quota.blocked flag in that private record",
                "no retry-after wait is active",
                "operator has reviewed the dry-run and small-batch records before the next phase",
            ],
            "stop_conditions": [
                "quota evidence is absent",
                "quota.blocked is true",
                "remaining quota is zero or unavailable after an error",
                "reset metadata indicates retry-after/x-ratelimit-reset wait is required",
            ],
            "can_enter_small_batch": decision == "go",
            "can_enter_batch": decision == "go",
        }
    )


def attach_batch_plan(record: dict[str, Any], batch_plan: dict[str, Any], output: Path) -> None:
    response = record.get("response")
    if isinstance(response, dict):
        plan = response.get("plan")
        if isinstance(plan, dict):
            plan["batch_plan"] = batch_plan
    request = record.get("request")
    if isinstance(request, dict):
        preflight = request.get("preflight")
        if isinstance(preflight, dict):
            preflight["batch_plan"] = {
                "schema_version": API_PROBE_BATCH_PLAN_SCHEMA_VERSION,
                "phase_order": batch_plan["phase_order"],
                "quota_decision": batch_plan["quota_stop_go"]["decision"],
                "modality_order": [item["modality"] for item in batch_plan["modality_sequence"]],
            }
    write_json(output, record)


def attach_quota_gate(record: dict[str, Any], quota_gate: dict[str, Any] | None, output: Path) -> dict[str, Any]:
    if not quota_gate:
        return record
    safe_gate = redact_sensitive(dict(quota_gate))
    record["quota_gate"] = safe_gate
    request = record.get("request")
    if isinstance(request, dict):
        preflight = request.get("preflight")
        if isinstance(preflight, dict):
            preflight["quota_gate"] = safe_gate
        else:
            request["quota_gate"] = safe_gate
    write_json(output, record)
    return record


def enforce_mutating_quota_gate(args: argparse.Namespace) -> dict[str, Any]:
    quota_gate_record = load_optional_json(getattr(args, "quota_gate_record", None))
    override = bool(getattr(args, "allow_quota_override", False))
    reason = str(getattr(args, "quota_override_reason", "") or "").strip()
    if quota_gate_record is None:
        if override:
            if len(reason) < 12:
                raise ValueError("--allow-quota-override requires --quota-override-reason with at least 12 characters")
            return {**build_quota_stop_go(None), "decision": "override", "override": {"used": True, "reason": reason}}
        raise ValueError(f"{args.operation} execution requires --quota-gate-record from plan-batch or --allow-quota-override with an audit reason")
    quota_gate = extract_quota_gate(quota_gate_record)
    decision = quota_gate["decision"]
    if decision == "go":
        validate_quota_go_gate(quota_gate)
        return {**quota_gate, "override": {"used": False, "reason": None}}
    if override:
        if len(reason) < 12:
            raise ValueError("--allow-quota-override requires --quota-override-reason with at least 12 characters")
        return {**quota_gate, "override": {"used": True, "reason": reason}}
    raise ValueError(f"{args.operation} execution blocked by quota gate decision={decision}; rerun after reset evidence or pass --allow-quota-override with --quota-override-reason")


def extract_quota_gate(record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("--quota-gate-record must contain a JSON object")
    response = record.get("response")
    plan = response.get("plan") if isinstance(response, dict) else None
    if (
        record.get("function") != "plan_batch"
        or not isinstance(plan, dict)
        or (
            record.get("schema_version") != API_PROBE_BATCH_PLAN_SCHEMA_VERSION
            and plan.get("schema_version") != API_PROBE_BATCH_PLAN_SCHEMA_VERSION
        )
    ):
        raise ValueError(f"--quota-gate-record must be a plan-batch record with schema_version={API_PROBE_BATCH_PLAN_SCHEMA_VERSION} and function=plan_batch")
    gate = plan.get("quota_stop_go")
    if not isinstance(gate, dict):
        raise ValueError("--quota-gate-record must include response.plan.quota_stop_go.decision")
    decision = gate.get("decision")
    if decision not in {"go", "stop", "wait"}:
        raise ValueError(f"--quota-gate-record has unsupported quota_stop_go.decision={redact_sensitive(str(decision))}")
    return redact_sensitive(dict(gate))


def validate_quota_go_gate(gate: dict[str, Any]) -> None:
    reset = gate.get("reset") if isinstance(gate.get("reset"), dict) else {}
    header_keys = reset.get("header_keys") if isinstance(reset.get("header_keys"), list) else []
    evidence_present = gate.get("quota_or_reset_evidence_present") is True or bool(gate.get("quota")) or bool(header_keys)
    if gate.get("source") == "not-provided" or not evidence_present:
        raise ValueError("--quota-gate-record decision=go requires reviewed quota/reset evidence; rerun plan-batch with --quota-record or use an audited override")


def default_output_path(operation: str, *, dry_run: bool) -> Path:
    suffix = "dry_run" if dry_run else "real"
    safe_operation = operation.replace("-", "_")
    return Path("docs") / "evidence" / "private_refs" / f"a1_api_{safe_operation}_{suffix}.json"


def require(value: Any, message: str) -> None:
    if value is None:
        raise ValueError(message)


def load_optional_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(redact_sensitive(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _positive_count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _inferred_batch_size(preflight: dict[str, Any] | None, small_batch_size: int, batch_size: int | None) -> int:
    if batch_size is not None:
        return _positive_count(batch_size, "batch_size")
    if preflight is not None and isinstance(preflight.get("num_variations"), int):
        return max(small_batch_size, int(preflight["num_variations"]))
    return max(small_batch_size, 2)


def _phase_requirements(
    mutates: bool,
    *,
    allow_media_generation: bool,
    allow_non_text_inputs: bool,
    max_request_variations: Any,
) -> dict[str, Any]:
    requirements: dict[str, Any] = {
        "execute": True,
        "max_retries": 0 if mutates else "operator-selected",
    }
    if mutates:
        requirements["allow_mutate"] = True
    requirements["allow_media_generation"] = allow_media_generation
    requirements["allow_non_text_inputs"] = allow_non_text_inputs
    requirements["max_request_variations"] = max_request_variations
    return requirements


def _quota_headers(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {}
    headers = record.get("response_headers")
    if not isinstance(headers, dict):
        error = record.get("error")
        if isinstance(error, dict) and isinstance(error.get("response_headers"), dict):
            headers = error["response_headers"]
        else:
            headers = {}
    selected: dict[str, Any] = {}
    for key, value in headers.items():
        lower_key = str(key).lower()
        if lower_key == "retry-after" or lower_key.startswith("x-ratelimit"):
            selected[str(key)] = value
    return selected


def _reset_metadata(headers: dict[str, Any]) -> dict[str, Any]:
    lower_headers = {key.lower(): value for key, value in headers.items()}
    retry_after = lower_headers.get("retry-after")
    reset_at = lower_headers.get("x-ratelimit-reset") or lower_headers.get("x-ratelimit-reset-at")
    return {
        "known": bool(retry_after or reset_at),
        "wait_hint_present": bool(retry_after or reset_at),
        "header_keys": sorted(headers.keys()),
        "retry_after_seconds": int(retry_after) if isinstance(retry_after, str) and retry_after.isdecimal() else retry_after if isinstance(retry_after, int) else None,
        "ratelimit_reset": reset_at,
    }


MUTATING_OPERATIONS = {"create-run", "create-request"}


if __name__ == "__main__":
    sys.exit(main())
