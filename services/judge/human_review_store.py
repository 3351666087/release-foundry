"""Durable, tenant-scoped human review and governed learning candidates."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .result_persistence import stable_hash


REVIEW_OUTCOMES = {"confirm", "overturn", "abstain", "escalate"}
LEARNING_PURPOSES = {"judge_calibration", "regression_generation", "failure_classification"}


def open_review_case(
    connection: sqlite3.Connection,
    *,
    scope: dict[str, str],
    record_id: str,
    reason_code: str,
    created_at: str,
    required_approvals: int = 1,
) -> dict[str, Any]:
    """Open one idempotent review case without copying private evidence."""
    if required_approvals not in {1, 2}:
        raise ValueError("required approvals must be one or two")
    normalized = _scope(scope)
    decision = _decision(connection, record_id, normalized)
    review_id = stable_hash({"record_id": record_id, "scope": normalized, "reason_code": reason_code})
    connection.execute(
        """
        INSERT OR IGNORE INTO a2_review_cases (
          review_id, record_id, organization_id, tenant_id, workspace_id, project_id,
          environment_id, machine_decision, machine_record_hash, reason_code, status,
          required_approvals, lease_generation, created_at, updated_at, public_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, 0, ?, ?, 1)
        """,
        (
            review_id, record_id, normalized["organization_id"], normalized["tenant_id"],
            normalized["workspace_id"], normalized["project_id"], normalized["environment_id"],
            decision["decision"], decision["record_hash"], reason_code, required_approvals,
            created_at, created_at,
        ),
    )
    connection.commit()
    row = _review(connection, review_id, normalized)
    if int(row["required_approvals"]) != required_approvals:
        raise ValueError("review case approval requirement conflicts with existing case")
    return {
        "review_id": review_id,
        "status": row["status"],
        "machine_decision": decision["decision"],
        "required_approvals": row["required_approvals"],
    }


def claim_review_case(
    connection: sqlite3.Connection,
    *,
    review_id: str,
    scope: dict[str, str],
    reviewer_id_hash: str,
    now: str,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    """Acquire a fenced reviewer lease; expired leases may be reclaimed."""
    if not reviewer_id_hash or lease_seconds <= 0:
        raise ValueError("reviewer identity hash and positive lease are required")
    normalized = _scope(scope)
    current = _timestamp(now)
    expires = (current + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = _review(connection, review_id, normalized)
        active = row["lease_expires_at"] and _timestamp(row["lease_expires_at"]) > current
        if row["status"] in {"completed", "arbitration"}:
            raise ValueError(f"review case is {row['status']}")
        if active:
            raise ValueError("review case lease contention")
        prior_vote = connection.execute(
            "SELECT 1 FROM a2_review_events WHERE review_id = ? AND reviewer_id_hash = ?",
            (review_id, reviewer_id_hash),
        ).fetchone()
        if prior_vote is not None:
            raise ValueError("reviewer has already submitted a disposition")
        generation = int(row["lease_generation"]) + 1
        cursor = connection.execute(
            """
            UPDATE a2_review_cases
            SET status = 'leased', lease_owner_hash = ?, lease_generation = ?,
                lease_expires_at = ?, updated_at = ?
            WHERE review_id = ? AND lease_generation = ?
            """,
            (reviewer_id_hash, generation, expires, now, review_id, row["lease_generation"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("review case lease contention")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "review_id": review_id,
        "reviewer_id_hash": reviewer_id_hash,
        "lease_generation": generation,
        "lease_expires_at": expires,
    }


def submit_review(
    connection: sqlite3.Connection,
    *,
    lease: dict[str, Any],
    scope: dict[str, str],
    outcome: str,
    reason_code: str,
    submitted_at: str,
    superseding_record_id: str | None = None,
    learning: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a disposition while preserving the original machine decision."""
    if outcome not in REVIEW_OUTCOMES:
        raise ValueError("unsupported review outcome")
    normalized = _scope(scope)
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = _review(connection, str(lease["review_id"]), normalized)
        if (
            row["status"] != "leased"
            or row["lease_owner_hash"] != lease["reviewer_id_hash"]
            or int(row["lease_generation"]) != int(lease["lease_generation"])
        ):
            raise ValueError("stale review lease")
        if not row["lease_expires_at"] or _timestamp(row["lease_expires_at"]) <= _timestamp(submitted_at):
            raise ValueError("review lease expired")
        if outcome == "overturn":
            if not superseding_record_id:
                raise ValueError("overturn requires a superseding decision reference")
            replacement = _decision(connection, superseding_record_id, normalized)
            if replacement["record_id"] == row["record_id"]:
                raise ValueError("superseding decision must be distinct")
        event_core = {
            "review_id": row["review_id"],
            "record_id": row["record_id"],
            "reviewer_id_hash": lease["reviewer_id_hash"],
            "lease_generation": lease["lease_generation"],
            "outcome": outcome,
            "reason_code": reason_code,
            "superseding_record_id": superseding_record_id,
            "submitted_at": submitted_at,
        }
        event_hash = stable_hash(event_core)
        event_id = stable_hash({"review_id": row["review_id"], "event_hash": event_hash})
        connection.execute(
            """
            INSERT INTO a2_review_events (
              event_id, review_id, record_id, tenant_id, project_id, reviewer_id_hash,
              lease_generation, outcome, reason_code, superseding_record_id,
              event_hash, created_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                event_id, row["review_id"], row["record_id"], normalized["tenant_id"],
                normalized["project_id"], lease["reviewer_id_hash"], lease["lease_generation"],
                outcome, reason_code, superseding_record_id, event_hash, submitted_at,
            ),
        )
        resolution = _resolve_review(
            connection, row=row, event_id=event_id, outcome=outcome,
            superseding_record_id=superseding_record_id, submitted_at=submitted_at,
        )
        candidate = None
        learning_blocked_reason = None
        if resolution["status"] == "completed":
            candidate = _create_learning_candidate(
                connection, row=row, event_id=event_id, scope=normalized,
                outcome=outcome, learning=learning, created_at=submitted_at,
            )
        elif learning is not None:
            learning_blocked_reason = "review_not_completed_or_conflict_requires_arbitration"
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "review_id": row["review_id"],
        "event_id": event_id,
        "outcome": outcome,
        "superseding_record_id": superseding_record_id,
        "status": resolution["status"],
        "approval_count": resolution["approval_count"],
        "disposition_count": resolution["disposition_count"],
        "learning_candidate": candidate,
        "learning_blocked_reason": learning_blocked_reason,
    }


def _resolve_review(
    connection: sqlite3.Connection,
    *,
    row: dict[str, Any],
    event_id: str,
    outcome: str,
    superseding_record_id: str | None,
    submitted_at: str,
) -> dict[str, Any]:
    events = [
        dict(item)
        for item in connection.execute(
            """
            SELECT outcome, superseding_record_id
            FROM a2_review_events
            WHERE review_id = ?
            ORDER BY created_at, event_id
            """,
            (row["review_id"],),
        ).fetchall()
    ]
    disposition_count = len(events)
    qualifying_events = [item for item in events if item["outcome"] in {"confirm", "overturn"}]
    approval_count = len(qualifying_events)
    required = int(row["required_approvals"])
    status = "open"
    final_event_id = None
    if disposition_count >= required:
        signatures = {(item["outcome"], item["superseding_record_id"]) for item in events}
        if approval_count == required and len(signatures) == 1:
            status = "completed"
            final_event_id = event_id
        else:
            status = "arbitration"
    connection.execute(
        """
        UPDATE a2_review_cases
        SET status = ?, lease_owner_hash = NULL, lease_expires_at = NULL,
            final_event_id = ?, updated_at = ?
        WHERE review_id = ? AND lease_generation = ?
        """,
        (status, final_event_id, submitted_at, row["review_id"], row["lease_generation"]),
    )
    return {
        "status": status,
        "approval_count": approval_count,
        "disposition_count": disposition_count,
    }


def _create_learning_candidate(
    connection: sqlite3.Connection,
    *,
    row: dict[str, Any],
    event_id: str,
    scope: dict[str, str],
    outcome: str,
    learning: dict[str, Any] | None,
    created_at: str,
) -> dict[str, Any] | None:
    if learning is None:
        return None
    required = {"consent_id_hash", "purpose", "lineage_hash", "residency", "retention_until", "deletion_key_hash"}
    if set(learning) != required or any(not learning[field] for field in required):
        raise ValueError("learning governance metadata is incomplete")
    if learning["purpose"] not in LEARNING_PURPOSES:
        raise ValueError("unsupported learning purpose")
    if outcome not in {"confirm", "overturn"}:
        raise ValueError("abstained or escalated reviews cannot become learning candidates")
    candidate_id = stable_hash({"event_id": event_id, "purpose": learning["purpose"]})
    connection.execute(
        """
        INSERT INTO a2_learning_candidates (
          candidate_id, review_event_id, record_id, organization_id, tenant_id,
          workspace_id, project_id, environment_id, consent_id_hash, purpose,
          lineage_hash, residency, retention_until, deletion_key_hash, status,
          cross_tenant_allowed, created_at, public_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'eligible', 0, ?, 1)
        """,
        (
            candidate_id, event_id, row["record_id"], scope["organization_id"], scope["tenant_id"],
            scope["workspace_id"], scope["project_id"], scope["environment_id"],
            learning["consent_id_hash"], learning["purpose"], learning["lineage_hash"],
            learning["residency"], learning["retention_until"], learning["deletion_key_hash"], created_at,
        ),
    )
    return {"candidate_id": candidate_id, "status": "eligible", "cross_tenant_allowed": False}


def _scope(scope: dict[str, str]) -> dict[str, str]:
    fields = ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
    normalized = {field: str(scope.get(field) or "") for field in fields}
    if any(not value for value in normalized.values()):
        raise ValueError("complete five-field tenant scope is required")
    return normalized


def _decision(connection: sqlite3.Connection, record_id: str, scope: dict[str, str]) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM a2_release_decisions WHERE record_id = ?", (record_id,)).fetchone()
    if row is None:
        raise ValueError("release decision not found")
    value = dict(row)
    if any(value[field] != expected for field, expected in scope.items()):
        raise ValueError("release decision scope mismatch")
    return value


def _review(connection: sqlite3.Connection, review_id: str, scope: dict[str, str]) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM a2_review_cases WHERE review_id = ?", (review_id,)).fetchone()
    if row is None:
        raise ValueError("review case not found")
    value = dict(row)
    if any(value[field] != expected for field, expected in scope.items()):
        raise ValueError("review case scope mismatch")
    return value


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
