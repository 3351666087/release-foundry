"""Atomic public-safe persistence for A2 release decisions."""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

from .result_persistence import stable_hash
from .trusted_spine import GENESIS_HASH, build_decision_ledger


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused for a different decision input."""


FailureInjector = Callable[[str], None]


def persist_release_decision(
    connection: sqlite3.Connection,
    result: dict[str, Any],
    *,
    idempotency_key: str,
    request_hash: str,
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
