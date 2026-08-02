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
    a2_build_releasefoundry_order_probe_methodology_correction as correction,
)
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue  # noqa: E402


DEFAULT_STABILITY_REPORT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_sensitivity_probe_expansion_35_stability.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_provisional_preference_review_package.json"
)
DEFAULT_METHODOLOGY_CORRECTION = correction.DEFAULT_OUTPUT
SCHEMA_VERSION = "a2.releasefoundry_provisional_preference_review_package.v2"
SOURCE_SCHEMA_VERSION = "a2.releasefoundry_sensitivity_probe_stability.v1"
PAIR_HYPOTHESES = (
    ("reference_aligned", "tool_and_answer_defect"),
    ("missing_middle_tool", "tool_and_answer_defect"),
    ("tool_and_answer_defect", "severe_control"),
)
ORDER_PROBES = ("wrong_tool_order", "reverse_tool_order")


class ProvisionalPreferenceReviewPackageError(ValueError):
    pass


def build_review_package(
    report: dict[str, Any],
    *,
    source_report_ref: str | Path = DEFAULT_STABILITY_REPORT,
    methodology_correction: dict[str, Any],
    methodology_correction_ref: str | Path = DEFAULT_METHODOLOGY_CORRECTION,
) -> dict[str, Any]:
    _validate_report(report)
    _validate_methodology_correction(methodology_correction, report)
    items = report["items"]

    provisional_pairs = []
    order_harness_regressions = []
    for item in items:
        provisional_pairs.extend(_pair_reviews(item))
        order_harness_regressions.extend(_order_reviews(item))

    expected_pair_count = len(items) * len(PAIR_HYPOTHESES)
    expected_order_count = len(items) * len(ORDER_PROBES)
    if len(provisional_pairs) != expected_pair_count:
        raise ProvisionalPreferenceReviewPackageError(
            "stable_pair_hypotheses_incomplete"
        )
    if len(order_harness_regressions) != expected_order_count:
        raise ProvisionalPreferenceReviewPackageError(
            "order_harness_regression_reviews_incomplete"
        )

    source_hash = review_queue._sha256_json(report)
    correction_hash = review_queue._sha256_json(methodology_correction)
    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "review_status": "pending_human_review",
        "source_stability_report": {
            "ref": calibration._display_path(source_report_ref),
            "sha256": source_hash,
            "artifact_hash": report.get("artifact_hash"),
        },
        "methodology_correction": {
            "ref": calibration._display_path(methodology_correction_ref),
            "sha256": correction_hash,
            "artifact_hash": methodology_correction.get("artifact_hash"),
            "historical_order_probe_validity": False,
            "invalidated_for_releasefoundry_order_sensitivity": True,
            "root_cause": "local_payload_order_normalization",
            "rerun_required": True,
        },
        "source_experiment_summary": report["experiment_summary"],
        "review_summary": {
            "source_task_count": len(items),
            "source_repeat_count": report["experiment_summary"][
                "report_count"
            ],
            "provisional_pair_review_item_count": len(provisional_pairs),
            "order_harness_regression_review_item_count": len(
                order_harness_regressions
            ),
            "methodologically_invalid_pair_review_item_count": sum(
                not item["historical_payload_semantics_valid"]
                for item in provisional_pairs
            ),
            "authorized_preference_pair_count": 0,
            "training_eligible_pair_count": 0,
        },
        "pair_hypotheses": [
            {
                "proposed_preferred_candidate_id": preferred,
                "proposed_disfavored_candidate_id": disfavored,
                "authorization_state": "machine_hypothesis_only",
                "historical_payload_semantics_valid": (
                    preferred != "missing_middle_tool"
                    and disfavored != "missing_middle_tool"
                ),
            }
            for preferred, disfavored in PAIR_HYPOTHESES
        ],
        "order_probe_candidates": list(ORDER_PROBES),
        "provisional_pair_reviews": provisional_pairs,
        "order_harness_regression_reviews": order_harness_regressions,
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
            "The proposed preference directions are machine hypotheses derived from three receipt-bound ReleaseFoundry repeats.",
            "Authorized chosen/rejected fields remain null until a human reviewer inspects the underlying candidate traces and evidence.",
            "Historical order-sensitive observations are harness regression candidates, not evidence that ReleaseFoundry is order-blind.",
            "The historical missing-middle candidate also requires a corrected positional-alignment rerun before its pair direction can be interpreted.",
            "This package is a redacted review index; raw prompts, candidate responses, tool arguments, and service identifiers remain outside the public artifact.",
            "All source cases are text projections and do not establish native multimodal capability.",
        ],
    }
    calibration._assert_public_summary_safe(core)
    return {
        **core,
        "artifact_hash": review_queue._sha256_json(core),
    }


def _validate_report(report: dict[str, Any]) -> None:
    if report.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_schema_mismatch"
        )
    if (
        report.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_not_exploratory"
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
            raise ProvisionalPreferenceReviewPackageError(
                f"stability_report_{field}_must_be_false"
            )
    if report.get("human_review_required") is not True:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_human_review_required"
        )
    if report.get("text_projection_only") is not True:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_text_projection_boundary_missing"
        )

    summary = report.get("experiment_summary")
    if not isinstance(summary, dict):
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_experiment_summary_missing"
        )
    if summary.get("report_count", 0) < 3:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_requires_three_repeats"
        )
    if summary.get("per_test_receipts_verified") is not True:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_receipts_not_verified"
        )
    if summary.get("aggregate_marker_used_as_authority") is not False:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_aggregate_marker_is_authority"
        )
    if summary.get("create_run_retry_count") != 0:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_create_run_retries_present"
        )

    report_items = report.get("items")
    if not isinstance(report_items, list) or not report_items:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_items_missing"
        )
    review_item_ids = {
        str(item.get("review_item_id"))
        for item in report_items
        if isinstance(item, dict) and item.get("review_item_id")
    }
    if len(review_item_ids) != len(report_items):
        raise ProvisionalPreferenceReviewPackageError(
            "stability_report_review_item_ids_not_unique"
        )


def _validate_methodology_correction(
    methodology_correction: dict[str, Any],
    report: dict[str, Any],
) -> None:
    if methodology_correction.get("schema_version") != (
        correction.SCHEMA_VERSION
    ):
        raise ProvisionalPreferenceReviewPackageError(
            "methodology_correction_schema_mismatch"
        )
    finding = methodology_correction.get("finding")
    if not isinstance(finding, dict) or (
        finding.get("historical_order_probe_validity") is not False
        or finding.get("invalidated_for_releasefoundry_order_sensitivity") is not True
        or finding.get("root_cause")
        != "local_payload_order_normalization"
        or finding.get("rerun_required") is not True
    ):
        raise ProvisionalPreferenceReviewPackageError(
            "methodology_correction_finding_invalid"
        )
    source = methodology_correction.get("source_stability_report")
    if not isinstance(source, dict) or source.get("sha256") != (
        review_queue._sha256_json(report)
    ):
        raise ProvisionalPreferenceReviewPackageError(
            "methodology_correction_source_mismatch"
        )
    for field in (
        "training_eligible",
        "c3_authority",
        "c3_transition_allowed",
        "release_authority",
    ):
        if methodology_correction.get(field) is not False:
            raise ProvisionalPreferenceReviewPackageError(
                f"methodology_correction_{field}_must_be_false"
            )


def _pair_reviews(item: dict[str, Any]) -> list[dict[str, Any]]:
    observations = _validated_observations(item)
    reviews = []
    for preferred, disfavored in PAIR_HYPOTHESES:
        repeat_evidence = []
        for observation in observations:
            evaluations = observation["evaluations"]
            preferred_eval = evaluations[preferred]
            disfavored_eval = evaluations[disfavored]
            gap = round(
                float(preferred_eval["overall_reward"])
                - float(disfavored_eval["overall_reward"]),
                4,
            )
            repeat_evidence.append(
                {
                    "experiment_label": observation["experiment_label"],
                    "proposed_preferred_reward": float(
                        preferred_eval["overall_reward"]
                    ),
                    "proposed_disfavored_reward": float(
                        disfavored_eval["overall_reward"]
                    ),
                    "reward_gap": gap,
                }
            )
        gaps = [row["reward_gap"] for row in repeat_evidence]
        if not all(gap > 0 for gap in gaps):
            raise ProvisionalPreferenceReviewPackageError(
                "pair_direction_not_stable"
            )
        source_review_item_id = str(item["review_item_id"])
        historical_payload_semantics_valid = (
            preferred != "missing_middle_tool"
            and disfavored != "missing_middle_tool"
        )
        reviews.append(
            {
                "pair_review_id": review_queue._sha256_text(
                    "a2:releasefoundry-provisional-pair-review:v1:"
                    f"{source_review_item_id}:{preferred}:{disfavored}"
                ),
                "source_review_item_id": source_review_item_id,
                "case_id": item.get("case_id"),
                "channel": item.get("channel"),
                "prompt_variant": item.get("prompt_variant"),
                "expected_variant": item.get("expected_variant"),
                "machine_hypothesis": {
                    "proposed_preferred_candidate_id": preferred,
                    "proposed_disfavored_candidate_id": disfavored,
                    "all_repeats_prefer_proposed": True,
                    "repeat_count": len(repeat_evidence),
                    "mean_reward_gap": round(statistics.mean(gaps), 4),
                    "minimum_reward_gap": min(gaps),
                    "maximum_reward_gap": max(gaps),
                },
                "repeat_evidence": repeat_evidence,
                "historical_payload_semantics_valid": (
                    historical_payload_semantics_valid
                ),
                "methodology_status": (
                    "historical_observation_valid"
                    if historical_payload_semantics_valid
                    else "invalidated_pending_positional_rerun"
                ),
                "rerun_required": not historical_payload_semantics_valid,
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
        reviews.append(
            {
                "order_review_id": review_queue._sha256_text(
                    "a2:releasefoundry-order-blind-review:v1:"
                    f"{source_review_item_id}:{probe}"
                ),
                "source_review_item_id": source_review_item_id,
                "case_id": item.get("case_id"),
                "channel": item.get("channel"),
                "prompt_variant": item.get("prompt_variant"),
                "expected_variant": item.get("expected_variant"),
                "reference_candidate_id": "reference_aligned",
                "order_probe_candidate_id": probe,
                "machine_observation": {
                    "selection_reason": (
                        "historical_harness_order_normalization_requires_rerun"
                    ),
                    "repeat_count": len(repeat_evidence),
                    "mean_reference_minus_probe_reward_gap": round(
                        statistics.mean(gaps),
                        4,
                    ),
                    "maximum_absolute_reward_gap": max(
                        abs(gap) for gap in gaps
                    ),
                    "probe_outscored_reference_count": sum(
                        gap < 0 for gap in gaps
                    ),
                    "equal_reward_count": sum(gap == 0 for gap in gaps),
                },
                "repeat_evidence": repeat_evidence,
                "review_priority": "high",
                "human_review_state": "blocked_pending_corrected_rerun",
                "human_decision": None,
                "historical_order_probe_validity": False,
                "invalidated_for_releasefoundry_order_sensitivity": True,
                "root_cause": "local_payload_order_normalization",
                "rerun_required": True,
                "releasefoundry_order_sensitivity_claim_allowed": False,
                "positive_training_example": False,
                "regression_candidate": True,
                "human_review_required": True,
                "training_eligible": False,
                "c3_authority": False,
                "release_authority": False,
            }
        )
    return reviews


def _validated_observations(
    item: dict[str, Any],
) -> list[dict[str, Any]]:
    observations = item.get("observations")
    if not isinstance(observations, list) or len(observations) < 3:
        raise ProvisionalPreferenceReviewPackageError(
            "stability_item_observations_incomplete"
        )
    required_candidates = {
        "reference_aligned",
        "tool_and_answer_defect",
        "missing_middle_tool",
        "severe_control",
        *ORDER_PROBES,
    }
    labels = set()
    for observation in observations:
        if not isinstance(observation, dict):
            raise ProvisionalPreferenceReviewPackageError(
                "stability_item_observation_invalid"
            )
        label = observation.get("experiment_label")
        if not isinstance(label, str) or not label or label in labels:
            raise ProvisionalPreferenceReviewPackageError(
                "stability_item_experiment_labels_invalid"
            )
        labels.add(label)
        evaluations = observation.get("evaluations")
        if not isinstance(evaluations, dict):
            raise ProvisionalPreferenceReviewPackageError(
                "stability_item_evaluations_missing"
            )
        if not required_candidates.issubset(evaluations):
            raise ProvisionalPreferenceReviewPackageError(
                "stability_item_candidates_incomplete"
            )
        for candidate_id in required_candidates:
            evaluation = evaluations[candidate_id]
            if (
                not isinstance(evaluation, dict)
                or not isinstance(
                    evaluation.get("overall_reward"), int | float
                )
            ):
                raise ProvisionalPreferenceReviewPackageError(
                    "stability_item_reward_invalid"
                )
    return observations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a redacted human-review package from repeated, "
            "receipt-bound ReleaseFoundry sensitivity results."
        )
    )
    parser.add_argument(
        "--stability-report",
        default=calibration._display_path(DEFAULT_STABILITY_REPORT),
    )
    parser.add_argument(
        "--output",
        default=calibration._display_path(DEFAULT_OUTPUT),
    )
    parser.add_argument(
        "--methodology-correction",
        default=calibration._display_path(DEFAULT_METHODOLOGY_CORRECTION),
    )
    args = parser.parse_args(argv)

    report_path = calibration._resolve(args.stability_report)
    output_path = calibration._resolve(args.output)
    correction_path = calibration._resolve(args.methodology_correction)
    package = build_review_package(
        calibration._read_json(report_path),
        source_report_ref=report_path,
        methodology_correction=calibration._read_json(correction_path),
        methodology_correction_ref=correction_path,
    )
    calibration._write_public_summary(output_path, package)
    print(
        "ReleaseFoundry provisional preference review package written: "
        f"pairs={package['review_summary']['provisional_pair_review_item_count']} "
        "order_harness_regressions="
        f"{package['review_summary']['order_harness_regression_review_item_count']} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
