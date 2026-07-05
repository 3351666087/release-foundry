"""Calibration matrix for local, Ashr, and LLM judge comparisons."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .coverage import DEFAULT_RUN_FIXTURES
from .runner import DEFAULT_SCENARIO_PACK, grade_run
from .schemas import CANONICAL_FAILURE_CLASSES


DEFAULT_CALIBRATION_OBSERVATIONS = Path("fixtures/a2/calibration/a2_g3_calibration_observations.json")
REQUIRED_SOURCES = ("local_judge", "ashr_grading", "llm_judge")
PASSING_TEXT_STATUSES = {"exact", "similar", "match"}
PASSING_TOOL_STATUSES = {"exact", "match"}
SECRET_LIKE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
)


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


def import_ashr_grading_observations(
    payload: dict[str, Any] | list[Any],
    *,
    case_map: dict[str, str] | None = None,
    evidence_ref: str = "",
    provider: str = "ashr server-side grading",
    review_status: str = "unreviewed",
) -> list[dict[str, Any]]:
    """Convert redacted Ashr run records into A2 calibration observations."""
    mapped_cases = case_map or {}
    observations = []
    for run in extract_ashr_runs(payload):
        run_id = str(run.get("id", ""))
        for test in _ashr_tests(run):
            raw_case_id = str(test.get("test_id") or test.get("case_id") or "")
            if not raw_case_id:
                continue
            case_id = str(mapped_cases.get(raw_case_id, raw_case_id))
            failure = _classify_ashr_test(test)
            observations.append(
                {
                    "case_id": case_id,
                    "scenario_id": case_id,
                    "source": "ashr_grading",
                    "status": "available",
                    "provider": provider,
                    "model": "ashr-server-side",
                    "passed": failure["primary_failure_class"] == "none",
                    "primary_failure_class": failure["primary_failure_class"],
                    "score": _ashr_score(test, failure["primary_failure_class"] == "none"),
                    "confidence": failure["confidence"],
                    "rationale": _redact_text(failure["summary"]),
                    "cost": _empty_cost(),
                    "evidence_ref": _redact_text(evidence_ref),
                    "metadata": {
                        "raw_case_id": _redact_text(raw_case_id),
                        "run_id": _redact_text(run_id),
                        "review_status": _redact_text(review_status),
                        "action_indexes": failure["action_indexes"],
                        "match_statuses": _ashr_match_statuses(test),
                    },
                }
            )
    return observations


def import_semantic_judge_observations(
    payload: dict[str, Any] | list[Any],
    *,
    case_map: dict[str, str] | None = None,
    evidence_ref: str = "",
) -> list[dict[str, Any]]:
    """Convert reviewed semantic judge summaries into A2 llm_judge observations."""
    mapped_cases = case_map or {}
    observations = []
    for item in _semantic_judge_items(payload):
        raw_case_id = str(item.get("case_id") or item.get("raw_case_id") or "")
        if not raw_case_id:
            continue
        case_id = str(mapped_cases.get(raw_case_id, raw_case_id))
        output = item.get("output") if isinstance(item.get("output"), dict) else item
        primary = str(output.get("primary_failure_class", ""))
        if primary not in CANONICAL_FAILURE_CLASSES | {"none"}:
            raise ValueError(f"semantic judge case {case_id!r} has unknown primary_failure_class {primary!r}")

        cost = _normalize_cost(item.get("cost", {}) if isinstance(item.get("cost"), dict) else {})
        observations.append(
            {
                "case_id": case_id,
                "scenario_id": str(item.get("scenario_id") or case_id),
                "source": "llm_judge",
                "status": "available",
                "provider": _redact_text(str(item.get("provider", ""))),
                "model": _redact_text(str(item.get("model", ""))),
                "passed": bool(output.get("passed")),
                "primary_failure_class": primary,
                "score": _normalize_score(output.get("score")) or 0.0,
                "confidence": _normalize_confidence(output.get("confidence")),
                "rationale": _redact_text(str(output.get("rationale", ""))),
                "cost": cost,
                "evidence_ref": _semantic_evidence_ref(item, output, evidence_ref),
                "metadata": _semantic_metadata(item, raw_case_id),
            }
        )
    return observations


def merge_calibration_observations(
    base_payload: dict[str, Any],
    incoming_payload: dict[str, Any] | list[Any],
    *,
    source: str = "ashr_grading",
) -> dict[str, Any]:
    """Merge reviewed external observations into an A2 calibration payload."""
    if source == "local_judge" or source not in REQUIRED_SOURCES:
        raise ValueError(f"source must be an external calibration source, got {source!r}")

    merged = json.loads(json.dumps(base_payload))
    known_cases = {
        str(case["case_id"]): str(case.get("scenario_id", ""))
        for case in merged.get("cases", [])
        if isinstance(case, dict) and case.get("case_id")
    }
    incoming = _extract_observations(incoming_payload)
    if not incoming:
        raise ValueError("incoming payload does not contain observations")

    observations_by_key = _observations_by_case_and_source(merged.get("observations", []))
    seen: set[tuple[str, str]] = set()
    for observation in incoming:
        incoming_source = str(observation.get("source", ""))
        case_id = str(observation.get("case_id", ""))
        key = (case_id, incoming_source)
        if incoming_source != source:
            raise ValueError(f"incoming observation {case_id!r} has source {incoming_source!r}, expected {source!r}")
        if case_id not in known_cases:
            raise ValueError(f"incoming observation case_id {case_id!r} is not in calibration cases")
        if key in seen:
            raise ValueError(f"duplicate incoming observation for {case_id!r}/{incoming_source!r}")
        seen.add(key)

        normalized = dict(observation)
        normalized["case_id"] = case_id
        normalized["scenario_id"] = known_cases[case_id]
        observations_by_key[key] = normalized

    merged["observations"] = _sorted_observations(observations_by_key, known_cases)
    return merged


def extract_ashr_runs(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    response = payload.get("response")
    if isinstance(response, dict):
        runs = extract_ashr_runs(response)
        if runs:
            return runs
    run = payload.get("run")
    if isinstance(run, dict):
        return [run]
    runs = payload.get("runs")
    if isinstance(runs, list):
        return [item for item in runs if isinstance(item, dict)]
    if payload.get("id") is not None and isinstance(payload.get("result"), dict):
        return [payload]
    return []


def _semantic_judge_items(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    observations = payload.get("observations")
    if isinstance(observations, list):
        return [item for item in observations if isinstance(item, dict)]
    cases = payload.get("cases")
    if isinstance(cases, list):
        return [item for item in cases if isinstance(item, dict)]
    if payload.get("case_id") or payload.get("raw_case_id"):
        return [payload]
    return []


def _extract_observations(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    observations = payload.get("observations")
    if isinstance(observations, list):
        return [item for item in observations if isinstance(item, dict)]
    if payload.get("case_id") and payload.get("source"):
        return [payload]
    return []


def _observations_by_case_and_source(observations: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(observation["case_id"]), str(observation["source"])): observation
        for observation in observations
    }


def _sorted_observations(
    observations_by_key: dict[tuple[str, str], dict[str, Any]],
    known_cases: dict[str, str],
) -> list[dict[str, Any]]:
    case_order = {case_id: index for index, case_id in enumerate(known_cases)}
    source_order = {source: index for index, source in enumerate(REQUIRED_SOURCES)}
    return [
        observation
        for _, observation in sorted(
            observations_by_key.items(),
            key=lambda item: (
                case_order.get(item[0][0], len(case_order)),
                source_order.get(item[0][1], len(source_order)),
                item[0][1],
                item[0][0],
            ),
        )
    ]


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

    source = {
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
    if isinstance(observation.get("metadata"), dict):
        source["metadata"] = observation["metadata"]
    return source


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


def _ashr_tests(run: dict[str, Any]) -> list[dict[str, Any]]:
    result = run.get("result") if isinstance(run.get("result"), dict) else {}
    tests = result.get("tests")
    return [item for item in tests if isinstance(item, dict)] if isinstance(tests, list) else []


def _classify_ashr_test(test: dict[str, Any]) -> dict[str, Any]:
    action_results = test.get("action_results") if isinstance(test.get("action_results"), list) else []
    for action in action_results:
        if not isinstance(action, dict) or action.get("action_type") != "tool_call":
            continue
        for call in action.get("tool_calls", []) if isinstance(action.get("tool_calls"), list) else []:
            if not isinstance(call, dict):
                continue
            status = _tool_match_status(action, call)
            if not status or status in PASSING_TOOL_STATUSES:
                continue
            expected = call.get("expected") if isinstance(call.get("expected"), dict) else {}
            actual = call.get("actual") if isinstance(call.get("actual"), dict) else {}
            primary = _tool_failure_class(expected, actual)
            return {
                "primary_failure_class": primary,
                "confidence": 0.86,
                "summary": call.get("divergence_notes")
                or action.get("divergence_notes")
                or f"Ashr tool-call match status was {status}.",
                "action_indexes": _action_indexes(action),
            }

    for action in action_results:
        if not isinstance(action, dict):
            continue
        status = str(action.get("match_status", ""))
        if action.get("actor") == "agent" and action.get("action_type") == "text" and status and status not in PASSING_TEXT_STATUSES:
            return {
                "primary_failure_class": "wrong_intent",
                "confidence": 0.72,
                "summary": action.get("divergence_notes") or f"Ashr text match status was {status}.",
                "action_indexes": _action_indexes(action),
            }

    test_status = str(test.get("status", ""))
    if test_status and test_status not in {"completed", "passed"}:
        return {
            "primary_failure_class": "poor_failure_recovery",
            "confidence": 0.6,
            "summary": f"Ashr test status was {test_status}.",
            "action_indexes": [],
        }

    return {
        "primary_failure_class": "none",
        "confidence": 0.82,
        "summary": "Ashr action results passed or had no failure signal.",
        "action_indexes": [],
    }


def _tool_match_status(action: dict[str, Any], call: dict[str, Any]) -> str:
    comparison = call.get("argument_comparison") if isinstance(call.get("argument_comparison"), dict) else {}
    return str(call.get("match_status") or action.get("match_status") or comparison.get("status") or "")


def _tool_failure_class(expected: dict[str, Any], actual: dict[str, Any]) -> str:
    expected_tool = expected.get("tool_name") or expected.get("name")
    actual_tool = actual.get("tool_name") or actual.get("name")
    if not actual_tool:
        return "missing_required_tool"
    if not expected_tool:
        return "unnecessary_tool_call"
    if str(expected_tool) != str(actual_tool):
        return "wrong_tool"
    return "wrong_arguments"


def _ashr_score(test: dict[str, Any], passed: bool) -> float:
    action_results = test.get("action_results") if isinstance(test.get("action_results"), list) else []
    scores = [
        _normalize_score(action.get("semantic_similarity"))
        for action in action_results
        if isinstance(action, dict) and action.get("semantic_similarity") is not None
    ]
    scores = [score for score in scores if score is not None]
    if scores:
        return round(sum(scores) / len(scores), 2)
    return 100.0 if passed else 0.0


def _normalize_score(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    if value < 0:
        return 0.0
    if value <= 1:
        return round(value * 100, 2)
    return round(min(float(value), 100.0), 2)


def _normalize_confidence(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    return round(max(0.0, min(float(value), 1.0)), 3)


def _semantic_metadata(item: dict[str, Any], raw_case_id: str) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    result = {
        "raw_case_id": _redact_text(raw_case_id),
        "prompt_template_id": _redact_text(str(item.get("prompt_template_id") or metadata.get("prompt_template_id", ""))),
        "prompt_hash": _redact_text(str(item.get("prompt_hash") or metadata.get("prompt_hash", ""))),
        "response_hash": _redact_text(str(item.get("response_hash") or metadata.get("response_hash", ""))),
        "review_status": _redact_text(str(item.get("review_status") or metadata.get("review_status", ""))),
        "sdk_language": _redact_text(str(item.get("sdk_language") or metadata.get("sdk_language", ""))),
    }
    return {key: value for key, value in result.items() if value}


def _semantic_evidence_ref(item: dict[str, Any], output: dict[str, Any], fallback: str) -> str:
    evidence_refs = output.get("evidence_refs")
    if isinstance(evidence_refs, list) and evidence_refs:
        return _redact_text(str(evidence_refs[0]))
    return _redact_text(str(item.get("evidence_ref") or fallback))


def _ashr_match_statuses(test: dict[str, Any]) -> list[str]:
    action_results = test.get("action_results") if isinstance(test.get("action_results"), list) else []
    statuses = []
    for action in action_results:
        if not isinstance(action, dict):
            continue
        if action.get("match_status"):
            statuses.append(str(action["match_status"]))
        for call in action.get("tool_calls", []) if isinstance(action.get("tool_calls"), list) else []:
            if isinstance(call, dict) and call.get("match_status"):
                statuses.append(str(call["match_status"]))
    return statuses


def _action_indexes(action: dict[str, Any]) -> list[int]:
    index = action.get("action_index")
    return [int(index)] if isinstance(index, int) else []


def _redact_text(value: str) -> str:
    redacted = str(value)
    for pattern in SECRET_LIKE_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _display_path(path: str | Path) -> str:
    resolved = Path(path)
    try:
        return resolved.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return resolved.as_posix()
