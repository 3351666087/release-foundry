"""Provider-neutral contracts for cancellation receipt verification and replay state."""

from __future__ import annotations

import hmac
from typing import Any, Callable

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
