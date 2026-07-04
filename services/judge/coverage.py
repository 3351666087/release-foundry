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
SCENARIO_DIMENSION_MINIMUMS = {
    "no_tool_or_direct_answer": 10,
    "optional_tool_choice": 10,
    "required_tool_use": 10,
    "forbidden_tool_boundary": 10,
    "ordered_tool_sequence": 2,
    "multi_turn_dialogue": 2,
    "workflow_planning": 10,
    "fixture_grounding": 20,
    "clarification": 5,
    "failure_recovery": 4,
    "safety_boundary": 10,
    "grounding_reference": 10,
    "argument_fidelity": 10,
    "output_contract": 5,
    "freshness_current_info": 5,
    "tool_output_grounding": 1,
}
SCENARIO_QUALITY_TARGETS = {
    "d4_scenario_count": 2,
    "multi_turn_scenario_count": 4,
    "ordered_tool_count": 4,
    "fixture_scenario_count": 30,
    "non_local_environment_count": 20,
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
    scenario_quality = _scenario_quality_metrics(scenarios)
    scenario_quality_warnings = _scenario_quality_warnings(scenario_quality)
    scenario_dimensions = _scenario_dimension_refs(scenarios)
    scenario_dimension_counts = {key: len(value) for key, value in scenario_dimensions.items()}
    scenario_dimension_checks = {
        key: scenario_dimension_counts.get(key, 0) >= minimum
        for key, minimum in SCENARIO_DIMENSION_MINIMUMS.items()
    }
    thin_scenario_dimensions = {
        key: scenario_dimension_counts.get(key, 0)
        for key, minimum in SCENARIO_DIMENSION_MINIMUMS.items()
        if scenario_dimension_counts.get(key, 0) < minimum
    }
    primary_rubrics = Counter(scenario.get("primaryRubric") for scenario in scenarios if scenario.get("primaryRubric"))
    primary_failures = Counter(scenario.get("primaryFailureClass") for scenario in scenarios if scenario.get("primaryFailureClass"))
    golden_failure_classes = Counter(
        canonical_primary_failure_class([str(case.get("expected_primary_failure_class", ""))])
        for case in golden_cases
        if not case.get("expected_passed", False)
    )
    golden_failure_class_cases = _golden_failure_case_refs(golden_cases, REQUIRED_FAILURE_CLASSES)
    executable_failure_classes = Counter(
        canonical_primary_failure_class([str(fixture.get("expected", {}).get("primary_failure_class", ""))])
        for fixture in run_fixtures
        if fixture.get("expected", {}).get("passed") is not True
    )
    executable_failure_class_cases = _executable_failure_case_refs(run_fixtures, REQUIRED_FAILURE_CLASSES)
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
        "scenario_dimension_minimums": SCENARIO_DIMENSION_MINIMUMS,
        "scenario_dimension_checks": scenario_dimension_checks,
        "scenario_quality_targets": SCENARIO_QUALITY_TARGETS,
        "scenario_quality_warnings": scenario_quality_warnings,
        "scenario_count": len(scenarios),
        "family_counts": dict(sorted(Counter(scenario.get("family") for scenario in scenarios).items())),
        "difficulty_counts": scenario_quality["difficulty_counts"],
        "action_count_counts": scenario_quality["action_count_counts"],
        "multi_turn_scenario_count": scenario_quality["multi_turn_scenario_count"],
        "environment_counts": scenario_quality["environment_counts"],
        "tag_counts": scenario_quality["tag_counts"],
        "scenario_dimension_counts": dict(sorted(scenario_dimension_counts.items())),
        "scenario_dimension_scenarios": scenario_dimensions,
        "thin_scenario_dimensions": thin_scenario_dimensions,
        "tool_policy_shape_counts": scenario_quality["tool_policy_shape_counts"],
        "required_tool_counts": scenario_quality["required_tool_counts"],
        "optional_tool_counts": scenario_quality["optional_tool_counts"],
        "forbidden_tool_counts": scenario_quality["forbidden_tool_counts"],
        "ordered_tool_count": scenario_quality["ordered_tool_count"],
        "ordered_tool_pairs": scenario_quality["ordered_tool_pairs"],
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
        "golden_failure_class_cases": golden_failure_class_cases,
        "golden_failure_classes_missing": sorted(REQUIRED_FAILURE_CLASSES - set(golden_failure_classes)),
        "thin_golden_failure_classes": thin_golden_failure_classes,
        "executable_run_case_count": len(run_fixtures),
        "executable_failure_case_count": sum(1 for fixture in run_fixtures if fixture.get("expected", {}).get("passed") is not True),
        "executable_failure_class_counts": dict(sorted(executable_failure_classes.items())),
        "executable_failure_class_cases": executable_failure_class_cases,
        "executable_failure_classes_missing": sorted(REQUIRED_FAILURE_CLASSES - set(executable_failure_classes)),
        "thin_executable_failure_classes": thin_executable_failure_classes,
        "coverage_warnings": _coverage_warnings(
            thin_golden_failure_classes,
            thin_executable_failure_classes,
            thin_scenario_dimensions,
        ),
        "fixture_ref_count": sum(len(scenario.get("fixtureRefs", [])) for scenario in scenarios),
        "fixture_scenario_count": scenario_quality["fixture_scenario_count"],
        "fixture_type_counts": scenario_quality["fixture_type_counts"],
        "fixture_ref_counts_by_scenario": scenario_quality["fixture_ref_counts_by_scenario"],
    }


def _thin_counts(counts: Counter[str], required: set[str], target: int) -> dict[str, int]:
    return {
        failure_class: counts.get(failure_class, 0)
        for failure_class in sorted(required)
        if counts.get(failure_class, 0) < target
    }


def _golden_failure_case_refs(cases: list[dict[str, Any]], required: set[str]) -> dict[str, list[dict[str, str]]]:
    refs = {failure_class: [] for failure_class in sorted(required)}
    for case in cases:
        if case.get("expected_passed") is True:
            continue
        failure_class = canonical_primary_failure_class([str(case.get("expected_primary_failure_class", ""))])
        if failure_class in refs:
            refs[failure_class].append(_case_ref(case))
    return {key: sorted(value, key=lambda item: (item["scenario_id"], item["case_id"])) for key, value in refs.items()}


def _executable_failure_case_refs(fixtures: list[dict[str, Any]], required: set[str]) -> dict[str, list[dict[str, str]]]:
    refs = {failure_class: [] for failure_class in sorted(required)}
    for fixture in fixtures:
        if fixture.get("expected", {}).get("passed") is True:
            continue
        failure_class = canonical_primary_failure_class([str(fixture.get("expected", {}).get("primary_failure_class", ""))])
        if failure_class in refs:
            refs[failure_class].append(_case_ref(fixture))
    return {key: sorted(value, key=lambda item: (item["scenario_id"], item["case_id"])) for key, value in refs.items()}


def _case_ref(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "case_id": str(payload.get("case_id", "")),
        "scenario_id": str(payload.get("scenario_id", "")),
    }


def _scenario_dimension_refs(scenarios: list[dict[str, Any]]) -> dict[str, list[str]]:
    dimensions = {key: [] for key in sorted(SCENARIO_DIMENSION_MINIMUMS)}
    checks = {
        "argument_fidelity": _is_argument_fidelity,
        "clarification": _is_clarification,
        "failure_recovery": _is_failure_recovery,
        "fixture_grounding": lambda scenario: bool(scenario.get("fixtureRefs")),
        "forbidden_tool_boundary": lambda scenario: bool(scenario.get("toolPolicy", {}).get("forbidden")),
        "freshness_current_info": lambda scenario: "freshness" in _tags(scenario) or "web" in _tags(scenario),
        "grounding_reference": _is_grounding_reference,
        "multi_turn_dialogue": _is_multi_turn_dialogue,
        "no_tool_or_direct_answer": lambda scenario: scenario.get("family") == "direct_answer" or "no-tool" in _tags(scenario),
        "optional_tool_choice": lambda scenario: bool(scenario.get("toolPolicy", {}).get("optional")),
        "ordered_tool_sequence": _is_ordered_tool_sequence,
        "output_contract": _is_output_contract,
        "required_tool_use": lambda scenario: bool(scenario.get("toolPolicy", {}).get("required")),
        "safety_boundary": _is_safety_boundary,
        "tool_output_grounding": _is_tool_output_grounding,
        "workflow_planning": _is_workflow_planning,
    }
    for scenario in scenarios:
        for dimension, predicate in checks.items():
            if predicate(scenario):
                dimensions[dimension].append(str(scenario.get("id", "")))
    return {key: sorted(value) for key, value in dimensions.items()}


def _scenario_quality_metrics(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    difficulty_counts = Counter(str(scenario.get("difficulty", "unknown")) for scenario in scenarios)
    action_count_counts = Counter(str(len(scenario.get("actions", []))) for scenario in scenarios)
    environment_counts = Counter(
        str(action.get("environment", "unknown"))
        for scenario in scenarios
        for action in scenario.get("actions", [])
    )
    tag_counts = Counter(tag for scenario in scenarios for tag in _tags(scenario))
    fixture_ref_counts_by_scenario = {
        str(scenario.get("id", "")): len(scenario.get("fixtureRefs", []))
        for scenario in scenarios
        if scenario.get("fixtureRefs")
    }
    fixture_type_counts = Counter(
        _fixture_type(ref)
        for scenario in scenarios
        for ref in scenario.get("fixtureRefs", [])
    )
    required_tools = Counter()
    optional_tools = Counter()
    forbidden_tools = Counter()
    tool_policy_shapes = Counter()
    ordered_tool_pairs = Counter()
    ordered_tool_count = 0
    for scenario in scenarios:
        policy = scenario.get("toolPolicy", {})
        required = policy.get("required", [])
        optional = policy.get("optional", [])
        forbidden = policy.get("forbidden", [])
        order = policy.get("order", [])
        if not required:
            tool_policy_shapes["no_required_tool"] += 1
        if required:
            tool_policy_shapes["required_tool"] += 1
        if optional:
            tool_policy_shapes["optional_tool"] += 1
        if forbidden:
            tool_policy_shapes["forbidden_tool"] += 1
        if required and forbidden:
            tool_policy_shapes["required_plus_forbidden"] += 1
        if any(item.get("tool") == "*" for item in forbidden if isinstance(item, dict)):
            tool_policy_shapes["wildcard_forbid"] += 1
        if any(item.get("severity") == "critical" for item in forbidden if isinstance(item, dict)):
            tool_policy_shapes["critical_forbid"] += 1
        if order:
            tool_policy_shapes["ordered_tools"] += 1
            ordered_tool_count += 1
        for item in required:
            required_tools[str(item.get("tool", "unknown"))] += 1
        for item in optional:
            optional_tools[str(item.get("tool", "unknown"))] += 1
        for item in forbidden:
            forbidden_tools[str(item.get("tool", "unknown"))] += 1
        for pair in _ordered_tool_pairs(order):
            ordered_tool_pairs[pair] += 1
    return {
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "action_count_counts": dict(sorted(action_count_counts.items())),
        "multi_turn_scenario_count": sum(1 for scenario in scenarios if len(scenario.get("actions", [])) > 1),
        "environment_counts": dict(sorted(environment_counts.items())),
        "tag_counts": dict(sorted(tag_counts.items())),
        "tool_policy_shape_counts": dict(sorted(tool_policy_shapes.items())),
        "required_tool_counts": dict(sorted(required_tools.items())),
        "optional_tool_counts": dict(sorted(optional_tools.items())),
        "forbidden_tool_counts": dict(sorted(forbidden_tools.items())),
        "ordered_tool_count": ordered_tool_count,
        "ordered_tool_pairs": dict(sorted(ordered_tool_pairs.items())),
        "fixture_scenario_count": len(fixture_ref_counts_by_scenario),
        "fixture_type_counts": dict(sorted(fixture_type_counts.items())),
        "fixture_ref_counts_by_scenario": dict(sorted(fixture_ref_counts_by_scenario.items())),
    }


def _fixture_type(ref: str) -> str:
    parts = Path(str(ref)).parts
    if "a2" in parts:
        index = parts.index("a2")
        if index + 1 < len(parts):
            return parts[index + 1]
    if len(parts) >= 2:
        return parts[-2]
    return "unknown"


def _ordered_tool_pairs(order: list[Any]) -> list[str]:
    pairs = []
    tools = []
    for item in order:
        if not isinstance(item, dict):
            continue
        if item.get("before") and item.get("after"):
            pairs.append(f"{item['before']} -> {item['after']}")
        elif item.get("tool"):
            tools.append(str(item["tool"]))
    return pairs + [f"{left} -> {right}" for left, right in zip(tools, tools[1:])]


def _scenario_quality_warnings(metrics: dict[str, Any]) -> list[str]:
    warnings = []
    d4_count = metrics["difficulty_counts"].get("D4", 0)
    if d4_count < SCENARIO_QUALITY_TARGETS["d4_scenario_count"]:
        warnings.append(
            f"D4 scenario count is {d4_count}; target is {SCENARIO_QUALITY_TARGETS['d4_scenario_count']} for harder edge cases."
        )
    if metrics["multi_turn_scenario_count"] < SCENARIO_QUALITY_TARGETS["multi_turn_scenario_count"]:
        warnings.append(
            f"Multi-turn scenario count is {metrics['multi_turn_scenario_count']}; target is "
            f"{SCENARIO_QUALITY_TARGETS['multi_turn_scenario_count']} for dialogue/state coverage."
        )
    if metrics["ordered_tool_count"] < SCENARIO_QUALITY_TARGETS["ordered_tool_count"]:
        warnings.append(
            f"Ordered-tool scenario count is {metrics['ordered_tool_count']}; target is "
            f"{SCENARIO_QUALITY_TARGETS['ordered_tool_count']} for multi-step protocol coverage."
        )
    if metrics["fixture_scenario_count"] < SCENARIO_QUALITY_TARGETS["fixture_scenario_count"]:
        warnings.append(
            f"Fixture-backed scenario count is {metrics['fixture_scenario_count']}; target is "
            f"{SCENARIO_QUALITY_TARGETS['fixture_scenario_count']} for executable audit depth."
        )
    non_local_count = sum(
        count
        for environment, count in metrics["environment_counts"].items()
        if environment != "local"
    )
    if non_local_count < SCENARIO_QUALITY_TARGETS["non_local_environment_count"]:
        warnings.append(
            f"Non-local action environment count is {non_local_count}; target is "
            f"{SCENARIO_QUALITY_TARGETS['non_local_environment_count']} for tool-surface breadth."
        )
    return warnings


def _tags(scenario: dict[str, Any]) -> set[str]:
    return {str(tag) for tag in scenario.get("tags", [])}


def _failures(scenario: dict[str, Any]) -> set[str]:
    return {str(failure) for failure in scenario.get("failureSignals", [])}


def _is_argument_fidelity(scenario: dict[str, Any]) -> bool:
    return (
        scenario.get("primaryRubric") == "argument_fidelity"
        or bool(_failures(scenario) & {"wrong_arguments", "wrong_tool_order"})
        or bool(_tags(scenario) & {"argument-fidelity", "path-validation", "wrong-arguments"})
    )


def _is_clarification(scenario: dict[str, Any]) -> bool:
    return (
        scenario.get("primaryFailureClass") == "missing_clarification"
        or "missing_clarification" in _failures(scenario)
        or bool(_tags(scenario) & {"clarification", "missing-info"})
    )


def _is_failure_recovery(scenario: dict[str, Any]) -> bool:
    return (
        scenario.get("primaryFailureClass") == "poor_failure_recovery"
        or "poor_failure_recovery" in _failures(scenario)
        or bool(_tags(scenario) & {"recovery", "retry", "tool-error", "error-recovery"})
    )


def _is_grounding_reference(scenario: dict[str, Any]) -> bool:
    return (
        scenario.get("family") == "retrieval_grounding"
        or bool(scenario.get("fixtureRefs"))
        or bool(_failures(scenario) & {"hallucinated_tool_result", "ignored_tool_result"})
        or bool(_tags(scenario) & {"citation", "docs", "evidence", "file", "given-context-only", "grounding", "mcp", "provided-context", "resource", "web"})
    )


def _is_multi_turn_dialogue(scenario: dict[str, Any]) -> bool:
    return (
        len(scenario.get("actions", [])) > 1
        or bool(_tags(scenario) & {"memory", "multi-turn"})
    )


def _is_ordered_tool_sequence(scenario: dict[str, Any]) -> bool:
    return (
        bool(scenario.get("toolPolicy", {}).get("order"))
        or bool(_tags(scenario) & {"multi-tool-order", "ordered-tools"})
    )


def _is_output_contract(scenario: dict[str, Any]) -> bool:
    return (
        "output_schema_invalid" in _failures(scenario)
        or bool(_tags(scenario) & {"checklist", "concise-output", "csv", "formatting", "json", "schema", "structured-output", "summary"})
    )


def _is_tool_output_grounding(scenario: dict[str, Any]) -> bool:
    return bool(scenario.get("expectedToolOutputFacts")) or "tool-output-grounding" in _tags(scenario)


def _is_safety_boundary(scenario: dict[str, Any]) -> bool:
    return (
        scenario.get("family") == "safety_policy"
        or scenario.get("primaryRubric") == "safety_permissions"
        or bool(_failures(scenario) & {"forbidden_tool_call", "unsafe_or_policy_violation"})
        or bool(_tags(scenario) & {"boundary", "credential-theft", "credentials", "forbidden-tool", "permission", "personal-data", "privacy", "refusal", "safety", "secret", "security", "unsafe"})
    )


def _is_workflow_planning(scenario: dict[str, Any]) -> bool:
    return (
        scenario.get("family") == "workflow_planning"
        or bool(_tags(scenario) & {"multi-step", "planning", "recovery", "retry", "state-delta", "tool-error"})
    )


def _coverage_warnings(
    thin_golden_failure_classes: dict[str, int],
    thin_executable_failure_classes: dict[str, int],
    thin_scenario_dimensions: dict[str, int],
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
    if thin_scenario_dimensions:
        warnings.append(f"{len(thin_scenario_dimensions)} scenario quality dimensions are below their G3 minimums.")
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
