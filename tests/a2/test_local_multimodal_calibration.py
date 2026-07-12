import json
import unittest
from pathlib import Path

from services.judge.local_multimodal_calibration import (
    build_credential_rotation_marker,
    evaluate_local_multimodal_golden,
)


ROOT = Path(__file__).parents[2]


class LocalMultimodalCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.golden = json.loads(
            (ROOT / "fixtures/a2/calibration/local_image_golden_case.json").read_text(encoding="utf-8")
        )

    def test_reviewed_structured_semantics_pass_golden_without_release_authority(self):
        result = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output={
                "contains_text": True,
                "primary_color": "blue",
                "safety_risk": "none",
            },
        )
        self.assertEqual(result["regression_status"], "passed")
        self.assertEqual(result["calibration_state"], "golden_passed")
        self.assertFalse(result["release_authority"])
        self.assertFalse(result["human_review_required"])

    def test_smoke_only_evidence_can_never_become_calibrated(self):
        result = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=None,
            smoke_evidence={
                "status": "completed",
                "capability_state": "callable",
                "calibration_state": "uncalibrated",
            },
        )
        self.assertEqual(result["regression_status"], "blocked")
        self.assertEqual(result["calibration_state"], "uncalibrated")
        self.assertIn("smoke_evidence_has_no_calibration_authority", result["blockers"])
        self.assertTrue(result["human_review_required"])

    def test_semantic_mismatch_is_public_safe_and_fail_closed(self):
        result = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output={"contains_text": True, "primary_color": "red"},
        )
        self.assertIn("golden_mismatch:primary_color", result["blockers"])
        self.assertIn("missing_semantic_field:safety_risk", result["blockers"])
        self.assertFalse(result["release_authority"])
        self.assertTrue(result["public_safe"])

    def test_credential_rotation_marker_is_stable_provider_bound_and_secret_free(self):
        first = build_credential_rotation_marker("credential-a", provider_id="dashscope")
        replay = build_credential_rotation_marker("credential-a", provider_id="dashscope")
        rotated = build_credential_rotation_marker("credential-b", provider_id="dashscope")
        other_provider = build_credential_rotation_marker("credential-a", provider_id="other")
        self.assertEqual(first, replay)
        self.assertNotEqual(first, rotated)
        self.assertNotEqual(first, other_provider)
        self.assertNotIn("credential", first)
        self.assertRegex(first, r"^hmac-sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
