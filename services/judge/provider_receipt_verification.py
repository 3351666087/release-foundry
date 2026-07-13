"""Provider-neutral contracts for cancellation receipt verification and replay state."""

from __future__ import annotations

import hmac
import base64
import json
import threading
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .result_persistence import stable_hash


def verify_provider_receipt_signature(
    *,
    receipt: dict[str, Any],
    issuer: str,
    signature_algorithm: str,
    verifier: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    receipt_hash = stable_hash(receipt)
    try:
        verified = verifier(dict(receipt)) is True
    except Exception:
        verified = False
    return {
        "schema_version": "a2.provider_receipt_signature_verification.v1",
        "receipt_hash": receipt_hash,
        "issuer": issuer,
        "signature_algorithm": signature_algorithm,
        "key_id": "adapter-defined",
        "key_policy_hash": stable_hash({"mode": "callable-verifier"}),
        "verification_state": "verified" if verified else "rejected",
        "release_authority": False,
        "blockers": [] if verified else ["provider_receipt_signature_invalid"],
        "public_safe": True,
    }


def verify_replay_set_snapshot(
    *, snapshot: dict[str, Any], expected_snapshot_hash: str
) -> dict[str, Any]:
    observed = stable_hash(snapshot)
    matched = hmac.compare_digest(observed, expected_snapshot_hash)
    return {
        "schema_version": "a2.provider_receipt_replay_set_verification.v1",
        "snapshot_hash": observed,
        "state": "verified" if matched else "blocked",
        "release_authority": False,
        "blockers": [] if matched else ["provider_receipt_replay_set_tampered"],
        "public_safe": True,
    }


def verify_ed25519_receipt(
    *,
    receipt: dict[str, Any],
    signature_base64: str,
    public_key_base64: str,
    issuer: str,
    key_id: str,
    key_policy: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    allowed = key_policy.get("allowed_keys", {})
    if key_policy.get("schema_version") != "a2.provider_receipt_key_policy.v1":
        blockers.append("provider_receipt_key_policy_invalid")
    elif allowed.get(key_id) != {"issuer": issuer, "state": "active"}:
        blockers.append("provider_receipt_key_not_active")
    try:
        message = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_base64, validate=True)).verify(
            base64.b64decode(signature_base64, validate=True), message
        )
    except (ValueError, InvalidSignature):
        blockers.append("provider_receipt_signature_invalid")
    return {
        "schema_version": "a2.provider_receipt_signature_verification.v1",
        "receipt_hash": stable_hash(receipt),
        "issuer": issuer,
        "signature_algorithm": "ed25519",
        "key_id": key_id,
        "key_policy_hash": stable_hash(key_policy),
        "verification_state": "verified" if not blockers else "rejected",
        "release_authority": False,
        "blockers": blockers,
        "public_safe": True,
    }


def verify_receipt_operation_binding(
    *, receipt: dict[str, Any], expected_request_hash: str, expected_operation_id_hash: str
) -> dict[str, Any]:
    blockers = []
    if receipt.get("request_hash") != expected_request_hash:
        blockers.append("provider_receipt_request_hash_mismatch")
    if receipt.get("cancellation_operation_id_hash") != expected_operation_id_hash:
        blockers.append("provider_receipt_operation_id_mismatch")
    if not receipt.get("nonce_hash"):
        blockers.append("provider_receipt_nonce_missing")
    return {"state": "verified" if not blockers else "blocked", "blockers": blockers, "public_safe": True}


class ReplaySet:
    """Thread-safe in-process replay admission; persisted snapshots remain separately hash-bound."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: set[str] = set()

    def admit(self, nonce_hash: str) -> bool:
        with self._lock:
            if nonce_hash in self._values:
                return False
            self._values.add(nonce_hash)
            return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"schema_version": "a2.provider_receipt_replay_set.v1", "nonce_hashes": sorted(self._values)}
