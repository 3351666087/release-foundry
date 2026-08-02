from __future__ import annotations

import copy

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue
from scripts import a2_build_releasefoundry_preference_active_learning_queue as active


def _source_queue() -> dict:
    items = [
        {
            "review_item_id": f"review-{index}",
            "variant_id_hash": f"sha256:variant-{index}",
            "case_id": "case-1",
            "channel": "multimodal",
            "prompt_variant": f"prompt-{index}",
            "expected_variant": f"expected-{index}",
            "training_eligible": False,
            "c3_authority": False,
            "release_authority": False,
        }
        for index in range(2)
    ]
    return {
        "schema_version": "test.queue.v1",
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "items": items,
    }


def _report(
    source: dict,
    *,
    first_status: str,
    first_chosen: str | None,
    reward_offset: float,
) -> dict:
    items = []
    for index in range(2):
        status = first_status if index == 0 else "blocked"
        chosen = first_chosen if index == 0 else None
        items.append(
            {
                "review_item_id": f"review-{index}",
                "preference_artifact": {
                    "pair": {
                        "status": status,
                        "chosen": (
                            {"candidate_id": chosen}
                            if chosen is not None
                            else None
                        ),
                        "releasefoundry_evaluations": [
                            {
                                "candidate_id": strategy,
                                "overall_reward": reward + reward_offset,
                                "receipt_verified": True,
                            }
                            for strategy, reward in (
                                ("observed_fixture", 95.0),
                                ("reference_aligned", 98.0),
                                ("degraded_control", 12.0),
                            )
                        ],
                    }
                },
            }
        )
    return {
        "schema_version": "a2.releasefoundry_preference_calibration.v1",
        "experiment_status": "completed",
        "source_queue_sha256": review_queue._sha256_json(source),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "items": items,
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


def test_selects_only_cases_with_an_observed_preference() -> None:
    source = _source_queue()
    reports = [
        _report(
            source,
            first_status="provisional_preference",
            first_chosen="reference_aligned",
            reward_offset=0.0,
        ),
        _report(
            source,
            first_status="blocked",
            first_chosen=None,
            reward_offset=1.0,
        ),
        _report(
            source,
            first_status="provisional_preference",
            first_chosen="reference_aligned",
            reward_offset=2.0,
        ),
    ]

    queue = active.build_active_learning_queue(
        source,
        reports,
        source_queue_ref="source.json",
        report_refs=["one.json", "two.json", "three.json"],
    )

    assert queue["review_item_count"] == 1
    assert queue["observed_repeat_count"] == 3
    assert queue["additional_repeats_requested"] == 2
    item = queue["items"][0]
    assert item["review_item_id"] == "review-0"
    assert item["active_learning"] == {
        "selection_reason": (
            "provisional_preference_observed_in_at_least_one_repeat"
        ),
        "observed_repeat_count": 3,
        "provisional_preference_count": 2,
        "blocked_count": 1,
        "chosen_by_strategy": {"reference_aligned": 2},
        "reward_population_std_by_strategy": {
            "degraded_control": 0.8165,
            "observed_fixture": 0.8165,
            "reference_aligned": 0.8165,
        },
        "target_repeat_count": 5,
        "additional_repeats_requested": 2,
    }
    assert queue["training_eligible"] is False
    assert queue["c3_authority"] is False
    assert queue["release_authority"] is False
    assert queue["text_projection_only"] is True


def test_rejects_mismatched_or_authoritative_reports() -> None:
    source = _source_queue()
    report = _report(
        source,
        first_status="provisional_preference",
        first_chosen="reference_aligned",
        reward_offset=0.0,
    )

    mismatch = copy.deepcopy(report)
    mismatch["source_queue_sha256"] = "sha256:not-the-source"
    with pytest.raises(
        active.PreferenceActiveLearningQueueError,
        match="preference_report_source_queue_mismatch",
    ):
        active.build_active_learning_queue(source, [report, mismatch])

    authoritative = copy.deepcopy(report)
    authoritative["release_authority"] = True
    with pytest.raises(
        active.PreferenceActiveLearningQueueError,
        match="preference_report_release_authority_must_be_false",
    ):
        active.build_active_learning_queue(source, [report, authoritative])
