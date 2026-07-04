"""Quota-aware batch plan for A2 commercial calibration."""

from __future__ import annotations

from typing import Any


def build_batch_plan_report(
    coverage_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    case_book_report: dict[str, Any] | None = None,
    sdk_parity_report: dict[str, Any] | None = None,
    semantic_harness_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic C2 plan before paid Ashr or live LLM calibration."""
    calibration_cases = calibration_matrix.get("cases", [])
    case_book_count = int((case_book_report or {}).get("regression_case_count", 0))
    sdk_languages = list((sdk_parity_report or {}).get("required_languages", []))
    batches = [
        _batch(
            "local_full_pack_regression",
            "local",
            int(coverage_report.get("scenario_count", 0)),
            ["local_judge", "coverage_report"],
            "Run the full scenario pack through deterministic A2 local judges.",
            ["packages/scenarios/a2_g3_full_pack.json", "fixtures/a2/results/a2_g3_grade_results.json"],
        ),
        _batch(
            "sdk_parity_smoke",
            "local",
            len(sdk_languages),
            ["python_sdk", "typescript_sdk", "local_judge"],
            "Keep both official SDK-language entrypoints compatible with A2 runner input.",
            ["fixtures/a2/results/a2_sdk_parity_report.json"],
        ),
        _batch(
            "ashr_grading_tiny_calibration",
            "paid_api_private_evidence",
            len(calibration_cases),
            ["ashr_grading", "local_judge"],
            "Collect reviewed server-side Ashr grading for the six C3 calibration cases.",
            [
                "fixtures/a2/calibration/ashr_grading_batch_case_map.json",
                "scripts/a2_import_ashr_grading.py",
                "scripts/a2_merge_calibration_observations.py",
            ],
            requires_private_evidence=True,
        ),
        _batch(
            "semantic_llm_judge_audit",
            "model_call_private_evidence",
            len(calibration_cases),
            ["llm_judge", "local_judge", "python_sdk", "typescript_sdk"],
            "Replace offline LLM references with audited prompt/model/cost observations across both SDK chains.",
            _semantic_evidence_refs(semantic_harness_report),
            requires_private_evidence=True,
        ),
        _batch(
            "case_book_regression_replay",
            "local",
            case_book_count,
            ["case_book", "regression_suite", "local_judge"],
            "Replay every disagreement seed so judge-boundary regressions remain visible.",
            ["fixtures/a2/results/a2_case_book.json"],
        ),
    ]
    quota_plan = _quota_plan(coverage_report, calibration_matrix, sdk_languages, case_book_count)
    readiness_checks = {
        "has_full_pack_batch": _has_batch(batches, "local_full_pack_regression"),
        "has_sdk_parity_batch": _has_batch(batches, "sdk_parity_smoke"),
        "has_ashr_grading_batch": _has_batch(batches, "ashr_grading_tiny_calibration"),
        "has_semantic_judge_batch": _has_batch(batches, "semantic_llm_judge_audit"),
        "has_regression_batch": _has_batch(batches, "case_book_regression_replay"),
        "has_queue_quota_phases": set(quota_plan["queue_status_flow"]) >= {"queued", "running", "completed"},
        "has_cost_ledger": bool(calibration_matrix.get("cost_ledger")),
    }
    return {
        "schema_version": "a2.batch_plan.v1",
        "plan_id": "a2_g3_batch_plan",
        "scenario_pack": coverage_report.get("pack_id", ""),
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "plan_ready": all(readiness_checks.values()),
        "readiness_checks": readiness_checks,
        "batch_count": len(batches),
        "batches": batches,
        "quota_plan": quota_plan,
        "evidence_policy": {
            "raw_private_path": "docs/evidence/private_refs/",
            "public_outputs": [
                "fixtures/a2/results/a2_g3_calibration_matrix.json",
                "fixtures/a2/results/a2_case_book.json",
                "fixtures/a2/results/a2_semantic_harness_report.json",
                "fixtures/a2/results/a2_commercial_readiness_report.json",
            ],
            "secret_rule": "API keys and raw model/API payloads stay outside committed fixtures.",
        },
        "metadata": {
            "deterministic": True,
            "purpose": "Make C2 batch generation and quota planning auditable before C3 paid calibration.",
            "peer_signal": "A1 queue-worker draft tracks queued/running/completed lifecycle and run.submit/observation.write quota phases.",
        },
    }


def _batch(
    batch_id: str,
    execution_tier: str,
    case_count: int,
    judge_sources: list[str],
    objective: str,
    evidence_refs: list[str],
    *,
    requires_private_evidence: bool = False,
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "execution_tier": execution_tier,
        "case_count": case_count,
        "judge_sources": judge_sources,
        "objective": objective,
        "requires_private_evidence": requires_private_evidence,
        "evidence_refs": evidence_refs,
    }


def _quota_plan(
    coverage_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    sdk_languages: list[str],
    case_book_count: int,
) -> dict[str, Any]:
    calibration_count = int(calibration_matrix.get("case_count", 0))
    local_case_count = int(coverage_report.get("executable_run_case_count", 0))
    planned_run_submit_units = 5
    planned_observation_units = (
        max(1, local_case_count)
        + max(1, len(sdk_languages))
        + max(1, calibration_count) * 2
        + max(1, case_book_count)
    )
    return {
        "a1_queue_contract": {
            "run_submit_phase": "enqueue or direct submit",
            "observation_write_phase": "run completion",
            "status_history_required": True,
        },
        "queue_status_flow": ["queued", "running", "completed"],
        "failure_statuses_to_preserve": ["failed", "cancelled"],
        "planned_quota_units": {
            "run.submit": planned_run_submit_units,
            "observation.write": planned_observation_units,
        },
        "batch_size_limits": {
            "ashr_grading_tiny_calibration": calibration_count,
            "semantic_llm_judge_audit": calibration_count,
            "local_full_pack_regression": int(coverage_report.get("scenario_count", 0)),
        },
    }


def _semantic_evidence_refs(semantic_harness_report: dict[str, Any] | None) -> list[str]:
    refs = ["fixtures/a2/results/a2_g3_calibration_matrix.json::cost_ledger"]
    if semantic_harness_report:
        refs.insert(0, "fixtures/a2/results/a2_semantic_harness_report.json")
    return refs


def _has_batch(batches: list[dict[str, Any]], batch_id: str) -> bool:
    return any(batch.get("batch_id") == batch_id and int(batch.get("case_count", 0)) > 0 for batch in batches)
