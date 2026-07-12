"""Executable A1 evidence to A2 release decision orchestration."""

from __future__ import annotations

from typing import Any, Callable

from .provider_gateway import ProviderGateway
from .provider_runtime import (
    build_provider_provenance_handoff,
    validate_semantic_judge_output,
    verify_authenticated_evidence_bundle,
)
from .result_persistence import stable_hash
from .trusted_spine import (
    build_decision_ledger,
    build_decision_record,
    build_evidence_snapshot,
)


ORCHESTRATION_SCHEMA_VERSION = "a2.release_decision_orchestration.v1"
SCOPE_FIELDS = ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")


def execute_release_decision(
    request: dict[str, Any],
    *,
    gateway: ProviderGateway,
    key_resolver: Callable[[str], bytes],
    now_unix_ms: int,
) -> dict[str, Any]:
    """Execute one fail-closed semantic release decision from authenticated A1 evidence."""
    scope = _scope(request)
    run_payload, bundle_verification = _authenticated_run(
        request,
        key_resolver=key_resolver,
        now_unix_ms=now_unix_ms,
        tenant_id=scope["tenant_id"],
        project_id=scope["project_id"],
    )
    snapshot = build_evidence_snapshot(
        run_payload,
        **scope,
        run_id=str(request["run_id"]),
        case_id=str(request["case_id"]),
        scenario_id=str(request["scenario_id"]),
        created_at=str(request["created_at"]),
        required_modalities=[str(item) for item in request.get("required_modalities", ["text"])],
        source_schema_version=str(
            run_payload.get("aggregate_metrics", {}).get("schema_version")
            or request.get("source_schema_version")
            or "unknown"
        ),
    )
    parts = _provider_parts(snapshot, request.get("judge_prompt"))
    provider_result = gateway.invoke(
        tenant_id=scope["tenant_id"],
        snapshot=snapshot,
        provider_id=str(request["provider_id"]),
        model_id=str(request["model_id"]),
        parts=parts,
        idempotency_key=str(request["idempotency_key"]),
        timeout_seconds=float(request.get("timeout_seconds", 30)),
        max_cost_usd=float(request.get("max_cost_usd", 0)),
    )
    semantic_output = _semantic_output(provider_result)
    provenance = build_provider_provenance_handoff(
        tenant_scope=scope,
        snapshot=snapshot,
        provider_result=provider_result,
        semantic_output=semantic_output,
        bundle_verification=bundle_verification,
    )
    decision, blockers = _decision(snapshot, provider_result, semantic_output, provenance)
    gate = {
        "schema_version": "a2.release_gate.v1",
        "decision": "pass" if decision == "allow" else "warn" if decision == "review" else "block",
        "blocking_reasons": blockers,
        "review_required": decision == "review",
        "provider_status": provider_result.get("status"),
        "public_safe": True,
    }
    judge_result = _judge_result(semantic_output, provider_result)
    policy_version = str(request.get("policy_version") or "a2.semantic_release_policy.v1")
    record = build_decision_record(
        snapshot,
        decision=decision,
        release_gate_report=gate,
        judge_results=[judge_result],
        provider_provenance=[provenance],
        policy_version=policy_version,
        policy_hash=stable_hash({"policy_version": policy_version, "required_modalities": snapshot["required_modalities"]}),
        model_versions=[f"{request['provider_id']}:{request['model_id']}"],
        created_at=str(request["created_at"]),
    )
    ledger = build_decision_ledger(
        [record],
        ledger_id=str(request.get("ledger_id") or f"{request['run_id']}:{request['case_id']}"),
        **scope,
        created_at=str(request["created_at"]),
    )
    return {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "evidence_snapshot": snapshot,
        "provider_provenance": provenance,
        "judge_result": judge_result,
        "release_gate": gate,
        "decision_ledger": ledger,
        "a3_consumption": {
            "release_ready": decision == "allow",
            "display_decision": decision,
            "review_required": decision == "review",
            "display_provenance_hash": record["record_hash"],
            "may_recompute_grade": False,
        },
        "metadata": {
            "public_safe": True,
            "raw_evidence_included": False,
            "raw_provider_payload_included": False,
            "secrets_included": False,
        },
    }


def _scope(request: dict[str, Any]) -> dict[str, str]:
    scope = {field: str(request.get(field) or "") for field in SCOPE_FIELDS}
    if not all(scope.values()):
        raise ValueError("complete five-field tenant scope is required")
    return scope


def _authenticated_run(
    request: dict[str, Any],
    *,
    key_resolver: Callable[[str], bytes],
    now_unix_ms: int,
    tenant_id: str,
    project_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    bundle = request.get("authenticated_evidence_bundle")
    if not isinstance(bundle, dict):
        raise ValueError("authenticated A1 evidence bundle is required")
    verification = verify_authenticated_evidence_bundle(
        bundle,
        key_resolver=key_resolver,
        tenant_id=tenant_id,
        project_id=project_id,
        now_unix_ms=now_unix_ms,
    )
    evidence = bundle.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != 1 or not isinstance(evidence[0], dict):
        raise ValueError("authenticated bundle must contain exactly one A1 RunResult")
    return evidence[0], verification


def _provider_parts(snapshot: dict[str, Any], judge_prompt: Any) -> list[dict[str, Any]]:
    parts = [{"modality": "text", "text": str(judge_prompt or "Evaluate the authenticated evidence snapshot.")}]
    for artifact in snapshot.get("artifacts", []):
        parts.append(
            {
                "modality": artifact["modality"],
                "content_hash": artifact["content_hash"],
                "reference_hash": artifact["reference_hash"],
            }
        )
    return parts


def _semantic_output(provider_result: dict[str, Any]) -> dict[str, Any] | None:
    if provider_result.get("status") != "completed":
        return None
    try:
        return validate_semantic_judge_output(str(provider_result.get("output_text") or ""))
    except ValueError:
        return None


def _decision(
    snapshot: dict[str, Any],
    provider_result: dict[str, Any],
    semantic_output: dict[str, Any] | None,
    provenance: dict[str, Any],
) -> tuple[str, list[str]]:
    blockers = list(snapshot.get("validation_errors") or []) + list(snapshot.get("missing_modalities") or [])
    blockers.extend(provider_result.get("blockers") or [])
    blockers.extend(provenance.get("blockers") or [])
    if snapshot.get("completeness") != "complete":
        blockers.append("evidence_not_complete")
    if semantic_output is None:
        blockers.append("semantic_output_invalid")
    elif semantic_output["abstained"]:
        blockers.append("semantic_judge_abstained")
    elif not semantic_output["passed"]:
        blockers.extend(semantic_output["failure_classes"] or ["semantic_judge_failed"])
    blockers = sorted(set(str(item) for item in blockers if item))
    if blockers:
        return ("review" if semantic_output and semantic_output["abstained"] and len(blockers) == 1 else "block"), blockers
    return "allow", []


def _judge_result(
    semantic_output: dict[str, Any] | None,
    provider_result: dict[str, Any],
) -> dict[str, Any]:
    if semantic_output is None:
        return {
            "judge_id": "semantic",
            "judge_version": "provider-strict-v1",
            "passed": False,
            "outcome": "fail",
            "score": 0,
            "failure_classes": ["semantic_output_invalid"],
            "provider_status": provider_result.get("status"),
        }
    return {
        "judge_id": "semantic",
        "judge_version": "provider-strict-v1",
        "passed": semantic_output["passed"],
        "outcome": "abstain" if semantic_output["abstained"] else "pass" if semantic_output["passed"] else "fail",
        "score": semantic_output["score"],
        "failure_classes": semantic_output["failure_classes"],
        "evidence_refs": semantic_output["evidence_refs"],
        "reason": semantic_output["reason"],
    }
