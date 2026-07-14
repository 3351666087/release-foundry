import unittest

from scripts.a2_build_multimodal_four_way_comparison import (
    build_four_way_comparison,
)


HASH = "sha256:" + "7" * 64


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


class FourWayComparisonTests(unittest.TestCase):
    def test_round48_four_eligible_agreement_is_explicitly_four_way(self):
        result = build_four_way_comparison({
            "a": evidence(False),
            "b": evidence(False),
            "c": evidence(False),
            "d": evidence(False),
        })
        self.assertEqual(result["summary"]["four_way_agreement"], 1)
        self.assertEqual(
            result["comparisons"][0]["comparison_state"], "four_way_agreement"
        )
        self.assertEqual(len(result["pairwise_summaries"]), 6)

    def test_round48_three_and_pairwise_names_remain_explicit(self):
        three = build_four_way_comparison({
            "a": evidence(False),
            "b": evidence(False),
            "c": evidence(False),
            "d": evidence(False, eligible=False),
        })
        pair = build_four_way_comparison({
            "a": evidence(False),
            "b": evidence(False),
            "c": evidence(False, eligible=False),
            "d": evidence(False, eligible=False),
        })
        self.assertEqual(
            three["comparisons"][0]["comparison_state"],
            "three_way_agreement_with_unavailable",
        )
        self.assertEqual(
            pair["comparisons"][0]["comparison_state"],
            "pairwise_agreement_with_unavailable",
        )

    def test_round48_unavailable_designated_reference_requires_review(self):
        result = build_four_way_comparison(
            {
                "a": evidence(False),
                "b": evidence(False),
                "c": evidence(False),
                "hq": evidence(False, eligible=False),
            },
            designated_high_quality_reference="hq",
        )
        self.assertTrue(result["comparisons"][0]["human_review_required"])
        self.assertEqual(
            result["human_review_queue_receipts"][0]["eligibility_rule"],
            "designated_high_quality_reference_unavailable",
        )


if __name__ == "__main__":
    unittest.main()
