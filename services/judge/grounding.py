"""Deterministic grounding judge for expected and forbidden factual claims."""

import json
from typing import Any

from .schemas import FailureAnalysis, GradeResult, rubric_entry, weighted_score


class GroundingJudge:
    mode = "g3_semantic_reference_judge"

    def grade(
        self,
        scenario: dict[str, Any],
        run: dict[str, Any],
        case_id: str | None = None,
    ) -> GradeResult:
        scenario_id = scenario["id"]
        response = str(run.get("final_response", "")).lower()
        expected_facts = [str(item).lower() for item in scenario.get("expectedFacts", run.get("expected_facts", []))]
        forbidden_facts = [str(item).lower() for item in scenario.get("forbiddenFacts", run.get("forbidden_facts", []))]
        expected_tool_output_rules = _normalize_tool_output_rules(
            scenario.get("expectedToolOutputFacts", run.get("expected_tool_output_facts", []))
        )
        failures: list[str] = []
        details: list[str] = []

        missing = [fact for fact in expected_facts if fact not in response]
        present_forbidden = [fact for fact in forbidden_facts if fact in response]
        missing_tool_output = _missing_tool_output_facts(run.get("tool_calls", []), expected_tool_output_rules)

        if missing:
            failures.append("ignored_tool_result")
            details.append(f"Missing grounded facts: {', '.join(missing)}")
        if present_forbidden:
            failures.append("hallucinated_tool_result")
            details.append(f"Forbidden or contradicted facts present: {', '.join(present_forbidden)}")
        if missing_tool_output:
            failures.append("hallucinated_tool_result")
            details.append(f"Missing tool-output support: {', '.join(missing_tool_output)}")

        grounding_score = 1.0 if not failures else 0.45
        failure_analysis = FailureAnalysis(
            primary_failure_class=list(dict.fromkeys(failures))[0] if failures else "none",
            failure_classes=list(dict.fromkeys(failures)),
            severity="major" if failures else "none",
            blame_stage="grounding" if failures else "reasoning",
            summary="; ".join(details) if details else "Grounding contract satisfied or no explicit grounding facts were provided.",
            details=details,
            remediation=["Align final response with expected_facts and forbidden_facts."] if failures else [],
        )
        rubric_scores = [
            rubric_entry("task_completion", grounding_score, "Grounded facts should be reflected in the final answer."),
            rubric_entry("skill_protocol", 1.0, "Tool usage is handled by the trace contract judge."),
            rubric_entry("argument_fidelity", 1.0, "Arguments are handled by the tool policy judge."),
            rubric_entry("safety_permissions", 1.0, "Safety is handled by the safety boundary judge."),
            rubric_entry("final_response_quality", grounding_score, "Final answer should not contradict available evidence."),
        ]
        return GradeResult(
            scenario_id=scenario_id,
            case_id=case_id or scenario_id,
            judge_mode=self.mode,
            passed=not failures,
            score=weighted_score(rubric_scores),
            rubric_scores=rubric_scores,
            failure_analysis=failure_analysis,
            evidence=_evidence(expected_facts, forbidden_facts, expected_tool_output_rules, missing_tool_output),
        )


def _normalize_tool_output_rules(raw_rules: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_rules, list):
        return []
    rules = []
    for item in raw_rules:
        if isinstance(item, str):
            rules.append({"tool": None, "facts": [item]})
        elif isinstance(item, dict):
            facts = item.get("facts", [])
            if isinstance(facts, str):
                facts = [facts]
            if isinstance(facts, list):
                rules.append({"tool": item.get("tool"), "facts": [str(fact).lower() for fact in facts]})
    return rules


def _missing_tool_output_facts(tool_calls: Any, rules: list[dict[str, Any]]) -> list[str]:
    if not rules or not isinstance(tool_calls, list):
        return []
    missing = []
    for rule in rules:
        tool_name = rule.get("tool")
        output_text = " ".join(_output_text(call) for call in tool_calls if _matches_tool(call, tool_name))
        for fact in rule.get("facts", []):
            if fact and fact not in output_text:
                label = f"{tool_name}:{fact}" if tool_name else fact
                missing.append(label)
    return missing


def _matches_tool(call: Any, tool_name: str | None) -> bool:
    if not isinstance(call, dict):
        return False
    return tool_name is None or str(call.get("tool") or call.get("name") or "") == tool_name


def _output_text(call: Any) -> str:
    if not isinstance(call, dict):
        return ""
    output = call.get("output", call.get("result", ""))
    if isinstance(output, str):
        return output.lower()
    try:
        return json.dumps(output, sort_keys=True).lower()
    except TypeError:
        return str(output).lower()


def _evidence(
    expected_facts: list[str],
    forbidden_facts: list[str],
    expected_tool_output_rules: list[dict[str, Any]],
    missing_tool_output: list[str],
) -> dict[str, Any]:
    evidence = {"expected_fact_count": len(expected_facts), "forbidden_fact_count": len(forbidden_facts)}
    if expected_tool_output_rules:
        evidence["expected_tool_output_fact_count"] = sum(len(rule.get("facts", [])) for rule in expected_tool_output_rules)
        evidence["missing_tool_output_facts"] = missing_tool_output
    return evidence
