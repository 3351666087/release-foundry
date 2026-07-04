"""Replay case-book regressions against the deterministic A2 judge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runner import DEFAULT_SCENARIO_PACK, grade_run


def build_regression_replay_report(
    calibration_matrix: dict[str, Any],
    case_book_report: dict[str, Any],
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    """Re-run case-book seeds so disagreement regressions stay executable."""
    matrix_by_case = {str(case.get("case_id", "")): case for case in calibration_matrix.get("cases", [])}
    cases = [
        _replay_case(regression, matrix_by_case.get(str(regression.get("case_id", ""))), pack_path)
        for regression in case_book_report.get("regression_cases", [])
    ]
    failed_cases = [case for case in cases if case.get("replay_status") != "passed"]
    return {
        "schema_version": "a2.regression_replay.v1",
        "replay_id": "a2_case_book_regression_replay",
        "source_case_book": case_book_report.get("case_book_id", ""),
        "source_matrix": calibration_matrix.get("matrix_id", ""),
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "replay_case_count": len(cases),
        "passed_count": len(cases) - len(failed_cases),
        "failed_count": len(failed_cases),
        "replay_ready": bool(cases) and not failed_cases,
        "maturity_status": "mature" if len(cases) >= 3 and not failed_cases else "seed",
        "cases": cases,
        "metadata": {
            "deterministic": True,
            "purpose": "Make C5 case-book regressions executable and auditable.",
            "notes": [
                "This report replays current local judge behavior; it does not resolve judge disagreements by itself.",
                "C5 remains partial until the case book covers more reviewed Ashr/local/LLM disagreements.",
            ],
        },
    }


def _replay_case(
    regression: dict[str, Any],
    matrix_case: dict[str, Any] | None,
    pack_path: str | Path,
) -> dict[str, Any]:
    fixture = _load_fixture(regression.get("fixture_ref", ""))
    grade = grade_run(
        fixture["scenario_id"],
        fixture.get("run", fixture),
        pack_path=pack_path,
        case_id=fixture.get("case_id"),
    )
    checks = {
        "fixture_replayed": True,
        "local_failure_class_preserved": grade.get("primary_failure_class")
        == regression.get("local_judge", {}).get("primary_failure_class"),
        "local_pass_status_preserved": grade.get("passed") == regression.get("local_judge", {}).get("passed"),
        "matrix_disagreement_visible": _matrix_disagreement_visible(matrix_case),
        "regression_assertion_present": bool(regression.get("regression_assertion")),
    }
    return {
        "regression_id": regression.get("regression_id", ""),
        "case_id": regression.get("case_id", ""),
        "scenario_id": regression.get("scenario_id", ""),
        "fixture_ref": regression.get("fixture_ref", ""),
        "replay_status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "expected_local_failure_class": regression.get("local_judge", {}).get("primary_failure_class", ""),
        "observed_local_failure_class": grade.get("primary_failure_class", ""),
        "expected_llm_failure_class": regression.get("semantic_or_llm_judge", {}).get("primary_failure_class", ""),
        "replay_grade": {
            "passed": grade.get("passed"),
            "score": grade.get("score"),
            "primary_failure_class": grade.get("primary_failure_class", ""),
            "judge_count": len(grade.get("judge_results", [])),
        },
        "evidence_refs": _evidence_refs(regression),
    }


def _load_fixture(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _matrix_disagreement_visible(matrix_case: dict[str, Any] | None) -> bool:
    if not matrix_case:
        return False
    return any(diff.get("status") == "mismatch" for diff in matrix_case.get("diffs", []))


def _evidence_refs(regression: dict[str, Any]) -> list[str]:
    refs = [str(regression.get("fixture_ref", ""))]
    refs.extend(str(ref) for ref in regression.get("evidence_refs", []))
    return sorted({ref for ref in refs if ref})
