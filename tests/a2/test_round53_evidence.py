from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence"
SCHEMAS = ROOT / "docs/a2/schemas"


class Round53EvidenceTests(unittest.TestCase):
    def _load(self, name: str) -> dict:
        return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))

    def _validate(self, evidence_name: str, schema_name: str) -> dict:
        value = self._load(evidence_name)
        schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(value)
        return value

    def test_real_cloud_controls_remain_fail_closed(self):
        calibration = self._validate(
            "a2_dashscope_round53_controls_round53.json",
            "dashscope_multimodal_calibration_v5.schema.json",
        )
        assessment = self._validate(
            "a2_multimodal_control_policy_assessment_round53.json",
            "multimodal_control_policy_assessment_v2.schema.json",
        )
        self.assertEqual(calibration["metrics"]["specificity"], 1.0)
        self.assertEqual(calibration["metrics"]["sensitivity"], 0.5)
        self.assertEqual(assessment["quality_state"], "blocked")
        self.assertFalse(calibration["secret_included"])
        self.assertTrue(assessment["quality_blockers"])
        self.assertFalse(assessment["release_authority"])

    def test_local_runtime_probe_and_promotion_remain_blocked(self):
        image_probe = self._validate(
            "a2_qwen3vl8b_structured_token_sweep_round53.json",
            "ollama_multimodal_latency_probe_v2.schema.json",
        )
        text_probe = self._validate(
            "a2_qwen3vl8b_text_only_structured_control_round53.json",
            "ollama_multimodal_latency_probe_v2.schema.json",
        )
        promotion = self._validate(
            "a2_qwen3vl8b_runtime_promotion_round53.json",
            "local_model_runtime_promotion_contract_v2.schema.json",
        )
        self.assertEqual(image_probe["completed_profile_count"], 0)
        self.assertEqual(text_probe["completed_profile_count"], 0)
        self.assertEqual(promotion["runtime_promotion_state"], "blocked")
        self.assertFalse(promotion["release_authority"])

    def test_repeat_projection_is_read_only_and_not_promoted(self):
        comparison = self._validate(
            "a2_multimodal_multi_repeat_comparison_round53.json",
            "multimodal_multi_repeat_comparison_v2.schema.json",
        )
        projection = self._validate(
            "a2_multimodal_repeat_public_projection_round53.json",
            "multimodal_repeat_comparison_public_projection_v1.schema.json",
        )
        self.assertEqual(comparison["quality_state"], "blocked")
        self.assertEqual(comparison["stability_state"], "qualified")
        self.assertFalse(comparison["promotion_eligible"])
        self.assertFalse(projection["release_authority"])
        self.assertFalse(projection["provider_is_truth"])
        self.assertFalse(projection["promotion_eligible"])

    def test_same_round_postgresql_proof_is_verified_without_release_authority(self):
        value = self._validate(
            "a2_postgresql_persistence_qualification_round53.json",
            "postgresql_persistence_qualification.schema.json",
        )
        self.assertEqual(value["real_postgresql_proof_state"], "verified")
        self.assertTrue(value["claims"]["same_round_real_postgresql_verified"])
        self.assertEqual(value["blockers"], [])
        self.assertFalse(value["release_authority"])

    def test_trusted_spine_recheck_rejects_mismatched_projects(self):
        value = self._validate(
            "a2_trusted_spine_binding_recheck_round53.json",
            "trusted_spine_binding_recheck.schema.json",
        )
        verification = self._load(
            "a2_shared_candidate_identity_verification_round53.json"
        )
        self.assertFalse(value["trusted_spine_generated"])
        self.assertEqual(value["binding_state"], "blocked")
        self.assertTrue(value["blockers"])
        self.assertFalse(verification["verified"])
        self.assertIn(
            "a3_consumes_round52_not_round53_release_decision",
            verification["blockers"],
        )

    def test_round53_public_evidence_contains_no_key_or_dsn(self):
        names = [
            "a2_dashscope_round53_controls_round53.json",
            "a2_multimodal_control_policy_assessment_round53.json",
            "a2_multimodal_multi_repeat_comparison_round53.json",
            "a2_multimodal_repeat_public_projection_round53.json",
            "a2_postgresql_persistence_qualification_round53.json",
            "a2_qwen3vl8b_runtime_promotion_round53.json",
            "a2_qwen3vl8b_structured_token_sweep_round53.json",
            "a2_qwen3vl8b_text_only_structured_control_round53.json",
            "a2_shared_candidate_identity_verification_round53.json",
            "a2_trusted_spine_binding_recheck_round53.json",
        ]
        raw = "\n".join(
            (EVIDENCE / name).read_text(encoding="utf-8-sig")
            for name in names
        )
        self.assertIsNone(
            re.search(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}", raw)
        )
        self.assertIsNone(re.search(r"postgres(?:ql)?://", raw, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
