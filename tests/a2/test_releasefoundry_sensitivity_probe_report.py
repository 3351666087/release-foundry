from __future__ import annotations

import copy

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_releasefoundry_preference_calibration as preference
from scripts import a2_build_releasefoundry_sensitivity_probe_report as probe


def _evaluation(
    strategy: str,
    *,
    reward: float,
) -> dict:
    return {
        "candidate_id": strategy,
        "overall_reward": reward,
        "final_answer_score": reward,
        "action_scores": [{"score": reward}],
        "failure_type": "none" if reward >= 95 else f"{strategy}_failure",
        "severity": "none" if reward >= 95 else "medium",
        "receipt_verified": True,
    }


def _item(
    review_item_id: str,
    *,
    order_adjustment: float = 0.0,
) -> dict:
    rewards = {
        "reference_aligned": 98.0,
        "wrong_tool_order": 98.0 + order_adjustment,
        "reverse_tool_order": 97.0 + order_adjustment,
        "missing_middle_tool": 80.0,
        "wrong_tool_name": 68.0,
        "double_tool_argument_defect": 64.0,
        "tool_and_answer_defect": 52.0,
        "severe_control": 10.0,
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
                    _evaluation(strategy, reward=rewards[strategy])
                    for strategy in preference.SENSITIVITY_PROBE_STRATEGIES
                ],
            }
        },
    }


def _report(
    label: str,
    items: list[dict],
) -> dict:
    evaluation_count = len(items) * len(
        preference.SENSITIVITY_PROBE_STRATEGIES
    )
    return {
        "schema_version": "a2.releasefoundry_preference_calibration.v1",
        "strategy_profile": "sensitivity_probe",
        "experiment_label": label,
        "experiment_status": "completed",
        "harness_revision": calibration.HARNESS_REVISION,
        "tool_call_alignment": calibration.TOOL_CALL_ALIGNMENT,
        "candidate_strategies": list(
            preference.SENSITIVITY_PROBE_STRATEGIES
        ),
        "source_queue_sha256": "sha256:" + ("b" * 64),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "items": items,
        "experiment_plan": {
            "task_count": len(items),
            "candidate_count_per_task": len(
                preference.SENSITIVITY_PROBE_STRATEGIES
            ),
            "observed_paid_evaluations": evaluation_count,
            "observed_create_run_calls": len(
                preference.SENSITIVITY_PROBE_STRATEGIES
            ),
            "create_run_retries": 0,
        },
        "http_calls": {
            "create_run": {
                "attempt_count": len(
                    preference.SENSITIVITY_PROBE_STRATEGIES
                ),
                "automatic_retry_enabled": False,
                "error_count": 0,
                "retry_count": 0,
                "success_count": len(
                    preference.SENSITIVITY_PROBE_STRATEGIES
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


def test_aggregates_probe_blind_spot_and_target_50_pairs() -> None:
    reports = [
        _report(
            f"repeat_{repeat}",
            [
                _item("one", order_adjustment=adjustment),
                _item("two", order_adjustment=adjustment),
            ],
        )
        for repeat, adjustment in (
            (1, 0.0),
            (2, -1.0),
            (3, 1.0),
        )
    ]

    report = probe.build_sensitivity_probe_report(
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
    summary = report["sensitivity_probe_summary"]
    assert summary["order_blind_spot"]["wrong_tool_order"][
        "blind_spot_confirmed"
    ] is True
    assert summary["order_blind_spot"]["reverse_tool_order"][
        "blind_spot_confirmed"
    ] is True
    assert summary["target_50_window"]["observation_count"] == 6
    pair = summary["provisional_distillation_pair_diagnostics"][0]
    assert pair["chosen_candidate_id"] == "reference_aligned"
    assert pair["rejected_candidate_id"] == "tool_and_answer_defect"
    assert pair["tasks_with_same_direction_in_every_repeat"] == 2
    assert pair["training_eligible"] is False
    assert report["human_gold"] is False
    assert report["text_projection_only"] is True
    assert report["harness_revision"] == "a2-releasefoundry-live-v5"
    assert report["tool_call_alignment"] == "positional"
    assert all(
        row["harness_revision"] == "a2-releasefoundry-live-v5"
        and row["tool_call_alignment"] == "positional"
        for row in report["source_sensitivity_probe_reports"]
    )


def test_rejects_retry_unverified_receipt_and_task_drift() -> None:
    reports = [
        _report(f"repeat_{repeat}", [_item("known")])
        for repeat in (1, 2, 3)
    ]

    retried = copy.deepcopy(reports)
    retried[1]["http_calls"]["create_run"]["retry_count"] = 1
    with pytest.raises(
        probe.SensitivityProbeReportError,
        match="sensitivity_probe_create_run_audit_invalid",
    ):
        probe.build_sensitivity_probe_report(retried)

    unverified = copy.deepcopy(reports)
    unverified[1]["items"][0]["preference_artifact"]["pair"][
        "releasefoundry_evaluations"
    ][0]["receipt_verified"] = False
    with pytest.raises(
        probe.SensitivityProbeReportError,
        match="sensitivity_probe_receipt_not_verified",
    ):
        probe.build_sensitivity_probe_report(unverified)

    drifted = copy.deepcopy(reports)
    drifted[2]["items"] = [_item("unknown")]
    with pytest.raises(
        probe.SensitivityProbeReportError,
        match="sensitivity_probe_task_set_mismatch",
    ):
        probe.build_sensitivity_probe_report(drifted)

    queue_drifted = copy.deepcopy(reports)
    queue_drifted[2]["source_queue_sha256"] = "sha256:" + ("c" * 64)
    with pytest.raises(
        probe.SensitivityProbeReportError,
        match="sensitivity_probe_source_queue_mismatch",
    ):
        probe.build_sensitivity_probe_report(queue_drifted)


def test_rejects_historical_order_normalizing_harness() -> None:
    reports = [
        _report(f"repeat_{repeat}", [_item("known")])
        for repeat in (1, 2, 3)
    ]

    historical_harness = copy.deepcopy(reports)
    historical_harness[1]["harness_revision"] = "a2-releasefoundry-live-v4"
    with pytest.raises(
        probe.SensitivityProbeReportError,
        match="sensitivity_probe_harness_revision_mismatch",
    ):
        probe.build_sensitivity_probe_report(historical_harness)

    normalized_alignment = copy.deepcopy(reports)
    normalized_alignment[1]["tool_call_alignment"] = (
        "expected_tool_name_search"
    )
    with pytest.raises(
        probe.SensitivityProbeReportError,
        match="sensitivity_probe_tool_call_alignment_mismatch",
    ):
        probe.build_sensitivity_probe_report(normalized_alignment)


def test_reports_when_corrected_order_blind_spot_is_not_confirmed() -> None:
    reports = [
        _report(
            f"repeat_{repeat}",
            [_item("known", order_adjustment=-10.0)],
        )
        for repeat in (1, 2, 3)
    ]

    report = probe.build_sensitivity_probe_report(reports)

    assert all(
        row["blind_spot_confirmed"] is False
        for row in report["sensitivity_probe_summary"][
            "order_blind_spot"
        ].values()
    )
    assert report["findings"][0] == (
        "The corrected positional repeats did not meet the declared "
        "tool-order blind-spot threshold for either order probe."
    )


def test_defaults_point_to_corrected_order_repeats() -> None:
    assert [path.name for path in probe.DEFAULT_REPORTS] == [
        "a2_releasefoundry_sensitivity_probe_corrected_order_repeat_1.json",
        "a2_releasefoundry_sensitivity_probe_corrected_order_repeat_2.json",
        "a2_releasefoundry_sensitivity_probe_corrected_order_repeat_3.json",
    ]
    assert (
        probe.DEFAULT_OUTPUT.name
        == "a2_releasefoundry_sensitivity_probe_corrected_order_stability.json"
    )
