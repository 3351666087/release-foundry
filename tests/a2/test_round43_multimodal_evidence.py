import json
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]


class Round43MultimodalEvidenceTests(unittest.TestCase):
    def test_round43_evidence_is_schema_valid_public_safe_and_non_authoritative(self):
        pairs = (
            (
                "multimodal_runtime_matrix_v2.schema.json",
                "a2_multimodal_runtime_matrix_round43_qwen3vl.json",
            ),
            (
                "multimodal_runtime_matrix_v2.schema.json",
                "a2_multimodal_runtime_matrix_round43_llava.json",
            ),
            (
                "multimodal_runtime_partial.schema.json",
                "a2_multimodal_runtime_matrix_round43_qwen3vl.partial.json",
            ),
            (
                "multimodal_runtime_partial.schema.json",
                "a2_multimodal_runtime_matrix_round43_llava.partial.json",
            ),
            (
                "dashscope_multimodal_calibration_v5.schema.json",
                "a2_dashscope_multimodal_calibration_round43.json",
            ),
            (
                "multimodal_cross_provider_comparison_v3.schema.json",
                "a2_multimodal_local_comparison_round43.json",
            ),
            (
                "multimodal_cross_provider_comparison_v3.schema.json",
                "a2_multimodal_cloud_local_comparison_round43.json",
            ),
            (
                "postgresql_persistence_qualification.schema.json",
                "a2_postgresql_persistence_qualification_round43.json",
            ),
            (
                "trusted_spine_binding_recheck.schema.json",
                "a2_trusted_spine_binding_recheck_round43.json",
            ),
        )
        for schema_name, evidence_name in pairs:
            with self.subTest(evidence=evidence_name):
                schema = json.loads(
                    (ROOT / "docs/a2/schemas" / schema_name).read_text(
                        encoding="utf-8"
                    )
                )
                evidence = json.loads(
                    (ROOT / "docs/evidence" / evidence_name).read_text(
                        encoding="utf-8-sig"
                    )
                )
                jsonschema.Draft202012Validator(schema).validate(evidence)
                self.assertTrue(evidence["public_safe"])
                self.assertFalse(evidence["release_authority"])

    def test_round43_local_failure_and_cloud_success_remain_distinct(self):
        qwen = json.loads(
            (
                ROOT
                / "docs/evidence/a2_multimodal_runtime_matrix_round43_qwen3vl.json"
            ).read_text(encoding="utf-8")
        )
        llava = json.loads(
            (
                ROOT / "docs/evidence/a2_multimodal_runtime_matrix_round43_llava.json"
            ).read_text(encoding="utf-8")
        )
        cloud = json.loads(
            (
                ROOT / "docs/evidence/a2_dashscope_multimodal_calibration_round43.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(qwen["qualification_state"], "blocked")
        self.assertEqual(llava["qualification_state"], "blocked")
        self.assertEqual(cloud["qualification_state"], "qualified_for_review")
        self.assertEqual(cloud["metrics"]["eligible_count"], 10)
        self.assertEqual(cloud["metrics"]["specificity"], 1.0)
        self.assertFalse(cloud["release_authority"])
        for matrix in (qwen, llava):
            for trial in matrix["trials"]:
                self.assertFalse(trial["raw_payload_included"])
                for attempt in trial["attempt_receipts"]:
                    self.assertFalse(
                        attempt["transport_receipt"]["response_body_retained"]
                    )


if __name__ == "__main__":
    unittest.main()
