import unittest

from scripts.a2_build_multimodal_cross_provider_comparison import build_comparison


class MultimodalCrossProviderComparisonTests(unittest.TestCase):
    def evidence(self, model, observed, parse_state="valid_json"):
        return {
            "provider_id": "test",
            "model_id": model,
            "generated_at": "2026-07-13T00:00:00Z",
            "prompt_hash": "sha256:" + "1" * 64,
            "observations": [
                {
                    "case_id": "case-1",
                    "artifact_hash": "sha256:" + "2" * 64,
                    "repeat": 1,
                    "parse_state": parse_state,
                    "observed_risk": observed,
                }
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


if __name__ == "__main__":
    unittest.main()
