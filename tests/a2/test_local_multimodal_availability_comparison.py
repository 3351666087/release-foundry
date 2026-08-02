import unittest

from scripts.a2_build_local_multimodal_availability_comparison import (
    build_comparison,
)


def artifact(case_ids, *, completed=0, failed=0):
    return {
        "qualification_state": "blocked",
        "request_count_receipt": {
            "attempted": len(case_ids),
            "completed": completed,
            "failed": failed,
        },
        "trials": [
            {
                "case_id": case_id,
                "artifact_hash": f"sha256:{index:064x}",
                "observed_risk": None,
                "attempt_receipts": [
                    {
                        "error_class": "timeout" if failed else "",
                        "duration_receipt": {"effective_seconds": index + 1},
                    }
                ],
            }
            for index, case_id in enumerate(case_ids)
        ],
        "binding_summaries": {"one": {"eligible_count": completed}},
    }


class LocalAvailabilityComparisonTests(unittest.TestCase):
    def test_same_case_set_compares_availability_without_quality_truth(self):
        result = build_comparison(
            artifact(["a", "b"], failed=2),
            artifact(["a", "b"], completed=2),
            left_label="qwen",
            right_label="llava",
        )
        self.assertEqual(result["comparison_state"], "complete")
        self.assertFalse(result["quality_comparison_performed"])
        self.assertFalse(result["provider_is_truth"])
        self.assertEqual(result["providers"]["qwen"]["timeout_case_count"], 2)
        self.assertEqual(result["providers"]["llava"]["completed_count"], 2)

    def test_case_set_mismatch_is_blocking(self):
        result = build_comparison(
            artifact(["a"]),
            artifact(["b"]),
            left_label="qwen",
            right_label="llava",
        )
        self.assertEqual(result["comparison_state"], "blocked")
        self.assertIn("local_availability_case_set_mismatch", result["blockers"])


if __name__ == "__main__":
    unittest.main()
