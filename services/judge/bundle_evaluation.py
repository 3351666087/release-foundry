"""Public-safe A1 evidence bundle evaluation facade for A2."""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from .provider_gateway import ProviderGateway
from .release_decision_orchestrator import execute_release_decision
from .result_persistence import stable_hash

EVALUATION_SCHEMA_VERSION = "a2.bundle_evaluation.v1"


def evaluate_a1_bundle(
    request: dict[str, Any],
    *,
    gateway: ProviderGateway,
    key_resolver: Callable[[str], bytes],
    now_unix_ms: int,
    persistence_connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Evaluate one authenticated A1 bundle and expose PASS/BLOCK/INCOMPLETE.

    Authentication, scope, integrity, or evidence-shape failures are returned as
    INCOMPLETE without invoking a Provider. Valid evidence reaches the configured
    Judge; every Provider/Judge/policy failure remains BLOCK or INCOMPLETE, never PASS.
    """
    request_fingerprint = stable_hash(_public_request_identity(request))
    try:
        result = execute_release_decision(
            request,
            gateway=gateway,
            key_resolver=key_resolver,
            now_unix_ms=now_unix_ms,
            persistence_connection=persistence_connection,
        )
    except (KeyError, TypeError, ValueError) as exc:
        finding = _safe_finding(exc)
        return {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "decision": "INCOMPLETE",
            "release_ready": False,
            "evidence_complete": False,
            "provider_called": False,
            "score": 0.0,
            "findings": [finding],
            "request_fingerprint": request_fingerprint,
            "reproducibility": {
                "input_version": str(request.get("source_schema_version") or "unknown"),
                "policy_version": str(request.get("policy_version") or "a2.semantic_release_policy.v1"),
                "request_fingerprint": request_fingerprint,
                "persisted": False,
                "idempotent_replay": False,
            },
            "metadata": _metadata(),
        }

    internal = str(result.get("a3_consumption", {}).get("display_decision") or result.get("persistence", {}).get("decision") or "block")
    gate = result.get("release_gate") if isinstance(result.get("release_gate"), dict) else {}
    snapshot = result.get("evidence_snapshot") if isinstance(result.get("evidence_snapshot"), dict) else {}
    judge = result.get("judge_result") if isinstance(result.get("judge_result"), dict) else {}
    persistence = result.get("persistence") if isinstance(result.get("persistence"), dict) else {}
    blockers = sorted(set(str(item) for item in gate.get("blocking_reasons", []) if item))
    decision = _external_decision(internal, blockers)
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "decision": decision,
        "release_ready": decision == "PASS" and persistence.get("committed") is True,
        "evidence_complete": snapshot.get("completeness") == "complete",
        "provider_called": _provider_called(result.get("provider_provenance", {})),
        "score": float(judge.get("score") or 0),
        "findings": [
            {"code": code, "severity": "blocking", "source": _finding_source(code)}
            for code in blockers
        ],
        "judge": judge,
        "release_gate": gate,
        "evidence_snapshot": {
            "snapshot_id": snapshot.get("snapshot_id", ""),
            "snapshot_hash": snapshot.get("snapshot_hash", ""),
            "completeness": snapshot.get("completeness", "incomplete"),
            "missing_modalities": snapshot.get("missing_modalities", []),
        },
        "provider_provenance": result.get("provider_provenance", {}),
        "decision_record_hash": result.get("a3_consumption", {}).get("display_provenance_hash", ""),
        "request_fingerprint": request_fingerprint,
        "reproducibility": {
            "input_version": str(request.get("source_schema_version") or snapshot.get("source_schema_version") or "unknown"),
            "policy_version": str(request.get("policy_version") or "a2.semantic_release_policy.v1"),
            "request_fingerprint": request_fingerprint,
            "persisted": persistence.get("committed") is True,
            "idempotent_replay": persistence.get("idempotent_replay") is True,
            "operation_id": persistence.get("operation_id", ""),
            "record_id": persistence.get("record_id", ""),
        },
        "metadata": _metadata(),
    }


def _external_decision(internal: str, blockers: list[str]) -> str:
    if internal == "allow" and not blockers:
        return "PASS"
    provider_failures = {"timeout", "rate_limited", "provider_unavailable", "provider_error", "invalid_response", "provider_not_completed"}
    if any(code in provider_failures for code in blockers):
        return "BLOCK"
    incomplete = {
        "evidence_not_complete", "semantic_output_invalid", "semantic_judge_abstained",
        "missing_text", "missing_image", "missing_audio", "missing_file", "missing_video",
    }
    if internal == "review" or any(code in incomplete or code.startswith("missing_") for code in blockers):
        return "INCOMPLETE"
    return "BLOCK"


def _provider_called(provenance: Any) -> bool:
    if not isinstance(provenance, dict):
        return False
    return int(provenance.get("attempt_count") or 0) > 0


def _safe_finding(exc: Exception) -> dict[str, str]:
    text = str(exc).lower()
    if "scope" in text or "tenant" in text or "project" in text:
        code = "evidence_scope_invalid"
    elif "signature" in text or "digest" in text or "authenticated" in text or "bundle" in text:
        code = "evidence_authenticity_invalid"
    else:
        code = "evidence_contract_invalid"
    return {"code": code, "severity": "blocking", "source": "evidence_verifier"}


def _finding_source(code: str) -> str:
    if code.startswith("evidence_") or code.startswith("missing_"):
        return "evidence_verifier"
    if code.startswith("semantic_"):
        return "judge"
    if code in {"timeout", "rate_limited", "provider_unavailable", "provider_error", "invalid_response"}:
        return "provider"
    return "policy"


def _public_request_identity(request: dict[str, Any]) -> dict[str, Any]:
    bundle = request.get("authenticated_evidence_bundle")
    return {
        "scope": {key: request.get(key) for key in (
            "organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"
        )},
        "run_id": request.get("run_id"), "case_id": request.get("case_id"),
        "scenario_id": request.get("scenario_id"), "provider_id": request.get("provider_id"),
        "model_id": request.get("model_id"), "policy_version": request.get("policy_version"),
        "bundle_digest": stable_hash(bundle) if isinstance(bundle, dict) else "",
    }


def _metadata() -> dict[str, bool]:
    return {"public_safe": True, "raw_evidence_included": False, "raw_provider_payload_included": False, "secrets_included": False}
