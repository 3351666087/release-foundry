from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence"
SCHEMAS = ROOT / "docs/a2/schemas"


class Round51EvidenceTests(unittest.TestCase):
    def _load(self, name: str) -> dict:
        return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))

    def _validate(self, evidence_name: str, schema_name: str) -> dict:
        value = self._load(evidence_name)
        schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(value)
        return value

    def test_real_dashscope_repeat_is_blocked_and_never_leaks_raw_material(self):
        value = self._validate(
            "a2_dashscope_multimodal_calibration_round51_run_c.json",
            "dashscope_multimodal_calibration_v5.schema.json",
        )
        self.assertEqual(value["qualification_state"], "blocked")
        self.assertIn(
            "dashscope_invalid_structured_output_observed", value["blockers"]
        )
        self.assertFalse(value["secret_included"])
        self.assertTrue(
            all(
                observation["raw_payload_included"] is False
                for observation in value["observations"]
            )
        )

    def test_multi_repeat_requires_qualified_retained_calibrations(self):
        value = self._validate(
            "a2_multimodal_multi_repeat_comparison_round51.json",
            "multimodal_multi_repeat_comparison_v1.schema.json",
        )
        self.assertEqual(value["retained_calibration_states"], ["blocked"] * 3)
        self.assertIn(
            "multi_repeat_retained_calibration_not_qualified",
            value["blockers"],
        )
        self.assertFalse(value["promotion_eligible"])
        self.assertFalse(value["provider_is_truth"])

    def test_local_evidence_is_availability_only_and_fail_closed(self):
        latency = self._validate(
            "a2_qwen3vl_latency_probe_round51.json",
            "ollama_multimodal_latency_probe_v1.schema.json",
        )
        comparison = self._validate(
            "a2_local_multimodal_availability_comparison_round51.json",
            "local_multimodal_availability_comparison_v1.schema.json",
        )
        self.assertEqual(latency["qualification_state"], "blocked")
        self.assertIn("model_warmup_material", latency["diagnosis"])
        self.assertFalse(comparison["quality_comparison_performed"])
        self.assertFalse(comparison["provider_is_truth"])
        self.assertEqual(comparison["providers"]["qwen3-vl:4b"]["eligible_count"], 0)
        self.assertEqual(comparison["providers"]["llava:7b"]["eligible_count"], 0)

    def test_pending_review_postgres_and_trusted_spine_are_conserved(self):
        collection = self._validate(
            "a2_multimodal_real_reviews_round51.json",
            "multimodal_real_review_collection_v1.schema.json",
        )
        conservation = self._validate(
            "a2_multimodal_review_conservation_round51.json",
            "multimodal_review_conservation_v1.schema.json",
        )
        postgres = self._validate(
            "a2_postgresql_persistence_qualification_round51.json",
            "postgresql_persistence_qualification.schema.json",
        )
        spine = self._validate(
            "a2_trusted_spine_binding_recheck_round51.json",
            "trusted_spine_binding_recheck.schema.json",
        )
        self.assertEqual(collection["collection_state"], "pending")
        self.assertEqual(conservation["pending_queue_receipt_count"], 1)
        self.assertEqual(postgres["real_postgresql_proof_state"], "blocked")
        self.assertFalse(
            postgres["claims"]["same_round_real_postgresql_verified"]
        )
        self.assertFalse(spine["trusted_spine_generated"])

    def test_public_summary_and_candidate_verification_are_public_safe(self):
        path = EVIDENCE / "a2_multimodal_public_summary_round51.json"
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
        identity = self._load(
            "a2_shared_candidate_identity_verification_round51.json"
        )
        self.assertTrue(value["public_safe"])
        self.assertFalse(value["secret_included"])
        self.assertFalse(value["interpretation"]["promotion_permitted"])
        self.assertFalse(identity["verified"])
        self.assertIn("shared_candidate_id_mismatch", identity["blockers"])
        self.assertIsNone(
            re.search(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{16,}", raw)
        )
        self.assertIsNone(re.search(r"postgres(?:ql)?://", raw, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
