from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import a2_releasefoundry_live_calibration as calibration  # noqa: E402
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue  # noqa: E402


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
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_preference_active_repeat_4.json",
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_preference_active_repeat_5.json",
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_preference_stability_report.json"
)
SCHEMA_VERSION = "a2.releasefoundry_preference_stability.v1"
CANDIDATE_STRATEGIES = (
    "degraded_control",
    "observed_fixture",
    "reference_aligned",
)


class PreferenceStabilityReportError(ValueError):
    pass


def build_stability_report(
    reports: list[dict[str, Any]],
    *,
    report_refs: list[str | Path] | None = None,
) -> dict[str, Any]:
    if len(reports) < 2:
        raise PreferenceStabilityReportError(
            "at_least_two_preference_reports_required"
        )
    refs = report_refs or [
        f"report-{index + 1}" for index in range(len(reports))
    ]
    if len(refs) != len(reports):
        raise PreferenceStabilityReportError("report_refs_count_mismatch")

    validated_reports = [
        _validated_report(report, report_index=index)
        for index, report in enumerate(reports)
    ]
    canonical_ids = set(validated_reports[0]["items"])
    if not canonical_ids:
        raise PreferenceStabilityReportError("canonical_report_items_missing")
    for report in validated_reports[1:]:
        if not set(report["items"]).issubset(canonical_ids):
            raise PreferenceStabilityReportError(
                "preference_report_contains_unknown_task"
            )

    observations_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metadata_by_id: dict[str, dict[str, str]] = {}
    source_reports = []
    total_create_run_attempts = 0
    total_create_run_retries = 0
    total_candidate_evaluations = 0
    total_structure_grades = 0
    total_final_answer_grades = 0
    report_hashes: set[str] = set()

    for ref, raw_report, report in zip(
        refs, reports, validated_reports, strict=True
    ):
        report_hash = review_queue._sha256_json(raw_report)
        if report_hash in report_hashes:
            raise PreferenceStabilityReportError(
                "duplicate_preference_report"
            )
        report_hashes.add(report_hash)
        source_reports.append(
            {
                "ref": calibration._display_path(ref),
                "sha256": report_hash,
                "experiment_label": report["experiment_label"],
                "task_count": len(report["items"]),
                "candidate_evaluation_count": report[
                    "candidate_evaluation_count"
                ],
                "create_run_attempt_count": report[
                    "create_run_attempt_count"
                ],
                "create_run_retry_count": report[
                    "create_run_retry_count"
                ],
            }
        )
        total_create_run_attempts += report["create_run_attempt_count"]
        total_create_run_retries += report["create_run_retry_count"]
        total_candidate_evaluations += report[
            "candidate_evaluation_count"
        ]
        total_structure_grades += report["structure_grade_count"]
        total_final_answer_grades += report["final_answer_grade_count"]

        for review_item_id, item in report["items"].items():
            metadata = item["metadata"]
            observed_metadata = metadata_by_id.setdefault(
                review_item_id, metadata
            )
            if observed_metadata != metadata:
                raise PreferenceStabilityReportError(
                    "preference_report_task_metadata_mismatch"
                )
            observations_by_id[review_item_id].append(
                {
                    "experiment_label": report["experiment_label"],
                    "source_report_sha256": report_hash,
                    "status": item["status"],
                    "chosen_candidate_id": item["chosen"],
                    "rejected_candidate_id": item["rejected"],
                    "rewards": item["rewards"],
                    "reference_minus_observed_reward_gap": round(
                        item["rewards"]["reference_aligned"]
                        - item["rewards"]["observed_fixture"],
                        4,
                    ),
                }
            )

    items = [
        _stability_item(
            review_item_id,
            metadata_by_id[review_item_id],
            observations_by_id[review_item_id],
        )
        for review_item_id in sorted(canonical_ids)
    ]
    observation_count_distribution = Counter(
        str(item["observation_count"]) for item in items
    )
    stability_counts = Counter(
        item["preference_stability"] for item in items
    )
    majority_counts = Counter(
        item["strict_majority_candidate"]
        for item in items
        if item["strict_majority_candidate"] is not None
    )
    all_rewards: dict[str, list[float]] = {
        strategy: [] for strategy in CANDIDATE_STRATEGIES
    }
    all_gaps: list[float] = []
    status_counts: Counter[str] = Counter()
    chosen_counts: Counter[str] = Counter()
    for item in items:
        for observation in item["observations"]:
            status_counts[observation["status"]] += 1
            if observation["chosen_candidate_id"] is not None:
                chosen_counts[observation["chosen_candidate_id"]] += 1
            for strategy, reward in observation["rewards"].items():
                all_rewards[strategy].append(reward)
            all_gaps.append(
                observation["reference_minus_observed_reward_gap"]
            )

    task_observation_count = sum(
        item["observation_count"] for item in items
    )
    if total_candidate_evaluations != (
        task_observation_count * len(CANDIDATE_STRATEGIES)
    ):
        raise PreferenceStabilityReportError(
            "candidate_evaluation_total_mismatch"
        )

    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "candidate_strategies": list(CANDIDATE_STRATEGIES),
        "source_preference_reports": source_reports,
        "experiment_summary": {
            "report_count": len(reports),
            "unique_task_count": len(items),
            "task_observation_count": task_observation_count,
            "candidate_evaluation_count": total_candidate_evaluations,
            "create_run_attempt_count": total_create_run_attempts,
            "create_run_retry_count": total_create_run_retries,
            "structure_grade_count": total_structure_grades,
            "final_answer_grade_count": total_final_answer_grades,
            "per_test_receipts_verified": True,
            "aggregate_marker_used_as_authority": False,
            "observation_count_distribution": dict(
                sorted(observation_count_distribution.items())
            ),
        },
        "preference_stability_summary": {
            "status_counts": dict(sorted(status_counts.items())),
            "chosen_by_strategy": {
                strategy: chosen_counts.get(strategy, 0)
                for strategy in CANDIDATE_STRATEGIES
            },
            "preference_stability_counts": {
                category: stability_counts.get(category, 0)
                for category in (
                    "always_blocked_or_tied",
                    "unanimous_stable_preference",
                    "strict_majority_preference",
                    "weak_or_conflicting_preference",
                )
            },
            "strict_majority_by_strategy": {
                strategy: majority_counts.get(strategy, 0)
                for strategy in CANDIDATE_STRATEGIES
            },
            "task_count_without_strict_majority": sum(
                item["strict_majority_candidate"] is None
                for item in items
            ),
            "reward_distribution_by_strategy": {
                strategy: _distribution(all_rewards[strategy])
                for strategy in CANDIDATE_STRATEGIES
            },
            "reference_minus_observed_reward_gap": {
                **_distribution(all_gaps),
                "positive_count": sum(gap > 0 for gap in all_gaps),
                "zero_count": sum(gap == 0 for gap in all_gaps),
                "negative_count": sum(gap < 0 for gap in all_gaps),
            },
        },
        "items": items,
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
        "notes": [
            "The report aggregates receipt-bound ReleaseFoundry observations without treating any ReleaseFoundry-only preference as human gold.",
            "A strict majority is measured against all observations for a task, including blocked or tied observations.",
            "The current three-candidate design separates severe controls reliably but often saturates near the top reward band.",
            "Preference pairs remain ineligible for training until human adjudication confirms that the chosen candidate is actually better.",
            "All source cases are text projections; this report does not claim native image, audio, video, or document evaluation.",
        ],
    }
    calibration._assert_public_summary_safe(core)
    return {
        **core,
        "artifact_hash": review_queue._sha256_json(core),
    }


def _validated_report(
    report: dict[str, Any],
    *,
    report_index: int,
) -> dict[str, Any]:
    if report.get("schema_version") != "a2.releasefoundry_preference_calibration.v1":
        raise PreferenceStabilityReportError(
            "preference_report_schema_mismatch"
        )
    if report.get("experiment_status") != "completed":
        raise PreferenceStabilityReportError(
            "preference_report_not_completed"
        )
    if (
        report.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise PreferenceStabilityReportError(
            "preference_report_not_exploratory"
        )
    if sorted(report.get("candidate_strategies", [])) != list(
        CANDIDATE_STRATEGIES
    ):
        raise PreferenceStabilityReportError(
            "preference_report_candidate_strategies_mismatch"
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
            raise PreferenceStabilityReportError(
                f"preference_report_{field}_must_be_false"
            )
    if report.get("human_review_required") is not True:
        raise PreferenceStabilityReportError(
            "preference_report_human_review_required"
        )
    if report.get("text_projection_only") is not True:
        raise PreferenceStabilityReportError(
            "preference_report_text_projection_boundary_missing"
        )

    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise PreferenceStabilityReportError(
            "preference_report_items_missing"
        )
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        parsed = _validated_item(item)
        review_item_id = parsed["review_item_id"]
        if review_item_id in by_id:
            raise PreferenceStabilityReportError(
                "preference_report_review_item_ids_not_unique"
            )
        by_id[review_item_id] = parsed

    expected_evaluations = len(by_id) * len(CANDIDATE_STRATEGIES)
    plan = report.get("experiment_plan")
    if not isinstance(plan, dict):
        raise PreferenceStabilityReportError(
            "preference_report_experiment_plan_missing"
        )
    if plan.get("task_count") != len(by_id):
        raise PreferenceStabilityReportError(
            "preference_report_task_count_mismatch"
        )
    if plan.get("candidate_count_per_task") != len(CANDIDATE_STRATEGIES):
        raise PreferenceStabilityReportError(
            "preference_report_candidate_count_mismatch"
        )
    if plan.get("observed_paid_evaluations") != expected_evaluations:
        raise PreferenceStabilityReportError(
            "preference_report_paid_evaluation_count_mismatch"
        )

    http_calls = report.get("http_calls")
    create_run = (
        http_calls.get("create_run")
        if isinstance(http_calls, dict)
        else None
    )
    if not isinstance(create_run, dict):
        raise PreferenceStabilityReportError(
            "preference_report_create_run_audit_missing"
        )
    if create_run.get("automatic_retry_enabled") is not False:
        raise PreferenceStabilityReportError(
            "preference_report_create_run_retry_enabled"
        )
    if create_run.get("retry_count") != 0:
        raise PreferenceStabilityReportError(
            "preference_report_create_run_retry_observed"
        )
    attempt_count = create_run.get("attempt_count")
    if (
        attempt_count != len(CANDIDATE_STRATEGIES)
        or create_run.get("success_count") != attempt_count
        or create_run.get("error_count") != 0
    ):
        raise PreferenceStabilityReportError(
            "preference_report_create_run_count_mismatch"
        )

    server_grading = report.get("server_grading")
    if not isinstance(server_grading, dict):
        raise PreferenceStabilityReportError(
            "preference_report_server_grading_missing"
        )
    if (
        server_grading.get("per_test_receipts_verified") is not True
        or server_grading.get("aggregate_marker_used_as_authority") is not False
        or server_grading.get("tests_with_structure_grading")
        != expected_evaluations
        or server_grading.get("tests_with_final_answer_grading")
        != expected_evaluations
    ):
        raise PreferenceStabilityReportError(
            "preference_report_server_grading_incomplete"
        )

    label = report.get("experiment_label")
    if label is None:
        label = "baseline" if report_index == 0 else f"repeat_{report_index + 1}"
    if not isinstance(label, str) or not label:
        raise PreferenceStabilityReportError(
            "preference_report_experiment_label_invalid"
        )
    return {
        "experiment_label": label,
        "items": by_id,
        "candidate_evaluation_count": expected_evaluations,
        "create_run_attempt_count": attempt_count,
        "create_run_retry_count": 0,
        "structure_grade_count": expected_evaluations,
        "final_answer_grade_count": expected_evaluations,
    }


def _validated_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or not item.get("review_item_id"):
        raise PreferenceStabilityReportError(
            "preference_report_item_invalid"
        )
    metadata = {
        key: str(item[key])
        for key in ("case_id", "channel", "prompt_variant", "expected_variant")
        if item.get(key) is not None
    }
    if len(metadata) != 4:
        raise PreferenceStabilityReportError(
            "preference_report_item_metadata_missing"
        )
    preference_artifact = item.get("preference_artifact")
    pair = (
        preference_artifact.get("pair")
        if isinstance(preference_artifact, dict)
        else None
    )
    if not isinstance(pair, dict):
        raise PreferenceStabilityReportError(
            "preference_report_pair_missing"
        )
    status = pair.get("status")
    if status not in {"blocked", "provisional_preference"}:
        raise PreferenceStabilityReportError(
            "preference_report_pair_status_invalid"
        )
    evaluations = pair.get("releasefoundry_evaluations")
    if not isinstance(evaluations, list) or len(evaluations) != len(
        CANDIDATE_STRATEGIES
    ):
        raise PreferenceStabilityReportError(
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
    if sorted(rewards) != list(CANDIDATE_STRATEGIES):
        raise PreferenceStabilityReportError(
            "preference_report_receipts_incomplete"
        )
    chosen = _candidate_id(pair.get("chosen"))
    rejected = _candidate_id(pair.get("rejected"))
    if status == "blocked" and (chosen is not None or rejected is not None):
        raise PreferenceStabilityReportError(
            "preference_report_blocked_pair_has_choice"
        )
    if status == "provisional_preference" and (
        chosen not in CANDIDATE_STRATEGIES
        or rejected not in CANDIDATE_STRATEGIES
        or chosen == rejected
    ):
        raise PreferenceStabilityReportError(
            "preference_report_provisional_pair_invalid"
        )
    return {
        "review_item_id": str(item["review_item_id"]),
        "metadata": metadata,
        "status": status,
        "chosen": chosen,
        "rejected": rejected,
        "rewards": {
            strategy: rewards[strategy]
            for strategy in CANDIDATE_STRATEGIES
        },
    }


def _candidate_id(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("candidate_id"):
        return str(value["candidate_id"])
    return None


def _stability_item(
    review_item_id: str,
    metadata: dict[str, str],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts = Counter(
        observation["status"] for observation in observations
    )
    chosen_counts = Counter(
        observation["chosen_candidate_id"]
        for observation in observations
        if observation["chosen_candidate_id"] is not None
    )
    observation_count = len(observations)
    strict_majority_candidate = next(
        (
            strategy
            for strategy in CANDIDATE_STRATEGIES
            if chosen_counts[strategy] > observation_count / 2
        ),
        None,
    )
    if status_counts["blocked"] == observation_count:
        preference_stability = "always_blocked_or_tied"
    elif (
        strict_majority_candidate is not None
        and chosen_counts[strict_majority_candidate] == observation_count
    ):
        preference_stability = "unanimous_stable_preference"
    elif strict_majority_candidate is not None:
        preference_stability = "strict_majority_preference"
    else:
        preference_stability = "weak_or_conflicting_preference"

    rewards_by_strategy = {
        strategy: [
            observation["rewards"][strategy]
            for observation in observations
        ]
        for strategy in CANDIDATE_STRATEGIES
    }
    gaps = [
        observation["reference_minus_observed_reward_gap"]
        for observation in observations
    ]
    return {
        "review_item_id": review_item_id,
        **metadata,
        "observation_count": observation_count,
        "status_counts": {
            status: status_counts.get(status, 0)
            for status in ("blocked", "provisional_preference")
        },
        "chosen_by_strategy": {
            strategy: chosen_counts.get(strategy, 0)
            for strategy in CANDIDATE_STRATEGIES
        },
        "strict_majority_candidate": strict_majority_candidate,
        "preference_stability": preference_stability,
        "reward_distribution_by_strategy": {
            strategy: _distribution(rewards_by_strategy[strategy])
            for strategy in CANDIDATE_STRATEGIES
        },
        "reference_minus_observed_reward_gap": {
            **_distribution(gaps),
            "positive_count": sum(gap > 0 for gap in gaps),
            "zero_count": sum(gap == 0 for gap in gaps),
            "negative_count": sum(gap < 0 for gap in gaps),
        },
        "observations": observations,
        "human_review_required": True,
        "training_eligible": False,
    }


def _distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise PreferenceStabilityReportError("empty_distribution")
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 4),
        "population_std": round(statistics.pstdev(values), 4),
        "minimum": round(min(values), 4),
        "maximum": round(max(values), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate repeated receipt-bound ReleaseFoundry preference experiments "
            "into a public stability report."
        )
    )
    parser.add_argument(
        "--report",
        action="append",
        help="Completed public preference report. Repeat in experiment order.",
    )
    parser.add_argument(
        "--output",
        default=calibration._display_path(DEFAULT_OUTPUT),
    )
    args = parser.parse_args(argv)

    report_paths = [
        calibration._resolve(path)
        for path in (
            args.report
            if args.report is not None
            else [calibration._display_path(path) for path in DEFAULT_REPORTS]
        )
    ]
    output_path = calibration._resolve(args.output)
    reports = [calibration._read_json(path) for path in report_paths]
    stability = build_stability_report(
        reports,
        report_refs=report_paths,
    )
    calibration._write_public_summary(output_path, stability)
    summary = stability["experiment_summary"]
    print(
        "ReleaseFoundry preference stability report written: "
        f"tasks={summary['unique_task_count']} "
        f"observations={summary['task_observation_count']} "
        f"evaluations={summary['candidate_evaluation_count']} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
