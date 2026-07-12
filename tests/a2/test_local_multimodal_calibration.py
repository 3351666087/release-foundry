import json
import unittest
from pathlib import Path

import jsonschema
from services.judge.result_persistence import stable_hash

from services.judge.local_multimodal_calibration import (
    aggregate_local_multimodal_golden_suite,
    build_evidence_evaluation_identity,
    build_multimodal_disagreement_review_packet,
    build_multimodal_disagreement_receipt,
    build_credential_rotation_marker,
    evaluate_provider_fallback,
    evaluate_local_multimodal_golden,
    govern_structured_output_repair,
    observe_local_model_resources,
    validate_a3_decision_consumption,
)


ROOT = Path(__file__).parents[2]


class LocalMultimodalCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.golden = json.loads(
            (ROOT / "fixtures/a2/calibration/local_image_golden_case.json").read_text(encoding="utf-8")
        )
        self.binding = dict(self.golden["binding"])
        self.local_model = {
            "provider_id": "ollama-local",
            "model_id": "qwen3-vl:4b",
            "model_version": self.binding["model_digest"],
        }
        self.cloud_model = {
            "provider_id": "dashscope",
            "model_id": "qwen-vl-max",
            "model_version": "provider-managed",
        }
        self.llava_model = {
            "provider_id": "ollama-local",
            "model_id": "llava:7b",
            "model_version": "sha256:8dd30f6b0cb19f555f2c7a7ebda861449ea2cc76bf1f44e262931f45fc81d081",
        }
        self.calibration_binding = {
            "prompt_hash": self.binding["prompt_hash"],
            "generation_options_hash": self.binding["generation_options_hash"],
            "artifact_hash": self.binding["artifact_hash"],
        }

    def assert_result_schema(self, result):
        schema = json.loads(
            (ROOT / "docs/a2/schemas/local_multimodal_golden_result.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(result)

    def assert_schema(self, name, value):
        schema = json.loads((ROOT / f"docs/a2/schemas/{name}").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(value)

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
        abstained = dict(abstained, case_id="local-image-text-blue-abstained-v1")
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
        self.assert_schema("local_multimodal_golden_suite.schema.json", suite)

        passed_suite = aggregate_local_multimodal_golden_suite(
            results=[passed],
            minimum_pass_rate=1,
            maximum_abstention_rate=0,
        )
        self.assertEqual(passed_suite["status"], "passed")
        self.assert_schema("local_multimodal_golden_suite.schema.json", passed_suite)

    def test_suite_rejects_missing_duplicate_identity_and_failed_safety_case(self):
        passed = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output=dict(self.golden["expected"]),
            runtime_binding=self.binding,
        )
        missing_id = dict(passed, case_id="")
        with self.assertRaisesRegex(ValueError, "non-empty case ids"):
            aggregate_local_multimodal_golden_suite(
                results=[missing_id], minimum_pass_rate=1, maximum_abstention_rate=0
            )
        with self.assertRaisesRegex(ValueError, "duplicate case ids"):
            aggregate_local_multimodal_golden_suite(
                results=[passed, dict(passed, structured_output_hash="sha256:" + "1" * 64)],
                minimum_pass_rate=1,
                maximum_abstention_rate=0,
            )
        other = dict(passed, case_id="second-case")
        with self.assertRaisesRegex(ValueError, "duplicate case result hashes"):
            aggregate_local_multimodal_golden_suite(
                results=[passed, dict(passed)],
                minimum_pass_rate=1,
                maximum_abstention_rate=0,
            )

        unsafe = dict(passed, regression_status="blocked", blockers=["golden_mismatch:safety_risk"])
        suite = aggregate_local_multimodal_golden_suite(
            results=[unsafe],
            minimum_pass_rate=0,
            maximum_abstention_rate=1,
            safety_critical_case_ids=[passed["case_id"]],
        )
        self.assertEqual(suite["status"], "blocked")
        self.assertIn("safety_critical_case_failed", suite["blockers"])

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
            local_model_binding=self.local_model,
            cloud_model_binding=self.cloud_model,
        )
        self.assertEqual(missing["state"], "local_output_missing")
        self.assertFalse(missing["semantic_comparison_performed"])

        auth_failure = build_multimodal_disagreement_receipt(
            local_result={"status": "completed", "structured_output_hash": "sha256:" + "b" * 64},
            cloud_result={"status": "authentication_failed"},
            local_model_binding=self.local_model,
            cloud_model_binding=self.cloud_model,
        )
        self.assertEqual(auth_failure["state"], "cloud_unavailable")
        self.assertFalse(auth_failure["semantic_comparison_performed"])
        self.assertNotEqual(auth_failure["state"], "semantic_disagreement")
        self.assert_schema("multimodal_disagreement_receipt.schema.json", missing)
        self.assert_schema("multimodal_disagreement_receipt.schema.json", auth_failure)

    def test_every_disagreement_state_is_schema_valid_and_binding_is_required(self):
        cases = [
            ({"status": "invalid_response"}, {"status": "completed"}, "local_output_missing"),
            ({"status": "completed"}, {"status": "provider_unavailable"}, "cloud_unavailable"),
            ({"status": "completed"}, {"status": "completed"}, "not_comparable"),
            (
                {"status": "completed", "structured_output_hash": "sha256:" + "a" * 64},
                {"status": "completed", "structured_output_hash": "sha256:" + "a" * 64},
                "agreement",
            ),
            (
                {"status": "completed", "structured_output_hash": "sha256:" + "a" * 64},
                {"status": "completed", "structured_output_hash": "sha256:" + "b" * 64},
                "semantic_disagreement",
            ),
        ]
        receipts = []
        for local, cloud, state in cases:
            receipt = build_multimodal_disagreement_receipt(
                local_result=local,
                cloud_result=cloud,
                local_model_binding=self.local_model,
                cloud_model_binding=self.cloud_model,
            )
            self.assertEqual(receipt["state"], state)
            self.assert_schema("multimodal_disagreement_receipt.schema.json", receipt)
            receipts.append(receipt)
        missing_binding = build_multimodal_disagreement_receipt(
            local_result=cases[-1][0],
            cloud_result=cases[-1][1],
        )
        self.assertEqual(missing_binding["state"], "not_comparable")
        self.assertFalse(missing_binding["semantic_comparison_performed"])

        packet = build_multimodal_disagreement_review_packet(receipts[-1])
        replay = build_multimodal_disagreement_review_packet(receipts[-1])
        self.assertEqual(packet, replay)
        self.assertFalse(packet["release_authority"])
        self.assert_schema("multimodal_disagreement_review.schema.json", packet)

    def test_fallback_never_upgrades_failed_primary_into_release_pass(self):
        blocked = evaluate_provider_fallback(
            primary_result={"status": "authentication_failed"},
            fallback_result={"status": "completed", "structured_output_hash": "sha256:" + "a" * 64},
            fallback_calibration_state="uncalibrated",
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("fallback_not_calibrated", blocked["blockers"])
        self.assertFalse(blocked["release_authority"])
        self.assert_schema("provider_fallback_evaluation.schema.json", blocked)
        review = evaluate_provider_fallback(
            primary_result={"status": "authentication_failed"},
            fallback_result={"status": "completed", "structured_output_hash": "sha256:" + "a" * 64},
            fallback_calibration_state="golden_passed",
            primary_model_binding=self.cloud_model,
            fallback_model_binding=self.llava_model,
            fallback_calibration_binding=self.calibration_binding,
            runtime_calibration_binding=self.calibration_binding,
        )
        self.assertEqual(review["status"], "review_available")
        self.assertFalse(review["release_authority"])
        self.assert_schema("provider_fallback_evaluation.schema.json", review)

    def test_fallback_rejects_missing_runtime_binding_and_changed_options_hash(self):
        missing = evaluate_provider_fallback(
            primary_result={"status": "timeout"},
            fallback_result={"status": "completed"},
            fallback_calibration_state="golden_passed",
        )
        self.assertEqual(missing["status"], "blocked")
        self.assertIn("fallback_model_binding_missing_or_invalid", missing["blockers"])
        self.assertIn("fallback_calibration_binding_missing_or_invalid", missing["blockers"])
        self.assert_schema("provider_fallback_evaluation.schema.json", missing)

        changed = dict(self.calibration_binding)
        changed["generation_options_hash"] = "sha256:" + "f" * 64
        mismatch = evaluate_provider_fallback(
            primary_result={"status": "timeout"},
            fallback_result={"status": "completed"},
            fallback_calibration_state="golden_passed",
            primary_model_binding=self.cloud_model,
            fallback_model_binding=self.llava_model,
            fallback_calibration_binding=self.calibration_binding,
            runtime_calibration_binding=changed,
        )
        self.assertEqual(mismatch["status"], "blocked")
        self.assertIn("fallback_calibration_binding_mismatch", mismatch["blockers"])
        self.assert_schema("provider_fallback_evaluation.schema.json", mismatch)

    def test_structured_output_repair_is_explicit_hashed_and_never_calibrated(self):
        original = {"contains_text": True, "primary_color": "gray"}
        blocked = govern_structured_output_repair(
            original_output=original,
            required_fields=["contains_text", "primary_color", "safety_risk"],
        )
        self.assertEqual(blocked["state"], "blocked")
        self.assertEqual(blocked["repaired_output_hash"], "")
        self.assertIn("repair_policy_not_configured", blocked["blockers"])
        self.assertTrue(blocked["human_review_required"])

        repaired = govern_structured_output_repair(
            original_output=original,
            required_fields=["contains_text", "primary_color", "safety_risk"],
            repair_policy={
                "mode": "deterministic_defaults",
                "allowed_defaults": {"safety_risk": "unknown"},
            },
        )
        self.assertEqual(repaired["state"], "repaired_for_review")
        self.assertNotEqual(repaired["original_output_hash"], repaired["repaired_output_hash"])
        self.assertEqual(repaired["repaired_output"]["safety_risk"], "unknown")
        self.assertEqual(repaired["calibration_state"], "uncalibrated")
        self.assertFalse(repaired["release_authority"])

    def test_missing_safety_field_has_explicit_safety_severity(self):
        result = evaluate_local_multimodal_golden(
            golden_case=self.golden,
            structured_output={"contains_text": True, "primary_color": "blue"},
            runtime_binding=self.binding,
        )
        self.assertEqual(result["field_results"]["safety_risk"]["severity"], "safety")
        self.assertIn("safety_field_missing:safety_risk", result["blockers"])
        self.assertTrue(result["human_review_required"])

    def test_local_resource_observation_enforces_incomplete_latency_policy(self):
        observation = observe_local_model_resources(
            model_binding=self.llava_model,
            installed_bytes=4733363377,
            wall_time_seconds=50.946,
            prompt_tokens=645,
            completion_tokens=16,
            maximum_latency_seconds=30,
        )
        self.assertEqual(observation["latency_policy_state"], "incomplete")
        self.assertFalse(observation["evaluation_eligible"])
        self.assertIn("local_judge_latency_exceeded", observation["blockers"])
        within = observe_local_model_resources(
            model_binding=self.llava_model,
            installed_bytes=4733363377,
            wall_time_seconds=20,
            prompt_tokens=645,
            completion_tokens=16,
            maximum_latency_seconds=30,
        )
        self.assertEqual(within["latency_policy_state"], "within_limit")
        self.assertTrue(within["evaluation_eligible"])

    def test_a1_replay_under_rotated_credentials_preserves_a2_evaluation_identity(self):
        inputs = {
            "evidence_snapshot_hash": "sha256:" + "1" * 64,
            "policy_version": "release-policy-v7",
            "golden_suite_hash": "sha256:" + "2" * 64,
        }
        generation_a = build_credential_rotation_marker("credential-a", provider_id="dashscope")
        generation_b = build_credential_rotation_marker("credential-b", provider_id="dashscope")
        self.assertNotEqual(generation_a, generation_b)
        first = build_evidence_evaluation_identity(**inputs)
        replay = build_evidence_evaluation_identity(**inputs)
        self.assertEqual(first, replay)

    def test_a3_consumes_exact_reviewed_decision_and_cannot_recompute_release_state(self):
        committed = {
            "decision_id": "decision-reviewed-disagreement-1",
            "status": "BLOCK",
            "review_packet_hash": "sha256:" + "3" * 64,
            "policy_version": "release-policy-v7",
        }
        exact = validate_a3_decision_consumption(
            committed_decision=committed,
            consumed_decision={"a2_committed_decision_hash": stable_hash(committed)},
        )
        self.assertTrue(exact["consumption_valid"])
        recomputed = validate_a3_decision_consumption(
            committed_decision=committed,
            consumed_decision={
                "a2_committed_decision_hash": exact["committed_decision_hash"],
                "recomputed_status": "PASS",
            },
        )
        self.assertFalse(recomputed["consumption_valid"])
        self.assertIn("a3_recomputed_release_state_forbidden", recomputed["blockers"])

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
