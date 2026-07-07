"""Preflight report for private Ashr and semantic judge calibration evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_ASHR_CASE_MAP = Path("fixtures/a2/calibration/ashr_grading_batch_case_map.json")
DEFAULT_A1_REAL_API_EVIDENCE_INDEX = Path("docs/a1/api_calibration/real_api_evidence_index.json")
DEFAULT_A2_REAL_API_SMOKE = Path("docs/evidence/a2_real_api_smoke.json")
REQUIRED_ASHR_REVIEW_FIELDS = [
    "metadata.review_status",
    "evidence_ref",
]
REQUIRED_SEMANTIC_FIELDS = [
    "case_id",
    "scenario_id",
    "provider",
    "model",
    "prompt_template_id",
    "prompt_hash",
    "response_hash",
    "review_status",
    "sdk_language",
    "cost.prompt_tokens",
    "cost.completion_tokens",
    "cost.estimated_usd",
    "output.passed",
    "output.primary_failure_class",
    "output.score",
    "output.confidence",
    "output.rationale",
    "output.evidence_refs",
]


def build_evidence_readiness_report(
    calibration_matrix: dict[str, Any],
    batch_plan_report: dict[str, Any],
    semantic_harness_report: dict[str, Any],
    *,
    ashr_case_map_path: str | Path = DEFAULT_ASHR_CASE_MAP,
    a1_real_api_evidence_index_path: str | Path = DEFAULT_A1_REAL_API_EVIDENCE_INDEX,
    official_sdk_smoke_path: str | Path = DEFAULT_A2_REAL_API_SMOKE,
) -> dict[str, Any]:
    """Describe what private evidence is still needed before C3/C4 can turn green."""
    cases = list(calibration_matrix.get("cases", []))
    case_ids = [str(case.get("case_id", "")) for case in cases]
    ashr_case_map = _load_case_map(ashr_case_map_path)
    mapped_case_ids = set(str(case_id) for case_id in ashr_case_map.values())
    ashr_missing = sorted(set(case_ids) - mapped_case_ids)
    semantic_languages = sorted(
        chain.get("language")
        for chain in semantic_harness_report.get("source_matrix", {}).get("official_sdk_chains", [])
        if chain.get("language")
    )
    source_coverage = calibration_matrix.get("source_coverage", {})
    ashr_counts = source_coverage.get("ashr_grading", {})
    llm_counts = source_coverage.get("llm_judge", {})
    llm_offline_only = _llm_offline_only(calibration_matrix)
    ashr_import_commands = [
        "python scripts/a2_scan_ashr_grading_evidence.py --input docs/evidence/private_refs/a2_ashr_get_run.redacted.json --case-map fixtures/a2/calibration/ashr_grading_batch_case_map.json",
        "python scripts/a2_import_ashr_grading.py --input docs/evidence/private_refs/a2_ashr_get_run.redacted.json --case-map fixtures/a2/calibration/ashr_grading_batch_case_map.json --evidence-ref docs/evidence/private_refs/a2_ashr_get_run.redacted.json --review-status reviewed --output docs/evidence/private_refs/a2_ashr_grading_import.review.json",
        "python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_ashr_grading_import.review.json --source ashr_grading --min-count 6 --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "python scripts/a2_regenerate_fixtures.py --write",
    ]
    semantic_import_commands = [
        "python scripts/a2_build_semantic_judge_collection_packet.py --check",
        "python scripts/a2_import_semantic_judge.py --input docs/evidence/private_refs/a2_semantic_judge_review.redacted.json --evidence-ref docs/evidence/private_refs/a2_semantic_judge_review.redacted.json --output docs/evidence/private_refs/a2_semantic_judge_import.review.json",
        "python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_semantic_judge_import.review.json --source llm_judge --min-count 6 --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "python scripts/a2_regenerate_fixtures.py --write",
    ]
    semantic_risk = semantic_harness_report.get("risk_assessment", {})
    a1_real_api_evidence = _a1_real_api_evidence_summary(a1_real_api_evidence_index_path)
    official_sdk_smoke = _official_sdk_smoke_summary(official_sdk_smoke_path)

    readiness_checks = {
        "has_calibration_cases": bool(cases),
        "ashr_case_map_covers_cases": not ashr_missing and len(ashr_case_map) == len(cases),
        "ashr_import_commands_documented": True,
        "semantic_harness_ready": bool(semantic_harness_report.get("harness_ready")),
        "semantic_false_positive_tracking_ready": bool(semantic_risk.get("tracking_ready")),
        "semantic_required_fields_documented": bool(REQUIRED_SEMANTIC_FIELDS),
        "semantic_sdk_language_matrix_ready": set(semantic_languages) >= {"python", "typescript"},
        "official_sdk_smoke_readonly_ok": bool(official_sdk_smoke.get("read_only_reachable")),
        "private_payload_boundary_documented": True,
    }

    return {
        "schema_version": "a2.evidence_readiness.v1",
        "report_id": "a2_g3_evidence_readiness",
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "status": "awaiting_private_evidence",
        "ready_for_external_collection": all(readiness_checks.values()),
        "readiness_checks": readiness_checks,
        "calibration_case_count": len(cases),
        "calibration_cases": [
            {
                "case_id": case.get("case_id", ""),
                "scenario_id": case.get("scenario_id", ""),
                "fixture_ref": case.get("fixture_ref", ""),
                "calibration_focus": case.get("calibration_focus", []),
            }
            for case in cases
        ],
        "ashr_grading_preflight": {
            "source": "ashr_grading",
            "current_available": int(ashr_counts.get("available", 0)),
            "current_missing": int(ashr_counts.get("missing", len(cases))),
            "expected_observation_count": len(cases),
            "case_map_path": Path(ashr_case_map_path).as_posix(),
            "case_map_count": len(ashr_case_map),
            "case_map_covers_all_calibration_cases": not ashr_missing and len(ashr_case_map) == len(cases),
            "case_map_missing_case_ids": ashr_missing,
            "expected_reviewed_observation_count": len(cases),
            "required_review_fields": REQUIRED_ASHR_REVIEW_FIELDS,
            "private_input_ref": "docs/evidence/private_refs/a2_ashr_get_run.redacted.json",
            "commands": ashr_import_commands,
        },
        "a1_real_api_evidence": a1_real_api_evidence,
        "official_sdk_smoke": official_sdk_smoke,
        "ashr_public_merge_gate": _ashr_public_merge_gate(cases, ashr_counts, len(cases), ashr_import_commands),
        "semantic_judge_preflight": {
            "source": "llm_judge",
            "current_available": int(llm_counts.get("available", 0)),
            "current_missing": int(llm_counts.get("missing", 0)),
            "offline_reference_only": llm_offline_only,
            "expected_observation_count": len(cases),
            "expected_reviewed_observation_count": len(cases),
            "reviewed_live_observation_count": int(semantic_harness_report.get("reviewed_live_observation_count", 0)),
            "missing_reviewed_live_observation_count": int(
                semantic_harness_report.get("missing_reviewed_live_observation_count", len(cases))
            ),
            "reviewed_live_sdk_languages": semantic_harness_report.get("reviewed_live_sdk_languages", []),
            "reviewed_live_required_metadata_fields": semantic_harness_report.get(
                "reviewed_live_required_metadata_fields", []
            ),
            "risk_assessment_status": semantic_risk.get("status", "unknown"),
            "false_positive_tracking_ready": bool(semantic_risk.get("tracking_ready")),
            "false_positive_candidate_count": int(semantic_risk.get("false_positive_candidate_count", 0)),
            "false_negative_candidate_count": int(semantic_risk.get("false_negative_candidate_count", 0)),
            "failure_class_drift_candidate_count": int(semantic_risk.get("failure_class_drift_candidate_count", 0)),
            "score_delta_review_count": int(semantic_risk.get("score_delta_review_count", 0)),
            "risk_case_count": int(semantic_risk.get("risk_case_count", 0)),
            "required_fields": REQUIRED_SEMANTIC_FIELDS,
            "required_sdk_languages": semantic_harness_report.get("source_matrix", {}).get("required_languages", []),
            "covered_sdk_languages": semantic_harness_report.get("source_matrix", {}).get("covered_languages", []),
            "private_input_ref": "docs/evidence/private_refs/a2_semantic_judge_review.redacted.json",
            "collection_packet_ref": "fixtures/a2/calibration/a2_semantic_judge_collection_packet.json",
            "commands": semantic_import_commands,
        },
        "semantic_live_merge_gate": _semantic_live_merge_gate(
            llm_counts,
            llm_offline_only,
            len(cases),
            semantic_harness_report,
            semantic_import_commands,
        ),
        "batch_plan_refs": [
            batch.get("batch_id", "")
            for batch in batch_plan_report.get("batches", [])
            if batch.get("requires_private_evidence")
        ],
        "redaction_policy": {
            "raw_private_path": "docs/evidence/private_refs/",
            "commit_only": [
                "reviewed observation summaries",
                "provider/model names",
                "prompt and response hashes",
                "cost totals",
                "confidence and review status",
                "private evidence refs",
            ],
            "never_commit": ["API keys", "raw prompts", "raw model responses", "raw account payloads"],
        },
        "metadata": {
            "deterministic": True,
            "purpose": "Make C3/C4 evidence collection auditable without committing private payloads.",
        },
    }


def _semantic_live_merge_gate(
    llm_counts: dict[str, Any],
    llm_offline_only: bool,
    expected_count: int,
    semantic_harness_report: dict[str, Any],
    commands: list[str],
) -> dict[str, Any]:
    current_available = int(llm_counts.get("available", 0))
    live_model_evidence = bool(semantic_harness_report.get("live_model_evidence_available"))
    reviewed_count = int(semantic_harness_report.get("reviewed_live_observation_count", 0))
    merged = expected_count > 0 and current_available >= expected_count and live_model_evidence and not llm_offline_only
    if merged:
        status = "audited_live_model_evidence"
    elif llm_offline_only:
        status = "offline_reference_only"
    else:
        status = "not_audited"
    return {
        "source": "llm_judge",
        "status": status,
        "audited_live_evidence_merged": merged,
        "safe_to_mark_c4_met": merged,
        "current_public_observation_count": current_available,
        "audited_public_observation_count": reviewed_count if merged else 0,
        "reviewed_live_observation_count": reviewed_count,
        "missing_audited_observation_count": max(0, expected_count - reviewed_count),
        "expected_reviewed_observation_count": expected_count,
        "offline_reference_only": llm_offline_only,
        "live_model_evidence_available": live_model_evidence,
        "public_matrix_path": "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "reviewed_private_import_ref": "docs/evidence/private_refs/a2_semantic_judge_import.review.json",
        "blocking_reason": ""
        if merged
        else "Audited semantic judge observations must replace offline references before C4 is met.",
        "required_commands": commands,
    }


def _ashr_public_merge_gate(
    cases: list[dict[str, Any]],
    ashr_counts: dict[str, Any],
    expected_count: int,
    commands: list[str],
) -> dict[str, Any]:
    current_available = int(ashr_counts.get("available", 0))
    current_missing = int(ashr_counts.get("missing", expected_count))
    reviewed_count = _reviewed_ashr_count(cases)
    count_complete = expected_count > 0 and current_available >= expected_count and current_missing == 0
    merged = count_complete and reviewed_count >= expected_count
    status = "merged" if merged else "merged_unreviewed" if count_complete else "not_merged"
    return {
        "source": "ashr_grading",
        "status": status,
        "public_matrix_merged": merged,
        "safe_to_mark_c3_met": merged,
        "current_public_observation_count": current_available,
        "merged_public_observation_count": reviewed_count if merged else 0,
        "reviewed_public_observation_count": reviewed_count,
        "missing_public_observation_count": current_missing,
        "missing_reviewed_observation_count": max(0, expected_count - reviewed_count),
        "required_public_observation_count": expected_count,
        "expected_reviewed_observation_count": expected_count,
        "required_review_fields": REQUIRED_ASHR_REVIEW_FIELDS,
        "public_matrix_path": "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        "reviewed_private_import_ref": "docs/evidence/private_refs/a2_ashr_grading_import.review.json",
        "blocking_reason": ""
        if merged
        else "Reviewed Ashr grading observations with review_status=reviewed and evidence_ref must be imported, merged, and regenerated before C3 is met.",
        "required_commands": commands,
    }


def _reviewed_ashr_count(cases: list[dict[str, Any]]) -> int:
    return sum(
        1
        for case in cases
        if _is_reviewed_ashr_source(case.get("sources", {}).get("ashr_grading", {}))
    )


def _is_reviewed_ashr_source(source: dict[str, Any]) -> bool:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return (
        source.get("available") is True
        and str(source.get("evidence_ref", "")).strip() != ""
        and str(metadata.get("review_status", "")).lower() == "reviewed"
    )


def _load_case_map(path: str | Path) -> dict[str, str]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _a1_real_api_evidence_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {
            "available": False,
            "index_path": target.as_posix(),
            "reason": "A1 public real API evidence index is not available yet.",
            "c3_grading_ready": False,
        }

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {
            "available": False,
            "index_path": target.as_posix(),
            "reason": "A1 public real API evidence index is not a JSON object.",
            "c3_grading_ready": False,
        }

    records = [record for record in payload.get("records", []) if isinstance(record, dict)]
    real_ok_functions = sorted(
        {
            str(record.get("function"))
            for record in records
            if record.get("dry_run") is False and record.get("status") == "ok" and record.get("function")
        }
    )
    mutating_functions = sorted(
        {
            str(record.get("function"))
            for record in records
            if str(record.get("function", "")).startswith("create_")
        }
    )
    real_records = [record for record in records if record.get("dry_run") is False]
    real_read_records = [
        record
        for record in real_records
        if str(record.get("function", "")).startswith(("get_", "list_"))
        or record.get("function") in {"init", "keep_alive"}
    ]
    real_create_request_records = [
        record for record in real_records if record.get("function") == "create_request"
    ]
    real_quota_records = [
        record for record in real_records if isinstance(record.get("quota"), dict) and record["quota"].get("blocked")
    ]
    c3_candidate_records = [
        record
        for record in records
        if record.get("function") in {"get_run", "list_runs"} and record.get("dry_run") is False
    ]
    return {
        "available": True,
        "index_path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "label": str(payload.get("label", "")),
        "field_map_version": str(payload.get("field_map_version", "")),
        "total_records": int(payload.get("total_records", len(records))),
        "status_counts": payload.get("status_counts", {}),
        "function_counts": payload.get("function_counts", {}),
        "quota_block_count": int(payload.get("quota_block_count", 0)),
        "real_ok_functions": real_ok_functions,
        "mutating_functions_present": mutating_functions,
        "real_record_count": len(real_records),
        "real_read_status_counts": _count_records(real_read_records, "status"),
        "real_create_request_status_counts": _count_records(real_create_request_records, "status"),
        "real_create_request_error_kind_counts": _count_records(real_create_request_records, "error_kind"),
        "real_quota_gate": _quota_gate_summary(real_quota_records),
        "c3_candidate_record_count": len(c3_candidate_records),
        "c3_grading_ready": False,
        "notes": [
            "A1 index is public-safe evidence of API reachability and field shapes, not an Ashr grading import.",
            "Create-request records are commercial API shape evidence; they do not count as server-side grading.",
            "C3 still requires scanner-confirmed 6/6 A2 grading cases and reviewed ashr_grading rows before public merge.",
        ],
    }


def _count_records(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(key)
        if value is None:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _quota_gate_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    quota_keys = sorted(
        {
            str(key)
            for record in records
            if isinstance(record.get("quota"), dict)
            for key in record["quota"].get("quota_keys", [])
        }
    )
    functions = sorted({str(record.get("function")) for record in records if record.get("function")})
    paths = sorted(str(record.get("path")) for record in records if record.get("path"))
    return {
        "blocked": bool(records),
        "blocked_count": len(records),
        "blocked_functions": functions,
        "create_request_blocked": "create_request" in functions,
        "quota_keys": quota_keys,
        "private_record_refs": paths,
        "public_action": (
            "Increase or reset hosted request quota before additional mutating create_request calibration."
            if "create_request" in functions
            else "No mutating request quota gate is currently visible in public-safe evidence."
        ),
    }


def _official_sdk_smoke_summary(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {
            "available": False,
            "path": target.as_posix(),
            "read_only_reachable": False,
            "reason": "A2 official SDK smoke summary is not available yet.",
        }

    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {
            "available": False,
            "path": target.as_posix(),
            "read_only_reachable": False,
            "reason": "A2 official SDK smoke summary is not a JSON object.",
        }

    calls = [call for call in payload.get("calls", []) if isinstance(call, dict)]
    ok_count = sum(1 for call in calls if call.get("status") == "ok")
    return {
        "available": True,
        "path": target.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "generated_at": str(payload.get("generated_at", "")),
        "sdk_source": str(payload.get("sdk_source", "")),
        "base_url": str(payload.get("base_url", "")),
        "api_call_count": int(payload.get("api_call_count", len(calls))),
        "ok_call_count": ok_count,
        "error_call_count": sum(1 for call in calls if call.get("status") != "ok"),
        "call_status_counts": _count_records(calls, "status"),
        "call_names": sorted(str(call.get("name")) for call in calls if call.get("name")),
        "all_required_calls_reached": bool(payload.get("all_required_calls_reached")),
        "read_only_reachable": bool(calls) and ok_count == len(calls) and bool(payload.get("all_required_calls_reached")),
        "notes": [
            "This is a redacted official ashr_labs SDK smoke summary, separate from clone API calibration.",
            "It proves current authenticated read/list reachability but does not count as C3 server-side grading evidence.",
        ],
    }


def _llm_offline_only(calibration_matrix: dict[str, Any]) -> bool:
    providers = set()
    for row in calibration_matrix.get("cost_ledger", []):
        if row.get("source") == "llm_judge":
            providers.update(str(provider) for provider in row.get("provider_counts", {}))
    return providers == {"offline_reference"}
