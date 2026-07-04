"""Deterministic trace-shape judge for A1/A2 handoff quality."""

from typing import Any

from .common import get_tool_args, get_tool_name
from .schemas import FailureAnalysis, GradeResult, canonical_primary_failure_class, rubric_entry, weighted_score


class TraceIntegrityJudge:
    mode = "g3_replay_sandbox_judge"

    def grade(
        self,
        scenario: dict[str, Any],
        run: dict[str, Any],
        case_id: str | None = None,
    ) -> GradeResult:
        scenario_id = scenario["id"]
        calls = list(run.get("tool_calls", []))
        observations = run.get("observations", [])
        failures: list[str] = []
        details: list[str] = []

        for index, call in enumerate(calls):
            if not get_tool_name(call):
                failures.append("wrong_tool")
                details.append(f"Tool call {index} has no tool/name field.")
            if not isinstance(get_tool_args(call), dict):
                failures.append("wrong_arguments")
                details.append(f"Tool call {index} arguments are not normalized as an object.")
            if call.get("error") and not _response_mentions_recovery(run):
                failures.append("poor_failure_recovery")
                details.append(f"Tool call {index} returned an error without visible recovery.")

        if run.get("status") in {"error", "timeout"} and not _response_mentions_recovery(run):
            failures.append("poor_failure_recovery")
            details.append(f"Run status is {run.get('status')} without an honest recovery response.")

        if observations and not any(_is_assistant_observation(item) for item in observations if isinstance(item, dict)):
            failures.append("bad_final_response")
            details.append("Trace observations exist but contain no assistant response observation.")

        trace_score = 1.0 if not failures else 0.55
        failure_analysis = FailureAnalysis(
            primary_failure_class=canonical_primary_failure_class(list(dict.fromkeys(failures))),
            failure_classes=list(dict.fromkeys(failures)),
            severity="major" if failures else "none",
            blame_stage="trace" if failures else "reasoning",
            summary="; ".join(details) if details else "Trace shape is usable for local grading and A3 display.",
            details=details,
            remediation=["Normalize trace/tool-call fields before A2 grading."] if failures else [],
        )
        rubric_scores = [
            rubric_entry("task_completion", trace_score, "Trace should contain enough outcome evidence."),
            rubric_entry("skill_protocol", trace_score, "Tool calls should expose tool/name and normalized args."),
            rubric_entry("argument_fidelity", trace_score, "Argument objects should be inspectable."),
            rubric_entry("safety_permissions", 1.0, "Safety is handled by policy and safety judges."),
            rubric_entry("final_response_quality", 1.0 if run.get("final_response") else 0.5, "Final response should be available in trace."),
        ]
        return GradeResult(
            scenario_id=scenario_id,
            case_id=case_id or scenario_id,
            judge_mode=self.mode,
            passed=not failures,
            score=weighted_score(rubric_scores),
            rubric_scores=rubric_scores,
            failure_analysis=failure_analysis,
            evidence={"tool_call_count": len(calls), "observation_count": len(observations) if isinstance(observations, list) else 0},
        )


def _response_mentions_recovery(run: dict[str, Any]) -> bool:
    response = str(run.get("final_response", "")).lower()
    markers = ("retry", "tried again", "could not", "unable", "error", "failed", "fallback")
    return any(marker in response for marker in markers)


def _is_assistant_observation(observation: dict[str, Any]) -> bool:
    return observation.get("role") == "assistant" or observation.get("event_type") == "agent_response"
