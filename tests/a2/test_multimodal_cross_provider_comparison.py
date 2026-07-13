import unittest

from scripts.a2_build_multimodal_cross_provider_comparison import build_comparison


class MultimodalCrossProviderComparisonTests(unittest.TestCase):
    def evidence(self, model, observed, parse_state="valid_json", repeats=1):
        return {
            "provider_id": "test",
            "model_id": model,
            "generated_at": "2026-07-13T00:00:00Z",
            "prompt_hash": "sha256:" + "1" * 64,
            "observations": [
                {
                    "case_id": "case-1",
                    "artifact_hash": "sha256:" + "2" * 64,
                    "repeat": repeat,
                    "parse_state": parse_state,
                    "observed_risk": observed,
                }
                for repeat in range(1, repeats + 1)
            ],
        }

    def test_disagreement_is_queued_without_release_authority(self):
        result = build_comparison(self.evidence("left", False), self.evidence("right", True))
        self.assertEqual(result["summary"]["semantic_disagreement"], 1)
        self.assertEqual(len(result["human_review_queue_receipts"]), 1)
        self.assertFalse(result["release_authority"])
        self.assertFalse(result["human_review_queue_receipts"][0]["release_authority"])

    def test_provider_invalid_output_is_unavailable_not_agreement(self):
        result = build_comparison(
            self.evidence("left", None, "empty_response"),
            self.evidence("right", None, "empty_response"),
        )
        self.assertEqual(result["summary"]["unavailable"], 1)
        self.assertEqual(result["summary"]["agreement"], 0)
        self.assertEqual(result["human_review_queue_receipts"], [])

    def test_asymmetric_repeat_is_unavailable_not_silently_dropped(self):
        result = build_comparison(
            self.evidence("left", False, repeats=2),
            self.evidence("right", False, repeats=1),
        )
        self.assertEqual(len(result["comparisons"]), 2)
        self.assertEqual(result["summary"]["agreement"], 1)
        self.assertEqual(result["summary"]["unavailable"], 1)
        self.assertEqual(result["aggregate_summary"]["unavailable"], 1)

    def test_internal_repeat_instability_is_aggregate_review_state(self):
        left = self.evidence("left", False, repeats=2)
        left["observations"][1]["observed_risk"] = True
        result = build_comparison(left, self.evidence("right", False, repeats=2))
        self.assertEqual(result["aggregate_summary"]["internally_unstable"], 1)
        self.assertTrue(result["aggregate_comparisons"][0]["human_review_required"])


if __name__ == "__main__":
    unittest.main()
