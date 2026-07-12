"""Atomic public-safe persistence for A2 release decisions."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .result_persistence import stable_hash
from .trusted_spine import GENESIS_HASH, build_decision_ledger


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused for a different decision input."""


FailureInjector = Callable[[str], None]
_SECRET_OR_LOCATION = re.compile(
    r"(?i)(bearer\s+|api[_-]?key|token=|https?://|file://|[a-z]:\\|/private_refs/)"
)
_SHA256_REF = re.compile(r"sha256:[0-9a-f]{64}\Z")


def reserve_decision_operation(
    connection: sqlite3.Connection,
    *,
    scope: dict[str, str],
    idempotency_key: str,
    request_hash: str,
    snapshot_id: str,
    snapshot_hash: str,
    provider_id: str,
    model_id: str,
    created_at: str,
    reconciliation_mode: str = "unsupported",
    provider_endpoint_hash: str = "",
) -> dict[str, Any]:
    """Reserve an idempotent operation before any external provider call."""
    if not idempotency_key:
        raise ValueError("idempotency key is required")
    if reconciliation_mode not in {"unsupported", "provider_status_lookup"}:
        raise ValueError("unsupported Provider reconciliation mode")
    if reconciliation_mode == "provider_status_lookup" and not provider_endpoint_hash:
        raise ValueError("provider_status_lookup requires a Provider endpoint hash")
    normalized_scope = _scope(scope)
    operation_core = {
        **normalized_scope,
        "idempotency_key": idempotency_key,
        "request_hash": request_hash,
        "snapshot_hash": snapshot_hash,
        "provider_id": provider_id,
        "model_id": model_id,
    }
    operation_id = stable_hash(operation_core)
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = _operation_row(connection, normalized_scope, idempotency_key)
        if existing is not None:
            if existing["request_hash"] != request_hash or existing["snapshot_hash"] != snapshot_hash:
                raise IdempotencyConflictError("idempotency key reused with different decision input")
            connection.commit()
            return _operation_summary(existing, replay=True)
        connection.execute(
            """
            INSERT INTO a2_decision_operations (
              operation_id, idempotency_key, organization_id, tenant_id, workspace_id,
              project_id, environment_id, request_hash, snapshot_id, snapshot_hash,
              provider_id, model_id, reconciliation_mode, provider_endpoint_hash,
              status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)
            """,
            (
                operation_id, idempotency_key, normalized_scope["organization_id"],
                normalized_scope["tenant_id"], normalized_scope["workspace_id"],
                normalized_scope["project_id"], normalized_scope["environment_id"],
                request_hash, snapshot_id, snapshot_hash, provider_id, model_id,
                reconciliation_mode, provider_endpoint_hash,
                created_at, created_at,
            ),
        )
        _write_operation_audit(
            connection, operation_id, normalized_scope, "operation_reserved", created_at,
            {"request_hash": request_hash, "snapshot_hash": snapshot_hash},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "operation_id": operation_id,
        "status": "reserved",
        "replay": False,
        "provider_call_allowed": True,
    }


def authorize_provider_call(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    created_at: str,
    worker_id: str = "a2-inline-worker",
    lease_seconds: int = 60,
    logical_call_id: str = "",
    payload_hash: str = "",
    idempotency_key_hash: str = "",
) -> dict[str, Any]:
    """Acquire fenced execution authority before handing control to the provider."""
    normalized_scope = _scope(scope)
    now = _timestamp(created_at)
    lease_expires_at = (now + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _operation_by_id(connection, operation_id)
        if row is None or any(row[field] != value for field, value in normalized_scope.items()):
            raise ValueError("decision operation scope mismatch")
        expired = bool(row.get("lease_expires_at")) and _timestamp(row["lease_expires_at"]) <= now
        if row["status"] != "reserved" and not (row["status"] == "provider_running" and expired):
            raise ValueError(f"decision operation cannot acquire lease from status {row['status']}")
        fencing_token = int(row["fencing_token"]) + 1
        provider_call_id = stable_hash(
            {"operation_id": operation_id, "fencing_token": fencing_token, "attempt": int(row["attempt_count"]) + 1}
        )
        cursor = connection.execute(
            """
            UPDATE a2_decision_operations
            SET status = 'provider_running', lease_owner = ?, lease_expires_at = ?,
                fencing_token = ?, attempt_count = attempt_count + 1,
                provider_call_id = ?, logical_call_id = ?, provider_payload_hash = ?,
                provider_idempotency_key_hash = ?, updated_at = ?
            WHERE operation_id = ? AND fencing_token = ?
            """,
            (
                worker_id, lease_expires_at, fencing_token, provider_call_id,
                logical_call_id, payload_hash, idempotency_key_hash,
                created_at, operation_id, row["fencing_token"],
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("decision operation lease contention")
        _write_operation_audit(
            connection, operation_id, normalized_scope, "provider_call_authorized", created_at,
            {"provider_call_id": provider_call_id, "fencing_token": fencing_token},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "operation_id": operation_id,
        "worker_id": worker_id,
        "fencing_token": fencing_token,
        "provider_call_id": provider_call_id,
        "lease_expires_at": lease_expires_at,
    }


def claim_provider_reconciliation(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    worker_id: str,
    now: str,
    lease_seconds: int = 60,
) -> dict[str, Any]:
    """Claim one uncertain Provider operation without authorizing another call."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    normalized_scope = _scope(scope)
    now_value = _timestamp(now)
    lease_expires_at = (now_value + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _operation_by_id(connection, operation_id)
        if row is None or any(row[field] != value for field, value in normalized_scope.items()):
            raise ValueError("decision operation scope mismatch")
        if row["status"] != "recovery_required":
            raise ValueError(f"provider reconciliation cannot claim status {row['status']}")
        if row["reconciliation_mode"] != "provider_status_lookup":
            raise ValueError("provider reconciliation is unsupported")
        if row.get("reconciliation_next_at") and _timestamp(row["reconciliation_next_at"]) > now_value:
            raise ValueError("provider reconciliation is not due")
        active = (
            bool(row.get("reconciliation_owner"))
            and bool(row.get("reconciliation_lease_expires_at"))
            and _timestamp(row["reconciliation_lease_expires_at"]) > now_value
        )
        if active:
            raise ValueError("provider reconciliation lease contention")
        required = ("provider_call_id", "logical_call_id", "provider_payload_hash", "provider_idempotency_key_hash")
        if any(not row.get(field) for field in required):
            raise ValueError("provider reconciliation identity is incomplete")
        generation = int(row["reconciliation_generation"]) + 1
        cursor = connection.execute(
            """
            UPDATE a2_decision_operations
            SET reconciliation_owner = ?, reconciliation_lease_expires_at = ?,
                reconciliation_generation = ?,
                reconciliation_attempt_count = reconciliation_attempt_count + 1,
                reconciliation_next_at = NULL, updated_at = ?
            WHERE operation_id = ? AND status = 'recovery_required'
              AND reconciliation_generation = ?
            """,
            (worker_id, lease_expires_at, generation, now, operation_id, row["reconciliation_generation"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("provider reconciliation lease contention")
        _write_operation_audit(
            connection, operation_id, normalized_scope, "provider_reconciliation_claimed", now,
            {"provider_fencing_token": row["fencing_token"], "reconciliation_generation": generation},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "operation_id": operation_id,
        "worker_id": worker_id,
        "provider_call_id": row["provider_call_id"],
        "fencing_token": int(row["fencing_token"]),
        "reconciliation_generation": generation,
        "lease_expires_at": lease_expires_at,
        "provider_id": row["provider_id"],
        "model_id": row["model_id"],
        "logical_call_id": row["logical_call_id"],
        "snapshot_hash": row["snapshot_hash"],
        "payload_hash": row["provider_payload_hash"],
        "idempotency_key_hash": row["provider_idempotency_key_hash"],
        "provider_endpoint_hash": row["provider_endpoint_hash"],
    }


def claim_due_provider_reconciliation(
    connection: sqlite3.Connection,
    *,
    worker_id: str,
    now: str,
    lease_seconds: int = 60,
) -> dict[str, Any] | None:
    """Claim the oldest due reconciliation job across tenant scopes."""
    _timestamp(now)
    row = connection.execute(
        """
        SELECT operation_id, organization_id, tenant_id, workspace_id, project_id, environment_id
        FROM a2_decision_operations
        WHERE status = 'recovery_required'
          AND reconciliation_mode = 'provider_status_lookup'
          AND provider_call_id IS NOT NULL
          AND logical_call_id IS NOT NULL
          AND provider_payload_hash IS NOT NULL
          AND provider_idempotency_key_hash IS NOT NULL
          AND provider_endpoint_hash <> ''
          AND (reconciliation_next_at IS NULL OR reconciliation_next_at <= ?)
          AND (
            reconciliation_owner IS NULL
            OR reconciliation_lease_expires_at IS NULL
            OR reconciliation_lease_expires_at <= ?
          )
        ORDER BY COALESCE(reconciliation_next_at, created_at), created_at, operation_id
        LIMIT 1
        """,
        (now, now),
    ).fetchone()
    if row is None:
        return None
    operation_id, *scope_values = row
    scope = dict(zip(
        ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"),
        scope_values,
    ))
    try:
        return claim_provider_reconciliation(
            connection, operation_id=operation_id, scope=scope, worker_id=worker_id,
            now=now, lease_seconds=lease_seconds,
        )
    except ValueError as exc:
        if "contention" in str(exc) or "not due" in str(exc):
            return None
        raise


def persist_provider_reconciliation_observation(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    lease: dict[str, Any],
    observation: dict[str, Any],
    observed_at: str,
    next_reconcile_at: str | None = None,
) -> dict[str, Any]:
    """Append one public-safe observation while keeping release and retry closed."""
    normalized_scope = _scope(scope)
    record = _reconciliation_record(operation_id, normalized_scope, lease, observation, observed_at, next_reconcile_at)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _operation_by_id(connection, operation_id)
        _assert_reconciliation_fence(row, normalized_scope, lease, observed_at)
        _insert_reconciliation_observation(connection, record)
        connection.execute(
            """
            UPDATE a2_decision_operations
            SET last_reconciliation_status = ?, last_reconciliation_observation_hash = ?,
                reconciliation_next_at = ?, reconciliation_owner = NULL,
                reconciliation_lease_expires_at = NULL, updated_at = ?
            WHERE operation_id = ? AND reconciliation_owner = ?
              AND reconciliation_generation = ?
            """,
            (
                record["status"], record["observation_hash"], next_reconcile_at, observed_at,
                operation_id, lease["worker_id"], lease["reconciliation_generation"],
            ),
        )
        _write_operation_audit(
            connection, operation_id, normalized_scope, "provider_reconciliation_observed", observed_at,
            {"status": record["status"], "observation_hash": record["observation_hash"]},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return record


def persist_provider_outcome(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    lease: dict[str, Any],
    provider_result: dict[str, Any],
    semantic_output: dict[str, Any] | None,
    recovery_envelope: dict[str, Any] | None = None,
    completed_at: str,
    failure_injector: FailureInjector | None = None,
) -> dict[str, str]:
    """Persist Provider hashes plus a governed public-safe recovery envelope."""
    normalized_scope = _scope(scope)
    if recovery_envelope is None:
        recovery_envelope = {
            "schema_version": "a2.normalized_decision_envelope.v1",
            **normalized_scope,
            "provider_outcome_hash": "",
            "public_safe": True,
            "recovery_supported": False,
        }
    _validate_recovery_envelope(recovery_envelope, normalized_scope)
    outcome = {
        "provider_call_id": lease["provider_call_id"],
        "operation_id": operation_id,
        "fencing_token": lease["fencing_token"],
        "provider_id": provider_result.get("provider_id"),
        "model_id": provider_result.get("model_id"),
        "normalized_status": provider_result.get("status"),
        "response_hash": stable_hash(provider_result),
        "semantic_output_hash": stable_hash(semantic_output),
        "usage_hash": stable_hash(provider_result.get("usage") or {}),
    }
    outcome_hash = stable_hash(outcome)
    recovery_envelope = dict(recovery_envelope)
    recovery_envelope["provider_outcome_hash"] = outcome_hash
    recovery_envelope_json = json.dumps(
        recovery_envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    recovery_envelope_hash = stable_hash(recovery_envelope)
    injector = failure_injector or (lambda _: None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _operation_by_id(connection, operation_id)
        _assert_fence(row, normalized_scope, lease, "provider_running")
        connection.execute(
            """
            INSERT INTO a2_provider_outcomes (
              provider_call_id, operation_id, organization_id, tenant_id, workspace_id,
              project_id, environment_id, fencing_token, provider_id, model_id,
              normalized_status, response_hash, semantic_output_hash, usage_hash,
              outcome_hash, recovery_envelope_schema, recovery_envelope_json,
              recovery_envelope_hash, completed_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                lease["provider_call_id"], operation_id, normalized_scope["organization_id"],
                normalized_scope["tenant_id"], normalized_scope["workspace_id"],
                normalized_scope["project_id"], normalized_scope["environment_id"],
                lease["fencing_token"], str(provider_result.get("provider_id") or ""),
                str(provider_result.get("model_id") or ""), str(provider_result.get("status") or "unknown"),
                outcome["response_hash"], outcome["semantic_output_hash"], outcome["usage_hash"],
                outcome_hash, recovery_envelope["schema_version"], recovery_envelope_json,
                recovery_envelope_hash, completed_at,
            ),
        )
        injector("after_provider_outcome")
        cursor = connection.execute(
            """
            UPDATE a2_decision_operations
            SET status = 'provider_completed', provider_outcome_hash = ?, updated_at = ?
            WHERE operation_id = ? AND lease_owner = ? AND fencing_token = ?
            """,
            (outcome_hash, completed_at, operation_id, lease["worker_id"], lease["fencing_token"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("stale fencing token")
        _write_operation_audit(
            connection, operation_id, normalized_scope, "provider_outcome_persisted", completed_at,
            {"provider_call_id": lease["provider_call_id"], "outcome_hash": outcome_hash},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "provider_call_id": str(lease["provider_call_id"]),
        "outcome_hash": outcome_hash,
        "recovery_envelope_hash": recovery_envelope_hash,
    }


def persist_reconciled_provider_outcome(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    lease: dict[str, Any],
    observation: dict[str, Any],
    provider_result: dict[str, Any],
    semantic_output: dict[str, Any],
    recovery_envelope: dict[str, Any],
    completed_at: str,
    failure_injector: FailureInjector | None = None,
) -> dict[str, str]:
    """Atomically bridge a verified remote completion into the normal outcome path."""
    normalized_scope = _scope(scope)
    _validate_recovery_envelope(recovery_envelope, normalized_scope)
    record = _reconciliation_record(operation_id, normalized_scope, lease, observation, completed_at, None)
    if record["status"] != "remote_completed":
        raise ValueError("only remote_completed may persist a reconciled outcome")
    outcome = {
        "provider_call_id": lease["provider_call_id"],
        "operation_id": operation_id,
        "fencing_token": lease["fencing_token"],
        "provider_id": provider_result.get("provider_id"),
        "model_id": provider_result.get("model_id"),
        "normalized_status": provider_result.get("status"),
        "response_hash": stable_hash(provider_result),
        "semantic_output_hash": stable_hash(semantic_output),
        "usage_hash": stable_hash(provider_result.get("usage") or {}),
    }
    outcome_hash = stable_hash(outcome)
    envelope = dict(recovery_envelope)
    envelope["provider_outcome_hash"] = outcome_hash
    envelope_json = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    envelope_hash = stable_hash(envelope)
    injector = failure_injector or (lambda _: None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _operation_by_id(connection, operation_id)
        _assert_reconciliation_fence(row, normalized_scope, lease, completed_at)
        _insert_reconciliation_observation(connection, record)
        injector("after_reconciliation_observation")
        connection.execute(
            """
            INSERT INTO a2_provider_outcomes (
              provider_call_id, operation_id, organization_id, tenant_id, workspace_id,
              project_id, environment_id, fencing_token, provider_id, model_id,
              normalized_status, response_hash, semantic_output_hash, usage_hash,
              outcome_hash, recovery_envelope_schema, recovery_envelope_json,
              recovery_envelope_hash, completed_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                lease["provider_call_id"], operation_id, normalized_scope["organization_id"],
                normalized_scope["tenant_id"], normalized_scope["workspace_id"],
                normalized_scope["project_id"], normalized_scope["environment_id"],
                lease["fencing_token"], str(provider_result.get("provider_id") or ""),
                str(provider_result.get("model_id") or ""), str(provider_result.get("status") or "unknown"),
                outcome["response_hash"], outcome["semantic_output_hash"], outcome["usage_hash"],
                outcome_hash, envelope["schema_version"], envelope_json, envelope_hash, completed_at,
            ),
        )
        injector("after_reconciled_provider_outcome")
        cursor = connection.execute(
            """
            UPDATE a2_decision_operations
            SET status = 'provider_completed', provider_outcome_hash = ?,
                last_reconciliation_status = 'remote_completed',
                last_reconciliation_observation_hash = ?,
                reconciliation_owner = NULL, reconciliation_lease_expires_at = NULL,
                updated_at = ?
            WHERE operation_id = ? AND status = 'recovery_required'
              AND reconciliation_owner = ? AND reconciliation_generation = ?
              AND fencing_token = ?
            """,
            (
                outcome_hash, record["observation_hash"], completed_at, operation_id,
                lease["worker_id"], lease["reconciliation_generation"], lease["fencing_token"],
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("stale provider reconciliation fence")
        _write_operation_audit(
            connection, operation_id, normalized_scope, "reconciled_provider_outcome_persisted", completed_at,
            {"observation_hash": record["observation_hash"], "outcome_hash": outcome_hash},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "provider_call_id": str(lease["provider_call_id"]),
        "outcome_hash": outcome_hash,
        "recovery_envelope_hash": envelope_hash,
    }


def claim_decision_recovery(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    worker_id: str,
    now: str,
    lease_seconds: int = 60,
) -> dict[str, Any]:
    """Claim a completed Provider outcome without authorizing another Provider call."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    normalized_scope = _scope(scope)
    lease_expires_at = (
        _timestamp(now) + timedelta(seconds=lease_seconds)
    ).isoformat().replace("+00:00", "Z")
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _operation_by_id(connection, operation_id)
        if row is None or any(row[field] != value for field, value in normalized_scope.items()):
            raise ValueError("decision operation scope mismatch")
        if row["status"] != "provider_completed":
            raise ValueError(f"decision recovery cannot claim status {row['status']}")
        active_recovery = (
            bool(row.get("recovery_owner"))
            and bool(row.get("recovery_lease_expires_at"))
            and _timestamp(row["recovery_lease_expires_at"]) > _timestamp(now)
        )
        if active_recovery:
            raise ValueError("decision recovery lease contention")
        recovery_generation = int(row["recovery_generation"]) + 1
        cursor = connection.execute(
            """
            UPDATE a2_decision_operations
            SET recovery_owner = ?, recovery_lease_expires_at = ?,
                recovery_generation = ?, updated_at = ?
            WHERE operation_id = ? AND status = 'provider_completed'
              AND recovery_generation = ?
            """,
            (
                worker_id, lease_expires_at, recovery_generation, now,
                operation_id, row["recovery_generation"],
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("decision recovery lease contention")
        _write_operation_audit(
            connection, operation_id, normalized_scope, "decision_recovery_claimed", now,
            {
                "provider_fencing_token": row["fencing_token"],
                "recovery_generation": recovery_generation,
            },
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "operation_id": operation_id,
        "worker_id": worker_id,
        "fencing_token": int(row["fencing_token"]),
        "recovery_generation": recovery_generation,
        "provider_call_id": row["provider_call_id"],
        "lease_expires_at": lease_expires_at,
    }


def load_decision_recovery_envelope(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
) -> dict[str, Any]:
    """Load and verify the canonical public-safe recovery input."""
    normalized_scope = _scope(scope)
    cursor = connection.execute(
        """
        SELECT o.provider_outcome_hash, p.outcome_hash, p.recovery_envelope_json,
               p.recovery_envelope_hash
        FROM a2_decision_operations o
        JOIN a2_provider_outcomes p ON p.operation_id = o.operation_id
        WHERE o.operation_id = ?
          AND o.organization_id = ? AND o.tenant_id = ? AND o.workspace_id = ?
          AND o.project_id = ? AND o.environment_id = ?
          AND p.organization_id = o.organization_id AND p.tenant_id = o.tenant_id
          AND p.workspace_id = o.workspace_id AND p.project_id = o.project_id
          AND p.environment_id = o.environment_id
        """,
        (
            operation_id, normalized_scope["organization_id"], normalized_scope["tenant_id"],
            normalized_scope["workspace_id"], normalized_scope["project_id"],
            normalized_scope["environment_id"],
        ),
    )
    row = _row_dict(cursor)
    if row is None or row["provider_outcome_hash"] != row["outcome_hash"]:
        raise ValueError("provider outcome recovery binding mismatch")
    try:
        envelope = json.loads(row["recovery_envelope_json"])
    except (TypeError, ValueError) as exc:
        raise ValueError("recovery envelope is not canonical JSON") from exc
    if not isinstance(envelope, dict) or stable_hash(envelope) != row["recovery_envelope_hash"]:
        raise ValueError("recovery envelope hash mismatch")
    if envelope.get("schema_version") != "a2.normalized_decision_envelope.v1":
        raise ValueError("unsupported recovery envelope schema")
    if envelope.get("recovery_supported") is not True:
        raise ValueError("provider outcome does not contain a recoverable envelope")
    _validate_recovery_envelope(envelope, normalized_scope)
    if envelope.get("provider_outcome_hash") != row["outcome_hash"]:
        raise ValueError("recovery envelope outcome hash mismatch")
    return envelope


def mark_operation_recovery_required(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    created_at: str,
    lease: dict[str, Any] | None = None,
) -> None:
    """Mark an uncertain external-call window for explicit recovery."""
    normalized_scope = _scope(scope)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _operation_by_id(connection, operation_id)
        if row is None or any(row[field] != value for field, value in normalized_scope.items()):
            raise ValueError("decision operation scope mismatch")
        if row["status"] == "committed":
            connection.commit()
            return
        if lease is not None:
            _assert_fence(row, normalized_scope, lease, "provider_running")
        connection.execute(
            """UPDATE a2_decision_operations SET status = 'recovery_required',
               lease_expires_at = ?, updated_at = ? WHERE operation_id = ?""",
            (created_at, created_at, operation_id),
        )
        _write_operation_audit(
            connection, operation_id, normalized_scope, "recovery_required", created_at,
            {"request_hash": row["request_hash"], "snapshot_hash": row["snapshot_hash"]},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def persist_release_decision(
    connection: sqlite3.Connection,
    result: dict[str, Any],
    *,
    idempotency_key: str,
    request_hash: str,
    operation_id: str | None = None,
    lease: dict[str, Any] | None = None,
    commit_now: str | None = None,
    failure_injector: FailureInjector | None = None,
) -> dict[str, Any]:
    """Atomically commit one decision and its mandatory audit event."""
    snapshot = _dict(result.get("evidence_snapshot"), "evidence snapshot")
    provenance = _dict(result.get("provider_provenance"), "provider provenance")
    judge = _dict(result.get("judge_result"), "judge result")
    gate = _dict(result.get("release_gate"), "release gate")
    ledger = _dict(result.get("decision_ledger"), "decision ledger")
    records = ledger.get("records")
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise ValueError("decision ledger must contain exactly one record")
    record = records[0]
    scope = _scope(record)
    _assert_scope(snapshot, scope, "evidence snapshot")
    _assert_scope(ledger, scope, "decision ledger")
    rebuilt = build_decision_ledger(
        [record],
        ledger_id=str(ledger.get("ledger_id") or ""),
        **scope,
        created_at=str(ledger.get("created_at") or ""),
    )
    if rebuilt.get("ledger_hash") != ledger.get("ledger_hash"):
        raise ValueError("decision ledger hash mismatch")
    if record.get("previous_record_hash") != GENESIS_HASH:
        raise ValueError("single-record decision must link to genesis")

    cursor = connection.execute(
        """
        SELECT record_id, request_hash, snapshot_hash, record_hash, decision
        FROM a2_release_decisions
        WHERE tenant_id = ? AND project_id = ? AND idempotency_key = ?
        """,
        (scope["tenant_id"], scope["project_id"], idempotency_key),
    )
    row = cursor.fetchone()
    existing = dict(zip((item[0] for item in cursor.description), row)) if row is not None else None
    if existing is not None:
        if existing["request_hash"] != request_hash or existing["snapshot_hash"] != snapshot.get("snapshot_hash"):
            raise IdempotencyConflictError("idempotency key reused with different decision input")
        if existing["record_hash"] != record.get("record_hash"):
            raise IdempotencyConflictError("idempotency key reused with different decision output")
        return _committed_summary(existing, idempotent_replay=True)

    injector = failure_injector or (lambda _: None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if operation_id is not None:
            operation = _operation_by_id(connection, operation_id)
            if operation is None or any(operation[field] != value for field, value in scope.items()):
                raise ValueError("decision operation scope mismatch")
            if operation["request_hash"] != request_hash or operation["snapshot_hash"] != snapshot["snapshot_hash"]:
                raise IdempotencyConflictError("decision operation input changed before commit")
            if operation["status"] != "provider_completed":
                raise ValueError(f"decision operation cannot commit from status {operation['status']}")
            if lease is None:
                raise ValueError("decision operation lease is required")
            if "recovery_generation" in lease:
                _assert_recovery_fence(operation, scope, lease, commit_now)
            else:
                _assert_fence(operation, scope, lease, "provider_completed")
        connection.execute(
            """
            INSERT INTO a2_release_decisions (
              record_id, idempotency_key, organization_id, tenant_id, workspace_id,
              project_id, environment_id, run_id, case_id, scenario_id, decision,
              review_required, snapshot_id, snapshot_hash, provider_provenance_hash,
              judge_result_hash, release_gate_hash, previous_record_hash, record_hash,
              ledger_id, ledger_hash, request_hash, created_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                record["record_id"], idempotency_key, scope["organization_id"], scope["tenant_id"],
                scope["workspace_id"], scope["project_id"], scope["environment_id"],
                record["run_id"], record["case_id"], record["scenario_id"], record["decision"],
                1 if record.get("review_required") else 0, snapshot["snapshot_id"],
                snapshot["snapshot_hash"], stable_hash(provenance), stable_hash(judge),
                stable_hash(gate), record["previous_record_hash"], record["record_hash"],
                ledger["ledger_id"], ledger["ledger_hash"], request_hash, record["created_at"],
            ),
        )
        injector("after_decision")
        audit = {
            "record_id": record["record_id"],
            "tenant_id": scope["tenant_id"],
            "project_id": scope["project_id"],
            "event_type": "release_decision_committed",
            "record_hash": record["record_hash"],
            "ledger_hash": ledger["ledger_hash"],
        }
        connection.execute(
            """
            INSERT INTO a2_release_decision_audit (
              audit_id, record_id, tenant_id, project_id, event_type, event_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stable_hash(audit), record["record_id"], scope["tenant_id"], scope["project_id"],
                audit["event_type"], stable_hash(audit), record["created_at"],
            ),
        )
        injector("after_audit")
        if operation_id is not None:
            cursor = connection.execute(
                """
                UPDATE a2_decision_operations
                SET status = 'committed', record_id = ?, record_hash = ?, decision = ?,
                    lease_owner = NULL, lease_expires_at = NULL,
                    recovery_owner = NULL, recovery_lease_expires_at = NULL, updated_at = ?
                WHERE operation_id = ? AND (
                  (recovery_owner = ? AND recovery_generation = ? AND fencing_token = ?)
                  OR
                  (recovery_owner IS NULL AND lease_owner = ? AND fencing_token = ?)
                )
                """,
                (
                    record["record_id"], record["record_hash"], record["decision"], record["created_at"],
                    operation_id,
                    lease["worker_id"], lease.get("recovery_generation", -1), lease["fencing_token"],
                    lease["worker_id"], lease["fencing_token"],
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("stale fencing token")
            _write_operation_audit(
                connection, operation_id, scope, "decision_committed", record["created_at"],
                {"record_hash": record["record_hash"], "ledger_hash": ledger["ledger_hash"]},
            )
            outbox_payload = {
                **scope,
                "operation_id": operation_id,
                "record_id": record["record_id"],
                "record_hash": record["record_hash"],
                "ledger_id": ledger["ledger_id"],
                "ledger_hash": ledger["ledger_hash"],
                "provider_outcome_hash": operation["provider_outcome_hash"],
                "decision": record["decision"],
                "review_required": bool(record.get("review_required")),
                "release_ready": record["decision"] == "allow",
            }
            event_id = stable_hash({"event_type": "a2.release_decision.committed.v1", **outbox_payload})
            connection.execute(
                """
                INSERT INTO a2_decision_outbox (
                  event_id, event_type, operation_id, record_id, organization_id, tenant_id,
                  workspace_id, project_id, environment_id, schema_version, payload_hash,
                  record_hash, ledger_hash, provider_outcome_hash, delivery_status,
                  available_at, created_at, public_safe
                ) VALUES (?, 'a2.release_decision.committed.v1', ?, ?, ?, ?, ?, ?, ?,
                          'ashr.event_envelope.v1', ?, ?, ?, ?, 'pending', ?, ?, 1)
                """,
                (
                    event_id, operation_id, record["record_id"], scope["organization_id"],
                    scope["tenant_id"], scope["workspace_id"], scope["project_id"],
                    scope["environment_id"], stable_hash(outbox_payload), record["record_hash"],
                    ledger["ledger_hash"], operation["provider_outcome_hash"],
                    record["created_at"], record["created_at"],
                ),
            )
            injector("after_outbox")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "committed": True,
        "idempotent_replay": False,
        "record_id": record["record_id"],
        "record_hash": record["record_hash"],
        "decision": record["decision"],
    }


def claim_decision_outbox(
    connection: sqlite3.Connection,
    *,
    worker_id: str,
    now: str,
    lease_seconds: int = 60,
) -> dict[str, Any] | None:
    """Claim one due A3 event with a monotonic delivery fencing generation."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    lease_expires_at = (
        _timestamp(now) + timedelta(seconds=lease_seconds)
    ).isoformat().replace("+00:00", "Z")
    try:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            SELECT * FROM a2_decision_outbox
            WHERE (
              delivery_status IN ('pending', 'retry')
              OR (delivery_status = 'leased' AND lease_expires_at <= ?)
            ) AND available_at <= ?
            ORDER BY created_at, event_id
            LIMIT 1
            """,
            (now, now),
        )
        row = _row_dict(cursor)
        if row is None:
            connection.commit()
            return None
        generation = int(row["lease_generation"]) + 1
        updated = connection.execute(
            """
            UPDATE a2_decision_outbox
            SET delivery_status = 'leased', lease_owner = ?, lease_generation = ?,
                lease_expires_at = ?, attempt_count = attempt_count + 1
            WHERE event_id = ? AND lease_generation = ?
            """,
            (worker_id, generation, lease_expires_at, row["event_id"], row["lease_generation"]),
        )
        if updated.rowcount != 1:
            raise ValueError("outbox claim contention")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    row.update(
        lease_owner=worker_id,
        lease_generation=generation,
        lease_expires_at=lease_expires_at,
        attempt_count=int(row["attempt_count"]) + 1,
        delivery_status="leased",
    )
    return row


def settle_decision_outbox(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    worker_id: str,
    lease_generation: int,
    delivered_at: str,
    outcome: str,
    retry_at: str | None = None,
    error_class: str | None = None,
) -> None:
    """Settle a claimed event without allowing a stale dispatcher to overwrite state."""
    if outcome not in {"delivered", "retry", "dead"}:
        raise ValueError("outbox outcome must be delivered, retry, or dead")
    if outcome == "retry" and not retry_at:
        raise ValueError("retry_at is required for retry")
    available_at = retry_at or delivered_at
    final_delivered_at = delivered_at if outcome == "delivered" else None
    cursor = connection.execute(
        """
        UPDATE a2_decision_outbox
        SET delivery_status = ?, available_at = ?, delivered_at = ?,
            last_error_class = ?, lease_owner = NULL, lease_expires_at = NULL
        WHERE event_id = ? AND delivery_status = 'leased'
          AND lease_owner = ? AND lease_generation = ?
        """,
        (
            outcome, available_at, final_delivered_at, error_class,
            event_id, worker_id, lease_generation,
        ),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise ValueError("stale outbox fencing generation")
    connection.commit()


def _scope(payload: dict[str, Any]) -> dict[str, str]:
    fields = ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
    scope = {field: str(payload.get(field) or "") for field in fields}
    if not all(scope.values()):
        raise ValueError("complete five-field tenant scope is required")
    return scope


def _operation_row(
    connection: sqlite3.Connection,
    scope: dict[str, str],
    idempotency_key: str,
) -> dict[str, Any] | None:
    cursor = connection.execute(
        """
        SELECT * FROM a2_decision_operations
        WHERE organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ? AND idempotency_key = ?
        """,
        (
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
            idempotency_key,
        ),
    )
    return _row_dict(cursor)


def _operation_by_id(connection: sqlite3.Connection, operation_id: str) -> dict[str, Any] | None:
    cursor = connection.execute(
        "SELECT * FROM a2_decision_operations WHERE operation_id = ?",
        (operation_id,),
    )
    return _row_dict(cursor)


def _row_dict(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip((item[0] for item in cursor.description), row))


def _operation_summary(row: dict[str, Any], *, replay: bool) -> dict[str, Any]:
    return {
        "operation_id": row["operation_id"],
        "status": row["status"],
        "replay": replay,
        "provider_call_allowed": False,
        "record_id": row.get("record_id"),
        "record_hash": row.get("record_hash"),
        "decision": row.get("decision"),
    }


def _write_operation_audit(
    connection: sqlite3.Connection,
    operation_id: str,
    scope: dict[str, str],
    event_type: str,
    created_at: str,
    details: dict[str, Any],
) -> None:
    event = {
        "operation_id": operation_id,
        "tenant_id": scope["tenant_id"],
        "project_id": scope["project_id"],
        "event_type": event_type,
        **details,
    }
    connection.execute(
        """
        INSERT INTO a2_decision_operation_audit (
          audit_id, operation_id, tenant_id, project_id, event_type, event_hash, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stable_hash(event), operation_id, scope["tenant_id"], scope["project_id"],
            event_type, stable_hash(event), created_at,
        ),
    )


def _assert_scope(payload: dict[str, Any], expected: dict[str, str], label: str) -> None:
    if _scope(payload) != expected:
        raise ValueError(f"{label} five-field scope mismatch")


def _dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} is required")
    return value


def _committed_summary(row: dict[str, Any], *, idempotent_replay: bool) -> dict[str, Any]:
    return {
        "committed": True,
        "idempotent_replay": idempotent_replay,
        "record_id": row["record_id"],
        "record_hash": row["record_hash"],
        "decision": row["decision"],
    }


def _assert_fence(
    row: dict[str, Any] | None,
    scope: dict[str, str],
    lease: dict[str, Any],
    expected_status: str,
) -> None:
    if row is None or any(row[field] != value for field, value in scope.items()):
        raise ValueError("decision operation scope mismatch")
    if row["status"] != expected_status:
        raise ValueError(f"decision operation expected {expected_status}, got {row['status']}")
    if row["lease_owner"] != lease["worker_id"] or int(row["fencing_token"]) != int(lease["fencing_token"]):
        raise ValueError("stale fencing token")


def _assert_recovery_fence(
    row: dict[str, Any] | None,
    scope: dict[str, str],
    lease: dict[str, Any],
    commit_now: str | None,
) -> None:
    if row is None or any(row[field] != value for field, value in scope.items()):
        raise ValueError("decision operation scope mismatch")
    if row["status"] != "provider_completed":
        raise ValueError(
            f"decision operation expected provider_completed, got {row['status']}"
        )
    if int(row["fencing_token"]) != int(lease["fencing_token"]):
        raise ValueError("provider outcome generation mismatch")
    if (
        row["recovery_owner"] != lease["worker_id"]
        or int(row["recovery_generation"]) != int(lease["recovery_generation"])
    ):
        raise ValueError("stale recovery generation")
    if commit_now is None:
        raise ValueError("recovery commit time is required")
    if (
        not row.get("recovery_lease_expires_at")
        or _timestamp(row["recovery_lease_expires_at"]) <= _timestamp(commit_now)
    ):
        raise ValueError("recovery lease expired")


def _assert_reconciliation_fence(
    row: dict[str, Any] | None,
    scope: dict[str, str],
    lease: dict[str, Any],
    observed_at: str,
) -> None:
    if row is None or any(row[field] != value for field, value in scope.items()):
        raise ValueError("decision operation scope mismatch")
    if row["status"] != "recovery_required":
        raise ValueError(f"decision operation expected recovery_required, got {row['status']}")
    if (
        row["reconciliation_owner"] != lease["worker_id"]
        or int(row["reconciliation_generation"]) != int(lease["reconciliation_generation"])
        or int(row["fencing_token"]) != int(lease["fencing_token"])
    ):
        raise ValueError("stale provider reconciliation fence")
    if (
        not row.get("reconciliation_lease_expires_at")
        or _timestamp(row["reconciliation_lease_expires_at"]) <= _timestamp(observed_at)
    ):
        raise ValueError("provider reconciliation lease expired")


def _reconciliation_record(
    operation_id: str,
    scope: dict[str, str],
    lease: dict[str, Any],
    observation: dict[str, Any],
    observed_at: str,
    next_reconcile_at: str | None,
) -> dict[str, Any]:
    status = str(observation.get("status") or "")
    allowed = {
        "remote_completed", "remote_pending", "remote_not_found",
        "remote_unknown", "reconciliation_unsupported",
    }
    if status not in allowed:
        raise ValueError("unsupported provider reconciliation status")
    if observation.get("retry_authorized") is not False or observation.get("public_safe") is not True:
        raise ValueError("provider reconciliation must remain public-safe and retry-closed")
    normalized_output = observation.get("normalized_output")
    if status != "remote_completed" and normalized_output is not None:
        raise ValueError("non-completed reconciliation cannot contain normalized output")
    normalized_json = (
        json.dumps(normalized_output, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if normalized_output is not None else None
    )
    identity = {
        "operation_id": operation_id,
        "provider_call_id": lease["provider_call_id"],
        "provider_fencing_token": lease["fencing_token"],
        "reconciliation_generation": lease["reconciliation_generation"],
        "provider_id": lease["provider_id"],
        "model_id": lease["model_id"],
        "logical_call_id": lease["logical_call_id"],
        "snapshot_hash": lease["snapshot_hash"],
        "payload_hash": lease["payload_hash"],
        "idempotency_key_hash": lease["idempotency_key_hash"],
        "provider_endpoint_hash": lease["provider_endpoint_hash"],
    }
    for field, expected in identity.items():
        if observation.get(field) != expected and field not in {"provider_fencing_token", "reconciliation_generation"}:
            raise ValueError(f"provider reconciliation {field} mismatch")
    safe_observation = {
        **identity,
        "status": status,
        "output_hash": observation.get("output_hash"),
        "normalized_output_hash": stable_hash(normalized_output) if normalized_output is not None else None,
        "observed_at": observed_at,
        "next_reconcile_at": next_reconcile_at,
        "retry_authorized": False,
    }
    observation_hash = stable_hash(safe_observation)
    return {
        "observation_id": stable_hash({"operation_id": operation_id, "observation_hash": observation_hash}),
        **scope,
        **safe_observation,
        "query_hash": stable_hash(identity),
        "normalized_output_json": normalized_json,
        "observation_hash": observation_hash,
        "public_safe": True,
    }


def _insert_reconciliation_observation(
    connection: sqlite3.Connection,
    record: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO a2_provider_reconciliation_observations (
          observation_id, operation_id, organization_id, tenant_id, workspace_id,
          project_id, environment_id, provider_call_id, provider_fencing_token,
          reconciliation_generation, provider_id, model_id, logical_call_id,
          snapshot_hash, payload_hash, idempotency_key_hash, query_hash, status,
          output_hash, normalized_output_json, normalized_output_hash, observation_hash,
          retry_authorized, observed_at, next_reconcile_at, public_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 1)
        """,
        (
            record["observation_id"], record["operation_id"], record["organization_id"],
            record["tenant_id"], record["workspace_id"], record["project_id"],
            record["environment_id"], record["provider_call_id"], record["provider_fencing_token"],
            record["reconciliation_generation"], record["provider_id"], record["model_id"],
            record["logical_call_id"], record["snapshot_hash"], record["payload_hash"],
            record["idempotency_key_hash"], record["query_hash"], record["status"],
            record["output_hash"], record["normalized_output_json"], record["normalized_output_hash"],
            record["observation_hash"], record["observed_at"], record["next_reconcile_at"],
        ),
    )


def _validate_recovery_envelope(
    envelope: dict[str, Any],
    scope: dict[str, str],
) -> None:
    unsupported_fields = {
        "schema_version", *scope.keys(), "provider_outcome_hash",
        "public_safe", "recovery_supported",
    }
    if set(envelope) == unsupported_fields and envelope.get("recovery_supported") is False:
        if envelope.get("schema_version") != "a2.normalized_decision_envelope.v1":
            raise ValueError("unsupported recovery envelope schema")
        _assert_scope(envelope, scope, "recovery envelope")
        if envelope.get("public_safe") is not True:
            raise ValueError("recovery envelope public_safe must be true")
        return
    supported_top = {
        "schema_version", *scope.keys(), "idempotency_key", "request_hash", "snapshot",
        "provider", "provider_provenance", "semantic_output", "citation_validation",
        "bundle_verification", "evaluation_quality",
        "policy_version", "ledger_id", "judge_version", "builder_version", "created_at",
        "provider_outcome_hash", "public_safe", "recovery_supported",
        "raw_provider_payload_included", "raw_evidence_included",
        "free_text_reason_included", "secrets_included",
    }
    _assert_exact_keys(envelope, supported_top, "recovery envelope")
    if envelope.get("schema_version") != "a2.normalized_decision_envelope.v1":
        raise ValueError("unsupported recovery envelope schema")
    _assert_scope(envelope, scope, "recovery envelope")
    for flag in (
        "public_safe", "recovery_supported",
    ):
        if envelope.get(flag) is not True:
            raise ValueError(f"recovery envelope {flag} must be true")
    for flag in (
        "raw_provider_payload_included", "raw_evidence_included",
        "free_text_reason_included", "secrets_included",
    ):
        if envelope.get(flag) is not False:
            raise ValueError(f"recovery envelope {flag} must be false")
    _assert_exact_keys(
        _dict(envelope.get("provider"), "recovery provider"),
        {
            "provider_id", "model_id", "status", "logical_call_id", "response_hash",
            "blockers", "release_authority",
        },
        "recovery provider",
    )
    _assert_exact_keys(
        _dict(envelope.get("bundle_verification"), "bundle verification"),
        {"manifest_authenticated", "authenticated_bundle_digest"},
        "bundle verification",
    )
    quality = _dict(envelope.get("evaluation_quality"), "evaluation quality")
    _assert_exact_keys(
        quality,
        {
            "schema_version", "proof_status", "issuer", "key_id_hash", "proof_hash",
            "calibration", "golden_regression", "disagreement", "human_review_required",
            "evidence_refs", "blockers", "public_safe",
        },
        "evaluation quality",
    )
    if quality.get("schema_version") != "a2.evaluation_quality.v2" or quality.get("public_safe") is not True:
        raise ValueError("evaluation quality contract is invalid")
    if quality.get("proof_status") not in {"verified", "invalid"}:
        raise ValueError("evaluation quality proof status is invalid")
    if not isinstance(quality.get("issuer"), str):
        raise ValueError("evaluation quality issuer is invalid")
    for field in ("key_id_hash", "proof_hash"):
        value = quality.get(field)
        if not isinstance(value, str) or (value and _SHA256_REF.fullmatch(value) is None):
            raise ValueError(f"evaluation quality {field} is invalid")
    if quality.get("calibration") not in {"passed", "failed", "missing"}:
        raise ValueError("evaluation quality calibration status is invalid")
    if quality.get("golden_regression") not in {"passed", "failed", "missing"}:
        raise ValueError("evaluation quality regression status is invalid")
    if quality.get("disagreement") not in {"agree", "disagree", "reviewed", "unknown"}:
        raise ValueError("evaluation quality disagreement status is invalid")
    if not isinstance(quality.get("human_review_required"), bool):
        raise ValueError("evaluation quality review state is invalid")
    if not isinstance(quality.get("evidence_refs"), list) or not all(
        isinstance(item, str) and _SHA256_REF.fullmatch(item) is not None
        for item in quality["evidence_refs"]
    ):
        raise ValueError("evaluation quality evidence refs are invalid")
    if not isinstance(quality.get("blockers"), list) or not all(
        isinstance(item, str) for item in quality["blockers"]
    ):
        raise ValueError("evaluation quality blockers are invalid")
    semantic = envelope.get("semantic_output")
    citation_validation = _dict(
        envelope.get("citation_validation"),
        "recovery citation validation",
    )
    _assert_exact_keys(
        citation_validation,
        {"status", "reference_hashes", "blockers", "public_safe"},
        "recovery citation validation",
    )
    if citation_validation.get("status") not in {"not_available", "grounded", "invalid"}:
        raise ValueError("recovery citation validation status is invalid")
    if citation_validation.get("public_safe") is not True:
        raise ValueError("recovery citation validation public_safe must be true")
    reference_hashes = citation_validation.get("reference_hashes")
    blockers = citation_validation.get("blockers")
    if not isinstance(reference_hashes, list) or not all(
        isinstance(item, str) and item.startswith("sha256:")
        for item in reference_hashes
    ):
        raise ValueError("recovery citation reference hashes are invalid")
    if not isinstance(blockers, list) or not all(isinstance(item, str) for item in blockers):
        raise ValueError("recovery citation blockers are invalid")
    status = citation_validation["status"]
    if semantic is None:
        if status != "not_available" or reference_hashes or blockers:
            raise ValueError("recovery citation state is inconsistent with absent semantic output")
    elif status == "not_available":
        raise ValueError("recovery citation state is inconsistent with semantic output")
    elif status == "grounded" and blockers:
        raise ValueError("grounded recovery citations cannot contain blockers")
    elif status == "invalid" and not blockers:
        raise ValueError("invalid recovery citations require blockers")
    if semantic is not None:
        semantic = _dict(semantic, "recovery semantic output")
        _assert_exact_keys(
            semantic,
            {"passed", "score", "failure_classes", "evidence_ref_hashes", "abstained"},
            "recovery semantic output",
        )
        score = semantic.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("recovery semantic score must be numeric")
        if not math.isfinite(float(score)) or not 0 <= float(score) <= 1:
            raise ValueError("recovery semantic score must be finite and between 0 and 1")
        if semantic.get("evidence_ref_hashes") != reference_hashes:
            raise ValueError("recovery semantic citation hashes do not match validation")
    _scan_public_safe_value(envelope)


def _assert_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ValueError(f"{label} fields do not match the governed schema")


def _scan_public_safe_value(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {
                "reason", "output_text", "prompt", "raw_request", "raw_response",
                "filename", "local_path", "signed_url", "object_key", "private_evidence_ref",
                "api_key", "authorization", "headers", "stack_trace",
            }:
                raise ValueError("recovery envelope contains forbidden field")
            _scan_public_safe_value(item)
    elif isinstance(value, list):
        for item in value:
            _scan_public_safe_value(item)
    elif isinstance(value, str) and _SECRET_OR_LOCATION.search(value):
        raise ValueError("recovery envelope contains secret or location-like text")


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
