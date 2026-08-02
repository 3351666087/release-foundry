from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import a2_releasefoundry_live_calibration as calibration  # noqa: E402
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue  # noqa: E402


DEFAULT_SOURCE_REPORT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_sensitivity_probe_expansion_35_stability.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "docs"
    / "evidence"
    / "a2_releasefoundry_order_probe_methodology_correction.json"
)
SCHEMA_VERSION = "a2.releasefoundry_order_probe_methodology_correction.v1"
SOURCE_SCHEMA_VERSION = "a2.releasefoundry_sensitivity_probe_stability.v1"
AFFECTED_CANDIDATE_IDS = (
    "wrong_tool_order",
    "reverse_tool_order",
    "missing_middle_tool",
)


class OrderProbeMethodologyCorrectionError(ValueError):
    pass


def build_correction(
    report: dict[str, Any],
    *,
    source_report_ref: str | Path = DEFAULT_SOURCE_REPORT,
) -> dict[str, Any]:
    _validate_source_report(report)
    source_hash = review_queue._sha256_json(report)
    core = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": calibration._now(),
        "correction_status": "published",
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "source_stability_report": {
            "ref": calibration._display_path(source_report_ref),
            "sha256": source_hash,
            "artifact_hash": report.get("artifact_hash"),
        },
        "affected_candidate_ids": list(AFFECTED_CANDIDATE_IDS),
        "affected_strategy_classes": [
            "tool_call_reordering",
            "tool_call_removal_with_positional_shift",
        ],
        "finding": {
            "historical_receipts_authentic": True,
            "historical_service_scores_observed": True,
            "historical_order_probe_validity": False,
            "invalidated_for_releasefoundry_order_sensitivity": True,
            "root_cause": "local_payload_order_normalization",
            "behavior_before_fix": (
                "The serializer searched remaining actual calls by the "
                "expected tool name, which could reorder a perturbed trace "
                "back into expected order before submission."
            ),
            "behavior_after_fix": (
                "The serializer consumes actual calls by position and "
                "therefore preserves reordering, omission shifts, and "
                "unexpected calls."
            ),
            "corrected_harness_revision": calibration.HARNESS_REVISION,
            "corrected_tool_call_alignment": calibration.TOOL_CALL_ALIGNMENT,
            "rerun_required": True,
            "minimum_corrected_repeat_count": 3,
        },
        "claim_limits": {
            "historical_reports_establish_releasefoundry_order_blindness": False,
            "historical_reports_authorize_order_training_labels": False,
            "historical_non_order_scores_are_human_gold": False,
            "historical_receipts_may_be_deleted": False,
        },
        "preservation_policy": {
            "retain_original_receipts": True,
            "retain_original_public_reports": True,
            "attach_correction_in_downstream_review_packages": True,
            "replace_only_after_corrected_receipt_bound_rerun": True,
        },
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
            "This correction changes the interpretation of historical order-sensitive probes; it does not alter or erase authentic service receipts.",
            "Historical scores remain observations of the payloads actually submitted by the old harness.",
            "Corrected claims require fresh experiment labels and fresh non-retried create_run calls under positional tool-call alignment.",
            "All affected evidence remains exploratory, text-projection-only, and ineligible for training or release authority.",
        ],
    }
    calibration._assert_public_summary_safe(core)
    return {
        **core,
        "artifact_hash": review_queue._sha256_json(core),
    }


def _validate_source_report(report: dict[str, Any]) -> None:
    if report.get("schema_version") != SOURCE_SCHEMA_VERSION:
        raise OrderProbeMethodologyCorrectionError(
            "source_stability_report_schema_mismatch"
        )
    if (
        report.get("evidence_lane")
        != calibration.EXPLORATORY_EVIDENCE_LANE
    ):
        raise OrderProbeMethodologyCorrectionError(
            "source_stability_report_not_exploratory"
        )
    summary = report.get("experiment_summary")
    if not isinstance(summary, dict) or (
        summary.get("report_count", 0) < 3
        or summary.get("per_test_receipts_verified") is not True
        or summary.get("aggregate_marker_used_as_authority") is not False
        or summary.get("create_run_retry_count") != 0
    ):
        raise OrderProbeMethodologyCorrectionError(
            "source_stability_report_receipt_audit_invalid"
        )
    items = report.get("items")
    if not isinstance(items, list) or not items:
        raise OrderProbeMethodologyCorrectionError(
            "source_stability_report_items_missing"
        )
    for item in items:
        observations = (
            item.get("observations") if isinstance(item, dict) else None
        )
        if not isinstance(observations, list) or not observations:
            raise OrderProbeMethodologyCorrectionError(
                "source_stability_report_observations_missing"
            )
        for observation in observations:
            evaluations = (
                observation.get("evaluations")
                if isinstance(observation, dict)
                else None
            )
            if not isinstance(evaluations, dict) or not set(
                AFFECTED_CANDIDATE_IDS
            ).issubset(evaluations):
                raise OrderProbeMethodologyCorrectionError(
                    "source_stability_report_affected_candidates_missing"
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Publish a redacted methodology correction for historical ReleaseFoundry "
            "order-sensitive probes affected by local payload normalization."
        )
    )
    parser.add_argument(
        "--source-report",
        default=calibration._display_path(DEFAULT_SOURCE_REPORT),
    )
    parser.add_argument(
        "--output",
        default=calibration._display_path(DEFAULT_OUTPUT),
    )
    args = parser.parse_args(argv)

    source_path = calibration._resolve(args.source_report)
    output_path = calibration._resolve(args.output)
    methodology_correction = build_correction(
        calibration._read_json(source_path),
        source_report_ref=source_path,
    )
    calibration._write_public_summary(output_path, methodology_correction)
    print(
        "ReleaseFoundry order-probe methodology correction written: "
        f"affected={len(methodology_correction['affected_candidate_ids'])} "
        f"output={calibration._display_path(output_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
