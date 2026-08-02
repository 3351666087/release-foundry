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
from scripts import a2_releasefoundry_preference_calibration as preference  # noqa: E402
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue  # noqa: E402


DEFAULT_REPORTS = tuple(
    ROOT
    / "docs"
    / "evidence"
    / f"a2_releasefoundry_quality_ladder_repeat_{repeat}.json"
    for repeat in (1, 2, 3)
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_quality_ladder_stability.json"
)
SCHEMA_VERSION = "a2.releasefoundry_quality_ladder_stability.v1"
CANDIDATE_STRATEGIES = preference.QUALITY_LADDER_STRATEGIES
COMPARISON_PAIRS = (
    ("reference_aligned", "minor_final_answer_defect"),
    ("reference_aligned", "wrong_tool_order"),
    ("reference_aligned", "observed_fixture"),
    ("minor_final_answer_defect", "minor_tool_argument_defect"),
    ("minor_tool_argument_defect", "premature_stop"),
    ("premature_stop", "wrong_final_answer"),
    ("wrong_final_answer", "severe_control"),
)
TARGET_REWARD_WINDOWS = (
    ("target_98", 95.0, 100.0),
    ("target_90", 85.0, 95.0),
    ("target_75", 70.0, 85.0),
    ("target_50", 40.0, 60.0),
    ("target_10", 0.0, 20.0),
)


class QualityLadderReportError(ValueError):
    pass


def build_quality_ladder_report(
    reports: list[dict[str, Any]],
    *,
    report_refs: list[str | Path] | None = None,
) -> dict[str, Any]:
    if len(reports) < 3:
        raise QualityLadderReportError(
            "at_least_three_quality_ladder_reports_required"
        )
    refs = report_refs or [
        f"report-{index + 1}" for index in range(len(reports))
    ]
    if len(refs) != len(reports):
        raise QualityLadderReportError("report_refs_count_mismatch")

    validated = [_validated_report(report) for report in reports]
    canonical_ids = set(validated[0]["items"])
    canonical_queue_hash = validated[0]["source_queue_sha256"]
    for report in validated[1:]:
        if set(report["items"]) != canonical_ids:
            raise QualityLadderReportError(
                "quality_ladder_task_set_mismatch"
            )
        if report["source_queue_sha256"] != canonical_queue_hash:
            raise QualityLadderReportError(
                "quality_ladder_source_queue_mismatch"
            )

    source_reports = []
    report_hashes: set[str] = set()
    experiment_labels: set[str] = set()
    observations_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metadata_by_id: dict[str, dict[str, str]] = {}
    total_evaluations = 0
    total_create_runs = 0
    total_structure_grades = 0
    total_final_answer_grades = 0

    for ref, raw_report, report in zip(
        refs, reports, validated, strict=True
    ):
        report_hash = review_queue._sha256_json(raw_report)
        if report_hash in report_hashes:
            raise QualityLadderReportError(
                "duplicate_quality_ladder_report"
            )
        report_hashes.add(report_hash)
        label = report["experiment_label"]
        if label in experiment_labels:
            raise QualityLadderReportError(
                "duplicate_quality_ladder_experiment_label"
            )
        experiment_labels.add(label)
        source_reports.append(
            {
                "ref": calibration._display_path(ref),
                "sha256": report_hash,
                "experiment_label": label,
                "task_count": len(report["items"]),
                "candidate_evaluation_count": report[
                    "candidate_evaluation_count"
                ],
                "create_run_attempt_count": report[
                    "create_run_attempt_count"
                ],
                "create_run_retry_count": 0,
            }
        )
        total_evaluations += report["candidate_evaluation_count"]
        total_create_runs += report["create_run_attempt_count"]
        total_structure_grades += report["structure_grade_count"]
        total_final_answer_grades += report["final_answer_grade_count"]

        for review_item_id, item in report["items"].items():
            metadata = item["metadata"]
            observed_metadata = metadata_by_id.setdefault(
                review_item_id,
                metadata,
            )
            if observed_metadata != metadata:
                raise QualityLadderReportError(
                    "quality_ladder_task_metadata_mismatch"
                )
            observations_by_id[review_item_id].append(
                {
                    "experiment_label": label,
                    "source_report_sha256": report_hash,
                    "status": item["status"],
                    "evaluations": item["evaluations"],
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
    task_observation_count = sum(
        item["observation_count"] for item in items
    )
    if total_evaluations != (
        task_observation_count * len(CANDIDATE_STRATEGIES)
    ):
        raise QualityLadderReportError(
            "quality_ladder_evaluation_total_mismatch"
        )

    flattened = [
        {
            "review_item_id": item["review_item_id"],
            "experiment_label": observation["experiment_label"],
            "evaluations": observation["evaluations"],
        }
        for item in items
        for observation in item["observations"]
    ]
    by_strategy = _strategy_summary(flattened)
    comparisons = _comparison_summary(flattened)
    target_coverage = _target_reward_coverage(flattened)
    sensitivity = _reference_sensitivity(flattened)
    top_set_counts = Counter(
        "+".join(observation["top_candidate_ids"])
        for item in items
        for observation in item["observations"]
    )
    pair_status_counts = Counter(
        observation["status"]
        for item in items
        for observation in item["observations"]
    )
    findings = _findings(
        sensitivity=sensitivity,
        target_coverage=target_coverage,
    )

    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "candidate_strategies": list(CANDIDATE_STRATEGIES),
        "source_queue_sha256": canonical_queue_hash,
        "source_quality_ladder_reports": source_reports,
        "experiment_summary": {
            "report_count": len(reports),
            "unique_task_count": len(items),
            "task_observation_count": task_observation_count,
            "candidate_evaluation_count": total_evaluations,
            "create_run_attempt_count": total_create_runs,
            "create_run_retry_count": 0,
            "structure_grade_count": total_structure_grades,
            "final_answer_grade_count": total_final_answer_grades,
            "per_test_receipts_verified": True,
            "exact_test_set_verified_for_every_strategy": True,
            "aggregate_marker_used_as_authority": False,
        },
        "quality_ladder_summary": {
            "pair_status_counts": dict(sorted(pair_status_counts.items())),
            "top_candidate_set_counts": dict(sorted(top_set_counts.items())),
            "reward_target_coverage": target_coverage,
            "by_strategy": by_strategy,
            "reference_sensitivity": sensitivity,
            "comparison_pairs": comparisons,
            "task_count_with_consistent_top_candidate_set": sum(
                item["top_candidate_set_consistent"] for item in items
            ),
        },
        "findings": findings,
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
            "This report aggregates receipt-bound ReleaseFoundry scores; it does not treat ReleaseFoundry output as human gold.",
            "Sensitivity classes use declared thresholds and are diagnostics, not training labels or release authority.",
            "The quality ladder uses controlled text-projection defects over the current active-learning queue.",
            "All source cases remain text projections; native image, audio, video, and document evaluation is not claimed.",
            "Any chosen/rejected pair remains ineligible for training until human adjudication confirms the preference.",
        ],
    }
    calibration._assert_public_summary_safe(core)
    return {
        **core,
        "artifact_hash": review_queue._sha256_json(core),
    }


def _validated_report(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != "a2.releasefoundry_preference_calibration.v1":
        raise QualityLadderReportError(
            "quality_ladder_report_schema_mismatch"
        )
    if report.get("strategy_profile") != "quality_ladder":
        raise QualityLadderReportError(
            "quality_ladder_strategy_profile_mismatch"
        )
    if report.get("experiment_status") != "completed":
        raise QualityLadderReportError(
            "quality_ladder_report_not_completed"
        )
    if (
        report.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise QualityLadderReportError(
            "quality_ladder_report_not_exploratory"
        )
    if tuple(report.get("candidate_strategies", [])) != (
        CANDIDATE_STRATEGIES
    ):
        raise QualityLadderReportError(
            "quality_ladder_candidate_strategies_mismatch"
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
            raise QualityLadderReportError(
                f"quality_ladder_{field}_must_be_false"
            )
    if report.get("human_review_required") is not True:
        raise QualityLadderReportError(
            "quality_ladder_human_review_required"
        )
    if report.get("text_projection_only") is not True:
        raise QualityLadderReportError(
            "quality_ladder_text_projection_boundary_missing"
        )

    label = report.get("experiment_label")
    if not isinstance(label, str) or not label:
        raise QualityLadderReportError(
            "quality_ladder_experiment_label_invalid"
        )
    source_queue_sha256 = report.get("source_queue_sha256")
    if not isinstance(source_queue_sha256, str) or not source_queue_sha256:
        raise QualityLadderReportError(
            "quality_ladder_source_queue_hash_missing"
        )
    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise QualityLadderReportError(
            "quality_ladder_report_items_missing"
        )
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        parsed = _validated_item(item)
        review_item_id = parsed["review_item_id"]
        if review_item_id in by_id:
            raise QualityLadderReportError(
                "quality_ladder_review_item_ids_not_unique"
            )
        by_id[review_item_id] = parsed

    expected_evaluations = len(by_id) * len(CANDIDATE_STRATEGIES)
    plan = report.get("experiment_plan")
    if not isinstance(plan, dict):
        raise QualityLadderReportError(
            "quality_ladder_experiment_plan_missing"
        )
    if (
        plan.get("task_count") != len(by_id)
        or plan.get("candidate_count_per_task")
        != len(CANDIDATE_STRATEGIES)
        or plan.get("observed_paid_evaluations") != expected_evaluations
        or plan.get("observed_create_run_calls")
        != len(CANDIDATE_STRATEGIES)
        or plan.get("create_run_retries") != 0
    ):
        raise QualityLadderReportError(
            "quality_ladder_experiment_plan_mismatch"
        )

    http_calls = report.get("http_calls")
    create_run = (
        http_calls.get("create_run")
        if isinstance(http_calls, dict)
        else None
    )
    if not isinstance(create_run, dict):
        raise QualityLadderReportError(
            "quality_ladder_create_run_audit_missing"
        )
    if (
        create_run.get("attempt_count") != len(CANDIDATE_STRATEGIES)
        or create_run.get("success_count") != len(CANDIDATE_STRATEGIES)
        or create_run.get("error_count") != 0
        or create_run.get("retry_count") != 0
        or create_run.get("automatic_retry_enabled") is not False
    ):
        raise QualityLadderReportError(
            "quality_ladder_create_run_audit_invalid"
        )

    server_grading = report.get("server_grading")
    if not isinstance(server_grading, dict):
        raise QualityLadderReportError(
            "quality_ladder_server_grading_missing"
        )
    if (
        server_grading.get("tests_with_structure_grading")
        != expected_evaluations
        or server_grading.get("tests_with_final_answer_grading")
        != expected_evaluations
        or server_grading.get("per_test_receipts_verified") is not True
        or server_grading.get(
            "exact_test_set_verified_for_every_strategy"
        )
        is not True
        or server_grading.get("aggregate_marker_used_as_authority")
        is not False
    ):
        raise QualityLadderReportError(
            "quality_ladder_server_grading_incomplete"
        )
    return {
        "experiment_label": label,
        "source_queue_sha256": source_queue_sha256,
        "items": by_id,
        "candidate_evaluation_count": expected_evaluations,
        "create_run_attempt_count": len(CANDIDATE_STRATEGIES),
        "structure_grade_count": expected_evaluations,
        "final_answer_grade_count": expected_evaluations,
    }


def _validated_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or not item.get("review_item_id"):
        raise QualityLadderReportError("quality_ladder_item_invalid")
    metadata = {
        key: str(item[key])
        for key in (
            "case_id",
            "channel",
            "prompt_variant",
            "expected_variant",
        )
        if item.get(key) is not None
    }
    if len(metadata) != 4:
        raise QualityLadderReportError(
            "quality_ladder_item_metadata_missing"
        )
    artifact = item.get("preference_artifact")
    pair = artifact.get("pair") if isinstance(artifact, dict) else None
    if not isinstance(pair, dict):
        raise QualityLadderReportError("quality_ladder_pair_missing")
    status = pair.get("status")
    if status not in {"blocked", "provisional_preference"}:
        raise QualityLadderReportError(
            "quality_ladder_pair_status_invalid"
        )
    raw_evaluations = pair.get("releasefoundry_evaluations")
    if not isinstance(raw_evaluations, list) or len(raw_evaluations) != len(
        CANDIDATE_STRATEGIES
    ):
        raise QualityLadderReportError(
            "quality_ladder_evaluations_invalid"
        )
    evaluations: dict[str, dict[str, Any]] = {}
    for raw in raw_evaluations:
        evaluation = _validated_evaluation(raw)
        candidate_id = evaluation["candidate_id"]
        if candidate_id in evaluations:
            raise QualityLadderReportError(
                "quality_ladder_candidate_ids_not_unique"
            )
        evaluations[candidate_id] = evaluation
    if set(evaluations) != set(CANDIDATE_STRATEGIES):
        raise QualityLadderReportError(
            "quality_ladder_receipts_incomplete"
        )
    return {
        "review_item_id": str(item["review_item_id"]),
        "metadata": metadata,
        "status": status,
        "evaluations": {
            strategy: evaluations[strategy]
            for strategy in CANDIDATE_STRATEGIES
        },
    }


def _validated_evaluation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise QualityLadderReportError(
            "quality_ladder_evaluation_invalid"
        )
    candidate_id = raw.get("candidate_id")
    if candidate_id not in CANDIDATE_STRATEGIES:
        raise QualityLadderReportError(
            "quality_ladder_candidate_id_invalid"
        )
    if raw.get("receipt_verified") is not True:
        raise QualityLadderReportError(
            "quality_ladder_receipt_not_verified"
        )
    action_scores = raw.get("action_scores")
    if not isinstance(action_scores, list) or not action_scores:
        raise QualityLadderReportError(
            "quality_ladder_action_scores_missing"
        )
    parsed_action_scores = []
    for action in action_scores:
        if not isinstance(action, dict) or not isinstance(
            action.get("score"),
            (int, float),
        ):
            raise QualityLadderReportError(
                "quality_ladder_action_score_invalid"
            )
        parsed_action_scores.append(float(action["score"]))
    for field in ("overall_reward", "final_answer_score"):
        if not isinstance(raw.get(field), (int, float)):
            raise QualityLadderReportError(
                f"quality_ladder_{field}_invalid"
            )
    rank = raw.get("rank")
    if not isinstance(rank, int) or rank < 1:
        raise QualityLadderReportError(
            "quality_ladder_rank_invalid"
        )
    return {
        "candidate_id": str(candidate_id),
        "overall_reward": float(raw["overall_reward"]),
        "final_answer_score": float(raw["final_answer_score"]),
        "mean_action_score": statistics.fmean(parsed_action_scores),
        "action_count": len(parsed_action_scores),
        "failure_type": str(raw.get("failure_type", "unknown")),
        "severity": str(raw.get("severity", "unknown")),
        "rank": rank,
    }


def _stability_item(
    review_item_id: str,
    metadata: dict[str, str],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    public_observations = []
    top_candidate_sets = []
    for observation in observations:
        evaluations = observation["evaluations"]
        maximum = max(
            evaluation["overall_reward"]
            for evaluation in evaluations.values()
        )
        top_candidate_ids = sorted(
            strategy
            for strategy, evaluation in evaluations.items()
            if evaluation["overall_reward"] == maximum
        )
        top_candidate_sets.append(tuple(top_candidate_ids))
        public_observations.append(
            {
                **observation,
                "top_candidate_ids": top_candidate_ids,
            }
        )
    reward_by_strategy = {
        strategy: [
            observation["evaluations"][strategy]["overall_reward"]
            for observation in observations
        ]
        for strategy in CANDIDATE_STRATEGIES
    }
    return {
        "review_item_id": review_item_id,
        **metadata,
        "observation_count": len(observations),
        "top_candidate_set_consistent": len(set(top_candidate_sets)) == 1,
        "reward_distribution_by_strategy": {
            strategy: _distribution(reward_by_strategy[strategy])
            for strategy in CANDIDATE_STRATEGIES
        },
        "reference_gap_by_strategy": {
            strategy: _signed_gap_summary(
                [
                    observation["evaluations"]["reference_aligned"][
                        "overall_reward"
                    ]
                    - observation["evaluations"][strategy]["overall_reward"]
                    for observation in observations
                ]
            )
            for strategy in CANDIDATE_STRATEGIES
            if strategy != "reference_aligned"
        },
        "observations": public_observations,
        "human_review_required": True,
        "training_eligible": False,
    }


def _strategy_summary(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {}
    for strategy in CANDIDATE_STRATEGIES:
        evaluations = [
            observation["evaluations"][strategy]
            for observation in observations
        ]
        task_groups: dict[str, list[float]] = defaultdict(list)
        for observation, evaluation in zip(
            observations,
            evaluations,
            strict=True,
        ):
            task_groups[observation["review_item_id"]].append(
                evaluation["overall_reward"]
            )
        task_std = [
            statistics.pstdev(values) for values in task_groups.values()
        ]
        summary[strategy] = {
            "overall_reward": _distribution(
                [item["overall_reward"] for item in evaluations]
            ),
            "final_answer_score": _distribution(
                [item["final_answer_score"] for item in evaluations]
            ),
            "mean_action_score": _distribution(
                [item["mean_action_score"] for item in evaluations]
            ),
            "action_count_distribution": dict(
                sorted(
                    Counter(
                        str(item["action_count"]) for item in evaluations
                    ).items()
                )
            ),
            "failure_type_counts": dict(
                sorted(
                    Counter(
                        item["failure_type"] for item in evaluations
                    ).items()
                )
            ),
            "severity_counts": dict(
                sorted(
                    Counter(
                        item["severity"] for item in evaluations
                    ).items()
                )
            ),
            "rank_counts": dict(
                sorted(
                    Counter(
                        str(item["rank"]) for item in evaluations
                    ).items()
                )
            ),
            "repeat_variability": {
                "task_count": len(task_std),
                "mean_within_task_population_std": round(
                    statistics.fmean(task_std),
                    4,
                ),
                "maximum_within_task_population_std": round(
                    max(task_std),
                    4,
                ),
                "tasks_with_reward_range_at_most_2": sum(
                    max(values) - min(values) <= 2
                    for values in task_groups.values()
                ),
            },
        }
    return summary


def _comparison_summary(
    observations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for first, second in COMPARISON_PAIRS:
        gaps = [
            observation["evaluations"][first]["overall_reward"]
            - observation["evaluations"][second]["overall_reward"]
            for observation in observations
        ]
        rows.append(
            {
                "first_candidate_id": first,
                "second_candidate_id": second,
                "first_minus_second_reward_gap": _signed_gap_summary(gaps),
            }
        )
    return rows


def _reference_sensitivity(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    sensitivity = {}
    for strategy in CANDIDATE_STRATEGIES:
        if strategy == "reference_aligned":
            continue
        gaps = [
            observation["evaluations"]["reference_aligned"][
                "overall_reward"
            ]
            - observation["evaluations"][strategy]["overall_reward"]
            for observation in observations
        ]
        within_two_count = sum(abs(gap) <= 2 for gap in gaps)
        within_two_rate = within_two_count / len(gaps)
        mean_gap = statistics.fmean(gaps)
        if within_two_rate >= 0.8:
            sensitivity_class = (
                "mostly_indistinguishable_from_reference"
            )
        elif mean_gap >= 20:
            sensitivity_class = "strongly_penalized"
        elif mean_gap >= 8:
            sensitivity_class = "moderately_penalized"
        elif mean_gap >= 2:
            sensitivity_class = "weakly_penalized"
        else:
            sensitivity_class = "inconsistent_or_unpenalized"
        sensitivity[strategy] = {
            "reference_minus_candidate_reward_gap": (
                _signed_gap_summary(gaps)
            ),
            "absolute_gap_at_most_2_count": within_two_count,
            "absolute_gap_at_most_2_rate": round(within_two_rate, 4),
            "sensitivity_class": sensitivity_class,
            "classification_thresholds": {
                "mostly_indistinguishable_from_reference": (
                    "absolute_gap_at_most_2_rate >= 0.8"
                ),
                "strongly_penalized": (
                    "mean_signed_gap >= 20 after indistinguishable check"
                ),
                "moderately_penalized": (
                    "mean_signed_gap >= 8 after stronger checks"
                ),
                "weakly_penalized": (
                    "mean_signed_gap >= 2 after stronger checks"
                ),
                "inconsistent_or_unpenalized": (
                    "all remaining observations"
                ),
            },
        }
    return sensitivity


def _target_reward_coverage(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    rewards = [
        evaluation["overall_reward"]
        for observation in observations
        for evaluation in observation["evaluations"].values()
    ]
    coverage = {}
    for name, lower, upper in TARGET_REWARD_WINDOWS:
        inclusive_upper = upper == 100.0
        matching = [
            reward
            for reward in rewards
            if reward >= lower
            and (reward <= upper if inclusive_upper else reward < upper)
        ]
        coverage[name] = {
            "lower_bound_inclusive": lower,
            "upper_bound": upper,
            "upper_bound_inclusive": inclusive_upper,
            "observation_count": len(matching),
            "covered": bool(matching),
        }
    return coverage


def _findings(
    *,
    sensitivity: dict[str, Any],
    target_coverage: dict[str, Any],
) -> list[str]:
    findings = []
    ignored = sorted(
        strategy
        for strategy, row in sensitivity.items()
        if row["sensitivity_class"]
        == "mostly_indistinguishable_from_reference"
    )
    if ignored:
        findings.append(
            "ReleaseFoundry treated these controlled perturbations as mostly "
            "indistinguishable from the reference under the declared "
            f"threshold: {', '.join(ignored)}."
        )
    missing_targets = sorted(
        name
        for name, row in target_coverage.items()
        if not row["covered"]
    )
    if missing_targets:
        findings.append(
            "The current ladder does not populate these target reward "
            f"windows: {', '.join(missing_targets)}."
        )
    findings.extend(
        [
            "The controlled ladder now spans top, intermediate, and severe reward regions, allowing active learning to target missing or unstable bands.",
            "ReleaseFoundry-only ranks and rewards remain teacher observations; human adjudication is required before producing training-eligible preference pairs.",
        ]
    )
    return findings


def _signed_gap_summary(values: list[float]) -> dict[str, Any]:
    return {
        **_distribution(values),
        "positive_count": sum(value > 0 for value in values),
        "zero_count": sum(value == 0 for value in values),
        "negative_count": sum(value < 0 for value in values),
    }


def _distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise QualityLadderReportError("empty_distribution")
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
            "Aggregate repeated receipt-bound ReleaseFoundry quality-ladder "
            "experiments into a public sensitivity report."
        )
    )
    parser.add_argument(
        "--report",
        action="append",
        help="Completed quality-ladder report. Repeat in experiment order.",
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
            else [
                calibration._display_path(path)
                for path in DEFAULT_REPORTS
            ]
        )
    ]
    output_path = calibration._resolve(args.output)
    reports = [calibration._read_json(path) for path in report_paths]
    quality_report = build_quality_ladder_report(
        reports,
        report_refs=report_paths,
    )
    calibration._write_public_summary(output_path, quality_report)
    summary = quality_report["experiment_summary"]
    print(
        "ReleaseFoundry quality ladder stability report written: "
        f"tasks={summary['unique_task_count']} "
        f"observations={summary['task_observation_count']} "
        f"evaluations={summary['candidate_evaluation_count']} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
