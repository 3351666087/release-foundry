import json
import unittest
from pathlib import Path

import jsonschema

from services.judge.local_multimodal_calibration import (
    aggregate_local_multimodal_golden_suite,
    build_multimodal_disagreement_receipt,
    build_credential_rotation_marker,
    evaluate_local_multimodal_golden,
)


ROOT = Path(__file__).parents[2]


class LocalMultimodalCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.golden = json.loads(
            (ROOT / "fixtures/a2/calibration/local_image_golden_case.json").read_text(encoding="utf-8")
        )
        self.binding = dict(self.golden["binding"])

    def assert_result_schema(self, result):
        schema = json.loads(
            (ROOT / "docs/a2/schemas/local_multimodal_golden_result.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(result)

    def test_reviewed_structured_semantics_pass_golden_without_release_authority(self):
        result = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output={
                "contains_text": True,
                "primary_color": "blue",
                "safety_risk": "none",
            },
            runtime_binding=self.binding,
        )
        self.assertEqual(result["regression_status"], "passed")
        self.assertEqual(result["calibration_state"], "golden_passed")
        self.assertFalse(result["release_authority"])
        self.assertFalse(result["human_review_required"])
        self.assert_result_schema(result)

    def test_smoke_only_evidence_can_never_become_calibrated(self):
        result = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=None,
            smoke_evidence={
                "status": "completed",
                "capability_state": "callable",
                "calibration_state": "uncalibrated",
            },
            runtime_binding=self.binding,
        )
        self.assertEqual(result["regression_status"], "blocked")
        self.assertEqual(result["calibration_state"], "uncalibrated")
        self.assertIn("smoke_evidence_has_no_calibration_authority", result["blockers"])
        self.assertTrue(result["human_review_required"])

    def test_semantic_mismatch_is_public_safe_and_fail_closed(self):
        result = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output={"contains_text": True, "primary_color": "red"},
            runtime_binding=self.binding,
        )
        self.assertIn("golden_mismatch:primary_color", result["blockers"])
        self.assertIn("missing_semantic_field:safety_risk", result["blockers"])
        self.assertFalse(result["release_authority"])
        self.assertTrue(result["public_safe"])
        self.assert_result_schema(result)

    def test_missing_and_mismatched_runtime_bindings_fail_closed(self):
        missing = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=dict(self.golden["expected"]),
        )
        self.assertIn("runtime_binding_missing", missing["blockers"])
        changed = dict(self.binding)
        changed["model_digest"] = "sha256:" + "0" * 64
        mismatch = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=dict(self.golden["expected"]),
            runtime_binding=changed,
        )
        self.assertIn("golden_binding_mismatch:model_digest", mismatch["blockers"])
        self.assert_result_schema(missing)
        self.assert_result_schema(mismatch)

    def test_suite_retains_case_hashes_and_enforces_rates(self):
        passed = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=dict(self.golden["expected"]),
            runtime_binding=self.binding,
        )
        abstained = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=None,
            runtime_binding=self.binding,
        )
        suite = aggregate_local_multimodal_golden_suite(
            results=[passed, abstained],
            minimum_pass_rate=0.75,
            maximum_abstention_rate=0.25,
        )
        self.assertEqual(suite["status"], "blocked")
        self.assertEqual(len(suite["case_result_hashes"]), 2)
        self.assertIn("minimum_pass_rate_not_met", suite["blockers"])
        self.assertIn("maximum_abstention_rate_exceeded", suite["blockers"])
        self.assertFalse(suite["release_authority"])

    def test_safety_field_failure_forces_human_review(self):
        unsafe = dict(self.golden["expected"])
        unsafe["safety_risk"] = "present"
        result = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=unsafe,
            runtime_binding=self.binding,
        )
        self.assertEqual(result["regression_status"], "blocked")
        self.assertIn("golden_mismatch:safety_risk", result["blockers"])
        self.assertTrue(result["human_review_required"])
        self.assertFalse(result["release_authority"])

    def test_disagreement_receipt_does_not_call_auth_failure_semantic_disagreement(self):
        local_missing = {"status": "invalid_response", "failure_detail": "empty_public_content"}
        cloud_output = {"status": "completed", "structured_output_hash": "sha256:" + "a" * 64}
        missing = build_multimodal_disagreement_receipt(
            local_result=local_missing,
            cloud_result=cloud_output,
        )
        self.assertEqual(missing["state"], "local_output_missing")
        self.assertFalse(missing["semantic_comparison_performed"])

        auth_failure = build_multimodal_disagreement_receipt(
            local_result={"status": "completed", "structured_output_hash": "sha256:" + "b" * 64},
            cloud_result={"status": "authentication_failed"},
        )
        self.assertEqual(auth_failure["state"], "cloud_unavailable")
        self.assertFalse(auth_failure["semantic_comparison_performed"])
        self.assertNotEqual(auth_failure["state"], "semantic_disagreement")

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

    def test_credential_rotation_cannot_change_golden_decision_identity(self):
        baseline = {
            "capability_state": "callable",
            "calibration_state": "uncalibrated",
            "credential_rotation_marker": build_credential_rotation_marker(
                "credential-a", provider_id="dashscope"
            ),
        }
        rotated = dict(baseline)
        rotated["credential_rotation_marker"] = build_credential_rotation_marker(
            "credential-b", provider_id="dashscope"
        )
        first = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=dict(self.golden["expected"]),
            smoke_evidence=baseline,
            runtime_binding=self.binding,
        )
        second = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=dict(self.golden["expected"]),
            smoke_evidence=rotated,
            runtime_binding=self.binding,
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
