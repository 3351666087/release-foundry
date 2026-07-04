"""Coverage reporting for A2 scenario and judge deliverables."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .runner import DEFAULT_SCENARIO_PACK, load_scenario_pack
from .schemas import CANONICAL_FAILURE_CLASSES, canonical_primary_failure_class


REQUIRED_FAILURE_CLASSES = CANONICAL_FAILURE_CLASSES
DEFAULT_GOLDEN_CASES = Path("fixtures/golden/a2_g2_golden_cases.json")
DEFAULT_RUN_FIXTURES = Path("fixtures/a2/runs")
ASSIGNMENT_MINIMUMS = {
    "scenario_count": 60,
    "rubric_class_count": 5,
    "judge_mode_count": 5,
    "golden_case_count": 20,
    "failure_class_count": 12,
}
CALIBRATION_REDUNDANCY_TARGETS = {
    "golden_failure_cases_per_class": 2,
    "executable_failure_cases_per_class": 2,
}


def build_coverage_report(
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    golden_path: str | Path = DEFAULT_GOLDEN_CASES,
    run_dir: str | Path = DEFAULT_RUN_FIXTURES,
) -> dict[str, Any]:
    pack = load_scenario_pack(pack_path)
    scenarios = pack.get("scenarios", [])
    golden_cases = load_golden_cases(golden_path)
    run_fixtures = load_run_fixtures(run_dir)
    failure_signals = {failure for scenario in scenarios for failure in scenario.get("failureSignals", [])}
    primary_rubrics = Counter(scenario.get("primaryRubric") for scenario in scenarios if scenario.get("primaryRubric"))
    primary_failures = Counter(scenario.get("primaryFailureClass") for scenario in scenarios if scenario.get("primaryFailureClass"))
    golden_failure_classes = Counter(
        canonical_primary_failure_class([str(case.get("expected_primary_failure_class", ""))])
        for case in golden_cases
        if not case.get("expected_passed", False)
    )
    executable_failure_classes = Counter(
        canonical_primary_failure_class([str(fixture.get("expected", {}).get("primary_failure_class", ""))])
        for fixture in run_fixtures
        if fixture.get("expected", {}).get("passed") is not True
    )
    thin_golden_failure_classes = _thin_counts(
        golden_failure_classes,
        REQUIRED_FAILURE_CLASSES,
        CALIBRATION_REDUNDANCY_TARGETS["golden_failure_cases_per_class"],
    )
    thin_executable_failure_classes = _thin_counts(
        executable_failure_classes,
        REQUIRED_FAILURE_CLASSES,
        CALIBRATION_REDUNDANCY_TARGETS["executable_failure_cases_per_class"],
    )
    assignment_checks = {
        "scenario_count": len(scenarios) >= ASSIGNMENT_MINIMUMS["scenario_count"],
        "rubric_class_count": len(pack.get("rubric_classes", [])) >= ASSIGNMENT_MINIMUMS["rubric_class_count"],
        "judge_mode_count": len(pack.get("judge_modes", [])) >= ASSIGNMENT_MINIMUMS["judge_mode_count"],
        "golden_case_count": len(golden_cases) >= ASSIGNMENT_MINIMUMS["golden_case_count"],
        "required_failure_classes_covered": not (REQUIRED_FAILURE_CLASSES - failure_signals),
        "golden_failure_classes_covered": not (REQUIRED_FAILURE_CLASSES - set(golden_failure_classes)),
        "executable_failure_classes_covered": not (REQUIRED_FAILURE_CLASSES - set(executable_failure_classes)),
    }
    return {
        "schema_version": "a2.coverage_report.v1",
        "pack_id": pack.get("pack_id"),
        "assignment_minimums": ASSIGNMENT_MINIMUMS,
        "assignment_checks": assignment_checks,
        "meets_assignment_minimums": all(assignment_checks.values()),
        "calibration_redundancy_targets": CALIBRATION_REDUNDANCY_TARGETS,
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
        "thin_golden_failure_classes": thin_golden_failure_classes,
        "executable_run_case_count": len(run_fixtures),
        "executable_failure_case_count": sum(1 for fixture in run_fixtures if fixture.get("expected", {}).get("passed") is not True),
        "executable_failure_class_counts": dict(sorted(executable_failure_classes.items())),
        "executable_failure_classes_missing": sorted(REQUIRED_FAILURE_CLASSES - set(executable_failure_classes)),
        "thin_executable_failure_classes": thin_executable_failure_classes,
        "coverage_warnings": _coverage_warnings(thin_golden_failure_classes, thin_executable_failure_classes),
        "fixture_ref_count": sum(len(scenario.get("fixtureRefs", [])) for scenario in scenarios),
    }


def _thin_counts(counts: Counter[str], required: set[str], target: int) -> dict[str, int]:
    return {
        failure_class: counts.get(failure_class, 0)
        for failure_class in sorted(required)
        if counts.get(failure_class, 0) < target
    }


def _coverage_warnings(
    thin_golden_failure_classes: dict[str, int],
    thin_executable_failure_classes: dict[str, int],
) -> list[str]:
    warnings = []
    if thin_golden_failure_classes:
        warnings.append(
            f"{len(thin_golden_failure_classes)} golden failure classes have fewer than "
            f"{CALIBRATION_REDUNDANCY_TARGETS['golden_failure_cases_per_class']} calibration cases."
        )
    if thin_executable_failure_classes:
        warnings.append(
            f"{len(thin_executable_failure_classes)} executable failure classes have fewer than "
            f"{CALIBRATION_REDUNDANCY_TARGETS['executable_failure_cases_per_class']} run fixtures."
        )
    return warnings


def load_golden_cases(path: str | Path = DEFAULT_GOLDEN_CASES) -> list[dict[str, Any]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    cases = payload.get("goldenCases", [])
    return cases if isinstance(cases, list) else []


def load_run_fixtures(path: str | Path = DEFAULT_RUN_FIXTURES) -> list[dict[str, Any]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    fixtures = []
    for fixture_path in sorted(resolved.glob("*.json")):
        fixtures.append(json.loads(fixture_path.read_text(encoding="utf-8")))
    return fixtures
