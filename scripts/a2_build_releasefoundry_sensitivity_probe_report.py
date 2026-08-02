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
    / f"a2_releasefoundry_sensitivity_probe_corrected_order_repeat_{repeat}.json"
    for repeat in (1, 2, 3)
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_sensitivity_probe_corrected_order_stability.json"
)
SCHEMA_VERSION = "a2.releasefoundry_sensitivity_probe_corrected_order_stability.v1"
REQUIRED_HARNESS_REVISION = "a2-releasefoundry-live-v5"
REQUIRED_TOOL_CALL_ALIGNMENT = "positional"
CANDIDATE_STRATEGIES = preference.SENSITIVITY_PROBE_STRATEGIES
ORDER_PROBES = ("wrong_tool_order", "reverse_tool_order")
DISTILLATION_PAIRS = (
    ("reference_aligned", "tool_and_answer_defect"),
    ("missing_middle_tool", "tool_and_answer_defect"),
    ("tool_and_answer_defect", "severe_control"),
)


class SensitivityProbeReportError(ValueError):
    pass


def build_sensitivity_probe_report(
    reports: list[dict[str, Any]],
    *,
    report_refs: list[str | Path] | None = None,
) -> dict[str, Any]:
    if len(reports) < 3:
        raise SensitivityProbeReportError(
            "at_least_three_sensitivity_probe_reports_required"
        )
    refs = report_refs or [
        f"report-{index + 1}" for index in range(len(reports))
    ]
    if len(refs) != len(reports):
        raise SensitivityProbeReportError("report_refs_count_mismatch")

    validated = [_validated_report(report) for report in reports]
    canonical_ids = set(validated[0]["items"])
    canonical_queue_hash = validated[0]["source_queue_sha256"]
    for report in validated[1:]:
        if set(report["items"]) != canonical_ids:
            raise SensitivityProbeReportError(
                "sensitivity_probe_task_set_mismatch"
            )
        if report["source_queue_sha256"] != canonical_queue_hash:
            raise SensitivityProbeReportError(
                "sensitivity_probe_source_queue_mismatch"
            )

    source_reports = []
    report_hashes: set[str] = set()
    experiment_labels: set[str] = set()
    observations_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metadata_by_id: dict[str, dict[str, str]] = {}
    total_evaluations = 0
    total_create_runs = 0

    for ref, raw_report, report in zip(
        refs, reports, validated, strict=True
    ):
        report_hash = review_queue._sha256_json(raw_report)
        if report_hash in report_hashes:
            raise SensitivityProbeReportError(
                "duplicate_sensitivity_probe_report"
            )
        report_hashes.add(report_hash)
        label = report["experiment_label"]
        if label in experiment_labels:
            raise SensitivityProbeReportError(
                "duplicate_sensitivity_probe_experiment_label"
            )
        experiment_labels.add(label)
        source_reports.append(
            {
                "ref": calibration._display_path(ref),
                "sha256": report_hash,
                "experiment_label": label,
                "harness_revision": report["harness_revision"],
                "tool_call_alignment": report["tool_call_alignment"],
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
        for review_item_id, item in report["items"].items():
            metadata = item["metadata"]
            observed_metadata = metadata_by_id.setdefault(
                review_item_id,
                metadata,
            )
            if observed_metadata != metadata:
                raise SensitivityProbeReportError(
                    "sensitivity_probe_task_metadata_mismatch"
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
        _probe_item(
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
        raise SensitivityProbeReportError(
            "sensitivity_probe_evaluation_total_mismatch"
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
    order_blind_spot = _order_blind_spot_summary(flattened)
    distillation_pairs = _distillation_pair_summary(items)
    target_50_rewards = [
        observation["evaluations"]["tool_and_answer_defect"][
            "overall_reward"
        ]
        for observation in flattened
        if 40
        <= observation["evaluations"]["tool_and_answer_defect"][
            "overall_reward"
        ]
        < 60
    ]
    pair_status_counts = Counter(
        observation["status"]
        for item in items
        for observation in item["observations"]
    )
    findings = _findings(
        order_blind_spot=order_blind_spot,
        target_50_count=len(target_50_rewards),
        target_50_total=len(flattened),
    )

    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "harness_revision": REQUIRED_HARNESS_REVISION,
        "tool_call_alignment": REQUIRED_TOOL_CALL_ALIGNMENT,
        "candidate_strategies": list(CANDIDATE_STRATEGIES),
        "source_queue_sha256": canonical_queue_hash,
        "source_sensitivity_probe_reports": source_reports,
        "experiment_summary": {
            "report_count": len(reports),
            "unique_task_count": len(items),
            "task_observation_count": task_observation_count,
            "candidate_evaluation_count": total_evaluations,
            "create_run_attempt_count": total_create_runs,
            "create_run_retry_count": 0,
            "structure_grade_count": total_evaluations,
            "final_answer_grade_count": total_evaluations,
            "per_test_receipts_verified": True,
            "exact_test_set_verified_for_every_strategy": True,
            "aggregate_marker_used_as_authority": False,
        },
        "sensitivity_probe_summary": {
            "pair_status_counts": dict(sorted(pair_status_counts.items())),
            "by_strategy": by_strategy,
            "order_blind_spot": order_blind_spot,
            "target_50_window": {
                "strategy": "tool_and_answer_defect",
                "lower_bound_inclusive": 40.0,
                "upper_bound_exclusive": 60.0,
                "observation_count": len(target_50_rewards),
                "total_observation_count": len(flattened),
                "coverage_rate": round(
                    len(target_50_rewards) / len(flattened),
                    4,
                ),
                "covered": bool(target_50_rewards),
            },
            "provisional_distillation_pair_diagnostics": (
                distillation_pairs
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
            "The probe uses official receipt-bound ReleaseFoundry scores but does not treat the service as human gold.",
            "Every source report was produced by the positional a2-releasefoundry-live-v5 harness, so reordered, omitted, and unexpected calls remain in submitted trace order.",
            "Historical pre-v5 order-probe reports remain preserved but are governed by docs/evidence/a2_releasefoundry_order_probe_methodology_correction.json and are not inputs to this corrected stability artifact.",
            "Provisional distillation pair diagnostics describe reward separation only; every pair remains training-ineligible until human adjudication.",
            "All source cases remain text projections and do not establish native multimodal capability.",
        ],
    }
    calibration._assert_public_summary_safe(core)
    return {
        **core,
        "artifact_hash": review_queue._sha256_json(core),
    }


def _validated_report(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema_version") != "a2.releasefoundry_preference_calibration.v1":
        raise SensitivityProbeReportError(
            "sensitivity_probe_report_schema_mismatch"
        )
    if report.get("strategy_profile") != "sensitivity_probe":
        raise SensitivityProbeReportError(
            "sensitivity_probe_strategy_profile_mismatch"
        )
    if report.get("experiment_status") != "completed":
        raise SensitivityProbeReportError(
            "sensitivity_probe_report_not_completed"
        )
    if report.get("harness_revision") != REQUIRED_HARNESS_REVISION:
        raise SensitivityProbeReportError(
            "sensitivity_probe_harness_revision_mismatch"
        )
    if report.get("tool_call_alignment") != REQUIRED_TOOL_CALL_ALIGNMENT:
        raise SensitivityProbeReportError(
            "sensitivity_probe_tool_call_alignment_mismatch"
        )
    if tuple(report.get("candidate_strategies", [])) != (
        CANDIDATE_STRATEGIES
    ):
        raise SensitivityProbeReportError(
            "sensitivity_probe_candidate_strategies_mismatch"
        )
    if (
        report.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise SensitivityProbeReportError(
            "sensitivity_probe_report_not_exploratory"
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
            raise SensitivityProbeReportError(
                f"sensitivity_probe_{field}_must_be_false"
            )
    if (
        report.get("human_review_required") is not True
        or report.get("text_projection_only") is not True
    ):
        raise SensitivityProbeReportError(
            "sensitivity_probe_evidence_boundary_invalid"
        )

    label = report.get("experiment_label")
    source_queue_sha256 = report.get("source_queue_sha256")
    if not isinstance(label, str) or not label:
        raise SensitivityProbeReportError(
            "sensitivity_probe_experiment_label_invalid"
        )
    if not isinstance(source_queue_sha256, str) or not source_queue_sha256:
        raise SensitivityProbeReportError(
            "sensitivity_probe_source_queue_hash_missing"
        )
    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise SensitivityProbeReportError(
            "sensitivity_probe_report_items_missing"
        )
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        parsed = _validated_item(item)
        review_item_id = parsed["review_item_id"]
        if review_item_id in by_id:
            raise SensitivityProbeReportError(
                "sensitivity_probe_review_item_ids_not_unique"
            )
        by_id[review_item_id] = parsed

    expected_evaluations = len(by_id) * len(CANDIDATE_STRATEGIES)
    plan = report.get("experiment_plan")
    if not isinstance(plan, dict) or (
        plan.get("task_count") != len(by_id)
        or plan.get("candidate_count_per_task")
        != len(CANDIDATE_STRATEGIES)
        or plan.get("observed_paid_evaluations") != expected_evaluations
        or plan.get("observed_create_run_calls")
        != len(CANDIDATE_STRATEGIES)
        or plan.get("create_run_retries") != 0
    ):
        raise SensitivityProbeReportError(
            "sensitivity_probe_experiment_plan_mismatch"
        )
    http_calls = report.get("http_calls")
    create_run = (
        http_calls.get("create_run")
        if isinstance(http_calls, dict)
        else None
    )
    if not isinstance(create_run, dict) or (
        create_run.get("attempt_count") != len(CANDIDATE_STRATEGIES)
        or create_run.get("success_count") != len(CANDIDATE_STRATEGIES)
        or create_run.get("error_count") != 0
        or create_run.get("retry_count") != 0
        or create_run.get("automatic_retry_enabled") is not False
    ):
        raise SensitivityProbeReportError(
            "sensitivity_probe_create_run_audit_invalid"
        )
    server_grading = report.get("server_grading")
    if not isinstance(server_grading, dict) or (
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
        raise SensitivityProbeReportError(
            "sensitivity_probe_server_grading_incomplete"
        )
    return {
        "experiment_label": label,
        "harness_revision": str(report["harness_revision"]),
        "tool_call_alignment": str(report["tool_call_alignment"]),
        "source_queue_sha256": source_queue_sha256,
        "items": by_id,
        "candidate_evaluation_count": expected_evaluations,
        "create_run_attempt_count": len(CANDIDATE_STRATEGIES),
    }


def _validated_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or not item.get("review_item_id"):
        raise SensitivityProbeReportError(
            "sensitivity_probe_item_invalid"
        )
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
        raise SensitivityProbeReportError(
            "sensitivity_probe_item_metadata_missing"
        )
    artifact = item.get("preference_artifact")
    pair = artifact.get("pair") if isinstance(artifact, dict) else None
    if not isinstance(pair, dict):
        raise SensitivityProbeReportError(
            "sensitivity_probe_pair_missing"
        )
    status = pair.get("status")
    if status not in {"blocked", "provisional_preference"}:
        raise SensitivityProbeReportError(
            "sensitivity_probe_pair_status_invalid"
        )
    raw_evaluations = pair.get("releasefoundry_evaluations")
    if not isinstance(raw_evaluations, list) or len(raw_evaluations) != len(
        CANDIDATE_STRATEGIES
    ):
        raise SensitivityProbeReportError(
            "sensitivity_probe_evaluations_invalid"
        )
    evaluations = {}
    for raw in raw_evaluations:
        evaluation = _validated_evaluation(raw)
        candidate_id = evaluation["candidate_id"]
        if candidate_id in evaluations:
            raise SensitivityProbeReportError(
                "sensitivity_probe_candidate_ids_not_unique"
            )
        evaluations[candidate_id] = evaluation
    if set(evaluations) != set(CANDIDATE_STRATEGIES):
        raise SensitivityProbeReportError(
            "sensitivity_probe_receipts_incomplete"
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
        raise SensitivityProbeReportError(
            "sensitivity_probe_evaluation_invalid"
        )
    candidate_id = raw.get("candidate_id")
    if candidate_id not in CANDIDATE_STRATEGIES:
        raise SensitivityProbeReportError(
            "sensitivity_probe_candidate_id_invalid"
        )
    if raw.get("receipt_verified") is not True:
        raise SensitivityProbeReportError(
            "sensitivity_probe_receipt_not_verified"
        )
    action_scores = raw.get("action_scores")
    if not isinstance(action_scores, list) or not action_scores:
        raise SensitivityProbeReportError(
            "sensitivity_probe_action_scores_missing"
        )
    scores = []
    for action in action_scores:
        if not isinstance(action, dict) or not isinstance(
            action.get("score"),
            (int, float),
        ):
            raise SensitivityProbeReportError(
                "sensitivity_probe_action_score_invalid"
            )
        scores.append(float(action["score"]))
    for field in ("overall_reward", "final_answer_score"):
        if not isinstance(raw.get(field), (int, float)):
            raise SensitivityProbeReportError(
                f"sensitivity_probe_{field}_invalid"
            )
    return {
        "candidate_id": str(candidate_id),
        "overall_reward": float(raw["overall_reward"]),
        "final_answer_score": float(raw["final_answer_score"]),
        "mean_action_score": statistics.fmean(scores),
        "action_count": len(scores),
        "failure_type": str(raw.get("failure_type", "unknown")),
        "severity": str(raw.get("severity", "unknown")),
    }


def _probe_item(
    review_item_id: str,
    metadata: dict[str, str],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    order_gaps = {
        strategy: [
            observation["evaluations"]["reference_aligned"][
                "overall_reward"
            ]
            - observation["evaluations"][strategy]["overall_reward"]
            for observation in observations
        ]
        for strategy in ORDER_PROBES
    }
    public_observations = []
    for observation in observations:
        evaluations = observation["evaluations"]
        maximum = max(
            evaluation["overall_reward"]
            for evaluation in evaluations.values()
        )
        public_observations.append(
            {
                **observation,
                "top_candidate_ids": sorted(
                    strategy
                    for strategy, evaluation in evaluations.items()
                    if evaluation["overall_reward"] == maximum
                ),
            }
        )
    return {
        "review_item_id": review_item_id,
        **metadata,
        "observation_count": len(observations),
        "reward_distribution_by_strategy": {
            strategy: _distribution(
                [
                    observation["evaluations"][strategy][
                        "overall_reward"
                    ]
                    for observation in observations
                ]
            )
            for strategy in CANDIDATE_STRATEGIES
        },
        "order_probe_reference_gaps": {
            strategy: {
                **_signed_gap_summary(gaps),
                "absolute_gap_at_most_2_count": sum(
                    abs(gap) <= 2 for gap in gaps
                ),
            }
            for strategy, gaps in order_gaps.items()
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
            "repeat_variability": {
                "task_count": len(task_groups),
                "mean_within_task_population_std": round(
                    statistics.fmean(
                        statistics.pstdev(values)
                        for values in task_groups.values()
                    ),
                    4,
                ),
                "maximum_within_task_population_std": round(
                    max(
                        statistics.pstdev(values)
                        for values in task_groups.values()
                    ),
                    4,
                ),
                "tasks_with_reward_range_at_most_2": sum(
                    max(values) - min(values) <= 2
                    for values in task_groups.values()
                ),
            },
        }
    return summary


def _order_blind_spot_summary(
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {}
    for strategy in ORDER_PROBES:
        gaps = [
            observation["evaluations"]["reference_aligned"][
                "overall_reward"
            ]
            - observation["evaluations"][strategy]["overall_reward"]
            for observation in observations
        ]
        within_two = sum(abs(gap) <= 2 for gap in gaps)
        summary[strategy] = {
            "reference_minus_probe_reward_gap": (
                _signed_gap_summary(gaps)
            ),
            "absolute_gap_at_most_2_count": within_two,
            "absolute_gap_at_most_2_rate": round(
                within_two / len(gaps),
                4,
            ),
            "blind_spot_confirmed": within_two / len(gaps) >= 0.8,
            "confirmation_threshold": (
                "absolute_gap_at_most_2_rate >= 0.8"
            ),
        }
    return summary


def _distillation_pair_summary(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for chosen, rejected in DISTILLATION_PAIRS:
        task_rows = []
        for item in items:
            gaps = [
                observation["evaluations"][chosen]["overall_reward"]
                - observation["evaluations"][rejected]["overall_reward"]
                for observation in item["observations"]
            ]
            task_rows.append(
                {
                    "review_item_id": item["review_item_id"],
                    "all_repeats_prefer_chosen": all(
                        gap > 0 for gap in gaps
                    ),
                    "minimum_reward_gap": round(min(gaps), 4),
                    "mean_reward_gap": round(
                        statistics.fmean(gaps),
                        4,
                    ),
                }
            )
        stable = [
            item
            for item in task_rows
            if item["all_repeats_prefer_chosen"]
        ]
        rows.append(
            {
                "chosen_candidate_id": chosen,
                "rejected_candidate_id": rejected,
                "task_count": len(task_rows),
                "tasks_with_same_direction_in_every_repeat": len(stable),
                "minimum_gap_across_stable_tasks": (
                    round(
                        min(item["minimum_reward_gap"] for item in stable),
                        4,
                    )
                    if stable
                    else None
                ),
                "human_review_required": True,
                "training_eligible": False,
                "tasks": task_rows,
            }
        )
    return rows


def _findings(
    *,
    order_blind_spot: dict[str, Any],
    target_50_count: int,
    target_50_total: int,
) -> list[str]:
    confirmed = sorted(
        strategy
        for strategy, row in order_blind_spot.items()
        if row["blind_spot_confirmed"]
    )
    findings = []
    if confirmed:
        findings.append(
            "The declared tool-order blind-spot threshold was met by: "
            f"{', '.join(confirmed)}."
        )
    else:
        findings.append(
            "The corrected positional repeats did not meet the declared "
            "tool-order blind-spot threshold for either order probe."
        )
    findings.append(
        "The compound tool-and-answer defect populated the 40-60 reward "
        f"window in {target_50_count}/{target_50_total} observations."
    )
    findings.extend(
        [
            "Missing a middle tool, using a wrong tool name, and corrupting two tool arguments produced progressively lower reward regions suitable for controlled preference comparisons.",
            "Order-blind observations should become high-priority human-reviewed casebook regressions rather than positive training labels.",
            "Reward-separated pairs are only provisional distillation candidates until a human gold review confirms the direction and failure evidence.",
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
        raise SensitivityProbeReportError("empty_distribution")
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
            "Aggregate repeated receipt-bound ReleaseFoundry sensitivity probes into "
            "a public blind-spot and distillation-candidate report."
        )
    )
    parser.add_argument(
        "--report",
        action="append",
        help="Completed sensitivity-probe report. Repeat in experiment order.",
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
    probe_report = build_sensitivity_probe_report(
        reports,
        report_refs=report_paths,
    )
    calibration._write_public_summary(output_path, probe_report)
    summary = probe_report["experiment_summary"]
    print(
        "ReleaseFoundry sensitivity probe report written: "
        f"tasks={summary['unique_task_count']} "
        f"observations={summary['task_observation_count']} "
        f"evaluations={summary['candidate_evaluation_count']} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
