import copy
import json
import unittest
from pathlib import Path

import jsonschema

from services.judge.extractor_registry import (
    ExtractorQualificationError,
    ExtractorQualificationRegistry,
    qualification_record_hash,
    validate_qualification_record,
)


def qualification_record():
    record = {
        "schema_version": "a2.extractor_qualification.v1",
        "record_id": "qual.pdf-text.4.2.1.2026-07",
        "extractor": {"id": "a2.pdf-text", "version": "4.2.1"},
        "runtime": {
            "id": "python",
            "version": "3.12.4",
            "platform": "linux-x86_64",
        },
        "artifact_digest": "sha256:" + "a" * 64,
        "license": "Apache-2.0",
        "supported_media_types": ["application/pdf", "text/plain"],
        "supported_languages": ["en", "zh-CN"],
        "quality_thresholds": {
            "minimum_precision": 0.96,
            "minimum_recall": 0.94,
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
            "reference": "change-control/EXQ-2041",
            "issued_at": "2026-07-01T00:00:00Z",
        },
        "record_hash": "",
    }
    record["record_hash"] = qualification_record_hash(record)
    return record


def deployment():
    return {
        "extractor_id": "a2.pdf-text",
        "extractor_version": "4.2.1",
        "runtime_id": "python",
        "runtime_version": "3.12.4",
        "runtime_platform": "linux-x86_64",
        "artifact_digest": "sha256:" + "a" * 64,
    }


def registry(record=None):
    return ExtractorQualificationRegistry(
        [record or qualification_record()],
        trusted_issuers={
            "a2.qualification-authority": frozenset({"extractor-promotion"})
        },
    )


class ExtractorQualificationRegistryTests(unittest.TestCase):
    def test_qualified_record_is_schema_valid_and_binds_deployment(self):
        record = qualification_record()
        schema_path = (
            Path(__file__).parents[2]
            / "docs"
            / "a2"
            / "schemas"
            / "extractor_qualification.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(record)
        self.assertEqual(
            validate_qualification_record(
                record,
                trusted_issuers={
                    "a2.qualification-authority": frozenset({"extractor-promotion"})
                },
                now="2026-07-12T00:00:00Z",
            ),
            [],
        )

        result = registry(record).qualify(
            deployment(),
            media_type="application/pdf",
            language="zh-CN",
            observed_quality={
                "minimum_precision": 0.98,
                "minimum_recall": 0.95,
                "minimum_content_coverage": 0.97,
            },
            now="2026-07-12T00:00:00Z",
        )
        self.assertEqual(result.extractor_version, "4.2.1")
        self.assertEqual(result.record_hash, record["record_hash"])

    def test_tamper_and_runtime_or_artifact_mismatch_fail_closed(self):
        tampered = qualification_record()
        tampered["supported_languages"].append("fr")
        with self.assertRaises(ExtractorQualificationError) as caught:
            registry(tampered)
        self.assertIn("record_hash_mismatch", caught.exception.blockers)

        active = registry()
        wrong = deployment()
        wrong["runtime_version"] = "3.13.0"
        wrong["artifact_digest"] = "sha256:" + "b" * 64
        with self.assertRaises(ExtractorQualificationError) as caught:
            active.qualify(
                wrong,
                media_type="application/pdf",
                language="en",
                observed_quality={
                    "minimum_precision": 0.99,
                    "minimum_recall": 0.99,
                    "minimum_content_coverage": 0.99,
                },
                now="2026-07-12T00:00:00Z",
            )
        self.assertIn("runtime_version_mismatch", caught.exception.blockers)
        self.assertIn("artifact_digest_mismatch", caught.exception.blockers)

    def test_extractor_cannot_self_attest(self):
        record = qualification_record()
        record["issuer"]["id"] = record["extractor"]["id"]
        record["record_hash"] = qualification_record_hash(record)
        blockers = validate_qualification_record(record)
        self.assertIn("extractor_self_attestation_forbidden", blockers)

    def test_revocation_and_expiry_fail_closed(self):
        active = registry()
        record = qualification_record()
        active.revoke(record["record_id"], reason_code="supply-chain-incident")
        with self.assertRaises(ExtractorQualificationError) as caught:
            active.qualify(
                deployment(),
                media_type="application/pdf",
                language="en",
                observed_quality={
                    "minimum_precision": 1.0,
                    "minimum_recall": 1.0,
                    "minimum_content_coverage": 1.0,
                },
                now="2026-07-12T00:00:00Z",
            )
        self.assertIn("qualification_revoked", caught.exception.blockers)

        with self.assertRaises(ExtractorQualificationError) as caught:
            registry().qualify(
                deployment(),
                media_type="application/pdf",
                language="en",
                observed_quality={
                    "minimum_precision": 1.0,
                    "minimum_recall": 1.0,
                    "minimum_content_coverage": 1.0,
                },
                now="2028-01-01T00:00:00Z",
            )
        self.assertIn("qualification_expired", caught.exception.blockers)

    def test_missing_threshold_or_failed_check_is_rejected(self):
        record = qualification_record()
        del record["quality_thresholds"]["minimum_recall"]
        record["security_checks"]["resource_limits"] = False
        record["record_hash"] = qualification_record_hash(record)
        blockers = validate_qualification_record(record)
        self.assertIn("quality_thresholds_incomplete", blockers)
        self.assertIn("security_checks_failed", blockers)

    def test_public_projection_redacts_attestation_and_has_no_false_signature_claim(self):
        record = qualification_record()
        public = registry(record).public_records(now="2026-07-12T00:00:00Z")
        serialized = json.dumps(public, sort_keys=True)
        projected = public["records"][0]
        self.assertNotIn(record["issuer_attestation"]["reference"], serialized)
        self.assertNotIn("quality_thresholds", projected)
        self.assertNotIn("security_checks", projected)
        self.assertNotIn("offline_checks", projected)
        self.assertFalse(projected["cryptographic_signature_verified"])
        self.assertFalse(projected["raw_attestation_included"])
        self.assertFalse(public["secret_material_included"])

    def test_malformed_inputs_fail_closed_without_echoing_unsafe_values(self):
        with self.assertRaises(ExtractorQualificationError) as caught:
            registry().qualify(
                ["not", "a", "deployment"],
                media_type="application/pdf",
                language="en",
                observed_quality={},
                now="2026-07-12T00:00:00Z",
            )
        self.assertEqual(caught.exception.blockers, ["extractor_deployment_invalid"])

        record = qualification_record()
        record["license"] = "secret\nmaterial"
        record["record_hash"] = qualification_record_hash(record)
        with self.assertRaises(ExtractorQualificationError) as caught:
            registry(record)
        self.assertIn("license_invalid", caught.exception.blockers)
        self.assertEqual(caught.exception.projection["license"], "")

    def test_untrusted_issuer_and_changed_request_are_rejected(self):
        record = qualification_record()
        with self.assertRaises(ExtractorQualificationError) as caught:
            ExtractorQualificationRegistry(
                [record],
                trusted_issuers={"a2.qualification-authority": frozenset({"other"})},
            )
        self.assertIn("issuer_not_trusted", caught.exception.blockers)

        active = registry(record)
        conflicting = copy.deepcopy(record)
        conflicting["artifact_digest"] = "sha256:" + "c" * 64
        conflicting["record_hash"] = qualification_record_hash(conflicting)
        with self.assertRaises(ExtractorQualificationError) as caught:
            active.register(conflicting)
        self.assertIn("extractor_version_record_conflict", caught.exception.blockers)


if __name__ == "__main__":
    unittest.main()
