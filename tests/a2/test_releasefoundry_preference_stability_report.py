from __future__ import annotations

import copy

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_build_releasefoundry_preference_stability_report as stability


def _item(
    review_item_id: str,
    *,
    status: str,
    chosen: str | None,
    observed_reward: float,
    reference_reward: float,
) -> dict:
    rejected = "degraded_control" if chosen is not None else None
    return {
        "review_item_id": review_item_id,
        "case_id": f"case-{review_item_id}",
        "channel": "multimodal",
        "prompt_variant": f"prompt-{review_item_id}",
        "expected_variant": f"expected-{review_item_id}",
        "preference_artifact": {
            "pair": {
                "status": status,
                "chosen": (
                    {"candidate_id": chosen}
                    if chosen is not None
                    else None
                ),
                "rejected": (
                    {"candidate_id": rejected}
                    if rejected is not None
                    else None
                ),
                "releasefoundry_evaluations": [
                    {
                        "candidate_id": "observed_fixture",
                        "overall_reward": observed_reward,
                        "receipt_verified": True,
                    },
                    {
                        "candidate_id": "reference_aligned",
                        "overall_reward": reference_reward,
                        "receipt_verified": True,
                    },
                    {
                        "candidate_id": "degraded_control",
                        "overall_reward": 12.0,
                        "receipt_verified": True,
                    },
                ],
            }
        },
    }


def _report(
    label: str | None,
    items: list[dict],
) -> dict:
    evaluation_count = len(items) * 3
    report = {
        "schema_version": "a2.releasefoundry_preference_calibration.v1",
        "experiment_status": "completed",
        "candidate_strategies": [
            "observed_fixture",
            "reference_aligned",
            "degraded_control",
        ],
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "items": items,
        "experiment_plan": {
            "task_count": len(items),
            "candidate_count_per_task": 3,
            "observed_paid_evaluations": evaluation_count,
        },
        "http_calls": {
            "create_run": {
                "attempt_count": 3,
                "automatic_retry_enabled": False,
                "error_count": 0,
                "retry_count": 0,
                "success_count": 3,
            }
        },
        "server_grading": {
            "aggregate_marker_used_as_authority": False,
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
    if label is not None:
        report["experiment_label"] = label
    return report


def test_aggregates_full_and_active_subset_repeats() -> None:
    baseline = _report(
        None,
        [
            _item(
                "always-blocked",
                status="blocked",
                chosen=None,
                observed_reward=98.0,
                reference_reward=98.0,
            ),
            _item(
                "active",
                status="provisional_preference",
                chosen="reference_aligned",
                observed_reward=94.0,
                reference_reward=98.0,
            ),
        ],
    )
    repeat_2 = copy.deepcopy(baseline)
    repeat_2["experiment_label"] = "repeat_2"
    repeat_3 = copy.deepcopy(baseline)
    repeat_3["experiment_label"] = "repeat_3"
    active_repeat_4 = _report(
        "active_repeat_4",
        [
            _item(
                "active",
                status="blocked",
                chosen=None,
                observed_reward=98.0,
                reference_reward=98.0,
            )
        ],
    )
    active_repeat_5 = _report(
        "active_repeat_5",
        [
            _item(
                "active",
                status="provisional_preference",
                chosen="reference_aligned",
                observed_reward=96.0,
                reference_reward=98.0,
            )
        ],
    )

    report = stability.build_stability_report(
        [
            baseline,
            repeat_2,
            repeat_3,
            active_repeat_4,
            active_repeat_5,
        ],
        report_refs=["one.json", "two.json", "three.json", "four.json", "five.json"],
    )

    assert report["experiment_summary"] == {
        "report_count": 5,
        "unique_task_count": 2,
        "task_observation_count": 8,
        "candidate_evaluation_count": 24,
        "create_run_attempt_count": 15,
        "create_run_retry_count": 0,
        "structure_grade_count": 24,
        "final_answer_grade_count": 24,
        "per_test_receipts_verified": True,
        "aggregate_marker_used_as_authority": False,
        "observation_count_distribution": {"3": 1, "5": 1},
    }
    summary = report["preference_stability_summary"]
    assert summary["preference_stability_counts"] == {
        "always_blocked_or_tied": 1,
        "unanimous_stable_preference": 0,
        "strict_majority_preference": 1,
        "weak_or_conflicting_preference": 0,
    }
    assert summary["strict_majority_by_strategy"] == {
        "degraded_control": 0,
        "observed_fixture": 0,
        "reference_aligned": 1,
    }
    assert summary["task_count_without_strict_majority"] == 1
    active = next(
        item for item in report["items"] if item["review_item_id"] == "active"
    )
    assert active["observation_count"] == 5
    assert active["chosen_by_strategy"]["reference_aligned"] == 4
    assert active["preference_stability"] == "strict_majority_preference"
    assert active["training_eligible"] is False
    assert report["human_review_required"] is True
    assert report["text_projection_only"] is True


def test_rejects_retry_or_unknown_subset_task() -> None:
    baseline = _report(
        None,
        [
            _item(
                "known",
                status="blocked",
                chosen=None,
                observed_reward=98.0,
                reference_reward=98.0,
            )
        ],
    )
    retried = copy.deepcopy(baseline)
    retried["experiment_label"] = "retry"
    retried["http_calls"]["create_run"]["retry_count"] = 1
    with pytest.raises(
        stability.PreferenceStabilityReportError,
        match="preference_report_create_run_retry_observed",
    ):
        stability.build_stability_report([baseline, retried])

    unknown = _report(
        "unknown",
        [
            _item(
                "unknown",
                status="blocked",
                chosen=None,
                observed_reward=98.0,
                reference_reward=98.0,
            )
        ],
    )
    with pytest.raises(
        stability.PreferenceStabilityReportError,
        match="preference_report_contains_unknown_task",
    ):
        stability.build_stability_report([baseline, unknown])
