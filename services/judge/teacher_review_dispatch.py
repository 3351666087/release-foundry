"""Dispatch verified paid-teacher receipts into human preference review."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import re
import sqlite3
from typing import Any

from .preference_review_store import open_preference_review_case
from .result_persistence import stable_hash
from .teacher_acquisition_queue import (
    get_teacher_acquisition,
    get_teacher_acquisition_receipt,
)


HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SCOPE_FIELDS = (
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id",
)


class TeacherReviewDispatchError(ValueError):
    """Raised when teacher evidence cannot safely enter human review."""


def dispatch_verified_teacher_receipt_to_preference_review(
    connection: sqlite3.Connection,
    *,
    queue_id: str,
    scope: Mapping[str, str],
    pair: Mapping[str, Any],
    reason_code: str,
    created_at: str,
    required_approvals: int = 1,
) -> dict[str, Any]:
    """Open a human review linked to one verified teacher receipt.

    Dispatch never upgrades the teacher label to human gold and never creates a
    training candidate.  Those actions remain behind the existing fenced human
    review and arbitration workflow.
    """
    normalized_scope = _scope(scope)
    _text(queue_id, "queue_id")
    reason = _text(reason_code, "reason_code")
    created = _timestamp(created_at, "created_at")
    if required_approvals not in {1, 2}:
        raise TeacherReviewDispatchError(
            "required_approvals_must_be_one_or_two"
        )
    pair_id = _pair_id(pair)
    if pair.get("training_eligible") is not False:
        raise TeacherReviewDispatchError("pair_training_state_invalid")
    if pair.get("review_required") is not True:
        raise TeacherReviewDispatchError("pair_review_not_required")
    if pair.get("status") not in {
        "provisional_preference",
        "review_required",
    }:
        raise TeacherReviewDispatchError("pair_not_reviewable")

    try:
        queued = get_teacher_acquisition(
            connection,
            queue_id=queue_id,
            scope=normalized_scope,
        )
        receipt = get_teacher_acquisition_receipt(
            connection,
            queue_id=queue_id,
            scope=normalized_scope,
        )
    except ValueError as exc:
        raise TeacherReviewDispatchError(str(exc)) from exc
    if queued["status"] != "completed":
        raise TeacherReviewDispatchError("teacher_queue_not_completed")
    if receipt["verification_state"] != "verified":
        raise TeacherReviewDispatchError("teacher_receipt_not_verified")
    public_receipt = receipt["public_receipt"]
    _assert_queue_receipt_bindings(queued, receipt, public_receipt)
    _assert_verified_terminal_receipt(public_receipt)
    if pair_id != queued["pair_id"] or pair_id != receipt["pair_id"]:
        raise TeacherReviewDispatchError("teacher_pair_binding_mismatch")
    if queued["receipt_hash"] != receipt["receipt_hash"]:
        raise TeacherReviewDispatchError("teacher_receipt_hash_mismatch")

    expected_review_id = stable_hash(
        {
            "pair_id": pair_id,
            "scope": normalized_scope,
            "reason_code": reason,
        }
    )
    existing = _dispatch_row(
        connection,
        queue_id=queue_id,
        scope=normalized_scope,
    )
    if existing is not None:
        _assert_dispatch_request_matches(
            existing,
            pair_id=pair_id,
            receipt_id=receipt["receipt_id"],
            receipt_hash=receipt["receipt_hash"],
            teacher_id=queued["teacher_id"],
            request_hash=queued["request_hash"],
            review_id=expected_review_id,
            reason_code=reason,
            required_approvals=required_approvals,
        )
        _assert_dispatch_links(existing, queued=queued, receipt=receipt)
        return _public_dispatch(
            connection,
            existing,
            idempotent_replay=True,
        )

    try:
        review = open_preference_review_case(
            connection,
            scope=normalized_scope,
            pair=pair,
            reason_code=reason,
            created_at=created,
            required_approvals=required_approvals,
        )
    except ValueError as exc:
        raise TeacherReviewDispatchError(str(exc)) from exc
    if review["review_id"] != expected_review_id:
        raise TeacherReviewDispatchError("preference_review_identity_mismatch")
    core = {
        "queue_id": queue_id,
        "receipt_id": receipt["receipt_id"],
        "review_id": review["review_id"],
        "pair_id": pair_id,
        "pair_hash": pair_id,
        "teacher_id": queued["teacher_id"],
        "scope": normalized_scope,
        "request_hash": queued["request_hash"],
        "receipt_hash": receipt["receipt_hash"],
        "reason_code": reason,
        "required_approvals": required_approvals,
        "created_at": created,
    }
    dispatch_id = stable_hash(
        {
            "queue_id": queue_id,
            "receipt_id": receipt["receipt_id"],
            "review_id": review["review_id"],
        }
    )
    dispatch_hash = stable_hash(core)
    try:
        connection.execute(
            """
            INSERT OR IGNORE INTO a2_teacher_review_dispatches (
              dispatch_id, queue_id, receipt_id, review_id, pair_id, pair_hash,
              teacher_id, organization_id, tenant_id, workspace_id, project_id,
              environment_id, request_hash, receipt_hash, reason_code,
              required_approvals, dispatch_hash, created_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                dispatch_id,
                queue_id,
                receipt["receipt_id"],
                review["review_id"],
                pair_id,
                pair_id,
                queued["teacher_id"],
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
                queued["request_hash"],
                receipt["receipt_hash"],
                reason,
                required_approvals,
                dispatch_hash,
                created,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    stored = _dispatch_row(
        connection,
        queue_id=queue_id,
        scope=normalized_scope,
    )
    if stored is None:
        raise TeacherReviewDispatchError("teacher_review_dispatch_not_stored")
    _assert_dispatch_request_matches(
        stored,
        pair_id=pair_id,
        receipt_id=receipt["receipt_id"],
        receipt_hash=receipt["receipt_hash"],
        teacher_id=queued["teacher_id"],
        request_hash=queued["request_hash"],
        review_id=expected_review_id,
        reason_code=reason,
        required_approvals=required_approvals,
    )
    if stored["dispatch_id"] != dispatch_id or stored["dispatch_hash"] != dispatch_hash:
        raise TeacherReviewDispatchError("teacher_review_dispatch_conflict")
    _assert_dispatch_links(stored, queued=queued, receipt=receipt)
    return _public_dispatch(connection, stored, idempotent_replay=False)


def get_teacher_review_dispatch(
    connection: sqlite3.Connection,
    *,
    queue_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any]:
    """Read and integrity-check one teacher-to-review dispatch."""
    normalized_scope = _scope(scope)
    _text(queue_id, "queue_id")
    row = _dispatch_row(
        connection,
        queue_id=queue_id,
        scope=normalized_scope,
    )
    if row is None:
        raise TeacherReviewDispatchError("teacher_review_dispatch_not_found")
    try:
        queued = get_teacher_acquisition(
            connection,
            queue_id=queue_id,
            scope=normalized_scope,
        )
        receipt = get_teacher_acquisition_receipt(
            connection,
            queue_id=queue_id,
            scope=normalized_scope,
        )
    except ValueError as exc:
        raise TeacherReviewDispatchError(str(exc)) from exc
    _assert_queue_receipt_bindings(queued, receipt, receipt["public_receipt"])
    _assert_verified_terminal_receipt(receipt["public_receipt"])
    _assert_dispatch_links(row, queued=queued, receipt=receipt)
    return _public_dispatch(connection, row, idempotent_replay=False)


def _dispatch_row(
    connection: sqlite3.Connection,
    *,
    queue_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any] | None:
    cursor = connection.execute(
        """
        SELECT *
        FROM a2_teacher_review_dispatches
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


def _public_dispatch(
    connection: sqlite3.Connection,
    row: Mapping[str, Any],
    *,
    idempotent_replay: bool,
) -> dict[str, Any]:
    core = {
        "queue_id": row["queue_id"],
        "receipt_id": row["receipt_id"],
        "review_id": row["review_id"],
        "pair_id": row["pair_id"],
        "pair_hash": row["pair_hash"],
        "teacher_id": row["teacher_id"],
        "scope": {field: row[field] for field in SCOPE_FIELDS},
        "request_hash": row["request_hash"],
        "receipt_hash": row["receipt_hash"],
        "reason_code": row["reason_code"],
        "required_approvals": int(row["required_approvals"]),
        "created_at": row["created_at"],
    }
    if stable_hash(core) != row["dispatch_hash"]:
        raise TeacherReviewDispatchError("teacher_review_dispatch_integrity_mismatch")
    if int(row["public_safe"]) != 1:
        raise TeacherReviewDispatchError("teacher_review_dispatch_not_public_safe")
    review = _row_dict(
        connection.execute(
        """
        SELECT review_id, pair_id, pair_hash, organization_id, tenant_id,
               workspace_id, project_id, environment_id, reason_code,
               required_approvals, status
        FROM a2_preference_review_cases
        WHERE review_id = ?
        """,
        (row["review_id"],),
        )
    )
    if review is None:
        raise TeacherReviewDispatchError("preference_review_case_missing")
    expected_review = {
        "review_id": row["review_id"],
        "pair_id": row["pair_id"],
        "pair_hash": row["pair_hash"],
        "reason_code": row["reason_code"],
        "required_approvals": int(row["required_approvals"]),
        **{field: row[field] for field in SCOPE_FIELDS},
    }
    observed_review = {
        **review,
        "required_approvals": int(review["required_approvals"]),
    }
    if any(
        observed_review[field] != value
        for field, value in expected_review.items()
    ):
        raise TeacherReviewDispatchError("preference_review_binding_mismatch")
    return {
        "dispatch_id": row["dispatch_id"],
        "dispatch_hash": row["dispatch_hash"],
        **core,
        "review_status": review["status"],
        "teacher_receipt_training_authority": False,
        "human_review_required": True,
        "training_candidate_created_by_dispatch": False,
        "public_safe": True,
        "idempotent_replay": idempotent_replay,
    }


def _assert_dispatch_request_matches(
    row: Mapping[str, Any],
    *,
    pair_id: str,
    receipt_id: str,
    receipt_hash: str,
    teacher_id: str,
    request_hash: str,
    review_id: str,
    reason_code: str,
    required_approvals: int,
) -> None:
    expected = {
        "pair_id": pair_id,
        "pair_hash": pair_id,
        "receipt_id": receipt_id,
        "receipt_hash": receipt_hash,
        "teacher_id": teacher_id,
        "request_hash": request_hash,
        "review_id": review_id,
        "reason_code": reason_code,
    }
    if any(row[field] != value for field, value in expected.items()):
        raise TeacherReviewDispatchError("teacher_review_dispatch_conflict")
    if int(row["required_approvals"]) != required_approvals:
        raise TeacherReviewDispatchError("teacher_review_dispatch_conflict")


def _assert_queue_receipt_bindings(
    queued: Mapping[str, Any],
    receipt: Mapping[str, Any],
    public_receipt: Any,
) -> None:
    if not isinstance(public_receipt, Mapping):
        raise TeacherReviewDispatchError("teacher_public_receipt_missing")
    for field in ("pair_id", "teacher_id", "request_hash", "receipt_hash"):
        if field != "receipt_hash" and receipt.get(field) != queued.get(field):
            raise TeacherReviewDispatchError(
                f"teacher_{field}_binding_mismatch"
            )
        expected = receipt.get(field)
        if public_receipt.get(field) != expected:
            raise TeacherReviewDispatchError(
                f"teacher_public_{field}_binding_mismatch"
            )
    if queued.get("receipt_hash") != receipt.get("receipt_hash"):
        raise TeacherReviewDispatchError("teacher_receipt_hash_mismatch")


def _assert_verified_terminal_receipt(public_receipt: Mapping[str, Any]) -> None:
    terminal = public_receipt.get("public_releasefoundry_receipt")
    if (
        public_receipt.get("verification_state") != "verified"
        or public_receipt.get("blockers") != []
        or not isinstance(terminal, Mapping)
        or terminal.get("verification_state") != "verified"
        or terminal.get("receipt_complete") is not True
        or terminal.get("all_expected_tests_terminal_scoring_verified")
        is not True
        or terminal.get("exact_test_set_verified") is not True
        or terminal.get("aggregate_marker_used_as_acceptance_authority")
        is not False
        or terminal.get("blockers") != []
    ):
        raise TeacherReviewDispatchError("teacher_receipt_incomplete")
    expected_count = terminal.get("expected_test_count")
    tests = terminal.get("tests")
    if (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count <= 0
        or not isinstance(tests, list)
        or len(tests) != expected_count
        or terminal.get("observed_test_count") != expected_count
        or terminal.get("valid_test_object_count") != expected_count
        or terminal.get("verified_test_count") != expected_count
    ):
        raise TeacherReviewDispatchError("teacher_test_count_mismatch")
    zero_count_fields = (
        "missing_test_count",
        "duplicate_test_count",
        "unexpected_test_count",
        "unidentified_test_count",
        "malformed_test_count",
        "nonterminal_test_count",
    )
    if any(terminal.get(field) != 0 for field in zero_count_fields):
        raise TeacherReviewDispatchError("teacher_test_set_not_exact")
    case_ids: set[str] = set()
    for item in tests:
        if (
            not isinstance(item, Mapping)
            or not isinstance(item.get("case_id"), str)
            or not item["case_id"]
            or item["case_id"] in case_ids
            or item.get("terminal_scoring_verified") is not True
            or item.get("terminal_status_verified") is not True
            or item.get("response_evidence_verified") is not True
            or item.get("server_grading_signal_verified") is not True
        ):
            raise TeacherReviewDispatchError(
                "teacher_test_terminal_scoring_not_verified"
            )
        case_ids.add(item["case_id"])


def _assert_dispatch_links(
    row: Mapping[str, Any],
    *,
    queued: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> None:
    expected = {
        "queue_id": queued["queue_id"],
        "receipt_id": receipt["receipt_id"],
        "pair_id": queued["pair_id"],
        "pair_hash": queued["pair_id"],
        "teacher_id": queued["teacher_id"],
        "request_hash": queued["request_hash"],
        "receipt_hash": receipt["receipt_hash"],
    }
    if any(row[field] != value for field, value in expected.items()):
        raise TeacherReviewDispatchError("teacher_review_dispatch_binding_mismatch")


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


def _pair_id(pair: Mapping[str, Any]) -> str:
    if not isinstance(pair, Mapping):
        raise TeacherReviewDispatchError("pair_must_be_object")
    pair_id = _hash(pair.get("pair_id"), "pair_id")
    core = {key: value for key, value in pair.items() if key != "pair_id"}
    if stable_hash(core) != pair_id:
        raise TeacherReviewDispatchError("pair_hash_mismatch")
    return pair_id


def _scope(scope: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(scope, Mapping):
        raise TeacherReviewDispatchError("scope_must_be_object")
    normalized = {field: str(scope.get(field) or "") for field in SCOPE_FIELDS}
    if any(not value for value in normalized.values()):
        raise TeacherReviewDispatchError("complete_five_field_scope_required")
    return normalized


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TeacherReviewDispatchError(f"{field}_must_be_non_empty")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise TeacherReviewDispatchError(f"{field}_must_be_sha256")
    return value


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise TeacherReviewDispatchError(f"{field}_must_be_iso_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TeacherReviewDispatchError(
            f"{field}_must_be_iso_timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise TeacherReviewDispatchError(f"{field}_must_be_iso_timestamp")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
