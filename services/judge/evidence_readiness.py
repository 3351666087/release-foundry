"""Preflight report for private Ashr and semantic judge calibration evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_ASHR_CASE_MAP = Path("fixtures/a2/calibration/ashr_grading_batch_case_map.json")
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

    readiness_checks = {
        "has_calibration_cases": bool(cases),
        "ashr_case_map_covers_cases": not ashr_missing and len(ashr_case_map) == len(cases),
        "ashr_import_commands_documented": True,
        "semantic_harness_ready": bool(semantic_harness_report.get("harness_ready")),
        "semantic_required_fields_documented": bool(REQUIRED_SEMANTIC_FIELDS),
        "semantic_sdk_language_matrix_ready": set(semantic_languages) >= {"python", "typescript"},
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
            "private_input_ref": "docs/evidence/private_refs/a2_ashr_get_run.redacted.json",
            "commands": [
                "python scripts/a2_import_ashr_grading.py --input docs/evidence/private_refs/a2_ashr_get_run.redacted.json --case-map fixtures/a2/calibration/ashr_grading_batch_case_map.json --evidence-ref docs/evidence/private_refs/a2_ashr_get_run.redacted.json --output docs/evidence/private_refs/a2_ashr_grading_import.review.json",
                "python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_ashr_grading_import.review.json --source ashr_grading --min-count 6 --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
                "python scripts/a2_regenerate_fixtures.py --write",
            ],
        },
        "semantic_judge_preflight": {
            "source": "llm_judge",
            "current_available": int(llm_counts.get("available", 0)),
            "current_missing": int(llm_counts.get("missing", 0)),
            "offline_reference_only": llm_offline_only,
            "expected_observation_count": len(cases),
            "expected_reviewed_observation_count": len(cases),
            "required_fields": REQUIRED_SEMANTIC_FIELDS,
            "required_sdk_languages": semantic_harness_report.get("source_matrix", {}).get("required_languages", []),
            "covered_sdk_languages": semantic_harness_report.get("source_matrix", {}).get("covered_languages", []),
            "private_input_ref": "docs/evidence/private_refs/a2_semantic_judge_review.redacted.json",
            "commands": [
                "python scripts/a2_import_semantic_judge.py --input docs/evidence/private_refs/a2_semantic_judge_review.redacted.json --evidence-ref docs/evidence/private_refs/a2_semantic_judge_review.redacted.json --output docs/evidence/private_refs/a2_semantic_judge_import.review.json",
                "python scripts/a2_merge_calibration_observations.py --incoming docs/evidence/private_refs/a2_semantic_judge_import.review.json --source llm_judge --min-count 6 --output fixtures/a2/calibration/a2_g3_calibration_observations.json",
                "python scripts/a2_regenerate_fixtures.py --write",
            ],
        },
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


def _load_case_map(path: str | Path) -> dict[str, str]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _llm_offline_only(calibration_matrix: dict[str, Any]) -> bool:
    providers = set()
    for row in calibration_matrix.get("cost_ledger", []):
        if row.get("source") == "llm_judge":
            providers.update(str(provider) for provider in row.get("provider_counts", {}))
    return providers == {"offline_reference"}
