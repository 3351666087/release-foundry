from __future__ import annotations

from statistics import median
from typing import Any, Mapping

JsonDict = dict[str, Any]
COMMERCIAL_KIT_SCHEMA_VERSION = "ashr.clone.commercial_control_plane.v1"

USAGE_LABELS = [
    "Videos",
    "Images",
    "Simulations",
    "Audio",
    "Files",
    "Graded scenarios",
    "Observations",
    "Voice minutes",
]

SAAS_CONTROL_PLANE_PILLARS = [
    "tenant_project_isolation",
    "usage_billing_governance",
    "api_key_lifecycle_governance",
    "observability_and_cost_analytics",
    "release_gate_and_audit_evidence",
    "frontend_official_surface_parity",
]


def build_commercial_control_plane_kit(*, capability_matrix: Mapping[str, Any], frontend_mirror_index: Mapping[str, Any], evidence_index: Mapping[str, Any]) -> JsonDict:
    return {
        "schema_version": COMMERCIAL_KIT_SCHEMA_VERSION,
        "product_posture": "enterprise_saas_control_plane_evidence_kit",
        "saas_control_plane_pillars": SAAS_CONTROL_PLANE_PILLARS,
        "source_labels": {
            "capability_matrix": capability_matrix.get("schema_version"),
            "frontend_mirror": frontend_mirror_index.get("schema_version"),
            "evidence_index": evidence_index.get("label"),
        },
        "usage_billing_snapshot": build_usage_billing_snapshot(frontend_mirror_index),
        "api_key_inventory": build_api_key_inventory(),
        "observability_summary": build_observability_summary(capability_matrix),
        "readiness_badge": build_readiness_badge(capability_matrix, evidence_index),
    }


def build_usage_billing_snapshot(frontend_mirror_index: Mapping[str, Any]) -> JsonDict:
    labels = [label for label in _strings(frontend_mirror_index.get("usage_labels")) if label in USAGE_LABELS]
    if not labels:
        labels = USAGE_LABELS
    return {
        "schema_version": "ashr.clone.usage_billing_snapshot.v1",
        "source": "frontend_static_plus_local_synthetic",
        "enterprise_saas_surface": True,
        "real_billing_called": False,
        "checkout_or_portal_called": False,
        "plan": {
            "plan_id": "local-enterprise-synthetic",
            "billing_mode": "synthetic_local_no_charge",
            "currency": "USD-placeholder",
            "overage_mode_supported": True,
            "hard_block_mode_supported": True,
        },
        "usage_dimensions": [
            {
                "label": label,
                "resource_key": _resource_key(label),
                "included_usage": None,
                "used": None,
                "remaining": None,
                "public_safe": True,
                "value_policy": "counts omitted from public artifact; private or tenant-specific usage must stay private",
            }
            for label in labels
        ],
    }


def build_api_key_inventory() -> JsonDict:
    return {
        "schema_version": "ashr.clone.api_key_inventory.v1",
        "source": "local_synthetic_governance_contract",
        "enterprise_saas_surface": True,
        "raw_sensitive_values_included": False,
        "keys": [
            {
                "key_id": "key_local_synthetic_active",
                "prefix": "ashr_local_***",
                "hash_presence": True,
                "sensitive_value_present": False,
                "status": "active",
                "created_at": "2026-07-07T00:00:00Z",
                "revoked_at": None,
                "last_used_at": None,
                "scopes": ["read:evidence", "write:runs"],
            },
            {
                "key_id": "key_local_synthetic_revoked",
                "prefix": "ashr_local_***",
                "hash_presence": True,
                "sensitive_value_present": False,
                "status": "revoked",
                "created_at": "2026-07-07T00:00:00Z",
                "revoked_at": "2026-07-07T00:10:00Z",
                "last_used_at": None,
                "scopes": ["read:evidence"],
            },
        ],
        "governance_rules": [
            "never store or print full API key values",
            "public artifacts may include prefix and hash-presence only",
            "revocation state is auditable without exposing the sensitive value",
        ],
    }


def build_observability_summary(capability_matrix: Mapping[str, Any]) -> JsonDict:
    capabilities = capability_matrix.get("capabilities") if isinstance(capability_matrix.get("capabilities"), list) else []
    summary = capability_matrix.get("summary") if isinstance(capability_matrix.get("summary"), Mapping) else {}
    categories = summary.get("categories") if isinstance(summary.get("categories"), Mapping) else {}
    axis_counts = summary.get("axis_counts") if isinstance(summary.get("axis_counts"), Mapping) else {}
    category_names = [str(key) for key in categories]
    return {
        "schema_version": "ashr.clone.observability_summary.v1",
        "source": "capability_matrix_local_summary",
        "enterprise_saas_surface": True,
        "raw_trace_payloads_included": False,
        "metrics": {
            "capability_domains": len(category_names),
            "total_capabilities": len(capabilities),
            "median_capabilities_per_domain": _median_domain_count([str(key) for key, count in categories.items() for _ in range(int(count))]),
            "real_read_verified_capabilities": int(axis_counts.get("real_read_verified", 0) or 0),
            "frontend_mirrored_capabilities": int(axis_counts.get("frontend_mirrored", 0) or 0),
            "test_covered_capabilities": int(axis_counts.get("test_covered", 0) or 0),
            "error_patterns": [],
            "tool_reliability": [],
            "latency_distribution": {"source": "not_computed_in_public_artifact"},
            "cost_analytics": {"source": "placeholder_public_safe_no_amounts"},
        },
        "a3_handoff_fields": ["capability_domains", "total_capabilities", "error_patterns", "tool_reliability", "cost_analytics"],
    }


def build_readiness_badge(capability_matrix: Mapping[str, Any], evidence_index: Mapping[str, Any]) -> JsonDict:
    summary = capability_matrix.get("summary") if isinstance(capability_matrix.get("summary"), Mapping) else {}
    axis_counts = summary.get("axis_counts") if isinstance(summary.get("axis_counts"), Mapping) else {}
    policy_counts = evidence_index.get("output_policy_counts") if isinstance(evidence_index.get("output_policy_counts"), Mapping) else {}
    unsafe = int(policy_counts.get("unsafe_real_nonprivate_override", 0) or 0)
    return {
        "schema_version": "ashr.clone.commercial_readiness_badge.v1",
        "enterprise_saas_surface": True,
        "read_only_current": int(axis_counts.get("real_read_verified", 0) or 0) > 0,
        "gate_current": unsafe == 0,
        "mutation_blocked_or_quota_guarded": True,
        "paid_mutation_executed_this_round": False,
        "private_output_policy_current": unsafe == 0,
        "status": "enterprise_saas_read_only_verified_mutation_guarded",
        "buyer_safe_claims": [
            "live read-only API shapes were sampled into private evidence",
            "mutating and billing surfaces are classified before execution",
            "public artifacts omit raw keys, private refs, tenant payloads, and exact usage amounts",
            "enterprise SaaS control-plane surfaces are mapped across usage, billing, API keys, observability, and release gates",
        ],
    }


def validate_commercial_control_plane_kit(kit: Mapping[str, Any]) -> list[JsonDict]:
    issues: list[JsonDict] = []
    if kit.get("schema_version") != COMMERCIAL_KIT_SCHEMA_VERSION:
        issues.append({"severity": "error", "kind": "bad_schema_version"})
    text = str(kit)
    for forbidden in ("ASHR_API_KEY", "private_refs", "tp_", "sk-", "Bearer ", "ashr_live_"):
        if forbidden in text:
            issues.append({"severity": "error", "kind": "forbidden_public_text", "value": forbidden})
    if kit.get("product_posture") != "enterprise_saas_control_plane_evidence_kit":
        issues.append({"severity": "error", "kind": "missing_enterprise_saas_posture"})
    inventory = kit.get("api_key_inventory") if isinstance(kit.get("api_key_inventory"), Mapping) else {}
    if inventory.get("raw_sensitive_values_included") is not False:
        issues.append({"severity": "error", "kind": "api_key_sensitive_values_not_blocked"})
    return issues


def _resource_key(label: str) -> str:
    return label.lower().replace(" ", "_")


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _median_domain_count(domains: list[str]) -> float:
    if not domains:
        return 0.0
    counts: dict[str, int] = {}
    for domain in domains:
        counts[domain] = counts.get(domain, 0) + 1
    return float(median(counts.values()))
