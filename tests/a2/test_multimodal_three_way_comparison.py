import unittest

from scripts.a2_build_multimodal_three_way_comparison import (
    build_three_way_comparison,
)


HASH = "sha256:" + "1" * 64


def evidence(risk, *, eligible=True):
    return {
        "trials": [{
            "case_id": "case",
            "artifact_hash": HASH,
            "repeat": 1,
            "http_state": "completed",
            "parse_state": "valid_json",
            "promotion_eligible": eligible,
            "observed_risk": risk,
        }]
    }


class ThreeWayComparisonTests(unittest.TestCase):
    def test_eligible_semantic_disagreement_enqueues_review(self):
        result = build_three_way_comparison({
            "qwen": evidence(False),
            "llava": evidence(True),
            "dashscope": evidence(False),
        })
        self.assertEqual(result["summary"]["semantic_disagreement"], 1)
        self.assertEqual(len(result["human_review_queue_receipts"]), 1)
        self.assertEqual(
            result["human_review_queue_receipts"][0]["eligibility_rule"],
            "at_least_two_eligible_and_semantically_disagree",
        )

    def test_unavailable_provider_does_not_create_false_disagreement(self):
        result = build_three_way_comparison({
            "qwen": evidence(False),
            "llava": evidence(True, eligible=False),
            "dashscope": evidence(False),
        })
        self.assertEqual(result["summary"]["agreement"], 1)
        self.assertEqual(result["human_review_queue_receipts"], [])

    def test_fewer_than_two_eligible_is_unavailable(self):
        result = build_three_way_comparison({
            "qwen": evidence(False, eligible=False),
            "llava": evidence(True, eligible=False),
            "dashscope": evidence(False),
        })
        self.assertEqual(result["summary"]["unavailable"], 1)
        self.assertEqual(result["human_review_queue_receipts"], [])


if __name__ == "__main__":
    unittest.main()
