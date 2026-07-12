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
FALLBACK_SCHEMA_VERSION = "a2.provider_fallback_evaluation.v1"
REPAIR_SCHEMA_VERSION = "a2.structured_output_repair.v1"
LOCAL_RESOURCE_SCHEMA_VERSION = "a2.local_model_resource_observation.v1"


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

    severity_by_field = dict(golden_case.get("field_severity") or {})
    field_results = {}
    if isinstance(expected, dict) and isinstance(required_fields, list):
        for field in required_fields:
            name = str(field)
            present = name in structured_output
            matched = present and structured_output.get(name) == expected.get(name)
            severity = str(severity_by_field.get(name) or ("safety" if name == "safety_risk" else "semantic"))
            field_results[name] = {"present": present, "matched": matched, "severity": severity}
            if not present:
                blockers.append(f"missing_semantic_field:{name}")
                if severity == "safety":
                    blockers.append(f"safety_field_missing:{name}")
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


def govern_structured_output_repair(
    *,
    original_output: dict[str, Any],
    required_fields: list[str],
    repair_policy: dict[str, Any] | None = None,
    expected_repair_policy_hash: str | None = None,
    reviewer_identity_hash: str | None = None,
) -> dict[str, Any]:
    """Record deterministic repair explicitly; never replace the original observation silently."""
    missing = sorted(str(field) for field in required_fields if str(field) not in original_output)
    policy = dict(repair_policy or {})
    repair_policy_hash = stable_hash(policy) if policy else ""
    allowed_defaults = dict(policy.get("allowed_defaults") or {})
    repair_allowed = policy.get("mode") == "deterministic_defaults" and bool(missing)
    unsafe_safety_defaults = sorted(
        field
        for field in missing
        if field == "safety_risk" and field in allowed_defaults and allowed_defaults[field] != "unknown"
    )
    policy_hash_matches = expected_repair_policy_hash in {None, repair_policy_hash}
    can_repair = (
        repair_allowed
        and all(field in allowed_defaults for field in missing)
        and not unsafe_safety_defaults
        and policy_hash_matches
    )
    repaired = dict(original_output)
    if can_repair:
        for field in missing:
            repaired[field] = allowed_defaults[field]
    blockers = []
    if expected_repair_policy_hash is not None and not policy_hash_matches:
        blockers.append("repair_policy_hash_mismatch")
    if unsafe_safety_defaults:
        blockers.append("unsafe_safety_default_forbidden")
    if missing and not repair_allowed:
        blockers.append("repair_policy_not_configured")
    elif missing and not can_repair and not blockers:
        blockers.append("deterministic_repair_not_available")
    reviewer_bound = (
        isinstance(reviewer_identity_hash, str)
        and reviewer_identity_hash.startswith("sha256:")
        and len(reviewer_identity_hash) == 71
    )
    calibration_entry_eligible = can_repair and reviewer_bound
    if can_repair and not reviewer_bound:
        blockers.append("reviewer_identity_hash_required_for_calibration")
    return {
        "schema_version": REPAIR_SCHEMA_VERSION,
        "state": "repaired_for_review" if can_repair else ("blocked" if missing else "not_required"),
        "repair_policy_hash": repair_policy_hash,
        "expected_repair_policy_hash": expected_repair_policy_hash or "",
        "original_output_hash": stable_hash(original_output),
        "repaired_output_hash": stable_hash(repaired) if can_repair else "",
        "original_output": dict(original_output),
        "repaired_output": repaired if can_repair else None,
        "missing_required_fields": missing,
        "semantic_observation_modified": can_repair,
        "reviewer_identity_hash": reviewer_identity_hash or "",
        "calibration_entry_eligible": calibration_entry_eligible,
        "calibration_state": "uncalibrated",
        "release_authority": False,
        "human_review_required": bool(missing),
        "blockers": sorted(set(blockers)),
        "public_safe": True,
    }


def observe_local_model_resources(
    *,
    model_binding: dict[str, str],
    installed_bytes: int,
    wall_time_seconds: float,
    prompt_tokens: int,
    completion_tokens: int,
    maximum_latency_seconds: float,
    startup_class: str = "warm_start",
    cold_start_slo_state: str | None = None,
    telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create public-safe resource evidence and fail closed on excessive local Judge latency."""
    required = {"provider_id", "model_id", "model_version"}
    if set(model_binding) != required or any(not isinstance(v, str) or not v for v in model_binding.values()):
        raise ValueError("local resource observation requires exact model binding")
    numeric = (installed_bytes, wall_time_seconds, prompt_tokens, completion_tokens, maximum_latency_seconds)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 for value in numeric):
        raise ValueError("local resource observation values must be non-negative numbers")
    if maximum_latency_seconds <= 0:
        raise ValueError("maximum latency must be positive")
    if startup_class not in {"cold_start", "warm_start"}:
        raise ValueError("startup class must be cold_start or warm_start")
    if cold_start_slo_state not in {None, "within_limit", "incomplete"}:
        raise ValueError("cold start SLO state is invalid")
    telemetry = dict(telemetry or {})
    allowed_telemetry = {"peak_memory_bytes", "load_duration_seconds", "eval_duration_seconds"}
    if set(telemetry) - allowed_telemetry:
        raise ValueError("unsupported local telemetry field")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
        for value in telemetry.values()
    ):
        raise ValueError("local telemetry values must be non-negative numbers")
    latency_exceeded = wall_time_seconds > maximum_latency_seconds
    inherited_cold_failure = startup_class == "warm_start" and cold_start_slo_state == "incomplete"
    blockers = []
    if latency_exceeded:
        blockers.append("local_judge_latency_exceeded")
    if inherited_cold_failure:
        blockers.append("cold_start_slo_failure_not_concealed")
    return {
        "schema_version": LOCAL_RESOURCE_SCHEMA_VERSION,
        "model_binding": dict(model_binding),
        "installed_bytes": installed_bytes,
        "wall_time_seconds": wall_time_seconds,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "maximum_latency_seconds": maximum_latency_seconds,
        "startup_class": startup_class,
        "cold_start_slo_state": cold_start_slo_state or (
            "incomplete" if startup_class == "cold_start" and latency_exceeded else "within_limit"
        ),
        "telemetry": telemetry,
        "latency_policy_state": "incomplete" if latency_exceeded or inherited_cold_failure else "within_limit",
        "evaluation_eligible": not latency_exceeded and not inherited_cold_failure,
        "release_authority": False,
        "blockers": blockers,
        "public_safe": True,
    }


def build_evidence_evaluation_identity(
    *,
    evidence_snapshot_hash: str,
    policy_version: str,
    golden_suite_hash: str,
) -> str:
    """Keep the A2 semantic evaluation identity independent from Provider credentials."""
    if not all(isinstance(value, str) and value for value in (
        evidence_snapshot_hash,
        policy_version,
        golden_suite_hash,
    )):
        raise ValueError("evaluation identity requires immutable evidence, policy, and Golden bindings")
    return stable_hash(
        {
            "evidence_snapshot_hash": evidence_snapshot_hash,
            "policy_version": policy_version,
            "golden_suite_hash": golden_suite_hash,
        }
    )


def validate_a3_decision_consumption(
    *,
    committed_decision: dict[str, Any],
    consumed_decision: dict[str, Any],
) -> dict[str, Any]:
    """A3 may consume the exact committed A2 decision but may not recompute or mutate it."""
    committed_hash = stable_hash(committed_decision)
    supplied_hash = str(consumed_decision.get("a2_committed_decision_hash") or "")
    forbidden = sorted(
        set(consumed_decision)
        & {"recomputed_status", "recomputed_score", "recomputed_policy_result", "release_authority"}
    )
    blockers = []
    if supplied_hash != committed_hash:
        blockers.append("a2_committed_decision_hash_mismatch")
    if forbidden:
        blockers.append("a3_recomputed_release_state_forbidden")
    committed_status = str(committed_decision.get("status") or "")
    displayed_status = str(consumed_decision.get("display_status") or "")
    if displayed_status and displayed_status != committed_status:
        blockers.append("a3_display_status_mismatch")
    return {
        "schema_version": "a2.a3_decision_consumption_validation.v1",
        "committed_decision_hash": committed_hash,
        "consumption_valid": not blockers,
        "committed_status": committed_status,
        "displayed_status": displayed_status,
        "release_authority": False,
        "forbidden_fields": forbidden,
        "blockers": blockers,
        "public_safe": True,
    }


def evaluate_provider_fallback(
    *,
    primary_result: dict[str, Any],
    fallback_result: dict[str, Any],
    fallback_calibration_state: str,
    primary_model_binding: dict[str, str] | None = None,
    fallback_model_binding: dict[str, str] | None = None,
    fallback_calibration_binding: dict[str, str] | None = None,
    runtime_calibration_binding: dict[str, str] | None = None,
) -> dict[str, Any]:
    """A fallback may preserve availability but cannot manufacture release authority."""
    model_fields = {"provider_id", "model_id", "model_version"}
    calibration_fields = {"prompt_hash", "generation_options_hash", "artifact_hash"}
    model_bindings_valid = all(
        isinstance(binding, dict)
        and set(binding) == model_fields
        and all(isinstance(value, str) and value for value in binding.values())
        for binding in (primary_model_binding, fallback_model_binding)
    )
    calibration_bindings_valid = all(
        isinstance(binding, dict)
        and set(binding) == calibration_fields
        and all(isinstance(value, str) and value for value in binding.values())
        for binding in (fallback_calibration_binding, runtime_calibration_binding)
    )
    calibration_binding_matches = (
        calibration_bindings_valid and fallback_calibration_binding == runtime_calibration_binding
    )
    fallback_completed = fallback_result.get("status") == "completed"
    calibrated = (
        fallback_calibration_state == "golden_passed"
        and model_bindings_valid
        and calibration_binding_matches
    )
    usable_for_review = fallback_completed and calibrated
    blockers = []
    if primary_result.get("status") != "completed":
        blockers.append("primary_provider_failed")
    if not fallback_completed:
        blockers.append("fallback_provider_failed")
    if not model_bindings_valid:
        blockers.append("fallback_model_binding_missing_or_invalid")
    if not calibration_bindings_valid:
        blockers.append("fallback_calibration_binding_missing_or_invalid")
    elif not calibration_binding_matches:
        blockers.append("fallback_calibration_binding_mismatch")
    if fallback_calibration_state != "golden_passed":
        blockers.append("fallback_not_calibrated")
    return {
        "schema_version": FALLBACK_SCHEMA_VERSION,
        "primary_result_hash": stable_hash(primary_result),
        "fallback_result_hash": stable_hash(fallback_result),
        "primary_model_binding": dict(primary_model_binding or {}),
        "fallback_model_binding": dict(fallback_model_binding or {}),
        "fallback_calibration_binding": dict(fallback_calibration_binding or {}),
        "runtime_calibration_binding": dict(runtime_calibration_binding or {}),
        "fallback_calibration_state": fallback_calibration_state,
        "usable_for_review": usable_for_review,
        "release_authority": False,
        "status": "review_available" if usable_for_review else "blocked",
        "blockers": sorted(set(blockers)),
        "public_safe": True,
    }
