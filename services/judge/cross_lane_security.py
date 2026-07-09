"""Public-safe A1/A3 security boundary context for A2 policy verification."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "a2.cross_lane_security_context.v1"
DEFAULT_REPORT_ID = "a2_cross_lane_security_context"
DEFAULT_CREATED_AT = "2026-07-09T00:00:00Z"
DEFAULT_A1_ROUTE_SCOPE = Path("docs/a1/evidence/go_python_ts_route_parity_snapshot.json")
DEFAULT_A3_AUTH_RBAC_DOC = Path("docs/a3/p3_auth_rbac_boundary_2026_07_09.md")
DEFAULT_A3_OPENAPI = Path("docs/a3/openapi/a3_commercial_api.openapi.json")


def build_cross_lane_security_context(
    *,
    a1_route_scope_path: str | Path = DEFAULT_A1_ROUTE_SCOPE,
    a3_auth_rbac_doc_path: str | Path = DEFAULT_A3_AUTH_RBAC_DOC,
    a3_openapi_path: str | Path = DEFAULT_A3_OPENAPI,
    created_at: str = DEFAULT_CREATED_AT,
    report_id: str = DEFAULT_REPORT_ID,
) -> dict[str, Any]:
    """Summarize cross-lane auth/RBAC/RLS signals without reading private evidence."""
    a1 = _a1_route_scope_summary(Path(a1_route_scope_path))
    a3 = _a3_auth_rbac_summary(Path(a3_auth_rbac_doc_path), Path(a3_openapi_path))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "created_at": created_at,
        "source_refs": {
            "a1_route_scope": Path(a1_route_scope_path).as_posix(),
            "a3_auth_rbac_boundary": Path(a3_auth_rbac_doc_path).as_posix(),
            "a3_openapi": Path(a3_openapi_path).as_posix(),
        },
        "a1_route_scope": a1,
        "a3_auth_rbac_boundary": a3,
        "a2_policy_implications": _policy_implications(a1, a3),
        "a2_security_followups": _security_followups(a1, a3),
        "metadata": {
            "public_safe": True,
            "deterministic": True,
            "requires_network": False,
            "requires_ashr_api_key": False,
            "does_not_execute_live_calls": True,
            "does_not_read_private_evidence": True,
            "raw_private_evidence_not_recorded": True,
            "secrets_not_recorded": True,
            "intended_consumers": [
                "A2 release policy",
                "A2 security verification",
                "A3 SaaS admin console",
            ],
        },
    }


def _a1_route_scope_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _missing_source(
            path,
            "A1 route scope / RLS parity snapshot is not available on this branch yet.",
        )

    payload = _load_json(path)
    if not isinstance(payload, dict):
        return _invalid_source(path, "A1 route scope snapshot is not a JSON object.")

    routes = _route_values(payload)
    route_text = "\n".join(routes).lower()
    source_paths = _string_list(payload.get("source_paths"))
    rls_or_tenant_hardening_observed = _contains_any(payload, ["rls", "tenant", "project_id", "organization_id"])
    return {
        "available": True,
        "path": path.as_posix(),
        "schema_version": str(payload.get("schema_version", "")),
        "route_count": len(routes),
        "api_key_route_count": route_text.count("api-key") + route_text.count("api-keys"),
        "release_gate_route_count": route_text.count("release-gate") + route_text.count("release_gate"),
        "tenant_route_count": route_text.count("tenant") + route_text.count("project_id"),
        "has_python_routes": bool(payload.get("python_hosted_routes")),
        "has_ts_routes": bool(payload.get("ts_openapi_routes")),
        "has_go_routes": bool(payload.get("go_manifest_routes")),
        "intentional_difference_count": _intentional_difference_count(payload.get("intentional_route_differences")),
        "rls_or_tenant_hardening_observed": rls_or_tenant_hardening_observed,
        "source_paths": source_paths,
        "ready_for_a2_security_context": bool(routes) and rls_or_tenant_hardening_observed,
        "notes": [
            "A1 remains source of truth for backend route scope, tenant isolation, hosted auth, and RLS enforcement.",
            "A2 consumes this only as public-safe security verification context.",
        ],
    }


def _a3_auth_rbac_summary(doc_path: Path, openapi_path: Path) -> dict[str, Any]:
    if not doc_path.exists():
        return _missing_source(
            doc_path,
            "A3 Auth/RBAC boundary contract is not available on this branch yet.",
        )

    text = doc_path.read_text(encoding="utf-8")
    endpoints = sorted(set(re.findall(r"\b(?:GET|POST|PATCH|DELETE) /[A-Za-z0-9_./:{}-]+", text)))
    openapi_paths = _a3_openapi_auth_paths(openapi_path)
    anchor_present = "ANCHOR: A3_AUTH_RBAC_BOUNDARY_CONTRACT" in text
    a1_dependency_declared = "A1 remains source of truth" in text
    a2_dependency_declared = "A2 remains source of truth" in text
    safety = {
        "actor_hash_required": "actor_hash" in text,
        "raw_identity_redacted": "Raw actor identity is redacted" in text or "raw actor" in text.lower(),
        "tokens_forbidden": all(marker in text for marker in ["API keys", "tokens", "cookies"]),
        "hosted_mutations_blocked": "hosted mutations" in text.lower() and "blocked" in text.lower(),
        "metadata_only_audit": "metadata-only" in text.lower() and "ashr.event_envelope.v1" in text,
    }
    return {
        "available": True,
        "path": doc_path.as_posix(),
        "schema_version": "a3.auth_rbac_boundary.doc.v1",
        "anchor_present": anchor_present,
        "endpoint_count": len(endpoints),
        "endpoints": endpoints,
        "openapi_auth_path_count": len(openapi_paths),
        "openapi_auth_paths": openapi_paths,
        "a1_dependency_declared": a1_dependency_declared,
        "a2_dependency_declared": a2_dependency_declared,
        "hosted_auth_required_before_live_saas": "hosted auth" in text.lower(),
        "safety": safety,
        "ready_for_a2_security_context": (
            anchor_present
            and a1_dependency_declared
            and a2_dependency_declared
            and bool(openapi_paths)
            and all(safety.values())
        ),
        "notes": [
            "A3 owns product-workflow display and local authorization contract shape.",
            "A2 should verify denied states, abuse cases, redaction, and release policy effects.",
        ],
    }


def _policy_implications(a1: dict[str, Any], a3: dict[str, Any]) -> dict[str, Any]:
    return {
        "should_block_hosted_mutations_without_a1_auth": bool(
            a3.get("hosted_auth_required_before_live_saas")
            and a3.get("safety", {}).get("hosted_mutations_blocked")
        ),
        "should_require_metadata_only_audit_events": bool(a3.get("safety", {}).get("metadata_only_audit")),
        "should_keep_raw_actor_identity_forbidden": bool(a3.get("safety", {}).get("raw_identity_redacted")),
        "should_add_route_scope_security_cases": bool(a1.get("ready_for_a2_security_context")),
        "should_add_auth_rbac_abuse_cases": bool(a3.get("ready_for_a2_security_context")),
        "release_policy_refs": [
            "fixtures/a2/config/release_policies.json",
            "fixtures/a2/results/a2_release_gate_report.json",
            "fixtures/a2/results/a2_scenario_generation_backlog.json",
        ],
    }


def _security_followups(a1: dict[str, Any], a3: dict[str, Any]) -> list[dict[str, Any]]:
    followups = []
    if a1.get("ready_for_a2_security_context"):
        followups.append(
            _followup(
                "a2-route-scope-tenant-boundary",
                "Add route-scope tenant isolation abuse cases once A1 route parity is merged.",
                "A2 security verification",
                ["tenant_id", "project_id", "RLS", "route scope"],
            )
        )
    else:
        followups.append(
            _followup(
                "wait-for-a1-route-scope-public-snapshot",
                "Consume A1 route scope / RLS snapshot after it reaches this branch or main.",
                "A1/A2 integration",
                ["route parity", "RLS", "tenant isolation"],
            )
        )

    if a3.get("ready_for_a2_security_context"):
        followups.append(
            _followup(
                "a2-auth-rbac-denied-state-cases",
                "Promote A3 Auth/RBAC denied-state and hosted-mutation boundaries into A2 security scenarios.",
                "A2 scenario generation",
                ["authz", "RBAC", "hosted mutation", "redaction"],
            )
        )
    else:
        followups.append(
            _followup(
                "wait-for-a3-auth-rbac-boundary-contract",
                "Consume A3 Auth/RBAC boundary contract after it reaches this branch or main.",
                "A2/A3 integration",
                ["auth_context", "rbac_policy", "authz_decision"],
            )
        )
    return followups


def _followup(followup_id: str, action: str, owner: str, tags: list[str]) -> dict[str, Any]:
    return {
        "followup_id": followup_id,
        "action": action,
        "owner": owner,
        "tags": tags,
        "writes_private_evidence": False,
        "requires_user_decision": False,
    }


def _missing_source(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "ready_for_a2_security_context": False,
        "reason": reason,
        "notes": [reason],
    }


def _invalid_source(path: Path, reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "path": path.as_posix(),
        "schema_version": "",
        "ready_for_a2_security_context": False,
        "reason": reason,
        "notes": [reason],
    }


def _a3_openapi_auth_paths(path: Path) -> list[str]:
    if not path.exists():
        return []
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return []
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        return []
    return sorted(str(route) for route in paths if "/auth/" in str(route))


def _route_values(payload: dict[str, Any]) -> list[str]:
    routes: set[str] = set()
    for key, value in payload.items():
        if key.endswith("_routes") and isinstance(value, list):
            routes.update(str(item) for item in value)
    return sorted(route for route in routes if route.strip())


def _intentional_difference_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    count = 0
    for item in value.values():
        if isinstance(item, list):
            count += len(item)
    return count


def _contains_any(value: Any, needles: list[str]) -> bool:
    text = json.dumps(value, sort_keys=True).lower()
    return any(needle.lower() in text for needle in needles)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
