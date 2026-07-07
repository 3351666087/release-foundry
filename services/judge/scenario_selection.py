"""Project-aware scenario pack selection for A2 SaaS workflows."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .coverage import (
    _capability_axis_refs,
    _is_media_or_multimodal,
    _scenario_dimension_refs,
    _tags,
)
from .runner import DEFAULT_SCENARIO_PACK, load_scenario_pack


DEFAULT_PROJECT_PROFILE: dict[str, Any] = {
    "schema_version": "a2.scenario_selection_profile.v1",
    "selection_id": "a2_enterprise_saas_prod_selection",
    "tenant": {
        "organization_id": "org_enterprise_saas",
        "workspace_id": "workspace_eval_ops",
        "tenant_id": "tenant_enterprise_saas",
    },
    "project": {
        "project_id": "project_enterprise_saas_agent",
        "name": "Enterprise SaaS Support Agent",
    },
    "environment": "prod",
    "capability_axes": [
        "tool_choice_and_policy",
        "trace_contract",
        "grounding_and_reference",
        "safety_boundary",
        "enterprise_saas_operations",
        "media_and_multimodal",
    ],
    "risk_tiers": ["high", "critical"],
    "media_requirement": "required",
    "required_axis_minimums": {
        "enterprise_saas_operations": 6,
        "media_and_multimodal": 1,
        "safety_boundary": 2,
        "trace_contract": 2,
    },
    "required_tags": ["enterprise-saas"],
    "required_tag_minimum": 4,
    "tenant_saas_tags": [
        "admin-audit",
        "billing-risk",
        "change-management",
        "enterprise-saas",
        "privacy-compliance",
        "saas-observability",
        "secrets-management",
        "skill-governance",
    ],
    "minimums": {
        "golden_case_count": 4,
        "failure_class_count": 6,
        "regression_case_count": 1,
    },
    "policy_profile": {
        "policy_id": "release_policy_enterprise_prod",
        "judge_policy_id": "judge_policy_a2_enterprise_prod",
        "blocking_mode": "block_on_critical",
        "waiver_policy": "reviewer_approval_required",
    },
    "max_scenarios": 12,
}
DEFAULT_SELECTION_CONFIG = Path("fixtures/a2/config/a2_project_scenario_selection.json")
DEFAULT_GOLDEN_CASES = Path("fixtures/golden/a2_g2_golden_cases.json")
DEFAULT_RUN_FIXTURES = Path("fixtures/a2/runs")
DEFAULT_REGRESSION_REPLAY_REPORT = Path("fixtures/a2/results/a2_regression_replay_report.json")
DEFAULT_INCIDENT_REGRESSION_REPORT = Path("fixtures/a2/results/a2_incident_regression_candidates.json")
DEFAULT_MINIMUMS = {
    "golden_case_count": 4,
    "failure_class_count": 6,
    "regression_case_count": 1,
}

ENVIRONMENT_POLICIES: dict[str, dict[str, list[str]]] = {
    "dev": {
        "capability_axes": ["tool_choice_and_policy", "output_contract"],
        "risk_tiers": ["low", "medium"],
    },
    "staging": {
        "capability_axes": ["tool_choice_and_policy", "trace_contract", "grounding_and_reference"],
        "risk_tiers": ["medium", "high"],
    },
    "prod": {
        "capability_axes": ["trace_contract", "grounding_and_reference", "safety_boundary"],
        "risk_tiers": ["high", "critical"],
    },
}
RISK_TIER_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
HIGH_RISK_FAILURES = {
    "forbidden_tool_call",
    "hallucinated_tool_result",
    "missing_required_tool",
    "poor_failure_recovery",
    "wrong_arguments",
    "wrong_tool",
    "wrong_tool_order",
}
CRITICAL_TAGS = {
    "billing-risk",
    "credential-theft",
    "irreversible-action",
    "personal-data",
    "privacy",
    "privacy-compliance",
    "secret",
    "secrets-management",
    "unsafe",
}


def build_scenario_selection_report(
    profile: dict[str, Any] | None = None,
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    golden_path: str | Path = DEFAULT_GOLDEN_CASES,
    run_dir: str | Path = DEFAULT_RUN_FIXTURES,
    regression_report_path: str | Path = DEFAULT_REGRESSION_REPLAY_REPORT,
    incident_regression_path: str | Path = DEFAULT_INCIDENT_REGRESSION_REPORT,
) -> dict[str, Any]:
    """Select a deterministic scenario pack for a project/environment profile."""
    selection_profile = {**DEFAULT_PROJECT_PROFILE, **(profile or {})}
    pack = load_scenario_pack(pack_path)
    scenarios = list(pack.get("scenarios", []))
    scenario_evidence = _scenario_evidence_refs(
        golden_path=golden_path,
        run_dir=run_dir,
        regression_report_path=regression_report_path,
        incident_regression_path=incident_regression_path,
    )
    metadata = _scenario_metadata(scenarios, scenario_evidence)
    criteria = _effective_criteria(selection_profile)
    selected_ids = _select_scenario_ids(scenarios, metadata, criteria)
    selected = [
        _selected_scenario(scenario, metadata[str(scenario.get("id", ""))], criteria)
        for scenario in scenarios
        if str(scenario.get("id", "")) in selected_ids
    ]
    coverage_summary = _coverage_summary(selected, criteria, len(scenarios))
    minimums_summary = _minimums_summary(selected, criteria, coverage_summary)
    policy_profile = _policy_profile(selection_profile, criteria, minimums_summary)
    tenant = _tenant_context(selection_profile)
    project = selection_profile.get("project", {})
    environment = str(selection_profile.get("environment", ""))

    return {
        "schema_version": "a2.scenario_selection.v1",
        "report_id": "a2_scenario_selection_report",
        "selection_id": str(selection_profile.get("selection_id", "a2_scenario_selection")),
        "source_pack_id": str(pack.get("pack_id", "")),
        "source_scenario_count": len(scenarios),
        "tenant": tenant,
        "project": project,
        "environment": environment,
        "selection_context": {
            "tenant": tenant,
            "project": project,
            "environment": environment,
        },
        "policy_profile": policy_profile,
        "selection_profile": selection_profile,
        "effective_criteria": criteria,
        "selected_scenario_count": len(selected),
        "selected_scenarios": selected,
        "coverage_summary": coverage_summary,
        "minimums_summary": minimums_summary,
        "a3_consumption_summary": _a3_consumption_summary(
            selected=selected,
            coverage_summary=coverage_summary,
            minimums_summary=minimums_summary,
            tenant=tenant,
            project=project,
            environment=environment,
            policy_profile=policy_profile,
        ),
        "metadata": {
            "deterministic": True,
            "purpose": "Select a per-project A2 scenario pack for SaaS release evaluation without live API calls.",
            "does_not_read_private_evidence": True,
            "public_fixture_sources": [
                str(golden_path),
                str(run_dir),
                str(regression_report_path),
                str(incident_regression_path),
            ],
        },
    }


def load_selection_config(path: str | Path = DEFAULT_SELECTION_CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_project_scenario_selection(
    *,
    project_id: str,
    environment: str = "prod",
    selection_config: dict[str, Any] | None = None,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
) -> dict[str, Any]:
    """Return a compact per-project selection contract for service callers."""
    config = selection_config or load_selection_config()
    profile = _profile_for_project(config, project_id=project_id, environment=environment)
    report = build_scenario_selection_report(profile, pack_path=pack_path)
    selected_ids = [item["scenario_id"] for item in report["selected_scenarios"]]
    coverage_summary = report["coverage_summary"]
    return {
        "schema_version": "a2.project_scenario_selection.v1",
        "tenant": report["tenant"],
        "project_id": project_id,
        "environment": environment,
        "profile_id": str(profile.get("profile_id", profile.get("selection_id", ""))),
        "risk_tier": str(profile.get("risk_tier", ",".join(report["effective_criteria"].get("risk_tiers", [])))),
        "policy_profile": report["policy_profile"],
        "scenario_pack_id": report["source_pack_id"],
        "selected_count": len(selected_ids),
        "selected_scenario_ids": selected_ids,
        "selection_reasons": [
            {"scenario_id": item["scenario_id"], "reasons": [item["selection_reason"]]}
            for item in report["selected_scenarios"]
        ],
        "coverage_summary": {
            **coverage_summary,
            "enterprise_saas_count": sum(
                1 for item in report["selected_scenarios"] if "enterprise-saas" in item["matched_tenant_saas_tags"]
            ),
            "media_or_multimodal_count": coverage_summary.get("media_scenario_count", 0),
            "required_axes_met": {
                axis: axis not in set(coverage_summary.get("missing_capability_axes", []))
                for axis in coverage_summary.get("requested_capability_axes", [])
            },
        },
        "minimums_summary": report["minimums_summary"],
        "a3_consumption_summary": report["a3_consumption_summary"],
        "source_report": report,
    }


def scenario_risk_tier(scenario: dict[str, Any]) -> str:
    """Derive a coarse risk tier from existing scenario metadata."""
    tags = _tags(scenario)
    primary_failure = str(scenario.get("primaryFailureClass", ""))
    difficulty = str(scenario.get("difficulty", ""))
    policy = scenario.get("toolPolicy", {})
    has_critical_forbidden = any(
        isinstance(item, dict) and item.get("severity") == "critical"
        for item in policy.get("forbidden", [])
    )
    if primary_failure == "unsafe_or_policy_violation" or has_critical_forbidden or tags & CRITICAL_TAGS:
        return "critical"
    if difficulty in {"D3", "D4"} or primary_failure in HIGH_RISK_FAILURES or _is_media_or_multimodal(scenario):
        return "high"
    if difficulty == "D2" or scenario.get("fixtureRefs") or policy.get("required") or policy.get("optional"):
        return "medium"
    return "low"


def _profile_for_project(config: dict[str, Any], *, project_id: str, environment: str) -> dict[str, Any]:
    if config.get("schema_version") == "a2.scenario_selection_profile.v1":
        return dict(config)

    profiles = config.get("project_profiles", [])
    if isinstance(profiles, list):
        matches: list[tuple[int, dict[str, Any]]] = []
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            project_score = _profile_match_score(profile.get("project_ids", []), project_id)
            env_score = _profile_match_score(profile.get("environments", []), environment)
            if project_score == 0 or env_score == 0:
                continue
            matches.append((project_score + env_score, profile))
        if matches:
            matches.sort(key=lambda item: (-item[0], str(item[1].get("profile_id", ""))))
            return _to_selection_profile(matches[0][1], project_id=project_id, environment=environment)

        default_profile_id = str(config.get("default_profile_id", ""))
        for profile in profiles:
            if isinstance(profile, dict) and profile.get("profile_id") == default_profile_id:
                return _to_selection_profile(profile, project_id=project_id, environment=environment)

    return {
        **DEFAULT_PROJECT_PROFILE,
        "project": {"project_id": project_id, "name": project_id},
        "environment": environment,
    }


def _to_selection_profile(profile: dict[str, Any], *, project_id: str, environment: str) -> dict[str, Any]:
    required_axes = list(profile.get("required_axis_minimums", {}).keys())
    preferred_axes = _strings(profile.get("preferred_capability_axes"))
    required_tags = _strings(profile.get("required_tags"))
    tags = required_tags + _strings(profile.get("preferred_tags"))
    risk_tier = str(profile.get("risk_tier", ""))
    required_axis_minimums = _int_mapping(profile.get("required_axis_minimums"))
    media_minimum = required_axis_minimums.get("media_and_multimodal", 0)
    regression_minimum = 1 if environment == "prod" or risk_tier.startswith("enterprise") else 0
    return {
        "schema_version": "a2.scenario_selection_profile.v1",
        "selection_id": str(profile.get("profile_id", "a2_project_selection")),
        "profile_id": str(profile.get("profile_id", "")),
        "tenant": _tenant_context({**profile, "project": {"project_id": project_id}}),
        "project": {"project_id": project_id, "name": project_id},
        "environment": environment,
        "capability_axes": _sorted_unique(required_axes + preferred_axes),
        "risk_tiers": ["high", "critical"] if risk_tier.startswith("enterprise") else ["medium", "high"],
        "media_requirement": "required" if "media_and_multimodal" in required_axes else "preferred",
        "required_axis_minimums": required_axis_minimums,
        "required_tags": required_tags,
        "required_tag_minimum": int(profile.get("required_tag_minimum", 0)),
        "tenant_saas_tags": _sorted_unique(tags),
        "minimums": {
            "golden_case_count": int(profile.get("golden_case_minimum", 4)),
            "failure_class_count": int(profile.get("failure_class_minimum", 6 if risk_tier.startswith("enterprise") else 4)),
            "regression_case_count": int(profile.get("regression_case_minimum", regression_minimum)),
            "media_scenario_count": int(profile.get("media_scenario_minimum", media_minimum)),
        },
        "max_scenarios": int(profile.get("max_scenarios", 12)),
        "risk_tier": risk_tier,
        "policy_profile": _configured_policy_profile(profile, environment=environment, risk_tier=risk_tier),
    }


def _profile_match_score(configured: Any, requested: str) -> int:
    if not configured:
        return 10
    if not isinstance(configured, list):
        configured = [configured]
    configured_values = {str(item) for item in configured}
    if requested in configured_values:
        return 100
    if "*" in configured_values:
        return 10
    return 0


def _effective_criteria(profile: dict[str, Any]) -> dict[str, Any]:
    environment = str(profile.get("environment", "")).lower() or "dev"
    env_policy = ENVIRONMENT_POLICIES.get(environment, {})
    capability_axes = _sorted_unique(_strings(profile.get("capability_axes")) + env_policy.get("capability_axes", []))
    risk_tiers = _sort_risk_tiers(_strings(profile.get("risk_tiers")) + env_policy.get("risk_tiers", []))
    minimums = {**DEFAULT_MINIMUMS, **_int_mapping(profile.get("minimums"))}
    required_axis_minimums = _int_mapping(profile.get("required_axis_minimums"))
    media_requirement = str(profile.get("media_requirement", "none")).lower()
    if media_requirement == "required":
        required_axis_minimums.setdefault("media_and_multimodal", 1)
        minimums.setdefault("media_scenario_count", 1)
    return {
        "environment": environment,
        "environment_policy_applied": bool(env_policy),
        "capability_axes": capability_axes,
        "risk_tiers": risk_tiers,
        "media_requirement": media_requirement,
        "required_axis_minimums": required_axis_minimums,
        "required_tags": _sorted_unique(_strings(profile.get("required_tags"))),
        "required_tag_minimum": max(0, int(profile.get("required_tag_minimum", 0))),
        "tenant_saas_tags": _sorted_unique(_strings(profile.get("tenant_saas_tags"))),
        "minimums": minimums,
        "max_scenarios": max(1, int(profile.get("max_scenarios", 12))),
    }


def _scenario_metadata(
    scenarios: list[dict[str, Any]],
    scenario_evidence: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    dimensions = _scenario_dimension_refs(scenarios)
    axes = _capability_axis_refs(scenarios, dimensions)
    axes_by_scenario: dict[str, list[str]] = {}
    for axis, scenario_ids in axes.items():
        for scenario_id in scenario_ids:
            axes_by_scenario.setdefault(scenario_id, []).append(axis)

    metadata = {}
    for scenario in scenarios:
        scenario_id = str(scenario.get("id", ""))
        evidence = scenario_evidence.get(scenario_id, _empty_evidence_refs())
        metadata[scenario_id] = {
            "scenario_id": scenario_id,
            "capability_axes": sorted(axes_by_scenario.get(scenario_id, [])),
            "risk_tier": scenario_risk_tier(scenario),
            "is_media": _is_media_or_multimodal(scenario),
            "tags": sorted(_tags(scenario)),
            "action_environments": sorted(
                {str(action.get("environment", "local")) for action in scenario.get("actions", [])}
            ),
            "primary_failure_class": str(scenario.get("primaryFailureClass", "")),
            "golden_case_refs": evidence["golden_case_refs"],
            "run_fixture_refs": evidence["run_fixture_refs"],
            "regression_refs": evidence["regression_refs"],
            "golden_case_count": len(evidence["golden_case_refs"]),
            "run_fixture_count": len(evidence["run_fixture_refs"]),
            "regression_case_count": len(evidence["regression_refs"]),
        }
    return metadata


def _select_scenario_ids(
    scenarios: list[dict[str, Any]],
    metadata: dict[str, dict[str, Any]],
    criteria: dict[str, Any],
) -> set[str]:
    selected: list[str] = []
    max_scenarios = int(criteria["max_scenarios"])
    ranked = sorted(
        scenarios,
        key=lambda scenario: (-_score_scenario(metadata[str(scenario.get("id", ""))], criteria), str(scenario.get("id", ""))),
    )

    def add_best(predicate: Any) -> None:
        for scenario in ranked:
            scenario_id = str(scenario.get("id", ""))
            if scenario_id not in selected and predicate(metadata[scenario_id]):
                selected.append(scenario_id)
                return

    def add_best_until(predicate: Any, current_value: Any, target: int) -> None:
        while current_value() < target:
            before = len(selected)
            add_best(predicate)
            if len(selected) == before:
                return

    def selected_items() -> list[dict[str, Any]]:
        return [metadata[scenario_id] for scenario_id in selected]

    for axis in criteria["capability_axes"]:
        add_best(lambda item, axis=axis: axis in item["capability_axes"])
    if criteria["media_requirement"] == "required":
        add_best(lambda item: item["is_media"])

    for axis, minimum in criteria["required_axis_minimums"].items():
        add_best_until(
            lambda item, axis=axis: axis in item["capability_axes"],
            lambda axis=axis: sum(1 for item in selected_items() if axis in item["capability_axes"]),
            int(minimum),
        )
    for tag in criteria["required_tags"]:
        add_best_until(
            lambda item, tag=tag: tag in item["tags"],
            lambda tag=tag: sum(1 for item in selected_items() if tag in item["tags"]),
            int(criteria["required_tag_minimum"]),
        )

    minimums = criteria["minimums"]
    add_best_until(
        lambda item: item["regression_case_count"] > 0,
        lambda: sum(int(item["regression_case_count"]) for item in selected_items()),
        int(minimums.get("regression_case_count", 0)),
    )
    add_best_until(
        lambda item: item["golden_case_count"] > 0,
        lambda: sum(int(item["golden_case_count"]) for item in selected_items()),
        int(minimums.get("golden_case_count", 0)),
    )
    add_best_until(
        lambda item: item["primary_failure_class"] not in {
            existing["primary_failure_class"] for existing in selected_items()
        },
        lambda: len({item["primary_failure_class"] for item in selected_items() if item["primary_failure_class"]}),
        int(minimums.get("failure_class_count", 0)),
    )

    for tag in criteria["tenant_saas_tags"]:
        add_best(lambda item, tag=tag: tag in item["tags"])
    for risk_tier in criteria["risk_tiers"]:
        add_best(lambda item, risk_tier=risk_tier: item["risk_tier"] == risk_tier)

    for scenario in ranked:
        if len(selected) >= max_scenarios:
            break
        scenario_id = str(scenario.get("id", ""))
        if scenario_id not in selected and _score_scenario(metadata[scenario_id], criteria) > 0:
            selected.append(scenario_id)
    return set(selected[:max_scenarios])


def _score_scenario(item: dict[str, Any], criteria: dict[str, Any]) -> int:
    matched_axes = set(item["capability_axes"]) & set(criteria["capability_axes"])
    matched_tags = set(item["tags"]) & set(criteria["tenant_saas_tags"])
    score = len(matched_axes) * 10 + len(matched_tags) * 6
    if item["risk_tier"] in criteria["risk_tiers"]:
        score += 5
    if criteria["media_requirement"] in {"preferred", "required"} and item["is_media"]:
        score += 5
    if criteria["environment"] == "prod" and item["risk_tier"] in {"high", "critical"}:
        score += 3
    score += min(int(item.get("golden_case_count", 0)), 2) * 2
    score += min(int(item.get("regression_case_count", 0)), 2) * 4
    return score


def _selected_scenario(
    scenario: dict[str, Any],
    item: dict[str, Any],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    matched_axes = sorted(set(item["capability_axes"]) & set(criteria["capability_axes"]))
    matched_tags = sorted(set(item["tags"]) & set(criteria["tenant_saas_tags"]))
    return {
        "scenario_id": str(scenario.get("id", "")),
        "title": str(scenario.get("title", "")),
        "family": str(scenario.get("family", "")),
        "difficulty": str(scenario.get("difficulty", "")),
        "risk_tier": item["risk_tier"],
        "capability_axes": item["capability_axes"],
        "matched_capability_axes": matched_axes,
        "matched_tenant_saas_tags": matched_tags,
        "is_media_or_multimodal": bool(item["is_media"]),
        "media_required_match": bool(item["is_media"] and criteria["media_requirement"] == "required"),
        "action_environments": item["action_environments"],
        "primary_failure_class": str(scenario.get("primaryFailureClass", "")),
        "golden_case_refs": item["golden_case_refs"],
        "run_fixture_refs": item["run_fixture_refs"],
        "regression_refs": item["regression_refs"],
        "selection_score": _score_scenario(item, criteria),
        "coverage_roles": _coverage_roles(item, matched_axes, matched_tags, criteria),
        "selection_reason": _selection_reason(item, matched_axes, matched_tags, criteria),
    }


def _selection_reason(
    item: dict[str, Any],
    matched_axes: list[str],
    matched_tags: list[str],
    criteria: dict[str, Any],
) -> str:
    parts = []
    if matched_axes:
        parts.append("matches capability axes " + ", ".join(matched_axes))
    if item["risk_tier"] in criteria["risk_tiers"]:
        parts.append(f"covers {item['risk_tier']} risk")
    if matched_tags:
        parts.append("matches SaaS tags " + ", ".join(matched_tags))
    if item["is_media"] and criteria["media_requirement"] == "required":
        parts.append("satisfies required media coverage")
    if item.get("golden_case_count", 0):
        parts.append("has golden calibration evidence")
    if item.get("regression_case_count", 0):
        parts.append("has regression replay or candidate coverage")
    if criteria["environment_policy_applied"]:
        parts.append(f"uses {criteria['environment']} environment policy")
    return "; ".join(parts) if parts else "selected as deterministic filler for the requested pack"


def _coverage_summary(
    selected: list[dict[str, Any]],
    criteria: dict[str, Any],
    source_count: int,
) -> dict[str, Any]:
    selected_axes = sorted({axis for scenario in selected for axis in scenario["capability_axes"]})
    requested_axes = set(criteria["capability_axes"])
    requested_tags = set(criteria["tenant_saas_tags"])
    risk_counts = Counter(scenario["risk_tier"] for scenario in selected)
    tag_counts = Counter(tag for scenario in selected for tag in scenario["matched_tenant_saas_tags"])
    required_tag_counts = {
        tag: tag_counts.get(tag, 0)
        for tag in criteria["required_tags"]
    }
    media_scenarios = [scenario for scenario in selected if scenario["is_media_or_multimodal"]]
    media_count = len(media_scenarios)
    action_env_counts = Counter(env for scenario in selected for env in scenario["action_environments"])
    capability_axis_counts = Counter(axis for scenario in selected for axis in scenario["capability_axes"])
    requested_capability_axis_counts = {
        axis: capability_axis_counts.get(axis, 0)
        for axis in criteria["capability_axes"]
    }
    required_axis_minimum_status = {
        axis: {
            "required": int(minimum),
            "selected": capability_axis_counts.get(axis, 0),
            "met": capability_axis_counts.get(axis, 0) >= int(minimum),
        }
        for axis, minimum in criteria["required_axis_minimums"].items()
    }
    missing_axis_minimums = {
        axis: status
        for axis, status in required_axis_minimum_status.items()
        if not status["met"]
    }
    required_tag_minimum_status = {
        tag: {
            "required": int(criteria["required_tag_minimum"]),
            "selected": required_tag_counts.get(tag, 0),
            "met": required_tag_counts.get(tag, 0) >= int(criteria["required_tag_minimum"]),
        }
        for tag in criteria["required_tags"]
    }
    missing_tag_minimums = {
        tag: status
        for tag, status in required_tag_minimum_status.items()
        if not status["met"]
    }
    missing_axes = sorted(requested_axes - set(selected_axes))
    missing_tags = sorted(requested_tags - set(tag_counts))
    missing_risk_tiers = [tier for tier in criteria["risk_tiers"] if risk_counts.get(tier, 0) == 0]
    media_met = criteria["media_requirement"] != "required" or media_count > 0
    return {
        "source_scenario_count": source_count,
        "selected_scenario_count": len(selected),
        "coverage_ready": (
            not missing_axes
            and not missing_tags
            and not missing_risk_tiers
            and not missing_axis_minimums
            and not missing_tag_minimums
            and media_met
        ),
        "requested_capability_axes": criteria["capability_axes"],
        "covered_capability_axes": selected_axes,
        "capability_axis_counts": dict(sorted(capability_axis_counts.items())),
        "requested_capability_axis_counts": requested_capability_axis_counts,
        "required_capability_axis_minimums": criteria["required_axis_minimums"],
        "required_capability_axis_minimum_status": required_axis_minimum_status,
        "missing_capability_axis_minimums": missing_axis_minimums,
        "missing_capability_axes": missing_axes,
        "requested_risk_tiers": criteria["risk_tiers"],
        "risk_tier_counts": dict(sorted(risk_counts.items())),
        "missing_risk_tiers": missing_risk_tiers,
        "media_requirement": criteria["media_requirement"],
        "media_scenario_count": media_count,
        "media_scenario_ids": [scenario["scenario_id"] for scenario in media_scenarios],
        "media_requirement_met": media_met,
        "media_coverage": {
            "requirement": criteria["media_requirement"],
            "selected_count": media_count,
            "selected_scenario_ids": [scenario["scenario_id"] for scenario in media_scenarios],
            "met": media_met,
        },
        "required_tenant_saas_tags": criteria["required_tags"],
        "required_tag_minimum": criteria["required_tag_minimum"],
        "required_tag_counts": required_tag_counts,
        "required_tag_minimum_status": required_tag_minimum_status,
        "missing_required_tag_minimums": missing_tag_minimums,
        "requested_tenant_saas_tags": criteria["tenant_saas_tags"],
        "tenant_saas_tag_counts": dict(sorted(tag_counts.items())),
        "missing_tenant_saas_tags": missing_tags,
        "family_counts": dict(sorted(Counter(scenario["family"] for scenario in selected).items())),
        "action_environment_counts": dict(sorted(action_env_counts.items())),
    }


def _coverage_roles(
    item: dict[str, Any],
    matched_axes: list[str],
    matched_tags: list[str],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    return {
        "capability_axes": matched_axes,
        "tenant_saas_tags": matched_tags,
        "media_required": bool(item["is_media"] and criteria["media_requirement"] == "required"),
        "golden_calibration": bool(item.get("golden_case_count", 0)),
        "executable_run_fixture": bool(item.get("run_fixture_count", 0)),
        "regression_replay_or_candidate": bool(item.get("regression_case_count", 0)),
    }


def _minimums_summary(
    selected: list[dict[str, Any]],
    criteria: dict[str, Any],
    coverage_summary: dict[str, Any],
) -> dict[str, Any]:
    minimums = dict(criteria["minimums"])
    observed = {
        "golden_case_count": sum(len(scenario["golden_case_refs"]) for scenario in selected),
        "run_fixture_count": sum(len(scenario["run_fixture_refs"]) for scenario in selected),
        "regression_case_count": sum(len(scenario["regression_refs"]) for scenario in selected),
        "failure_class_count": len(
            {scenario["primary_failure_class"] for scenario in selected if scenario["primary_failure_class"]}
        ),
        "media_scenario_count": coverage_summary["media_scenario_count"],
    }
    checks = {
        key: {
            "required": int(required),
            "selected": int(observed.get(key, 0)),
            "met": int(observed.get(key, 0)) >= int(required),
        }
        for key, required in minimums.items()
    }
    checks["required_capability_axis_minimums"] = {
        "required": coverage_summary["required_capability_axis_minimums"],
        "selected": coverage_summary["requested_capability_axis_counts"],
        "met": not coverage_summary["missing_capability_axis_minimums"],
    }
    checks["required_tag_minimums"] = {
        "required": {
            tag: coverage_summary["required_tag_minimum"]
            for tag in coverage_summary["required_tenant_saas_tags"]
        },
        "selected": coverage_summary["required_tag_counts"],
        "met": not coverage_summary["missing_required_tag_minimums"],
    }
    minimums_ready = all(
        check["met"] if isinstance(check, dict) and "met" in check else True
        for check in checks.values()
    )
    return {
        "requested_minimums": minimums,
        "observed": observed,
        "checks": checks,
        "minimums_ready": minimums_ready,
        "gaps": _minimum_gaps(checks),
        "failure_classes": sorted(
            {scenario["primary_failure_class"] for scenario in selected if scenario["primary_failure_class"]}
        ),
        "golden_case_scenario_ids": sorted(
            {scenario["scenario_id"] for scenario in selected if scenario["golden_case_refs"]}
        ),
        "run_fixture_scenario_ids": sorted(
            {scenario["scenario_id"] for scenario in selected if scenario["run_fixture_refs"]}
        ),
        "regression_scenario_ids": sorted(
            {scenario["scenario_id"] for scenario in selected if scenario["regression_refs"]}
        ),
    }


def _minimum_gaps(checks: dict[str, Any]) -> list[str]:
    gaps = []
    for key, check in checks.items():
        if not isinstance(check, dict) or check.get("met", True):
            continue
        if key in {"required_capability_axis_minimums", "required_tag_minimums"}:
            gaps.append(f"{key} are not fully met.")
            continue
        gaps.append(f"{key} selected {check.get('selected', 0)} below required {check.get('required', 0)}.")
    return gaps


def _policy_profile(
    profile: dict[str, Any],
    criteria: dict[str, Any],
    minimums_summary: dict[str, Any],
) -> dict[str, Any]:
    configured = profile.get("policy_profile", {})
    if not isinstance(configured, dict):
        configured = {}
    environment = criteria["environment"]
    policy_id = str(configured.get("policy_id") or f"release_policy_{environment}")
    judge_policy_id = str(configured.get("judge_policy_id") or f"judge_policy_a2_{environment}")
    return {
        "policy_id": policy_id,
        "judge_policy_id": judge_policy_id,
        "profile_id": str(profile.get("profile_id", profile.get("selection_id", policy_id))),
        "environment": environment,
        "risk_tiers": criteria["risk_tiers"],
        "blocking_mode": str(configured.get("blocking_mode", "block_on_critical" if environment == "prod" else "warn")),
        "waiver_policy": str(
            configured.get(
                "waiver_policy",
                "reviewer_approval_required" if environment == "prod" else "team_owner_approval",
            )
        ),
        "release_gate_decision": "eligible" if minimums_summary["minimums_ready"] else "needs_attention",
        "minimums_ready": minimums_summary["minimums_ready"],
        "per_project_policy": True,
        "per_environment_policy": True,
        "blocking_failure_classes": sorted(HIGH_RISK_FAILURES | {"unsafe_or_policy_violation"}),
    }


def _a3_consumption_summary(
    *,
    selected: list[dict[str, Any]],
    coverage_summary: dict[str, Any],
    minimums_summary: dict[str, Any],
    tenant: dict[str, Any],
    project: dict[str, Any],
    environment: str,
    policy_profile: dict[str, Any],
) -> dict[str, Any]:
    selected_ids = [scenario["scenario_id"] for scenario in selected]
    regression_refs = [
        ref
        for scenario in selected
        for ref in scenario["regression_refs"]
    ]
    run_fixture_refs = [
        ref
        for scenario in selected
        for ref in scenario["run_fixture_refs"]
    ]
    return {
        "schema_version": "a2.a3_scenario_selection_summary.v1",
        "tenant_project_environment": {
            "tenant": tenant,
            "project": project,
            "environment": environment,
        },
        "selected_scenario_ids": selected_ids,
        "scenario_count": len(selected_ids),
        "policy_profile": {
            "policy_id": policy_profile["policy_id"],
            "judge_policy_id": policy_profile["judge_policy_id"],
            "blocking_mode": policy_profile["blocking_mode"],
            "release_gate_decision": policy_profile["release_gate_decision"],
        },
        "coverage": {
            "coverage_ready": coverage_summary["coverage_ready"],
            "requested_capability_axis_counts": coverage_summary["requested_capability_axis_counts"],
            "media_coverage": coverage_summary["media_coverage"],
            "missing_capability_axes": coverage_summary["missing_capability_axes"],
            "missing_tenant_saas_tags": coverage_summary["missing_tenant_saas_tags"],
        },
        "minimums": {
            "minimums_ready": minimums_summary["minimums_ready"],
            "observed": minimums_summary["observed"],
            "gaps": minimums_summary["gaps"],
        },
        "failure_classes": minimums_summary["failure_classes"],
        "regression_scenario_ids": minimums_summary["regression_scenario_ids"],
        "dashboard_cards": [
            {
                "card_id": "scenario_coverage",
                "status": "ready" if coverage_summary["coverage_ready"] else "needs_attention",
                "value": len(selected_ids),
            },
            {
                "card_id": "policy_profile",
                "status": policy_profile["release_gate_decision"],
                "value": policy_profile["policy_id"],
            },
            {
                "card_id": "regression_minimum",
                "status": "ready" if not minimums_summary["gaps"] else "needs_attention",
                "value": minimums_summary["observed"]["regression_case_count"],
            },
        ],
        "release_gate_inputs": {
            "scenario_ids": selected_ids,
            "policy_id": policy_profile["policy_id"],
            "judge_policy_id": policy_profile["judge_policy_id"],
            "environment": environment,
        },
        "evidence_refs": {
            "run_fixtures": _sorted_unique([str(ref.get("fixture_ref", "")) for ref in run_fixture_refs]),
            "regressions": _sorted_unique([str(ref.get("fixture_ref", ref.get("regression_id", ""))) for ref in regression_refs]),
        },
    }


def _scenario_evidence_refs(
    *,
    golden_path: str | Path,
    run_dir: str | Path,
    regression_report_path: str | Path,
    incident_regression_path: str | Path,
) -> dict[str, dict[str, Any]]:
    refs: dict[str, dict[str, Any]] = {}

    for case in _load_golden_cases(golden_path):
        scenario_id = str(case.get("scenario_id", ""))
        refs.setdefault(scenario_id, _empty_evidence_refs())["golden_case_refs"].append(
            {
                "case_id": str(case.get("case_id", "")),
                "expected_passed": bool(case.get("expected_passed", False)),
                "expected_primary_failure_class": str(case.get("expected_primary_failure_class", "")),
            }
        )

    for fixture_path, fixture in _load_run_fixtures(run_dir):
        scenario_id = str(fixture.get("scenario_id", ""))
        refs.setdefault(scenario_id, _empty_evidence_refs())["run_fixture_refs"].append(
            {
                "case_id": str(fixture.get("case_id", "")),
                "fixture_ref": fixture_path.as_posix(),
                "expected_passed": bool(fixture.get("expected", {}).get("passed", False)),
                "expected_primary_failure_class": str(fixture.get("expected", {}).get("primary_failure_class", "")),
            }
        )

    for ref in _load_regression_refs(regression_report_path, source="regression_replay"):
        scenario_id = str(ref.get("scenario_id", ""))
        refs.setdefault(scenario_id, _empty_evidence_refs())["regression_refs"].append(ref)

    for ref in _load_incident_regression_refs(incident_regression_path):
        scenario_id = str(ref.get("scenario_id", ""))
        refs.setdefault(scenario_id, _empty_evidence_refs())["regression_refs"].append(ref)

    for evidence in refs.values():
        for key in ("golden_case_refs", "run_fixture_refs", "regression_refs"):
            evidence[key] = sorted(evidence[key], key=lambda item: json.dumps(item, sort_keys=True))
    return refs


def _empty_evidence_refs() -> dict[str, list[dict[str, Any]]]:
    return {
        "golden_case_refs": [],
        "run_fixture_refs": [],
        "regression_refs": [],
    }


def _load_golden_cases(path: str | Path) -> list[dict[str, Any]]:
    payload = _load_json_object(path)
    cases = payload.get("goldenCases", [])
    return cases if isinstance(cases, list) else []


def _load_run_fixtures(path: str | Path) -> list[tuple[Path, dict[str, Any]]]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    fixtures = []
    for fixture_path in sorted(resolved.glob("*.json")):
        fixtures.append((fixture_path, json.loads(fixture_path.read_text(encoding="utf-8"))))
    return fixtures


def _load_regression_refs(path: str | Path, *, source: str) -> list[dict[str, Any]]:
    payload = _load_json_object(path)
    refs = []
    for case in payload.get("cases", []) if isinstance(payload.get("cases"), list) else []:
        refs.append(
            {
                "source": source,
                "regression_id": str(case.get("regression_id", "")),
                "case_id": str(case.get("case_id", "")),
                "scenario_id": str(case.get("scenario_id", "")),
                "fixture_ref": str(case.get("fixture_ref", "")),
                "status": str(case.get("replay_status", case.get("status", ""))),
            }
        )
    return refs


def _load_incident_regression_refs(path: str | Path) -> list[dict[str, Any]]:
    payload = _load_json_object(path)
    refs = []
    for case in payload.get("candidates", []) if isinstance(payload.get("candidates"), list) else []:
        refs.append(
            {
                "source": "incident_regression_candidate",
                "regression_id": str(case.get("regression_id", "")),
                "case_id": str(case.get("case_id", "")),
                "scenario_id": str(case.get("scenario_id", "")),
                "fixture_ref": str(case.get("fixture_ref", "")),
                "status": str(case.get("status", "")),
                "ready_for_case_book_review": bool(case.get("ready_for_case_book_review", False)),
            }
        )
    return refs


def _load_json_object(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    if not resolved.exists():
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _tenant_context(profile: dict[str, Any]) -> dict[str, str]:
    tenant = profile.get("tenant", {})
    if not isinstance(tenant, dict):
        tenant = {}
    project = profile.get("project", {})
    project_id = ""
    if isinstance(project, dict):
        project_id = str(project.get("project_id", ""))
    if not project_id:
        project_ids = profile.get("project_ids", [])
        if isinstance(project_ids, list) and project_ids:
            project_id = str(project_ids[0])
    slug = project_id or str(profile.get("profile_id", "default"))
    return {
        "organization_id": str(tenant.get("organization_id") or profile.get("organization_id") or "org_default"),
        "workspace_id": str(tenant.get("workspace_id") or profile.get("workspace_id") or "workspace_default"),
        "tenant_id": str(tenant.get("tenant_id") or profile.get("tenant_id") or f"tenant_{slug}"),
    }


def _configured_policy_profile(profile: dict[str, Any], *, environment: str, risk_tier: str) -> dict[str, str]:
    policy = profile.get("policy_profile", {})
    if not isinstance(policy, dict):
        policy = {}
    suffix = risk_tier or environment
    return {
        "policy_id": str(policy.get("policy_id", f"release_policy_{suffix}")),
        "judge_policy_id": str(policy.get("judge_policy_id", f"judge_policy_a2_{suffix}")),
        "blocking_mode": str(policy.get("blocking_mode", "block_on_critical" if environment == "prod" else "warn")),
        "waiver_policy": str(
            policy.get("waiver_policy", "reviewer_approval_required" if environment == "prod" else "team_owner_approval")
        ),
    }


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _int_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        if not str(key).strip() or item is None:
            continue
        try:
            result[str(key)] = max(0, int(item))
        except (TypeError, ValueError):
            continue
    return result


def _sorted_unique(values: list[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def _sort_risk_tiers(values: list[str]) -> list[str]:
    return sorted({value for value in values if value in RISK_TIER_ORDER}, key=lambda value: RISK_TIER_ORDER[value])
