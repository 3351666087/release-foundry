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
    "max_scenarios": 12,
}
DEFAULT_SELECTION_CONFIG = Path("fixtures/a2/config/a2_project_scenario_selection.json")

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
) -> dict[str, Any]:
    """Select a deterministic scenario pack for a project/environment profile."""
    selection_profile = dict(DEFAULT_PROJECT_PROFILE if profile is None else profile)
    pack = load_scenario_pack(pack_path)
    scenarios = list(pack.get("scenarios", []))
    metadata = _scenario_metadata(scenarios)
    criteria = _effective_criteria(selection_profile)
    selected_ids = _select_scenario_ids(scenarios, metadata, criteria)
    selected = [
        _selected_scenario(scenario, metadata[str(scenario.get("id", ""))], criteria)
        for scenario in scenarios
        if str(scenario.get("id", "")) in selected_ids
    ]

    return {
        "schema_version": "a2.scenario_selection.v1",
        "report_id": "a2_scenario_selection_report",
        "selection_id": str(selection_profile.get("selection_id", "a2_scenario_selection")),
        "source_pack_id": str(pack.get("pack_id", "")),
        "source_scenario_count": len(scenarios),
        "project": selection_profile.get("project", {}),
        "environment": str(selection_profile.get("environment", "")),
        "selection_profile": selection_profile,
        "effective_criteria": criteria,
        "selected_scenario_count": len(selected),
        "selected_scenarios": selected,
        "coverage_summary": _coverage_summary(selected, criteria, len(scenarios)),
        "metadata": {
            "deterministic": True,
            "purpose": "Select a per-project A2 scenario pack for SaaS release evaluation without live API calls.",
            "does_not_read_private_evidence": True,
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
        "project_id": project_id,
        "environment": environment,
        "profile_id": str(profile.get("profile_id", profile.get("selection_id", ""))),
        "risk_tier": str(profile.get("risk_tier", ",".join(report["effective_criteria"].get("risk_tiers", [])))),
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
    tags = _strings(profile.get("required_tags")) + _strings(profile.get("preferred_tags"))
    risk_tier = str(profile.get("risk_tier", ""))
    return {
        "schema_version": "a2.scenario_selection_profile.v1",
        "selection_id": str(profile.get("profile_id", "a2_project_selection")),
        "profile_id": str(profile.get("profile_id", "")),
        "project": {"project_id": project_id, "name": project_id},
        "environment": environment,
        "capability_axes": _sorted_unique(required_axes + preferred_axes),
        "risk_tiers": ["high", "critical"] if risk_tier.startswith("enterprise") else ["medium", "high"],
        "media_requirement": "required" if "media_and_multimodal" in required_axes else "preferred",
        "tenant_saas_tags": _sorted_unique(tags),
        "max_scenarios": int(profile.get("max_scenarios", 12)),
        "risk_tier": risk_tier,
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
    return {
        "environment": environment,
        "environment_policy_applied": bool(env_policy),
        "capability_axes": capability_axes,
        "risk_tiers": risk_tiers,
        "media_requirement": str(profile.get("media_requirement", "none")).lower(),
        "tenant_saas_tags": _sorted_unique(_strings(profile.get("tenant_saas_tags"))),
        "max_scenarios": max(1, int(profile.get("max_scenarios", 12))),
    }


def _scenario_metadata(scenarios: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    dimensions = _scenario_dimension_refs(scenarios)
    axes = _capability_axis_refs(scenarios, dimensions)
    axes_by_scenario: dict[str, list[str]] = {}
    for axis, scenario_ids in axes.items():
        for scenario_id in scenario_ids:
            axes_by_scenario.setdefault(scenario_id, []).append(axis)

    return {
        str(scenario.get("id", "")): {
            "scenario_id": str(scenario.get("id", "")),
            "capability_axes": sorted(axes_by_scenario.get(str(scenario.get("id", "")), [])),
            "risk_tier": scenario_risk_tier(scenario),
            "is_media": _is_media_or_multimodal(scenario),
            "tags": sorted(_tags(scenario)),
            "action_environments": sorted(
                {str(action.get("environment", "local")) for action in scenario.get("actions", [])}
            ),
        }
        for scenario in scenarios
    }


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

    for axis in criteria["capability_axes"]:
        add_best(lambda item, axis=axis: axis in item["capability_axes"])
    if criteria["media_requirement"] == "required":
        add_best(lambda item: item["is_media"])
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
        "media_required_match": bool(item["is_media"] and criteria["media_requirement"] == "required"),
        "action_environments": item["action_environments"],
        "primary_failure_class": str(scenario.get("primaryFailureClass", "")),
        "selection_score": _score_scenario(item, criteria),
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
    media_count = sum(1 for scenario in selected if scenario["media_required_match"])
    action_env_counts = Counter(env for scenario in selected for env in scenario["action_environments"])
    missing_axes = sorted(requested_axes - set(selected_axes))
    missing_tags = sorted(requested_tags - set(tag_counts))
    missing_risk_tiers = [tier for tier in criteria["risk_tiers"] if risk_counts.get(tier, 0) == 0]
    media_met = criteria["media_requirement"] != "required" or media_count > 0
    return {
        "source_scenario_count": source_count,
        "selected_scenario_count": len(selected),
        "coverage_ready": not missing_axes and not missing_tags and not missing_risk_tiers and media_met,
        "requested_capability_axes": criteria["capability_axes"],
        "covered_capability_axes": selected_axes,
        "missing_capability_axes": missing_axes,
        "requested_risk_tiers": criteria["risk_tiers"],
        "risk_tier_counts": dict(sorted(risk_counts.items())),
        "missing_risk_tiers": missing_risk_tiers,
        "media_requirement": criteria["media_requirement"],
        "media_scenario_count": media_count,
        "media_requirement_met": media_met,
        "requested_tenant_saas_tags": criteria["tenant_saas_tags"],
        "tenant_saas_tag_counts": dict(sorted(tag_counts.items())),
        "missing_tenant_saas_tags": missing_tags,
        "family_counts": dict(sorted(Counter(scenario["family"] for scenario in selected).items())),
        "action_environment_counts": dict(sorted(action_env_counts.items())),
    }


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _sorted_unique(values: list[str]) -> list[str]:
    return sorted({str(value) for value in values if str(value).strip()})


def _sort_risk_tiers(values: list[str]) -> list[str]:
    return sorted({value for value in values if value in RISK_TIER_ORDER}, key=lambda value: RISK_TIER_ORDER[value])
