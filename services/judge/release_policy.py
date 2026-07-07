"""Configurable A2 release policy selection and evaluation.

The engine is intentionally local and deterministic. It evaluates already
materialized judge reports, so it does not read private evidence or call live
model/API services.
"""

from __future__ import annotations

import hashlib
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select the best matching policy for a project/environment pair."""
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
    selected: tuple[int, int, int, dict[str, Any]] | None = None
    for index, assignment in enumerate(assignments):
        policy_id = str(assignment.get("policy_id", ""))
        if policy_id not in policies_by_id:
            raise ReleasePolicyError(f"assignment references unknown policy_id: {policy_id}")

        project_score = _match_score(assignment.get("project_id"), project_id)
        env_score = _match_score(assignment.get("environment", assignment.get("env")), environment)
        if project_score == 0 or env_score == 0:
            continue

        priority = int(assignment.get("priority", 0)) if _is_int_like(assignment.get("priority")) else 0
        candidate = (project_score + env_score + priority, project_score, -index, assignment)
        if selected is None or candidate[:3] > selected[:3]:
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
            }
        raise ReleasePolicyError(f"no release policy assignment for project_id={project_id!r} env={environment!r}")

    assignment = selected[3]
    policy = deepcopy(policies_by_id[str(assignment["policy_id"])])
    return policy, {
        "assignment_id": str(assignment.get("assignment_id") or assignment.get("id") or ""),
        "match_scope": _match_scope(assignment, project_id, environment),
        "project_id": project_id,
        "environment": environment,
    }


def evaluate_release_policy_config(
    config: dict[str, Any],
    *,
    project_id: str,
    environment: str,
    grade_report: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    release_candidate_id: str = "",
    waivers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    policy, selection = select_release_policy(config, project_id=project_id, environment=environment)
    return evaluate_release_policy(
        policy,
        grade_report=grade_report,
        metrics=metrics,
        project_id=project_id,
        environment=environment,
        release_candidate_id=release_candidate_id,
        selection=selection,
        waivers=waivers,
    )


def evaluate_release_policy(
    policy: dict[str, Any],
    *,
    grade_report: dict[str, Any],
    metrics: dict[str, Any] | None = None,
    project_id: str = "",
    environment: str = "",
    release_candidate_id: str = "",
    selection: dict[str, Any] | None = None,
    waivers: list[dict[str, Any]] | None = None,
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
        release_candidate_id=release_candidate_id,
        policy_id=str(policy.get("policy_id", "")),
        policy_version=str(policy.get("policy_version", "")),
    )
    active_violations = waiver_result["active_violations"]
    blockers = [item for item in active_violations if item["mode"] == "blocking"]
    warnings = [item for item in active_violations if item["mode"] != "blocking"]
    evaluated_rules = _mark_waived_rules(evaluated_rules, waiver_result["waived_violations"])

    decision = "block" if blockers else "warn" if warnings else "pass"
    policy_hash = compute_policy_hash(policy)
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "policy_id": str(policy.get("policy_id", "")),
        "policy_version": str(policy.get("policy_version", "")),
        "policy_hash": policy_hash,
        "project_id": project_id,
        "environment": environment,
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
        "evaluated_rules": evaluated_rules,
        "metrics": metric_summary,
        "failure_class_counts": failure_counts,
        "selection": selection or {},
        "metadata": {
            "deterministic": True,
            "requires_network": False,
            "requires_ashr_api_key": False,
            "does_not_execute_live_calls": True,
        },
    }


def _apply_waivers(
    violations: list[dict[str, Any]],
    waivers: list[dict[str, Any]],
    *,
    project_id: str,
    environment: str,
    release_candidate_id: str,
    policy_id: str,
    policy_version: str,
) -> dict[str, Any]:
    active_violations = [dict(item) for item in violations]
    waived_violations: list[dict[str, Any]] = []
    applied_waivers: list[dict[str, Any]] = []
    unapplied_waivers: list[dict[str, Any]] = []
    context = {
        "project_id": project_id,
        "environment": environment,
        "release_candidate_id": release_candidate_id,
        "policy_id": policy_id,
        "policy_version": policy_version,
    }

    for raw_waiver in waivers:
        waiver = _public_waiver_record(raw_waiver)
        invalid_reason = _waiver_invalid_reason(waiver, context)
        if invalid_reason:
            unapplied_waivers.append({**waiver, "unapplied_reason": invalid_reason})
            continue

        match_index = next(
            (
                index
                for index, violation in enumerate(active_violations)
                if _waiver_matches_violation(waiver, violation)
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
    return {
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
        "release_candidate_id",
        "policy_id",
        "policy_version",
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


def _waiver_invalid_reason(waiver: dict[str, Any], context: dict[str, str]) -> str:
    if not waiver:
        return "waiver_must_be_object"
    if waiver.get("status", "").strip().lower() != "approved":
        return "status_not_approved"
    if not _reviewer(waiver):
        return "missing_reviewer"
    if not waiver.get("reason", "").strip():
        return "missing_reason"
    if not _audit_anchor(waiver):
        return "missing_approval_or_evidence_ref"
    for field in ("project_id", "environment", "release_candidate_id", "policy_id", "policy_version"):
        if not _optional_scope_matches(waiver.get(field), context.get(field, "")):
            return f"{field}_scope_mismatch"
    return ""


def _waiver_matches_violation(waiver: dict[str, Any], violation: dict[str, Any]) -> bool:
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


def _audit_anchor(waiver: dict[str, Any]) -> str:
    evidence_refs = waiver.get("evidence_refs")
    if isinstance(evidence_refs, list) and evidence_refs:
        return str(evidence_refs[0])
    return str(waiver.get("approval_id") or waiver.get("evidence_ref") or "").strip()


def _optional_scope_matches(configured: Any, requested: str) -> bool:
    if configured is None or str(configured).strip() == "":
        return True
    if isinstance(configured, list):
        return any(_optional_scope_matches(item, requested) for item in configured)
    configured_text = str(configured)
    return configured_text in {"*", "any"} or configured_text == requested


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


def _match_scope(assignment: dict[str, Any], project_id: str, environment: str) -> str:
    project_exact = str(assignment.get("project_id", "*")) == project_id
    env_exact = str(assignment.get("environment", assignment.get("env", "*"))) == environment
    if project_exact and env_exact:
        return "project_environment"
    if project_exact:
        return "project_default_environment"
    if env_exact:
        return "environment_default_project"
    return "global_default"


def _normalize_mode(value: Any) -> str:
    if isinstance(value, bool):
        return "blocking" if value else "non_blocking"
    text = str(value).strip().lower().replace("-", "_")
    if text in {"non_blocking", "warning", "warn"}:
        return "non_blocking"
    return "blocking"


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
