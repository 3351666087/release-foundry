from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import a2_releasefoundry_live_calibration as calibration  # noqa: E402
from scripts import (  # noqa: E402
    a2_build_releasefoundry_disagreement_review_queue as review_queue,
)
from scripts import (  # noqa: E402
    a2_build_releasefoundry_order_probe_methodology_correction as correction,
)
from scripts import (  # noqa: E402
    a2_build_releasefoundry_sensitivity_probe_report as stability,
)


DEFAULT_STABILITY_REPORT = stability.DEFAULT_OUTPUT
DEFAULT_METHODOLOGY_CORRECTION = correction.DEFAULT_OUTPUT
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_corrected_order_preference_review_package.json"
)
SCHEMA_VERSION = (
    "a2.releasefoundry_corrected_order_preference_review_package.v1"
)
SOURCE_SCHEMA_VERSION = stability.SCHEMA_VERSION
PAIR_HYPOTHESES = stability.DISTILLATION_PAIRS
ORDER_PROBES = stability.ORDER_PROBES
CANDIDATE_STRATEGIES = stability.CANDIDATE_STRATEGIES


class CorrectedOrderPreferenceReviewPackageError(ValueError):
    pass


def build_review_package(
    report: dict[str, Any],
    *,
    source_report_ref: str | Path = DEFAULT_STABILITY_REPORT,
    methodology_correction: dict[str, Any],
    methodology_correction_ref: str | Path = (
        DEFAULT_METHODOLOGY_CORRECTION
    ),
) -> dict[str, Any]:
    _validate_report(report)
    _validate_methodology_correction(methodology_correction)

    pair_reviews = [
        review
        for item in report["items"]
        for review in _pair_reviews(item)
    ]
    order_reviews = [
        review
        for item in report["items"]
        for review in _order_reviews(item)
    ]
    expected_pair_count = len(report["items"]) * len(PAIR_HYPOTHESES)
    expected_order_count = len(report["items"]) * len(ORDER_PROBES)
    if len(pair_reviews) != expected_pair_count:
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_pair_reviews_incomplete"
        )
    if len(order_reviews) != expected_order_count:
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_order_reviews_incomplete"
        )

    direction_counts = _count_values(pair_reviews, "direction_status")
    order_status_counts = _count_values(
        order_reviews,
        "corrected_order_observation_status",
    )
    source_hash = review_queue._sha256_json(report)
    correction_hash = review_queue._sha256_json(methodology_correction)
    source_summary = report["sensitivity_probe_summary"]
    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "review_status": "pending_human_review",
        "harness_revision": stability.REQUIRED_HARNESS_REVISION,
        "tool_call_alignment": stability.REQUIRED_TOOL_CALL_ALIGNMENT,
        "source_stability_report": {
            "ref": calibration._display_path(source_report_ref),
            "sha256": source_hash,
            "artifact_hash": report["artifact_hash"],
            "source_queue_sha256": report["source_queue_sha256"],
        },
        "historical_methodology_correction": {
            "ref": calibration._display_path(
                methodology_correction_ref
            ),
            "sha256": correction_hash,
            "artifact_hash": methodology_correction["artifact_hash"],
            "historical_order_probe_validity": False,
            "invalidated_for_releasefoundry_order_sensitivity": True,
            "root_cause": "local_payload_order_normalization",
            "corrected_positional_rerun_completed": True,
        },
        "source_experiment_summary": report["experiment_summary"],
        "source_corrected_order_summary": {
            "pair_status_counts": source_summary["pair_status_counts"],
            "order_blind_spot": source_summary["order_blind_spot"],
            "target_50_window": source_summary["target_50_window"],
        },
        "review_summary": {
            "source_task_count": len(report["items"]),
            "source_repeat_count": report["experiment_summary"][
                "report_count"
            ],
            "pair_review_item_count": len(pair_reviews),
            "pair_direction_status_counts": direction_counts,
            "corrected_order_review_item_count": len(order_reviews),
            "corrected_order_observation_status_counts": (
                order_status_counts
            ),
            "authorized_preference_pair_count": 0,
            "training_eligible_pair_count": 0,
        },
        "pair_hypotheses": [
            {
                "proposed_preferred_candidate_id": preferred,
                "proposed_disfavored_candidate_id": disfavored,
                "authorization_state": "machine_hypothesis_only",
                "corrected_payload_semantics_valid": True,
            }
            for preferred, disfavored in PAIR_HYPOTHESES
        ],
        "order_probe_candidates": list(ORDER_PROBES),
        "provisional_pair_reviews": pair_reviews,
        "corrected_order_reviews": order_reviews,
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
            "All source observations come from three receipt-bound positional a2-releasefoundry-live-v5 repeats.",
            "The corrected traces preserve reordering, omission shifts, unexpected calls, and actual call order instead of normalizing by expected tool name.",
            "Pairwise reward directions and corrected order observations are machine review hypotheses, not authorized chosen/rejected labels.",
            "Authorized chosen/rejected fields remain null until a recorded human review inspects the underlying private traces and evidence.",
            "Historical pre-v5 order conclusions remain governed by the methodology-correction artifact and are not silently rewritten.",
            "All source cases remain text projections and do not establish native multimodal capability.",
        ],
    }
    calibration._assert_public_summary_safe(core)
    return {
        **core,
        "artifact_hash": review_queue._sha256_json(core),
    }


def _validate_report(report: dict[str, Any]) -> None:
    if report.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_report_schema_mismatch"
        )
    if (
        report.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_report_not_exploratory"
        )
    if (
        report.get("harness_revision")
        != stability.REQUIRED_HARNESS_REVISION
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_harness_revision_mismatch"
        )
    if (
        report.get("tool_call_alignment")
        != stability.REQUIRED_TOOL_CALL_ALIGNMENT
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_tool_call_alignment_mismatch"
        )
    if tuple(report.get("candidate_strategies", [])) != (
        CANDIDATE_STRATEGIES
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_candidate_strategies_mismatch"
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
            raise CorrectedOrderPreferenceReviewPackageError(
                f"corrected_stability_{field}_must_be_false"
            )
    if (
        report.get("human_review_required") is not True
        or report.get("text_projection_only") is not True
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_evidence_boundary_invalid"
        )
    _validate_self_hash(
        report,
        error="corrected_stability_artifact_hash_mismatch",
    )

    source_queue_sha256 = report.get("source_queue_sha256")
    if (
        not isinstance(source_queue_sha256, str)
        or not source_queue_sha256.startswith("sha256:")
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_source_queue_hash_invalid"
        )
    summary = report.get("experiment_summary")
    if not isinstance(summary, dict):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_experiment_summary_missing"
        )
    report_count = summary.get("report_count")
    task_count = summary.get("unique_task_count")
    observation_count = summary.get("task_observation_count")
    evaluation_count = summary.get("candidate_evaluation_count")
    if (
        not isinstance(report_count, int)
        or report_count < 3
        or not isinstance(task_count, int)
        or task_count <= 0
        or observation_count != task_count * report_count
        or evaluation_count
        != observation_count * len(CANDIDATE_STRATEGIES)
        or summary.get("create_run_attempt_count")
        != report_count * len(CANDIDATE_STRATEGIES)
        or summary.get("create_run_retry_count") != 0
        or summary.get("structure_grade_count") != evaluation_count
        or summary.get("final_answer_grade_count") != evaluation_count
        or summary.get("per_test_receipts_verified") is not True
        or summary.get("exact_test_set_verified_for_every_strategy")
        is not True
        or summary.get("aggregate_marker_used_as_authority") is not False
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_experiment_summary_invalid"
        )
    items = report.get("items")
    if not isinstance(items, list) or len(items) != task_count:
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_items_invalid"
        )
    review_item_ids = [item.get("review_item_id") for item in items]
    if (
        any(
            not isinstance(item_id, str) or not item_id
            for item_id in review_item_ids
        )
        or len(set(review_item_ids)) != len(review_item_ids)
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_review_item_ids_invalid"
        )
    for item in items:
        _validated_observations(item, expected_count=report_count)

    probe_summary = report.get("sensitivity_probe_summary")
    if not isinstance(probe_summary, dict) or not all(
        key in probe_summary
        for key in (
            "pair_status_counts",
            "order_blind_spot",
            "target_50_window",
        )
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_probe_summary_invalid"
        )


def _validate_methodology_correction(
    methodology_correction: dict[str, Any],
) -> None:
    if methodology_correction.get("schema_version") != (
        correction.SCHEMA_VERSION
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "methodology_correction_schema_mismatch"
        )
    _validate_self_hash(
        methodology_correction,
        error="methodology_correction_artifact_hash_mismatch",
    )
    finding = methodology_correction.get("finding")
    if not isinstance(finding, dict) or (
        finding.get("historical_order_probe_validity") is not False
        or finding.get("invalidated_for_releasefoundry_order_sensitivity")
        is not True
        or finding.get("root_cause")
        != "local_payload_order_normalization"
        or finding.get("corrected_harness_revision")
        != stability.REQUIRED_HARNESS_REVISION
        or finding.get("corrected_tool_call_alignment")
        != stability.REQUIRED_TOOL_CALL_ALIGNMENT
        or finding.get("rerun_required") is not True
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "methodology_correction_finding_invalid"
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
        if methodology_correction.get(field) is not False:
            raise CorrectedOrderPreferenceReviewPackageError(
                f"methodology_correction_{field}_must_be_false"
            )


def _pair_reviews(item: dict[str, Any]) -> list[dict[str, Any]]:
    observations = _validated_observations(item)
    source_review_item_id = str(item["review_item_id"])
    reviews = []
    for preferred, disfavored in PAIR_HYPOTHESES:
        repeat_evidence = []
        for observation in observations:
            evaluations = observation["evaluations"]
            preferred_reward = float(
                evaluations[preferred]["overall_reward"]
            )
            disfavored_reward = float(
                evaluations[disfavored]["overall_reward"]
            )
            repeat_evidence.append(
                {
                    "experiment_label": observation["experiment_label"],
                    "proposed_preferred_reward": preferred_reward,
                    "proposed_disfavored_reward": disfavored_reward,
                    "reward_gap": round(
                        preferred_reward - disfavored_reward,
                        4,
                    ),
                }
            )
        gaps = [row["reward_gap"] for row in repeat_evidence]
        if all(gap > 0 for gap in gaps):
            direction_status = "stable_as_proposed"
            machine_chosen = preferred
            machine_rejected = disfavored
        elif all(gap < 0 for gap in gaps):
            direction_status = "stable_reversed"
            machine_chosen = disfavored
            machine_rejected = preferred
        else:
            direction_status = "mixed_or_tied"
            machine_chosen = None
            machine_rejected = None
        reviews.append(
            {
                "pair_review_id": review_queue._sha256_text(
                    "a2:releasefoundry-corrected-order-pair-review:v1:"
                    f"{source_review_item_id}:{preferred}:{disfavored}"
                ),
                "source_review_item_id": source_review_item_id,
                "case_id": item.get("case_id"),
                "channel": item.get("channel"),
                "prompt_variant": item.get("prompt_variant"),
                "expected_variant": item.get("expected_variant"),
                "proposed_preferred_candidate_id": preferred,
                "proposed_disfavored_candidate_id": disfavored,
                "direction_status": direction_status,
                "machine_chosen_candidate_id": machine_chosen,
                "machine_rejected_candidate_id": machine_rejected,
                "repeat_count": len(repeat_evidence),
                "mean_reward_gap": round(statistics.fmean(gaps), 4),
                "minimum_reward_gap": min(gaps),
                "maximum_reward_gap": max(gaps),
                "repeat_evidence": repeat_evidence,
                "corrected_payload_semantics_valid": True,
                "methodology_status": (
                    "corrected_positional_observation_valid"
                ),
                "rerun_required": False,
                "human_review_state": "pending",
                "human_decision": None,
                "authorized_chosen_candidate_id": None,
                "authorized_rejected_candidate_id": None,
                "human_review_required": True,
                "training_eligible": False,
                "c3_authority": False,
                "release_authority": False,
            }
        )
    return reviews


def _order_reviews(item: dict[str, Any]) -> list[dict[str, Any]]:
    observations = _validated_observations(item)
    source_review_item_id = str(item["review_item_id"])
    reviews = []
    for probe in ORDER_PROBES:
        repeat_evidence = []
        for observation in observations:
            evaluations = observation["evaluations"]
            reference_reward = float(
                evaluations["reference_aligned"]["overall_reward"]
            )
            probe_reward = float(evaluations[probe]["overall_reward"])
            repeat_evidence.append(
                {
                    "experiment_label": observation["experiment_label"],
                    "reference_reward": reference_reward,
                    "order_probe_reward": probe_reward,
                    "reference_minus_probe_reward_gap": round(
                        reference_reward - probe_reward,
                        4,
                    ),
                }
            )
        gaps = [
            row["reference_minus_probe_reward_gap"]
            for row in repeat_evidence
        ]
        if all(gap > 0 for gap in gaps):
            status = "reference_outscores_probe_every_repeat"
        elif all(gap < 0 for gap in gaps):
            status = "probe_outscores_reference_every_repeat"
        elif all(gap == 0 for gap in gaps):
            status = "equal_every_repeat"
        else:
            status = "mixed_or_tied"
        within_two_count = sum(abs(gap) <= 2 for gap in gaps)
        reviews.append(
            {
                "order_review_id": review_queue._sha256_text(
                    "a2:releasefoundry-corrected-order-review:v1:"
                    f"{source_review_item_id}:{probe}"
                ),
                "source_review_item_id": source_review_item_id,
                "case_id": item.get("case_id"),
                "channel": item.get("channel"),
                "prompt_variant": item.get("prompt_variant"),
                "expected_variant": item.get("expected_variant"),
                "reference_candidate_id": "reference_aligned",
                "order_probe_candidate_id": probe,
                "corrected_order_observation_status": status,
                "machine_observation": {
                    "selection_reason": (
                        "corrected_positional_order_probe"
                    ),
                    "repeat_count": len(repeat_evidence),
                    "mean_reference_minus_probe_reward_gap": round(
                        statistics.fmean(gaps),
                        4,
                    ),
                    "minimum_reference_minus_probe_reward_gap": min(gaps),
                    "maximum_reference_minus_probe_reward_gap": max(gaps),
                    "absolute_gap_at_most_2_count": within_two_count,
                    "absolute_gap_at_most_2_rate": round(
                        within_two_count / len(gaps),
                        4,
                    ),
                    "probe_outscored_reference_count": sum(
                        gap < 0 for gap in gaps
                    ),
                    "equal_reward_count": sum(gap == 0 for gap in gaps),
                },
                "repeat_evidence": repeat_evidence,
                "corrected_payload_semantics_valid": True,
                "historical_order_probe_validity": False,
                "historical_order_blindness_reproduced": (
                    within_two_count / len(gaps) >= 0.8
                ),
                "scope_limited_service_observation": True,
                "general_order_sensitivity_claim_allowed": False,
                "rerun_required": False,
                "regression_candidate": True,
                "human_review_state": "pending",
                "human_decision": None,
                "positive_training_example": False,
                "human_review_required": True,
                "training_eligible": False,
                "c3_authority": False,
                "release_authority": False,
            }
        )
    return reviews


def _validated_observations(
    item: dict[str, Any],
    *,
    expected_count: int | None = None,
) -> list[dict[str, Any]]:
    observations = item.get("observations")
    if (
        not isinstance(observations, list)
        or len(observations) < 3
        or (
            expected_count is not None
            and len(observations) != expected_count
        )
    ):
        raise CorrectedOrderPreferenceReviewPackageError(
            "corrected_stability_item_observations_incomplete"
        )
    labels = set()
    for observation in observations:
        if not isinstance(observation, dict):
            raise CorrectedOrderPreferenceReviewPackageError(
                "corrected_stability_item_observation_invalid"
            )
        label = observation.get("experiment_label")
        if not isinstance(label, str) or not label or label in labels:
            raise CorrectedOrderPreferenceReviewPackageError(
                "corrected_stability_item_experiment_labels_invalid"
            )
        labels.add(label)
        evaluations = observation.get("evaluations")
        if not isinstance(evaluations, dict) or set(evaluations) != set(
            CANDIDATE_STRATEGIES
        ):
            raise CorrectedOrderPreferenceReviewPackageError(
                "corrected_stability_item_candidates_incomplete"
            )
        for candidate_id in CANDIDATE_STRATEGIES:
            evaluation = evaluations[candidate_id]
            if (
                not isinstance(evaluation, dict)
                or not isinstance(
                    evaluation.get("overall_reward"),
                    (int, float),
                )
            ):
                raise CorrectedOrderPreferenceReviewPackageError(
                    "corrected_stability_item_reward_invalid"
                )
    return observations


def _validate_self_hash(
    payload: dict[str, Any],
    *,
    error: str,
) -> None:
    artifact_hash = payload.get("artifact_hash")
    core = {
        key: value
        for key, value in payload.items()
        if key != "artifact_hash"
    }
    if (
        not isinstance(artifact_hash, str)
        or artifact_hash != review_queue._sha256_json(core)
    ):
        raise CorrectedOrderPreferenceReviewPackageError(error)


def _count_values(
    items: list[dict[str, Any]],
    field: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item[field])
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a redacted human-review package from corrected "
            "receipt-bound positional ReleaseFoundry sensitivity results."
        )
    )
    parser.add_argument(
        "--stability-report",
        default=calibration._display_path(DEFAULT_STABILITY_REPORT),
    )
    parser.add_argument(
        "--methodology-correction",
        default=calibration._display_path(
            DEFAULT_METHODOLOGY_CORRECTION
        ),
    )
    parser.add_argument(
        "--output",
        default=calibration._display_path(DEFAULT_OUTPUT),
    )
    args = parser.parse_args(argv)

    report_path = calibration._resolve(args.stability_report)
    correction_path = calibration._resolve(args.methodology_correction)
    output_path = calibration._resolve(args.output)
    package = build_review_package(
        calibration._read_json(report_path),
        source_report_ref=report_path,
        methodology_correction=calibration._read_json(correction_path),
        methodology_correction_ref=correction_path,
    )
    calibration._write_public_summary(output_path, package)
    summary = package["review_summary"]
    print(
        "ReleaseFoundry corrected-order preference review package written: "
        f"pairs={summary['pair_review_item_count']} "
        f"order_reviews={summary['corrected_order_review_item_count']} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
