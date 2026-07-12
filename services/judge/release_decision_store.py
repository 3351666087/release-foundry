"""Atomic public-safe persistence for A2 release decisions."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .result_persistence import stable_hash
from .trusted_spine import GENESIS_HASH, build_decision_ledger


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused for a different decision input."""


FailureInjector = Callable[[str], None]


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
) -> dict[str, Any]:
    """Reserve an idempotent operation before any external provider call."""
    if not idempotency_key:
        raise ValueError("idempotency key is required")
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
              provider_id, model_id, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)
            """,
            (
                operation_id, idempotency_key, normalized_scope["organization_id"],
                normalized_scope["tenant_id"], normalized_scope["workspace_id"],
                normalized_scope["project_id"], normalized_scope["environment_id"],
                request_hash, snapshot_id, snapshot_hash, provider_id, model_id,
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
        if row["status"] != "reserved" and not (
            row["status"] in {"provider_running", "recovery_required"} and expired
        ):
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
                provider_call_id = ?, updated_at = ?
            WHERE operation_id = ? AND fencing_token = ?
            """,
            (
                worker_id, lease_expires_at, fencing_token, provider_call_id,
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


def persist_provider_outcome(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    lease: dict[str, Any],
    provider_result: dict[str, Any],
    semantic_output: dict[str, Any],
    completed_at: str,
    failure_injector: FailureInjector | None = None,
) -> dict[str, str]:
    """Persist a hash-only Provider outcome under the current fencing token."""
    normalized_scope = _scope(scope)
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
              outcome_hash, completed_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                lease["provider_call_id"], operation_id, normalized_scope["organization_id"],
                normalized_scope["tenant_id"], normalized_scope["workspace_id"],
                normalized_scope["project_id"], normalized_scope["environment_id"],
                lease["fencing_token"], str(provider_result.get("provider_id") or ""),
                str(provider_result.get("model_id") or ""), str(provider_result.get("status") or "unknown"),
                outcome["response_hash"], outcome["semantic_output_hash"], outcome["usage_hash"],
                outcome_hash, completed_at,
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
    return {"provider_call_id": str(lease["provider_call_id"]), "outcome_hash": outcome_hash}


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
                    lease_owner = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE operation_id = ? AND lease_owner = ? AND fencing_token = ?
                """,
                (
                    record["record_id"], record["record_hash"], record["decision"], record["created_at"],
                    operation_id, lease["worker_id"], lease["fencing_token"],
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


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
