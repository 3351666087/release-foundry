"""Executable A1 evidence to A2 release decision orchestration."""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from .evaluation_quality_proof import (
    quality_proof_bindings,
    verify_evaluation_quality_proof,
)
from .provider_gateway import ProviderGateway
from .provider_runtime import (
    build_provider_provenance_handoff,
    validate_semantic_judge_output,
    verify_authenticated_evidence_bundle,
)
from .result_persistence import stable_hash
from .release_decision_store import (
    FailureInjector,
    authorize_provider_call,
    claim_provider_reconciliation,
    claim_decision_recovery,
    load_decision_recovery_envelope,
    mark_operation_recovery_required,
    persist_provider_outcome,
    persist_provider_reconciliation_observation,
    persist_reconciled_provider_outcome,
    persist_release_decision,
    reserve_decision_operation,
)
from .trusted_spine import (
    build_decision_ledger,
    build_decision_record,
    build_evidence_snapshot,
)
from .derived_evidence import provider_text_parts


ORCHESTRATION_SCHEMA_VERSION = "a2.release_decision_orchestration.v1"
SCOPE_FIELDS = ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
RECOVERY_ENVELOPE_SCHEMA_VERSION = "a2.normalized_decision_envelope.v1"


def execute_release_decision(
    request: dict[str, Any],
    *,
    gateway: ProviderGateway,
    key_resolver: Callable[[str], bytes],
    now_unix_ms: int,
    persistence_connection: sqlite3.Connection | None = None,
    persistence_failure_injector: FailureInjector | None = None,
    worker_id: str = "a2-inline-worker",
    lease_seconds: int = 60,
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
        artifact_pipeline_records=_record_list(request, "artifact_pipeline_records"),
        derived_evidence_records=_record_list(request, "derived_evidence_records"),
    )
    parts, disclosed_citations = _provider_parts(
        snapshot,
        request.get("judge_prompt"),
        _record_list(request, "derived_evidence_records"),
    )
    provider_payload_hash = stable_hash(parts)
    evaluation_quality = verify_evaluation_quality_proof(
        request.get("evaluation_quality_proof"),
        expected_bindings=quality_proof_bindings(
            request,
            authenticated_bundle_digest=str(bundle_verification["authenticated_bundle_digest"]),
            snapshot_hash=str(snapshot["snapshot_hash"]),
            prompt_hash=stable_hash(str(request.get("judge_prompt") or "Evaluate the authenticated evidence snapshot.")),
        ),
        key_resolver=key_resolver,
        now_unix_ms=now_unix_ms,
    )
    request_hash = stable_hash(
        _request_identity(
            request,
            snapshot,
            provider_payload_hash=provider_payload_hash,
            evaluation_quality=evaluation_quality,
        )
    )
    provider_request_core = {
        "schema_version": "a2.provider_gateway.v1",
        "tenant_id": scope["tenant_id"],
        "snapshot_id": str(snapshot["snapshot_id"]),
        "snapshot_hash": str(snapshot["snapshot_hash"]),
        "provider_id": str(request["provider_id"]),
        "model_id": str(request["model_id"]),
        "modalities": sorted({str(part.get("modality") or "") for part in parts}),
        "payload_hash": provider_payload_hash,
        "idempotency_key": str(request["idempotency_key"]),
    }
    operation = None
    lease = None
    if persistence_connection is not None:
        operation = reserve_decision_operation(
            persistence_connection,
            scope=scope,
            idempotency_key=str(request["idempotency_key"]),
            request_hash=request_hash,
            snapshot_id=str(snapshot["snapshot_id"]),
            snapshot_hash=str(snapshot["snapshot_hash"]),
            provider_id=str(request["provider_id"]),
            model_id=str(request["model_id"]),
            created_at=str(request["created_at"]),
            reconciliation_mode=gateway.providers[str(request["provider_id"])].reconciliation_mode,
            provider_endpoint_hash=stable_hash({
                "provider_id": request["provider_id"],
                "protocol": gateway.providers[str(request["provider_id"])].protocol,
                "base_url": gateway.providers[str(request["provider_id"])].base_url,
            }),
        )
        if operation["replay"]:
            return _replayed_operation(operation)
        lease = authorize_provider_call(
            persistence_connection,
            operation_id=str(operation["operation_id"]),
            scope=scope,
            created_at=str(request["created_at"]),
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            logical_call_id=stable_hash(provider_request_core),
            payload_hash=provider_request_core["payload_hash"],
            idempotency_key_hash=stable_hash(str(request["idempotency_key"])),
        )
    try:
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
    except BaseException:
        if persistence_connection is not None and operation is not None:
            mark_operation_recovery_required(
                persistence_connection,
                operation_id=str(operation["operation_id"]),
                scope=scope,
                created_at=str(request["created_at"]),
                lease=lease,
            )
        raise
    semantic_output = _semantic_output(provider_result)
    citation_validation = _validate_evidence_refs(
        snapshot,
        semantic_output,
        disclosed_citations=disclosed_citations,
    )
    recovery_envelope = _build_recovery_envelope(
        request=request,
        scope=scope,
        snapshot=snapshot,
        provider_result=provider_result,
        semantic_output=semantic_output,
        citation_validation=citation_validation,
        bundle_verification=bundle_verification,
        provider_payload_hash=provider_payload_hash,
        evaluation_quality=evaluation_quality,
    )
    if persistence_connection is not None and operation is not None and lease is not None:
        persist_provider_outcome(
            persistence_connection,
            operation_id=str(operation["operation_id"]),
            scope=scope,
            lease=lease,
            provider_result=provider_result,
            semantic_output=semantic_output,
            recovery_envelope=recovery_envelope,
            completed_at=str(request["created_at"]),
            failure_injector=persistence_failure_injector,
        )
        if persistence_failure_injector is not None:
            persistence_failure_injector("after_provider_outcome_committed")
    result = _build_decision_result(recovery_envelope)
    provenance = result["provider_provenance"]
    decision = result["a3_consumption"]["display_decision"]
    if persistence_connection is not None:
        persistence = persist_release_decision(
            persistence_connection,
            result,
            idempotency_key=str(request["idempotency_key"]),
            request_hash=request_hash,
            operation_id=str(operation["operation_id"]) if operation else None,
            lease=lease,
            failure_injector=persistence_failure_injector,
        )
        result["persistence"] = persistence
        result["metadata"]["persistence_status"] = "committed"
        result["a3_consumption"]["release_ready"] = decision == "allow"
        result["a3_consumption"]["committed_record_id"] = persistence["record_id"]
    return result


def reconcile_release_decision(
    request: dict[str, Any],
    *,
    gateway: ProviderGateway,
    key_resolver: Callable[[str], bytes],
    now_unix_ms: int,
    connection: sqlite3.Connection,
    operation_id: str,
    worker_id: str = "a2-reconciliation-worker",
    now: str,
    lease_seconds: int = 60,
    next_reconcile_at: str | None = None,
    persistence_failure_injector: FailureInjector | None = None,
) -> dict[str, Any]:
    """Reconcile an uncertain Provider call without invoking or retrying it."""
    scope = _scope(request)
    run_payload, bundle_verification = _authenticated_run(
        request, key_resolver=key_resolver, now_unix_ms=now_unix_ms,
        tenant_id=scope["tenant_id"], project_id=scope["project_id"],
    )
    snapshot = build_evidence_snapshot(
        run_payload, **scope, run_id=str(request["run_id"]), case_id=str(request["case_id"]),
        scenario_id=str(request["scenario_id"]), created_at=str(request["created_at"]),
        required_modalities=[str(item) for item in request.get("required_modalities", ["text"])],
        source_schema_version=str(
            run_payload.get("aggregate_metrics", {}).get("schema_version")
            or request.get("source_schema_version") or "unknown"
        ),
        artifact_pipeline_records=_record_list(request, "artifact_pipeline_records"),
        derived_evidence_records=_record_list(request, "derived_evidence_records"),
    )
    lease = claim_provider_reconciliation(
        connection, operation_id=operation_id, scope=scope, worker_id=worker_id,
        now=now, lease_seconds=lease_seconds,
    )
    observation = gateway.reconcile(
        scope=scope, operation_id=operation_id, provider_call_id=lease["provider_call_id"],
        logical_call_id=lease["logical_call_id"], provider_id=lease["provider_id"],
        model_id=lease["model_id"], snapshot_hash=lease["snapshot_hash"],
        payload_hash=lease["payload_hash"], idempotency_key_hash=lease["idempotency_key_hash"],
        provider_endpoint_hash=lease["provider_endpoint_hash"],
        provider_generation=lease["fencing_token"],
        timeout_seconds=float(request.get("timeout_seconds", 30)),
    )
    if observation["status"] != "remote_completed":
        persist_provider_reconciliation_observation(
            connection, operation_id=operation_id, scope=scope, lease=lease,
            observation=observation, observed_at=now, next_reconcile_at=next_reconcile_at,
        )
        return _reconciliation_blocked(operation_id, observation["status"])
    semantic_output = observation["normalized_output"]
    provider_result = {
        "provider_id": lease["provider_id"],
        "model_id": lease["model_id"],
        "status": "completed",
        "logical_call_id": lease["logical_call_id"],
        "response_hash": observation["output_hash"],
        "blockers": [],
        "usage": {},
        "evaluation_eligible": True,
        "release_authority": False,
        "raw_request_included": False,
        "raw_response_included": False,
        "secret_included": False,
    }
    parts, disclosed_citations = _provider_parts(
        snapshot,
        request.get("judge_prompt"),
        _record_list(request, "derived_evidence_records"),
    )
    provider_payload_hash = stable_hash(parts)
    evaluation_quality = verify_evaluation_quality_proof(
        request.get("evaluation_quality_proof"),
        expected_bindings=quality_proof_bindings(
            request,
            authenticated_bundle_digest=str(bundle_verification["authenticated_bundle_digest"]),
            snapshot_hash=str(snapshot["snapshot_hash"]),
            prompt_hash=stable_hash(str(request.get("judge_prompt") or "Evaluate the authenticated evidence snapshot.")),
        ),
        key_resolver=key_resolver,
        now_unix_ms=now_unix_ms,
    )
    citation_validation = _validate_evidence_refs(
        snapshot,
        semantic_output,
        disclosed_citations=disclosed_citations,
    )
    envelope = _build_recovery_envelope(
        request=request, scope=scope, snapshot=snapshot, provider_result=provider_result,
        semantic_output=semantic_output, citation_validation=citation_validation,
        bundle_verification=bundle_verification, provider_payload_hash=provider_payload_hash,
        evaluation_quality=evaluation_quality,
    )
    persist_reconciled_provider_outcome(
        connection, operation_id=operation_id, scope=scope, lease=lease,
        observation=observation, provider_result=provider_result,
        semantic_output=semantic_output, recovery_envelope=envelope, completed_at=now,
        failure_injector=persistence_failure_injector,
    )
    return recover_release_decision(
        connection, operation_id=operation_id, scope=scope, worker_id=worker_id,
        now=now, lease_seconds=lease_seconds,
        persistence_failure_injector=persistence_failure_injector,
    )


def recover_release_decision(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    worker_id: str = "a2-recovery-worker",
    now: str,
    lease_seconds: int = 60,
    persistence_failure_injector: FailureInjector | None = None,
) -> dict[str, Any]:
    """Recover a provider-completed operation without invoking any Provider."""
    lease = claim_decision_recovery(
        connection,
        operation_id=operation_id,
        scope=scope,
        worker_id=worker_id,
        now=now,
        lease_seconds=lease_seconds,
    )
    envelope = load_decision_recovery_envelope(
        connection, operation_id=operation_id, scope=scope,
    )
    result = _build_decision_result(envelope)
    persistence = persist_release_decision(
        connection,
        result,
        idempotency_key=str(envelope["idempotency_key"]),
        request_hash=str(envelope["request_hash"]),
        operation_id=operation_id,
        lease=lease,
        commit_now=now,
        failure_injector=persistence_failure_injector,
    )
    decision = result["a3_consumption"]["display_decision"]
    result["persistence"] = persistence
    result["metadata"]["persistence_status"] = "committed"
    result["metadata"]["recovered_without_provider_call"] = True
    result["a3_consumption"]["release_ready"] = decision == "allow"
    result["a3_consumption"]["committed_record_id"] = persistence["record_id"]
    return result


def _reconciliation_blocked(operation_id: str, status: str) -> dict[str, Any]:
    result = _replayed_operation({"operation_id": operation_id, "status": "recovery_required"})
    result["metadata"]["reconciliation_status"] = status
    result["metadata"]["retry_authorized"] = False
    return result


def _replayed_operation(operation: dict[str, Any]) -> dict[str, Any]:
    status = str(operation.get("status") or "recovery_required")
    if status == "committed":
        decision = str(operation.get("decision") or "block")
        return {
            "schema_version": ORCHESTRATION_SCHEMA_VERSION,
            "persistence": {
                "committed": True,
                "idempotent_replay": True,
                "operation_id": operation["operation_id"],
                "record_id": operation["record_id"],
                "record_hash": operation["record_hash"],
                "decision": decision,
            },
            "a3_consumption": {
                "release_ready": decision == "allow",
                "display_decision": decision,
                "review_required": decision == "review",
                "display_provenance_hash": operation["record_hash"],
                "may_recompute_grade": False,
                "committed_decision_required": True,
                "committed_record_id": operation["record_id"],
            },
            "metadata": {
                "public_safe": True,
                "persistence_status": "committed",
                "idempotent_replay": True,
                "raw_evidence_included": False,
                "raw_provider_payload_included": False,
                "secrets_included": False,
            },
        }
    replay_status = "in_progress" if status in {"reserved", "provider_running", "provider_completed"} else "recovery_required"
    return {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "persistence": {
            "committed": False,
            "idempotent_replay": True,
            "operation_id": operation["operation_id"],
            "status": replay_status,
        },
        "a3_consumption": {
            "release_ready": False,
            "display_decision": "review",
            "review_required": True,
            "may_recompute_grade": False,
            "committed_decision_required": True,
        },
        "metadata": {
            "public_safe": True,
            "persistence_status": replay_status,
            "idempotent_replay": True,
            "raw_evidence_included": False,
            "raw_provider_payload_included": False,
            "secrets_included": False,
        },
    }


def _request_identity(
    request: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    provider_payload_hash: str = "",
    evaluation_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scope": _scope(request),
        "run_id": request.get("run_id"),
        "case_id": request.get("case_id"),
        "scenario_id": request.get("scenario_id"),
        "provider_id": request.get("provider_id"),
        "model_id": request.get("model_id"),
        "policy_version": request.get("policy_version"),
        "evaluation_quality": evaluation_quality,
        "required_modalities": snapshot.get("required_modalities"),
        "snapshot_hash": snapshot.get("snapshot_hash"),
        "provider_payload_hash": provider_payload_hash,
    }


def _scope(request: dict[str, Any]) -> dict[str, str]:
    scope = {field: str(request.get(field) or "") for field in SCOPE_FIELDS}
    if not all(scope.values()):
        raise ValueError("complete five-field tenant scope is required")
    return scope


def _record_list(request: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = request.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} must be a list of records")
    return value


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


def _provider_parts(
    snapshot: dict[str, Any],
    judge_prompt: Any,
    derived_evidence_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str]]:
    parts = [{"modality": "text", "text": str(judge_prompt or "Evaluate the authenticated evidence snapshot.")}]
    derived_parts = provider_text_parts(derived_evidence_records)
    parts.extend(derived_parts)
    disclosed = {
        str(citation)
        for part in derived_parts
        for citation in part.get("citation_ids") or []
    }
    return parts, disclosed


def _semantic_output(provider_result: dict[str, Any]) -> dict[str, Any] | None:
    if provider_result.get("status") != "completed":
        return None
    try:
        return validate_semantic_judge_output(str(provider_result.get("output_text") or ""))
    except ValueError:
        return None


def _validate_evidence_refs(
    snapshot: dict[str, Any],
    semantic_output: dict[str, Any] | None,
    *,
    disclosed_citations: set[str],
) -> dict[str, Any]:
    """Ground Provider citations in evidence actually disclosed to that Provider."""
    if semantic_output is None:
        return {
            "status": "not_available",
            "reference_hashes": [],
            "blockers": [],
            "public_safe": True,
        }
    snapshot_id = str(snapshot.get("snapshot_id") or "")
    requires_derived = "image" in set(snapshot.get("required_modalities") or [])
    allowed = set(disclosed_citations)
    if not requires_derived:
        allowed.add(snapshot_id)
    normalized: list[str] = []
    blockers: list[str] = []
    for reference in semantic_output.get("evidence_refs") or []:
        candidate = snapshot_id if reference == "snapshot" else str(reference)
        normalized.append(candidate)
        if candidate not in allowed:
            blockers.append("semantic_evidence_ref_ungrounded")
    if not normalized:
        blockers.append("semantic_evidence_refs_missing")
    if requires_derived and not any(item in disclosed_citations for item in normalized):
        blockers.append("semantic_derived_evidence_ref_missing")
    semantic_output["evidence_refs"] = normalized
    return {
        "status": "grounded" if not blockers else "invalid",
        "reference_hashes": [stable_hash(item) for item in normalized],
        "blockers": sorted(set(blockers)),
        "public_safe": True,
    }


def _build_recovery_envelope(
    *,
    request: dict[str, Any],
    scope: dict[str, str],
    snapshot: dict[str, Any],
    provider_result: dict[str, Any],
    semantic_output: dict[str, Any] | None,
    citation_validation: dict[str, Any],
    bundle_verification: dict[str, Any],
    provider_payload_hash: str,
    evaluation_quality: dict[str, Any],
) -> dict[str, Any]:
    provenance = build_provider_provenance_handoff(
        tenant_scope=scope,
        snapshot=snapshot,
        provider_result=provider_result,
        semantic_output=semantic_output,
        bundle_verification=bundle_verification,
    )
    safe_semantic = None
    if semantic_output is not None:
        safe_semantic = {
            "passed": semantic_output["passed"],
            "score": semantic_output["score"],
            "failure_classes": semantic_output["failure_classes"],
            "evidence_ref_hashes": [stable_hash(item) for item in semantic_output["evidence_refs"]],
            "abstained": semantic_output["abstained"],
        }
    return {
        "schema_version": RECOVERY_ENVELOPE_SCHEMA_VERSION,
        **scope,
        "idempotency_key": str(request["idempotency_key"]),
        "request_hash": stable_hash(
            _request_identity(
                request,
                snapshot,
                provider_payload_hash=provider_payload_hash,
                evaluation_quality=evaluation_quality,
            )
        ),
        "snapshot": snapshot,
        "provider": {
            "provider_id": str(provider_result.get("provider_id") or request["provider_id"]),
            "model_id": str(provider_result.get("model_id") or request["model_id"]),
            "status": str(provider_result.get("status") or "unknown"),
            "logical_call_id": str(provider_result.get("logical_call_id") or ""),
            "response_hash": str(provider_result.get("response_hash") or stable_hash(provider_result)),
            "blockers": sorted(set(str(item) for item in provider_result.get("blockers") or [])),
            "release_authority": False,
        },
        "provider_provenance": provenance,
        "semantic_output": safe_semantic,
        "citation_validation": citation_validation,
        "bundle_verification": {
            "manifest_authenticated": bundle_verification.get("manifest_authenticated") is True,
            "authenticated_bundle_digest": str(
                bundle_verification.get("authenticated_bundle_digest") or ""
            ),
        },
        "policy_version": str(request.get("policy_version") or "a2.semantic_release_policy.v1"),
        "evaluation_quality": evaluation_quality,
        "ledger_id": str(request.get("ledger_id") or f"{request['run_id']}:{request['case_id']}"),
        "judge_version": "provider-strict-v1",
        "builder_version": "a2.release-decision-builder.v1",
        "created_at": str(request["created_at"]),
        "provider_outcome_hash": "",
        "public_safe": True,
        "recovery_supported": True,
        "raw_provider_payload_included": False,
        "raw_evidence_included": False,
        "free_text_reason_included": False,
        "secrets_included": False,
    }


def _build_decision_result(envelope: dict[str, Any]) -> dict[str, Any]:
    if envelope.get("schema_version") != RECOVERY_ENVELOPE_SCHEMA_VERSION:
        raise ValueError("unsupported recovery envelope schema")
    if envelope.get("builder_version") != "a2.release-decision-builder.v1":
        raise ValueError("unsupported recovery decision builder")
    scope = _scope(envelope)
    snapshot = envelope.get("snapshot")
    provider = envelope.get("provider")
    provenance = envelope.get("provider_provenance")
    if not isinstance(snapshot, dict) or not isinstance(provider, dict) or not isinstance(provenance, dict):
        raise ValueError("recovery envelope structures are incomplete")
    if snapshot.get("snapshot_hash") != stable_hash(
        {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
    ):
        raise ValueError("recovery snapshot hash mismatch")
    semantic = envelope.get("semantic_output")
    if semantic is not None:
        semantic = dict(semantic)
        semantic["evidence_refs"] = list(semantic.pop("evidence_ref_hashes"))
        semantic["reason"] = "public-safe reason omitted"
    if provenance.get("tenant_scope") != scope:
        raise ValueError("recovery provenance scope mismatch")
    if provenance.get("snapshot_hash") != snapshot.get("snapshot_hash"):
        raise ValueError("recovery provenance snapshot mismatch")
    citation_validation = envelope.get("citation_validation")
    if not isinstance(citation_validation, dict):
        raise ValueError("recovery citation validation is incomplete")
    quality = envelope.get("evaluation_quality")
    if not isinstance(quality, dict):
        raise ValueError("recovery evaluation quality is incomplete")
    decision, blockers = _decision(
        snapshot,
        provider,
        semantic,
        provenance,
        citation_validation,
        quality,
    )
    gate = {
        "schema_version": "a2.release_gate.v1",
        "decision": "pass" if decision == "allow" else "warn" if decision == "review" else "block",
        "blocking_reasons": blockers,
        "review_required": decision == "review",
        "provider_status": provider.get("status"),
        "evaluation_quality": quality,
        "public_safe": True,
    }
    judge_result = _judge_result(semantic, provider)
    policy_version = str(envelope["policy_version"])
    record = build_decision_record(
        snapshot,
        decision=decision,
        release_gate_report=gate,
        judge_results=[judge_result],
        provider_provenance=[provenance],
        policy_version=policy_version,
        policy_hash=stable_hash(
            {
                "policy_version": policy_version,
                "required_modalities": snapshot["required_modalities"],
                "evaluation_quality": quality,
            }
        ),
        model_versions=[f"{provider['provider_id']}:{provider['model_id']}"],
        created_at=str(envelope["created_at"]),
    )
    ledger = build_decision_ledger(
        [record], ledger_id=str(envelope["ledger_id"]), **scope,
        created_at=str(envelope["created_at"]),
    )
    return {
        "schema_version": ORCHESTRATION_SCHEMA_VERSION,
        "evidence_snapshot": snapshot,
        "provider_provenance": provenance,
        "judge_result": judge_result,
        "release_gate": gate,
        "decision_ledger": ledger,
        "a3_consumption": {
            "release_ready": False,
            "display_decision": decision,
            "review_required": decision == "review",
            "display_provenance_hash": record["record_hash"],
            "may_recompute_grade": False,
            "committed_decision_required": True,
            "evaluation_quality": quality,
        },
        "metadata": {
            "public_safe": True,
            "raw_evidence_included": False,
            "raw_provider_payload_included": False,
            "secrets_included": False,
            "persistence_status": "not_configured",
        },
    }


def _decision(
    snapshot: dict[str, Any],
    provider_result: dict[str, Any],
    semantic_output: dict[str, Any] | None,
    provenance: dict[str, Any],
    citation_validation: dict[str, Any],
    evaluation_quality: dict[str, Any],
) -> tuple[str, list[str]]:
    blockers = list(snapshot.get("validation_errors") or []) + list(snapshot.get("missing_modalities") or [])
    blockers.extend(provider_result.get("blockers") or [])
    blockers.extend(provenance.get("blockers") or [])
    blockers.extend(citation_validation.get("blockers") or [])
    blockers.extend(evaluation_quality.get("blockers") or [])
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
