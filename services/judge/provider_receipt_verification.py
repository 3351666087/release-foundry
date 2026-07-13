"""Provider-neutral contracts for cancellation receipt verification and replay state."""

from __future__ import annotations

import hmac
import base64
import json
import threading
import os
from pathlib import Path
import tempfile
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
    signed_identity = {
        "signature_algorithm": signature_algorithm,
        "canonicalization_version": "adapter-defined",
        "receipt": receipt,
    }
    try:
        verified = verifier(dict(receipt)) is True
    except Exception:
        verified = False
    return {
        "schema_version": "a2.provider_receipt_signature_verification.v1",
        "receipt_hash": receipt_hash,
        "issuer": issuer,
        "signature_algorithm": signature_algorithm,
        "canonicalization_version": "adapter-defined",
        "signed_identity_hash": stable_hash(signed_identity),
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
    now_unix_ms: int | None = None,
    signature_algorithm: str = "ed25519",
    canonicalization_version: str = "rfc8785-subset-json-v1",
) -> dict[str, Any]:
    blockers: list[str] = []
    allowed = key_policy.get("allowed_keys", {})
    key_record = allowed.get(key_id)
    if key_policy.get("schema_version") != "a2.provider_receipt_key_policy.v1":
        blockers.append("provider_receipt_key_policy_invalid")
    elif not isinstance(key_record, dict) or key_record.get("issuer") != issuer:
        blockers.append("provider_receipt_key_not_active")
    else:
        if key_record.get("state") != "active":
            blockers.append("provider_receipt_key_not_active")
        if now_unix_ms is not None:
            effective = key_record.get("effective_at_unix_ms", 0)
            expires = key_record.get("expires_at_unix_ms")
            if not isinstance(effective, int) or isinstance(effective, bool):
                blockers.append("provider_receipt_key_time_policy_invalid")
            elif now_unix_ms < effective:
                blockers.append("provider_receipt_key_not_yet_active")
            if expires is not None:
                if not isinstance(expires, int) or isinstance(expires, bool):
                    blockers.append("provider_receipt_key_time_policy_invalid")
                elif now_unix_ms >= expires:
                    blockers.append("provider_receipt_key_expired")
    if signature_algorithm != "ed25519":
        blockers.append("provider_receipt_signature_algorithm_unsupported")
    if canonicalization_version != "rfc8785-subset-json-v1":
        blockers.append("provider_receipt_canonicalization_unsupported")
    signed_identity = {
        "signature_algorithm": signature_algorithm,
        "canonicalization_version": canonicalization_version,
        "receipt": receipt,
    }
    try:
        message = json.dumps(signed_identity, sort_keys=True, separators=(",", ":")).encode()
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_base64, validate=True)).verify(
            base64.b64decode(signature_base64, validate=True), message
        )
    except (ValueError, InvalidSignature):
        blockers.append("provider_receipt_signature_invalid")
    return {
        "schema_version": "a2.provider_receipt_signature_verification.v1",
        "receipt_hash": stable_hash(receipt),
        "issuer": issuer,
        "signature_algorithm": signature_algorithm,
        "canonicalization_version": canonicalization_version,
        "signed_identity_hash": stable_hash(signed_identity),
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


class PersistentReplaySet:
    """Cross-process replay admission through an atomically replaced, OS-locked snapshot."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def admit(self, nonce_hash: str) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_file:
            _lock_file(lock_file)
            try:
                snapshot = self._load()
                values = set(snapshot["nonce_hashes"])
                admitted = nonce_hash not in values
                if admitted:
                    values.add(nonce_hash)
                    updated = {
                        "schema_version": "a2.provider_receipt_replay_set.v1",
                        "nonce_hashes": sorted(values),
                    }
                    fd, temporary_name = tempfile.mkstemp(
                        prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent
                    )
                    try:
                        with os.fdopen(fd, "wb") as temporary:
                            temporary.write(
                                json.dumps(updated, sort_keys=True, separators=(",", ":")).encode()
                            )
                            temporary.flush()
                            os.fsync(temporary.fileno())
                        os.replace(temporary_name, self.path)
                    finally:
                        Path(temporary_name).unlink(missing_ok=True)
                return {
                    "admitted": admitted,
                    "snapshot_hash": stable_hash(self._load()),
                    "lock_state": "exclusive_os_lock",
                    "atomic_replace": True,
                    "release_authority": False,
                    "public_safe": True,
                }
            finally:
                _unlock_file(lock_file)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": "a2.provider_receipt_replay_set.v1", "nonce_hashes": []}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("schema_version") != "a2.provider_receipt_replay_set.v1"
            or not isinstance(value.get("nonce_hashes"), list)
        ):
            raise ValueError("persistent replay snapshot is invalid")
        return value


def _lock_file(file_object: Any) -> None:
    if os.name == "nt":
        import msvcrt
        file_object.seek(0)
        if file_object.tell() == 0:
            file_object.write(b"\0")
            file_object.flush()
        file_object.seek(0)
        msvcrt.locking(file_object.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl
        fcntl.flock(file_object.fileno(), fcntl.LOCK_EX)


def _unlock_file(file_object: Any) -> None:
    if os.name == "nt":
        import msvcrt
        file_object.seek(0)
        msvcrt.locking(file_object.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(file_object.fileno(), fcntl.LOCK_UN)
