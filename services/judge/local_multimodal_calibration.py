"""Fail-closed local multimodal golden regression and probe rotation markers."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from .result_persistence import stable_hash


GOLDEN_SCHEMA_VERSION = "a2.local_multimodal_golden.v1"
GOLDEN_RESULT_SCHEMA_VERSION = "a2.local_multimodal_golden_result.v1"
GOLDEN_SUITE_SCHEMA_VERSION = "a2.local_multimodal_golden_suite.v1"
DISAGREEMENT_SCHEMA_VERSION = "a2.multimodal_disagreement_receipt.v1"
DISAGREEMENT_REVIEW_SCHEMA_VERSION = "a2.multimodal_disagreement_review.v1"


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
    runtime_binding: dict[str, str] | None = None,
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
    governed_binding = golden_case.get("binding")
    if governed_binding is not None:
        if not isinstance(governed_binding, dict) or set(governed_binding) != {
            "model_digest",
            "prompt_hash",
            "generation_options_hash",
            "artifact_hash",
        }:
            blockers.append("invalid_golden_binding")
        elif not isinstance(runtime_binding, dict):
            blockers.append("runtime_binding_missing")
        else:
            for field, expected_value in governed_binding.items():
                if runtime_binding.get(field) != expected_value:
                    blockers.append(f"golden_binding_mismatch:{field}")
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
        "schema_version": GOLDEN_RESULT_SCHEMA_VERSION,
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


def aggregate_local_multimodal_golden_suite(
    *,
    results: list[dict[str, Any]],
    minimum_pass_rate: float,
    maximum_abstention_rate: float,
    safety_critical_case_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate governed case results without discarding case-level provenance."""
    if not results:
        raise ValueError("golden suite requires at least one result")
    if not 0 <= minimum_pass_rate <= 1 or not 0 <= maximum_abstention_rate <= 1:
        raise ValueError("golden suite thresholds must be within 0..1")
    if any(item.get("schema_version") != GOLDEN_RESULT_SCHEMA_VERSION for item in results):
        raise ValueError("golden suite contains an unsupported result")
    case_ids = [str(item.get("case_id") or "") for item in results]
    if any(not case_id for case_id in case_ids):
        raise ValueError("golden suite requires non-empty case ids")
    case_result_hashes = [stable_hash(item) for item in results]
    if len(set(case_result_hashes)) != len(case_result_hashes):
        raise ValueError("golden suite contains duplicate case result hashes")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("golden suite contains duplicate case ids")
    safety_ids = sorted(set(safety_critical_case_ids or []))
    unknown_safety_ids = sorted(set(safety_ids) - set(case_ids))
    if unknown_safety_ids:
        raise ValueError("safety-critical case id is absent from the suite")

    passed = sum(item.get("regression_status") == "passed" for item in results)
    abstained = sum("structured_output_missing" in (item.get("blockers") or []) for item in results)
    pass_rate = passed / len(results)
    abstention_rate = abstained / len(results)
    blockers = []
    if pass_rate < minimum_pass_rate:
        blockers.append("minimum_pass_rate_not_met")
    if abstention_rate > maximum_abstention_rate:
        blockers.append("maximum_abstention_rate_exceeded")
    failed_safety_ids = sorted(
        item["case_id"]
        for item in results
        if item["case_id"] in safety_ids and item.get("regression_status") != "passed"
    )
    if failed_safety_ids:
        blockers.append("safety_critical_case_failed")
    return {
        "schema_version": GOLDEN_SUITE_SCHEMA_VERSION,
        "case_count": len(results),
        "passed_count": passed,
        "abstained_count": abstained,
        "pass_rate": pass_rate,
        "abstention_rate": abstention_rate,
        "minimum_pass_rate": minimum_pass_rate,
        "maximum_abstention_rate": maximum_abstention_rate,
        "case_result_hashes": case_result_hashes,
        "safety_critical_case_ids": safety_ids,
        "failed_safety_critical_case_ids": failed_safety_ids,
        "status": "passed" if not blockers else "blocked",
        "release_authority": False,
        "human_review_required": bool(blockers),
        "blockers": blockers,
        "public_safe": True,
    }


def build_multimodal_disagreement_receipt(
    *,
    local_result: dict[str, Any],
    cloud_result: dict[str, Any],
    local_model_binding: dict[str, str] | None = None,
    cloud_model_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Classify comparable semantic disagreement separately from Provider availability."""
    local_status = str(local_result.get("status") or "")
    cloud_status = str(cloud_result.get("status") or "")
    local_output_hash = str(local_result.get("structured_output_hash") or "")
    cloud_output_hash = str(cloud_result.get("structured_output_hash") or "")
    blockers: list[str] = []
    required_binding_fields = {"provider_id", "model_id", "model_version"}
    bindings_valid = all(
        isinstance(binding, dict)
        and set(binding) == required_binding_fields
        and all(isinstance(value, str) and value for value in binding.values())
        for binding in (local_model_binding, cloud_model_binding)
    )
    if not bindings_valid:
        state = "not_comparable"
        blockers.append("model_binding_missing_or_invalid")
    elif cloud_status == "authentication_failed":
        state = "cloud_unavailable"
        blockers.append("cloud_authentication_failed")
    elif local_status != "completed":
        state = "local_output_missing"
        blockers.append("local_output_not_comparable")
    elif cloud_status != "completed":
        state = "cloud_unavailable"
        blockers.append("cloud_output_not_comparable")
    elif not local_output_hash or not cloud_output_hash:
        state = "not_comparable"
        blockers.append("structured_output_hash_missing")
    elif local_output_hash == cloud_output_hash:
        state = "agreement"
    else:
        state = "semantic_disagreement"
        blockers.append("human_review_required")
    return {
        "schema_version": DISAGREEMENT_SCHEMA_VERSION,
        "state": state,
        "local_result_hash": stable_hash(local_result),
        "cloud_result_hash": stable_hash(cloud_result),
        "local_model_binding": dict(local_model_binding or {}),
        "cloud_model_binding": dict(cloud_model_binding or {}),
        "semantic_comparison_performed": state in {"agreement", "semantic_disagreement"},
        "release_authority": False,
        "human_review_required": bool(blockers),
        "blockers": blockers,
        "public_safe": True,
    }


def build_multimodal_disagreement_review_packet(receipt: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic, public-safe human review packet for a real disagreement."""
    if receipt.get("schema_version") != DISAGREEMENT_SCHEMA_VERSION:
        raise ValueError("unsupported disagreement receipt")
    if receipt.get("state") != "semantic_disagreement":
        raise ValueError("review packet requires semantic disagreement")
    packet_core = {
        "schema_version": DISAGREEMENT_REVIEW_SCHEMA_VERSION,
        "receipt_hash": stable_hash(receipt),
        "local_result_hash": receipt["local_result_hash"],
        "cloud_result_hash": receipt["cloud_result_hash"],
        "local_model_binding": dict(receipt["local_model_binding"]),
        "cloud_model_binding": dict(receipt["cloud_model_binding"]),
        "review_reason": "semantic_disagreement",
        "release_authority": False,
        "public_safe": True,
    }
    return {**packet_core, "review_packet_hash": stable_hash(packet_core)}


def evaluate_provider_fallback(
    *,
    primary_result: dict[str, Any],
    fallback_result: dict[str, Any],
    fallback_calibration_state: str,
) -> dict[str, Any]:
    """A fallback may preserve availability but cannot manufacture release authority."""
    fallback_completed = fallback_result.get("status") == "completed"
    calibrated = fallback_calibration_state == "golden_passed"
    usable_for_review = fallback_completed and calibrated
    blockers = []
    if primary_result.get("status") != "completed":
        blockers.append("primary_provider_failed")
    if not fallback_completed:
        blockers.append("fallback_provider_failed")
    if not calibrated:
        blockers.append("fallback_not_calibrated")
    return {
        "schema_version": "a2.provider_fallback_evaluation.v1",
        "primary_result_hash": stable_hash(primary_result),
        "fallback_result_hash": stable_hash(fallback_result),
        "fallback_calibration_state": fallback_calibration_state,
        "usable_for_review": usable_for_review,
        "release_authority": False,
        "status": "review_available" if usable_for_review else "blocked",
        "blockers": sorted(set(blockers)),
        "public_safe": True,
    }
