from __future__ import annotations

import copy

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_build_releasefoundry_order_probe_methodology_correction as correction
from scripts import a2_build_releasefoundry_provisional_preference_review_package as package


def _report() -> dict:
    observations = []
    for index in range(3):
        observations.append(
            {
                "experiment_label": f"repeat-{index + 1}",
                "evaluations": {
                    "reference_aligned": {"overall_reward": 98.0},
                    "wrong_tool_order": {"overall_reward": 98.0},
                    "reverse_tool_order": {"overall_reward": 99.0},
                    "missing_middle_tool": {"overall_reward": 80.0},
                    "tool_and_answer_defect": {"overall_reward": 54.0},
                    "severe_control": {"overall_reward": 12.0},
                },
            }
        )
    return {
        "schema_version": package.SOURCE_SCHEMA_VERSION,
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "artifact_hash": "sha256:source-artifact",
        "experiment_summary": {
            "report_count": 3,
            "per_test_receipts_verified": True,
            "aggregate_marker_used_as_authority": False,
            "create_run_retry_count": 0,
        },
        "items": [
            {
                "review_item_id": "sha256:review-1",
                "case_id": "case-1",
                "channel": "multimodal",
                "prompt_variant": "prompt-1",
                "expected_variant": "expected-1",
                "observations": observations,
            }
        ],
        "human_gold": False,
        "human_reviewed": False,
        "human_review_required": True,
        "training_eligible": False,
        "c3_authority": False,
        "c3_transition_allowed": False,
        "release_authority": False,
        "text_projection_only": True,
        "native_media_uploaded": False,
    }


def _correction(report: dict) -> dict:
    return correction.build_correction(
        report,
        source_report_ref="stability.json",
    )


def test_builds_unapproved_pairs_and_order_harness_regressions() -> None:
    report = _report()
    result = package.build_review_package(
        report,
        source_report_ref="stability.json",
        methodology_correction=_correction(report),
        methodology_correction_ref="correction.json",
    )

    assert result["review_summary"] == {
        "source_task_count": 1,
        "source_repeat_count": 3,
        "provisional_pair_review_item_count": 3,
        "order_harness_regression_review_item_count": 2,
        "methodologically_invalid_pair_review_item_count": 1,
        "authorized_preference_pair_count": 0,
        "training_eligible_pair_count": 0,
    }
    pair = result["provisional_pair_reviews"][0]
    assert pair["machine_hypothesis"] == {
        "proposed_preferred_candidate_id": "reference_aligned",
        "proposed_disfavored_candidate_id": "tool_and_answer_defect",
        "all_repeats_prefer_proposed": True,
        "repeat_count": 3,
        "mean_reward_gap": 44.0,
        "minimum_reward_gap": 44.0,
        "maximum_reward_gap": 44.0,
    }
    assert pair["authorized_chosen_candidate_id"] is None
    assert pair["authorized_rejected_candidate_id"] is None
    assert pair["training_eligible"] is False

    missing_middle = result["provisional_pair_reviews"][1]
    assert missing_middle["historical_payload_semantics_valid"] is False
    assert missing_middle["rerun_required"] is True

    reverse_order = result["order_harness_regression_reviews"][1]
    assert reverse_order["machine_observation"][
        "probe_outscored_reference_count"
    ] == 3
    assert reverse_order["historical_order_probe_validity"] is False
    assert reverse_order["invalidated_for_releasefoundry_order_sensitivity"] is True
    assert reverse_order["releasefoundry_order_sensitivity_claim_allowed"] is False
    assert reverse_order["positive_training_example"] is False
    assert reverse_order["regression_candidate"] is True
    assert result["human_gold"] is False
    assert result["human_reviewed"] is False
    assert result["training_eligible"] is False
    assert result["c3_transition_allowed"] is False
    assert result["release_authority"] is False
    assert result["text_projection_only"] is True
    assert result["native_media_uploaded"] is False


def test_rejects_authoritative_or_unstable_source_reports() -> None:
    authoritative = _report()
    authoritative["training_eligible"] = True
    with pytest.raises(
        package.ProvisionalPreferenceReviewPackageError,
        match="stability_report_training_eligible_must_be_false",
    ):
        package.build_review_package(
            authoritative,
            methodology_correction=_correction(_report()),
        )

    unstable = copy.deepcopy(_report())
    unstable["items"][0]["observations"][2]["evaluations"][
        "tool_and_answer_defect"
    ]["overall_reward"] = 99.0
    with pytest.raises(
        package.ProvisionalPreferenceReviewPackageError,
        match="pair_direction_not_stable",
    ):
        package.build_review_package(
            unstable,
            methodology_correction=_correction(unstable),
        )


def test_requires_correction_bound_to_the_same_historical_report() -> None:
    report = _report()
    other = copy.deepcopy(report)
    other["artifact_hash"] = "sha256:other"

    with pytest.raises(
        package.ProvisionalPreferenceReviewPackageError,
        match="methodology_correction_source_mismatch",
    ):
        package.build_review_package(
            report,
            methodology_correction=_correction(other),
        )
