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
    summarize_generation_request,
    summarize_quota_error,
    utc_now,
)

CALIBRATION_MANIFEST_SCHEMA_VERSION = "ashr.clone.api_calibration_manifest.v1"
PUBLIC_OFFICIAL_API_MANIFEST_SUMMARY_SCHEMA_VERSION = "ashr.clone.public_official_api_manifest_summary.v1"
FIELD_PARITY_PLAN_SCHEMA_VERSION = "ashr.clone.api_field_parity_plan.v1"
API_CALIBRATION_READINESS_PACKET_SCHEMA_VERSION = "ashr.clone.api_calibration_readiness_packet.v1"
PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION = "ashr.clone.api_probe_batch_plan.v1"
PLAN_BATCH_QUOTA_GATE_VALIDATION_SCHEMA_VERSION = "ashr.clone.api_probe_gate_validation.v1"
API_PROBE_TARGET_BINDING_SCHEMA_VERSION = "ashr.clone.api_probe_target_binding.v1"
PLAN_BATCH_QUOTA_GATE_DECISIONS = {"go", "stop", "wait"}
CALIBRATION_QUOTA_GATE_TARGET_OPERATION = "create-request"
DEFAULT_QUOTA_GATE_TTL_SECONDS = 24 * 60 * 60
MIN_QUOTA_OVERRIDE_REASON_CHARS = 12
CALIBRATION_MODALITIES = AGENT_INPUT_PART_TYPES
REPO_ROOT = Path(__file__).resolve().parents[3]
PRIVATE_EVIDENCE_DIR = REPO_ROOT / "docs" / "evidence" / "private_refs"
PUBLIC_API_CALIBRATION_DIR = REPO_ROOT / "docs" / "a1" / "api_calibration"
FIELD_MAP_PATH = PUBLIC_API_CALIBRATION_DIR / "real_api_response_field_map.json"
DEFAULT_PUBLIC_OFFICIAL_API_MANIFEST_SUMMARY_PATH = REPO_ROOT / "docs" / "a1" / "evidence" / "official_api_readonly_manifest_summary.json"
DEFAULT_PRIVATE_OFFICIAL_API_READONLY_MANIFEST_PATH = PRIVATE_EVIDENCE_DIR / "a1_worker_evidence_api_readonly_20260709_133939.json"


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
    allow_nonprivate_output: bool = False


@dataclass(frozen=True, slots=True)
class ModalitySpec:
    modality: str
    accepted_input: str
    generation_option: str | None
    sample_asset: str
    small_batch_phase: str


CALIBRATION_MODALITY_SPECS: dict[str, ModalitySpec] = {
    "text": ModalitySpec("text", "text", None, "one-sentence synthetic prompt", "small-batch"),
    "image": ModalitySpec("image", "image", "generate_images", "1x1 synthetic PNG-equivalent fixture reference", "media-batch-after-text"),
    "audio": ModalitySpec("audio", "audio", "generate_audio", "short synthetic tone/transcript fixture reference", "media-batch-after-text"),
    "file": ModalitySpec("file", "file", "generate_files", "tiny synthetic text file fixture reference", "media-batch-after-text"),
    "video": ModalitySpec("video", "video", "generate_videos", "single-frame synthetic video fixture reference", "media-batch-after-text"),
}


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
    dry_run = not args.execute
    manifest_path = args.output or default_output_path(args.execute)
    enforce_private_output_path(args, manifest_path)
    enforce_private_stdout_policy(args)
    validate_calibration_guards(args)
    quota_gate_summary = enforce_mutating_quota_gate(args)
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
                "output_policy": output_policy(args, manifest_path),
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


def build_field_parity_plan(args: CalibrationArgs | None = None, *, field_map_path: str | Path = FIELD_MAP_PATH) -> JsonDict:
    plan_args = args or CalibrationArgs(modalities=("text",))
    steps = calibration_steps(plan_args)
    if not plan_args.include_mutating:
        steps = [step for step in steps if step.kind != "mutate"]
    field_map = load_json_object(str(field_map_path), "--field-map")
    functions = field_map.get("functions") if isinstance(field_map.get("functions"), Mapping) else {}
    parity_steps = [field_parity_step(step, functions) for step in steps]
    missing_observed = sorted(
        step["function"]
        for step in parity_steps
        if not step.get("observed_response_keys") and step.get("function") != "create_request"
    )
    selected_modalities = selected_calibration_modalities(plan_args) if plan_args.include_mutating else ()
    return redact_sensitive(
        {
            "schema_version": FIELD_PARITY_PLAN_SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source_field_map": _repo_relative_output_path(field_map_path),
            "field_map_version": field_map.get("field_map_version") or ASHR_API_FIELD_MAP_VERSION,
            "official_api_contract": {
                "dispatch": "single POST endpoint with function field",
                "base_url_env": ASHR_LABS_BASE_URL_ENV_VAR,
                "auth_env_vars": [ASHR_API_ENV_VAR, ASHR_LABS_API_ENV_VAR],
                "key_material_source": "environment at execution time only",
                "key_material_logged": False,
            },
            "execution_modes": {
                "default": "dry-run",
                "dry_run_calls_real_api": False,
                "small_batch_requires": ["--execute", "--small-batch", "--max-retries 0"],
                "mutating_requires": ["--include-mutating", "explicit --modality", "--quota-gate-record", "private output path"],
                "paid_media_requires": "--allow-paid-media",
            },
            "output_policy": {
                "public_plan_contains": ["field names", "operation names", "call counts", "guardrail commands"],
                "public_plan_excludes": ["API keys", "raw payload responses", "private evidence contents", "hosted quota values"],
                "real_or_gate_records_private_root": "docs/evidence/private_refs",
                "full_record_stdout_blocked_for_real_or_gate": True,
            },
            "commands": {
                "safe_dry_run_text": "python -B -m packages.sdk.ashr_clone.calibrate --modality text --output docs/evidence/private_refs/a1_python_api_calibration_manifest_dry_run.json",
                "read_only_small_batch": "python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_real.json",
                "mutating_text_small_batch_after_gate": "python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --include-mutating --modality text --quota-gate-record docs/evidence/private_refs/<plan_batch_gate>.json --output docs/evidence/private_refs/a1_python_api_calibration_manifest_real.json",
            },
    "quota_gate": {
        "schema_version": PLAN_BATCH_QUOTA_GATE_SCHEMA_VERSION,
        "target_operation": CALIBRATION_QUOTA_GATE_TARGET_OPERATION,
        "ttl_seconds": DEFAULT_QUOTA_GATE_TTL_SECONDS,
        "expected_modalities": list(expected_calibration_gate_modalities(plan_args)) if plan_args.include_mutating else [],
        "request_fingerprints": calibration_request_fingerprints(plan_args) if plan_args.include_mutating else {},
        "target_bindings": calibration_target_bindings(plan_args) if plan_args.include_mutating else {},
    },
            "modality_matrix": [modality_plan_entry(modality) for modality in selected_modalities],
            "summary": {
                "steps": len(parity_steps),
                "read_steps": sum(1 for step in parity_steps if step.get("kind") == "read"),
                "mutating_steps": sum(1 for step in parity_steps if step.get("kind") == "mutate"),
                "estimated_calls_dry_run": 0,
                "estimated_calls_small_batch": sum(step.estimated_calls for step in steps),
                "modalities": sorted(selected_modalities),
                "missing_observed_functions": missing_observed,
            },
            "steps": parity_steps,
        }
    )


def build_api_calibration_readiness_packet(
    args: CalibrationArgs | None = None,
    *,
    field_map_path: str | Path = FIELD_MAP_PATH,
    evidence_index_path: str | Path | None = PUBLIC_API_CALIBRATION_DIR / "real_api_evidence_index.json",
) -> JsonDict:
    plan_args = args or CalibrationArgs(modalities=("text",))
    field_map = load_json_object(str(field_map_path), "--field-map")
    functions = field_map.get("functions") if isinstance(field_map.get("functions"), Mapping) else {}
    evidence_index: JsonDict = {}
    if evidence_index_path is not None and Path(evidence_index_path).exists():
        evidence_index = load_json_object(str(evidence_index_path), "--evidence-index")
    plan = build_field_parity_plan(plan_args, field_map_path=field_map_path)
    observed_functions = sorted(functions)
    read_only_steps = [step for step in plan.get("steps", []) if isinstance(step, Mapping) and step.get("kind") == "read"]
    read_only_missing = sorted(str(step.get("function")) for step in read_only_steps if not step.get("observed_response_keys"))
    next_read_only_targets = build_next_read_only_calibration_targets(functions)
    return redact_sensitive(
        {
            "schema_version": API_CALIBRATION_READINESS_PACKET_SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source_field_map": _repo_relative_output_path(field_map_path),
            "source_evidence_index": _repo_relative_output_path(evidence_index_path) if evidence_index_path else None,
            "field_map_version": field_map.get("field_map_version") or ASHR_API_FIELD_MAP_VERSION,
            "public_safety": {
                "raw_key_material_present": False,
                "auth_header_present": False,
                "contains_raw_payload_response": False,
                "contains_private_evidence_contents": False,
                "private_evidence_root": "docs/evidence/private_refs",
                "private_evidence_references_only": True,
            },
            "official_api_contract": plan.get("official_api_contract", {}),
            "execution_guardrails": {
                "default_mode": "dry-run",
                "real_read_only_requires": ["--execute", "--small-batch", "--max-retries 0", "private output path"],
                "real_mutating_requires": ["--include-mutating", "explicit --modality", "fresh quota gate", "private output path"],
                "paid_media_requires": "--allow-paid-media",
                "full_record_stdout_blocked_for_real_or_gate": True,
            },
            "observed_surface": {
                "function_count": len(observed_functions),
                "functions": observed_functions,
                "read_only_manifest_step_count": len(read_only_steps),
                "read_only_missing_from_field_map": read_only_missing,
                "private_record_count": evidence_index.get("total_records"),
                "status_counts": evidence_index.get("status_counts", {}),
                "quota_block_count": evidence_index.get("quota_block_count", 0),
            },
            "readiness": {
                "public_packet_ready": True,
                "read_only_small_batch_ready": not read_only_missing,
                "next_read_only_calibration_ready": True,
                "mutating_small_batch_ready": False,
                "reason_mutating_not_ready": "requires a fresh reviewed plan-batch quota gate and explicit modality before any real create-request call",
            },
            "next_read_only_calibration": {
                "purpose": "Refresh official API calibration for public-safe error, usage, and quota shape coverage without mutating hosted state.",
                "mode": "read-only small batch",
                "target_shape_groups": next_read_only_targets,
                "private_evidence_paths": {
                    "manifest": "docs/evidence/private_refs/a1_python_api_calibration_manifest_real_error_usage_quota_<timestamp>.json",
                    "step_records": "docs/evidence/private_refs/a1_python_api_calibration_manifest_real_error_usage_quota_<timestamp>.*.json",
                    "refreshed_private_index_input": "docs/evidence/private_refs/",
                },
                "publishable_outputs": [
                    "docs/a1/api_calibration/real_api_evidence_index.json",
                    "docs/a1/api_calibration/real_api_response_field_map.json",
                    "docs/a1/api_calibration/official_api_readiness_packet.json",
                ],
                "constraints": {
                    "env_only_auth_material": True,
                    "never_print_or_store_key": True,
                    "mutating_calls_allowed": False,
                    "include_mutating_allowed": False,
                    "paid_media_allowed": False,
                    "stdout_full_record_allowed": False,
                    "raw_response_payload_publication_allowed": False,
                    "real_output_root": "docs/evidence/private_refs",
                },
                "acceptance_checks": [
                    "real read-only command uses --execute --small-batch --max-retries 0",
                    "real read-only command omits --include-mutating and --allow-paid-media",
                    "real manifest and step records are written only under docs/evidence/private_refs",
                    "public summaries contain field names/counts/private paths only, never raw payloads or auth material",
                    "refreshed packet records error, usage, and quota target outcomes before any mutating calibration round",
                ],
                "commands": {
                    "dry_run_plan": "python -B -m packages.sdk.ashr_clone.calibrate --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_dry_run_error_usage_quota_<timestamp>.json",
                    "real_read_only_private": "python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_real_error_usage_quota_<timestamp>.json",
                    "regenerate_public_packet": "python -B -c \"from pathlib import Path; import json; from packages.sdk.ashr_clone.calibrate import build_api_calibration_readiness_packet; Path('docs/a1/api_calibration/official_api_readiness_packet.json').write_text(json.dumps(build_api_calibration_readiness_packet(), indent=2, sort_keys=True) + '\\n', encoding='utf-8')\"",
                },
            },
            "gaps": official_api_calibration_gaps(functions, read_only_missing),
            "commands": {
                "generate_public_packet": "python -B -c \"from pathlib import Path; import json; from packages.sdk.ashr_clone.calibrate import build_api_calibration_readiness_packet; Path('docs/a1/api_calibration/official_api_readiness_packet.json').write_text(json.dumps(build_api_calibration_readiness_packet(), indent=2, sort_keys=True) + '\\n', encoding='utf-8')\"",
                "read_only_small_batch": "python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --output docs/evidence/private_refs/a1_python_api_calibration_manifest_real_<timestamp>.json",
                "mutating_text_after_gate": "python -B -m packages.sdk.ashr_clone.calibrate --execute --small-batch --max-retries 0 --include-mutating --modality text --quota-gate-record docs/evidence/private_refs/<plan_batch_gate>.json --output docs/evidence/private_refs/a1_python_api_calibration_manifest_real_<timestamp>.json",
            },
        }
    )


def build_next_read_only_calibration_targets(observed_functions: Mapping[str, Any]) -> list[JsonDict]:
    public_safe_observed_keys_exclude = {"authorization", "headers", "request_headers", "response_headers"}

    def observed_keys(function_name: str, key: str) -> list[str]:
        details = observed_functions.get(function_name)
        if not isinstance(details, Mapping):
            return []
        value = details.get(key)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return sorted(str(item) for item in value if str(item).lower() not in public_safe_observed_keys_exclude)

    return [
        {
            "id": "error_shape_refresh",
            "target_functions": ["init", "get_dataset", "get_run", "get_request", "poll_run", "poll_request"],
            "target_fields": ["error", "error_kind", "status", "message", "detail"],
            "observed_error_keys": sorted({key for function in observed_functions for key in observed_keys(function, "error_keys")}),
            "method": "Use read-only identifiers and intentionally invalid read-only IDs where needed; capture only redacted error envelopes in private records.",
        },
        {
            "id": "usage_shape_refresh",
            "target_functions": ["init", "keep_alive", "list_runs", "list_requests"],
            "target_fields": ["usage", "billing", "plan", "limits", "remaining"],
            "observed_response_keys": sorted({key for function in ("init", "keep_alive", "list_runs", "list_requests") for key in observed_keys(function, "response_keys")}),
            "method": "Prefer session and list endpoints that may expose account, plan, or ledger metadata without creating runs or requests.",
        },
        {
            "id": "quota_shape_refresh",
            "target_functions": ["init", "list_datasets", "list_runs", "list_requests", "list_agents"],
            "target_fields": ["quota", "quota_stop_go", "remaining", "reset_at", "retry_after", "rate_limit"],
            "observed_quota_block_count": sum(
                int(details.get("quota_block_count") or 0)
                for details in observed_functions.values()
                if isinstance(details, Mapping)
            ),
            "method": "Record quota and rate-limit shape names from normal read-only responses and controlled read-only failures; do not attempt to exhaust quota.",
        },
    ]


def official_api_calibration_gaps(observed_functions: Mapping[str, Any], read_only_missing: Sequence[str]) -> list[JsonDict]:
    gaps: list[JsonDict] = []
    if read_only_missing:
        gaps.append(
            {
                "id": "read_only_field_map_missing",
                "severity": "high",
                "summary": "Read-only calibration steps exist without observed response fields in the public field map.",
                "blocked_by": ["official API key", "read-only small-batch execution", "private evidence output"],
                "functions": sorted(read_only_missing),
            }
        )
    for function in ("create_run", "get_run", "list_runs"):
        if function not in observed_functions:
            gaps.append(
                {
                    "id": f"{function}_limited_or_missing",
                    "severity": "medium",
                    "summary": f"{function} coverage is absent from the latest field map and needs a read-only or gated lifecycle follow-up.",
                    "blocked_by": ["safe target identifiers", "private evidence output"],
                    "functions": [function],
                }
            )
    create_request = observed_functions.get("create_request") if isinstance(observed_functions.get("create_request"), Mapping) else {}
    quota_blocks = create_request.get("quota_block_count", 0) if isinstance(create_request, Mapping) else 0
    gaps.append(
        {
            "id": "mutating_create_request_quota_gate",
            "severity": "high",
            "summary": "Real create-request calibration remains blocked until a fresh quota/reset-reviewed plan-batch gate approves the tiny text mutation.",
            "blocked_by": ["reviewed quota/reset evidence", "fresh target binding", "explicit --modality text"],
            "functions": ["create_request"],
            "observed_quota_block_count": quota_blocks,
        }
    )
    gaps.append(
        {
            "id": "media_modalities_unproven",
            "severity": "medium",
            "summary": "Image, audio, file, and video request envelopes are public-planned but should wait for reviewed text mutation evidence before paid media probes.",
            "blocked_by": ["text small-batch result", "--allow-paid-media acknowledgement", "one modality per round"],
            "modalities": ["image", "audio", "file", "video"],
        }
    )
    gaps.append(
        {
            "id": "hosted_surface_not_commercially_complete",
            "severity": "medium",
            "summary": "Official API calibration still does not prove API-key lifecycle, usage ledger, trace ingestion, artifact upload, release evidence, or webhook parity.",
            "blocked_by": ["official docs or observed endpoints", "safe read-only probes", "local control-plane implementation parity"],
            "functions": ["api_keys", "usage", "trace_events", "artifacts", "release_evidence", "webhooks"],
        }
    )
    return gaps


def field_parity_step(step: CalibrationStep, observed_functions: Mapping[str, Any]) -> JsonDict:
    function_aliases = {"health-check": "keep_alive"}
    function = function_aliases.get(step.step_id, "create_request" if step.step_id.startswith("create-request-") else step.step_id.replace("-", "_"))
    observed = observed_functions.get(function) if isinstance(observed_functions.get(function), Mapping) else {}
    return {
        "step_id": step.step_id,
        "kind": step.kind,
        "function": function,
        "modality": step.modality,
        "purpose": step.purpose,
        "estimated_small_batch_calls": step.estimated_calls,
        "dry_run_behavior": "writes planned call record only",
        "observed_response_keys": sorted(str(key) for key in observed.get("response_keys", []) if isinstance(key, str)),
        "observed_error_keys": sorted(str(key) for key in observed.get("error_keys", []) if isinstance(key, str)),
        "observed_response_summary_keys": sorted(str(key) for key in observed.get("response_summary_keys", []) if isinstance(key, str)),
        "observed_top_count_keys": sorted(str(key) for key in observed.get("top_count_keys", []) if isinstance(key, str)),
        "quota_block_count_observed": observed.get("quota_block_count") if isinstance(observed.get("quota_block_count"), int) else None,
        "request_shape": modality_plan_entry(step.modality) if step.modality else None,
        "private_evidence_required_for_raw_payload": True,
    }


def modality_plan_entry(modality: str | None) -> JsonDict | None:
    if modality is None:
        return None
    spec = CALIBRATION_MODALITY_SPECS.get(modality)
    if spec is None:
        return None
    return {
        "modality": spec.modality,
        "accepted_input": spec.accepted_input,
        "generation_option": spec.generation_option,
        "sample_asset": spec.sample_asset,
        "small_batch_phase": spec.small_batch_phase,
        "requires_paid_media_ack": modality != "text",
        "raw_asset_recorded_publicly": False,
    }


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
    spec = CALIBRATION_MODALITY_SPECS[modality]
    generation_options: JsonDict = {
        "generate_audio": spec.generation_option == "generate_audio",
        "generate_files": spec.generation_option == "generate_files",
        "generate_images": spec.generation_option == "generate_images",
        "generate_videos": spec.generation_option == "generate_videos",
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
        "metadata": {
            "dataset_name": f"A1 {modality} API calibration",
            "description": "Generated by A1 env-gated calibration harness.",
            "local_secret_policy": "ASHR_API_KEY read from environment only; no key is logged or stored.",
            "synthetic_asset": spec.sample_asset,
            "small_batch_phase": spec.small_batch_phase,
        },
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


def public_official_api_manifest_summary(manifest: Mapping[str, Any], *, source_path: str | Path | None = None) -> JsonDict:
    steps = manifest.get("steps") if isinstance(manifest.get("steps"), list) else []
    errors = manifest.get("errors") if isinstance(manifest.get("errors"), list) else []
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), Mapping) else {}
    guardrails = manifest.get("guardrails") if isinstance(manifest.get("guardrails"), Mapping) else {}
    output_policy_value = guardrails.get("output_policy") if isinstance(guardrails.get("output_policy"), Mapping) else {}
    env_value = manifest.get("env") if isinstance(manifest.get("env"), Mapping) else {}
    step_summaries = [_public_official_api_step_summary(step) for step in steps if isinstance(step, Mapping)]
    error_summaries = [_public_official_api_error_summary(error) for error in errors if isinstance(error, Mapping)]
    payload = {
        "schema_version": PUBLIC_OFFICIAL_API_MANIFEST_SUMMARY_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "source_private_manifest": _repo_relative_output_path(source_path) if source_path is not None else None,
        "source_private_manifest_present": True,
        "source_schema_version": manifest.get("schema_version") if isinstance(manifest.get("schema_version"), str) else None,
        "mode": manifest.get("mode") if isinstance(manifest.get("mode"), str) else None,
        "dry_run": manifest.get("dry_run") if isinstance(manifest.get("dry_run"), bool) else None,
        "status": manifest.get("status") if isinstance(manifest.get("status"), str) else None,
        "field_map_version": manifest.get("field_map_version") if isinstance(manifest.get("field_map_version"), str) else None,
        "started_at_present": isinstance(manifest.get("started_at"), str),
        "ended_at_present": isinstance(manifest.get("ended_at"), str),
        "duration_ms_present": isinstance(manifest.get("duration_ms"), int),
        "env": {
            "auth_env_present_count": len(env_value.get("auth_env_present")) if isinstance(env_value.get("auth_env_present"), list) else 0,
            "base_url_host": _url_host(env_value.get("base_url")),
        },
        "guardrails": {
            "raw_records_private": guardrails.get("raw_records_private") is True,
            "execute_requires_small_batch": guardrails.get("execute_requires_small_batch") is True,
            "mutating_requires_include_mutating": guardrails.get("mutating_requires_include_mutating") is True,
            "paid_media_requires_allow_paid_media": guardrails.get("paid_media_requires_allow_paid_media") is True,
            "mutating_execute_requires_quota_gate": guardrails.get("mutating_execute_requires_quota_gate") is True,
            "quota_gate_present": isinstance(guardrails.get("quota_gate"), Mapping),
            "output_policy": {
                "private_output_required": output_policy_value.get("private_output_required") is True,
                "output_is_private": output_policy_value.get("output_is_private") is True,
                "sink": output_policy_value.get("sink") if isinstance(output_policy_value.get("sink"), str) else None,
                "private_root": output_policy_value.get("private_root") if isinstance(output_policy_value.get("private_root"), str) else "docs/evidence/private_refs",
                "full_record_stdout_blocked": output_policy_value.get("full_record_stdout_blocked") is True,
            },
        },
        "summary": {
            "total_steps": _int_or_zero(summary.get("total_steps"), len(step_summaries)),
            "read_steps": _int_or_zero(summary.get("read_steps"), sum(1 for step in step_summaries if step.get("kind") == "read")),
            "mutating_steps": _int_or_zero(summary.get("mutating_steps"), sum(1 for step in step_summaries if step.get("kind") == "mutate")),
            "ok_or_planned_steps": _int_or_zero(summary.get("ok_or_planned_steps"), sum(1 for step in step_summaries if step.get("status") in {"ok", "planned"})),
            "error_steps": _int_or_zero(summary.get("error_steps"), len(error_summaries)),
            "estimated_calls": _int_or_zero(summary.get("estimated_calls"), sum(_int_or_zero(step.get("estimated_calls"), 0) for step in step_summaries)),
            "modalities": sorted(str(modality) for modality in summary.get("modalities", []) if isinstance(modality, str)) if isinstance(summary.get("modalities"), list) else [],
            "quota_block_count": _int_or_zero(summary.get("quota_block_count"), sum(1 for step in step_summaries if step.get("quota_blocked") is True)),
        },
        "step_summaries": step_summaries,
        "error_summaries": error_summaries,
        "public_safety": {
            "redacted_summary_fields_only": True,
            "raw_payload_values_included": False,
            "header_values_included": False,
            "request_parameter_values_included": False,
            "step_record_locations_included": False,
            "auth_env_names_included": False,
            "raw_key_material_present": False,
            "private_payload_contents_present": False,
        },
    }
    return redact_sensitive(payload)


def public_official_api_manifest_summary_from_file(path: str | Path = DEFAULT_PRIVATE_OFFICIAL_API_READONLY_MANIFEST_PATH) -> JsonDict:
    source = Path(path)
    if not source.exists():
        return {
            "schema_version": PUBLIC_OFFICIAL_API_MANIFEST_SUMMARY_SCHEMA_VERSION,
            "generated_at": utc_now(),
            "source_private_manifest": _repo_relative_output_path(source),
            "source_private_manifest_present": False,
            "status": "missing",
            "summary": {
                "total_steps": 0,
                "read_steps": 0,
                "mutating_steps": 0,
                "ok_or_planned_steps": 0,
                "error_steps": 0,
                "estimated_calls": 0,
                "modalities": [],
                "quota_block_count": 0,
            },
            "step_summaries": [],
            "error_summaries": [],
            "public_safety": {
                "redacted_summary_fields_only": True,
                "raw_payload_values_included": False,
                "header_values_included": False,
                "request_parameter_values_included": False,
                "step_record_locations_included": False,
                "auth_env_names_included": False,
                "raw_key_material_present": False,
                "private_payload_contents_present": False,
            },
        }
    manifest = load_json_object(str(source), "--private-official-api-manifest")
    return public_official_api_manifest_summary(manifest, source_path=source)


def write_public_official_api_manifest_summary(
    *,
    input_path: str | Path = DEFAULT_PRIVATE_OFFICIAL_API_READONLY_MANIFEST_PATH,
    output_path: str | Path = DEFAULT_PUBLIC_OFFICIAL_API_MANIFEST_SUMMARY_PATH,
) -> JsonDict:
    summary = public_official_api_manifest_summary_from_file(input_path)
    write_json(output_path, summary)
    return summary


def _public_official_api_step_summary(step: Mapping[str, Any]) -> JsonDict:
    quota = step.get("quota") if isinstance(step.get("quota"), Mapping) else {}
    top_counts = step.get("top_counts") if isinstance(step.get("top_counts"), Mapping) else {}
    return redact_sensitive(
        {
            "step_id": step.get("step_id") if isinstance(step.get("step_id"), str) else None,
            "kind": step.get("kind") if isinstance(step.get("kind"), str) else None,
            "modality": step.get("modality") if isinstance(step.get("modality"), str) else None,
            "function": step.get("function") if isinstance(step.get("function"), str) else None,
            "dry_run": step.get("dry_run") if isinstance(step.get("dry_run"), bool) else None,
            "status": step.get("status") if isinstance(step.get("status"), str) else None,
            "status_code": step.get("status_code") if isinstance(step.get("status_code"), int) else None,
            "attempts": step.get("attempts") if isinstance(step.get("attempts"), int) else None,
            "estimated_calls": step.get("estimated_calls") if isinstance(step.get("estimated_calls"), int) else None,
            "response_keys": sorted(str(key) for key in step.get("response_keys", []) if isinstance(key, str)) if isinstance(step.get("response_keys"), list) else [],
            "response_status": step.get("response_status") if isinstance(step.get("response_status"), str) else None,
            "response_summary_keys": sorted(str(key) for key in step.get("response_summary_keys", []) if isinstance(key, str)) if isinstance(step.get("response_summary_keys"), list) else [],
            "top_counts": {str(key): value for key, value in top_counts.items() if isinstance(key, str) and isinstance(value, int)},
            "next_cursor_present": step.get("next_cursor") is not None,
            "error_keys": sorted(str(key) for key in step.get("error_keys", []) if isinstance(key, str)) if isinstance(step.get("error_keys"), list) else [],
            "error_kind": step.get("error_kind") if isinstance(step.get("error_kind"), str) else None,
            "quota_blocked": quota.get("blocked") is True,
            "quota_resource": quota.get("resource") if isinstance(quota.get("resource"), str) else None,
            "quota_remaining_present": quota.get("remaining") is not None,
        }
    )


def _public_official_api_error_summary(error: Mapping[str, Any]) -> JsonDict:
    quota = error.get("quota") if isinstance(error.get("quota"), Mapping) else {}
    return redact_sensitive(
        {
            "step_id": error.get("step_id") if isinstance(error.get("step_id"), str) else None,
            "status": error.get("status") if isinstance(error.get("status"), str) else None,
            "status_code": error.get("status_code") if isinstance(error.get("status_code"), int) else None,
            "error_kind": error.get("error_kind") if isinstance(error.get("error_kind"), str) else None,
            "error_keys": sorted(str(key) for key in error.get("error_keys", []) if isinstance(key, str)) if isinstance(error.get("error_keys"), list) else [],
            "quota_blocked": quota.get("blocked") is True,
            "quota_resource": quota.get("resource") if isinstance(quota.get("resource"), str) else None,
            "quota_remaining_present": quota.get("remaining") is not None,
        }
    )


def _int_or_zero(value: Any, fallback: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return fallback


def _url_host(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(value)
    return parsed.netloc or None


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
    if mutating_quota_gate_required(args) and not args.modalities:
        raise CalibrationUsageError("mutating real API calibration requires explicit --modality selection; dry-run may enumerate all modalities")


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
    if "target_binding" in plan:
        binding.update(validate_target_binding(plan.get("target_binding"), args, issues))
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


def validate_target_binding(value: Any, args: CalibrationArgs, issues: list[JsonDict]) -> JsonDict:
    expected = calibration_target_bindings(args)
    binding: JsonDict = {"target_binding": target_binding_summary(value), "expected_target_bindings": {key: target_binding_summary(item) for key, item in expected.items()}}
    if not isinstance(value, Mapping):
        issues.append({"code": "missing_target_binding", "message": "quota gate target_binding must be an object when present"})
        return redact_sensitive(binding)

    selected_modalities = selected_calibration_modalities(args)
    if len(selected_modalities) != 1:
        issues.append({"code": "target_binding_ambiguous", "message": "quota gate target_binding can only bind one selected calibrator modality; use request_fingerprint modality map for multi-modality gates"})
        return redact_sensitive(binding)

    expected_binding = expected[selected_modalities[0]]
    actual_fingerprint = value.get("fingerprint")
    expected_fingerprint = expected_binding.get("fingerprint")
    if value.get("schema_version") != API_PROBE_TARGET_BINDING_SCHEMA_VERSION:
        issues.append({"code": "invalid_target_binding_schema", "message": f"quota gate target_binding.schema_version must be {API_PROBE_TARGET_BINDING_SCHEMA_VERSION}"})
    if not isinstance(actual_fingerprint, str) or actual_fingerprint != expected_fingerprint:
        issues.append({"code": "target_binding_mismatch", "message": "quota gate target_binding.fingerprint does not match the current calibrator request payload and execution guardrails"})
        return redact_sensitive(binding)

    for field in (
        "target_operation",
        "request_fingerprint",
        "request_input_schema_fingerprint",
        "request_input_schema_source",
        "allow_media_generation",
        "allow_non_text_inputs",
        "max_request_variations",
        "small_batch_size",
        "batch_size",
        "modalities",
    ):
        if value.get(field) != expected_binding.get(field):
            issues.append({"code": "target_binding_field_mismatch", "message": f"quota gate target_binding.{field} does not match the current calibrator request"})
            break
    return redact_sensitive(binding)


def calibration_request_fingerprints(args: CalibrationArgs) -> JsonDict:
    return {modality: calibration_request_fingerprint(modality) for modality in selected_calibration_modalities(args)}


def calibration_request_fingerprint(modality: str) -> str:
    payload = json.dumps(request_for_modality(modality), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def calibration_target_bindings(args: CalibrationArgs) -> JsonDict:
    return {modality: calibration_target_binding(modality, args) for modality in selected_calibration_modalities(args)}


def calibration_target_binding(modality: str, args: CalibrationArgs) -> JsonDict:
    request = request_for_modality(modality)
    preflight = summarize_generation_request(request)
    modality_sequence = calibration_modality_sequence(preflight)
    modalities = [item["modality"] for item in modality_sequence]
    media_modalities = [item["modality"] for item in modality_sequence if item.get("kind") != "text"]
    request_fingerprint = stable_sha256(request)
    components = {
        "target_operation": CALIBRATION_QUOTA_GATE_TARGET_OPERATION,
        "request_fingerprint": request_fingerprint,
        "request_input_schema_fingerprint": None,
        "request_input_schema_source": "client_default",
        "allow_media_generation": bool(args.allow_paid_media),
        "allow_non_text_inputs": True,
        "max_request_variations": 1,
        "small_batch_size": 1,
        "batch_size": 1,
        "modalities": modalities,
        "media_modalities": media_modalities,
        "text_first_small_batch": bool("text" in modalities and media_modalities),
    }
    return redact_sensitive(
        {
            "schema_version": API_PROBE_TARGET_BINDING_SCHEMA_VERSION,
            "target_operation": CALIBRATION_QUOTA_GATE_TARGET_OPERATION,
            "binding_scope": "request-payload",
            "request_fingerprint": request_fingerprint,
            "request_input_schema_fingerprint": None,
            "request_input_schema_source": "client_default",
            "allow_media_generation": bool(args.allow_paid_media),
            "allow_non_text_inputs": True,
            "max_request_variations": 1,
            "small_batch_size": 1,
            "batch_size": 1,
            "modalities": modalities,
            "media_modalities": media_modalities,
            "text_first_small_batch": bool("text" in modalities and media_modalities),
            "modality_sequence": modality_sequence,
            "fingerprint": stable_sha256(components),
            "fingerprint_fields": sorted(components.keys()),
            "raw_request_not_recorded": True,
        }
    )


def calibration_modality_sequence(preflight: Mapping[str, Any]) -> list[JsonDict]:
    enabled_modalities: dict[str, set[str]] = {}
    accepted_flags = preflight.get("accepted_input_flags") if isinstance(preflight.get("accepted_input_flags"), Mapping) else {}
    for modality in ("text", "image", "audio", "file", "video", "conversation"):
        if accepted_flags.get(modality):
            enabled_modalities.setdefault(modality, set()).add("accepted_inputs")
    media_generation = preflight.get("media_generation") if isinstance(preflight.get("media_generation"), Mapping) else {}
    for generated_name, modality in {"audio": "audio", "files": "file", "images": "image", "videos": "video", "simulations": "simulation"}.items():
        if media_generation.get(generated_name):
            enabled_modalities.setdefault(modality, set()).add("media_generation")
    if not enabled_modalities:
        enabled_modalities["text"] = {"default"}

    sequence: list[JsonDict] = []
    for modality in ("text", "image", "audio", "file", "video", "conversation", "simulation"):
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


def target_binding_summary(value: Any) -> JsonDict | None:
    if not isinstance(value, Mapping):
        return None
    fields = (
        "schema_version",
        "target_operation",
        "binding_scope",
        "fingerprint",
        "request_fingerprint",
        "request_input_schema_fingerprint",
        "request_input_schema_source",
        "allow_media_generation",
        "allow_non_text_inputs",
        "max_request_variations",
        "small_batch_size",
        "batch_size",
        "modalities",
        "raw_request_not_recorded",
    )
    return redact_sensitive({field: value.get(field) for field in fields if field in value})


def stable_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
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
    return str(PRIVATE_EVIDENCE_DIR / f"a1_python_api_calibration_manifest_{'real' if execute else 'dry_run'}.json")


def enforce_private_stdout_policy(args: CalibrationArgs) -> None:
    if args.print_record and _requires_private_output(args) and not args.allow_nonprivate_output:
        raise CalibrationUsageError("--print-record is disabled for real API and gate evidence; use the JSON file under docs/evidence/private_refs or pass --allow-nonprivate-output only for synthetic tests")


def enforce_private_output_path(args: CalibrationArgs, output: str | Path) -> None:
    if args.allow_nonprivate_output or not _requires_private_output(args):
        return
    if _is_private_output_path(output):
        return
    raise CalibrationUsageError("--output for real API and gate evidence must stay under docs/evidence/private_refs; pass --allow-nonprivate-output only for synthetic tests")


def output_policy(args: CalibrationArgs, output: str | Path) -> JsonDict:
    required = _requires_private_output(args)
    private = _is_private_output_path(output)
    return {
        "schema_version": "ashr.clone.output_policy.v1",
        "private_output_required": required,
        "allow_nonprivate_output": bool(args.allow_nonprivate_output),
        "nonprivate_output_override_used": bool(required and args.allow_nonprivate_output and not private),
        "output_is_private": private,
        "sink": "private_file" if private else "nonprivate_file",
        "private_root": "docs/evidence/private_refs",
        "resolved_under_repo": _repo_relative_output_path(output),
        "full_record_stdout_blocked": bool(required and not args.allow_nonprivate_output),
    }


def _repo_relative_output_path(path: str | Path) -> str:
    target = _resolve_output_path(path)
    try:
        return target.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return "<outside-repo>"


def _requires_private_output(args: CalibrationArgs) -> bool:
    return bool(args.execute or args.quota_gate_record or args.allow_quota_override)


def _is_private_output_path(path: str | Path) -> bool:
    root = PRIVATE_EVIDENCE_DIR.resolve()
    target = _resolve_output_path(path)
    if target == root or target.is_dir():
        return False
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_output_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


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
    parser.add_argument("--allow-nonprivate-output", action="store_true", help="Allow protected real API or gate evidence outside docs/evidence/private_refs for synthetic tests only.")
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
        allow_nonprivate_output=ns.allow_nonprivate_output,
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
