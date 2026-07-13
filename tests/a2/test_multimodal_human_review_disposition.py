import json
import unittest

import jsonschema

from scripts.a2_resolve_multimodal_disagreement import ROOT, build_disposition


class MultimodalHumanReviewDispositionTests(unittest.TestCase):
    def receipt(self):
        return {
            "receipt_id": "sha256:" + "1" * 64,
            "comparison_artifact_hash": "sha256:" + "5" * 64,
            "comparison_hash": "sha256:" + "2" * 64,
            "artifact_hash": "sha256:" + "3" * 64,
            "case_id": "case-1",
            "queue_state": "awaiting_human_review",
            "reviewer_role": "multimodal_safety_reviewer",
            "release_authority": False,
        }

    def test_disposition_binds_receipt_and_hashed_reviewer_without_authority(self):
        result = build_disposition(
            self.receipt(),
            comparison_artifact_hash="sha256:" + "5" * 64,
            reviewer_identity_hash="sha256:" + "4" * 64,
            disposition="request_more_evidence",
            rationale_code="insufficient_visual_evidence",
        )
        self.assertFalse(result["release_authority"])
        self.assertFalse(result["raw_payload_included"])
        self.assertEqual(result["case_id"], "case-1")

    def test_plain_reviewer_identity_is_rejected(self):
        with self.assertRaises(jsonschema.ValidationError):
            build_disposition(
                self.receipt(),
                comparison_artifact_hash="sha256:" + "5" * 64,
                reviewer_identity_hash="reviewer@example.com",
                disposition="inconclusive",
                rationale_code="model_disagreement",
            )

    def test_mismatched_comparison_artifact_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
            build_disposition(
                self.receipt(),
                comparison_artifact_hash="sha256:" + "6" * 64,
                reviewer_identity_hash="sha256:" + "4" * 64,
                disposition="request_more_evidence",
                rationale_code="model_disagreement",
            )


if __name__ == "__main__":
    unittest.main()
