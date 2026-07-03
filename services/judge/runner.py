"""Small local runner for A2 judge handoff.

This is intentionally lightweight: A1 can pass a run dict with
`tool_calls`, `final_response`, and optional outcome keywords; A2 returns
deterministic GradeResult JSON for A3 to display.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .outcome import OutcomeJudge
from .tool_policy import ToolPolicyJudge


DEFAULT_SCENARIO_PACK = Path("packages/scenarios/a2_g2_seed_pack.json")


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
    results = [
        ToolPolicyJudge().grade(scenario, run, case_id=case_id).to_dict(),
        OutcomeJudge().grade(scenario, run, case_id=case_id).to_dict(),
    ]
    passed = all(result["passed"] for result in results)
    score = round(sum(result["score"] for result in results) / len(results), 2)
    failure_classes = [
        result["failure_analysis"]["primary_failure_class"]
        for result in results
        if result["failure_analysis"]["primary_failure_class"] != "none"
    ]
    return {
        "schema_version": "a2.local_judge_run.v1",
        "scenario_id": scenario_id,
        "case_id": case_id or scenario_id,
        "passed": passed,
        "score": score,
        "primary_failure_class": failure_classes[0] if failure_classes else "none",
        "judge_results": results,
    }
