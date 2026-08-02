from __future__ import annotations

from copy import deepcopy

import pytest

from services.judge.probability_calibration import (
    SCHEMA_VERSION as CALIBRATION_REPORT_SCHEMA_VERSION,
)
from services.judge.result_persistence import stable_hash
from services.judge.uncertainty_router import (
    SCHEMA_VERSION,
    UncertaintyRoutingError,
    build_uncertainty_route,
)
from services.judge.unified_label import build_unified_judge_label


def _hash(value: object) -> str:
    return stable_hash({"value": value})


def _label(**overrides) -> dict:
    values = {
        "label_id": "label-001",
        "case_id": "case-001",
        "modality": "text",
        "passed": True,
        "failure_type": "none",
        "failure_types": ["none"],
        "severity": "none",
        "failed_action": "",
        "evidence_locations": [
            {
                "modality": "text",
                "source_hash": _hash("source"),
                "start_char": 0,
                "end_char": 12,
            }
        ],
        "confidence": 0.95,
        "failure_probability": 0.05,
        "probability_calibration": {
            "status": "calibrated",
            "method": "isotonic",
            "version": "a2-calibrator@1.0.0",
            "artifact_hash": _hash("calibrator"),
        },
        "release_recommendation": "allow",
        "reason": "The answer is supported by the cited input span.",
        "judge_id": "a2-text-judge",
        "judge_version": "1.0.0",
        "model_version": "a2-local-rm@4",
        "prompt_version": "judge-prompt-v8",
        "input_hash": _hash("input"),
        "output_hash": _hash("output"),
    }
    values.update(overrides)
    return build_unified_judge_label(**values)


def _report(**overrides) -> dict:
    def metric(case_count: int, ece: float) -> dict:
        return {
            "case_count": case_count,
            "expected_calibration_error": ece,
            "maximum_calibration_error": ece,
            "brier_score": 0.01,
            "negative_log_likelihood": 0.02,
            "mean_probability": 0.5,
            "empirical_rate": 0.5,
            "reliability_bins": [],
        }

    report = {
        "schema_version": CALIBRATION_REPORT_SCHEMA_VERSION,
        "report_id": "a2-probability-calibration",
        "calibrator": {
            "calibrator_id": "a2-local-reward-calibrator",
            "calibrator_version": "a2-calibrator@1.0.0",
            "method": "isotonic",
            "model_version": "a2-local-rm@4",
            "artifact_hash": _hash("calibrator"),
            "fitted_parameter_hash": _hash("parameters"),
            "fit_dataset_id": "a2-calibration-fit",
            "fit_dataset_hash": _hash("fit-dataset"),
            "fit_receipt_hash": _hash("fit-receipt"),
            "fit_receipt_verified": True,
        },
        "holdout": {
            "manifest_id": "a2-calibration-holdout",
            "manifest_hash": _hash("manifest"),
            "dataset_id": "a2-human-gold-holdout",
            "dataset_hash": _hash("holdout"),
            "case_count": 1000,
            "failed_count": 500,
            "passed_count": 500,
            "gold_authority": "human_adjudicated",
            "gold_receipt_hash": _hash("gold-receipt"),
            "gold_receipt_verified": True,
            "source_isolation_receipt_hash": _hash("isolation-receipt"),
            "source_isolation_verified": True,
        },
        "thresholds": {
            "ece": 0.03,
            "minimum_cases": 1000,
            "minimum_class_cases": 100,
            "bin_count": 10,
        },
        "metrics": {
            "overall": metric(1000, 0.02),
            "class_conditional": {
                "fail": metric(500, 0.02),
                "pass": metric(500, 0.02),
            },
            "per_modality": {},
            "per_severity": {},
        },
        "calibration_gate": {
            "status": "calibrated",
            "eligible_for_unified_label_calibrated_status": True,
            "blockers": [],
            "automatic_model_promotion_allowed": False,
            "requires_blind_version_comparison": True,
        },
        "observation_bindings": [
            {
                "case_id": f"case-{index:04d}",
                "source_hash": _hash(f"source-{index}"),
                "source_group_hash": _hash(f"group-{index}"),
                "prediction_hash": _hash(f"prediction-{index}"),
            }
            for index in range(1000)
        ],
        "metadata": {
            "public_safe": True,
            "deterministic": True,
            "raw_inputs_recorded": False,
            "raw_outputs_recorded": False,
            "does_not_fit_or_promote_models": True,
            "calibration_requires_human_gold": True,
            "train_holdout_source_overlap_allowed": False,
        },
    }
    for path, value in overrides.items():
        target = report
        parts = path.split("__")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = value
    report["report_hash"] = stable_hash(report)
    return report


def _uncalibrated_label(**overrides) -> dict:
    values = {
        "probability_calibration": {
            "status": "uncalibrated",
            "method": "",
            "version": "",
            "artifact_hash": None,
        },
        "release_recommendation": "retest",
    }
    values.update(overrides)
    return _label(**values)


def test_resolves_calibrated_low_risk_case_locally_even_when_releasefoundry_is_down():
    route = build_uncertainty_route(
        label=_label(),
        calibration_report=_report(),
        releasefoundry_available=False,
    )

    assert route["schema_version"] == SCHEMA_VERSION
    assert route["calibration"]["status"] == "qualified"
    assert route["local_resolution_gate"]["eligible"] is True
    assert route["decision"] == {
        "resolution_state": "resolved",
        "next_destination": "local_judge",
        "resolution_basis": "calibrated_local_judge",
        "reason_codes": ["calibrated_low_risk_local_resolution"],
        "release_recommendation": "allow",
        "local_auto_resolution": True,
        "releasefoundry_teacher_call_recommended": False,
        "paid_releasefoundry_call_authorized": False,
        "requires_external_mutation_gate": False,
        "human_review_required": False,
        "automatic_release_allowed": True,
    }
    assert route["route_hash"] == stable_hash(
        {key: value for key, value in route.items() if key != "route_hash"}
    )


def test_resolves_low_risk_failure_locally_without_softening_release_action():
    label = _label(
        passed=False,
        failure_type="wrong_intent",
        failure_types=["wrong_intent"],
        severity="low",
        failed_action="final_answer",
        confidence=0.93,
        failure_probability=0.82,
        release_recommendation="restrict_capability",
    )
    route = build_uncertainty_route(
        label=label,
        calibration_report=_report(),
        releasefoundry_available=True,
    )

    assert route["decision"]["next_destination"] == "local_judge"
    assert route["decision"]["release_recommendation"] == "restrict_capability"
    assert route["decision"]["automatic_release_allowed"] is False


def test_uncalibrated_or_uncertain_case_routes_to_releasefoundry_without_authorizing_spend():
    route = build_uncertainty_route(
        label=_uncalibrated_label(confidence=0.58, failure_probability=0.48),
        calibration_report=None,
        releasefoundry_available=True,
    )

    assert route["calibration"]["status"] == "unqualified"
    assert route["decision"]["resolution_state"] == "uncertain"
    assert route["decision"]["next_destination"] == "releasefoundry_teacher"
    assert route["decision"]["release_recommendation"] == "retest"
    assert route["decision"]["releasefoundry_teacher_call_recommended"] is True
    assert route["decision"]["paid_releasefoundry_call_authorized"] is False
    assert route["decision"]["requires_external_mutation_gate"] is True


def test_valid_but_failed_calibration_report_routes_to_releasefoundry():
    report = _report()
    report["metrics"]["overall"]["expected_calibration_error"] = 0.20
    report["metrics"]["class_conditional"]["fail"][
        "expected_calibration_error"
    ] = 0.20
    report["metrics"]["class_conditional"]["pass"][
        "expected_calibration_error"
    ] = 0.20
    report["calibration_gate"] = {
        "status": "uncalibrated",
        "eligible_for_unified_label_calibrated_status": False,
        "blockers": [
            "failure_class_ece_above_threshold",
            "overall_ece_above_threshold",
            "pass_class_ece_above_threshold",
        ],
        "automatic_model_promotion_allowed": False,
        "requires_blind_version_comparison": True,
    }
    report.pop("report_hash")
    report["report_hash"] = stable_hash(report)

    route = build_uncertainty_route(
        label=_label(release_recommendation="staged_rollout"),
        calibration_report=report,
        releasefoundry_available=True,
    )

    assert route["calibration"]["status"] == "unqualified"
    assert route["decision"]["next_destination"] == "releasefoundry_teacher"
    assert "calibration_unqualified" in route["decision"]["reason_codes"]


def test_releasefoundry_unavailable_falls_back_to_human_instead_of_guessing():
    route = build_uncertainty_route(
        label=_uncalibrated_label(confidence=0.55, failure_probability=0.49),
        calibration_report=None,
        releasefoundry_available=False,
    )

    assert route["decision"]["resolution_state"] == "uncertain"
    assert route["decision"]["next_destination"] == "human_review"
    assert route["decision"]["human_review_required"] is True
    assert route["decision"]["automatic_release_allowed"] is False
    assert "releasefoundry_unavailable" in route["decision"]["reason_codes"]
    assert route["metadata"]["local_label_preserved_when_releasefoundry_unavailable"] is True


@pytest.mark.parametrize(
    "label_kwargs,route_kwargs,reason",
    [
        (
                {
                    "passed": False,
                    "failure_type": "unsafe_or_policy_violation",
                    "failure_types": ["unsafe_or_policy_violation"],
                "severity": "critical",
                "failed_action": "final_answer",
                "failure_probability": 0.99,
                "release_recommendation": "block",
            },
            {},
            "critical_severity",
        ),
        ({}, {"historical_critical_regression": True}, "historical_critical_regression"),
    ],
)
def test_critical_risk_routes_to_human_and_blocks(label_kwargs, route_kwargs, reason):
    route = build_uncertainty_route(
        label=_label(**label_kwargs),
        calibration_report=_report(),
        releasefoundry_available=True,
        **route_kwargs,
    )

    assert route["decision"]["next_destination"] == "human_review"
    assert route["decision"]["release_recommendation"] == "block"
    assert reason in route["decision"]["reason_codes"]
    assert route["active_learning"]["band"] == "critical"


@pytest.mark.parametrize(
    "route_kwargs,reason",
    [
        ({"releasefoundry_comparison": "disagrees"}, "local_releasefoundry_disagreement"),
        ({"teacher_state": "conflict"}, "teacher_conflict"),
    ],
)
def test_disagreement_and_teacher_conflict_require_human_review(
    route_kwargs,
    reason,
):
    route = build_uncertainty_route(
        label=_label(release_recommendation="staged_rollout"),
        calibration_report=_report(),
        releasefoundry_available=True,
        **route_kwargs,
    )

    assert route["decision"]["next_destination"] == "human_review"
    assert route["decision"]["release_recommendation"] == "human_review"
    assert reason in route["decision"]["reason_codes"]
    assert reason in route["active_learning"]["reasons"]


def test_incomplete_evidence_requires_human_retest():
    route = build_uncertainty_route(
        label=_label(release_recommendation="staged_rollout"),
        calibration_report=_report(),
        releasefoundry_available=True,
        evidence_complete=False,
    )

    assert route["decision"]["next_destination"] == "human_review"
    assert route["decision"]["release_recommendation"] == "retest"
    assert "evidence_incomplete" in route["decision"]["reason_codes"]


def test_medium_risk_uses_releasefoundry_then_accepts_nonconflicting_teacher_support():
    label = _label(
        passed=False,
        failure_type="wrong_intent",
        failure_types=["wrong_intent"],
        severity="medium",
        failed_action="final_answer",
        failure_probability=0.78,
        release_recommendation="retest",
    )
    pending = build_uncertainty_route(
        label=label,
        calibration_report=_report(),
        releasefoundry_available=True,
    )
    agreed = build_uncertainty_route(
        label=label,
        calibration_report=_report(),
        releasefoundry_available=True,
        releasefoundry_comparison="agrees",
    )

    assert pending["decision"]["next_destination"] == "releasefoundry_teacher"
    assert agreed["decision"]["next_destination"] == "local_judge"
    assert agreed["decision"]["resolution_basis"] == "local_releasefoundry_agreement"
    assert agreed["decision"]["local_auto_resolution"] is False
    assert agreed["decision"]["automatic_release_allowed"] is False


@pytest.mark.parametrize("flag", ["out_of_scope", "novel_failure_type"])
def test_out_of_scope_and_novel_cases_are_bought_from_releasefoundry_first(flag):
    route = build_uncertainty_route(
        label=_label(release_recommendation="staged_rollout"),
        calibration_report=_report(),
        releasefoundry_available=True,
        **{flag: True},
    )

    assert route["decision"]["next_destination"] == "releasefoundry_teacher"
    assert route["decision"]["paid_releasefoundry_call_authorized"] is False
    expected_reason = (
        "novel_failure_type"
        if flag == "novel_failure_type"
        else "local_judge_out_of_scope"
    )
    assert expected_reason in route["decision"]["reason_codes"]


def test_releasefoundry_agreement_is_insufficient_for_out_of_scope_or_novel_case():
    route = build_uncertainty_route(
        label=_label(release_recommendation="staged_rollout"),
        calibration_report=_report(),
        releasefoundry_available=True,
        releasefoundry_comparison="agrees",
        novel_failure_type=True,
    )

    assert route["decision"]["next_destination"] == "human_review"
    assert "releasefoundry_agreement_insufficient_for_case" in route["decision"]["reason_codes"]


@pytest.mark.parametrize(
    "report,code",
    [
        (_report(calibrator__model_version="other-model"), "calibration_model_version_mismatch"),
        (
            _report(calibrator__artifact_hash=_hash("other-calibrator")),
            "calibration_artifact_hash_mismatch",
        ),
        (
            _report(thresholds__minimum_cases=10),
            "calibration_case_threshold_too_permissive",
        ),
    ],
)
def test_rejects_mismatched_or_weakened_calibration_evidence(report, code):
    with pytest.raises(UncertaintyRoutingError, match=code):
        build_uncertainty_route(
            label=_label(),
            calibration_report=report,
            releasefoundry_available=True,
        )


def test_rejects_tampered_label_and_report():
    label = _label()
    label["confidence"] = 0.1
    with pytest.raises(UncertaintyRoutingError, match="unified_label_invalid"):
        build_uncertainty_route(
            label=label,
            calibration_report=_report(),
            releasefoundry_available=True,
        )

    report = _report()
    report["holdout"]["case_count"] = 999
    with pytest.raises(
        UncertaintyRoutingError,
        match="calibration_report_hash_mismatch",
    ):
        build_uncertainty_route(
            label=_label(),
            calibration_report=report,
            releasefoundry_available=True,
        )


def test_rejects_private_paths_invalid_signals_and_margin():
    with pytest.raises(
        UncertaintyRoutingError,
        match="private_or_secret_material_rejected",
    ):
        build_uncertainty_route(
            label=_label(),
            calibration_report=_report(),
            releasefoundry_available=True,
            route_id=r"C:\Users\Kaylee\private-route",
        )
    with pytest.raises(UncertaintyRoutingError, match="releasefoundry_comparison_invalid"):
        build_uncertainty_route(
            label=_label(),
            calibration_report=_report(),
            releasefoundry_available=True,
            releasefoundry_comparison="maybe",
        )
    with pytest.raises(
        UncertaintyRoutingError,
        match="local_probability_margin_must_not_exceed_half",
    ):
        build_uncertainty_route(
            label=_label(),
            calibration_report=_report(),
            releasefoundry_available=True,
            local_probability_margin=0.6,
        )


def test_output_is_deterministic_and_does_not_mutate_inputs():
    label = _label()
    report = _report()
    original_label = deepcopy(label)
    original_report = deepcopy(report)

    first = build_uncertainty_route(
        label=label,
        calibration_report=report,
        releasefoundry_available=True,
    )
    second = build_uncertainty_route(
        label=label,
        calibration_report=report,
        releasefoundry_available=True,
    )

    assert first == second
    assert label == original_label
    assert report == original_report
