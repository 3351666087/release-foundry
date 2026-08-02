import unittest

from scripts.a2_build_multimodal_source_repeat_comparison import (
    BINDING_FIELDS,
    build_source_repeat_comparison,
)


def calibration(values, *, manifest_hash="sha256:" + "a" * 64):
    result = {
        field: f"bound-{field}"
        for field in BINDING_FIELDS
    }
    result["manifest_hash"] = manifest_hash
    result["observations"] = [
        {
            "expected_risk": True,
            "source_case_hash": f"sha256:{index:064x}",
            "perturbation": {
                "kind": "rotation",
                "rotation_degrees": 2,
                "jpeg_quality": None,
            },
            "observed_risk": value,
        }
        for index, value in enumerate(values, 1)
    ]
    return result


class MultimodalSourceRepeatComparisonTests(unittest.TestCase):
    def test_paired_bootstrap_is_deterministic_and_does_not_pool_sources(self):
        first = build_source_repeat_comparison(
            calibration([True, False, True]),
            calibration([True, True, True]),
            bootstrap_samples=500,
            seed=50,
        )
        second = build_source_repeat_comparison(
            calibration([True, False, True]),
            calibration([True, True, True]),
            bootstrap_samples=500,
            seed=50,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first["baseline"]["matched_distinct_bucket_source_count"], 3
        )
        self.assertAlmostEqual(
            first["sensitivity_delta_repeat_minus_baseline"], 1 / 3
        )
        self.assertTrue(first["promotion_eligible"])

    def test_missing_unit_and_binding_mismatch_are_fail_closed(self):
        baseline = calibration([True, False])
        repeat = calibration([True], manifest_hash="sha256:" + "b" * 64)
        result = build_source_repeat_comparison(
            baseline,
            repeat,
            bootstrap_samples=100,
        )
        self.assertIn("source_repeat_binding_mismatch", result["blockers"])
        self.assertIn(
            "source_repeat_units_missing_from_repeat", result["blockers"]
        )
        self.assertFalse(result["promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
