import unittest

from scripts.a2_build_multimodal_three_way_comparison import (
    build_three_way_comparison,
    load_pairs,
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
        self.assertEqual(
            result["summary"]["pairwise_agreement_with_unavailable"], 1
        )
        self.assertEqual(
            result["comparisons"][0]["comparison_state"],
            "pairwise_agreement_with_unavailable",
        )
        self.assertEqual(result["human_review_queue_receipts"], [])

    def test_round48_unavailable_designated_reference_enqueues_human_review(self):
        result = build_three_way_comparison(
            {
                "qwen": evidence(False),
                "llava": evidence(False),
                "dashscope": evidence(False, eligible=False),
            },
            designated_high_quality_reference="dashscope",
        )
        comparison = result["comparisons"][0]
        receipt = result["human_review_queue_receipts"][0]
        self.assertEqual(
            comparison["comparison_state"], "pairwise_agreement_with_unavailable"
        )
        self.assertTrue(comparison["human_review_required"])
        self.assertEqual(
            receipt["eligibility_rule"],
            "designated_high_quality_reference_unavailable",
        )
        self.assertEqual(receipt["reference_provider"], "dashscope")

    def test_round48_designated_reference_must_be_a_provider_label(self):
        with self.assertRaisesRegex(ValueError, "high-quality reference"):
            build_three_way_comparison(
                {
                    "qwen": evidence(False),
                    "llava": evidence(False),
                    "dashscope": evidence(False),
                },
                designated_high_quality_reference="missing",
            )

    def test_round47_three_eligible_agreement_is_named_three_way(self):
        result = build_three_way_comparison({
            "qwen": evidence(False),
            "llava": evidence(False),
            "dashscope": evidence(False),
        })
        self.assertEqual(result["summary"]["three_way_agreement"], 1)
        self.assertEqual(
            result["comparisons"][0]["comparison_state"], "three_way_agreement"
        )

    def test_fewer_than_two_eligible_is_unavailable(self):
        result = build_three_way_comparison({
            "qwen": evidence(False, eligible=False),
            "llava": evidence(True, eligible=False),
            "dashscope": evidence(False),
        })
        self.assertEqual(result["summary"]["unavailable"], 1)
        self.assertEqual(result["human_review_queue_receipts"], [])

    def test_round45_receipt_identity_is_stable_across_unrelated_evidence_changes(self):
        providers = {
            "qwen": evidence(False),
            "llava": evidence(True),
            "dashscope": evidence(False),
        }
        first = build_three_way_comparison(providers)
        providers["qwen"]["unrelated_metadata"] = {"generated_at": "later"}
        second = build_three_way_comparison(providers)
        self.assertNotEqual(
            first["comparison_artifact_hash"], second["comparison_artifact_hash"]
        )
        self.assertEqual(
            first["human_review_queue_receipts"][0]["receipt_id"],
            second["human_review_queue_receipts"][0]["receipt_id"],
        )
        self.assertEqual(sum(second["summary"].values()), len(second["comparisons"]))

    def test_round46_pairwise_conservation_and_duplicate_rejection(self):
        providers = {
            "qwen": evidence(False),
            "llava": evidence(True),
            "dashscope": evidence(False),
        }
        result = build_three_way_comparison(providers)
        self.assertEqual(
            result["schema_version"], "a2.multimodal_three_way_comparison.v2"
        )
        self.assertEqual(len(result["pairwise_summaries"]), 3)
        for summary in result["pairwise_summaries"].values():
            self.assertEqual(sum(summary.values()), len(result["comparisons"]))
        providers["qwen"]["trials"].append(dict(providers["qwen"]["trials"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate comparison case key"):
            build_three_way_comparison(providers)

    def test_round47_rejects_ambiguous_and_duplicate_provider_labels(self):
        for labels in (
            ("qwen", " qwen ", "dashscope"),
            ("qwen::local", "llava", "dashscope"),
            ("", "llava", "dashscope"),
        ):
            with self.subTest(labels=labels), self.assertRaisesRegex(
                ValueError, "provider labels"
            ):
                build_three_way_comparison({
                    labels[0]: evidence(False),
                    labels[1]: evidence(True),
                    labels[2]: evidence(False),
                })
        with self.assertRaisesRegex(ValueError, "partial journal labels"):
            build_three_way_comparison(
                {
                    "qwen": evidence(False),
                    "llava": evidence(True),
                    "dashscope": evidence(False),
                },
                partial_journals={"other": {}},
            )


if __name__ == "__main__":
    unittest.main()
