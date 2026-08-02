"""Configurable A2 release policy selection and evaluation.

The engine is intentionally local and deterministic. It evaluates already
materialized judge reports, so it does not read private evidence or call live
model/API services.
"""

from __future__ import annotations

import hashlib
import fnmatch
import json
from collections import Counter
from copy import deepcopy
from typing import Any


CONFIG_SCHEMA_VERSION = "a2.release_policy_config.v1"
EVALUATION_SCHEMA_VERSION = "a2.release_policy_evaluation.v1"
POLICY_HASH_PREFIX = "sha256:"


class ReleasePolicyError(ValueError):
    """Raised when a release policy config cannot be selected or evaluated."""


def compute_policy_hash(policy: dict[str, Any]) -> str:
    """Return a stable SHA-256 hash for a policy, excluding policy_hash itself."""
    return POLICY_HASH_PREFIX + hashlib.sha256(_policy_hash_material(policy).encode("utf-8")).hexdigest()


def policy_hash_matches(policy: dict[str, Any]) -> bool:
    expected = policy.get("policy_hash")
    return not expected or expected == compute_policy_hash(policy)


def select_release_policy(
    config: dict[str, Any],
    *,
    project_id: str,
    environment: str,
    branch: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select the best matching policy for a project/environment/branch context."""
    policies = config.get("policies")
    if not isinstance(policies, list) or not policies:
        raise ReleasePolicyError("release policy config must include at least one policy")

    policies_by_id = {
        str(policy.get("policy_id")): policy
        for policy in policies
        if isinstance(policy, dict) and policy.get("policy_id")
    }
    if not policies_by_id:
        raise ReleasePolicyError("release policy config has no usable policies")

    assignments = _configured_assignments(config, policies)
    selected: tuple[int, int, int, int, dict[str, Any]] | None = None
    for index, assignment in enumerate(assignments):
        policy_id = str(assignment.get("policy_id", ""))
        if policy_id not in policies_by_id:
            raise ReleasePolicyError(f"assignment references unknown policy_id: {policy_id}")

        project_score = _match_score(assignment.get("project_id"), project_id)
        env_score = _match_score(assignment.get("environment", assignment.get("env")), environment)
        branch_score = _branch_match_score(assignment, branch)
        if project_score == 0 or env_score == 0 or branch_score == 0:
            continue

        priority = int(assignment.get("priority", 0)) if _is_int_like(assignment.get("priority")) else 0
        candidate = (project_score + env_score + branch_score + priority, branch_score, project_score, -index, assignment)
        if selected is None or candidate[:4] > selected[:4]:
            selected = candidate

    if selected is None:
        default_policy_id = str(config.get("default_policy_id", ""))
        if default_policy_id and default_policy_id in policies_by_id:
            policy = deepcopy(policies_by_id[default_policy_id])
            return policy, {
                "assignment_id": "default_policy_id",
                "match_scope": "default_policy",
                "project_id": project_id,
                "environment": environment,
                "branch": branch,
            }
        raise ReleasePolicyError(f"no release policy assignment for project_id={project_id!r} env={environment!r}")

    assignment = selected[4]
    policy = deepcopy(policies_by_id[str(assignment["policy_id"])])
    return policy, {
        "assignment_id": str(assignment.get("assignment_id") or assignment.get("id") or ""),
        "match_scope": _match_scope(assignment, project_id, environment, branch),
        "project_id": project_id,
        "environment": environment,
        "branch": branch,
        "branch_pattern": _assignment_branch_pattern(assignment),
    }


def evaluate_release_policy_config(
    config: dict[str, Any],
    *,
    project_id: str,
    environment: str,
    branch: str = "",
    grade_report: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    release_candidate_id: str = "",
    waivers: list[dict[str, Any]] | None = None,
    approvals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    policy, selection = select_release_policy(config, project_id=project_id, environment=environment, branch=branch)
    return evaluate_release_policy(
        policy,
        grade_report=grade_report,
        metrics=metrics,
        project_id=project_id,
        environment=environment,
        branch=branch,
        release_candidate_id=release_candidate_id,
        selection=selection,
        waivers=waivers,
        approvals=approvals,
    )


def evaluate_release_policy(
    policy: dict[str, Any],
    *,
    grade_report: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    project_id: str = "",
    environment: str = "",
    branch: str = "",
    release_candidate_id: str = "",
    selection: dict[str, Any] | None = None,
    waivers: list[dict[str, Any]] | None = None,
    approvals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate failure-class and metric thresholds against a grade report."""
    if not policy_hash_matches(policy):
        raise ReleasePolicyError(f"policy_hash mismatch for policy_id={policy.get('policy_id')}")

    metric_summary = summarize_grade_report(grade_report)
    metric_summary.update(_number_metrics(metrics or {}))
    failure_counts = dict(metric_summary.pop("failure_class_counts"))

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    evaluated_rules: list[dict[str, Any]] = []
    rules = policy.get("rules")
    if not isinstance(rules, list):
        raise ReleasePolicyError("release policy must include a rules array")

    for rule in rules:
        if not isinstance(rule, dict):
            raise ReleasePolicyError("release policy rules must be objects")
        evaluation = _evaluate_rule(rule, metric_summary, failure_counts)
        evaluated_rules.append(evaluation)
        if not evaluation["passed"]:
            if evaluation["mode"] == "blocking":
                blockers.append(evaluation)
            else:
                warnings.append(evaluation)

    waiver_result = _apply_waivers(
        blockers + warnings,
        waivers or [],
        project_id=project_id,
        environment=environment,
        branch=branch,
        release_candidate_id=release_candidate_id,
        policy_id=str(policy.get("policy_id", "")),
        policy_version=str(policy.get("policy_version", "")),
        waiver_policy=policy.get("waiver_policy") if isinstance(policy.get("waiver_policy"), dict) else {},
    )
    active_violations = waiver_result["active_violations"]
    blockers = [item for item in active_violations if item["mode"] == "blocking"]
    warnings = [item for item in active_violations if item["mode"] != "blocking"]
    evaluated_rules = _mark_waived_rules(evaluated_rules, waiver_result["waived_violations"])

    blocking_mode = _normalize_blocking_mode(policy.get("blocking_mode", policy.get("metadata", {}).get("blocking_mode")))
    blocking_mode_result = _apply_blocking_mode(blockers, warnings, blocking_mode)
    blockers = blocking_mode_result["blockers"]
    warnings = blocking_mode_result["warnings"]

    risk_result = _evaluate_risk_thresholds(policy, blockers + warnings)
    if not blockers and risk_result["threshold_decision"] == "block":
        blockers.append(_risk_threshold_violation(risk_result))

    decision_before_approvals = _decision_from_violations(blockers, warnings)
    approval_result = _evaluate_approval_policy(
        policy,
        approvals or [],
        project_id=project_id,
        environment=environment,
        branch=branch,
        release_candidate_id=release_candidate_id,
        policy_id=str(policy.get("policy_id", "")),
        policy_version=str(policy.get("policy_version", "")),
        decision=decision_before_approvals,
        risk_result=risk_result,
        active_violations=blockers + warnings,
        waiver_result=waiver_result,
    )
    blockers.extend(_approval_blockers(approval_result))

    decision = _decision_from_violations(blockers, warnings)
    approval_result["decision_after_approval"] = decision
    policy_hash = compute_policy_hash(policy)
    evidence = _evaluation_evidence(
        policy=policy,
        selection=selection or {},
        decision=decision,
        decision_before_approvals=decision_before_approvals,
        blocking_mode_result=blocking_mode_result,
        risk_result=risk_result,
        waiver_result=waiver_result,
        approval_result=approval_result,
        active_violations=blockers + warnings,
    )
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "policy_id": str(policy.get("policy_id", "")),
        "policy_version": str(policy.get("policy_version", "")),
        "policy_hash": policy_hash,
        "project_id": project_id,
        "environment": environment,
        "branch": branch,
        "release_candidate_id": release_candidate_id,
        "decision": decision,
        "blocking_violation_count": len(blockers),
        "non_blocking_violation_count": len(warnings),
        "waived_violation_count": len(waiver_result["waived_violations"]),
        "violations": blockers + warnings,
        "waived_violations": waiver_result["waived_violations"],
        "waiver_summary": waiver_result["summary"],
        "applied_waivers": waiver_result["applied_waivers"],
        "unapplied_waivers": waiver_result["unapplied_waivers"],
        "approval_summary": approval_result["summary"],
        "applied_approvals": approval_result["applied_approvals"],
        "missing_approvals": approval_result["missing_approvals"],
        "unapplied_approvals": approval_result["unapplied_approvals"],
        "blocking_mode": blocking_mode,
        "blocking_mode_summary": blocking_mode_result["summary"],
        "risk": risk_result,
        "decision_evidence": evidence["decision_evidence"],
        "a3_gate_summary": evidence["a3_gate_summary"],
        "consumer_contract": evidence["consumer_contract"],
        "evaluated_rules": evaluated_rules,
        "metrics": metric_summary,
        "failure_class_counts": failure_counts,
        "selection": selection or {},
        "policy_context": {
            "project_id": project_id,
            "environment": environment,
            "branch": branch,
            "release_candidate_id": release_candidate_id,
        },
        "metadata": {
            "deterministic": True,
            "requires_network": False,
            "requires_releasefoundry_api_key": False,
            "does_not_execute_live_calls": True,
            "public_safe": True,
        },
    }


def _apply_waivers(
    violations: list[dict[str, Any]],
    waivers: list[dict[str, Any]],
    *,
    project_id: str,
    environment: str,
    branch: str,
    release_candidate_id: str,
    policy_id: str,
    policy_version: str,
    waiver_policy: dict[str, Any],
) -> dict[str, Any]:
    active_violations = [dict(item) for item in violations]
    waived_violations: list[dict[str, Any]] = []
    applied_waivers: list[dict[str, Any]] = []
    unapplied_waivers: list[dict[str, Any]] = []
    context = {
        "project_id": project_id,
        "environment": environment,
        "branch": branch,
        "release_candidate_id": release_candidate_id,
        "policy_id": policy_id,
        "policy_version": policy_version,
    }

    for raw_waiver in waivers:
        waiver = _public_waiver_record(raw_waiver)
        invalid_reason = _waiver_invalid_reason(waiver, context, waiver_policy)
        if invalid_reason:
            unapplied_waivers.append({**waiver, "unapplied_reason": invalid_reason})
            continue

        match_index = next(
            (
                index
                for index, violation in enumerate(active_violations)
                if _waiver_matches_violation(waiver, violation, waiver_policy)
            ),
            None,
        )
        if match_index is None:
            unapplied_waivers.append({**waiver, "unapplied_reason": "no_matching_active_violation"})
            continue

        violation = dict(active_violations.pop(match_index))
        waiver_ref = _waiver_reference(waiver)
        violation["waived"] = True
        violation["waiver"] = waiver_ref
        waived_violations.append(violation)
        applied_waivers.append(
            {
                **waiver_ref,
                "waived_rule_id": violation.get("rule_id", ""),
                "waived_mode": violation.get("mode", ""),
                "waived_severity": violation.get("severity", ""),
                "waived_type": violation.get("type", ""),
            }
        )

    return {
        "active_violations": active_violations,
        "waived_violations": waived_violations,
        "applied_waivers": applied_waivers,
        "unapplied_waivers": unapplied_waivers,
        "summary": {
            "submitted_count": len(waivers),
            "applied_count": len(applied_waivers),
            "unapplied_count": len(unapplied_waivers),
            "waived_blocking_count": sum(1 for item in waived_violations if item.get("mode") == "blocking"),
            "waived_non_blocking_count": sum(1 for item in waived_violations if item.get("mode") != "blocking"),
            "active_blocking_count": sum(1 for item in active_violations if item.get("mode") == "blocking"),
            "active_non_blocking_count": sum(1 for item in active_violations if item.get("mode") != "blocking"),
        },
    }


def _mark_waived_rules(
    evaluated_rules: list[dict[str, Any]],
    waived_violations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    waived_by_rule_id = {str(item.get("rule_id", "")): item.get("waiver", {}) for item in waived_violations}
    marked: list[dict[str, Any]] = []
    for rule in evaluated_rules:
        next_rule = dict(rule)
        waiver = waived_by_rule_id.get(str(rule.get("rule_id", "")))
        if waiver:
            next_rule["waived"] = True
            next_rule["waiver"] = waiver
        marked.append(next_rule)
    return marked


def _apply_blocking_mode(
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    blocking_mode: str,
) -> dict[str, Any]:
    if blocking_mode not in {"warn_only", "observe"}:
        return {
            "blockers": blockers,
            "warnings": warnings,
            "summary": {
                "mode": blocking_mode,
                "demoted_blocking_count": 0,
                "enforced_blocking_count": len(blockers),
            },
        }

    demoted = []
    for blocker in blockers:
        item = dict(blocker)
        item["original_mode"] = item.get("mode", "blocking")
        item["mode"] = "non_blocking"
        item["blocking_mode_override"] = blocking_mode
        demoted.append(item)
    return {
        "blockers": [],
        "warnings": demoted + warnings,
        "summary": {
            "mode": blocking_mode,
            "demoted_blocking_count": len(demoted),
            "enforced_blocking_count": 0,
        },
    }


def _decision_from_violations(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> str:
    return "block" if blockers else "warn" if warnings else "pass"


def _evaluate_risk_thresholds(policy: dict[str, Any], active_violations: list[dict[str, Any]]) -> dict[str, Any]:
    risk_config = policy.get("risk_thresholds")
    if not isinstance(risk_config, dict):
        risk_config = {}
    weights = {
        "critical": 40.0,
        "high": 25.0,
        "medium": 10.0,
        "low": 3.0,
    }
    configured_weights = risk_config.get("severity_weights")
    if isinstance(configured_weights, dict):
        for severity, weight in configured_weights.items():
            number = _to_number(weight)
            if number is not None:
                weights[str(severity)] = float(number)

    score = 0.0
    contributions = []
    for violation in active_violations:
        explicit_weight = _to_number(violation.get("risk_weight"))
        severity = str(violation.get("severity", "medium"))
        base_weight = explicit_weight if explicit_weight is not None else weights.get(severity, 5.0)
        mode_factor = 1.0 if violation.get("mode") == "blocking" else 0.5
        contribution = round(float(base_weight) * mode_factor, 4)
        score += contribution
        contributions.append(
            {
                "rule_id": str(violation.get("rule_id", "")),
                "severity": severity,
                "mode": str(violation.get("mode", "")),
                "weight": round(float(base_weight), 4),
                "mode_factor": mode_factor,
                "contribution": contribution,
            }
        )

    score = min(round(score, 4), 100.0)
    warn_threshold = _to_number(risk_config.get("warn_threshold"))
    block_threshold = _to_number(risk_config.get("block_threshold"))
    if warn_threshold is None:
        warn_threshold = 25.0
    if block_threshold is None:
        block_threshold = 75.0
    threshold_decision = "pass"
    band = "low"
    if score >= block_threshold:
        threshold_decision = "block"
        band = "blocking"
    elif score >= warn_threshold:
        threshold_decision = "warn"
        band = "warning"

    return {
        "score": score,
        "band": band,
        "threshold_decision": threshold_decision,
        "warn_threshold": float(warn_threshold),
        "block_threshold": float(block_threshold),
        "contributions": contributions,
    }


def _risk_threshold_violation(risk_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": "risk_threshold_block",
        "type": "risk_threshold",
        "mode": "blocking",
        "severity": "high",
        "passed": False,
        "summary": "Accumulated release risk exceeded the blocking threshold.",
        "observed": {"risk_score": risk_result["score"], "risk_band": risk_result["band"]},
        "threshold": {"operator": "<", "threshold": risk_result["block_threshold"]},
        "remediation": ["Reduce active policy violations or attach approved release exceptions."],
    }


def _evaluate_approval_policy(
    policy: dict[str, Any],
    approvals: list[dict[str, Any]],
    *,
    project_id: str,
    environment: str,
    branch: str,
    release_candidate_id: str,
    policy_id: str,
    policy_version: str,
    decision: str,
    risk_result: dict[str, Any],
    active_violations: list[dict[str, Any]],
    waiver_result: dict[str, Any],
) -> dict[str, Any]:
    approval_policy = policy.get("approval_policy")
    if not isinstance(approval_policy, dict):
        approval_policy = {}
    approval_sources = [_public_approval_record(item) for item in approvals if isinstance(item, dict)]
    approval_sources.extend(_approval_source_from_waiver(item) for item in waiver_result["applied_waivers"])
    approval_sources = [item for item in approval_sources if item]
    context = {
        "project_id": project_id,
        "environment": environment,
        "branch": branch,
        "release_candidate_id": release_candidate_id,
        "policy_id": policy_id,
        "policy_version": policy_version,
    }
    triggers = _approval_triggers(
        environment=environment,
        branch=branch,
        decision=decision,
        risk_result=risk_result,
        active_violations=active_violations,
        waiver_result=waiver_result,
    )

    requirements = [
        requirement
        for requirement in approval_policy.get("requirements", [])
        if isinstance(requirement, dict) and _approval_requirement_applies(requirement, triggers, context)
    ]
    applied_approvals = []
    missing_approvals = []
    used_approval_ids: set[str] = set()
    for requirement in requirements:
        matches = [
            approval
            for approval in approval_sources
            if _approval_matches_requirement(approval, requirement, context)
        ]
        min_count = int(_to_number(requirement.get("min_count")) or 1)
        applied = matches[:min_count]
        used_approval_ids.update(str(item.get("approval_id", "")) for item in applied if item.get("approval_id"))
        applied_approvals.extend(
            {
                **item,
                "requirement_id": str(requirement.get("requirement_id", "")),
            }
            for item in applied
        )
        if len(matches) < min_count:
            missing_approvals.append(
                {
                    "requirement_id": str(requirement.get("requirement_id", "")),
                    "approval_type": str(requirement.get("approval_type", "")),
                    "min_count": min_count,
                    "approved_count": len(matches),
                    "missing_count": min_count - len(matches),
                    "when": _string_list(requirement.get("when")) or ["always"],
                    "roles": _string_list(requirement.get("roles")),
                    "summary": str(requirement.get("summary", "Approval requirement is not satisfied.")),
                }
            )

    unapplied_approvals = [
        {**approval, "unapplied_reason": "no_matching_approval_requirement"}
        for approval in approval_sources
        if approval.get("approval_id") and approval.get("approval_id") not in used_approval_ids
    ]
    block_on_missing = approval_policy.get("block_on_missing_approvals") is True
    blocking_missing = missing_approvals if block_on_missing else []
    return {
        "triggers": sorted(triggers),
        "required_approvals": requirements,
        "applied_approvals": applied_approvals,
        "missing_approvals": missing_approvals,
        "unapplied_approvals": unapplied_approvals,
        "blocking_missing_approvals": blocking_missing,
        "summary": {
            "required_count": len(requirements),
            "applied_count": len(applied_approvals),
            "missing_count": len(missing_approvals),
            "blocking_missing_count": len(blocking_missing),
            "status": "missing" if missing_approvals else "approved" if requirements else "not_required",
            "block_on_missing_approvals": block_on_missing,
        },
    }


def _approval_blockers(approval_result: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = []
    for missing in approval_result["blocking_missing_approvals"]:
        blockers.append(
            {
                "rule_id": f"approval_required::{missing.get('requirement_id', '')}",
                "type": "approval_required",
                "mode": "blocking",
                "severity": "high",
                "passed": False,
                "summary": missing.get("summary", "Required approval is missing."),
                "observed": {
                    "approved_count": missing.get("approved_count", 0),
                    "missing_count": missing.get("missing_count", 0),
                },
                "threshold": {
                    "approval_type": missing.get("approval_type", ""),
                    "min_count": missing.get("min_count", 1),
                },
                "remediation": ["Collect the required release approval and rerun policy evaluation."],
            }
        )
    return blockers


def _approval_triggers(
    *,
    environment: str,
    branch: str,
    decision: str,
    risk_result: dict[str, Any],
    active_violations: list[dict[str, Any]],
    waiver_result: dict[str, Any],
) -> set[str]:
    triggers = {"always", f"environment:{environment}", f"decision:{decision}", f"risk:{risk_result['band']}"}
    if environment == "prod":
        triggers.add("prod_release")
    if branch:
        triggers.add(f"branch:{branch}")
    if any(item.get("mode") == "blocking" for item in active_violations):
        triggers.add("blocking_violation")
    if any(item.get("mode") != "blocking" for item in active_violations):
        triggers.add("non_blocking_violation")
    if waiver_result["applied_waivers"]:
        triggers.add("waiver_applied")
    if any(item.get("waived_mode") == "blocking" for item in waiver_result["applied_waivers"]):
        triggers.add("blocking_waiver")
    return triggers


def _approval_requirement_applies(
    requirement: dict[str, Any],
    triggers: set[str],
    context: dict[str, str],
) -> bool:
    if not _scope_list_matches(requirement.get("environments"), context.get("environment", "")):
        return False
    if not _scope_list_matches(requirement.get("branches"), context.get("branch", "")):
        return False
    when = _string_list(requirement.get("when")) or ["always"]
    return any(_trigger_matches(pattern, triggers) for pattern in when)


def _approval_matches_requirement(
    approval: dict[str, Any],
    requirement: dict[str, Any],
    context: dict[str, str],
) -> bool:
    if approval.get("status", "").strip().lower() != "approved":
        return False
    if not _optional_scope_matches(approval.get("project_id"), context.get("project_id", "")):
        return False
    if not _optional_scope_matches(approval.get("environment"), context.get("environment", "")):
        return False
    if not _optional_scope_matches(approval.get("branch"), context.get("branch", "")):
        return False
    if not _optional_scope_matches(approval.get("release_candidate_id"), context.get("release_candidate_id", "")):
        return False
    approval_type = str(requirement.get("approval_type", ""))
    if approval_type and approval_type != str(approval.get("approval_type", approval.get("type", ""))):
        return False
    roles = _string_list(requirement.get("roles"))
    if roles and str(approval.get("approver_role", approval.get("reviewer_role", ""))) not in roles:
        return False
    return bool(approval.get("approval_id") or approval.get("evidence_ref") or approval.get("evidence_refs"))


def _public_approval_record(raw_approval: dict[str, Any]) -> dict[str, Any]:
    record = {}
    for field in (
        "approval_id",
        "approval_type",
        "type",
        "status",
        "project_id",
        "environment",
        "branch",
        "release_candidate_id",
        "policy_id",
        "policy_version",
        "approver",
        "approved_by",
        "reviewer",
        "reviewer_role",
        "approver_role",
        "reason",
        "evidence_ref",
        "approved_at",
        "expires_at",
    ):
        value = raw_approval.get(field)
        if value is not None:
            record[field] = str(value)
    evidence_refs = raw_approval.get("evidence_refs")
    if isinstance(evidence_refs, list):
        record["evidence_refs"] = [str(item) for item in evidence_refs if str(item).strip()]
    return record


def _approval_source_from_waiver(applied_waiver: dict[str, Any]) -> dict[str, Any]:
    approval_id = str(applied_waiver.get("approval_id", "")).strip()
    if not approval_id:
        return {}
    return {
        "approval_id": approval_id,
        "approval_type": "release_exception",
        "status": "approved",
        "reviewer": str(applied_waiver.get("reviewer", "")),
        "reviewer_role": str(applied_waiver.get("reviewer_role", "")),
        "reason": str(applied_waiver.get("reason", "")),
        "source": "waiver",
    }


def _evaluation_evidence(
    *,
    policy: dict[str, Any],
    selection: dict[str, Any],
    decision: str,
    decision_before_approvals: str,
    blocking_mode_result: dict[str, Any],
    risk_result: dict[str, Any],
    waiver_result: dict[str, Any],
    approval_result: dict[str, Any],
    active_violations: list[dict[str, Any]],
) -> dict[str, Any]:
    active_rule_ids = [str(item.get("rule_id", "")) for item in active_violations if item.get("rule_id")]
    waived_rule_ids = [
        str(item.get("rule_id", ""))
        for item in waiver_result["waived_violations"]
        if item.get("rule_id")
    ]
    decision_evidence = {
        "decision": decision,
        "decision_before_approvals": decision_before_approvals,
        "policy_id": str(policy.get("policy_id", "")),
        "policy_version": str(policy.get("policy_version", "")),
        "selection": selection,
        "active_rule_ids": active_rule_ids,
        "waived_rule_ids": waived_rule_ids,
        "risk_score": risk_result["score"],
        "risk_band": risk_result["band"],
        "blocking_mode": blocking_mode_result["summary"]["mode"],
        "approval_status": approval_result["summary"]["status"],
        "approval_triggers": approval_result["triggers"],
        "public_safe": True,
    }
    return {
        "decision_evidence": decision_evidence,
        "a3_gate_summary": {
            "status": decision.upper(),
            "risk_score": risk_result["score"],
            "risk_band": risk_result["band"],
            "blocking_count": sum(1 for item in active_violations if item.get("mode") == "blocking"),
            "warning_count": sum(1 for item in active_violations if item.get("mode") != "blocking"),
            "waived_count": len(waiver_result["waived_violations"]),
            "approval_status": approval_result["summary"]["status"],
            "missing_approval_count": approval_result["summary"]["missing_count"],
            "policy_badge": str(policy.get("dashboard_label") or policy.get("policy_id", "")),
            "match_scope": str(selection.get("match_scope", "")),
        },
        "consumer_contract": {
            "service_wrapper_stable_fields": [
                "decision",
                "violations",
                "waived_violations",
                "risk",
                "approval_summary",
                "selection",
            ],
            "a3_release_gate_fields": [
                "a3_gate_summary",
                "decision_evidence",
                "evaluated_rules",
                "applied_waivers",
                "missing_approvals",
            ],
            "private_evidence_policy": "Only public refs and reviewer metadata are emitted; raw private evidence is not read.",
        },
    }


def summarize_grade_report(grade_report: dict[str, Any]) -> dict[str, Any]:
    grade_results = grade_report.get("grade_results")
    rows = grade_results if isinstance(grade_results, list) else []
    total_cases = _number_or(grade_report.get("total_cases"), len(rows))
    passed = _number_or(grade_report.get("passed", grade_report.get("passed_count")), _count_passed(rows))
    failed = _number_or(grade_report.get("failed", grade_report.get("failed_count")), max(0, total_cases - passed))
    scores = [_to_number(row.get("score")) for row in rows if isinstance(row, dict) and _to_number(row.get("score")) is not None]
    average_score = _to_number(grade_report.get("average_score"))
    if average_score is None:
        average_score = round(sum(scores) / len(scores), 4) if scores else 0.0

    counts = Counter()
    configured_counts = grade_report.get("primary_failure_class_counts")
    if isinstance(configured_counts, dict):
        counts.update({str(key): int(value) for key, value in configured_counts.items() if _is_int_like(value)})
    elif rows:
        for row in rows:
            if not isinstance(row, dict):
                continue
            failure_class = str(row.get("primary_failure_class", "none"))
            if failure_class != "none":
                counts[failure_class] += 1

    safety_blocking_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        for judge_result in row.get("judge_results", []):
            if isinstance(judge_result, dict) and judge_result.get("failure_analysis", {}).get("safety_blocking") is True:
                safety_blocking_count += 1

    denominator = total_cases if total_cases > 0 else 1
    return {
        "total_cases": total_cases,
        "passed": passed,
        "failed": failed,
        "pass_rate": round((passed / denominator) * 100, 4),
        "fail_rate": round((failed / denominator) * 100, 4),
        "average_score": round(float(average_score), 4),
        "safety_blocking_count": safety_blocking_count,
        "usage_quota_blocked": 0,
        "trust_publishability_blocked": 0,
        "api_key_boundary_violations": 0,
        "server_side_grading_stale": 0,
        "failure_class_counts": dict(sorted(counts.items())),
    }


def _evaluate_rule(
    rule: dict[str, Any],
    metrics: dict[str, Any],
    failure_counts: dict[str, int],
) -> dict[str, Any]:
    rule_type = str(rule.get("type", ""))
    if rule_type == "failure_class_threshold":
        return _evaluate_failure_class_rule(rule, metrics, failure_counts)
    if rule_type == "metric_threshold":
        return _evaluate_metric_rule(rule, metrics)
    raise ReleasePolicyError(f"unsupported release policy rule type: {rule_type}")


def _evaluate_failure_class_rule(
    rule: dict[str, Any],
    metrics: dict[str, Any],
    failure_counts: dict[str, int],
) -> dict[str, Any]:
    failure_class = str(rule.get("failure_class", ""))
    if not failure_class:
        raise ReleasePolicyError("failure_class_threshold rule requires failure_class")

    count = int(failure_counts.get(failure_class, 0))
    total_cases = int(metrics.get("total_cases", 0))
    rate = round((count / total_cases) * 100, 4) if total_cases else 0.0
    max_count = _to_number(rule.get("max_count"))
    max_rate = _to_number(rule.get("max_rate"))
    count_ok = max_count is None or count <= max_count
    rate_ok = max_rate is None or rate <= max_rate
    passed = count_ok and rate_ok
    threshold = {}
    if max_count is not None:
        threshold["max_count"] = max_count
    if max_rate is not None:
        threshold["max_rate"] = max_rate
    return _rule_result(
        rule,
        passed=passed,
        observed={"failure_class": failure_class, "count": count, "rate": rate},
        threshold=threshold,
        summary=(
            f"{failure_class} count/rate within policy threshold."
            if passed
            else f"{failure_class} exceeded release policy threshold."
        ),
    )


def _evaluate_metric_rule(rule: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    metric = str(rule.get("metric", ""))
    if metric not in metrics:
        raise ReleasePolicyError(f"metric_threshold rule references unknown metric: {metric}")
    value = _to_number(metrics.get(metric))
    threshold = _to_number(rule.get("threshold"))
    if value is None or threshold is None:
        raise ReleasePolicyError("metric_threshold rule requires numeric observed value and threshold")
    operator = str(rule.get("operator", ">="))
    passed = _compare(value, operator, threshold)
    return _rule_result(
        rule,
        passed=passed,
        observed={"metric": metric, "value": value},
        threshold={"operator": operator, "threshold": threshold},
        summary=(
            f"{metric} satisfied {operator} {threshold}."
            if passed
            else f"{metric} failed {operator} {threshold}."
        ),
    )


def _rule_result(
    rule: dict[str, Any],
    *,
    passed: bool,
    observed: dict[str, Any],
    threshold: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    result = {
        "rule_id": str(rule.get("rule_id", "")),
        "type": str(rule.get("type", "")),
        "mode": _normalize_mode(rule.get("mode", rule.get("blocking", "blocking"))),
        "severity": str(rule.get("severity", "high")),
        "passed": passed,
        "summary": str(rule.get("summary") or summary),
        "observed": observed,
        "threshold": threshold,
        "remediation": [str(item) for item in rule.get("remediation", []) if str(item).strip()]
        if isinstance(rule.get("remediation"), list)
        else [],
    }
    optional_fields = {
        "owner_role": rule.get("owner_role"),
        "business_impact": rule.get("business_impact"),
        "dashboard_label": rule.get("dashboard_label"),
        "waiver_eligible": rule.get("waiver_eligible"),
        "risk_weight": _to_number(rule.get("risk_weight")),
        "approval_requirement": rule.get("approval_requirement"),
        "evidence_refs": _string_list(rule.get("evidence_refs")),
    }
    for key, value in optional_fields.items():
        if value not in (None, "", []):
            result[key] = value
    return result


def _public_waiver_record(raw_waiver: Any) -> dict[str, Any]:
    if not isinstance(raw_waiver, dict):
        return {}
    record: dict[str, Any] = {}
    for field in (
        "waiver_id",
        "approval_id",
        "status",
        "rule_id",
        "failure_class",
        "metric",
        "project_id",
        "environment",
        "branch",
        "release_candidate_id",
        "policy_id",
        "policy_version",
        "reviewer_role",
        "approver_role",
        "reviewer",
        "reviewed_by",
        "approver",
        "approved_by",
        "reason",
        "evidence_ref",
        "expires_at",
    ):
        value = raw_waiver.get(field)
        if value is not None:
            record[field] = str(value)
    evidence_refs = raw_waiver.get("evidence_refs")
    if isinstance(evidence_refs, list):
        record["evidence_refs"] = [str(item) for item in evidence_refs if str(item).strip()]
    return record


def _waiver_invalid_reason(
    waiver: dict[str, Any],
    context: dict[str, str],
    waiver_policy: dict[str, Any],
) -> str:
    if not waiver:
        return "waiver_must_be_object"
    if waiver_policy.get("allowed") is False:
        return "waivers_disabled"
    if waiver.get("status", "").strip().lower() != "approved":
        return "status_not_approved"
    if not _reviewer(waiver):
        return "missing_reviewer"
    if not waiver.get("reason", "").strip():
        return "missing_reason"
    if not _audit_anchor(waiver):
        return "missing_approval_or_evidence_ref"
    for field in ("project_id", "environment", "branch", "release_candidate_id", "policy_id", "policy_version"):
        if not _optional_scope_matches(waiver.get(field), context.get(field, "")):
            return f"{field}_scope_mismatch"
    for field in _string_list(waiver_policy.get("required_fields")):
        if not str(waiver.get(field, "")).strip():
            return f"missing_{field}"
    if waiver_policy.get("requires_approval_id") is True and not waiver.get("approval_id"):
        return "missing_approval_id"
    if waiver_policy.get("requires_evidence_ref") is True and not _evidence_anchor(waiver):
        return "missing_evidence_ref"
    if waiver_policy.get("requires_expires_at") is True and not waiver.get("expires_at"):
        return "missing_expires_at"
    reviewer_roles = _string_list(waiver_policy.get("reviewer_roles"))
    if reviewer_roles and _reviewer_role(waiver) not in reviewer_roles:
        return "reviewer_role_not_allowed"
    if not _scope_list_matches(waiver_policy.get("allowed_environments"), context.get("environment", "")):
        return "environment_not_allowed"
    if not _scope_list_matches(waiver_policy.get("allowed_branches"), context.get("branch", "")):
        return "branch_not_allowed"
    return ""


def _waiver_matches_violation(
    waiver: dict[str, Any],
    violation: dict[str, Any],
    waiver_policy: dict[str, Any],
) -> bool:
    if not _violation_waivable(violation, waiver_policy):
        return False
    checks: list[bool] = []
    if waiver.get("rule_id"):
        checks.append(waiver["rule_id"] == str(violation.get("rule_id", "")))
    observed = violation.get("observed", {})
    if not isinstance(observed, dict):
        observed = {}
    if waiver.get("failure_class"):
        checks.append(waiver["failure_class"] == str(observed.get("failure_class", "")))
    if waiver.get("metric"):
        checks.append(waiver["metric"] == str(observed.get("metric", "")))
    return bool(checks) and all(checks)


def _waiver_reference(waiver: dict[str, Any]) -> dict[str, Any]:
    reference = {
        "waiver_id": waiver.get("waiver_id", ""),
        "approval_id": waiver.get("approval_id", ""),
        "status": waiver.get("status", ""),
        "reviewer": _reviewer(waiver),
        "reviewer_role": _reviewer_role(waiver),
        "reason": waiver.get("reason", ""),
        "evidence_ref": waiver.get("evidence_ref", ""),
        "expires_at": waiver.get("expires_at", ""),
    }
    if waiver.get("evidence_refs"):
        reference["evidence_refs"] = waiver["evidence_refs"]
    return {key: value for key, value in reference.items() if value}


def _reviewer(waiver: dict[str, Any]) -> str:
    return str(
        waiver.get("reviewer")
        or waiver.get("reviewed_by")
        or waiver.get("approver")
        or waiver.get("approved_by")
        or ""
    ).strip()


def _reviewer_role(waiver: dict[str, Any]) -> str:
    return str(waiver.get("reviewer_role") or waiver.get("approver_role") or "").strip()


def _audit_anchor(waiver: dict[str, Any]) -> str:
    evidence_refs = waiver.get("evidence_refs")
    if isinstance(evidence_refs, list) and evidence_refs:
        return str(evidence_refs[0])
    return str(waiver.get("approval_id") or waiver.get("evidence_ref") or "").strip()


def _evidence_anchor(waiver: dict[str, Any]) -> str:
    evidence_refs = waiver.get("evidence_refs")
    if isinstance(evidence_refs, list) and evidence_refs:
        return str(evidence_refs[0])
    return str(waiver.get("evidence_ref") or "").strip()


def _violation_waivable(violation: dict[str, Any], waiver_policy: dict[str, Any]) -> bool:
    non_waivable_rule_ids = set(_string_list(waiver_policy.get("non_waivable_rule_ids")))
    if str(violation.get("rule_id", "")) in non_waivable_rule_ids:
        return False
    allowed_modes = set(_string_list(waiver_policy.get("allowed_modes")))
    if allowed_modes and str(violation.get("mode", "")) not in allowed_modes:
        return False
    allowed_severities = set(_string_list(waiver_policy.get("allowed_severities")))
    if allowed_severities and str(violation.get("severity", "")) not in allowed_severities:
        return False
    if violation.get("waiver_eligible") is False:
        return False
    return True


def _optional_scope_matches(configured: Any, requested: str) -> bool:
    if configured is None or str(configured).strip() == "":
        return True
    if isinstance(configured, list):
        return any(_optional_scope_matches(item, requested) for item in configured)
    configured_text = str(configured)
    return configured_text in {"*", "any"} or configured_text == requested


def _scope_list_matches(configured: Any, requested: str) -> bool:
    if configured is None or configured == "":
        return True
    values = _string_list(configured)
    if not values:
        return True
    return any(value in {"*", "any"} or fnmatch.fnmatchcase(requested, value) for value in values)


def _trigger_matches(pattern: str, triggers: set[str]) -> bool:
    return any(fnmatch.fnmatchcase(trigger, pattern) for trigger in triggers)


def _configured_assignments(config: dict[str, Any], policies: list[Any]) -> list[dict[str, Any]]:
    assignments = [item for item in config.get("assignments", []) if isinstance(item, dict)]
    for policy in policies:
        if not isinstance(policy, dict):
            continue
        if "project_id" not in policy and "environment" not in policy and "environments" not in policy:
            continue
        environments = policy.get("environments", policy.get("environment", "*"))
        if not isinstance(environments, list):
            environments = [environments]
        for env in environments:
            assignments.append(
                {
                    "assignment_id": f"inline::{policy.get('policy_id')}::{env}",
                    "project_id": policy.get("project_id", "*"),
                    "environment": env,
                    "policy_id": policy.get("policy_id"),
                }
            )
    return assignments


def _policy_hash_material(policy: dict[str, Any]) -> str:
    material = deepcopy(policy)
    material.pop("policy_hash", None)
    return json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _match_score(configured: Any, requested: str) -> int:
    if configured is None:
        configured = "*"
    if isinstance(configured, list):
        return max((_match_score(item, requested) for item in configured), default=0)
    configured_text = str(configured)
    if configured_text == requested:
        return 100
    if configured_text == "*":
        return 10
    return 0


def _branch_match_score(assignment: dict[str, Any], branch: str) -> int:
    configured = assignment.get("branch", assignment.get("branches", "*"))
    if configured is None:
        configured = "*"
    values = _string_list(configured)
    if not values:
        values = ["*"]
    if not branch and not any(value in {"*", "any"} for value in values):
        return 0
    return max((_branch_pattern_score(value, branch) for value in values), default=0)


def _branch_pattern_score(pattern: str, branch: str) -> int:
    pattern = str(pattern)
    if pattern in {"*", "any"}:
        return 10
    if pattern == branch:
        return 75
    if branch and fnmatch.fnmatchcase(branch, pattern):
        return 50
    return 0


def _assignment_branch_pattern(assignment: dict[str, Any]) -> str:
    configured = assignment.get("branch", assignment.get("branches", "*"))
    if isinstance(configured, list):
        return ",".join(str(item) for item in configured)
    return str(configured)


def _match_scope(assignment: dict[str, Any], project_id: str, environment: str, branch: str) -> str:
    project_exact = str(assignment.get("project_id", "*")) == project_id
    env_exact = str(assignment.get("environment", assignment.get("env", "*"))) == environment
    branch_pattern = _assignment_branch_pattern(assignment)
    branch_exact = branch_pattern == branch and branch != ""
    branch_constrained = bool(branch) and branch_pattern not in {"*", "any", ""}
    if project_exact and env_exact:
        return "project_environment_branch" if branch_exact or branch_constrained else "project_environment"
    if project_exact:
        return "project_default_environment"
    if env_exact:
        return "environment_branch_default_project" if branch_exact or branch_constrained else "environment_default_project"
    return "global_default"


def _normalize_mode(value: Any) -> str:
    if isinstance(value, bool):
        return "blocking" if value else "non_blocking"
    text = str(value).strip().lower().replace("-", "_")
    if text in {"non_blocking", "warning", "warn"}:
        return "non_blocking"
    return "blocking"


def _normalize_blocking_mode(value: Any) -> str:
    text = str(value or "enforce").strip().lower().replace("-", "_")
    if text in {"warn_only", "observe", "advisory"}:
        return "warn_only" if text == "advisory" else text
    return "enforce"


def _compare(value: float, operator: str, threshold: float) -> bool:
    if operator == ">=":
        return value >= threshold
    if operator == ">":
        return value > threshold
    if operator == "<=":
        return value <= threshold
    if operator == "<":
        return value < threshold
    if operator == "==":
        return value == threshold
    if operator == "!=":
        return value != threshold
    raise ReleasePolicyError(f"unsupported metric threshold operator: {operator}")


def _number_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    return {str(key): value for key, value in metrics.items() if _to_number(value) is not None}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _number_or(value: Any, default: int) -> int:
    number = _to_number(value)
    return int(number) if number is not None else int(default)


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _is_int_like(value: Any) -> bool:
    number = _to_number(value)
    return number is not None and int(number) == number


def _count_passed(rows: list[Any]) -> int:
    return sum(1 for row in rows if isinstance(row, dict) and row.get("passed") is True)
