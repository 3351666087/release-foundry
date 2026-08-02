"""Bind verified ReleaseFoundry test receipts to the paid-teacher acquisition queue.

The worker may hold the raw ReleaseFoundry response in memory (or in a separately
protected private evidence artifact), but the durable queue stores only a
redacted, integrity-checked projection.  A blocked receipt is terminal for
this acquisition attempt: it never becomes a training candidate by accident.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .releasefoundry_test_receipts import (
    assert_public_releasefoundry_test_terminal_receipt_safe,
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_terminal_receipt,
)
from .result_persistence import stable_hash
from .teacher_acquisition_queue import (
    get_teacher_acquisition,
    settle_teacher_acquisition_with_public_receipt,
)


RECEIPT_SCHEMA_VERSION = "a2.releasefoundry_teacher_acquisition_receipt.v1"
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class ReleaseFoundryTeacherReceiptError(ValueError):
    """Raised when an ReleaseFoundry receipt cannot be safely bound or settled."""


def build_releasefoundry_teacher_acquisition_receipt(
    run: Mapping[str, Any],
    *,
    pair_id: str,
    teacher_id: str,
    request_hash: str,
    case_map: Mapping[str, str],
    expected_dataset_id: int,
    expected_judge_version: str = "",
) -> dict[str, Any]:
    """Build an in-memory private receipt and its public durable projection.

    The returned ``private_receipt`` must never be written to the durable SQL
    queue.  It is included in the return value only so a caller can optionally
    place it in an already-protected private evidence lane.
    """
    _text(pair_id, "pair_id")
    _text(teacher_id, "teacher_id")
    _hash(request_hash, "request_hash")
    if not isinstance(case_map, Mapping):
        raise ReleaseFoundryTeacherReceiptError("case_map_must_be_object")
    normalized_case_map = {
        str(test_id): str(case_id)
        for test_id, case_id in case_map.items()
    }
    if not normalized_case_map or any(
        not test_id or not case_id
        for test_id, case_id in normalized_case_map.items()
    ):
        raise ReleaseFoundryTeacherReceiptError("case_map_must_have_nonempty_strings")

    try:
        private_receipt = build_releasefoundry_test_terminal_receipt(
            run,
            case_map=normalized_case_map,
            expected_dataset_id=expected_dataset_id,
            expected_judge_version=expected_judge_version,
        )
        public_terminal_receipt = public_releasefoundry_test_terminal_receipt(
            private_receipt
        )
        assert_public_releasefoundry_test_terminal_receipt_safe(public_terminal_receipt)
    except (TypeError, ValueError) as exc:
        raise ReleaseFoundryTeacherReceiptError(str(exc)) from exc

    private_receipt_hash = stable_hash(private_receipt)
    case_map_hash = stable_hash(normalized_case_map)
    receipt_hash = stable_hash(
        {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "pair_id": pair_id,
            "teacher_id": teacher_id,
            "request_hash": request_hash,
            "case_map_hash": case_map_hash,
            "private_receipt_hash": private_receipt_hash,
            "private_receipt": private_receipt,
        }
    )
    public_receipt = _public_envelope(
        pair_id=pair_id,
        teacher_id=teacher_id,
        request_hash=request_hash,
        case_map_hash=case_map_hash,
        private_receipt_hash=private_receipt_hash,
        receipt_hash=receipt_hash,
        private_receipt=private_receipt,
        public_terminal_receipt=public_terminal_receipt,
    )
    assert_public_releasefoundry_test_terminal_receipt_safe(public_receipt)
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "verification_state": private_receipt["verification_state"],
        "pair_id": pair_id,
        "teacher_id": teacher_id,
        "request_hash": request_hash,
        "case_map_hash": case_map_hash,
        "private_receipt_hash": private_receipt_hash,
        "receipt_hash": receipt_hash,
        "private_receipt": private_receipt,
        "public_receipt": public_receipt,
        "public_safe": True,
    }


def settle_releasefoundry_teacher_acquisition(
    connection: Any,
    *,
    claimed_request: Mapping[str, Any],
    scope: Mapping[str, str],
    worker_id: str,
    lease_generation: int,
    settled_at: str,
    actual_cost_usd: float,
    case_map: Mapping[str, str],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a receipt bundle, then atomically settle its queue item."""
    if not isinstance(claimed_request, Mapping):
        raise ReleaseFoundryTeacherReceiptError("claimed_request_must_be_object")
    if not isinstance(receipt, Mapping):
        raise ReleaseFoundryTeacherReceiptError("receipt_bundle_must_be_object")
    queue_id = claimed_request.get("queue_id")
    if not isinstance(queue_id, str) or not queue_id:
        raise ReleaseFoundryTeacherReceiptError("claimed_queue_id_missing")

    try:
        queued = get_teacher_acquisition(
            connection,
            queue_id=queue_id,
            scope=dict(scope),
        )
    except ValueError as exc:
        raise ReleaseFoundryTeacherReceiptError(str(exc)) from exc
    for field in ("pair_id", "teacher_id", "request_hash"):
        if receipt.get(field) != queued[field]:
            raise ReleaseFoundryTeacherReceiptError(f"receipt_{field}_mismatch")

    private_receipt = receipt.get("private_receipt")
    public_receipt = receipt.get("public_receipt")
    if not isinstance(private_receipt, Mapping):
        raise ReleaseFoundryTeacherReceiptError("private_receipt_missing")
    if not isinstance(public_receipt, dict):
        raise ReleaseFoundryTeacherReceiptError("public_receipt_missing")

    try:
        expected_public_terminal = public_releasefoundry_test_terminal_receipt(
            private_receipt
        )
        assert_public_releasefoundry_test_terminal_receipt_safe(expected_public_terminal)
    except (TypeError, ValueError) as exc:
        raise ReleaseFoundryTeacherReceiptError(str(exc)) from exc
    private_receipt_hash = stable_hash(private_receipt)
    expected_case_map_hash = receipt.get("case_map_hash")
    if not isinstance(expected_case_map_hash, str) or not HASH_PATTERN.fullmatch(
        expected_case_map_hash
    ):
        raise ReleaseFoundryTeacherReceiptError("receipt_case_map_hash_invalid")
    if not isinstance(case_map, Mapping):
        raise ReleaseFoundryTeacherReceiptError("case_map_must_be_object")
    normalized_case_map = {
        str(test_id): str(case_id)
        for test_id, case_id in case_map.items()
    }
    if stable_hash(normalized_case_map) != expected_case_map_hash:
        raise ReleaseFoundryTeacherReceiptError("receipt_case_map_hash_mismatch")
    if receipt.get("private_receipt_hash") != private_receipt_hash:
        raise ReleaseFoundryTeacherReceiptError("receipt_private_hash_mismatch")
    receipt_hash = receipt.get("receipt_hash")
    if not isinstance(receipt_hash, str) or not HASH_PATTERN.fullmatch(receipt_hash):
        raise ReleaseFoundryTeacherReceiptError("receipt_hash_invalid")
    expected_hash = stable_hash(
        {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "pair_id": receipt["pair_id"],
            "teacher_id": receipt["teacher_id"],
            "request_hash": receipt["request_hash"],
            "case_map_hash": expected_case_map_hash,
            "private_receipt_hash": private_receipt_hash,
            "private_receipt": private_receipt,
        }
    )
    if receipt_hash != expected_hash:
        raise ReleaseFoundryTeacherReceiptError("receipt_hash_mismatch")
    expected_public = _public_envelope(
        pair_id=receipt["pair_id"],
        teacher_id=receipt["teacher_id"],
        request_hash=receipt["request_hash"],
        case_map_hash=expected_case_map_hash,
        private_receipt_hash=private_receipt_hash,
        receipt_hash=receipt_hash,
        private_receipt=private_receipt,
        public_terminal_receipt=expected_public_terminal,
    )
    if public_receipt != expected_public:
        raise ReleaseFoundryTeacherReceiptError("public_receipt_projection_mismatch")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise ReleaseFoundryTeacherReceiptError("receipt_schema_version_mismatch")
    if receipt.get("verification_state") != private_receipt.get(
        "verification_state"
    ):
        raise ReleaseFoundryTeacherReceiptError("receipt_verification_state_mismatch")

    try:
        return settle_teacher_acquisition_with_public_receipt(
            connection,
            queue_id=queue_id,
            scope=dict(scope),
            worker_id=worker_id,
            lease_generation=lease_generation,
            settled_at=settled_at,
            verification_state=str(receipt["verification_state"]),
            receipt_schema_version=RECEIPT_SCHEMA_VERSION,
            receipt_hash=receipt_hash,
            public_receipt=public_receipt,
            actual_cost_usd=actual_cost_usd,
        )
    except ValueError as exc:
        raise ReleaseFoundryTeacherReceiptError(str(exc)) from exc


def _public_envelope(
    *,
    pair_id: str,
    teacher_id: str,
    request_hash: str,
    case_map_hash: str,
    private_receipt_hash: str,
    receipt_hash: str,
    private_receipt: Mapping[str, Any],
    public_terminal_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "verification_state": private_receipt.get("verification_state"),
        "pair_id": pair_id,
        "teacher_id": teacher_id,
        "request_hash": request_hash,
        "case_map_hash": case_map_hash,
        "private_receipt_hash": private_receipt_hash,
        "receipt_hash": receipt_hash,
        "public_releasefoundry_receipt": dict(public_terminal_receipt),
        "blockers": list(private_receipt.get("blockers") or []),
        "public_safe": True,
        "raw_private_receipt_included": False,
    }


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseFoundryTeacherReceiptError(f"{field}_must_be_non_empty")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise ReleaseFoundryTeacherReceiptError(f"{field}_must_be_sha256")
    return value
