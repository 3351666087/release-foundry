import unittest

from scripts.a2_build_multimodal_multi_repeat_comparison import (
    build_multi_repeat_comparison,
)
from scripts.a2_build_multimodal_source_repeat_comparison import BINDING_FIELDS


def calibration(*, omit: str | None = None, manifest: str = "bound"):
    result = {field: f"bound-{field}" for field in BINDING_FIELDS}
    result["manifest_hash"] = manifest
    result["qualification_state"] = "qualified"
    specifications = [
        ("safe", False, "safe_control", False),
        ("benign", False, "benign_text_safe", False),
        ("conflict", True, "cross_modal_conflict", True),
        ("injection", True, "visual_prompt_injection", True),
    ]
    result["observations"] = [
        {
            "artifact_hash": f"sha256:{index:064x}",
            "source_case_hash": f"sha256:{index:064x}",
            "expected_risk": expected,
            "observed_risk": observed,
            "taxonomy": taxonomy,
            "user_text_present": taxonomy == "benign_text_safe",
        }
        for index, (case_id, expected, taxonomy, observed) in enumerate(
            specifications, 1
        )
        if case_id != omit
    ]
    return result


class MultiRepeatComparisonTests(unittest.TestCase):
    def test_complete_three_repeat_bootstrap_is_deterministic(self):
        inputs = [calibration(), calibration(), calibration()]
        first = build_multi_repeat_comparison(
            inputs, bootstrap_samples=200, seed=51
        )
        second = build_multi_repeat_comparison(
            inputs, bootstrap_samples=200, seed=51
        )
        self.assertEqual(first, second)
        self.assertTrue(first["all_required_units_complete"])
        self.assertTrue(first["promotion_eligible"])
        self.assertEqual(first["metrics"]["specificity"]["matched_unit_count"], 2)

    def test_missing_source_unit_and_binding_mismatch_fail_closed(self):
        result = build_multi_repeat_comparison(
            [
                calibration(),
                calibration(omit="injection"),
                calibration(manifest="different"),
            ],
            bootstrap_samples=100,
            seed=51,
        )
        self.assertIn("multi_repeat_binding_mismatch", result["blockers"])
        self.assertIn(
            "multi_repeat_units_incomplete:visual_prompt_injection",
            result["blockers"],
        )
        self.assertIn(
            "multi_repeat_units_incomplete:all_source_units",
            result["blockers"],
        )
        self.assertFalse(result["promotion_eligible"])

    def test_retained_blocked_calibration_can_never_be_promotion_eligible(self):
        values = [calibration(), calibration(), calibration()]
        values[1]["qualification_state"] = "blocked"
        result = build_multi_repeat_comparison(
            values, bootstrap_samples=100, seed=51
        )
        self.assertIn(
            "multi_repeat_retained_calibration_not_qualified",
            result["blockers"],
        )
        self.assertFalse(result["promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
