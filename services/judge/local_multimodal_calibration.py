"""Fail-closed local multimodal golden regression and probe rotation markers."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .result_persistence import stable_hash


GOLDEN_SCHEMA_VERSION = "a2.local_multimodal_golden.v1"


def build_credential_rotation_marker(credential: str, *, provider_id: str) -> str:
    """Return a non-reversible, provider-bound marker without persisting the secret."""
    if not isinstance(credential, str) or not credential:
        raise ValueError("credential is required")
    if not isinstance(provider_id, str) or not provider_id:
        raise ValueError("provider_id is required")
    digest = hmac.new(
        b"ashr-a2-credential-rotation-marker-v1",
        f"{provider_id}\0{credential}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:{digest}"


def evaluate_local_multimodal_golden(
    *,
    golden_case: dict[str, Any],
    structured_output: dict[str, Any] | None,
    smoke_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate exact semantic fields; smoke callability can never imply calibration."""
    expected = golden_case.get("expected")
    required_fields = golden_case.get("required_semantic_fields")
    blockers: list[str] = []
    if golden_case.get("schema_version") != GOLDEN_SCHEMA_VERSION:
        blockers.append("unsupported_golden_schema")
    if not isinstance(expected, dict) or not isinstance(required_fields, list) or not required_fields:
        blockers.append("invalid_golden_case")
    if smoke_evidence is not None:
        blockers.append("smoke_evidence_has_no_calibration_authority")
    if not isinstance(structured_output, dict):
        blockers.append("structured_output_missing")
        structured_output = {}

    field_results = {}
    if isinstance(expected, dict) and isinstance(required_fields, list):
        for field in required_fields:
            name = str(field)
            present = name in structured_output
            matched = present and structured_output.get(name) == expected.get(name)
            field_results[name] = {"present": present, "matched": matched}
            if not present:
                blockers.append(f"missing_semantic_field:{name}")
            elif not matched:
                blockers.append(f"golden_mismatch:{name}")

    blockers = sorted(set(blockers))
    passed = not blockers
    return {
        "schema_version": "a2.local_multimodal_golden_result.v1",
        "case_id": str(golden_case.get("case_id") or ""),
        "golden_case_hash": stable_hash(golden_case),
        "structured_output_hash": stable_hash(structured_output) if structured_output else "",
        "field_results": field_results,
        "regression_status": "passed" if passed else "blocked",
        "calibration_state": "golden_passed" if passed else "uncalibrated",
        "release_authority": False,
        "human_review_required": not passed,
        "blockers": blockers,
        "public_safe": True,
    }
