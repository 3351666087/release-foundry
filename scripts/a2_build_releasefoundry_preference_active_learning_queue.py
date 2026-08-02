from __future__ import annotations

import argparse
import copy
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import a2_releasefoundry_live_calibration as calibration  # noqa: E402
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue  # noqa: E402


DEFAULT_SOURCE_QUEUE = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_disagreement_review_queue.json"
)
DEFAULT_REPORTS = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_preference_calibration.json",
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_preference_calibration_repeat_2.json",
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_exploratory_preference_calibration_repeat_3.json",
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_preference_active_learning_queue.json"
)
SCHEMA_VERSION = "a2.releasefoundry_preference_active_learning_queue.v1"


class PreferenceActiveLearningQueueError(ValueError):
    pass


def build_active_learning_queue(
    source_queue: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    source_queue_ref: str | Path = DEFAULT_SOURCE_QUEUE,
    report_refs: list[str | Path] | None = None,
) -> dict[str, Any]:
    if len(reports) < 2:
        raise PreferenceActiveLearningQueueError(
            "at_least_two_preference_reports_required"
        )
    source_hash = review_queue._sha256_json(source_queue)
    source_items = _source_items_by_id(source_queue)
    report_maps = [
        _validated_report_items(report, source_hash=source_hash)
        for report in reports
    ]
    expected_ids = set(source_items)
    for report_map in report_maps:
        if set(report_map) != expected_ids:
            raise PreferenceActiveLearningQueueError(
                "preference_report_item_set_mismatch"
            )

    selected = []
    for review_item_id in sorted(expected_ids):
        observations = [
            report_map[review_item_id] for report_map in report_maps
        ]
        provisional_count = sum(
            item["status"] == "provisional_preference"
            for item in observations
        )
        if provisional_count == 0:
            continue
        chosen_counts = Counter(
            str(item["chosen"])
            for item in observations
            if item["chosen"] is not None
        )
        reward_std = {
            strategy: round(
                statistics.pstdev(
                    item["rewards"][strategy] for item in observations
                ),
                4,
            )
            for strategy in observations[0]["rewards"]
        }
        item = copy.deepcopy(source_items[review_item_id])
        item["active_learning"] = {
            "selection_reason": (
                "provisional_preference_observed_in_at_least_one_repeat"
            ),
            "observed_repeat_count": len(reports),
            "provisional_preference_count": provisional_count,
            "blocked_count": len(reports) - provisional_count,
            "chosen_by_strategy": dict(sorted(chosen_counts.items())),
            "reward_population_std_by_strategy": dict(sorted(reward_std.items())),
            "target_repeat_count": 5,
            "additional_repeats_requested": max(0, 5 - len(reports)),
        }
        selected.append(item)

    refs = report_refs or [f"report-{index + 1}" for index in range(len(reports))]
    if len(refs) != len(reports):
        raise PreferenceActiveLearningQueueError(
            "report_refs_count_mismatch"
        )
    by_channel = Counter(str(item["channel"]) for item in selected)
    by_prompt_variant = Counter(
        str(item["prompt_variant"]) for item in selected
    )
    by_case = Counter(str(item["case_id"]) for item in selected)
    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "selection_rule": (
            "ever_provisional_preference_across_completed_repeats"
        ),
        "source_queue_ref": calibration._display_path(source_queue_ref),
        "source_queue_sha256": source_hash,
        "source_preference_reports": [
            {
                "ref": calibration._display_path(ref),
                "sha256": review_queue._sha256_json(report),
            }
            for ref, report in zip(refs, reports, strict=True)
        ],
        "observed_repeat_count": len(reports),
        "target_repeat_count": 5,
        "additional_repeats_requested": max(0, 5 - len(reports)),
        "review_item_count": len(selected),
        "coverage": {
            "by_case": dict(sorted(by_case.items())),
            "by_channel": dict(sorted(by_channel.items())),
            "by_prompt_variant": dict(sorted(by_prompt_variant.items())),
        },
        "items": selected,
        "human_gold": False,
        "human_reviewed": False,
        "human_review_required": True,
        "training_eligible": False,
        "c3_authority": False,
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
        "notes": [
            "Only cases that produced a provisional preference in at least one completed repeat are selected.",
            "The queue purchases two additional repeats to estimate preference and reward stability over five observations.",
            "ReleaseFoundry-only results remain provisional and cannot become human gold, training authority, C3 evidence, or release authority.",
            "The source candidates remain text projections and do not claim native multimodal uploads.",
        ],
    }
    calibration._assert_public_summary_safe(core)
    return {
        **core,
        "artifact_hash": review_queue._sha256_json(core),
    }


def _source_items_by_id(
    source_queue: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if (
        source_queue.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise PreferenceActiveLearningQueueError(
            "source_queue_not_exploratory"
        )
    items = source_queue.get("items")
    if not isinstance(items, list) or not items:
        raise PreferenceActiveLearningQueueError("source_queue_items_missing")
    by_id = {
        str(item["review_item_id"]): item
        for item in items
        if isinstance(item, dict) and item.get("review_item_id")
    }
    if len(by_id) != len(items):
        raise PreferenceActiveLearningQueueError(
            "source_queue_review_item_ids_not_unique"
        )
    return by_id


def _validated_report_items(
    report: dict[str, Any],
    *,
    source_hash: str,
) -> dict[str, dict[str, Any]]:
    if report.get("schema_version") != "a2.releasefoundry_preference_calibration.v1":
        raise PreferenceActiveLearningQueueError(
            "preference_report_schema_mismatch"
        )
    if report.get("experiment_status") != "completed":
        raise PreferenceActiveLearningQueueError(
            "preference_report_not_completed"
        )
    if report.get("source_queue_sha256") != source_hash:
        raise PreferenceActiveLearningQueueError(
            "preference_report_source_queue_mismatch"
        )
    if (
        report.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise PreferenceActiveLearningQueueError(
            "preference_report_not_exploratory"
        )
    for field in (
        "human_gold",
        "human_reviewed",
        "training_eligible",
        "c3_authority",
        "c3_transition_allowed",
        "release_authority",
        "native_media_uploaded",
    ):
        if report.get(field) is not False:
            raise PreferenceActiveLearningQueueError(
                f"preference_report_{field}_must_be_false"
            )
    if report.get("human_review_required") is not True:
        raise PreferenceActiveLearningQueueError(
            "preference_report_human_review_required"
        )
    if report.get("text_projection_only") is not True:
        raise PreferenceActiveLearningQueueError(
            "preference_report_text_projection_boundary_missing"
        )

    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise PreferenceActiveLearningQueueError(
            "preference_report_items_missing"
        )
    result = {}
    for item in items:
        if not isinstance(item, dict) or not item.get("review_item_id"):
            raise PreferenceActiveLearningQueueError(
                "preference_report_item_invalid"
            )
        pair = (
            item.get("preference_artifact", {}).get("pair")
            if isinstance(item.get("preference_artifact"), dict)
            else None
        )
        if not isinstance(pair, dict):
            raise PreferenceActiveLearningQueueError(
                "preference_report_pair_missing"
            )
        evaluations = pair.get("releasefoundry_evaluations")
        if not isinstance(evaluations, list) or len(evaluations) != 3:
            raise PreferenceActiveLearningQueueError(
                "preference_report_evaluations_invalid"
            )
        rewards = {
            str(evaluation["candidate_id"]): float(
                evaluation["overall_reward"]
            )
            for evaluation in evaluations
            if isinstance(evaluation, dict)
            and evaluation.get("candidate_id")
            and evaluation.get("receipt_verified") is True
        }
        if len(rewards) != 3:
            raise PreferenceActiveLearningQueueError(
                "preference_report_receipts_incomplete"
            )
        chosen = pair.get("chosen")
        result[str(item["review_item_id"])] = {
            "status": pair.get("status"),
            "chosen": (
                str(chosen["candidate_id"])
                if isinstance(chosen, dict) and chosen.get("candidate_id")
                else None
            ),
            "rewards": rewards,
        }
    if len(result) != len(items):
        raise PreferenceActiveLearningQueueError(
            "preference_report_review_item_ids_not_unique"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Select high-information ReleaseFoundry preference cases for additional "
            "receipt-bound repeats."
        )
    )
    parser.add_argument(
        "--source-queue",
        default=calibration._display_path(DEFAULT_SOURCE_QUEUE),
    )
    parser.add_argument(
        "--report",
        action="append",
        help="Completed public preference report. Repeat for each observation.",
    )
    parser.add_argument(
        "--output",
        default=calibration._display_path(DEFAULT_OUTPUT),
    )
    args = parser.parse_args(argv)

    source_path = calibration._resolve(args.source_queue)
    report_paths = [
        calibration._resolve(path)
        for path in (
            args.report
            if args.report is not None
            else [calibration._display_path(path) for path in DEFAULT_REPORTS]
        )
    ]
    output_path = calibration._resolve(args.output)
    source = calibration._read_json(source_path)
    reports = [calibration._read_json(path) for path in report_paths]
    queue = build_active_learning_queue(
        source,
        reports,
        source_queue_ref=source_path,
        report_refs=report_paths,
    )
    calibration._write_public_summary(output_path, queue)
    print(
        "ReleaseFoundry preference active-learning queue written: "
        f"items={queue['review_item_count']} "
        f"observed_repeats={queue['observed_repeat_count']} "
        f"additional_repeats={queue['additional_repeats_requested']} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
