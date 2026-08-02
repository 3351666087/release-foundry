from __future__ import annotations

import copy

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import (
    a2_build_releasefoundry_corrected_order_preference_review_package as package,
)
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue
from scripts import a2_build_releasefoundry_order_probe_methodology_correction as correction


def _evaluation(reward: float) -> dict:
    return {
        "overall_reward": reward,
        "final_answer_score": reward,
        "mean_action_score": reward,
        "action_count": 1,
        "failure_type": "none",
        "severity": "none",
    }


def _observation(label: str, *, middle_reward: float = 80.0) -> dict:
    rewards = {
        "reference_aligned": 98.0,
        "wrong_tool_order": 60.0,
        "reverse_tool_order": 58.0,
        "missing_middle_tool": middle_reward,
        "wrong_tool_name": 68.0,
        "double_tool_argument_defect": 64.0,
        "tool_and_answer_defect": 52.0,
        "severe_control": 10.0,
    }
    return {
        "experiment_label": label,
        "source_report_sha256": "sha256:" + ("d" * 64),
        "status": "blocked",
        "evaluations": {
            candidate_id: _evaluation(reward)
            for candidate_id, reward in rewards.items()
        },
    }


def _report() -> dict:
    core = {
        "schema_version": package.SOURCE_SCHEMA_VERSION,
        "generated_at": "2026-07-28T00:00:00Z",
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "harness_revision": "a2-releasefoundry-live-v5",
        "tool_call_alignment": "positional",
        "candidate_strategies": list(package.CANDIDATE_STRATEGIES),
        "source_queue_sha256": "sha256:" + ("b" * 64),
        "source_sensitivity_probe_reports": [],
        "experiment_summary": {
            "report_count": 3,
            "unique_task_count": 1,
            "task_observation_count": 3,
            "candidate_evaluation_count": 24,
            "create_run_attempt_count": 24,
            "create_run_retry_count": 0,
            "structure_grade_count": 24,
            "final_answer_grade_count": 24,
            "per_test_receipts_verified": True,
            "exact_test_set_verified_for_every_strategy": True,
            "aggregate_marker_used_as_authority": False,
        },
        "sensitivity_probe_summary": {
            "pair_status_counts": {"blocked": 3},
            "order_blind_spot": {
                "wrong_tool_order": {"blind_spot_confirmed": False},
                "reverse_tool_order": {"blind_spot_confirmed": False},
            },
            "target_50_window": {"covered": True},
        },
        "findings": [],
        "items": [
            {
                "review_item_id": "sha256:review-1",
                "case_id": "case-1",
                "channel": "multimodal",
                "prompt_variant": "prompt-1",
                "expected_variant": "expected-1",
                "observation_count": 3,
                "observations": [
                    _observation("repeat-1"),
                    _observation("repeat-2"),
                    _observation("repeat-3"),
                ],
                "human_review_required": True,
                "training_eligible": False,
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
        "public_safety": {
            "contains_api_key": False,
            "contains_api_key_hash": False,
            "contains_raw_prompt": False,
            "contains_raw_candidate_response": False,
            "contains_raw_tool_arguments": False,
            "contains_private_service_ids": False,
            "contains_local_absolute_paths": False,
        },
        "notes": [],
    }
    return {
        **core,
        "artifact_hash": review_queue._sha256_json(core),
    }


def _correction() -> dict:
    report = {
        "schema_version": correction.SOURCE_SCHEMA_VERSION,
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "artifact_hash": "sha256:historical",
        "experiment_summary": {
            "report_count": 3,
            "per_test_receipts_verified": True,
            "aggregate_marker_used_as_authority": False,
            "create_run_retry_count": 0,
        },
        "items": [
            {
                "observations": [
                    {
                        "evaluations": {
                            candidate_id: _evaluation(50.0)
                            for candidate_id in (
                                correction.AFFECTED_CANDIDATE_IDS
                            )
                        }
                    }
                ]
            }
        ],
    }
    result = correction.build_correction(
        report,
        source_report_ref="historical.json",
    )
    return result


def test_builds_corrected_pair_and_order_reviews() -> None:
    result = package.build_review_package(
        _report(),
        source_report_ref="corrected-stability.json",
        methodology_correction=_correction(),
        methodology_correction_ref="correction.json",
    )

    assert result["review_summary"] == {
        "source_task_count": 1,
        "source_repeat_count": 3,
        "pair_review_item_count": 3,
        "pair_direction_status_counts": {
            "stable_as_proposed": 3,
        },
        "corrected_order_review_item_count": 2,
        "corrected_order_observation_status_counts": {
            "reference_outscores_probe_every_repeat": 2,
        },
        "authorized_preference_pair_count": 0,
        "training_eligible_pair_count": 0,
    }
    pair = result["provisional_pair_reviews"][0]
    assert pair["direction_status"] == "stable_as_proposed"
    assert pair["machine_chosen_candidate_id"] == "reference_aligned"
    assert pair["machine_rejected_candidate_id"] == (
        "tool_and_answer_defect"
    )
    assert pair["corrected_payload_semantics_valid"] is True
    assert pair["rerun_required"] is False
    assert pair["authorized_chosen_candidate_id"] is None
    assert pair["authorized_rejected_candidate_id"] is None
    assert pair["training_eligible"] is False

    order_review = result["corrected_order_reviews"][0]
    assert (
        order_review["corrected_order_observation_status"]
        == "reference_outscores_probe_every_repeat"
    )
    assert order_review["historical_order_blindness_reproduced"] is False
    assert order_review["corrected_payload_semantics_valid"] is True
    assert order_review["general_order_sensitivity_claim_allowed"] is False
    assert result["human_gold"] is False
    assert result["human_reviewed"] is False
    assert result["training_eligible"] is False
    assert result["c3_transition_allowed"] is False
    assert result["release_authority"] is False


def test_keeps_mixed_pair_direction_pending() -> None:
    report = _report()
    report["items"][0]["observations"][2] = _observation(
        "repeat-3",
        middle_reward=40.0,
    )
    core = {
        key: value
        for key, value in report.items()
        if key != "artifact_hash"
    }
    report["artifact_hash"] = review_queue._sha256_json(core)

    result = package.build_review_package(
        report,
        methodology_correction=_correction(),
    )

    missing_middle = result["provisional_pair_reviews"][1]
    assert missing_middle["direction_status"] == "mixed_or_tied"
    assert missing_middle["machine_chosen_candidate_id"] is None
    assert missing_middle["machine_rejected_candidate_id"] is None
    assert missing_middle["human_review_state"] == "pending"
    assert missing_middle["training_eligible"] is False


def test_keeps_stable_reversed_pair_pending_human_review() -> None:
    report = _report()
    report["items"][0]["observations"] = [
        _observation(label, middle_reward=40.0)
        for label in ("repeat-1", "repeat-2", "repeat-3")
    ]
    core = {
        key: value
        for key, value in report.items()
        if key != "artifact_hash"
    }
    report["artifact_hash"] = review_queue._sha256_json(core)

    result = package.build_review_package(
        report,
        methodology_correction=_correction(),
    )

    missing_middle = result["provisional_pair_reviews"][1]
    assert missing_middle["direction_status"] == "stable_reversed"
    assert (
        missing_middle["machine_chosen_candidate_id"]
        == "tool_and_answer_defect"
    )
    assert (
        missing_middle["machine_rejected_candidate_id"]
        == "missing_middle_tool"
    )
    assert missing_middle["authorized_chosen_candidate_id"] is None
    assert missing_middle["authorized_rejected_candidate_id"] is None
    assert missing_middle["human_review_state"] == "pending"
    assert missing_middle["training_eligible"] is False


def test_rejects_non_positional_or_tampered_inputs() -> None:
    non_positional = _report()
    non_positional["tool_call_alignment"] = "expected_tool_name_search"
    core = {
        key: value
        for key, value in non_positional.items()
        if key != "artifact_hash"
    }
    non_positional["artifact_hash"] = review_queue._sha256_json(core)
    with pytest.raises(
        package.CorrectedOrderPreferenceReviewPackageError,
        match="corrected_stability_tool_call_alignment_mismatch",
    ):
        package.build_review_package(
            non_positional,
            methodology_correction=_correction(),
        )

    tampered_report = _report()
    tampered_report["items"][0]["case_id"] = "tampered"
    with pytest.raises(
        package.CorrectedOrderPreferenceReviewPackageError,
        match="corrected_stability_artifact_hash_mismatch",
    ):
        package.build_review_package(
            tampered_report,
            methodology_correction=_correction(),
        )

    tampered_correction = copy.deepcopy(_correction())
    tampered_correction["finding"]["root_cause"] = "other"
    with pytest.raises(
        package.CorrectedOrderPreferenceReviewPackageError,
        match="methodology_correction_artifact_hash_mismatch",
    ):
        package.build_review_package(
            _report(),
            methodology_correction=tampered_correction,
        )
