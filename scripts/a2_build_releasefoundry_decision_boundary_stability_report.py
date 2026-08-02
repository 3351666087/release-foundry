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
    / f"a2_releasefoundry_decision_boundary_probe_repeat_{repeat}.json"
    for repeat in range(1, 7)
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_decision_boundary_probe_stability.json"
)
SCHEMA_VERSION = "a2.releasefoundry_decision_boundary_stability.v1"
SOURCE_SCHEMA_VERSION = "a2.releasefoundry_preference_calibration.v1"
STRATEGY_PROFILE = "decision_boundary_probe"
HARNESS_REVISION = "a2-releasefoundry-live-v5"
TOOL_CALL_ALIGNMENT = "positional"
EXPECTED_TASK_COUNT = 35
MINIMUM_REPORT_COUNT = 3
CANDIDATE_STRATEGIES = (
    "reference_aligned",
    "redundant_post_success_call",
    "redundant_post_success_calls_2",
    "redundant_post_success_calls_3",
    "premature_stop",
    "premature_stop_two_actions",
    "minor_final_answer_after_tools",
    "contradictory_final_answer_after_tools",
)
MONOTONIC_FAMILIES = {
    "redundant_call_count": {
        "strategies": (
            "reference_aligned",
            "redundant_post_success_call",
            "redundant_post_success_calls_2",
            "redundant_post_success_calls_3",
        ),
        "step_names": (
            "reference_to_one_extra_call",
            "one_to_two_extra_calls",
            "two_to_three_extra_calls",
        ),
    },
    "missing_action_count": {
        "strategies": (
            "reference_aligned",
            "premature_stop",
            "premature_stop_two_actions",
        ),
        "step_names": (
            "reference_to_one_missing_action",
            "one_to_two_missing_actions",
        ),
    },
    "final_answer_defect_severity": {
        "strategies": (
            "reference_aligned",
            "minor_final_answer_after_tools",
            "contradictory_final_answer_after_tools",
        ),
        "step_names": (
            "reference_to_minor_defect",
            "minor_to_major_defect",
        ),
    },
}
IDENTITY_FIELDS = (
    "dataset_identity_hash",
    "final_answer_hash",
    "media_evidence_hashes",
    "model_version",
    "prompt_hash",
    "prompt_version",
    "sample_id",
    "task_id",
    "trace_hash",
)


class DecisionBoundaryStabilityReportError(ValueError):
    pass


def build_stability_report(
    reports: list[dict[str, Any]],
    *,
    report_refs: list[str | Path] | None = None,
    expected_task_count: int = EXPECTED_TASK_COUNT,
) -> dict[str, Any]:
    if len(reports) < MINIMUM_REPORT_COUNT:
        raise DecisionBoundaryStabilityReportError(
            "at_least_three_decision_boundary_reports_required"
        )
    refs = report_refs or [
        f"report-{index + 1}" for index in range(len(reports))
    ]
    if len(refs) != len(reports):
        raise DecisionBoundaryStabilityReportError("report_refs_count_mismatch")

    validated_reports = [
        _validated_report(report, expected_task_count=expected_task_count)
        for report in reports
    ]
    raw_report_hashes = [
        review_queue._sha256_json(report) for report in reports
    ]
    artifact_hash_values = [
        report["artifact_hash"] for report in validated_reports
    ]
    if (
        len(set(raw_report_hashes)) != len(raw_report_hashes)
        or len(set(artifact_hash_values)) != len(artifact_hash_values)
    ):
        raise DecisionBoundaryStabilityReportError(
            "duplicate_decision_boundary_report"
        )
    labels = [report["experiment_label"] for report in validated_reports]
    if len(set(labels)) != len(labels):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_experiment_labels_not_unique"
        )

    canonical_ids = set(validated_reports[0]["items"])
    for report in validated_reports[1:]:
        if set(report["items"]) != canonical_ids:
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_report_task_set_mismatch"
            )

    report_hashes: set[str] = set()
    artifact_hashes: set[str] = set()
    source_reports: list[dict[str, Any]] = []
    observations_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metadata_by_id: dict[str, dict[str, str]] = {}
    identities_by_id: dict[str, dict[str, dict[str, Any]]] = {}

    total_evaluations = 0
    total_create_run_attempts = 0
    total_structure_grades = 0
    total_final_answer_grades = 0
    for ref, raw_report, report in zip(
        refs, reports, validated_reports, strict=True
    ):
        report_hash = review_queue._sha256_json(raw_report)
        artifact_hash = report["artifact_hash"]
        if report_hash in report_hashes or artifact_hash in artifact_hashes:
            raise DecisionBoundaryStabilityReportError(
                "duplicate_decision_boundary_report"
            )
        report_hashes.add(report_hash)
        artifact_hashes.add(artifact_hash)
        source_reports.append(
            {
                "ref": calibration._display_path(ref),
                "sha256": report_hash,
                "artifact_hash": artifact_hash,
                "experiment_label": report["experiment_label"],
                "task_count": len(report["items"]),
                "candidate_evaluation_count": report[
                    "candidate_evaluation_count"
                ],
                "create_run_attempt_count": report[
                    "create_run_attempt_count"
                ],
                "create_run_retry_count": 0,
                "receipt_verified_evaluation_count": report[
                    "receipt_verified_evaluation_count"
                ],
            }
        )
        total_evaluations += report["candidate_evaluation_count"]
        total_create_run_attempts += report["create_run_attempt_count"]
        total_structure_grades += report["structure_grade_count"]
        total_final_answer_grades += report["final_answer_grade_count"]

        for review_item_id, item in report["items"].items():
            observed_metadata = metadata_by_id.setdefault(
                review_item_id, item["metadata"]
            )
            if observed_metadata != item["metadata"]:
                raise DecisionBoundaryStabilityReportError(
                    "decision_boundary_task_metadata_mismatch"
                )
            observed_identities = identities_by_id.setdefault(
                review_item_id, item["candidate_identities"]
            )
            if observed_identities != item["candidate_identities"]:
                raise DecisionBoundaryStabilityReportError(
                    "decision_boundary_candidate_identity_mismatch"
                )
            observations_by_id[review_item_id].append(
                {
                    "experiment_label": report["experiment_label"],
                    "source_report_sha256": report_hash,
                    "pair_status": item["pair_status"],
                    "chosen_candidate_id": item["chosen"],
                    "rejected_candidate_id": item["rejected"],
                    "rewards": item["rewards"],
                    "ranks": item["ranks"],
                    "ranking_tiers": item["ranking_tiers"],
                }
            )

    items = [
        _stability_item(
            review_item_id,
            metadata_by_id[review_item_id],
            identities_by_id[review_item_id],
            observations_by_id[review_item_id],
        )
        for review_item_id in sorted(canonical_ids)
    ]
    all_rewards = {
        strategy: [
            observation["rewards"][strategy]
            for item in items
            for observation in item["observations"]
        ]
        for strategy in CANDIDATE_STRATEGIES
    }
    reference_gaps = {
        strategy: [
            observation["rewards"]["reference_aligned"]
            - observation["rewards"][strategy]
            for item in items
            for observation in item["observations"]
        ]
        for strategy in CANDIDATE_STRATEGIES
        if strategy != "reference_aligned"
    }
    all_pair_statuses = Counter(
        observation["pair_status"]
        for item in items
        for observation in item["observations"]
    )
    all_pair_choices = Counter(
        observation["chosen_candidate_id"]
        for item in items
        for observation in item["observations"]
        if observation["chosen_candidate_id"] is not None
    )
    repeat_strategy_means = {
        report["experiment_label"]: {
            strategy: statistics.fmean(
                item["rewards"][strategy]
                for item in report["items"].values()
            )
            for strategy in CANDIDATE_STRATEGIES
        }
        for report in validated_reports
    }
    strategy_summary = {
        strategy: {
            "reward": _distribution(all_rewards[strategy]),
            "repeat_mean_reward": _distribution(
                [
                    repeat_strategy_means[label][strategy]
                    for label in labels
                ]
            ),
            "mean_rank": round(
                statistics.fmean(
                    observation["ranks"][strategy]
                    for item in items
                    for observation in item["observations"]
                ),
                4,
            ),
            **(
                {}
                if strategy == "reference_aligned"
                else {
                    "reference_reward_gap": _distribution(
                        reference_gaps[strategy]
                    )
                }
            ),
        }
        for strategy in CANDIDATE_STRATEGIES
    }
    overall_ranking = sorted(
        CANDIDATE_STRATEGIES,
        key=lambda strategy: (
            -float(strategy_summary[strategy]["reward"]["mean"]),
            strategy,
        ),
    )
    exact_ranking_stable_count = sum(
        item["exact_ranking_stable"] for item in items
    )
    stable_pair_status_count = sum(
        item["pair_stability"]["status_stable"] for item in items
    )
    pair_choice_stable_count = sum(
        item["pair_stability"]["choice_stable"] for item in items
    )
    monotonicity_summary = _monotonicity_summary(items)

    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "strategy_profile": STRATEGY_PROFILE,
        "harness_revision": HARNESS_REVISION,
        "tool_call_alignment": TOOL_CALL_ALIGNMENT,
        "candidate_strategies": list(CANDIDATE_STRATEGIES),
        "source_reports": source_reports,
        "experiment_summary": {
            "report_count": len(reports),
            "unique_task_count": len(items),
            "task_observation_count": len(items) * len(reports),
            "candidate_evaluation_count": total_evaluations,
            "create_run_attempt_count": total_create_run_attempts,
            "create_run_success_count": total_create_run_attempts,
            "create_run_error_count": 0,
            "create_run_retry_count": 0,
            "receipt_verified_evaluation_count": total_evaluations,
            "structure_grade_count": total_structure_grades,
            "final_answer_grade_count": total_final_answer_grades,
            "per_test_receipts_verified": True,
            "exact_test_set_verified_for_every_strategy": True,
            "aggregate_marker_used_as_authority": False,
        },
        "strategy_stability_summary": {
            "overall_mean_reward_ranking": overall_ranking,
            "by_strategy": strategy_summary,
            "step_penalty_summary": {
                family: summary["step_penalty_distribution"]
                for family, summary in monotonicity_summary[
                    "by_family"
                ].items()
            },
        },
        "monotonicity_summary": monotonicity_summary,
        "ranking_stability_summary": {
            "exact_ranking_stable_task_count": exact_ranking_stable_count,
            "exact_ranking_unstable_task_count": (
                len(items) - exact_ranking_stable_count
            ),
            "exact_ranking_stability_rate": round(
                exact_ranking_stable_count / len(items), 4
            ),
        },
        "pair_stability_summary": {
            "pair_status_counts": {
                status: all_pair_statuses.get(status, 0)
                for status in ("blocked", "provisional_preference")
            },
            "chosen_by_strategy": {
                strategy: all_pair_choices.get(strategy, 0)
                for strategy in CANDIDATE_STRATEGIES
            },
            "status_stable_task_count": stable_pair_status_count,
            "status_unstable_task_count": len(items)
            - stable_pair_status_count,
            "choice_stable_task_count": pair_choice_stable_count,
            "choice_unstable_task_count": len(items)
            - pair_choice_stable_count,
            "authorized_preference_pair_count": 0,
            "training_eligible_pair_count": 0,
        },
        "active_learning_priorities": _active_learning_priorities(items),
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
            f"This report aggregates {len(reports)} independent, receipt-bound ReleaseFoundry decision-boundary probes.",
            "All create_run calls were single-attempt operations; only read-only recovery is retryable.",
            "The probe measures reward gradients for one through three redundant calls, one through two missing actions, and minor through major final-answer defects.",
            "Monotonicity is measured per task and repeat; a violation is retained for active learning rather than silently repaired.",
            "Stable ReleaseFoundry rewards are teacher observations, not human gold or training authorization.",
            "All source cases remain text projections and do not establish native multimodal coverage.",
        ],
    }
    calibration._assert_public_summary_safe(core)
    return {**core, "artifact_hash": review_queue._sha256_json(core)}


def _validated_report(
    report: dict[str, Any],
    *,
    expected_task_count: int,
) -> dict[str, Any]:
    if report.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_report_schema_mismatch"
        )
    if report.get("experiment_status") != "completed":
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_report_not_completed"
        )
    if report.get("strategy_profile") != STRATEGY_PROFILE:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_strategy_profile_mismatch"
        )
    if report.get("harness_revision") != HARNESS_REVISION:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_harness_revision_mismatch"
        )
    if report.get("tool_call_alignment") != TOOL_CALL_ALIGNMENT:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_tool_call_alignment_mismatch"
        )
    if (
        report.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_report_not_exploratory"
        )
    if report.get("candidate_strategies") != list(CANDIDATE_STRATEGIES):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_candidate_strategies_mismatch"
        )
    _validate_boundary_fields(report)
    _validate_public_safety(report)
    _validate_artifact_hash(report)

    label = report.get("experiment_label")
    if not isinstance(label, str) or not label:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_experiment_label_invalid"
        )
    items = report.get("items")
    if not isinstance(items, list) or len(items) != expected_task_count:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_task_count_mismatch"
        )
    by_id: dict[str, dict[str, Any]] = {}
    for raw_item in items:
        item = _validated_item(raw_item)
        if item["review_item_id"] in by_id:
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_review_item_ids_not_unique"
            )
        by_id[item["review_item_id"]] = item

    expected_evaluations = len(by_id) * len(CANDIDATE_STRATEGIES)
    plan = report.get("experiment_plan")
    if not isinstance(plan, dict):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_experiment_plan_missing"
        )
    expected_plan = {
        "task_count": len(by_id),
        "candidate_count_per_task": len(CANDIDATE_STRATEGIES),
        "planned_paid_evaluations": expected_evaluations,
        "observed_paid_evaluations": expected_evaluations,
        "planned_create_run_calls": len(CANDIDATE_STRATEGIES),
        "observed_create_run_calls": len(CANDIDATE_STRATEGIES),
        "create_run_retries": 0,
    }
    if any(plan.get(key) != value for key, value in expected_plan.items()):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_experiment_plan_mismatch"
        )

    http_calls = report.get("http_calls")
    create_run = (
        http_calls.get("create_run")
        if isinstance(http_calls, dict)
        else None
    )
    if not isinstance(create_run, dict):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_create_run_audit_missing"
        )
    expected_create_calls = len(CANDIDATE_STRATEGIES)
    if (
        create_run.get("automatic_retry_enabled") is not False
        or create_run.get("retry_count") != 0
        or create_run.get("error_count") != 0
        or create_run.get("attempt_count") != expected_create_calls
        or create_run.get("success_count") != expected_create_calls
    ):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_create_run_audit_invalid"
        )

    server_grading = report.get("server_grading")
    if not isinstance(server_grading, dict):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_server_grading_missing"
        )
    if (
        server_grading.get("per_test_receipts_verified") is not True
        or server_grading.get(
            "exact_test_set_verified_for_every_strategy"
        )
        is not True
        or server_grading.get("aggregate_marker_used_as_authority")
        is not False
        or server_grading.get("tests_with_structure_grading")
        != expected_evaluations
        or server_grading.get("tests_with_final_answer_grading")
        != expected_evaluations
    ):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_server_grading_incomplete"
        )
    return {
        "artifact_hash": report["artifact_hash"],
        "experiment_label": label,
        "items": by_id,
        "candidate_evaluation_count": expected_evaluations,
        "create_run_attempt_count": expected_create_calls,
        "receipt_verified_evaluation_count": expected_evaluations,
        "structure_grade_count": expected_evaluations,
        "final_answer_grade_count": expected_evaluations,
    }


def _validate_boundary_fields(report: dict[str, Any]) -> None:
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
            raise DecisionBoundaryStabilityReportError(
                f"decision_boundary_{field}_must_be_false"
            )
    if report.get("human_review_required") is not True:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_human_review_required"
        )
    if report.get("text_projection_only") is not True:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_text_projection_boundary_missing"
        )


def _validate_public_safety(report: dict[str, Any]) -> None:
    public_safety = report.get("public_safety")
    if not isinstance(public_safety, dict) or any(
        public_safety.get(field) is not False
        for field in (
            "contains_api_key",
            "contains_api_key_hash",
            "contains_raw_prompt",
            "contains_raw_candidate_response",
            "contains_raw_tool_arguments",
            "contains_private_service_ids",
            "contains_local_absolute_paths",
        )
    ):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_public_safety_boundary_invalid"
        )


def _validate_artifact_hash(report: dict[str, Any]) -> None:
    artifact_hash = report.get("artifact_hash")
    if not isinstance(artifact_hash, str):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_artifact_hash_missing"
        )
    core = {key: value for key, value in report.items() if key != "artifact_hash"}
    if preference.stable_hash(core) != artifact_hash:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_artifact_hash_mismatch"
        )


def _validated_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or not item.get("review_item_id"):
        raise DecisionBoundaryStabilityReportError("decision_boundary_item_invalid")
    metadata = {
        key: str(item[key])
        for key in ("case_id", "channel", "prompt_variant", "expected_variant")
        if item.get(key) is not None
    }
    if len(metadata) != 4:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_item_metadata_missing"
        )
    preference_artifact = item.get("preference_artifact")
    pair = (
        preference_artifact.get("pair")
        if isinstance(preference_artifact, dict)
        else None
    )
    if not isinstance(pair, dict):
        raise DecisionBoundaryStabilityReportError("decision_boundary_pair_missing")
    if (
        preference_artifact.get("training_eligible") is not False
        or preference_artifact.get("c3_transition_allowed") is not False
        or preference_artifact.get("release_authority") is not False
        or preference_artifact.get("human_gold") is not False
        or preference_artifact.get("human_review_required") is not True
    ):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_preference_artifact_boundary_invalid"
        )
    if (
        pair.get("training_eligible") is not False
        or pair.get("review_required") is not True
        or pair.get("human_adjudication") is not None
    ):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_pair_boundary_invalid"
        )

    candidates = pair.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != len(
        CANDIDATE_STRATEGIES
    ):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_candidates_invalid"
        )
    identities: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_candidate_invalid"
            )
        candidate_id = candidate.get("candidate_id")
        if candidate_id not in CANDIDATE_STRATEGIES:
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_candidate_id_invalid"
            )
        if candidate_id in identities:
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_candidate_ids_not_unique"
            )
        if any(field not in candidate for field in IDENTITY_FIELDS):
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_candidate_identity_incomplete"
            )
        identities[str(candidate_id)] = {
            field: candidate[field] for field in IDENTITY_FIELDS
        }
    if set(identities) != set(CANDIDATE_STRATEGIES):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_candidate_set_mismatch"
        )

    evaluations = pair.get("releasefoundry_evaluations")
    if not isinstance(evaluations, list) or len(evaluations) != len(
        CANDIDATE_STRATEGIES
    ):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_evaluations_invalid"
        )
    rewards: dict[str, float] = {}
    ranks: dict[str, int] = {}
    for evaluation in evaluations:
        if (
            not isinstance(evaluation, dict)
            or evaluation.get("candidate_id") not in CANDIDATE_STRATEGIES
            or evaluation.get("receipt_verified") is not True
        ):
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_receipt_incomplete"
            )
        candidate_id = str(evaluation["candidate_id"])
        if candidate_id in rewards:
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_evaluation_ids_not_unique"
            )
        reward = evaluation.get("overall_reward")
        rank = evaluation.get("rank")
        if not isinstance(reward, (int, float)) or not isinstance(rank, int):
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_reward_or_rank_invalid"
            )
        rewards[candidate_id] = float(reward)
        ranks[candidate_id] = rank
    if set(rewards) != set(CANDIDATE_STRATEGIES):
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_receipts_incomplete"
        )

    status = pair.get("status")
    chosen = _candidate_id(pair.get("chosen"))
    rejected = _candidate_id(pair.get("rejected"))
    if status == "blocked":
        if chosen is not None or rejected is not None:
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_blocked_pair_has_choice"
            )
        if (
            pair.get("preference_authority") != "none"
            or pair.get("external_teacher_count") != 0
        ):
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_blocked_pair_authority_invalid"
            )
    elif status == "provisional_preference":
        if (
            chosen not in CANDIDATE_STRATEGIES
            or rejected not in CANDIDATE_STRATEGIES
            or chosen == rejected
        ):
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_provisional_pair_invalid"
            )
        if (
            pair.get("preference_authority") != "releasefoundry_provisional"
            or pair.get("external_teacher_count") != 1
        ):
            raise DecisionBoundaryStabilityReportError(
                "decision_boundary_provisional_pair_authority_invalid"
            )
    else:
        raise DecisionBoundaryStabilityReportError(
            "decision_boundary_pair_status_invalid"
        )
    return {
        "review_item_id": str(item["review_item_id"]),
        "metadata": metadata,
        "candidate_identities": {
            strategy: identities[strategy]
            for strategy in CANDIDATE_STRATEGIES
        },
        "pair_status": status,
        "chosen": chosen,
        "rejected": rejected,
        "rewards": {
            strategy: rewards[strategy] for strategy in CANDIDATE_STRATEGIES
        },
        "ranks": {
            strategy: ranks[strategy] for strategy in CANDIDATE_STRATEGIES
        },
        "ranking_tiers": _ranking_tiers(rewards),
    }


def _candidate_id(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("candidate_id"):
        return str(value["candidate_id"])
    return None


def _ranking_tiers(rewards: dict[str, float]) -> list[list[str]]:
    tiers: dict[float, list[str]] = defaultdict(list)
    for strategy, reward in rewards.items():
        tiers[reward].append(strategy)
    return [
        sorted(tiers[reward])
        for reward in sorted(tiers, reverse=True)
    ]


def _stability_item(
    review_item_id: str,
    metadata: dict[str, str],
    candidate_identities: dict[str, dict[str, Any]],
    observations: list[dict[str, Any]],
) -> dict[str, Any]:
    rewards_by_strategy = {
        strategy: [
            observation["rewards"][strategy]
            for observation in observations
        ]
        for strategy in CANDIDATE_STRATEGIES
    }
    mean_rewards = {
        strategy: statistics.fmean(rewards_by_strategy[strategy])
        for strategy in CANDIDATE_STRATEGIES
    }
    status_sequence = [
        observation["pair_status"] for observation in observations
    ]
    choice_sequence = [
        {
            "chosen": observation["chosen_candidate_id"],
            "rejected": observation["rejected_candidate_id"],
        }
        for observation in observations
    ]
    ranking_sequences = [
        observation["ranking_tiers"] for observation in observations
    ]
    max_strategy_std = max(
        statistics.pstdev(values) for values in rewards_by_strategy.values()
    )
    reference_gap = {
        strategy: _distribution(
            [
                observation["rewards"]["reference_aligned"]
                - observation["rewards"][strategy]
                for observation in observations
            ]
        )
        for strategy in CANDIDATE_STRATEGIES
        if strategy != "reference_aligned"
    }
    boundary_monotonicity = {
        family: _family_monotonicity(observations, family)
        for family in MONOTONIC_FAMILIES
    }
    return {
        "review_item_id": review_item_id,
        **metadata,
        "observation_count": len(observations),
        "candidate_identities": candidate_identities,
        "reward_distribution_by_strategy": {
            strategy: _distribution(rewards_by_strategy[strategy])
            for strategy in CANDIDATE_STRATEGIES
        },
        "reference_reward_gap_by_strategy": reference_gap,
        "mean_reward_ranking": sorted(
            CANDIDATE_STRATEGIES,
            key=lambda strategy: (-mean_rewards[strategy], strategy),
        ),
        "exact_ranking_stable": all(
            ranking == ranking_sequences[0]
            for ranking in ranking_sequences[1:]
        ),
        "maximum_strategy_population_std": round(max_strategy_std, 4),
        "decision_boundary_monotonicity": {
            "by_family": boundary_monotonicity,
            "all_families_nonincreasing_in_every_repeat": all(
                summary["all_observations_nonincreasing"]
                for summary in boundary_monotonicity.values()
            ),
        },
        "pair_stability": {
            "status_sequence": status_sequence,
            "status_stable": len(set(status_sequence)) == 1,
            "choice_sequence": choice_sequence,
            "choice_stable": all(
                choice == choice_sequence[0]
                for choice in choice_sequence[1:]
            ),
            "human_review_required": True,
            "training_eligible": False,
        },
        "observations": observations,
        "human_review_required": True,
        "training_eligible": False,
    }


def _monotonicity_summary(
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    observations = [
        observation
        for item in items
        for observation in item["observations"]
    ]
    by_family: dict[str, dict[str, Any]] = {}
    for family in MONOTONIC_FAMILIES:
        summary = _family_monotonicity(observations, family)
        task_count = sum(
            item["decision_boundary_monotonicity"]["by_family"][family][
                "all_observations_nonincreasing"
            ]
            for item in items
        )
        by_family[family] = {
            **summary,
            "all_repeats_monotonic_task_count": task_count,
            "any_repeat_violation_task_count": len(items) - task_count,
            "all_repeats_monotonic_task_rate": round(
                task_count / len(items), 4
            ),
        }

    all_family_monotonic_observation_count = sum(
        all(
            all(margin >= 0 for margin in _step_margins(observation, family))
            for family in MONOTONIC_FAMILIES
        )
        for observation in observations
    )
    all_family_monotonic_task_count = sum(
        item["decision_boundary_monotonicity"][
            "all_families_nonincreasing_in_every_repeat"
        ]
        for item in items
    )
    return {
        "observation_count": len(observations),
        "all_family_monotonic_observation_count": (
            all_family_monotonic_observation_count
        ),
        "all_family_monotonic_observation_rate": round(
            all_family_monotonic_observation_count / len(observations), 4
        ),
        "all_family_monotonic_task_count": (
            all_family_monotonic_task_count
        ),
        "all_family_monotonic_task_rate": round(
            all_family_monotonic_task_count / len(items), 4
        ),
        "by_family": by_family,
    }


def _family_monotonicity(
    observations: list[dict[str, Any]],
    family: str,
) -> dict[str, Any]:
    config = MONOTONIC_FAMILIES[family]
    step_names = config["step_names"]
    step_values = {name: [] for name in step_names}
    nonincreasing_count = 0
    strict_decrease_count = 0
    violation_labels: list[str] = []
    minimum_margin: float | None = None
    for observation in observations:
        margins = _step_margins(observation, family)
        for name, margin in zip(step_names, margins, strict=True):
            step_values[name].append(margin)
        if all(margin >= 0 for margin in margins):
            nonincreasing_count += 1
        else:
            violation_labels.append(observation["experiment_label"])
        if all(margin > 0 for margin in margins):
            strict_decrease_count += 1
        observed_minimum = min(margins)
        minimum_margin = (
            observed_minimum
            if minimum_margin is None
            else min(minimum_margin, observed_minimum)
        )
    return {
        "strategy_sequence": list(config["strategies"]),
        "observation_count": len(observations),
        "nonincreasing_observation_count": nonincreasing_count,
        "violation_observation_count": len(observations)
        - nonincreasing_count,
        "strict_decrease_observation_count": strict_decrease_count,
        "nonincreasing_observation_rate": round(
            nonincreasing_count / len(observations), 4
        ),
        "strict_decrease_observation_rate": round(
            strict_decrease_count / len(observations), 4
        ),
        "minimum_step_margin": round(float(minimum_margin), 4),
        "all_observations_nonincreasing": (
            nonincreasing_count == len(observations)
        ),
        "violation_experiment_labels": sorted(set(violation_labels)),
        "step_penalty_distribution": {
            name: _distribution(step_values[name])
            for name in step_names
        },
    }


def _step_margins(
    observation: dict[str, Any],
    family: str,
) -> list[float]:
    strategies = MONOTONIC_FAMILIES[family]["strategies"]
    rewards = observation["rewards"]
    values = [float(rewards[strategy]) for strategy in strategies]
    return [
        left - right
        for left, right in zip(values, values[1:])
    ]


def _active_learning_priorities(
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    status_flips = [
        item["review_item_id"]
        for item in items
        if not item["pair_stability"]["status_stable"]
    ]
    ranking_flips = [
        item["review_item_id"]
        for item in items
        if not item["exact_ranking_stable"]
    ]

    def closest_step_margin(family: str) -> list[dict[str, Any]]:
        rows = [
            {
                "review_item_id": item["review_item_id"],
                "case_id": item["case_id"],
                "minimum_step_margin": item[
                    "decision_boundary_monotonicity"
                ]["by_family"][family]["minimum_step_margin"],
                "all_observations_nonincreasing": item[
                    "decision_boundary_monotonicity"
                ]["by_family"][family]["all_observations_nonincreasing"],
            }
            for item in items
        ]
        return sorted(
            rows,
            key=lambda row: (
                row["minimum_step_margin"],
                row["review_item_id"],
            ),
        )[:10]

    highest_variance = sorted(
        (
            {
                "review_item_id": item["review_item_id"],
                "case_id": item["case_id"],
                "maximum_strategy_population_std": item[
                    "maximum_strategy_population_std"
                ],
            }
            for item in items
        ),
        key=lambda row: (
            -row["maximum_strategy_population_std"],
            row["review_item_id"],
        ),
    )[:10]
    return {
        "pair_status_flip_review_item_ids": status_flips,
        "ranking_flip_review_item_ids": ranking_flips,
        "monotonic_violation_review_item_ids_by_family": {
            family: [
                item["review_item_id"]
                for item in items
                if not item["decision_boundary_monotonicity"][
                    "by_family"
                ][family]["all_observations_nonincreasing"]
            ]
            for family in MONOTONIC_FAMILIES
        },
        "highest_reward_variance": highest_variance,
        "closest_or_violated_step_margin_by_family": {
            family: closest_step_margin(family)
            for family in MONOTONIC_FAMILIES
        },
        "recommended_next_experiments": [
            "Send every non-monotonic or threshold-adjacent task to independent teacher and human adjudication.",
            "Repeat the same defect-count gradients with native image, audio, video, and document uploads rather than text projections.",
            "Add latency and monetary-cost features before using redundant-call penalties to train an action-value model.",
            "Re-test pair-status and rank-unstable tasks before any preference-pair promotion or training use.",
        ],
    }


def _distribution(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise DecisionBoundaryStabilityReportError("empty_distribution")
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 4),
        "population_std": round(statistics.pstdev(values), 4),
        "minimum": round(min(values), 4),
        "maximum": round(max(values), 4),
        "range": round(max(values) - min(values), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate repeated receipt-bound ReleaseFoundry decision-boundary probes "
            "into a public stability report."
        )
    )
    parser.add_argument(
        "--report",
        action="append",
        help="Completed public decision-boundary report. Repeat in experiment order.",
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
        "ReleaseFoundry decision-boundary stability report written: "
        f"reports={summary['report_count']} "
        f"tasks={summary['unique_task_count']} "
        f"evaluations={summary['candidate_evaluation_count']} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
