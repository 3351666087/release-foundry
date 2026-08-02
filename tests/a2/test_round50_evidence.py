from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence"
SCHEMAS = ROOT / "docs/a2/schemas"


class Round50EvidenceTests(unittest.TestCase):
    def _load(self, name: str) -> dict:
        return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))

    def _validate(self, evidence_name: str, schema_name: str) -> dict:
        value = self._load(evidence_name)
        schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(value)
        return value

    def test_real_cloud_repeats_are_schema_valid_blocked_and_public_safe(self):
        for suffix in ("a", "b"):
            value = self._validate(
                f"a2_dashscope_multimodal_calibration_round50_run_{suffix}.json",
                "dashscope_multimodal_calibration_v5.schema.json",
            )
            self.assertEqual(value["qualification_state"], "blocked")
            self.assertTrue(value["public_safe"])
            self.assertFalse(value["secret_included"])
            self.assertFalse(value["release_authority"])
            self.assertTrue(
                all(
                    observation["raw_payload_included"] is False
                    for observation in value["observations"]
                )
            )

    def test_repeat_comparison_fails_closed_when_one_source_unit_is_missing(self):
        value = self._validate(
            "a2_multimodal_source_repeat_comparison_round50.json",
            "multimodal_source_repeat_comparison_v1.schema.json",
        )
        self.assertFalse(value["promotion_eligible"])
        self.assertEqual(
            value["blockers"], ["source_repeat_units_missing_from_repeat"]
        )
        self.assertEqual(value["missing_unit_counts"]["from_repeat"], 1)

    def test_local_qwen_timeouts_and_three_way_review_queue_are_conserved(self):
        local = self._validate(
            "a2_qwen3vl_multimodal_review_round50.json",
            "multimodal_runtime_matrix_v2.schema.json",
        )
        self.assertEqual(local["qualification_state"], "blocked")
        self.assertEqual(
            {trial["error_class"] for trial in local["trials"]}, {"timeout"}
        )
        comparison = self._validate(
            "a2_multimodal_three_way_comparison_round50.json",
            "multimodal_three_way_comparison_v2.schema.json",
        )
        conservation = self._validate(
            "a2_multimodal_review_conservation_round50.json",
            "multimodal_review_conservation_v1.schema.json",
        )
        self.assertEqual(comparison["summary"]["semantic_disagreement"], 1)
        self.assertEqual(len(comparison["human_review_queue_receipts"]), 1)
        self.assertTrue(conservation["conservation_holds"])
        self.assertEqual(conservation["pending_queue_receipt_count"], 1)
        self.assertEqual(conservation["reviewed_queue_receipt_count"], 0)

    def test_postgresql_and_trusted_spine_receipts_are_schema_valid_blockers(self):
        postgres = self._validate(
            "a2_postgresql_persistence_qualification_round50.json",
            "postgresql_persistence_qualification.schema.json",
        )
        spine = self._validate(
            "a2_trusted_spine_binding_recheck_round50.json",
            "trusted_spine_binding_recheck.schema.json",
        )
        self.assertEqual(postgres["real_postgresql_proof_state"], "blocked")
        self.assertFalse(
            postgres["claims"]["same_round_real_postgresql_verified"]
        )
        self.assertEqual(spine["binding_state"], "blocked")
        self.assertFalse(spine["trusted_spine_generated"])
        self.assertFalse(spine["a3_candidate"]["recomputes_a2_release_decision"])

    def test_public_summary_excludes_credentials_and_raw_provider_material(self):
        path = EVIDENCE / "a2_dashscope_multimodal_public_summary_round50.json"
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
        self.assertTrue(value["public_safe"])
        self.assertFalse(value["secret_included"])
        self.assertFalse(value["raw_provider_payload_included"])
        self.assertFalse(value["raw_provider_text_included"])
        self.assertFalse(value["raw_request_id_included"])
        self.assertFalse(value["interpretation"]["promotion_permitted"])
        self.assertIsNone(
            re.search(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{16,}", raw)
        )
        self.assertIsNone(re.search(r"postgres(?:ql)?://", raw, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
