"""Judge version registry for SaaS-grade A2 auditability."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .result_persistence import stable_hash


SCHEMA_VERSION = "a2.judge_versions.v1"
DEFAULT_REGISTRY_ID = "a2_judge_version_registry"
DEFAULT_CREATED_AT = "2026-07-07T00:00:00Z"
DEFAULT_JUDGE_VERSION = "0.1.0"


JUDGE_SPECS: dict[str, dict[str, Any]] = {
    "g1_trace_contract_judge": {
        "display_name": "Trace and Tool Contract Judge",
        "source_module": "services.judge.tool_policy.ToolPolicyJudge",
        "owner": "A2",
        "rubric_focus": ["skill_protocol", "argument_fidelity", "safety_permissions"],
        "failure_classes": [
            "missing_required_tool",
            "unnecessary_tool_call",
            "forbidden_tool_call",
            "wrong_tool",
            "wrong_arguments",
            "wrong_tool_order",
        ],
        "upgrade_policy": "pin_before_prod_release",
    },
    "g2_output_contract_judge": {
        "display_name": "Outcome Contract Judge",
        "source_module": "services.judge.outcome.OutcomeJudge",
        "owner": "A2",
        "rubric_focus": ["task_completion", "final_response_quality"],
        "failure_classes": ["wrong_intent", "missing_clarification", "unsafe_or_policy_violation"],
        "upgrade_policy": "pin_before_prod_release",
    },
    "g3_replay_sandbox_judge": {
        "display_name": "Replay and Trace Integrity Judge",
        "source_module": "services.judge.trace_integrity.TraceIntegrityJudge",
        "owner": "A2",
        "rubric_focus": ["task_completion", "skill_protocol", "argument_fidelity"],
        "failure_classes": ["wrong_tool", "wrong_arguments", "poor_failure_recovery"],
        "upgrade_policy": "pin_before_prod_release",
    },
    "g3_semantic_reference_judge": {
        "display_name": "Grounding and Reference Judge",
        "source_module": "services.judge.grounding.GroundingJudge",
        "owner": "A2",
        "rubric_focus": ["task_completion", "final_response_quality"],
        "failure_classes": ["hallucinated_tool_result", "ignored_tool_result", "wrong_intent"],
        "upgrade_policy": "review_calibration_diff_before_prod",
    },
    "g3_safety_boundary_judge": {
        "display_name": "Safety Boundary Judge",
        "source_module": "services.judge.safety_boundary.SafetyBoundaryJudge",
        "owner": "A2",
        "rubric_focus": ["safety_permissions"],
        "failure_classes": ["unsafe_or_policy_violation", "forbidden_tool_call"],
        "upgrade_policy": "block_unreviewed_prod_upgrade",
    },
}


def build_judge_version_registry(
    *,
    scenario_pack: dict[str, Any],
    grade_report: dict[str, Any],
    registry_id: str = DEFAULT_REGISTRY_ID,
    created_at: str = DEFAULT_CREATED_AT,
) -> dict[str, Any]:
    """Build a public-safe registry proving which judge versions evaluated results."""
    declared_modes = [str(mode) for mode in scenario_pack.get("judge_modes", [])]
    observed = _observed_judges(grade_report)
    judges = [_judge_entry(mode, observed.get(mode, {}), scenario_pack) for mode in declared_modes]
    undeclared_observed = sorted(set(observed) - set(declared_modes))
    registry_without_hash = {
        "schema_version": SCHEMA_VERSION,
        "registry_id": registry_id,
        "created_at": created_at,
        "scenario_pack_id": str(scenario_pack.get("pack_id", "")),
        "grade_report_id": str(grade_report.get("report_id", "")),
        "active_release": {
            "release_id": "a2-local-deterministic-judge-0.1",
            "status": "active",
            "default_version": DEFAULT_JUDGE_VERSION,
            "pinning_required_for_prod": True,
            "history_replay_supported": True,
        },
        "declared_judge_count": len(declared_modes),
        "observed_judge_count": len(observed),
        "all_declared_judges_observed": set(declared_modes).issubset(set(observed)),
        "undeclared_observed_judges": undeclared_observed,
        "judges": judges,
        "migration_policy": _migration_policy(judges),
        "service_contract": {
            "version_fields": [
                "judge_id",
                "judge_version",
                "registry_hash",
                "policy_hash",
                "input_hash",
                "output_hash",
            ],
            "pinning_supported": True,
            "history_replay_supported": True,
            "safe_to_compare_versions": True,
        },
        "metadata": {
            "public_safe": True,
            "deterministic": True,
            "requires_network": False,
            "requires_releasefoundry_api_key": False,
            "does_not_execute_live_calls": True,
            "raw_private_evidence_not_recorded": True,
            "secrets_not_recorded": True,
        },
    }
    return {
        **registry_without_hash,
        "registry_hash": stable_hash(registry_without_hash),
    }


def _observed_judges(grade_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for case_result in grade_report.get("grade_results", []):
        if not isinstance(case_result, dict):
            continue
        for judge_result in case_result.get("judge_results", []):
            if not isinstance(judge_result, dict):
                continue
            judge_id = str(judge_result.get("judge_mode", ""))
            if not judge_id:
                continue
            entry = observed.setdefault(
                judge_id,
                {
                    "versions": Counter(),
                    "result_schema_versions": Counter(),
                    "result_count": 0,
                    "passed_count": 0,
                    "failed_count": 0,
                    "failure_class_counts": Counter(),
                },
            )
            entry["result_count"] += 1
            if judge_result.get("passed") is True:
                entry["passed_count"] += 1
            else:
                entry["failed_count"] += 1
            entry["versions"][str(judge_result.get("judge_version", ""))] += 1
            entry["result_schema_versions"][str(judge_result.get("schema_version", ""))] += 1
            failure_class = str(judge_result.get("failure_analysis", {}).get("primary_failure_class", "none"))
            entry["failure_class_counts"][failure_class] += 1
    return observed


def _judge_entry(
    judge_id: str,
    observed: dict[str, Any],
    scenario_pack: dict[str, Any],
) -> dict[str, Any]:
    spec = JUDGE_SPECS.get(judge_id, {})
    versions = _counter_dict(observed.get("versions", Counter()))
    result_count = int(observed.get("result_count", 0))
    current_version = next(iter(versions), DEFAULT_JUDGE_VERSION)
    entry_without_hash = {
        "judge_id": judge_id,
        "display_name": str(spec.get("display_name", judge_id)),
        "current_version": current_version,
        "status": "active",
        "source_module": str(spec.get("source_module", "")),
        "owner": str(spec.get("owner", "A2")),
        "scenario_pack_id": str(scenario_pack.get("pack_id", "")),
        "result_schema_version": _first_counter_key(observed.get("result_schema_versions", Counter()), "a2.grade_result.v1"),
        "rubric_focus": list(spec.get("rubric_focus", [])),
        "failure_classes": list(spec.get("failure_classes", [])),
        "observed_result_count": result_count,
        "observed_versions": versions,
        "observed_result_schema_versions": _counter_dict(observed.get("result_schema_versions", Counter())),
        "observed_failure_class_counts": _counter_dict(observed.get("failure_class_counts", Counter())),
        "pinning": {
            "pin_supported": True,
            "pin_required_for_prod": True,
            "recommended_pin": f"{judge_id}@{current_version}",
        },
        "migration": {
            "history_replay_supported": True,
            "compare_before_after_supported": True,
            "deprecation_status": "not_deprecated",
            "upgrade_policy": str(spec.get("upgrade_policy", "pin_before_prod_release")),
        },
        "audit": {
            "deterministic": True,
            "requires_network": False,
            "requires_releasefoundry_api_key": False,
            "raw_private_evidence_not_recorded": True,
        },
    }
    return {
        **entry_without_hash,
        "judge_contract_hash": stable_hash(entry_without_hash),
    }


def _migration_policy(judges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "requires_registry_hash_on_release_gate": True,
        "requires_calibration_before_major_upgrade": True,
        "requires_history_replay_before_prod_unpin": True,
        "can_compare_judge_versions": all(judge.get("migration", {}).get("compare_before_after_supported") for judge in judges),
        "can_replay_history": all(judge.get("migration", {}).get("history_replay_supported") for judge in judges),
        "deprecated_judge_count": sum(1 for judge in judges if judge.get("migration", {}).get("deprecation_status") != "not_deprecated"),
    }


def _counter_dict(counter: Counter) -> dict[str, int]:
    return dict(sorted((str(key), int(value)) for key, value in counter.items() if str(key)))


def _first_counter_key(counter: Counter, default: str) -> str:
    if not counter:
        return default
    return str(counter.most_common(1)[0][0] or default)
