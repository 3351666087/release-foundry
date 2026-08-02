"""Replay case-book regressions against the deterministic A2 judge."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .casebook import (
    EXTERNAL_EVIDENCE_RECEIPT_BINDINGS_FIELD,
    build_case_book_report,
    build_case_book_receipt_bindings,
    reviewed_external_evidence_count,
    verify_case_book_artifact,
)
from .result_persistence import stable_hash
from .runner import DEFAULT_SCENARIO_PACK, grade_run


MATURE_REPLAY_CASE_TARGET = 3
_REVIEWER_RECEIPT = re.compile(r"^sha256:[a-f0-9]{64}$")
ROOT = Path(__file__).resolve().parents[2]
PUBLIC_REPLAY_FIXTURE_ROOT = (ROOT / "fixtures/a2/runs").resolve()
PUBLIC_REPLAY_FIXTURE_PREFIX = ("fixtures", "a2", "runs")
PUBLIC_REPLAY_ERROR_MESSAGES = {
    "fixture is missing scenario_id",
    "replay fixture is not valid JSON",
    "replay fixture_ref cannot contain parent traversal",
    "replay fixture_ref does not name an existing public fixture",
    "replay fixture_ref must be a non-empty path",
    "replay fixture_ref must be repository-relative",
    "replay fixture_ref must be under fixtures/a2/runs",
    "replay fixture_ref must name a JSON file",
    "replay fixture_ref resolves outside fixtures/a2/runs",
}


def build_regression_replay_report(
    calibration_matrix: dict[str, Any],
    case_book_report: dict[str, Any],
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    """Re-run case-book seeds so disagreement regressions stay executable."""
    matrix_by_case = _calibration_cases_by_id(calibration_matrix.get("cases"))
    regression_cases = case_book_report.get("regression_cases", [])
    _validate_unique_case_ids(regression_cases)
    declared_case_count = _non_negative_count(
        case_book_report.get("regression_case_count"),
        field="regression_case_count",
    )
    if declared_case_count != len(regression_cases):
        raise ValueError(
            "regression replay case-book regression_case_count "
            "does not match the number of regression_cases"
        )
    source_case_book_hash = verify_case_book_artifact(case_book_report)
    source_matrix_hash = _validate_source_binding(
        calibration_matrix,
        case_book_report,
    )
    cases = [
        _replay_case(regression, matrix_by_case.get(str(regression.get("case_id", ""))), pack_path)
        for regression in regression_cases
    ]
    failed_cases = [case for case in cases if case.get("replay_status") != "passed"]
    case_book_maturity = case_book_report.get("maturity_gate", {})
    maturity_gate = _maturity_gate(
        cases,
        failed_cases,
        regression_cases,
        case_book_maturity,
        case_book_report.get(EXTERNAL_EVIDENCE_RECEIPT_BINDINGS_FIELD),
    )
    replay_ready = bool(cases) and not failed_cases
    report = {
        "schema_version": "a2.regression_replay.v1",
        "replay_id": "a2_case_book_regression_replay",
        "source_case_book": case_book_report.get("case_book_id", ""),
        "source_case_book_hash": source_case_book_hash,
        "source_matrix": calibration_matrix.get("matrix_id", ""),
        "source_matrix_hash": source_matrix_hash,
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
    return {**report, "artifact_hash": stable_hash(report)}


def verify_regression_replay_artifact(
    regression_replay_report: dict[str, Any],
    *,
    calibration_matrix: dict[str, Any] | None = None,
    case_book_report: dict[str, Any] | None = None,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> str:
    """Verify and return the replay report content hash.

    When current source artifacts are supplied, rebuild the deterministic replay
    so a re-sealed report cannot overstate readiness or refer to stale inputs.
    """
    if not isinstance(regression_replay_report, dict):
        raise TypeError("regression replay artifact must be an object")
    artifact_hash = regression_replay_report.get("artifact_hash")
    if not isinstance(artifact_hash, str) or not _REVIEWER_RECEIPT.fullmatch(
        artifact_hash
    ):
        raise ValueError(
            "regression replay artifact_hash must be a canonical sha256 reference"
        )
    core = {
        key: value
        for key, value in regression_replay_report.items()
        if key != "artifact_hash"
    }
    if stable_hash(core) != artifact_hash:
        raise ValueError(
            "regression replay artifact_hash does not match replay content"
        )
    if (calibration_matrix is None) != (case_book_report is None):
        raise ValueError(
            "regression replay source verification requires both "
            "calibration_matrix and case_book_report"
        )
    if calibration_matrix is not None and case_book_report is not None:
        expected_report = build_regression_replay_report(
            calibration_matrix,
            case_book_report,
            pack_path=pack_path,
        )
        if expected_report.get("artifact_hash") != artifact_hash:
            raise ValueError(
                "regression replay artifact does not match replay rebuilt "
                "from calibration matrix and case book"
            )
    return artifact_hash


def _validate_source_binding(
    calibration_matrix: dict[str, Any],
    case_book_report: dict[str, Any],
) -> str:
    matrix_id = str(calibration_matrix.get("matrix_id", "")).strip()
    dataset_id = str(calibration_matrix.get("dataset_id", "")).strip()
    if not matrix_id or not dataset_id:
        raise ValueError("regression replay calibration matrix requires matrix_id and dataset_id")
    if case_book_report.get("source_matrix") != matrix_id:
        raise ValueError("regression replay case-book source_matrix does not match calibration matrix")
    if case_book_report.get("dataset_id") != dataset_id:
        raise ValueError("regression replay case-book dataset_id does not match calibration matrix")
    matrix_hash = stable_hash(calibration_matrix)
    if case_book_report.get("source_matrix_hash") != matrix_hash:
        raise ValueError("regression replay case-book source_matrix_hash does not match calibration matrix")
    expected_receipt_bindings = build_case_book_receipt_bindings(
        calibration_matrix
    )
    if (
        case_book_report.get(EXTERNAL_EVIDENCE_RECEIPT_BINDINGS_FIELD)
        != expected_receipt_bindings
    ):
        raise ValueError(
            "regression replay case-book external evidence receipt bindings "
            "do not match the calibration matrix"
        )
    expected_matrix_regressions = {
        str(regression.get("case_id", "")).strip(): regression
        for regression in build_case_book_report(calibration_matrix).get(
            "regression_cases",
            [],
        )
    }
    for regression in case_book_report.get("regression_cases", []):
        case_id = str(regression.get("case_id", "")).strip()
        expected_regression = expected_matrix_regressions.get(case_id)
        if expected_regression is None:
            continue
        for field in (
            "local_judge",
            "releasefoundry_grading",
            "semantic_or_llm_judge",
            "disagreement_pairs",
        ):
            if regression.get(field) != expected_regression.get(field):
                raise ValueError(
                    "regression replay case-book matrix-derived judge evidence "
                    "does not match the calibration matrix"
                )
    return matrix_hash


def _maturity_gate(
    cases: list[dict[str, Any]],
    failed_cases: list[dict[str, Any]],
    regression_cases: list[dict[str, Any]],
    case_book_maturity: Any,
    receipt_bindings: Any,
) -> dict[str, Any]:
    current_count = len(cases)
    if not isinstance(case_book_maturity, dict):
        raise ValueError("regression replay case-book maturity_gate must be an object")
    case_book_ready = case_book_maturity.get("ready", False)
    if not isinstance(case_book_ready, bool):
        raise ValueError("regression replay case-book maturity ready must be a boolean")
    declared_reviewed_count = _non_negative_count(
        case_book_maturity.get("reviewed_external_evidence_count", 0),
        field="reviewed_external_evidence_count",
    )
    reviewed_target = _non_negative_count(
        case_book_maturity.get("reviewed_evidence_target_count", MATURE_REPLAY_CASE_TARGET),
        field="reviewed_evidence_target_count",
    )
    if reviewed_target < MATURE_REPLAY_CASE_TARGET:
        raise ValueError(
            "regression replay case-book reviewed_evidence_target_count "
            f"must be at least {MATURE_REPLAY_CASE_TARGET}"
        )
    if declared_reviewed_count > current_count:
        raise ValueError(
            "regression replay case-book reviewed_external_evidence_count "
            "cannot exceed the replay case count"
        )
    reviewed_count = reviewed_external_evidence_count(
        regression_cases,
        receipt_bindings,
    )
    if declared_reviewed_count != reviewed_count:
        raise ValueError(
            "regression replay case-book reviewed_external_evidence_count "
            "does not match reviewed evidence recomputed from regression_cases"
        )
    if case_book_ready and (
        current_count < MATURE_REPLAY_CASE_TARGET or reviewed_count < reviewed_target
    ):
        raise ValueError(
            "regression replay case-book maturity ready is inconsistent with its case and evidence counts"
        )
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


def _non_negative_count(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"regression replay case-book {field} must be a non-negative integer")
    return value


def _validate_unique_case_ids(regression_cases: Any) -> None:
    if not isinstance(regression_cases, list):
        raise TypeError("regression replay case_book regression_cases must be a list")
    seen: set[str] = set()
    for regression in regression_cases:
        if not isinstance(regression, dict):
            raise TypeError("regression replay cases must be objects")
        case_id = str(regression.get("case_id", "")).strip()
        if not case_id:
            raise ValueError("regression replay case requires case_id")
        if case_id in seen:
            raise ValueError(f"duplicate regression replay case_id {case_id!r}")
        seen.add(case_id)


def _calibration_cases_by_id(cases: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(cases, list):
        raise ValueError("regression replay calibration cases must be a list")
    by_case_id: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(
                f"regression replay calibration cases[{index}] must be an object"
            )
        case_id = str(case.get("case_id", "")).strip()
        if not case_id:
            raise ValueError(
                f"regression replay calibration cases[{index}] requires case_id"
            )
        if case_id in by_case_id:
            raise ValueError(
                f"duplicate regression replay calibration case_id {case_id!r}"
            )
        by_case_id[case_id] = case
    return by_case_id


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
    fixture_ref = ""
    try:
        fixture_path, fixture_ref = _resolve_public_fixture(
            regression.get("fixture_ref", "")
        )
        fixture = _load_fixture(fixture_path)
        scenario_id = str(fixture.get("scenario_id", "")).strip()
        if not scenario_id:
            raise ValueError("fixture is missing scenario_id")
        grade = grade_run(
            scenario_id,
            fixture.get("run", fixture),
            pack_path=pack_path,
            case_id=fixture.get("case_id"),
        )
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return _failed_replay_case(regression, exc, fixture_ref=fixture_ref)
    checks = {
        "fixture_replayed": True,
        "local_failure_class_preserved": grade.get("primary_failure_class")
        == regression.get("local_judge", {}).get("primary_failure_class"),
        "local_pass_status_preserved": grade.get("passed") == regression.get("local_judge", {}).get("passed"),
    }
    expected_fixture_sha256 = regression.get("fixture_sha256")
    observed_fixture_sha256 = stable_hash(fixture)
    if "promotion" in regression:
        fixture_content_hash_present = (
            isinstance(expected_fixture_sha256, str)
            and _REVIEWER_RECEIPT.fullmatch(expected_fixture_sha256) is not None
        )
        checks["fixture_content_hash_present"] = fixture_content_hash_present
        checks["fixture_content_hash_preserved"] = bool(
            fixture_content_hash_present
            and expected_fixture_sha256 == observed_fixture_sha256
        )
        checks["approved_promotion_visible"] = _approved_promotion_visible(regression)
    elif matrix_case is not None:
        checks["matrix_disagreement_visible"] = _matrix_disagreement_visible(matrix_case)
    else:
        checks["matrix_disagreement_visible"] = False
    checks["regression_assertion_present"] = _regression_assertion_present(regression)
    replay = {
        "regression_id": regression.get("regression_id", ""),
        "case_id": regression.get("case_id", ""),
        "scenario_id": regression.get("scenario_id", ""),
        "fixture_ref": fixture_ref,
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
        "evidence_refs": _evidence_refs(regression, fixture_ref=fixture_ref),
    }
    if "promotion" in regression:
        replay["expected_fixture_sha256"] = (
            expected_fixture_sha256
            if checks["fixture_content_hash_present"]
            else ""
        )
        replay["observed_fixture_sha256"] = observed_fixture_sha256
    return replay


def _failed_replay_case(
    regression: dict[str, Any],
    error: Exception,
    *,
    fixture_ref: str,
) -> dict[str, Any]:
    checks = {
        "fixture_replayed": False,
        "replay_error_recorded": True,
        "regression_assertion_present": _regression_assertion_present(regression),
    }
    if "promotion" in regression:
        expected_fixture_sha256 = regression.get("fixture_sha256")
        checks["fixture_content_hash_present"] = (
            isinstance(expected_fixture_sha256, str)
            and _REVIEWER_RECEIPT.fullmatch(expected_fixture_sha256) is not None
        )
        checks["fixture_content_hash_preserved"] = False
    replay = {
        "regression_id": regression.get("regression_id", ""),
        "case_id": regression.get("case_id", ""),
        "scenario_id": regression.get("scenario_id", ""),
        "fixture_ref": fixture_ref,
        "replay_status": "failed",
        "checks": checks,
        "error": {
            "type": type(error).__name__,
            "message": _public_error_message(error),
        },
        "expected_local_failure_class": regression.get("local_judge", {}).get("primary_failure_class", ""),
        "observed_local_failure_class": "",
        "expected_llm_failure_class": regression.get("semantic_or_llm_judge", {}).get("primary_failure_class", ""),
        "replay_grade": {
            "passed": None,
            "score": None,
            "primary_failure_class": "",
            "judge_count": 0,
        },
        "evidence_refs": _evidence_refs(regression, fixture_ref=fixture_ref),
    }
    if "promotion" in regression:
        replay["expected_fixture_sha256"] = (
            regression.get("fixture_sha256")
            if checks["fixture_content_hash_present"]
            else ""
        )
        replay["observed_fixture_sha256"] = ""
    return replay


def _regression_assertion_present(regression: dict[str, Any]) -> bool:
    assertion = regression.get("regression_assertion")
    return isinstance(assertion, str) and bool(assertion.strip())


def _resolve_public_fixture(path: Any) -> tuple[Path, str]:
    if not isinstance(path, (str, Path)):
        raise TypeError("replay fixture_ref must be a path string")
    raw_ref = str(path).strip()
    if not raw_ref:
        raise ValueError("replay fixture_ref must be a non-empty path")
    windows_path = PureWindowsPath(raw_ref)
    normalized_ref = PurePosixPath(raw_ref.replace("\\", "/"))
    if (
        normalized_ref.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    ):
        raise ValueError("replay fixture_ref must be repository-relative")
    if ".." in normalized_ref.parts:
        raise ValueError("replay fixture_ref cannot contain parent traversal")
    if normalized_ref.parts[:3] != PUBLIC_REPLAY_FIXTURE_PREFIX:
        raise ValueError("replay fixture_ref must be under fixtures/a2/runs")
    if normalized_ref.suffix.lower() != ".json":
        raise ValueError("replay fixture_ref must name a JSON file")

    target = (ROOT / Path(*normalized_ref.parts)).resolve()
    try:
        target.relative_to(PUBLIC_REPLAY_FIXTURE_ROOT)
    except ValueError as exc:
        raise ValueError(
            "replay fixture_ref resolves outside fixtures/a2/runs"
        ) from exc
    if not target.is_file():
        raise ValueError("replay fixture_ref does not name an existing public fixture")
    return target, normalized_ref.as_posix()


def _load_fixture(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OSError("replay fixture could not be read") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("replay fixture is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TypeError("fixture must be a JSON object")
    return payload


def _public_error_message(error: Exception) -> str:
    if isinstance(error, OSError):
        return "replay fixture could not be read"
    if isinstance(error, TypeError):
        return "replay fixture or case data has an invalid type"
    if isinstance(error, KeyError):
        return "replay fixture or scenario data is missing a required field"
    message = str(error)
    if message in PUBLIC_REPLAY_ERROR_MESSAGES:
        return message
    return "replay fixture or scenario data is invalid"


def _matrix_disagreement_visible(matrix_case: dict[str, Any] | None) -> bool:
    if not matrix_case:
        return False
    return any(diff.get("status") == "mismatch" for diff in matrix_case.get("diffs", []))


def _approved_promotion_visible(regression: dict[str, Any]) -> bool:
    promotion = regression.get("promotion", {})
    reviewed_at = promotion.get("reviewed_at_unix_ms") if isinstance(promotion, dict) else None
    return (
        isinstance(promotion, dict)
        and promotion.get("source") == "incident_candidate"
        and promotion.get("decision") == "approved"
        and promotion.get("replay_input_approved") is True
        and isinstance(promotion.get("reviewer_receipt"), str)
        and _REVIEWER_RECEIPT.fullmatch(promotion["reviewer_receipt"]) is not None
        and isinstance(promotion.get("source_incident_candidates_hash"), str)
        and _REVIEWER_RECEIPT.fullmatch(
            promotion["source_incident_candidates_hash"]
        )
        is not None
        and isinstance(promotion.get("candidate_hash"), str)
        and _REVIEWER_RECEIPT.fullmatch(promotion["candidate_hash"]) is not None
        and not isinstance(reviewed_at, bool)
        and isinstance(reviewed_at, int)
        and reviewed_at > 0
    )


def _evidence_refs(
    regression: dict[str, Any],
    *,
    fixture_ref: str,
) -> list[str]:
    refs = [fixture_ref]
    refs.extend(
        safe_ref
        for ref in regression.get("evidence_refs", [])
        if (safe_ref := _safe_repository_ref(ref))
    )
    return sorted({ref for ref in refs if ref})


def _safe_repository_ref(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    raw_ref = value.strip()
    windows_path = PureWindowsPath(raw_ref)
    normalized_ref = PurePosixPath(raw_ref.replace("\\", "/"))
    if (
        normalized_ref.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.drive)
        or ".." in normalized_ref.parts
    ):
        return ""
    return normalized_ref.as_posix()
