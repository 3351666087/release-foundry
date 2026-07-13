import json
import unittest

import jsonschema

from scripts.a2_ollama_multimodal_matrix import ROOT


class Round40EvidenceSchemaTests(unittest.TestCase):
    def test_v3_is_frozen_and_v4_evidence_validates(self):
        v3 = json.loads(
            (
                ROOT
                / "docs/a2/schemas/dashscope_multimodal_calibration_v3.schema.json"
            ).read_text(encoding="utf-8")
        )
        v4 = json.loads(
            (
                ROOT
                / "docs/a2/schemas/dashscope_multimodal_calibration_v4.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            v3["properties"]["schema_version"]["const"],
            "a2.dashscope_multimodal_calibration.v3",
        )
        self.assertNotIn(
            "recovered_invalid_response",
            v3["properties"]["observations"]["items"]["properties"],
        )
        for name in (
            "a2_dashscope_multimodal_round40_controls_plus.json",
            "a2_dashscope_multimodal_round40_controls_max.json",
            "a2_dashscope_multimodal_round40_hallucination_stability_plus.json",
            "a2_dashscope_multimodal_round40_hallucination_stability_max.json",
        ):
            evidence = json.loads(
                (ROOT / "docs/evidence" / name).read_text(encoding="utf-8")
            )
            jsonschema.Draft202012Validator(v4).validate(evidence)

    def test_real_review_schema_rejects_test_fixture_identity(self):
        schema = json.loads(
            (
                ROOT
                / "docs/a2/schemas/multimodal_real_review_receipt.schema.json"
            ).read_text(encoding="utf-8")
        )
        fixture = json.loads(
            (
                ROOT
                / "docs/evidence/a2_multimodal_human_review_disposition_round39_fixture.json"
            ).read_text(encoding="utf-8")
        )
        fixture["schema_version"] = "a2.multimodal_real_review_receipt.v1"
        fixture["review_completed_at"] = "2026-07-13T00:00:00Z"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(fixture)


if __name__ == "__main__":
    unittest.main()
