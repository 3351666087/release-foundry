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
              event_id, review_id, record_id, organization_id, tenant_id, workspace_id,
              project_id, environment_id, reviewer_id_hash,
              lease_generation, outcome, reason_code, superseding_record_id,
              event_hash, created_at, release_authority, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1)
            """,
            (
                event_id, row["review_id"], row["record_id"], normalized["organization_id"],
                normalized["tenant_id"], normalized["workspace_id"], normalized["project_id"],
                normalized["environment_id"], lease["reviewer_id_hash"],
                lease["lease_generation"], outcome, reason_code, superseding_record_id,
                event_hash, submitted_at,
            ),
        )
        resolution = _resolve_review(
            connection, row=row, event_id=event_id, outcome=outcome,
            superseding_record_id=superseding_record_id, submitted_at=submitted_at,
        )
        candidate = None
        learning_blocked_reason = None
        if resolution["status"] == "completed":
            _write_resolution(
                connection, row=row, scope=normalized, resolution_type="review_consensus",
                final_outcome=outcome, superseding_record_id=superseding_record_id,
                approval_count=resolution["approval_count"], resolved_at=submitted_at,
            )
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


def resolve_arbitration(
    connection: sqlite3.Connection,
    *,
    review_id: str,
    scope: dict[str, str],
    arbitrator_id_hash: str,
    arbitrator_role: str,
    final_outcome: str,
    resolved_at: str,
    superseding_record_id: str | None = None,
) -> dict[str, Any]:
    """Create the sole release-authoritative record for a conflicted review."""
    if arbitrator_role != "release_arbitrator" or not arbitrator_id_hash:
        raise ValueError("release_arbitrator role and identity are required")
    if final_outcome not in {"confirm", "overturn"}:
        raise ValueError("arbitration must conclusively confirm or overturn")
    normalized = _scope(scope)
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = _review(connection, review_id, normalized)
        if row["status"] != "arbitration":
            raise ValueError("review case is not awaiting arbitration")
        prior = connection.execute(
            "SELECT 1 FROM a2_review_events WHERE review_id = ? AND reviewer_id_hash = ?",
            (review_id, arbitrator_id_hash),
        ).fetchone()
        if prior is not None:
            raise ValueError("arbitrator must be independent from prior reviewers")
        if final_outcome == "overturn":
            if not superseding_record_id:
                raise ValueError("overturn requires a superseding decision reference")
            replacement = _decision(connection, superseding_record_id, normalized)
            if replacement["record_id"] == row["record_id"]:
                raise ValueError("superseding decision must be distinct")
        elif superseding_record_id is not None:
            raise ValueError("confirm cannot reference a superseding decision")
        count = connection.execute(
            "SELECT COUNT(*) FROM a2_review_events WHERE review_id = ?", (review_id,)
        ).fetchone()[0]
        resolution = _write_resolution(
            connection, row=row, scope=normalized, resolution_type="arbitration",
            final_outcome=final_outcome, superseding_record_id=superseding_record_id,
            approval_count=max(1, int(count)), resolved_at=resolved_at,
            arbitrator_id_hash=arbitrator_id_hash,
        )
        connection.execute(
            """
            UPDATE a2_review_cases
            SET status = 'completed', updated_at = ?
            WHERE review_id = ? AND status = 'arbitration'
            """,
            (resolved_at, review_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return resolution


def get_authoritative_review_resolution(
    connection: sqlite3.Connection,
    *,
    review_id: str,
    scope: dict[str, str],
) -> dict[str, Any] | None:
    """Return a release-consumable resolution, never an individual review event."""
    normalized = _scope(scope)
    review = _review(connection, review_id, normalized)
    if review["status"] != "completed":
        return None
    stored = connection.execute(
        "SELECT * FROM a2_review_resolutions WHERE review_id = ?", (review_id,)
    ).fetchone()
    if stored is None:
        return None
    value = dict(stored)
    if any(value[field] != expected for field, expected in normalized.items()):
        raise ValueError("review resolution scope mismatch")
    machine = _decision(connection, value["record_id"], normalized)
    if machine["record_hash"] != value["machine_record_hash"]:
        raise ValueError("review resolution machine decision hash mismatch")
    if machine["snapshot_hash"] != value["evidence_snapshot_hash"]:
        raise ValueError("review resolution evidence snapshot hash mismatch")
    if machine["release_gate_hash"] != value["policy_hash"]:
        raise ValueError("review resolution policy hash mismatch")
    if value["final_outcome"] == "overturn":
        replacement = _decision(connection, value["superseding_record_id"], normalized)
        if replacement["record_hash"] != value["superseding_record_hash"]:
            raise ValueError("review resolution superseding decision hash mismatch")
    core = _resolution_core(value)
    if stable_hash(core) != value["resolution_hash"]:
        raise ValueError("review resolution integrity mismatch")
    return {
        **core,
        "resolution_id": value["resolution_id"],
        "resolution_hash": value["resolution_hash"],
        "release_authority": True,
    }


def claim_review_resolution_outbox(
    connection: sqlite3.Connection,
    *,
    worker_id: str,
    now: str,
    lease_seconds: int = 60,
) -> dict[str, Any] | None:
    """Claim one committed review resolution with monotonic delivery fencing."""
    if not worker_id or lease_seconds <= 0:
        raise ValueError("worker identity and positive lease are required")
    expires = (_timestamp(now) + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute(
            """
            SELECT * FROM a2_review_resolution_outbox
            WHERE (
              delivery_status IN ('pending', 'retry')
              OR (delivery_status = 'leased' AND lease_expires_at <= ?)
            ) AND available_at <= ?
            ORDER BY created_at, event_id
            LIMIT 1
            """,
            (now, now),
        ).fetchone()
        if row is None:
            connection.commit()
            return None
        value = dict(row)
        generation = int(value["lease_generation"]) + 1
        cursor = connection.execute(
            """
            UPDATE a2_review_resolution_outbox
            SET delivery_status = 'leased', lease_owner = ?, lease_generation = ?,
                lease_expires_at = ?, attempt_count = attempt_count + 1
            WHERE event_id = ? AND lease_generation = ?
            """,
            (worker_id, generation, expires, value["event_id"], value["lease_generation"]),
        )
        if cursor.rowcount != 1:
            raise ValueError("review resolution outbox claim contention")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    value.update(
        delivery_status="leased", lease_owner=worker_id, lease_generation=generation,
        lease_expires_at=expires, attempt_count=int(value["attempt_count"]) + 1,
    )
    return value


def settle_review_resolution_outbox(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    worker_id: str,
    lease_generation: int,
    settled_at: str,
    outcome: str,
    retry_at: str | None = None,
    error_class: str | None = None,
) -> None:
    """Settle delivery without allowing stale workers to overwrite newer state."""
    if outcome not in {"delivered", "retry", "dead"}:
        raise ValueError("outbox outcome must be delivered, retry, or dead")
    if outcome == "retry" and not retry_at:
        raise ValueError("retry_at is required for retry")
    cursor = connection.execute(
        """
        UPDATE a2_review_resolution_outbox
        SET delivery_status = ?, available_at = ?, delivered_at = ?,
            last_error_class = ?, lease_owner = NULL, lease_expires_at = NULL
        WHERE event_id = ? AND delivery_status = 'leased'
          AND lease_owner = ? AND lease_generation = ?
        """,
        (
            outcome, retry_at or settled_at, settled_at if outcome == "delivered" else None,
            error_class, event_id, worker_id, lease_generation,
        ),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise ValueError("stale review resolution outbox fencing generation")
    connection.commit()


def build_review_resolution_handoff(
    connection: sqlite3.Connection,
    *,
    event_id: str,
    scope: dict[str, str],
) -> dict[str, Any]:
    """Build the metadata-only A3 payload for one committed outbox event."""
    normalized = _scope(scope)
    row = connection.execute(
        "SELECT * FROM a2_review_resolution_outbox WHERE event_id = ?", (event_id,)
    ).fetchone()
    if row is None:
        raise ValueError("review resolution outbox event not found")
    value = dict(row)
    if any(value[field] != expected for field, expected in normalized.items()):
        raise ValueError("review resolution outbox scope mismatch")
    resolution = get_authoritative_review_resolution(
        connection, review_id=value["review_id"], scope=normalized
    )
    if resolution is None or resolution["resolution_hash"] != value["resolution_hash"]:
        raise ValueError("review resolution outbox integrity mismatch")
    payload = _handoff_payload(resolution)
    if stable_hash(payload) != value["payload_hash"]:
        raise ValueError("review resolution outbox payload mismatch")
    return payload


def _write_resolution(
    connection: sqlite3.Connection,
    *,
    row: dict[str, Any],
    scope: dict[str, str],
    resolution_type: str,
    final_outcome: str,
    superseding_record_id: str | None,
    approval_count: int,
    resolved_at: str,
    arbitrator_id_hash: str | None = None,
) -> dict[str, Any]:
    machine = _decision(connection, row["record_id"], scope)
    replacement = (
        _decision(connection, superseding_record_id, scope)
        if superseding_record_id is not None else None
    )
    effective = replacement if final_outcome == "overturn" else machine
    core = {
        "review_id": row["review_id"], "record_id": row["record_id"], **scope,
        "resolution_type": resolution_type, "final_outcome": final_outcome,
        "superseding_record_id": superseding_record_id,
        "effective_record_id": effective["record_id"],
        "effective_decision": effective["decision"],
        "release_ready": effective["decision"] == "allow",
        "machine_record_hash": machine["record_hash"],
        "superseding_record_hash": replacement["record_hash"] if replacement else None,
        "evidence_snapshot_hash": machine["snapshot_hash"],
        "policy_hash": machine["release_gate_hash"],
        "approval_count": approval_count, "required_approvals": int(row["required_approvals"]),
        "arbitrator_id_hash": arbitrator_id_hash, "resolved_at": resolved_at,
    }
    resolution_hash = stable_hash(core)
    resolution_id = stable_hash({"review_id": row["review_id"], "resolution_hash": resolution_hash})
    connection.execute(
        """
        INSERT INTO a2_review_resolutions (
          resolution_id, review_id, record_id, organization_id, tenant_id, workspace_id,
          project_id, environment_id, resolution_type, final_outcome, superseding_record_id,
          effective_record_id, effective_decision, release_ready, machine_record_hash,
          superseding_record_hash, evidence_snapshot_hash, policy_hash, approval_count,
          required_approvals, arbitrator_id_hash, resolution_hash, resolved_at,
          release_authority, public_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
        """,
        (
            resolution_id, row["review_id"], row["record_id"], scope["organization_id"],
            scope["tenant_id"], scope["workspace_id"], scope["project_id"],
            scope["environment_id"], resolution_type, final_outcome, superseding_record_id,
            effective["record_id"], effective["decision"], int(effective["decision"] == "allow"),
            machine["record_hash"], replacement["record_hash"] if replacement else None,
            machine["snapshot_hash"], machine["release_gate_hash"], approval_count,
            row["required_approvals"], arbitrator_id_hash, resolution_hash, resolved_at,
        ),
    )
    resolution = {
        **core, "resolution_id": resolution_id, "resolution_hash": resolution_hash,
        "release_authority": True,
    }
    payload = _handoff_payload(resolution)
    event_id = stable_hash(
        {"event_type": "a2.review_resolution.committed.v1", "payload": payload}
    )
    connection.execute(
        """
        INSERT INTO a2_review_resolution_outbox (
          event_id, event_type, resolution_id, review_id, organization_id, tenant_id,
          workspace_id, project_id, environment_id, schema_version, payload_hash,
          resolution_hash, effective_record_id, effective_decision, release_ready,
          automatic_unblock, delivery_status, available_at, created_at, public_safe
        ) VALUES (?, 'a2.review_resolution.committed.v1', ?, ?, ?, ?, ?, ?, ?,
                  'a2.human_review_resolution.v1', ?, ?, ?, ?, ?, 0, 'pending', ?, ?, 1)
        """,
        (
            event_id, resolution_id, row["review_id"], scope["organization_id"],
            scope["tenant_id"], scope["workspace_id"], scope["project_id"],
            scope["environment_id"], stable_hash(payload), resolution_hash,
            effective["record_id"], effective["decision"],
            int(effective["decision"] == "allow"), resolved_at, resolved_at,
        ),
    )
    return resolution


def _handoff_payload(resolution: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "a2.human_review_resolution.v1",
        "event_type": "a2.review_resolution.committed.v1",
        "tenant_scope": {
            field: resolution[field]
            for field in (
                "organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"
            )
        },
        "resolution_id": resolution["resolution_id"],
        "resolution_hash": resolution["resolution_hash"],
        "review_id": resolution["review_id"],
        "resolution_type": resolution["resolution_type"],
        "final_outcome": resolution["final_outcome"],
        "machine_record_id": resolution["record_id"],
        "machine_record_hash": resolution["machine_record_hash"],
        "superseding_record_id": resolution["superseding_record_id"],
        "superseding_record_hash": resolution["superseding_record_hash"],
        "effective_record_id": resolution["effective_record_id"],
        "effective_decision": resolution["effective_decision"],
        "release_ready": bool(resolution["release_ready"]),
        "release_authority": True,
        "automatic_unblock": False,
        "evidence_snapshot_hash": resolution["evidence_snapshot_hash"],
        "policy_hash": resolution["policy_hash"],
        "approval_count": resolution["approval_count"],
        "required_approvals": resolution["required_approvals"],
        "resolved_at": resolution["resolved_at"],
        "raw_evidence_included": False,
        "review_reason_included": False,
    }


def _resolution_core(value: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "review_id", "record_id", "organization_id", "tenant_id", "workspace_id",
        "project_id", "environment_id", "resolution_type", "final_outcome",
        "superseding_record_id", "effective_record_id", "effective_decision", "release_ready",
        "machine_record_hash", "superseding_record_hash",
        "evidence_snapshot_hash", "policy_hash", "approval_count", "required_approvals",
        "arbitrator_id_hash", "resolved_at",
    )
    core = {field: value[field] for field in fields}
    core["release_ready"] = bool(core["release_ready"])
    return core


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
