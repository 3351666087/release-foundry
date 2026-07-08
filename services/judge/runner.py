"""Small local runner for A2 judge handoff.

This is intentionally lightweight: A1 can pass a run dict with
`tool_calls`, `final_response`, and optional outcome keywords; A2 returns
deterministic GradeResult JSON for A3 to display.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .grounding import GroundingJudge
from .outcome import OutcomeJudge
from .safety_boundary import SafetyBoundaryJudge
from .trace_integrity import TraceIntegrityJudge
from .tool_policy import ToolPolicyJudge


DEFAULT_SCENARIO_PACK = Path("packages/scenarios/a2_g3_full_pack.json")
JUDGES = (
    ToolPolicyJudge,
    OutcomeJudge,
    TraceIntegrityJudge,
    GroundingJudge,
    SafetyBoundaryJudge,
)


def load_scenario_pack(path: str | Path = DEFAULT_SCENARIO_PACK) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_scenario(scenario_id: str, pack: dict[str, Any]) -> dict[str, Any]:
    for scenario in pack.get("scenarios", []):
        if scenario.get("id") == scenario_id:
            return scenario
    raise KeyError(f"Scenario not found: {scenario_id}")


def grade_run(
    scenario_id: str,
    run: dict[str, Any],
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    case_id: str | None = None,
) -> dict[str, Any]:
    pack = load_scenario_pack(pack_path)
    scenario = get_scenario(scenario_id, pack)
    normalized_run = normalize_run_input(run)
    effective_case_id = case_id or normalized_run.get("case_id") or scenario_id
    normalized_run["case_id"] = effective_case_id
    results = [judge().grade(scenario, normalized_run, case_id=effective_case_id).to_dict() for judge in JUDGES]
    passed = all(result["passed"] for result in results)
    score = round(sum(result["score"] for result in results) / len(results), 2)
    failure_classes = [
        result["failure_analysis"]["primary_failure_class"]
        for result in results
        if result["failure_analysis"]["primary_failure_class"] != "none"
    ]
    if not passed:
        failing_scores = [result["score"] for result in results if not result["passed"]]
        score = min(score, min(failing_scores) if failing_scores else score)
    return {
        "schema_version": "a2.local_judge_run.v1",
        "scenario_id": scenario_id,
        "case_id": effective_case_id,
        "passed": passed,
        "score": score,
        "primary_failure_class": failure_classes[0] if failure_classes else "none",
        "judge_results": results,
    }


def grade_runs(
    run_fixtures: list[dict[str, Any]],
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    *,
    report_id: str = "a2_g3_grade_results",
    dataset_id: str = "a2-g3-calibration",
) -> dict[str, Any]:
    grade_results = [
        grade_run(
            fixture["scenario_id"],
            fixture.get("run", fixture),
            pack_path=pack_path,
            case_id=fixture.get("case_id"),
        )
        for fixture in run_fixtures
    ]
    return {
        "schema_version": "a2.grade_results.v1",
        "report_id": report_id,
        "dataset_id": dataset_id,
        "scenario_pack": _display_pack_path(pack_path),
        "total_cases": len(grade_results),
        "passed": sum(1 for result in grade_results if result["passed"]),
        "failed": sum(1 for result in grade_results if not result["passed"]),
        "grade_results": grade_results,
    }


def _display_pack_path(pack_path: str | Path) -> str:
    path = Path(pack_path)
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def normalize_run_input(run: dict[str, Any]) -> dict[str, Any]:
    """Accept A2 run objects and A1 AgentTurn/CaseResult handoff shapes."""
    source = run.get("agent_output") if isinstance(run.get("agent_output"), dict) else run
    tool_calls = source.get("tool_calls")
    if not isinstance(tool_calls, list):
        tool_calls = _tool_calls_from_observations(run)

    normalized = {
        "tool_calls": [_normalize_tool_call(call, index) for index, call in enumerate(tool_calls or [])],
        "final_response": _final_response(run, source),
    }
    for key in (
        "case_id",
        "status",
        "error",
        "latency_ms",
        "observations",
        "trace_events",
        "expected",
        "actual",
        "expected_keywords",
        "forbidden_keywords",
        "expected_facts",
        "forbidden_facts",
        "metadata",
    ):
        if key in run:
            normalized[key] = run[key]
        elif key in source:
            normalized[key] = source[key]
    return normalized


def _normalize_tool_call(call: Any, index: int) -> dict[str, Any]:
    if not isinstance(call, dict):
        return {"tool": str(call), "name": str(call), "args": {}, "arguments": {}}

    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(call.get("tool") or call.get("name") or function.get("name") or call.get("type") or f"tool_{index}")
    args = _first_args(call.get("args"), call.get("arguments"), function.get("arguments"), call.get("arguments_json"), call.get("input"))

    normalized = dict(call)
    normalized["tool"] = name
    normalized["name"] = name
    normalized["args"] = args
    normalized["arguments"] = args
    call_id = call.get("id") or call.get("call_id")
    if call_id is not None:
        normalized["id"] = str(call_id)
    return normalized


def _first_args(*candidates: Any) -> dict[str, Any]:
    for candidate in candidates:
        args = _coerce_args(candidate)
        if args is not None:
            return args
    return {}


def _coerce_args(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
        if parsed is None:
            return {}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {"value": value}


def _final_response(run: dict[str, Any], source: dict[str, Any]) -> str:
    for candidate in (
        run.get("final_response"),
        source.get("final_response"),
        source.get("text"),
        source.get("content"),
        _assistant_content_from_observations(run),
    ):
        if candidate is not None:
            return candidate if isinstance(candidate, str) else json.dumps(candidate, sort_keys=True)
    return ""


def _tool_calls_from_observations(run: dict[str, Any]) -> list[Any]:
    for observation in reversed(run.get("observations", []) if isinstance(run.get("observations"), list) else []):
        calls = observation.get("tool_calls") if isinstance(observation, dict) else None
        if calls:
            return calls if isinstance(calls, list) else [calls]
    return []


def _assistant_content_from_observations(run: dict[str, Any]) -> Any:
    observations = run.get("observations", [])
    if not isinstance(observations, list):
        return None
    for observation in reversed(observations):
        if not isinstance(observation, dict):
            continue
        if observation.get("role") == "assistant" or observation.get("event_type") == "agent_response":
            return observation.get("content")
    return None
