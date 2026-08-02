from __future__ import annotations

import json

import pytest

from services.judge.result_persistence import stable_hash
from services.judge.uncertainty_evaluation import (
    SCHEMA_VERSION,
    evaluate_with_uncertainty_routing,
)
from tests.a2.test_release_decision_orchestrator import (
    KEY,
    NOW,
    gateway,
    grounded_gateway,
    grounded_request,
    request,
)
from tests.a2.test_uncertainty_router import (
    _label,
    _report,
    _uncalibrated_label,
)


def _request() -> dict:
    return request()


def _calls(provider_gateway) -> int:
    return provider_gateway.adapters["fake"].calls


def _failure_label(*, modality: str = "text", evidence_locations=None) -> dict:
    return _label(
        case_id="case-1",
        modality=modality,
        passed=False,
        failure_type="wrong_intent",
        failure_types=["wrong_intent"],
        severity="medium",
        failed_action="final_answer",
        evidence_locations=evidence_locations
        or [
            {
                "modality": "text",
                "source_hash": stable_hash({"source": "text"}),
                "start_char": 0,
                "end_char": 12,
            }
        ],
        confidence=0.90,
        failure_probability=0.80,
        release_recommendation="retest",
    )


def _media_label(modality: str) -> dict:
    locations = {
        "image": {
            "modality": "image",
            "source_hash": stable_hash({"source": "image"}),
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 1,
            "coordinate_space": "normalized",
        },
        "audio": {
            "modality": "audio",
            "source_hash": stable_hash({"source": "audio"}),
            "start_ms": 0,
            "end_ms": 1000,
        },
        "video": {
            "modality": "video",
            "source_hash": stable_hash({"source": "video"}),
            "start_ms": 0,
            "end_ms": 1000,
            "start_frame": 0,
            "end_frame": 24,
        },
        "document": {
            "modality": "document",
            "source_hash": stable_hash({"source": "document"}),
            "document_type": "pdf",
            "page": 1,
        },
    }
    return _label(
        case_id="case-1",
        modality=modality,
        evidence_locations=[locations[modality]],
    )


def test_calibrated_low_risk_case_skips_provider_and_keeps_hash_bound_route():
    provider_gateway = gateway(failure="must-not-call")

    result = evaluate_with_uncertainty_routing(
        _request(),
        label=_label(case_id="case-1"),
        calibration_report=_report(),
        releasefoundry_available=True,
        releasefoundry_mutation_authorized=True,
        gateway=provider_gateway,
        key_resolver=lambda _: KEY,
        now_unix_ms=NOW,
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["execution"]["status"] == "resolved_by_local_judge"
    assert result["execution"]["provider_call_attempted"] is False
    assert result["execution"]["provider_called"] is False
    assert _calls(provider_gateway) == 0
    assert result["decision"]["release_action"] == "allow"
    assert result["decision"]["automatic_release_allowed"] is True
    assert result["decision"]["label_hash"] == result["final_route"]["label_hash"]
    assert result["decision"]["route_hash"] == result["final_route"]["route_hash"]
    assert result["evaluation_hash"] == stable_hash(
        {key: value for key, value in result.items() if key != "evaluation_hash"}
    )


def test_uncertain_case_calls_generic_teacher_only_after_external_mutation_authorization():
    candidate = grounded_request()
    provider_gateway = grounded_gateway(candidate)
    label = _uncalibrated_label(
        case_id="case-1",
        confidence=0.55,
        failure_probability=0.49,
    )

    pending = evaluate_with_uncertainty_routing(
        candidate,
        label=label,
        calibration_report=None,
        releasefoundry_available=True,
        gateway=provider_gateway,
        key_resolver=lambda _: KEY,
        now_unix_ms=NOW,
    )
    completed = evaluate_with_uncertainty_routing(
        candidate,
        label=label,
        calibration_report=None,
        releasefoundry_available=True,
        releasefoundry_mutation_authorized=True,
        gateway=provider_gateway,
        key_resolver=lambda _: KEY,
        now_unix_ms=NOW,
    )

    assert pending["execution"]["status"] == (
        "awaiting_external_mutation_authorization"
    )
    assert pending["execution"]["provider_call_attempted"] is False
    assert completed["execution"]["status"] == "teacher_result_observed"
    assert completed["execution"]["provider_call_attempted"] is True
    assert completed["execution"]["provider_called"] is True
    assert completed["execution"]["facade_retry_count"] == 0
    assert completed["execution"]["generic_teacher_configured"] is True
    assert completed["execution"]["official_releasefoundry_adapter_configured"] is False
    assert completed["execution"]["official_releasefoundry_receipt_observed"] is False
    assert _calls(provider_gateway) == 1
    assert completed["final_route"]["signals"]["releasefoundry_comparison"] == "not_observed"
    assert completed["final_route"]["signals"]["teacher_state"] == "consensus"
    assert completed["decision"]["next_destination"] == "human_review"
    assert completed["decision"]["automatic_release_allowed"] is False
    assert completed["teacher_evaluation"]["source"] == {
        "provider_id": "unit",
        "model_id": "semantic-1",
        "protocol": "fake",
        "teacher_authority": "generic_provider",
        "transport_mode": "provider_gateway",
        "submitted_modalities": ["text"],
        "caller_native_media_submitted": False,
        "official_releasefoundry_receipt_observed": False,
    }


def test_releasefoundry_unavailable_preserves_uncertain_human_review_without_call():
    provider_gateway = gateway(failure="must-not-call")

    result = evaluate_with_uncertainty_routing(
        _request(),
        label=_uncalibrated_label(
            case_id="case-1",
            confidence=0.55,
            failure_probability=0.49,
        ),
        calibration_report=None,
        releasefoundry_available=False,
        releasefoundry_mutation_authorized=True,
        gateway=provider_gateway,
        key_resolver=lambda _: KEY,
        now_unix_ms=NOW,
    )

    assert result["execution"]["status"] == "releasefoundry_unavailable"
    assert result["execution"]["provider_call_attempted"] is False
    assert result["decision"]["next_destination"] == "human_review"
    assert result["decision"]["release_action"] == "human_review"
    assert result["decision"]["resolution_state"] == "uncertain"
    assert result["decision"]["next_destination"] == "human_review"
    assert result["decision"]["automatic_release_allowed"] is False
    assert _calls(provider_gateway) == 0


def test_local_generic_teacher_conflict_cannot_impersonate_releasefoundry_or_pass():
    candidate = grounded_request()
    provider_gateway = grounded_gateway(candidate)

    result = evaluate_with_uncertainty_routing(
        candidate,
        label=_failure_label(),
        calibration_report=_report(),
        releasefoundry_available=True,
        releasefoundry_mutation_authorized=True,
        gateway=provider_gateway,
        key_resolver=lambda _: KEY,
        now_unix_ms=NOW,
    )

    assert _calls(provider_gateway) == 1
    assert result["execution"]["status"] == "teacher_result_observed"
    assert result["execution"]["official_releasefoundry_receipt_observed"] is False
    assert result["final_route"]["signals"]["releasefoundry_comparison"] == "not_observed"
    assert result["final_route"]["signals"]["teacher_state"] == "conflict"
    assert result["decision"]["next_destination"] == "human_review"
    assert result["decision"]["release_action"] == "human_review"
    assert result["decision"]["automatic_release_allowed"] is False
    assert "teacher_conflict" in (
        result["final_route"]["decision"]["reason_codes"]
    )
    assert "local_releasefoundry_disagreement" not in (
        result["final_route"]["decision"]["reason_codes"]
    )


@pytest.mark.parametrize(
    ("modality", "release_modality", "generated_state"),
    [
        ("image", "image", "verified_non_qualifying"),
        ("audio", "audio", "verified_non_qualifying"),
        ("document", "file", "verified_non_qualifying"),
    ],
)
def test_generated_media_capability_does_not_unlock_caller_native_release(
    modality,
    release_modality,
    generated_state,
):
    result = evaluate_with_uncertainty_routing(
        _request(),
        label=_media_label(modality),
        calibration_report=_report(),
        releasefoundry_available=True,
    )

    boundary = result["media_release_gate"]["modality_boundaries"][0]
    assert result["media_release_gate"]["qualified"] is False
    assert result["decision"]["release_action"] == "retest"
    assert result["decision"]["automatic_release_allowed"] is False
    assert boundary["modality"] == release_modality
    assert boundary["releasefoundry_generated_artifact_state"] == generated_state
    assert boundary["releasefoundry_caller_native_submission_state"] == (
        "provider_surface_missing"
    )
    assert result["metadata"][
        "generated_media_proves_caller_native_submission"
    ] is False


def test_video_provider_unverified_never_calls_releasefoundry_or_auto_releases():
    provider_gateway = gateway(failure="must-not-call")

    result = evaluate_with_uncertainty_routing(
        _request(),
        label=_media_label("video"),
        calibration_report=_report(),
        releasefoundry_available=True,
        releasefoundry_mutation_authorized=True,
        gateway=provider_gateway,
        key_resolver=lambda _: KEY,
        now_unix_ms=NOW,
    )

    boundary = result["media_release_gate"]["modality_boundaries"][0]
    assert result["execution"]["releasefoundry_declared_available"] is True
    assert result["execution"]["releasefoundry_effectively_available"] is False
    assert result["execution"]["provider_call_attempted"] is False
    assert _calls(provider_gateway) == 0
    assert result["decision"]["release_action"] == "human_review"
    assert result["decision"]["automatic_release_allowed"] is False
    assert boundary["releasefoundry_generated_artifact_state"] == "provider_unverified"
    assert result["metadata"]["video_provider_state"] == "provider_unverified"


def test_untrusted_teacher_blockers_are_not_treated_as_teacher_consensus():
    provider_gateway = gateway(
        response={
            "output_text": json.dumps(
                {
                    "passed": True,
                    "score": 0.98,
                    "reason": "evidence supports release",
                    "failure_classes": [],
                    "evidence_refs": ["snapshot"],
                    "abstained": False,
                }
            ),
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
    )
    candidate = _request()
    candidate["evaluation_quality_proof"]["signature"] = "tampered"

    result = evaluate_with_uncertainty_routing(
        candidate,
        label=_uncalibrated_label(
            case_id="case-1",
            confidence=0.55,
            failure_probability=0.49,
        ),
        calibration_report=None,
        releasefoundry_available=True,
        releasefoundry_mutation_authorized=True,
        gateway=provider_gateway,
        key_resolver=lambda _: KEY,
        now_unix_ms=NOW,
    )

    assert result["execution"]["status"] == "teacher_result_unusable"
    assert result["execution"]["official_releasefoundry_receipt_observed"] is False
    assert result["final_route"]["signals"]["releasefoundry_comparison"] == "not_observed"
    assert result["final_route"]["signals"]["teacher_state"] == "not_evaluated"
    assert result["final_route"]["decision"]["next_destination"] == "human_review"
    assert result["decision"]["automatic_release_allowed"] is False


def test_releasefoundry_availability_requires_a_real_boolean_before_routing():
    provider_gateway = gateway(failure="must-not-call")

    with pytest.raises(ValueError, match="releasefoundry_available_must_be_boolean"):
        evaluate_with_uncertainty_routing(
            _request(),
            label=_label(case_id="case-1"),
            calibration_report=_report(),
            releasefoundry_available="false",
            releasefoundry_mutation_authorized=True,
            gateway=provider_gateway,
            key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
        )

    assert _calls(provider_gateway) == 0


def test_label_is_bound_to_requested_case_before_any_provider_call():
    provider_gateway = gateway(failure="must-not-call")

    with pytest.raises(ValueError, match="label_request_case_id_mismatch"):
        evaluate_with_uncertainty_routing(
            request(),
            label=_uncalibrated_label(),
            calibration_report=None,
            releasefoundry_available=True,
            releasefoundry_mutation_authorized=True,
            gateway=provider_gateway,
            key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
        )

    assert _calls(provider_gateway) == 0
