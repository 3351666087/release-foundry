"""Deterministic grounding judge for expected and forbidden factual claims."""

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
        failures: list[str] = []
        details: list[str] = []

        missing = [fact for fact in expected_facts if fact not in response]
        present_forbidden = [fact for fact in forbidden_facts if fact in response]

        if missing:
            failures.append("ignored_tool_result")
            details.append(f"Missing grounded facts: {', '.join(missing)}")
        if present_forbidden:
            failures.append("hallucinated_tool_result")
            details.append(f"Forbidden or contradicted facts present: {', '.join(present_forbidden)}")

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
            evidence={"expected_fact_count": len(expected_facts), "forbidden_fact_count": len(forbidden_facts)},
        )
