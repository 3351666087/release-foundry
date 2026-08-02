import unittest

from scripts.a2_build_multimodal_cross_provider_comparison import stable_hash
from scripts.a2_resolve_multimodal_disagreement import build_real_review_receipt
from scripts.a2_verify_multimodal_review_conservation import (
    verify_review_conservation,
)


def queue_receipt(index, eligibility_rule):
    return {
        "receipt_id": "sha256:" + f"{index + 1:064x}",
        "comparison_artifact_hash": "sha256:" + "5" * 64,
        "comparison_hash": "sha256:" + f"{index + 20:064x}",
        "artifact_hash": "sha256:" + f"{index + 40:064x}",
        "case_id": f"case-{index}",
        "repeat": 1,
        "eligibility_rule": eligibility_rule,
        "queue_state": "awaiting_human_review",
        "reviewer_role": "multimodal_safety_reviewer",
        "release_authority": False,
    }


class MultimodalReviewConservationTests(unittest.TestCase):
    def test_mixed_disagreement_and_reference_unavailable_are_conserved(self):
        disagreement = queue_receipt(
            1, "at_least_two_eligible_and_semantically_disagree"
        )
        unavailable = queue_receipt(
            2, "designated_high_quality_reference_unavailable"
        )
        review = build_real_review_receipt(
            unavailable,
            comparison_artifact_hash=unavailable["comparison_artifact_hash"],
            reviewer_identity_hash="sha256:" + "8" * 64,
            disposition="reference_unavailable_collect_more_evidence",
            rationale_code="designated_reference_unavailable",
            reviewed_at="2026-07-14T00:00:00Z",
        )
        result = verify_review_conservation(
            [disagreement, unavailable],
            [review],
        )
        self.assertEqual(result["verification_state"], "verified")
        self.assertEqual(result["queue_receipt_count"], 2)
        self.assertEqual(result["reviewed_queue_receipt_count"], 1)
        self.assertEqual(result["pending_queue_receipt_count"], 1)
        self.assertEqual(
            result["latest_receipt_hashes"][stable_hash(unavailable)],
            stable_hash(review),
        )

    def test_orphan_review_receipt_is_rejected(self):
        queued = queue_receipt(1, "designated_high_quality_reference_unavailable")
        review = build_real_review_receipt(
            queued,
            comparison_artifact_hash=queued["comparison_artifact_hash"],
            reviewer_identity_hash="sha256:" + "8" * 64,
            disposition="request_more_evidence",
            rationale_code="insufficient_visual_evidence",
            reviewed_at="2026-07-14T00:00:00Z",
        )
        result = verify_review_conservation([], [review])
        self.assertEqual(result["verification_state"], "rejected")
        self.assertIn("orphan_review_receipt", result["errors"])


if __name__ == "__main__":
    unittest.main()
