from __future__ import annotations

import copy

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_releasefoundry_preference_calibration as preference
from scripts import a2_build_releasefoundry_decision_boundary_stability_report as stability


def _candidate(strategy: str, review_item_id: str) -> dict:
    return {
        "candidate_id": strategy,
        "dataset_identity_hash": "sha256:dataset",
        "final_answer_hash": f"sha256:answer-{strategy}",
        "media_evidence_hashes": [],
        "model_version": f"candidate.v1:{strategy}",
        "prompt_hash": f"sha256:prompt-{review_item_id}",
        "prompt_version": "prompt.v1",
        "sample_id": f"sha256:sample-{review_item_id}",
        "task_id": review_item_id,
        "trace_hash": f"sha256:trace-{strategy}",
    }


def _item(
    review_item_id: str,
    rewards: dict[str, float],
    *,
    status: str = "blocked",
) -> dict:
    ordered = sorted(
        rewards,
        key=lambda strategy: (-rewards[strategy], strategy),
    )
    rank_by_reward = {
        reward: index + 1
        for index, reward in enumerate(
            sorted(set(rewards.values()), reverse=True)
        )
    }
    chosen = None
    rejected = None
    if status == "provisional_preference":
        chosen = {"candidate_id": ordered[0]}
        rejected = {"candidate_id": ordered[-1]}
    return {
        "review_item_id": review_item_id,
        "case_id": f"case-{review_item_id}",
        "channel": "tool",
        "prompt_variant": "baseline",
        "expected_variant": "expected",
        "preference_artifact": {
            "human_gold": False,
            "human_review_required": True,
            "training_eligible": False,
            "c3_transition_allowed": False,
            "release_authority": False,
            "pair": {
                "status": status,
                "chosen": chosen,
                "rejected": rejected,
                "review_required": True,
                "training_eligible": False,
                "preference_authority": (
                    "releasefoundry_provisional"
                    if status == "provisional_preference"
                    else "none"
                ),
                "external_teacher_count": (
                    1 if status == "provisional_preference" else 0
                ),
                "human_adjudication": None,
                "candidates": [
                    _candidate(strategy, review_item_id)
                    for strategy in stability.CANDIDATE_STRATEGIES
                ],
                "releasefoundry_evaluations": [
                    {
                        "candidate_id": strategy,
                        "overall_reward": rewards[strategy],
                        "rank": rank_by_reward[rewards[strategy]],
                        "receipt_verified": True,
                    }
                    for strategy in stability.CANDIDATE_STRATEGIES
                ],
            },
        },
    }


def _rewards(**overrides: float) -> dict[str, float]:
    rewards = {
        "reference_aligned": 98.0,
        "redundant_post_success_call": 85.0,
        "redundant_post_success_calls_2": 78.0,
        "redundant_post_success_calls_3": 73.0,
        "premature_stop": 79.0,
        "premature_stop_two_actions": 62.0,
        "minor_final_answer_after_tools": 86.0,
        "contradictory_final_answer_after_tools": 70.0,
    }
    rewards.update(overrides)
    return rewards


def _report(label: str, items: list[dict]) -> dict:
    evaluation_count = len(items) * len(stability.CANDIDATE_STRATEGIES)
    create_run_count = len(stability.CANDIDATE_STRATEGIES)
    core = {
        "schema_version": stability.SOURCE_SCHEMA_VERSION,
        "experiment_status": "completed",
        "experiment_label": label,
        "strategy_profile": stability.STRATEGY_PROFILE,
        "harness_revision": stability.HARNESS_REVISION,
        "tool_call_alignment": stability.TOOL_CALL_ALIGNMENT,
        "candidate_strategies": list(stability.CANDIDATE_STRATEGIES),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "items": items,
        "experiment_plan": {
            "task_count": len(items),
            "candidate_count_per_task": len(
                stability.CANDIDATE_STRATEGIES
            ),
            "planned_paid_evaluations": evaluation_count,
            "observed_paid_evaluations": evaluation_count,
            "planned_create_run_calls": create_run_count,
            "observed_create_run_calls": create_run_count,
            "create_run_retries": 0,
        },
        "http_calls": {
            "create_run": {
                "attempt_count": create_run_count,
                "automatic_retry_enabled": False,
                "error_count": 0,
                "retry_count": 0,
                "success_count": create_run_count,
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
        "public_safety": {
            "contains_api_key": False,
            "contains_api_key_hash": False,
            "contains_raw_prompt": False,
            "contains_raw_candidate_response": False,
            "contains_raw_tool_arguments": False,
            "contains_private_service_ids": False,
            "contains_local_absolute_paths": False,
        },
    }
    return {**core, "artifact_hash": preference.stable_hash(core)}


def _three_reports() -> list[dict]:
    return [
        _report(
            "repeat-1",
            [
                _item("task-1", _rewards()),
                _item("task-2", _rewards(), status="blocked"),
            ],
        ),
        _report(
            "repeat-2",
            [
                _item(
                    "task-1",
                    _rewards(
                        redundant_post_success_calls_3=72.0,
                        minor_final_answer_after_tools=85.0,
                    ),
                ),
                _item(
                    "task-2",
                    _rewards(
                        redundant_post_success_calls_2=87.0,
                    ),
                    status="provisional_preference",
                ),
            ],
        ),
        _report(
            "repeat-3",
            [
                _item(
                    "task-1",
                    _rewards(
                        premature_stop_two_actions=61.0,
                        contradictory_final_answer_after_tools=69.0,
                    ),
                ),
                _item("task-2", _rewards(), status="blocked"),
            ],
        ),
    ]


def test_aggregates_decision_boundary_stability() -> None:
    report = stability.build_stability_report(
        _three_reports(),
        report_refs=["one.json", "two.json", "three.json"],
        expected_task_count=2,
    )

    assert report["experiment_summary"] == {
        "report_count": 3,
        "unique_task_count": 2,
        "task_observation_count": 6,
        "candidate_evaluation_count": 48,
        "create_run_attempt_count": 24,
        "create_run_success_count": 24,
        "create_run_error_count": 0,
        "create_run_retry_count": 0,
        "receipt_verified_evaluation_count": 48,
        "structure_grade_count": 48,
        "final_answer_grade_count": 48,
        "per_test_receipts_verified": True,
        "exact_test_set_verified_for_every_strategy": True,
        "aggregate_marker_used_as_authority": False,
    }
    strategy = report["strategy_stability_summary"]["by_strategy"]
    assert strategy["reference_aligned"]["reward"]["mean"] == 98.0
    assert (
        strategy["redundant_post_success_call"]["reference_reward_gap"][
            "mean"
        ]
        == 13.0
    )
    pair_summary = report["pair_stability_summary"]
    assert pair_summary["pair_status_counts"] == {
        "blocked": 5,
        "provisional_preference": 1,
    }
    assert pair_summary["status_unstable_task_count"] == 1
    assert pair_summary["authorized_preference_pair_count"] == 0
    assert pair_summary["training_eligible_pair_count"] == 0
    task_2 = next(
        item for item in report["items"] if item["review_item_id"] == "task-2"
    )
    assert task_2["exact_ranking_stable"] is False
    assert task_2["pair_stability"]["status_stable"] is False
    monotonicity = report["monotonicity_summary"]
    assert monotonicity["observation_count"] == 6
    assert monotonicity["all_family_monotonic_observation_count"] == 5
    assert monotonicity["all_family_monotonic_task_count"] == 1
    redundant = monotonicity["by_family"]["redundant_call_count"]
    assert redundant["nonincreasing_observation_count"] == 5
    assert redundant["violation_observation_count"] == 1
    assert redundant["minimum_step_margin"] == -2.0
    assert redundant["all_repeats_monotonic_task_count"] == 1
    assert report["active_learning_priorities"][
        "monotonic_violation_review_item_ids_by_family"
    ]["redundant_call_count"] == ["task-2"]
    assert report["human_gold"] is False
    assert report["training_eligible"] is False
    assert report["text_projection_only"] is True
    assert report["notes"][0] == (
        "This report aggregates 3 independent, receipt-bound ReleaseFoundry "
        "decision-boundary probes."
    )


def test_default_reports_cover_six_paid_repeats() -> None:
    assert [path.name for path in stability.DEFAULT_REPORTS] == [
        f"a2_releasefoundry_decision_boundary_probe_repeat_{repeat}.json"
        for repeat in range(1, 7)
    ]


def test_rejects_duplicate_or_retried_reports() -> None:
    reports = _three_reports()
    with pytest.raises(
        stability.DecisionBoundaryStabilityReportError,
        match="duplicate_decision_boundary_report",
    ):
        stability.build_stability_report(
            [reports[0], reports[1], reports[1]],
            expected_task_count=2,
        )

    retried = copy.deepcopy(reports[2])
    retried["http_calls"]["create_run"]["retry_count"] = 1
    retried["artifact_hash"] = preference.stable_hash(
        {key: value for key, value in retried.items() if key != "artifact_hash"}
    )
    with pytest.raises(
        stability.DecisionBoundaryStabilityReportError,
        match="decision_boundary_create_run_audit_invalid",
    ):
        stability.build_stability_report(
            [reports[0], reports[1], retried],
            expected_task_count=2,
        )


def test_rejects_candidate_identity_drift_or_missing_receipt() -> None:
    reports = _three_reports()
    identity_drift = copy.deepcopy(reports[2])
    identity_drift["items"][0]["preference_artifact"]["pair"]["candidates"][
        0
    ]["trace_hash"] = "sha256:changed"
    identity_drift["artifact_hash"] = preference.stable_hash(
        {
            key: value
            for key, value in identity_drift.items()
            if key != "artifact_hash"
        }
    )
    with pytest.raises(
        stability.DecisionBoundaryStabilityReportError,
        match="decision_boundary_candidate_identity_mismatch",
    ):
        stability.build_stability_report(
            [reports[0], reports[1], identity_drift],
            expected_task_count=2,
        )

    missing_receipt = copy.deepcopy(reports[2])
    missing_receipt["items"][0]["preference_artifact"]["pair"][
        "releasefoundry_evaluations"
    ][0]["receipt_verified"] = False
    missing_receipt["artifact_hash"] = preference.stable_hash(
        {
            key: value
            for key, value in missing_receipt.items()
            if key != "artifact_hash"
        }
    )
    with pytest.raises(
        stability.DecisionBoundaryStabilityReportError,
        match="decision_boundary_receipt_incomplete",
    ):
        stability.build_stability_report(
            [reports[0], reports[1], missing_receipt],
            expected_task_count=2,
        )


def test_rejects_duplicate_labels_and_boundary_promotion() -> None:
    reports = _three_reports()
    duplicate_label = copy.deepcopy(reports[2])
    duplicate_label["experiment_label"] = reports[1]["experiment_label"]
    duplicate_label["artifact_hash"] = preference.stable_hash(
        {
            key: value
            for key, value in duplicate_label.items()
            if key != "artifact_hash"
        }
    )
    with pytest.raises(
        stability.DecisionBoundaryStabilityReportError,
        match="decision_boundary_experiment_labels_not_unique",
    ):
        stability.build_stability_report(
            [reports[0], reports[1], duplicate_label],
            expected_task_count=2,
        )

    promoted = copy.deepcopy(reports[2])
    promoted["training_eligible"] = True
    promoted["artifact_hash"] = preference.stable_hash(
        {key: value for key, value in promoted.items() if key != "artifact_hash"}
    )
    with pytest.raises(
        stability.DecisionBoundaryStabilityReportError,
        match="decision_boundary_training_eligible_must_be_false",
    ):
        stability.build_stability_report(
            [reports[0], reports[1], promoted],
            expected_task_count=2,
        )
