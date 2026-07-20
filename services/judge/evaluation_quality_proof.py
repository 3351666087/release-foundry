"""Authenticated quality evidence required before A2 may allow a release."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


EVALUATION_QUALITY_PROOF_SCHEMA_VERSION = "a2.evaluation_quality_proof.v1"
_SHA256_REF = re.compile(r"sha256:[0-9a-f]{64}\Z")
_STATUS = {"passed", "failed"}
_DISAGREEMENT = {"agree", "disagree", "reviewed", "unknown"}
_BINDING_FIELDS = (
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id",
    "authenticated_bundle_digest",
    "snapshot_hash",
    "provider_id",
    "model_id",
    "model_digest",
    "prompt_hash",
    "rubric_version",
    "golden_dataset_digest",
    "calibration_thresholds_hash",
    "policy_version",
)


def verify_evaluation_quality_proof(
    proof: Any,
    *,
    expected_bindings: dict[str, str],
    key_resolver: Callable[[str], bytes],
    now_unix_ms: int,
    allowed_issuers: frozenset[str] | None = None,
    revoked_key_ids: frozenset[str] = frozenset(),
    revoked_proof_hashes: frozenset[str] = frozenset(),
    maximum_lifetime_ms: int = 86_400_000,
    issuer_tenants: dict[str, frozenset[str]] | None = None,
    maximum_review_age_ms: int = 604_800_000,
) -> dict[str, Any]:
    """Verify a public-safe, content-addressed quality proof and normalize its gate state."""
    if not isinstance(proof, dict):
        return _blocked("quality_proof_missing")
    required = {
        "schema_version",
        "algorithm",
        "issuer",
        "key_id",
        *_BINDING_FIELDS,
        "calibration",
        "golden_regression",
        "disagreement",
        "reviewer_identity_digest",
        "reviewed_at_unix_ms",
        "evidence_refs",
        "issued_at_unix_ms",
        "expires_at_unix_ms",
        "signature",
    }
    if set(proof) != required:
        return _blocked("quality_proof_contract_invalid")
    if (
        proof.get("schema_version") != EVALUATION_QUALITY_PROOF_SCHEMA_VERSION
        or proof.get("algorithm") not in {"hmac-sha256", "ed25519"}
        or not isinstance(proof.get("issuer"), str)
        or not proof["issuer"]
        or not isinstance(proof.get("key_id"), str)
        or not proof["key_id"]
    ):
        return _blocked("quality_proof_contract_invalid")
    if allowed_issuers is not None and proof["issuer"] not in allowed_issuers:
        return _blocked("quality_proof_issuer_unauthorized")
    if issuer_tenants is not None and proof["tenant_id"] not in issuer_tenants.get(proof["issuer"], frozenset()):
        return _blocked("quality_proof_issuer_tenant_unauthorized")
    if proof["key_id"] in revoked_key_ids:
        return _blocked("quality_proof_key_revoked")
    issued_at = proof.get("issued_at_unix_ms")
    expires_at = proof.get("expires_at_unix_ms")
    if (
        not isinstance(issued_at, int)
        or not isinstance(expires_at, int)
        or not issued_at <= now_unix_ms <= expires_at
    ):
        return _blocked("quality_proof_outside_validity_window")
    if expires_at - issued_at > maximum_lifetime_ms:
        return _blocked("quality_proof_lifetime_exceeded")
    if any(str(proof.get(field) or "") != str(expected_bindings.get(field) or "") for field in _BINDING_FIELDS):
        return _blocked("quality_proof_binding_mismatch")
    if _SHA256_REF.fullmatch(str(proof.get("model_digest") or "")) is None:
        return _blocked("quality_proof_model_digest_invalid")
    if _SHA256_REF.fullmatch(str(proof.get("prompt_hash") or "")) is None:
        return _blocked("quality_proof_prompt_hash_invalid")
    if _SHA256_REF.fullmatch(str(proof.get("golden_dataset_digest") or "")) is None:
        return _blocked("quality_proof_golden_dataset_digest_invalid")
    if _SHA256_REF.fullmatch(str(proof.get("calibration_thresholds_hash") or "")) is None:
        return _blocked("quality_proof_calibration_thresholds_invalid")
    if not str(proof.get("rubric_version") or ""):
        return _blocked("quality_proof_rubric_version_invalid")
    if proof.get("calibration") not in _STATUS or proof.get("golden_regression") not in _STATUS:
        return _blocked("quality_proof_contract_invalid")
    if proof.get("disagreement") not in _DISAGREEMENT:
        return _blocked("quality_proof_contract_invalid")
    reviewer_digest = proof.get("reviewer_identity_digest")
    reviewed_at = proof.get("reviewed_at_unix_ms")
    if proof["disagreement"] == "reviewed":
        if (
            _SHA256_REF.fullmatch(str(reviewer_digest or "")) is None
            or isinstance(reviewed_at, bool)
            or not isinstance(reviewed_at, int)
        ):
            return _blocked("disagreement_review_receipt_invalid")
        if reviewed_at > now_unix_ms or now_unix_ms - reviewed_at > maximum_review_age_ms:
            return _blocked("disagreement_review_receipt_stale")
    elif reviewer_digest != "" or reviewed_at != 0:
        return _blocked("disagreement_review_receipt_unexpected")
    refs = proof.get("evidence_refs")
    if (
        not isinstance(refs, list)
        or not refs
        or any(not isinstance(item, str) or _SHA256_REF.fullmatch(item) is None for item in refs)
    ):
        return _blocked("evaluation_quality_evidence_missing")
    signed_fields = {key: proof[key] for key in sorted(required - {"signature"})}
    proof_hash = _sha256_ref(_canonical_json(signed_fields))
    if proof_hash in revoked_proof_hashes:
        return _blocked("quality_proof_revoked")
    try:
        key = key_resolver(proof["key_id"])
    except Exception:
        return _blocked("quality_proof_key_unavailable")
    canonical = _canonical_json(signed_fields)
    signature = str(proof.get("signature") or "")
    if proof["algorithm"] == "hmac-sha256":
        expected = hmac.new(key, canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return _blocked("quality_proof_signature_mismatch")
    else:
        try:
            Ed25519PublicKey.from_public_bytes(key).verify(bytes.fromhex(signature), canonical)
        except (ValueError, InvalidSignature):
            return _blocked("quality_proof_signature_mismatch")

    blockers = []
    if proof["calibration"] != "passed":
        blockers.append("calibration_not_passed")
    if proof["golden_regression"] != "passed":
        blockers.append("golden_regression_not_passed")
    if proof["disagreement"] not in {"agree", "reviewed"}:
        blockers.append(
            "disagreement_requires_review"
            if proof["disagreement"] == "disagree"
            else "disagreement_not_evaluated"
        )
    return {
        "schema_version": "a2.evaluation_quality.v2",
        "proof_status": "verified",
        "issuer": proof["issuer"],
        "key_id_hash": _sha256_ref(proof["key_id"]),
        "proof_hash": proof_hash,
        "calibration": proof["calibration"],
        "golden_regression": proof["golden_regression"],
        "disagreement": proof["disagreement"],
        "reviewer_identity_digest": reviewer_digest,
        "reviewed_at_unix_ms": reviewed_at,
        "human_review_required": bool(blockers),
        "evidence_refs": sorted(set(refs)),
        "blockers": sorted(set(blockers)),
        "public_safe": True,
    }


def quality_proof_bindings(
    request: dict[str, Any],
    *,
    authenticated_bundle_digest: str,
    snapshot_hash: str,
    prompt_hash: str,
) -> dict[str, str]:
    return {
        **{
            field: str(request.get(field) or "")
            for field in (
                "organization_id",
                "tenant_id",
                "workspace_id",
                "project_id",
                "environment_id",
            )
        },
        "authenticated_bundle_digest": authenticated_bundle_digest,
        "snapshot_hash": snapshot_hash,
        "provider_id": str(request.get("provider_id") or ""),
        "model_id": str(request.get("model_id") or ""),
        "model_digest": str(request.get("model_digest") or ""),
        "prompt_hash": prompt_hash,
        "rubric_version": str(request.get("rubric_version") or ""),
        "golden_dataset_digest": str(request.get("golden_dataset_digest") or ""),
        "calibration_thresholds_hash": str(request.get("calibration_thresholds_hash") or ""),
        "policy_version": str(request.get("policy_version") or "a2.semantic_release_policy.v1"),
    }


def _blocked(blocker: str) -> dict[str, Any]:
    return {
        "schema_version": "a2.evaluation_quality.v2",
        "proof_status": "invalid",
        "issuer": "",
        "key_id_hash": "",
        "proof_hash": "",
        "calibration": "missing",
        "golden_regression": "missing",
        "disagreement": "unknown",
        "reviewer_identity_digest": "",
        "reviewed_at_unix_ms": 0,
        "human_review_required": True,
        "evidence_refs": [],
        "blockers": [blocker],
        "public_safe": True,
    }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha256_ref(value: str | bytes) -> str:
    payload = value.encode() if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
