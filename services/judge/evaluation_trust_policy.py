"""Versioned, public-safe trust policy for evaluation quality proofs."""

from __future__ import annotations

from typing import Any

from .result_persistence import stable_hash


EVALUATION_TRUST_POLICY_SCHEMA_VERSION = "a2.evaluation_trust_policy.v1"
_FIELDS = {
    "schema_version",
    "allowed_issuers",
    "issuer_tenants",
    "revoked_key_ids",
    "revoked_proof_hashes",
    "maximum_lifetime_ms",
    "maximum_review_age_ms",
}


def normalize_evaluation_trust_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize a content-addressable policy without key material."""
    candidate = policy or {
        "schema_version": EVALUATION_TRUST_POLICY_SCHEMA_VERSION,
        "allowed_issuers": [],
        "issuer_tenants": {},
        "revoked_key_ids": [],
        "revoked_proof_hashes": [],
        "maximum_lifetime_ms": 86_400_000,
        "maximum_review_age_ms": 604_800_000,
    }
    if not isinstance(candidate, dict) or set(candidate) != _FIELDS:
        raise ValueError("evaluation trust policy fields do not match the governed schema")
    if candidate.get("schema_version") != EVALUATION_TRUST_POLICY_SCHEMA_VERSION:
        raise ValueError("unsupported evaluation trust policy schema")
    allowed = _strings(candidate["allowed_issuers"], "allowed issuers")
    revoked_keys = _strings(candidate["revoked_key_ids"], "revoked key ids")
    revoked_proofs = _strings(candidate["revoked_proof_hashes"], "revoked proof hashes")
    tenants = candidate["issuer_tenants"]
    if not isinstance(tenants, dict) or any(not isinstance(key, str) or not key for key in tenants):
        raise ValueError("evaluation trust policy issuer tenants are invalid")
    normalized_tenants = {
        issuer: _strings(values, f"issuer tenants for {issuer}")
        for issuer, values in sorted(tenants.items())
    }
    for field in ("maximum_lifetime_ms", "maximum_review_age_ms"):
        value = candidate[field]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"evaluation trust policy {field} must be a positive integer")
    return {
        "schema_version": EVALUATION_TRUST_POLICY_SCHEMA_VERSION,
        "allowed_issuers": allowed,
        "issuer_tenants": normalized_tenants,
        "revoked_key_ids": revoked_keys,
        "revoked_proof_hashes": revoked_proofs,
        "maximum_lifetime_ms": candidate["maximum_lifetime_ms"],
        "maximum_review_age_ms": candidate["maximum_review_age_ms"],
    }


def evaluation_trust_policy_hash(policy: dict[str, Any]) -> str:
    return stable_hash(normalize_evaluation_trust_policy(policy))


def verifier_arguments(policy: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_evaluation_trust_policy(policy)
    return {
        "allowed_issuers": frozenset(normalized["allowed_issuers"]) or None,
        "issuer_tenants": {
            issuer: frozenset(tenants)
            for issuer, tenants in normalized["issuer_tenants"].items()
        } or None,
        "revoked_key_ids": frozenset(normalized["revoked_key_ids"]),
        "revoked_proof_hashes": frozenset(normalized["revoked_proof_hashes"]),
        "maximum_lifetime_ms": normalized["maximum_lifetime_ms"],
        "maximum_review_age_ms": normalized["maximum_review_age_ms"],
    }


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"evaluation trust policy {label} are invalid")
    return sorted(set(value))
