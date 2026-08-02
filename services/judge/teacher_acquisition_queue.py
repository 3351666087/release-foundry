"""Durable, fenced queue for governed paid-teacher acquisition."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import re
import sqlite3
from typing import Any

from .result_persistence import canonical_json, stable_hash


QUEUE_STATUSES = {"pending", "leased", "retry", "completed", "dead", "blocked"}
SETTLEMENT_OUTCOMES = {"completed", "retry", "dead", "blocked"}
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SCOPE_FIELDS = (
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id",
)


class TeacherAcquisitionQueueError(ValueError):
    """Raised when a paid-teacher queue operation is unsafe or unverifiable."""


def enqueue_teacher_acquisition(
    connection: sqlite3.Connection,
    *,
    scope: dict[str, str],
    pair_id: str,
    teacher_id: str,
    request_hash: str,
    idempotency_key: str,
    priority_score: float,
    max_cost_usd: float,
    created_at: str,
    available_at: str | None = None,
    max_attempts: int = 1,
) -> dict[str, Any]:
    """Enqueue one teacher request with tenant-scoped paid-call deduplication."""
    normalized_scope = _scope(scope)
    _text(pair_id, "pair_id")
    _text(teacher_id, "teacher_id")
    _hash(request_hash, "request_hash")
    _text(idempotency_key, "idempotency_key")
    priority = _bounded_number(priority_score, "priority_score", maximum=100.0)
    budget = _nonnegative_number(max_cost_usd, "max_cost_usd")
    attempts = _positive_int(max_attempts, "max_attempts")
    created = _canonical_timestamp(created_at, "created_at")
    available = _canonical_timestamp(available_at or created_at, "available_at")
    idempotency_hash = stable_hash({"idempotency_key": idempotency_key})
    queue_id = stable_hash(
        {
            "scope": normalized_scope,
            "pair_id": pair_id,
            "teacher_id": teacher_id,
            "request_hash": request_hash,
            "idempotency_key_hash": idempotency_hash,
        }
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        existing = _find_by_idempotency(connection, normalized_scope, idempotency_hash)
        if existing is not None:
            if not _same_request(
                existing,
                pair_id=pair_id,
                teacher_id=teacher_id,
                request_hash=request_hash,
                priority_score=priority,
                max_cost_usd=budget,
                max_attempts=attempts,
            ):
                raise TeacherAcquisitionQueueError("idempotency_key_reuse_conflict")
            connection.commit()
            return _public_row(existing, idempotent_replay=True)
        connection.execute(
            """
            INSERT INTO a2_teacher_acquisition_queue (
              queue_id, pair_id, teacher_id, request_hash, idempotency_key_hash,
              organization_id, tenant_id, workspace_id, project_id, environment_id,
              priority_score, max_cost_usd, status, max_attempts, attempt_count,
              lease_generation, available_at, created_at, updated_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, 0, 0, ?, ?, ?, 1)
            """,
            (
                queue_id,
                pair_id,
                teacher_id,
                request_hash,
                idempotency_hash,
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
                priority,
                budget,
                attempts,
                available,
                created,
                created,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    row = _queue(connection, queue_id, normalized_scope)
    return _public_row(row, idempotent_replay=False)


def enqueue_preference_teacher_acquisition(
    connection: sqlite3.Connection,
    *,
    scope: dict[str, str],
    preference_pair: dict[str, Any],
    teacher_id: str,
    request_payload: dict[str, Any],
    max_cost_usd: float,
    created_at: str,
    available_at: str | None = None,
    max_attempts: int = 1,
) -> dict[str, Any]:
    """Queue one governed preference pair for a paid teacher.

    The pair remains provisional until human review or an explicitly allowed
    teacher-consensus path resolves it.  Only the request hash and derived
    idempotency material enter the durable queue; the request payload itself is
    never persisted here.
    """
    if not isinstance(preference_pair, dict):
        raise TeacherAcquisitionQueueError("preference_pair_must_be_object")
    if not isinstance(request_payload, dict):
        raise TeacherAcquisitionQueueError("request_payload_must_be_object")
    pair_id = preference_pair.get("pair_id")
    _hash(pair_id, "pair_id")
    status = preference_pair.get("status")
    if status not in {"provisional_preference", "review_required"}:
        raise TeacherAcquisitionQueueError("preference_pair_not_reviewable")
    if preference_pair.get("training_eligible") is not False:
        raise TeacherAcquisitionQueueError("preference_pair_training_state_invalid")
    if preference_pair.get("review_required") is not True:
        raise TeacherAcquisitionQueueError("preference_pair_review_required")
    provisional = preference_pair.get("releasefoundry_provisional_preference")
    if (
        not isinstance(provisional, dict)
        or not provisional.get("chosen_candidate_id")
        or not provisional.get("rejected_candidate_id")
        or provisional["chosen_candidate_id"] == provisional["rejected_candidate_id"]
    ):
        raise TeacherAcquisitionQueueError("preference_pair_provisional_direction_invalid")
    priority = preference_pair.get("active_learning")
    if not isinstance(priority, dict) or "score" not in priority:
        raise TeacherAcquisitionQueueError("preference_pair_active_learning_missing")
    request_hash = stable_hash(request_payload)
    idempotency_key = stable_hash(
        {
            "pair_id": pair_id,
            "teacher_id": teacher_id,
            "request_hash": request_hash,
        }
    )
    return enqueue_teacher_acquisition(
        connection,
        scope=scope,
        pair_id=pair_id,
        teacher_id=teacher_id,
        request_hash=request_hash,
        idempotency_key=idempotency_key,
        priority_score=priority["score"],
        max_cost_usd=max_cost_usd,
        created_at=created_at,
        available_at=available_at,
        max_attempts=max_attempts,
    )


def claim_teacher_acquisition(
    connection: sqlite3.Connection,
    *,
    scope: dict[str, str],
    worker_id: str,
    now: str,
    lease_seconds: int = 300,
) -> dict[str, Any] | None:
    """Claim the highest-priority due request with monotonic lease fencing."""
    normalized_scope = _scope(scope)
    _text(worker_id, "worker_id")
    current = _canonical_timestamp(now, "now")
    seconds = _positive_int(lease_seconds, "lease_seconds")
    expires = (
        _timestamp(current) + timedelta(seconds=seconds)
    ).isoformat().replace("+00:00", "Z")
    connection.execute("BEGIN IMMEDIATE")
    try:
        cursor = connection.execute(
            """
            SELECT *
            FROM a2_teacher_acquisition_queue
            WHERE organization_id = ? AND tenant_id = ? AND workspace_id = ?
              AND project_id = ? AND environment_id = ?
              AND attempt_count < max_attempts
              AND (
                (
                  status IN ('pending', 'retry')
                  AND julianday(available_at) <= julianday(?)
                )
                OR (
                  status = 'leased'
                  AND julianday(lease_expires_at) <= julianday(?)
                )
              )
            ORDER BY priority_score DESC, julianday(created_at) ASC, queue_id ASC
            LIMIT 1
            """,
            (
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
                current,
                current,
            ),
        )
        row = _row_dict(cursor)
        if row is None:
            connection.commit()
            return None
        generation = int(row["lease_generation"]) + 1
        updated = connection.execute(
            """
            UPDATE a2_teacher_acquisition_queue
            SET status = 'leased', lease_owner = ?, lease_generation = ?,
                lease_expires_at = ?, attempt_count = attempt_count + 1,
                updated_at = ?
            WHERE queue_id = ? AND lease_generation = ?
            """,
            (
                worker_id,
                generation,
                expires,
                current,
                row["queue_id"],
                row["lease_generation"],
            ),
        )
        if updated.rowcount != 1:
            raise TeacherAcquisitionQueueError("queue_claim_contention")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    row.update(
        status="leased",
        lease_owner=worker_id,
        lease_generation=generation,
        lease_expires_at=expires,
        attempt_count=int(row["attempt_count"]) + 1,
        updated_at=current,
    )
    return _public_row(row, idempotent_replay=False)


def settle_teacher_acquisition(
    connection: sqlite3.Connection,
    *,
    queue_id: str,
    scope: dict[str, str],
    worker_id: str,
    lease_generation: int,
    settled_at: str,
    outcome: str,
    receipt_hash: str | None = None,
    actual_cost_usd: float | None = None,
    retry_at: str | None = None,
    error_class: str | None = None,
) -> dict[str, Any]:
    """Settle one fenced request without allowing stale workers to overwrite it."""
    if outcome not in SETTLEMENT_OUTCOMES:
        raise TeacherAcquisitionQueueError("unsupported_queue_settlement")
    normalized_scope = _scope(scope)
    _text(queue_id, "queue_id")
    _text(worker_id, "worker_id")
    generation = _positive_int(lease_generation, "lease_generation")
    settled = _canonical_timestamp(settled_at, "settled_at")
    retry = _canonical_timestamp(retry_at, "retry_at") if retry_at else None
    if outcome == "retry" and retry is None:
        raise TeacherAcquisitionQueueError("retry_at_required_for_retry")
    if retry is not None and _timestamp(retry) <= _timestamp(settled):
        raise TeacherAcquisitionQueueError("retry_at_must_be_later_than_settled_at")
    if outcome == "completed":
        _hash(receipt_hash, "receipt_hash")
        if actual_cost_usd is None:
            raise TeacherAcquisitionQueueError("actual_cost_required_for_completion")
    cost = (
        _nonnegative_number(actual_cost_usd, "actual_cost_usd")
        if actual_cost_usd is not None
        else None
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = _queue(connection, queue_id, normalized_scope)
        if (
            row["status"] != "leased"
            or row["lease_owner"] != worker_id
            or int(row["lease_generation"]) != generation
        ):
            raise TeacherAcquisitionQueueError("stale_queue_fencing_generation")
        if cost is not None and cost > float(row["max_cost_usd"]):
            raise TeacherAcquisitionQueueError("actual_cost_exceeds_reserved_budget")
        effective_outcome = outcome
        effective_error = error_class
        available = retry or settled
        completed_at = settled if outcome == "completed" else None
        if outcome == "retry" and int(row["attempt_count"]) >= int(row["max_attempts"]):
            effective_outcome = "dead"
            effective_error = "max_attempts_exhausted"
            available = settled
        connection.execute(
            """
            UPDATE a2_teacher_acquisition_queue
            SET status = ?, actual_cost_usd = ?, receipt_hash = ?,
                available_at = ?, lease_owner = NULL, lease_expires_at = NULL,
                last_error_class = ?, completed_at = ?, updated_at = ?
            WHERE queue_id = ? AND status = 'leased'
              AND lease_owner = ? AND lease_generation = ?
            """,
            (
                effective_outcome,
                cost,
                receipt_hash,
                available,
                effective_error,
                completed_at,
                settled,
                queue_id,
                worker_id,
                generation,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    result = _queue(connection, queue_id, normalized_scope)
    return _public_row(result, idempotent_replay=False)


def settle_teacher_acquisition_with_public_receipt(
    connection: sqlite3.Connection,
    *,
    queue_id: str,
    scope: dict[str, str],
    worker_id: str,
    lease_generation: int,
    settled_at: str,
    verification_state: str,
    receipt_schema_version: str,
    receipt_hash: str,
    public_receipt: dict[str, Any],
    actual_cost_usd: float,
    error_class: str | None = None,
) -> dict[str, Any]:
    """Atomically record a redacted teacher receipt and settle its queue item.

    The durable store receives only the public receipt projection.  A verified
    projection completes the paid request; an incomplete or blocked projection
    terminates it as ``blocked`` so no training candidate can be inferred from
    an unverified provider response.  Replaying the same receipt is safe and
    does not mutate or charge the queue item a second time.
    """
    if verification_state not in {"verified", "blocked"}:
        raise TeacherAcquisitionQueueError("unsupported_receipt_verification_state")
    normalized_scope = _scope(scope)
    _text(queue_id, "queue_id")
    _text(worker_id, "worker_id")
    _positive_int(lease_generation, "lease_generation")
    settled = _canonical_timestamp(settled_at, "settled_at")
    _text(receipt_schema_version, "receipt_schema_version")
    _hash(receipt_hash, "receipt_hash")
    if not isinstance(public_receipt, dict):
        raise TeacherAcquisitionQueueError("public_receipt_must_be_object")
    if public_receipt.get("public_safe") is not True:
        raise TeacherAcquisitionQueueError("public_receipt_not_public_safe")
    if public_receipt.get("verification_state") != verification_state:
        raise TeacherAcquisitionQueueError("public_receipt_state_mismatch")
    cost = _nonnegative_number(actual_cost_usd, "actual_cost_usd")
    try:
        serialized_receipt = canonical_json(public_receipt)
    except (TypeError, ValueError) as exc:
        raise TeacherAcquisitionQueueError("public_receipt_not_json") from exc
    public_receipt_hash = stable_hash(public_receipt)
    receipt_id = stable_hash(
        {"queue_id": queue_id, "receipt_hash": receipt_hash}
    )

    connection.execute("BEGIN IMMEDIATE")
    try:
        row = _queue(connection, queue_id, normalized_scope)
        existing_receipt = _receipt_row(connection, queue_id, normalized_scope)
        if row["status"] != "leased":
            if existing_receipt is not None and _same_receipt(
                existing_receipt,
                receipt_id=receipt_id,
                receipt_hash=receipt_hash,
                public_receipt_hash=public_receipt_hash,
                verification_state=verification_state,
            ):
                connection.commit()
                return _public_row(row, idempotent_replay=True)
            raise TeacherAcquisitionQueueError("stale_queue_fencing_generation")
        if (
            row["lease_owner"] != worker_id
            or int(row["lease_generation"]) != int(lease_generation)
        ):
            raise TeacherAcquisitionQueueError("stale_queue_fencing_generation")
        if cost > float(row["max_cost_usd"]):
            raise TeacherAcquisitionQueueError("actual_cost_exceeds_reserved_budget")
        if row["request_hash"] != public_receipt.get("request_hash"):
            raise TeacherAcquisitionQueueError("receipt_request_hash_mismatch")
        if row["pair_id"] != public_receipt.get("pair_id"):
            raise TeacherAcquisitionQueueError("receipt_pair_id_mismatch")
        if row["teacher_id"] != public_receipt.get("teacher_id"):
            raise TeacherAcquisitionQueueError("receipt_teacher_id_mismatch")

        if existing_receipt is None:
            connection.execute(
                """
                INSERT INTO a2_teacher_acquisition_receipts (
                  receipt_id, queue_id, pair_id, teacher_id,
                  organization_id, tenant_id, workspace_id, project_id,
                  environment_id, request_hash, receipt_hash,
                  receipt_schema_version, verification_state,
                  public_receipt_json, public_receipt_hash,
                  created_at, public_safe
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    receipt_id,
                    queue_id,
                    row["pair_id"],
                    row["teacher_id"],
                    normalized_scope["organization_id"],
                    normalized_scope["tenant_id"],
                    normalized_scope["workspace_id"],
                    normalized_scope["project_id"],
                    normalized_scope["environment_id"],
                    row["request_hash"],
                    receipt_hash,
                    receipt_schema_version,
                    verification_state,
                    serialized_receipt,
                    public_receipt_hash,
                    settled,
                ),
            )
        elif not _same_receipt(
            existing_receipt,
            receipt_id=receipt_id,
            receipt_hash=receipt_hash,
            public_receipt_hash=public_receipt_hash,
            verification_state=verification_state,
        ):
            raise TeacherAcquisitionQueueError("receipt_reuse_conflict")

        outcome = "completed" if verification_state == "verified" else "blocked"
        effective_error = (
            error_class
            if error_class is not None
            else ("releasefoundry_receipt_blocked" if outcome == "blocked" else None)
        )
        connection.execute(
            """
            UPDATE a2_teacher_acquisition_queue
            SET status = ?, actual_cost_usd = ?, receipt_hash = ?,
                available_at = ?, lease_owner = NULL, lease_expires_at = NULL,
                last_error_class = ?, completed_at = ?, updated_at = ?
            WHERE queue_id = ? AND status = 'leased'
              AND lease_owner = ? AND lease_generation = ?
            """,
            (
                outcome,
                cost,
                receipt_hash,
                settled,
                effective_error,
                settled if outcome == "completed" else None,
                settled,
                queue_id,
                worker_id,
                lease_generation,
            ),
        )
        if connection.execute("SELECT changes()").fetchone()[0] != 1:
            raise TeacherAcquisitionQueueError("stale_queue_fencing_generation")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    result = _queue(connection, queue_id, normalized_scope)
    return _public_row(result, idempotent_replay=False)


def get_teacher_acquisition_receipt(
    connection: sqlite3.Connection,
    *,
    queue_id: str,
    scope: dict[str, str],
) -> dict[str, Any]:
    """Read and integrity-check one redacted teacher receipt."""
    normalized_scope = _scope(scope)
    _text(queue_id, "queue_id")
    _queue(connection, queue_id, normalized_scope)
    row = _receipt_row(connection, queue_id, normalized_scope)
    if row is None:
        raise TeacherAcquisitionQueueError("teacher_receipt_not_found")
    try:
        public_receipt = json.loads(row["public_receipt_json"])
    except (TypeError, ValueError) as exc:
        raise TeacherAcquisitionQueueError("stored_public_receipt_invalid") from exc
    if not isinstance(public_receipt, dict):
        raise TeacherAcquisitionQueueError("stored_public_receipt_invalid")
    if stable_hash(public_receipt) != row["public_receipt_hash"]:
        raise TeacherAcquisitionQueueError("stored_public_receipt_integrity_mismatch")
    if public_receipt.get("public_safe") is not True:
        raise TeacherAcquisitionQueueError("stored_public_receipt_not_public_safe")
    return {
        "receipt_id": row["receipt_id"],
        "queue_id": row["queue_id"],
        "pair_id": row["pair_id"],
        "teacher_id": row["teacher_id"],
        "scope": {field: row[field] for field in SCOPE_FIELDS},
        "request_hash": row["request_hash"],
        "receipt_hash": row["receipt_hash"],
        "receipt_schema_version": row["receipt_schema_version"],
        "verification_state": row["verification_state"],
        "public_receipt_hash": row["public_receipt_hash"],
        "public_receipt": public_receipt,
        "created_at": row["created_at"],
        "public_safe": True,
    }


def get_teacher_acquisition(
    connection: sqlite3.Connection,
    *,
    queue_id: str,
    scope: dict[str, str],
) -> dict[str, Any]:
    """Read one queue item without crossing tenant scope."""
    row = _queue(connection, queue_id, _scope(scope))
    return _public_row(row, idempotent_replay=False)


def _same_request(
    row: dict[str, Any],
    *,
    pair_id: str,
    teacher_id: str,
    request_hash: str,
    priority_score: float,
    max_cost_usd: float,
    max_attempts: int,
) -> bool:
    return (
        row["pair_id"] == pair_id
        and row["teacher_id"] == teacher_id
        and row["request_hash"] == request_hash
        and float(row["priority_score"]) == priority_score
        and float(row["max_cost_usd"]) == max_cost_usd
        and int(row["max_attempts"]) == max_attempts
    )


def _find_by_idempotency(
    connection: sqlite3.Connection,
    scope: dict[str, str],
    idempotency_key_hash: str,
) -> dict[str, Any] | None:
    cursor = connection.execute(
        """
        SELECT *
        FROM a2_teacher_acquisition_queue
        WHERE organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ?
          AND idempotency_key_hash = ?
        """,
        (
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
            idempotency_key_hash,
        ),
    )
    return _row_dict(cursor)


def _queue(
    connection: sqlite3.Connection,
    queue_id: str,
    scope: dict[str, str],
) -> dict[str, Any]:
    cursor = connection.execute(
        "SELECT * FROM a2_teacher_acquisition_queue WHERE queue_id = ?",
        (queue_id,),
    )
    row = _row_dict(cursor)
    if row is None:
        raise TeacherAcquisitionQueueError("queue_item_not_found")
    if any(row[field] != expected for field, expected in scope.items()):
        raise TeacherAcquisitionQueueError("queue_scope_mismatch")
    return row


def _receipt_row(
    connection: sqlite3.Connection,
    queue_id: str,
    scope: dict[str, str],
) -> dict[str, Any] | None:
    cursor = connection.execute(
        """
        SELECT *
        FROM a2_teacher_acquisition_receipts
        WHERE queue_id = ?
          AND organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ?
        """,
        (
            queue_id,
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
        ),
    )
    return _row_dict(cursor)


def _same_receipt(
    row: dict[str, Any],
    *,
    receipt_id: str,
    receipt_hash: str,
    public_receipt_hash: str,
    verification_state: str,
) -> bool:
    return (
        row["receipt_id"] == receipt_id
        and row["receipt_hash"] == receipt_hash
        and row["public_receipt_hash"] == public_receipt_hash
        and row["verification_state"] == verification_state
    )


def _public_row(row: dict[str, Any], *, idempotent_replay: bool) -> dict[str, Any]:
    return {
        "queue_id": row["queue_id"],
        "pair_id": row["pair_id"],
        "teacher_id": row["teacher_id"],
        "request_hash": row["request_hash"],
        "idempotency_key_hash": row["idempotency_key_hash"],
        "scope": {field: row[field] for field in SCOPE_FIELDS},
        "priority_score": float(row["priority_score"]),
        "max_cost_usd": float(row["max_cost_usd"]),
        "actual_cost_usd": (
            float(row["actual_cost_usd"])
            if row["actual_cost_usd"] is not None
            else None
        ),
        "status": row["status"],
        "max_attempts": int(row["max_attempts"]),
        "attempt_count": int(row["attempt_count"]),
        "lease_owner": row["lease_owner"],
        "lease_generation": int(row["lease_generation"]),
        "lease_expires_at": row["lease_expires_at"],
        "available_at": row["available_at"],
        "receipt_hash": row["receipt_hash"],
        "last_error_class": row["last_error_class"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "idempotent_replay": idempotent_replay,
    }


def _scope(scope: dict[str, str]) -> dict[str, str]:
    normalized = {field: str(scope.get(field) or "") for field in SCOPE_FIELDS}
    if any(not value for value in normalized.values()):
        raise TeacherAcquisitionQueueError("complete_five_field_scope_required")
    return normalized


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TeacherAcquisitionQueueError(f"{label}_must_be_non_empty")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise TeacherAcquisitionQueueError(f"{label}_must_be_sha256")
    return value


def _bounded_number(value: Any, label: str, *, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TeacherAcquisitionQueueError(f"{label}_must_be_number")
    result = float(value)
    if not math.isfinite(result) or result < 0 or result > maximum:
        raise TeacherAcquisitionQueueError(f"{label}_out_of_range")
    return result


def _nonnegative_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TeacherAcquisitionQueueError(f"{label}_must_be_number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise TeacherAcquisitionQueueError(f"{label}_must_be_nonnegative")
    return result


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TeacherAcquisitionQueueError(f"{label}_must_be_positive_integer")
    return value


def _canonical_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TeacherAcquisitionQueueError(f"{label}_must_be_iso_timestamp")
    try:
        return _timestamp(value).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError) as exc:
        raise TeacherAcquisitionQueueError(f"{label}_must_be_iso_timestamp") from exc


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)


def _row_dict(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return {
        description[0]: value
        for description, value in zip(cursor.description or (), row)
    }
