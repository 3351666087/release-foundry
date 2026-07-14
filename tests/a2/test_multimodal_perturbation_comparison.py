import unittest

from scripts.a2_build_multimodal_perturbation_comparison import (
    build_perturbation_comparison,
)


def calibration(outcomes):
    observations = []
    for index, outcome in enumerate(outcomes):
        observations.append({
            "case_id": f"case-{index}",
            "artifact_hash": "sha256:" + f"{index + 10:064x}",
            "source_case_hash": "sha256:" + f"{index + 100:064x}",
            "expected_risk": True,
            "perturbation": {
                "kind": "rotation",
                "rotation_degrees": 5,
                "jpeg_quality": None,
            },
            "observed_risk": outcome,
        })
    return {"observations": observations}


class MultimodalPerturbationComparisonTests(unittest.TestCase):
    def test_bootstrap_comparison_is_deterministic_and_public_safe(self):
        first = build_perturbation_comparison(
            calibration([True, False, True]),
            calibration([True, True, True, False]),
            bootstrap_samples=500,
            seed=49,
        )
        second = build_perturbation_comparison(
            calibration([True, False, True]),
            calibration([True, True, True, False]),
            bootstrap_samples=500,
            seed=49,
        )
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["round47"]["sensitivity"], 2 / 3)
        self.assertEqual(first["round48"]["sensitivity"], 0.75)
        self.assertTrue(first["promotion_eligible"])
        self.assertFalse(first["raw_provider_text_included"])

    def test_missing_round_observations_fail_closed(self):
        result = build_perturbation_comparison(
            {"observations": []},
            calibration([True, True, True]),
            bootstrap_samples=100,
        )
        self.assertFalse(result["promotion_eligible"])
        self.assertIsNone(result["sensitivity_delta_round48_minus_round47"])
        self.assertIn(
            "round47_transformed_attack_observations_unavailable",
            result["blockers"],
        )

    def test_repeat_outcomes_are_conservatively_collapsed_by_source(self):
        value = calibration([True])
        value["observations"].append({
            **value["observations"][0],
            "case_id": "repeat-two",
            "observed_risk": False,
        })
        result = build_perturbation_comparison(
            value,
            calibration([True, True, True]),
            bootstrap_samples=100,
        )
        self.assertEqual(result["round47"]["distinct_source_count"], 1)
        self.assertEqual(result["round47"]["detected_source_count"], 0)


if __name__ == "__main__":
    unittest.main()
