import hashlib
import json
from pathlib import Path
import unittest

import jsonschema

from services.judge.derived_evidence import (
    build_ocr_derived_evidence,
    provider_text_parts,
    public_derived_evidence,
)
from services.judge.extractor_registry import (
    ExtractorQualificationRegistry,
    qualification_record_hash,
)


ROOT = Path(__file__).parents[2]


def digest(value):
    payload = value if isinstance(value, bytes) else str(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def scope():
    return {
        "organization_id": "org-a",
        "tenant_id": "tenant-a",
        "workspace_id": "workspace-a",
        "project_id": "project-a",
        "environment_id": "test",
    }


def extractor(*, production_qualified=True):
    return {
        "extractor_id": "rapidocr",
        "extractor_version": "3.9.1",
        "runtime_id": "onnxruntime-cpu",
        "runtime_version": "1.23.2",
            "runtime_platform": "windows-x86_64",
        "model_id": "pp-ocrv6-small",
        "model_hash": digest("model"),
        "config_hash": digest("config"),
        "dictionary_hash": digest("dictionary"),
        "production_qualified": production_qualified,
    }


def qualification_record(**overrides):
    value = {
        "schema_version": "a2.extractor_qualification.v1",
        "record_id": "qual.rapidocr.3.9.1.2026-07",
        "extractor": {"id": "rapidocr", "version": "3.9.1"},
        "runtime": {
            "id": "onnxruntime-cpu",
            "version": "1.23.2",
            "platform": "windows-x86_64",
        },
        "artifact_digest": digest("model"),
        "license": "Apache-2.0",
        "supported_media_types": ["image/jpeg", "image/png"],
        "supported_languages": ["en"],
        "quality_thresholds": {
            "minimum_precision": 0.95,
            "minimum_recall": 0.95,
            "minimum_content_coverage": 0.95,
        },
        "security_checks": {
            "malformed_input": True,
            "resource_limits": True,
            "path_isolation": True,
            "active_content_disabled": True,
        },
        "offline_checks": {
            "network_disabled": True,
            "model_artifacts_pinned": True,
            "dependency_lock_verified": True,
        },
        "promotion_status": "qualified",
        "valid_from": "2026-07-01T00:00:00Z",
        "valid_until": "2027-07-01T00:00:00Z",
        "issuer": {
            "id": "a2.qualification-authority",
            "authority": "extractor-promotion",
        },
        "issuer_attestation": {
            "method": "external-record",
            "reference": "change-control/EXQ-2042",
            "issued_at": "2026-07-01T00:00:00Z",
        },
        "record_hash": "",
    }
    value.update(overrides)
    value["record_hash"] = qualification_record_hash(value)
    return value


def qualification(*, artifact_digest=None, **record_overrides):
    artifact_digest = artifact_digest or digest("model")
    record_overrides["artifact_digest"] = artifact_digest
    registry = ExtractorQualificationRegistry(
        [qualification_record(**record_overrides)],
        trusted_issuers={
            "a2.qualification-authority": frozenset({"extractor-promotion"})
        },
    )
    return registry.qualify(
        {
            "extractor_id": "rapidocr",
            "extractor_version": "3.9.1",
            "runtime_id": "onnxruntime-cpu",
            "runtime_version": "1.23.2",
            "runtime_platform": "windows-x86_64",
            "runtime_platform": "windows-x86_64",
            "artifact_digest": artifact_digest,
        },
        media_type="image/png",
        language="en",
        observed_quality={
            "minimum_precision": 0.99,
            "minimum_recall": 0.99,
            "minimum_content_coverage": 0.99,
        },
        now="2026-07-12T00:00:00Z",
    )


def record(**overrides):
    values = {
        "tenant_scope": scope(),
        "artifact_id": "artifact-1",
        "content_hash": digest(b"image"),
        "media_type": "image/png",
        "width": 640,
        "height": 480,
        "blocks": [
            {
                "text": "RELEASE BLOCKED",
                "confidence": 0.99,
                "polygon": [[10, 20], [210, 20], [210, 50], [10, 50]],
            }
        ],
        "extractor": extractor(),
        "extractor_qualification": qualification(),
        "prompt_injection_status": "passed",
        "redaction_status": "passed",
    }
    values.update(overrides)
    return build_ocr_derived_evidence(**values)


class DerivedEvidenceTests(unittest.TestCase):
    def test_public_projection_is_hash_bound_and_contains_no_ocr_text(self):
        private = record()
        public = public_derived_evidence(private)
        schema = json.loads(
            (ROOT / "docs/a2/schemas/derived_evidence.schema.json").read_text(encoding="utf-8")
        )

        jsonschema.validate(public, schema)
        self.assertTrue(public["semantic_ready"])
        self.assertTrue(public["production_eligible"])
        self.assertEqual(
            public["extractor"]["qualification"]["record_id"],
            "qual.rapidocr.3.9.1.2026-07",
        )
        self.assertFalse(
            public["extractor"]["qualification"]["cryptographic_signature_verified"]
        )
        self.assertNotIn("change-control/EXQ-2042", json.dumps(public))
        self.assertEqual(public["derived_evidence_hash"], private["public_projection_hash"])
        self.assertNotIn("text", public["blocks"][0])
        self.assertNotIn("RELEASE BLOCKED", json.dumps(public))

    def test_provider_text_requires_explicit_disclosure_and_passed_redaction(self):
        self.assertEqual(provider_text_parts([record()]), [])
        disclosed = record(provider_disclosure_allowed=True)
        parts = provider_text_parts([disclosed])
        self.assertEqual(parts[0]["text"], "RELEASE BLOCKED")
        self.assertEqual(parts[0]["citation_ids"], [disclosed["blocks"][0]["citation_id"]])
        with self.assertRaisesRegex(ValueError, "passed redaction"):
            record(provider_disclosure_allowed=True, redaction_status="not_assessed")

    def test_nonproduction_runtime_is_development_only_and_fail_closed(self):
        private = record(extractor_qualification=None)
        self.assertTrue(private["development_eligible"])
        self.assertFalse(private["semantic_ready"])
        self.assertFalse(private["production_eligible"])
        self.assertIn("ocr_runtime_not_production_qualified", private["blockers"])
        self.assertEqual(provider_text_parts([private]), [])

    def test_producer_cannot_self_declare_production_qualification(self):
        private = record(
            extractor=extractor(production_qualified=True),
            extractor_qualification=None,
        )
        self.assertFalse(private["production_eligible"])
        self.assertIn("ocr_runtime_not_production_qualified", private["blockers"])

    def test_mismatched_trusted_qualification_fails_closed(self):
        qualified = qualification()
        private = record(
            extractor={**extractor(), "model_hash": digest("other-model")},
            extractor_qualification=qualified,
        )
        self.assertFalse(private["production_eligible"])
        self.assertIn("ocr_runtime_not_production_qualified", private["blockers"])

    def test_plain_mapping_cannot_impersonate_registry_qualification(self):
        private = record(
            extractor_qualification={
                "record_id": "qual.rapidocr.3.9.1.2026-07",
                "record_hash": digest("forged"),
            }
        )
        self.assertFalse(private["production_eligible"])
        self.assertIsNone(private["extractor"]["qualification"])

    def test_unassessed_safety_controls_are_blockers(self):
        private = record(prompt_injection_status="not_assessed", redaction_status="not_assessed")
        self.assertIn("ocr_prompt_injection_not_assessed", private["blockers"])
        self.assertIn("ocr_redaction_not_assessed", private["blockers"])
        self.assertFalse(private["semantic_ready"])

    def test_empty_low_confidence_and_invalid_geometry_fail_closed(self):
        private = record(
            blocks=[
                {"text": "", "confidence": float("nan"), "polygon": [[0, 0], [1, 0], [1, 1]]},
                {
                    "text": "weak",
                    "confidence": 0.2,
                    "polygon": [[0, 0], [700, 0], [700, 10], [0, 10]],
                },
            ]
        )
        self.assertFalse(private["semantic_ready"])
        self.assertIn("ocr_block_0_text_empty", private["blockers"])
        self.assertIn("ocr_block_0_confidence_invalid", private["blockers"])
        self.assertIn("ocr_block_0_polygon_invalid", private["blockers"])
        self.assertIn("ocr_block_1_polygon_invalid", private["blockers"])
        self.assertIn("ocr_confidence_below_policy", private["blockers"])

    def test_tampering_private_text_hash_or_citation_is_rejected(self):
        for field, value in (
            ("text", "ALLOW"),
            ("text_hash", digest("other")),
            ("citation_id", digest("other")),
            ("polygon", [[0, 0], [1, 0], [1, 1], [0, 1]]),
        ):
            private = record()
            private["blocks"][0][field] = value
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                public_derived_evidence(private)

    def test_scope_and_supply_chain_hashes_are_required(self):
        bad_scope = scope()
        bad_scope.pop("environment_id")
        with self.assertRaisesRegex(ValueError, "five-field"):
            record(tenant_scope=bad_scope)
        bad_extractor = extractor()
        bad_extractor["model_hash"] = "floating-model"
        with self.assertRaisesRegex(ValueError, "supply-chain"):
            record(extractor=bad_extractor)


if __name__ == "__main__":
    unittest.main()
