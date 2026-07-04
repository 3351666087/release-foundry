"""Reviewer-facing case book for A2 calibration regressions."""

from __future__ import annotations

from typing import Any


MATURE_REGRESSION_CASE_TARGET = 3


def build_case_book_report(calibration_matrix: dict[str, Any]) -> dict[str, Any]:
    """Build a durable case-book seed from calibration disagreement candidates."""
    regression_cases = [
        _regression_case(case)
        for case in calibration_matrix.get("cases", [])
        if "judge_disagreement_regression" in case.get("calibration_tags", [])
    ]
    return {
        "schema_version": "a2.case_book.v1",
        "case_book_id": "a2_case_book",
        "source_matrix": calibration_matrix.get("matrix_id", ""),
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "regression_case_count": len(regression_cases),
        "candidate_pool": _candidate_pool(calibration_matrix, regression_cases),
        "maturity_gate": _maturity_gate(regression_cases),
        "regression_cases": regression_cases,
        "metadata": {
            "deterministic": True,
            "purpose": "Promote calibration disagreements into reviewer-visible regression seeds.",
            "notes": [
                "This report is additive and does not change local judge scores.",
                "Live Ashr or LLM evidence should update calibration observations first, then regenerate this case book.",
            ],
        },
    }


def _candidate_pool(calibration_matrix: dict[str, Any], regression_cases: list[dict[str, Any]]) -> dict[str, Any]:
    agreement = calibration_matrix.get("agreement_summary", {}).get("local_vs_llm_judge", {})
    ashr_coverage = calibration_matrix.get("source_coverage", {}).get("ashr_grading", {})
    return {
        "calibration_case_count": int(calibration_matrix.get("case_count", 0)),
        "comparable_local_llm_count": int(agreement.get("comparable", 0)),
        "local_llm_mismatch_count": int(agreement.get("mismatch_count", 0)),
        "ashr_grading_missing_count": int(ashr_coverage.get("missing", 0)),
        "promoted_regression_case_count": len(regression_cases),
    }


def _maturity_gate(regression_cases: list[dict[str, Any]]) -> dict[str, Any]:
    current_count = len(regression_cases)
    ready = current_count >= MATURE_REGRESSION_CASE_TARGET
    return {
        "status": "mature" if ready else "seed",
        "ready": ready,
        "target_regression_case_count": MATURE_REGRESSION_CASE_TARGET,
        "current_regression_case_count": current_count,
        "gaps": _maturity_gaps(current_count),
    }


def _maturity_gaps(current_count: int) -> list[str]:
    if current_count >= MATURE_REGRESSION_CASE_TARGET:
        return []
    remaining = MATURE_REGRESSION_CASE_TARGET - current_count
    return [
        f"Promote {remaining} more reviewed disagreement case(s) before marking the C5 case book mature.",
        "Keep new seeds tied to reviewed Ashr or audited semantic evidence before using them to close C5.",
    ]


def _regression_case(case: dict[str, Any]) -> dict[str, Any]:
    disagreement_pairs = [diff for diff in case.get("diffs", []) if diff.get("status") == "mismatch"]
    sources = case.get("sources", {})
    local = sources.get("local_judge", {})
    llm = sources.get("llm_judge", {})
    return {
        "regression_id": f"regression-{case.get('case_id', '')}",
        "case_id": case.get("case_id", ""),
        "scenario_id": case.get("scenario_id", ""),
        "fixture_ref": case.get("fixture_ref", ""),
        "status": "open",
        "severity": "medium",
        "calibration_focus": case.get("calibration_focus", []),
        "expected": case.get("expected", {}),
        "local_judge": _source_summary(local),
        "semantic_or_llm_judge": _source_summary(llm),
        "disagreement_pairs": disagreement_pairs,
        "regression_assertion": _regression_assertion(local, llm),
        "reviewer_note": _reviewer_note(case, local, llm),
        "evidence_refs": _evidence_refs(case, local, llm),
    }


def _source_summary(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": source.get("source", ""),
        "provider": source.get("provider", ""),
        "passed": source.get("passed"),
        "primary_failure_class": source.get("primary_failure_class", ""),
        "score": source.get("score"),
        "confidence": source.get("confidence"),
        "rationale": source.get("rationale", ""),
        "evidence_ref": source.get("evidence_ref", ""),
    }


def _regression_assertion(local: dict[str, Any], llm: dict[str, Any]) -> str:
    return (
        f"Keep local primary_failure_class={local.get('primary_failure_class', '')} visible when semantic/LLM "
        f"judge reports {llm.get('primary_failure_class', '')} for the same case."
    )


def _reviewer_note(case: dict[str, Any], local: dict[str, Any], llm: dict[str, Any]) -> str:
    return (
        f"{case.get('case_id', '')} is a calibration disagreement: local_judge identifies "
        f"{local.get('primary_failure_class', '')}, while the semantic/LLM reference identifies "
        f"{llm.get('primary_failure_class', '')}. Keep it as a regression seed until reviewed Ashr or live LLM "
        "evidence resolves whether this is a judge-boundary issue or an expected semantic ambiguity."
    )


def _evidence_refs(case: dict[str, Any], local: dict[str, Any], llm: dict[str, Any]) -> list[str]:
    refs = [str(case.get("fixture_ref", "")), str(local.get("evidence_ref", "")), str(llm.get("evidence_ref", ""))]
    return sorted({ref for ref in refs if ref})
