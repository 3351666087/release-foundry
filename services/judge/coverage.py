"""Coverage reporting for A2 scenario and judge deliverables."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .runner import DEFAULT_SCENARIO_PACK, load_scenario_pack
from .schemas import CANONICAL_FAILURE_CLASSES, canonical_primary_failure_class


REQUIRED_FAILURE_CLASSES = CANONICAL_FAILURE_CLASSES
DEFAULT_GOLDEN_CASES = Path("fixtures/golden/a2_g2_golden_cases.json")


def build_coverage_report(
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    golden_path: str | Path = DEFAULT_GOLDEN_CASES,
) -> dict[str, Any]:
    pack = load_scenario_pack(pack_path)
    scenarios = pack.get("scenarios", [])
    golden_cases = load_golden_cases(golden_path)
    failure_signals = {failure for scenario in scenarios for failure in scenario.get("failureSignals", [])}
    primary_rubrics = Counter(scenario.get("primaryRubric") for scenario in scenarios if scenario.get("primaryRubric"))
    primary_failures = Counter(scenario.get("primaryFailureClass") for scenario in scenarios if scenario.get("primaryFailureClass"))
    golden_failure_classes = Counter(
        canonical_primary_failure_class([str(case.get("expected_primary_failure_class", ""))])
        for case in golden_cases
        if not case.get("expected_passed", False)
    )
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
        "golden_case_count": len(golden_cases),
        "golden_pass_case_count": sum(1 for case in golden_cases if case.get("expected_passed") is True),
        "golden_failure_case_count": sum(1 for case in golden_cases if case.get("expected_passed") is not True),
        "golden_failure_class_counts": dict(sorted(golden_failure_classes.items())),
        "golden_failure_classes_missing": sorted(REQUIRED_FAILURE_CLASSES - set(golden_failure_classes)),
        "fixture_ref_count": sum(len(scenario.get("fixtureRefs", [])) for scenario in scenarios),
    }


def load_golden_cases(path: str | Path = DEFAULT_GOLDEN_CASES) -> list[dict[str, Any]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    cases = payload.get("goldenCases", [])
    return cases if isinstance(cases, list) else []
