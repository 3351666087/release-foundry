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
        fixture["predecessor_receipt_hash"] = ""
        fixture["review_sequence"] = 1
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema).validate(fixture)

    def test_round41_provider_neutral_evidence_validates(self):
        pairs = (
            (
                "dashscope_multimodal_calibration_v5.schema.json",
                "a2_dashscope_multimodal_round41_unstable_plus.json",
            ),
            (
                "dashscope_multimodal_calibration_v5.schema.json",
                "a2_dashscope_multimodal_round41_unstable_max.json",
            ),
            (
                "multimodal_comparison_receipt_verification.schema.json",
                "a2_multimodal_comparison_receipt_verification_round41_unstable.json",
            ),
            (
                "multimodal_runtime_matrix_v2.schema.json",
                "a2_multimodal_runtime_matrix_round41_qwen_unstable.json",
            ),
            (
                "multimodal_runtime_partial.schema.json",
                "a2_multimodal_runtime_matrix_round41_qwen_unstable.partial.json",
            ),
            (
                "multimodal_runtime_partial.schema.json",
                "a2_multimodal_runtime_matrix_round41_qwen_round40.partial.json",
            ),
            (
                "local_multimodal_runtime_qualification.schema.json",
                "a2_local_multimodal_runtime_qualification_round41.json",
            ),
            (
                "postgresql_persistence_qualification.schema.json",
                "a2_postgresql_persistence_qualification_round41.json",
            ),
            (
                "trusted_spine_binding_recheck.schema.json",
                "a2_trusted_spine_binding_recheck_round41.json",
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
                        encoding="utf-8"
                    )
                )
                jsonschema.Draft202012Validator(schema).validate(evidence)

    def test_round41_provider_conformance_receipts_validate(self):
        schema = json.loads(
            (
                ROOT / "docs/a2/schemas/provider_conformance_receipt.schema.json"
            ).read_text(encoding="utf-8")
        )
        for provider_id in ("dashscope", "offline_deterministic", "ollama_local"):
            evidence = json.loads(
                (
                    ROOT
                    / "docs/evidence"
                    / f"a2_provider_conformance_round41_{provider_id}.json"
                ).read_text(encoding="utf-8")
            )
            jsonschema.Draft202012Validator(schema).validate(evidence)

    def test_round41_policy_and_case_manifest_validate(self):
        pairs = (
            (
                "dashscope_multimodal_policy.schema.json",
                ROOT
                / "fixtures/a2/calibration/multimodal_taxonomy_policy_round41.json",
            ),
            (
                "multimodal_runtime_probe_cases.schema.json",
                ROOT
                / "fixtures/a2/calibration/multimodal_runtime_cases_round41_unstable.json",
            ),
        )
        for schema_name, fixture_path in pairs:
            with self.subTest(fixture=fixture_path.name):
                schema = json.loads(
                    (ROOT / "docs/a2/schemas" / schema_name).read_text(
                        encoding="utf-8"
                    )
                )
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                jsonschema.Draft202012Validator(schema).validate(fixture)
        manifest = json.loads(pairs[1][1].read_text(encoding="utf-8"))
        self.assertEqual(
            [item["case_id"] for item in manifest["cases"]],
            [
                "round40-round37-hallucination-2-jpeg-q35",
                "round40-round37-hallucination-2-rescaled-384",
            ],
        )


if __name__ == "__main__":
    unittest.main()
