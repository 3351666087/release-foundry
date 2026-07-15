from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence"
SCHEMAS = ROOT / "docs/a2/schemas"


class Round52EvidenceTests(unittest.TestCase):
    def _load(self, name: str) -> dict:
        return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))

    def _validate(self, evidence_name: str, schema_name: str) -> dict:
        value = self._load(evidence_name)
        schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(value)
        return value

    def test_real_cloud_controls_are_specific_but_attack_quality_blocks(self):
        calibration = self._validate(
            "a2_dashscope_round51_controls_round52.json",
            "dashscope_multimodal_calibration_v5.schema.json",
        )
        assessment = self._validate(
            "a2_multimodal_control_policy_assessment_round52.json",
            "multimodal_control_policy_assessment_v1.schema.json",
        )
        self.assertEqual(calibration["metrics"]["specificity"], 1.0)
        self.assertEqual(calibration["metrics"]["sensitivity"], 0.6)
        self.assertEqual(assessment["quality_state"], "blocked")
        self.assertIn(
            "multimodal_taxonomy_sensitivity_threshold_not_met:cross_modal_conflict",
            assessment["quality_blockers"],
        )
        self.assertFalse(calibration["secret_included"])

    def test_repeat_v2_separates_quality_from_stability(self):
        value = self._validate(
            "a2_multimodal_multi_repeat_comparison_round52.json",
            "multimodal_multi_repeat_comparison_v2.schema.json",
        )
        self.assertEqual(value["quality_state"], "blocked")
        self.assertEqual(value["stability_state"], "qualified")
        self.assertTrue(value["freshness_policy"]["all_repeats_fresh"])
        self.assertFalse(value["promotion_eligible"])
        self.assertFalse(value["provider_is_truth"])

    def test_high_quality_local_candidate_fails_closed_on_invalid_json(self):
        probe = self._validate(
            "a2_qwen3vl8b_structured_token_sweep_round52.json",
            "ollama_multimodal_latency_probe_v1.schema.json",
        )
        promotion = self._validate(
            "a2_qwen3vl8b_runtime_promotion_round52.json",
            "local_model_runtime_promotion_contract_v1.schema.json",
        )
        self.assertEqual(probe["model_id"], "qwen3-vl:8b")
        self.assertEqual(probe["completed_profile_count"], 0)
        self.assertEqual(promotion["runtime_promotion_state"], "blocked")
        self.assertTrue(
            any("structured_output_invalid" in item for item in promotion["blockers"])
        )

    def test_review_postgres_candidate_and_spine_remain_fail_closed(self):
        collection = self._validate(
            "a2_multimodal_real_reviews_round52.json",
            "multimodal_real_review_collection_v1.schema.json",
        )
        conservation = self._validate(
            "a2_multimodal_review_conservation_round52.json",
            "multimodal_review_conservation_v1.schema.json",
        )
        postgres = self._validate(
            "a2_postgresql_persistence_qualification_round52.json",
            "postgresql_persistence_qualification.schema.json",
        )
        spine = self._validate(
            "a2_trusted_spine_binding_recheck_round52.json",
            "trusted_spine_binding_recheck.schema.json",
        )
        identity = json.loads(
            (
                ROOT
                / "fixtures/a2/calibration/shared_candidate_identity_round52.json"
            ).read_text(encoding="utf-8")
        )
        identity_schema = json.loads(
            (
                SCHEMAS / "shared_candidate_identity_v2.schema.json"
            ).read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(identity_schema).validate(identity)
        self.assertEqual(collection["collection_state"], "pending")
        self.assertEqual(conservation["pending_queue_receipt_count"], 1)
        self.assertIn("review_collection_hash", identity["a2"])
        self.assertEqual(postgres["real_postgresql_proof_state"], "blocked")
        self.assertFalse(spine["trusted_spine_generated"])

    def test_public_summary_contains_no_secret_or_dsn(self):
        path = EVIDENCE / "a2_multimodal_public_summary_round52.json"
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
        verification = self._load(
            "a2_shared_candidate_identity_verification_round52.json"
        )
        self.assertTrue(value["public_safe"])
        self.assertFalse(value["secret_included"])
        self.assertFalse(value["interpretation"]["promotion_permitted"])
        self.assertFalse(verification["verified"])
        self.assertIsNone(
            re.search(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}", raw)
        )
        self.assertIsNone(re.search(r"postgres(?:ql)?://", raw, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
