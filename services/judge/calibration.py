"""Calibration matrix for local, Ashr, and LLM judge comparisons."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .coverage import DEFAULT_RUN_FIXTURES
from .runner import DEFAULT_SCENARIO_PACK, grade_run


DEFAULT_CALIBRATION_OBSERVATIONS = Path("fixtures/a2/calibration/a2_g3_calibration_observations.json")
REQUIRED_SOURCES = ("local_judge", "ashr_grading", "llm_judge")


def build_calibration_matrix(
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    run_dir: str | Path = DEFAULT_RUN_FIXTURES,
    observations_path: str | Path = DEFAULT_CALIBRATION_OBSERVATIONS,
) -> dict[str, Any]:
    observations_payload = load_calibration_observations(observations_path)
    fixture_by_case = load_run_fixtures_by_case(run_dir)
    observations = _observations_by_case_and_source(observations_payload.get("observations", []))
    source_notes = observations_payload.get("source_notes", {})
    cases = []

    for case in observations_payload.get("cases", []):
        case_id = str(case["case_id"])
        fixture = fixture_by_case[case_id]
        local = grade_run(
            fixture["scenario_id"],
            fixture.get("run", fixture),
            pack_path=pack_path,
            case_id=case_id,
        )
        sources = {
            "local_judge": _local_source(local),
            "ashr_grading": _external_source(
                observations.get((case_id, "ashr_grading")),
                source_notes.get("ashr_grading", {}),
            ),
            "llm_judge": _external_source(
                observations.get((case_id, "llm_judge")),
                source_notes.get("llm_judge", {}),
            ),
        }
        cases.append(
            {
                "case_id": case_id,
                "scenario_id": fixture["scenario_id"],
                "fixture_ref": str(case.get("fixture_ref", "")),
                "calibration_focus": case.get("calibration_focus", []),
                "expected": fixture.get("expected", {}),
                "sources": sources,
                "diffs": _case_diffs(sources),
                "calibration_tags": _calibration_tags(fixture.get("expected", {}), sources),
            }
        )

    return {
        "schema_version": "a2.calibration_matrix.v1",
        "matrix_id": observations_payload.get("matrix_id", "a2_g3_calibration_matrix"),
        "dataset_id": observations_payload.get("dataset_id", "a2-g3-calibration"),
        "scenario_pack": _display_path(pack_path),
        "case_count": len(cases),
        "sources": list(REQUIRED_SOURCES),
        "source_coverage": _source_coverage(cases),
        "agreement_summary": {
            "local_vs_ashr_grading": _agreement_summary(cases, "local_judge", "ashr_grading"),
            "local_vs_llm_judge": _agreement_summary(cases, "local_judge", "llm_judge"),
            "ashr_grading_vs_llm_judge": _agreement_summary(cases, "ashr_grading", "llm_judge"),
        },
        "cost_ledger": _cost_ledger(cases),
        "calibration_warnings": _calibration_warnings(cases),
        "cases": cases,
        "metadata": {
            "deterministic": True,
            "observation_source": _display_path(observations_path),
            "notes": observations_payload.get("notes", []),
        },
    }


def load_calibration_observations(path: str | Path = DEFAULT_CALIBRATION_OBSERVATIONS) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_run_fixtures_by_case(path: str | Path = DEFAULT_RUN_FIXTURES) -> dict[str, dict[str, Any]]:
    fixtures = {}
    for fixture_path in sorted(Path(path).glob("*.json")):
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixtures[str(fixture["case_id"])] = fixture
    return fixtures


def _observations_by_case_and_source(observations: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(observation["case_id"]), str(observation["source"])): observation
        for observation in observations
    }


def _local_source(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "status": "available",
        "source": "local_judge",
        "provider": "services.judge.runner.grade_run",
        "passed": result["passed"],
        "primary_failure_class": result["primary_failure_class"],
        "score": result["score"],
        "confidence": 1.0,
        "rationale": "Deterministic local A2 judge result.",
        "cost": _empty_cost(),
        "evidence_ref": "fixtures/a2/results/a2_g3_grade_results.json",
    }


def _external_source(observation: dict[str, Any] | None, source_note: dict[str, Any]) -> dict[str, Any]:
    if not observation or observation.get("status") != "available":
        return {
            "available": False,
            "status": observation.get("status", "missing") if observation else "missing",
            "source": observation.get("source", source_note.get("source", "")) if observation else source_note.get("source", ""),
            "provider": observation.get("provider", source_note.get("provider", "")) if observation else source_note.get("provider", ""),
            "reason": observation.get("reason", source_note.get("reason", "No calibration observation supplied."))
            if observation
            else source_note.get("reason", "No calibration observation supplied."),
            "cost": _empty_cost(),
        }

    return {
        "available": True,
        "status": "available",
        "source": observation["source"],
        "provider": observation.get("provider", ""),
        "model": observation.get("model", ""),
        "passed": observation["passed"],
        "primary_failure_class": observation["primary_failure_class"],
        "score": observation.get("score", 0),
        "confidence": observation.get("confidence", 0),
        "rationale": observation.get("rationale", ""),
        "cost": _normalize_cost(observation.get("cost", {})),
        "evidence_ref": observation.get("evidence_ref", ""),
    }


def _case_diffs(sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _source_diff(sources, "local_judge", "ashr_grading"),
        _source_diff(sources, "local_judge", "llm_judge"),
        _source_diff(sources, "ashr_grading", "llm_judge"),
    ]


def _source_diff(sources: dict[str, dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    left_result = sources[left]
    right_result = sources[right]
    comparable = left_result.get("available") is True and right_result.get("available") is True
    diff = {
        "left": left,
        "right": right,
        "comparable": comparable,
        "passed_match": None,
        "failure_class_match": None,
        "score_delta": None,
        "status": "missing_source",
    }
    if not comparable:
        return diff

    diff["passed_match"] = left_result["passed"] == right_result["passed"]
    diff["failure_class_match"] = left_result["primary_failure_class"] == right_result["primary_failure_class"]
    diff["score_delta"] = round(left_result.get("score", 0) - right_result.get("score", 0), 2)
    diff["status"] = "match" if diff["passed_match"] and diff["failure_class_match"] else "mismatch"
    return diff


def _calibration_tags(expected: dict[str, Any], sources: dict[str, dict[str, Any]]) -> list[str]:
    tags = []
    local = sources["local_judge"]
    if expected and (
        local.get("passed") != expected.get("passed")
        or local.get("primary_failure_class") != expected.get("primary_failure_class")
    ):
        tags.append("local_expected_mismatch")
    if any(diff["status"] == "mismatch" for diff in _case_diffs(sources)):
        tags.append("judge_disagreement_regression")
    if sources["ashr_grading"].get("available") is not True:
        tags.append("needs_ashr_grading")
    if not tags:
        tags.append("calibrated_agreement")
    return tags


def _source_coverage(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    coverage = {}
    for source in REQUIRED_SOURCES:
        available = sum(1 for case in cases if case["sources"][source].get("available") is True)
        coverage[source] = {
            "available": available,
            "missing": len(cases) - available,
            "coverage_ratio": round(available / len(cases), 3) if cases else 0,
        }
    return coverage


def _agreement_summary(cases: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    diffs = [
        diff
        for case in cases
        for diff in case["diffs"]
        if diff["left"] == left and diff["right"] == right
    ]
    comparable = [diff for diff in diffs if diff["comparable"]]
    mismatches = [
        {
            "case_id": case["case_id"],
            "scenario_id": case["scenario_id"],
            "status": diff["status"],
            "passed_match": diff["passed_match"],
            "failure_class_match": diff["failure_class_match"],
        }
        for case in cases
        for diff in case["diffs"]
        if diff["left"] == left and diff["right"] == right and diff["status"] == "mismatch"
    ]
    return {
        "comparable": len(comparable),
        "missing": len(diffs) - len(comparable),
        "passed_agreement": sum(1 for diff in comparable if diff["passed_match"]),
        "failure_class_agreement": sum(1 for diff in comparable if diff["failure_class_match"]),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def _cost_ledger(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for source in REQUIRED_SOURCES:
        provider_counts = Counter()
        prompt_tokens = 0
        completion_tokens = 0
        estimated_usd = 0.0
        sample_count = 0
        for case in cases:
            result = case["sources"][source]
            if result.get("available") is not True:
                continue
            sample_count += 1
            provider_counts[str(result.get("provider", ""))] += 1
            cost = _normalize_cost(result.get("cost", {}))
            prompt_tokens += cost["prompt_tokens"]
            completion_tokens += cost["completion_tokens"]
            estimated_usd += cost["estimated_usd"]
        rows.append(
            {
                "source": source,
                "sample_count": sample_count,
                "provider_counts": dict(sorted(provider_counts.items())),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_usd": round(estimated_usd, 6),
            }
        )
    return rows


def _calibration_warnings(cases: list[dict[str, Any]]) -> list[str]:
    warnings = []
    coverage = _source_coverage(cases)
    for source, counts in coverage.items():
        if counts["missing"]:
            warnings.append(f"{source} is missing {counts['missing']} of {len(cases)} calibration cases.")
    local_llm = _agreement_summary(cases, "local_judge", "llm_judge")
    if local_llm["mismatch_count"]:
        warnings.append(
            f"local_judge vs llm_judge has {local_llm['mismatch_count']} disagreement regression candidates."
        )
    return warnings


def _normalize_cost(cost: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_tokens": int(cost.get("prompt_tokens", 0)),
        "completion_tokens": int(cost.get("completion_tokens", 0)),
        "estimated_usd": float(cost.get("estimated_usd", 0.0)),
    }


def _empty_cost() -> dict[str, Any]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "estimated_usd": 0.0}


def _display_path(path: str | Path) -> str:
    resolved = Path(path)
    try:
        return resolved.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return resolved.as_posix()
