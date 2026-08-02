from __future__ import annotations

from copy import deepcopy

import pytest

from services.judge.result_persistence import stable_hash
from services.judge.schemas import FailureAnalysis, GradeResult
from services.judge.unified_label import (
    SCHEMA_VERSION,
    UnifiedJudgeLabelError,
    adapt_grade_result_to_unified_label,
    build_unified_judge_label,
    verify_unified_judge_label,
)


def _hash(value: str) -> str:
    return stable_hash({"value": value})


def _calibrated() -> dict:
    return {
        "status": "calibrated",
        "method": "isotonic",
        "version": "a2-calibrator@1.0.0",
        "artifact_hash": _hash("calibrator"),
    }


def _text_evidence() -> list[dict]:
    return [
        {
            "modality": "text",
            "source_hash": _hash("input"),
            "start_char": 4,
            "end_char": 18,
        }
    ]


def _build(**overrides) -> dict:
    values = {
        "label_id": "label-001",
        "case_id": "case-001",
        "modality": "tool",
        "passed": False,
        "failure_type": "wrong_arguments",
        "failure_types": ["wrong_arguments"],
        "severity": "high",
        "failed_action": "tool_call[1]:weather.location",
        "evidence_locations": [
            {
                "modality": "tool",
                "source_hash": _hash("trace"),
                "action_index": 1,
                "tool_name": "weather",
                "argument_path": "$.location",
            }
        ],
        "confidence": 0.94,
        "failure_probability": 0.91,
        "probability_calibration": _calibrated(),
        "release_recommendation": "block",
        "reason": "The requested city was replaced with an unsupported location.",
        "judge_id": "a2-tool-judge",
        "judge_version": "1.2.0",
        "model_version": "local-rm@4",
        "prompt_version": "judge-prompt-v8",
        "input_hash": _hash("input"),
        "output_hash": _hash("output"),
    }
    values.update(overrides)
    return build_unified_judge_label(**values)


def test_builds_hash_bound_calibrated_failure_label():
    label = _build()

    assert label["schema_version"] == SCHEMA_VERSION
    assert label["label"] == "fail"
    assert label["calibrated_failure_probability"] == 0.91
    assert label["evidence_hash"] == stable_hash(label["evidence_locations"])
    assert label["label_hash"] == stable_hash(
        {key: value for key, value in label.items() if key != "label_hash"}
    )
    assert label["metadata"]["automatic_release_authority"] is False
    verify_unified_judge_label(label)


def test_builds_calibrated_pass_label_with_text_span():
    label = _build(
        modality="text",
        passed=True,
        failure_type="none",
        failure_types=["none"],
        severity="none",
        failed_action="",
        evidence_locations=_text_evidence(),
        failure_probability=0.08,
        release_recommendation="allow",
    )

    assert label["label"] == "pass"
    assert label["metadata"]["automatic_release_authority"] is True
    verify_unified_judge_label(label)


@pytest.mark.parametrize(
    "modality,evidence",
    [
        (
            "image",
            {
                "modality": "image",
                "source_hash": _hash("image"),
                "x": 0.1,
                "y": 0.2,
                "width": 0.3,
                "height": 0.4,
                "coordinate_space": "normalized",
            },
        ),
        (
            "audio",
            {
                "modality": "audio",
                "source_hash": _hash("audio"),
                "start_ms": 120,
                "end_ms": 940,
                "speaker": "speaker-2",
            },
        ),
        (
            "video",
            {
                "modality": "video",
                "source_hash": _hash("video"),
                "start_ms": 1000,
                "end_ms": 1800,
                "start_frame": 30,
                "end_frame": 54,
            },
        ),
        (
            "document",
            {
                "modality": "document",
                "source_hash": _hash("pdf"),
                "document_type": "pdf",
                "page": 4,
                "table": 2,
                "field": "total",
            },
        ),
    ],
)
def test_accepts_strongly_typed_native_evidence_locations(modality, evidence):
    label = _build(modality=modality, evidence_locations=[evidence])

    assert label["evidence_locations"][0] == evidence


def test_multimodal_label_requires_and_accepts_multiple_source_modalities():
    label = _build(
        modality="multimodal",
        failure_type="cross_modal_conflict_ignored",
        failure_types=["cross_modal_conflict_ignored"],
        evidence_locations=[
            _text_evidence()[0],
            {
                "modality": "image",
                "source_hash": _hash("image"),
                "x": 10,
                "y": 20,
                "width": 30,
                "height": 40,
                "coordinate_space": "pixels",
            },
        ],
    )

    assert {item["modality"] for item in label["evidence_locations"]} == {
        "text",
        "image",
    }


@pytest.mark.parametrize(
    "overrides,code",
    [
        (
            {"passed": True},
            "pass_has_failure_class",
        ),
        (
            {
                "passed": True,
                "failure_type": "none",
                "failure_types": ["none"],
                "severity": "high",
                "failed_action": "",
                "failure_probability": 0.1,
            },
            "pass_has_failure_severity",
        ),
        (
            {
                "passed": True,
                "failure_type": "none",
                "failure_types": ["none"],
                "severity": "none",
                "failed_action": "tool_call[1]",
                "failure_probability": 0.1,
            },
            "pass_has_failed_action",
        ),
        (
            {
                "passed": True,
                "failure_type": "none",
                "failure_types": ["none"],
                "severity": "none",
                "failed_action": "",
                "failure_probability": 0.5,
            },
            "pass_probability_crosses_failure_threshold",
        ),
        (
            {"failure_type": "none", "failure_types": ["none"]},
            "fail_missing_failure_class",
        ),
        (
            {"failure_types": ["wrong_tool"]},
            "primary_failure_not_in_failure_types",
        ),
        (
            {"severity": "none"},
            "fail_missing_severity",
        ),
        (
            {"failed_action": ""},
            "fail_missing_failed_action",
        ),
        (
            {"failure_probability": 0.49},
            "fail_probability_below_failure_threshold",
        ),
        (
            {"release_recommendation": "allow"},
            "failed_label_cannot_recommend_allow",
        ),
        (
            {"release_recommendation": "staged_rollout"},
            "high_risk_failure_cannot_recommend_staged_rollout",
        ),
        (
            {
                "severity": "critical",
                "release_recommendation": "restrict_capability",
            },
            "critical_failure_requires_review_or_block",
        ),
    ],
)
def test_rejects_inconsistent_binary_risk_labels(overrides, code):
    with pytest.raises(UnifiedJudgeLabelError, match=code):
        _build(**overrides)


def test_uncalibrated_probability_is_explicit_and_cannot_authorize_release():
    uncalibrated = {
        "status": "uncalibrated",
        "method": "",
        "version": "",
        "artifact_hash": None,
    }
    label = _build(
        probability_calibration=uncalibrated,
        release_recommendation="human_review",
    )

    assert label["calibrated_failure_probability"] is None
    assert label["failure_probability"] == 0.91

    with pytest.raises(
        UnifiedJudgeLabelError,
        match="uncalibrated_probability_cannot_authorize_release",
    ):
        _build(
            passed=True,
            failure_type="none",
            failure_types=["none"],
            severity="none",
            failed_action="",
            evidence_locations=_text_evidence(),
            modality="text",
            failure_probability=0.1,
            probability_calibration=uncalibrated,
            release_recommendation="allow",
        )


@pytest.mark.parametrize(
    "calibration,code",
    [
        (
            {
                "status": "calibrated",
                "method": "",
                "version": "v1",
                "artifact_hash": _hash("calibrator"),
            },
            "calibrated_probability_provenance_missing",
        ),
        (
            {
                "status": "uncalibrated",
                "method": "isotonic",
                "version": "",
                "artifact_hash": None,
            },
            "uncalibrated_probability_has_calibration_provenance",
        ),
    ],
)
def test_rejects_false_probability_calibration_claims(calibration, code):
    with pytest.raises(UnifiedJudgeLabelError, match=code):
        _build(probability_calibration=calibration)


@pytest.mark.parametrize(
    "evidence,code",
    [
        (
            {
                "modality": "image",
                "source_hash": _hash("image"),
                "x": 0,
                "y": 0,
                "width": 2,
                "height": 1,
                "coordinate_space": "normalized",
            },
            "normalized_coordinates_out_of_range",
        ),
        (
            {
                "modality": "audio",
                "source_hash": _hash("audio"),
                "start_ms": 10,
                "end_ms": 10,
            },
            "range_invalid",
        ),
        (
            {
                "modality": "document",
                "source_hash": _hash("document"),
                "document_type": "pdf",
            },
            "document_locator_missing",
        ),
        (
            {
                "modality": "tool",
                "source_hash": _hash("trace"),
                "action_index": -1,
                "tool_name": "weather",
            },
            "must_be_non_negative_integer",
        ),
    ],
)
def test_rejects_invalid_evidence_locations(evidence, code):
    with pytest.raises(UnifiedJudgeLabelError, match=code):
        _build(modality=evidence["modality"], evidence_locations=[evidence])


def test_rejects_multimodal_label_backed_by_only_one_modality():
    with pytest.raises(
        UnifiedJudgeLabelError,
        match="multimodal_label_requires_multiple_evidence_modalities",
    ):
        _build(modality="multimodal")


def test_rejects_private_paths_and_secrets():
    with pytest.raises(
        UnifiedJudgeLabelError,
        match="private_or_secret_material_rejected",
    ):
        _build(reason=r"See C:\Users\Kaylee\secret.json")


def test_verifier_rejects_tampered_evidence_and_label_hash():
    label = _build()
    tampered = deepcopy(label)
    tampered["evidence_locations"][0]["action_index"] = 2

    with pytest.raises(UnifiedJudgeLabelError, match="evidence_hash_mismatch"):
        verify_unified_judge_label(tampered)

    tampered = deepcopy(label)
    tampered["reason"] = "Changed after signing."
    with pytest.raises(UnifiedJudgeLabelError, match="label_hash_mismatch"):
        verify_unified_judge_label(tampered)


def test_grade_result_adapter_maps_legacy_major_to_high_without_inventing_evidence():
    grade = GradeResult(
        scenario_id="s010",
        case_id="s010-wrong-arguments",
        judge_mode="deterministic",
        passed=False,
        score=35,
        rubric_scores=[],
        failure_analysis=FailureAnalysis(
            primary_failure_class="wrong_arguments",
            failure_classes=["wrong_arguments"],
            severity="major",
            summary="The tool received the wrong city.",
        ),
        judge_version="0.1.0",
    )

    label = adapt_grade_result_to_unified_label(
        grade,
        label_id="label-s010",
        modality="tool",
        failed_action="tool_call[0]:weather.location",
        evidence_locations=[
            {
                "modality": "tool",
                "source_hash": _hash("s010-trace"),
                "action_index": 0,
                "tool_name": "weather",
                "argument_path": "$.location",
            }
        ],
        confidence=0.9,
        failure_probability=0.86,
        probability_calibration=_calibrated(),
        release_recommendation="block",
        judge_id="a2-deterministic-judge",
        model_version="ruleset@0.1.0",
        prompt_version="not-applicable@1",
        input_hash=_hash("s010-input"),
        output_hash=_hash("s010-output"),
    )

    assert label["case_id"] == "s010-wrong-arguments"
    assert label["severity"] == "high"
    assert label["failure_type"] == "wrong_arguments"


def test_grade_result_adapter_fails_when_structured_evidence_is_missing():
    grade = GradeResult(
        scenario_id="s001",
        case_id="s001-pass",
        judge_mode="deterministic",
        passed=True,
        score=100,
        rubric_scores=[],
        failure_analysis=FailureAnalysis(),
    )

    with pytest.raises(
        UnifiedJudgeLabelError,
        match="evidence_locations_must_be_non_empty_list",
    ):
        adapt_grade_result_to_unified_label(
            grade,
            label_id="label-s001",
            modality="text",
            failed_action="",
            evidence_locations=[],
            confidence=0.9,
            failure_probability=0.05,
            probability_calibration=_calibrated(),
            release_recommendation="allow",
            judge_id="a2-deterministic-judge",
            model_version="ruleset@0.1.0",
            prompt_version="not-applicable@1",
            input_hash=_hash("s001-input"),
            output_hash=_hash("s001-output"),
        )
