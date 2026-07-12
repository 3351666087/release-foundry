"""Atomic public-safe persistence for A2 release decisions."""

from __future__ import annotations

import sqlite3
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
) -> None:
    """Durably authorize one provider call before handing control to the gateway."""
    normalized_scope = _scope(scope)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _operation_by_id(connection, operation_id)
        if row is None or any(row[field] != value for field, value in normalized_scope.items()):
            raise ValueError("decision operation scope mismatch")
        if row["status"] != "reserved":
            raise ValueError(f"decision operation cannot evaluate from status {row['status']}")
        connection.execute(
            "UPDATE a2_decision_operations SET status = 'evaluating', updated_at = ? WHERE operation_id = ?",
            (created_at, operation_id),
        )
        _write_operation_audit(
            connection, operation_id, normalized_scope, "provider_call_authorized", created_at,
            {"request_hash": row["request_hash"], "snapshot_hash": row["snapshot_hash"]},
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def mark_operation_recovery_required(
    connection: sqlite3.Connection,
    *,
    operation_id: str,
    scope: dict[str, str],
    created_at: str,
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
        connection.execute(
            "UPDATE a2_decision_operations SET status = 'recovery_required', updated_at = ? WHERE operation_id = ?",
            (created_at, operation_id),
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
            if operation["status"] != "evaluating":
                raise ValueError(f"decision operation cannot commit from status {operation['status']}")
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
            connection.execute(
                """
                UPDATE a2_decision_operations
                SET status = 'committed', record_id = ?, record_hash = ?, decision = ?, updated_at = ?
                WHERE operation_id = ?
                """,
                (record["record_id"], record["record_hash"], record["decision"], record["created_at"], operation_id),
            )
            _write_operation_audit(
                connection, operation_id, scope, "decision_committed", record["created_at"],
                {"record_hash": record["record_hash"], "ledger_hash": ledger["ledger_hash"]},
            )
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
