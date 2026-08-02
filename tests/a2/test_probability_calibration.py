from __future__ import annotations

from copy import deepcopy

import pytest

from services.judge.probability_calibration import (
    ARTIFACT_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    OBSERVATION_SCHEMA_VERSION,
    SCHEMA_VERSION,
    ProbabilityCalibrationError,
    build_probability_calibration_report,
)
from services.judge.result_persistence import stable_hash


def _hash(value: object) -> str:
    return stable_hash({"value": value})


def _seal(value: dict, field: str) -> dict:
    value[field] = stable_hash(value)
    return value


def _artifact(*, verified: bool = True) -> dict:
    return _seal(
        {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "calibrator_id": "a2-local-reward-calibrator",
            "calibrator_version": "a2-calibrator@1.0.0",
            "method": "isotonic",
            "model_version": "a2-local-rm@4",
            "fit_dataset_id": "a2-calibration-fit",
            "fit_dataset_hash": _hash("fit-dataset"),
            "fit_source_group_hashes": [_hash("fit-group-1"), _hash("fit-group-2")],
            "fitted_parameter_hash": _hash("isotonic-parameters"),
            "fit_receipt_hash": _hash("fit-receipt"),
            "fit_receipt_verified": verified,
            "created_at": "2026-07-27T00:00:00Z",
        },
        "artifact_hash",
    )


def _manifest(
    *,
    case_count: int = 1000,
    gold_verified: bool = True,
    isolation_verified: bool = True,
) -> dict:
    cases = []
    for index in range(case_count):
        failed = index % 2 == 0
        cases.append(
            {
                "case_id": f"case-{index:04d}",
                "source_hash": _hash(f"source-{index}"),
                "source_group_hash": _hash(f"holdout-group-{index}"),
                "modality": ["text", "tool", "image", "audio", "video", "document"][
                    index % 6
                ],
                "severity": "high" if failed else "none",
                "failed": failed,
            }
        )
    return _seal(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "manifest_id": "a2-calibration-holdout-v1",
            "dataset_id": "a2-human-gold-holdout",
            "dataset_hash": _hash("holdout-dataset"),
            "split": "holdout",
            "gold_authority": "human_adjudicated",
            "gold_receipt_hash": _hash("gold-receipt"),
            "gold_receipt_verified": gold_verified,
            "source_isolation_policy_hash": _hash("source-policy"),
            "source_isolation_receipt_hash": _hash("source-isolation-receipt"),
            "source_isolation_verified": isolation_verified,
            "cases": cases,
        },
        "manifest_hash",
    )


def _observations(
    manifest: dict,
    *,
    failure_probability: float = 0.99,
    pass_probability: float = 0.01,
) -> list[dict]:
    observations = []
    for case in manifest["cases"]:
        observations.append(
            _seal(
                {
                    "schema_version": OBSERVATION_SCHEMA_VERSION,
                    "case_id": case["case_id"],
                    "source_hash": case["source_hash"],
                    "model_version": "a2-local-rm@4",
                    "calibrator_version": "a2-calibrator@1.0.0",
                    "failure_probability": (
                        failure_probability if case["failed"] else pass_probability
                    ),
                },
                "prediction_hash",
            )
        )
    return observations


def _build(
    *,
    artifact: dict | None = None,
    manifest: dict | None = None,
    observations: list[dict] | None = None,
    **kwargs,
) -> dict:
    selected_manifest = manifest or _manifest()
    return build_probability_calibration_report(
        calibration_artifact=artifact or _artifact(),
        holdout_manifest=selected_manifest,
        observations=observations or _observations(selected_manifest),
        **kwargs,
    )


def _reseal(value: dict, field: str) -> None:
    value.pop(field, None)
    _seal(value, field)


def test_qualifies_verified_low_ece_human_gold_holdout():
    report = _build()

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["holdout"]["case_count"] == 1000
    assert report["metrics"]["overall"]["expected_calibration_error"] == 0.01
    assert report["metrics"]["class_conditional"]["fail"][
        "expected_calibration_error"
    ] == 0.01
    assert report["metrics"]["class_conditional"]["pass"][
        "expected_calibration_error"
    ] == 0.01
    assert report["calibration_gate"] == {
        "status": "calibrated",
        "eligible_for_unified_label_calibrated_status": True,
        "blockers": [],
        "automatic_model_promotion_allowed": False,
        "requires_blind_version_comparison": True,
    }
    assert report["report_hash"] == stable_hash(
        {key: value for key, value in report.items() if key != "report_hash"}
    )


def test_reports_reliability_bins_brier_nll_and_slices():
    report = _build()
    overall = report["metrics"]["overall"]

    assert len(overall["reliability_bins"]) == 2
    assert overall["brier_score"] == 0.0001
    assert overall["negative_log_likelihood"] == pytest.approx(0.010050335854)
    assert set(report["metrics"]["per_modality"]) == {
        "audio",
        "document",
        "image",
        "text",
        "tool",
        "video",
    }
    assert set(report["metrics"]["per_severity"]) == {"high", "none"}


def test_blocks_bad_overall_and_class_conditional_calibration():
    manifest = _manifest()
    report = _build(
        manifest=manifest,
        observations=_observations(
            manifest,
            failure_probability=0.7,
            pass_probability=0.3,
        ),
    )

    assert report["calibration_gate"]["status"] == "uncalibrated"
    assert report["calibration_gate"]["blockers"] == [
        "failure_class_ece_above_threshold",
        "overall_ece_above_threshold",
        "pass_class_ece_above_threshold",
    ]


def test_blocks_insufficient_holdout_and_class_coverage():
    manifest = _manifest(case_count=20)
    report = _build(
        manifest=manifest,
        observations=_observations(manifest),
    )

    assert report["calibration_gate"]["blockers"] == [
        "heldout_case_count_below_minimum",
        "heldout_failure_count_below_minimum",
        "heldout_pass_count_below_minimum",
    ]


@pytest.mark.parametrize(
    "artifact_kwargs,manifest_kwargs,blocker",
    [
        ({"verified": False}, {}, "fit_receipt_not_verified"),
        ({}, {"gold_verified": False}, "human_gold_receipt_not_verified"),
        ({}, {"isolation_verified": False}, "source_isolation_not_verified"),
    ],
)
def test_receipt_and_isolation_claims_are_gate_inputs(
    artifact_kwargs,
    manifest_kwargs,
    blocker,
):
    artifact = _artifact(**artifact_kwargs)
    manifest = _manifest(**manifest_kwargs)
    report = _build(
        artifact=artifact,
        manifest=manifest,
        observations=_observations(manifest),
    )

    assert blocker in report["calibration_gate"]["blockers"]
    assert report["calibration_gate"]["status"] == "uncalibrated"


def test_rejects_fit_holdout_source_group_leakage():
    artifact = _artifact()
    manifest = _manifest()
    artifact["fit_source_group_hashes"][0] = manifest["cases"][0][
        "source_group_hash"
    ]
    _reseal(artifact, "artifact_hash")

    with pytest.raises(
        ProbabilityCalibrationError,
        match="fit_holdout_source_group_overlap",
    ):
        _build(
            artifact=artifact,
            manifest=manifest,
            observations=_observations(manifest),
        )


@pytest.mark.parametrize(
    "mutation,code",
    [
        (
            lambda manifest, observations: observations.pop(),
            "observation_case_coverage_mismatch",
        ),
        (
            lambda manifest, observations: observations.append(
                deepcopy(observations[0])
            ),
            "duplicate_observation_case_id",
        ),
        (
            lambda manifest, observations: observations[0].update(
                {"source_hash": _hash("wrong-source")}
            ),
            "prediction_hash_mismatch",
        ),
        (
            lambda manifest, observations: observations[0].update(
                {"model_version": "other-model"}
            ),
            "prediction_hash_mismatch",
        ),
    ],
)
def test_rejects_incomplete_duplicate_or_tampered_observations(mutation, code):
    manifest = _manifest(case_count=20)
    observations = _observations(manifest)
    mutation(manifest, observations)

    with pytest.raises(ProbabilityCalibrationError, match=code):
        _build(manifest=manifest, observations=observations)


def test_rejects_source_mismatch_even_when_observation_is_resealed():
    manifest = _manifest(case_count=20)
    observations = _observations(manifest)
    observations[0]["source_hash"] = _hash("wrong-source")
    _reseal(observations[0], "prediction_hash")

    with pytest.raises(
        ProbabilityCalibrationError,
        match="observation_source_hash_mismatch",
    ):
        _build(manifest=manifest, observations=observations)


def test_rejects_model_and_calibrator_binding_mismatch_when_resealed():
    manifest = _manifest(case_count=20)
    observations = _observations(manifest)
    observations[0]["model_version"] = "other-model"
    _reseal(observations[0], "prediction_hash")
    with pytest.raises(
        ProbabilityCalibrationError,
        match="observation_model_version_mismatch",
    ):
        _build(manifest=manifest, observations=observations)

    observations = _observations(manifest)
    observations[0]["calibrator_version"] = "other-calibrator"
    _reseal(observations[0], "prediction_hash")
    with pytest.raises(
        ProbabilityCalibrationError,
        match="observation_calibrator_version_mismatch",
    ):
        _build(manifest=manifest, observations=observations)


def test_rejects_tampered_artifact_manifest_and_predictions():
    artifact = _artifact()
    artifact["method"] = "platt"
    with pytest.raises(
        ProbabilityCalibrationError,
        match="calibration_artifact_artifact_hash_mismatch",
    ):
        _build(artifact=artifact)

    manifest = _manifest(case_count=20)
    manifest["cases"][0]["failed"] = not manifest["cases"][0]["failed"]
    with pytest.raises(
        ProbabilityCalibrationError,
        match="holdout_manifest_manifest_hash_mismatch",
    ):
        _build(manifest=manifest, observations=[])


def test_rejects_non_human_gold_and_non_holdout_manifest():
    manifest = _manifest(case_count=20)
    manifest["gold_authority"] = "releasefoundry"
    _reseal(manifest, "manifest_hash")
    with pytest.raises(
        ProbabilityCalibrationError,
        match="holdout_gold_must_be_human_adjudicated",
    ):
        _build(manifest=manifest, observations=_observations(manifest))


def test_rejects_private_paths_and_secrets_from_public_report_fields():
    with pytest.raises(
        ProbabilityCalibrationError,
        match="private_or_secret_material_rejected",
    ):
        _build(report_id=r"C:\Users\Kaylee\private-calibration")


def test_rejects_non_holdout_manifest():
    manifest = _manifest(case_count=20)
    manifest["split"] = "train"
    _reseal(manifest, "manifest_hash")
    with pytest.raises(
        ProbabilityCalibrationError,
        match="calibration_manifest_must_be_holdout",
    ):
        _build(manifest=manifest, observations=_observations(manifest))
