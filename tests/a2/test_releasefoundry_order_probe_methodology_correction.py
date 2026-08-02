from __future__ import annotations

import copy

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_build_releasefoundry_order_probe_methodology_correction as correction


def _report() -> dict:
    return {
        "schema_version": correction.SOURCE_SCHEMA_VERSION,
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "artifact_hash": "sha256:historical-artifact",
        "experiment_summary": {
            "report_count": 3,
            "per_test_receipts_verified": True,
            "aggregate_marker_used_as_authority": False,
            "create_run_retry_count": 0,
        },
        "items": [
            {
                "review_item_id": "sha256:review-1",
                "observations": [
                    {
                        "evaluations": {
                            "wrong_tool_order": {"overall_reward": 98.0},
                            "reverse_tool_order": {"overall_reward": 99.0},
                            "missing_middle_tool": {
                                "overall_reward": 80.0
                            },
                        }
                    }
                ],
            }
        ],
    }


def test_builds_receipt_preserving_methodology_correction() -> None:
    result = correction.build_correction(
        _report(),
        source_report_ref="historical-stability.json",
    )

    finding = result["finding"]
    assert finding["historical_receipts_authentic"] is True
    assert finding["historical_order_probe_validity"] is False
    assert finding["invalidated_for_releasefoundry_order_sensitivity"] is True
    assert finding["root_cause"] == "local_payload_order_normalization"
    assert finding["rerun_required"] is True
    assert finding["corrected_harness_revision"] == (
        calibration.HARNESS_REVISION
    )
    assert finding["corrected_tool_call_alignment"] == "positional"
    assert result["training_eligible"] is False
    assert result["c3_transition_allowed"] is False
    assert result["release_authority"] is False


def test_rejects_unverified_or_incomplete_historical_source() -> None:
    unverified = copy.deepcopy(_report())
    unverified["experiment_summary"]["per_test_receipts_verified"] = False
    with pytest.raises(
        correction.OrderProbeMethodologyCorrectionError,
        match="source_stability_report_receipt_audit_invalid",
    ):
        correction.build_correction(unverified)

    missing = copy.deepcopy(_report())
    del missing["items"][0]["observations"][0]["evaluations"][
        "reverse_tool_order"
    ]
    with pytest.raises(
        correction.OrderProbeMethodologyCorrectionError,
        match="source_stability_report_affected_candidates_missing",
    ):
        correction.build_correction(missing)
