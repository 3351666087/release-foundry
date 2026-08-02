"""Replay case-book regressions against the deterministic A2 judge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runner import DEFAULT_SCENARIO_PACK, grade_run


MATURE_REPLAY_CASE_TARGET = 3


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
    case_book_maturity = case_book_report.get("maturity_gate", {})
    maturity_gate = _maturity_gate(cases, failed_cases, case_book_maturity)
    replay_ready = bool(cases) and not failed_cases
    return {
        "schema_version": "a2.regression_replay.v1",
        "replay_id": "a2_case_book_regression_replay",
        "source_case_book": case_book_report.get("case_book_id", ""),
        "source_matrix": calibration_matrix.get("matrix_id", ""),
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "replay_case_count": len(cases),
        "passed_count": len(cases) - len(failed_cases),
        "failed_count": len(failed_cases),
        "replay_ready": replay_ready,
        "maturity_status": maturity_gate["status"],
        "maturity_gate": maturity_gate,
        "release_gate_summary": _release_gate_summary(replay_ready, maturity_gate),
        "cases": cases,
        "metadata": {
            "deterministic": True,
            "purpose": "Make C5 case-book regressions executable and auditable.",
            "notes": [
                "This report replays current local judge behavior; it does not resolve judge disagreements by itself.",
                "C5 remains partial until the case book covers more reviewed ReleaseFoundry/local/LLM disagreements.",
            ],
        },
    }


def _maturity_gate(
    cases: list[dict[str, Any]],
    failed_cases: list[dict[str, Any]],
    case_book_maturity: dict[str, Any],
) -> dict[str, Any]:
    current_count = len(cases)
    case_book_ready = bool(case_book_maturity.get("ready"))
    reviewed_count = int(case_book_maturity.get("reviewed_external_evidence_count", 0))
    reviewed_target = int(case_book_maturity.get("reviewed_evidence_target_count", MATURE_REPLAY_CASE_TARGET))
    missing_replay_case_count = max(0, MATURE_REPLAY_CASE_TARGET - current_count)
    missing_reviewed_evidence_count = max(0, reviewed_target - reviewed_count)
    ready = current_count >= MATURE_REPLAY_CASE_TARGET and not failed_cases and case_book_ready
    return {
        "status": "mature" if ready else "seed",
        "ready": ready,
        "target_replay_case_count": MATURE_REPLAY_CASE_TARGET,
        "current_replay_case_count": current_count,
        "missing_replay_case_count": missing_replay_case_count,
        "failed_replay_case_count": len(failed_cases),
        "case_book_maturity_ready": case_book_ready,
        "reviewed_evidence_target_count": reviewed_target,
        "reviewed_external_evidence_count": reviewed_count,
        "missing_reviewed_evidence_count": missing_reviewed_evidence_count,
        "missing_reviewed_replay_cases": max(missing_replay_case_count, missing_reviewed_evidence_count),
        "gaps": _maturity_gaps(current_count, failed_cases, case_book_ready),
    }


def _release_gate_summary(replay_ready: bool, maturity_gate: dict[str, Any]) -> dict[str, Any]:
    failed_count = int(maturity_gate.get("failed_replay_case_count", 0))
    current_count = int(maturity_gate.get("current_replay_case_count", 0))
    target_count = int(maturity_gate.get("target_replay_case_count", MATURE_REPLAY_CASE_TARGET))
    missing_replay_count = int(maturity_gate.get("missing_replay_case_count", 0))
    reviewed_count = int(maturity_gate.get("reviewed_external_evidence_count", 0))
    reviewed_target = int(maturity_gate.get("reviewed_evidence_target_count", MATURE_REPLAY_CASE_TARGET))
    missing_reviewed_count = int(maturity_gate.get("missing_reviewed_evidence_count", 0))
    case_book_ready = bool(maturity_gate.get("case_book_maturity_ready"))
    blocks_release = not (replay_ready and bool(maturity_gate.get("ready")))
    action, required_action = _release_gate_action(
        failed_count=failed_count,
        current_count=current_count,
        target_count=target_count,
        missing_replay_count=missing_replay_count,
        missing_reviewed_count=missing_reviewed_count,
        case_book_ready=case_book_ready,
    )
    return {
        "schema_version": "a2.regression_replay.release_gate_summary.v1",
        "gate": "C5",
        "status": str(maturity_gate.get("status", "seed")),
        "release_gate_status": "blocked" if blocks_release else "ready",
        "blocks_release": blocks_release,
        "action": action,
        "required_action": required_action,
        "blocking_count": max(failed_count, missing_replay_count, missing_reviewed_count),
        "current_replay_case_count": current_count,
        "target_replay_case_count": target_count,
        "missing_replay_case_count": missing_replay_count,
        "failed_replay_case_count": failed_count,
        "reviewed_external_evidence_count": reviewed_count,
        "reviewed_evidence_target_count": reviewed_target,
        "missing_reviewed_evidence_count": missing_reviewed_count,
        "case_book_maturity_ready": case_book_ready,
        "gaps": [str(gap) for gap in maturity_gate.get("gaps", [])],
        "evidence_refs": [
            "fixtures/a2/results/a2_regression_replay_report.json",
            "fixtures/a2/results/a2_case_book.json",
        ],
    }


def _release_gate_action(
    *,
    failed_count: int,
    current_count: int,
    target_count: int,
    missing_replay_count: int,
    missing_reviewed_count: int,
    case_book_ready: bool,
) -> tuple[str, str]:
    if failed_count:
        return "fix_failed_replays", "Fix failed C5 replay cases before release."
    if current_count < target_count:
        return (
            "promote_more_regressions",
            "Promote more reviewed disagreement or incident cases into replayable C5 regressions.",
        )
    if missing_reviewed_count or not case_book_ready:
        return (
            "attach_reviewed_evidence",
            "Attach reviewed ReleaseFoundry grading or audited semantic evidence to C5 regression cases.",
        )
    return "ready", "No C5 regression replay action required."


def _maturity_gaps(current_count: int, failed_cases: list[dict[str, Any]], case_book_ready: bool) -> list[str]:
    gaps = []
    if current_count < MATURE_REPLAY_CASE_TARGET:
        remaining = MATURE_REPLAY_CASE_TARGET - current_count
        gaps.append(f"Replay {remaining} more reviewed case-book regression(s) before marking C5 mature.")
    if not case_book_ready:
        gaps.append("Keep the case-book maturity gate open until reviewed external evidence supports the regression set.")
    if failed_cases:
        failed_ids = ", ".join(str(case.get("case_id", "")) for case in failed_cases if case.get("case_id"))
        gaps.append(f"Fix failed replay case(s): {failed_ids or 'unknown'}.")
    return gaps


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
