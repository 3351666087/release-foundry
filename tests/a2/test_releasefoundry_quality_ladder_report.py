from __future__ import annotations

import copy

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_releasefoundry_preference_calibration as preference
from scripts import a2_build_releasefoundry_quality_ladder_report as quality


def _evaluation(
    strategy: str,
    *,
    reward: float,
    rank: int,
) -> dict:
    return {
        "candidate_id": strategy,
        "overall_reward": reward,
        "final_answer_score": reward,
        "action_scores": [
            {
                "score": reward,
            }
        ],
        "failure_type": (
            "none" if reward >= 95 else f"{strategy}_failure"
        ),
        "severity": "none" if reward >= 95 else "medium",
        "rank": rank,
        "receipt_verified": True,
    }


def _item(
    review_item_id: str,
    *,
    reward_adjustment: float = 0.0,
) -> dict:
    rewards = {
        "reference_aligned": 98.0,
        "minor_final_answer_defect": 90.0,
        "wrong_final_answer": 68.0,
        "minor_tool_argument_defect": 80.0,
        "wrong_tool_order": 98.0 + reward_adjustment,
        "premature_stop": 75.0,
        "observed_fixture": 96.0,
        "severe_control": 10.0,
    }
    ordered = sorted(
        rewards,
        key=lambda strategy: (-rewards[strategy], strategy),
    )
    ranks = {
        strategy: index + 1 for index, strategy in enumerate(ordered)
    }
    return {
        "review_item_id": review_item_id,
        "case_id": f"case-{review_item_id}",
        "channel": "multimodal",
        "prompt_variant": f"prompt-{review_item_id}",
        "expected_variant": f"expected-{review_item_id}",
        "preference_artifact": {
            "pair": {
                "status": "blocked",
                "releasefoundry_evaluations": [
                    _evaluation(
                        strategy,
                        reward=rewards[strategy],
                        rank=ranks[strategy],
                    )
                    for strategy in preference.QUALITY_LADDER_STRATEGIES
                ],
            }
        },
    }


def _report(
    label: str,
    items: list[dict],
) -> dict:
    evaluation_count = len(items) * len(
        preference.QUALITY_LADDER_STRATEGIES
    )
    return {
        "schema_version": "a2.releasefoundry_preference_calibration.v1",
        "strategy_profile": "quality_ladder",
        "experiment_label": label,
        "experiment_status": "completed",
        "candidate_strategies": list(
            preference.QUALITY_LADDER_STRATEGIES
        ),
        "source_queue_sha256": "sha256:" + ("a" * 64),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "items": items,
        "experiment_plan": {
            "task_count": len(items),
            "candidate_count_per_task": len(
                preference.QUALITY_LADDER_STRATEGIES
            ),
            "observed_paid_evaluations": evaluation_count,
            "observed_create_run_calls": len(
                preference.QUALITY_LADDER_STRATEGIES
            ),
            "create_run_retries": 0,
        },
        "http_calls": {
            "create_run": {
                "attempt_count": len(
                    preference.QUALITY_LADDER_STRATEGIES
                ),
                "automatic_retry_enabled": False,
                "error_count": 0,
                "retry_count": 0,
                "success_count": len(
                    preference.QUALITY_LADDER_STRATEGIES
                ),
            }
        },
        "server_grading": {
            "aggregate_marker_used_as_authority": False,
            "exact_test_set_verified_for_every_strategy": True,
            "per_test_receipts_verified": True,
            "tests_with_final_answer_grading": evaluation_count,
            "tests_with_structure_grading": evaluation_count,
        },
        "human_gold": False,
        "human_reviewed": False,
        "human_review_required": True,
        "training_eligible": False,
        "c3_authority": False,
        "c3_transition_allowed": False,
        "release_authority": False,
        "native_media_uploaded": False,
        "text_projection_only": True,
    }


def test_aggregates_three_quality_ladder_repeats() -> None:
    reports = [
        _report(
            f"repeat_{repeat}",
            [
                _item("one", reward_adjustment=adjustment),
                _item("two", reward_adjustment=adjustment),
            ],
        )
        for repeat, adjustment in (
            (1, 0.0),
            (2, -1.0),
            (3, 1.0),
        )
    ]

    report = quality.build_quality_ladder_report(
        reports,
        report_refs=["one.json", "two.json", "three.json"],
    )

    assert report["experiment_summary"] == {
        "report_count": 3,
        "unique_task_count": 2,
        "task_observation_count": 6,
        "candidate_evaluation_count": 48,
        "create_run_attempt_count": 24,
        "create_run_retry_count": 0,
        "structure_grade_count": 48,
        "final_answer_grade_count": 48,
        "per_test_receipts_verified": True,
        "exact_test_set_verified_for_every_strategy": True,
        "aggregate_marker_used_as_authority": False,
    }
    summary = report["quality_ladder_summary"]
    wrong_order = summary["reference_sensitivity"]["wrong_tool_order"]
    assert wrong_order["absolute_gap_at_most_2_rate"] == 1.0
    assert wrong_order["sensitivity_class"] == (
        "mostly_indistinguishable_from_reference"
    )
    assert (
        summary["reward_target_coverage"]["target_50"]["covered"]
        is False
    )
    assert (
        summary["reward_target_coverage"]["target_10"]["covered"]
        is True
    )
    assert summary["by_strategy"]["reference_aligned"][
        "overall_reward"
    ]["mean"] == 98.0
    assert report["human_gold"] is False
    assert report["training_eligible"] is False
    assert report["text_projection_only"] is True


def test_rejects_retry_unverified_receipt_and_task_set_drift() -> None:
    reports = [
        _report(f"repeat_{repeat}", [_item("known")])
        for repeat in (1, 2, 3)
    ]

    retried = copy.deepcopy(reports)
    retried[1]["http_calls"]["create_run"]["retry_count"] = 1
    with pytest.raises(
        quality.QualityLadderReportError,
        match="quality_ladder_create_run_audit_invalid",
    ):
        quality.build_quality_ladder_report(retried)

    unverified = copy.deepcopy(reports)
    unverified[1]["items"][0]["preference_artifact"]["pair"][
        "releasefoundry_evaluations"
    ][0]["receipt_verified"] = False
    with pytest.raises(
        quality.QualityLadderReportError,
        match="quality_ladder_receipt_not_verified",
    ):
        quality.build_quality_ladder_report(unverified)

    drifted = copy.deepcopy(reports)
    drifted[2]["items"] = [_item("unknown")]
    with pytest.raises(
        quality.QualityLadderReportError,
        match="quality_ladder_task_set_mismatch",
    ):
        quality.build_quality_ladder_report(drifted)
