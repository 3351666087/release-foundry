"""Coverage reporting for A2 scenario and judge deliverables."""

from collections import Counter
from pathlib import Path
from typing import Any

from .schemas import CANONICAL_FAILURE_CLASSES
from .runner import DEFAULT_SCENARIO_PACK, load_scenario_pack


REQUIRED_FAILURE_CLASSES = CANONICAL_FAILURE_CLASSES


def build_coverage_report(pack_path: str | Path = DEFAULT_SCENARIO_PACK) -> dict[str, Any]:
    pack = load_scenario_pack(pack_path)
    scenarios = pack.get("scenarios", [])
    failure_signals = {failure for scenario in scenarios for failure in scenario.get("failureSignals", [])}
    primary_rubrics = Counter(scenario.get("primaryRubric") for scenario in scenarios if scenario.get("primaryRubric"))
    primary_failures = Counter(scenario.get("primaryFailureClass") for scenario in scenarios if scenario.get("primaryFailureClass"))
    return {
        "schema_version": "a2.coverage_report.v1",
        "pack_id": pack.get("pack_id"),
        "scenario_count": len(scenarios),
        "family_counts": dict(sorted(Counter(scenario.get("family") for scenario in scenarios).items())),
        "rubric_classes": pack.get("rubric_classes", []),
        "primary_rubric_counts": dict(sorted(primary_rubrics.items())),
        "judge_modes": pack.get("judge_modes", []),
        "primary_failure_class_counts": dict(sorted(primary_failures.items())),
        "failure_signal_count": len(failure_signals),
        "failure_signals": sorted(failure_signals),
        "required_failure_classes_covered": sorted(REQUIRED_FAILURE_CLASSES & failure_signals),
        "required_failure_classes_missing": sorted(REQUIRED_FAILURE_CLASSES - failure_signals),
        "fixture_ref_count": sum(len(scenario.get("fixtureRefs", [])) for scenario in scenarios),
    }
