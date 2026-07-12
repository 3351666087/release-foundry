import hashlib
import json
from pathlib import Path
import sqlite3
import unittest

import jsonschema
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.judge.artifact_pipeline import SignatureScanner, process_artifact_reference
from services.judge.artifact_reference import InMemoryVersionedObjectReader, ObjectRead
from services.judge.signed_artifact_reference import (
    ArtifactAuthorizationLedger,
    ArtifactVerificationKey,
    SIGNED_ARTIFACT_REFERENCE_SCHEMA_VERSION,
    sign_artifact_reference,
)
from services.judge.trusted_spine import build_evidence_snapshot


ROOT = Path(__file__).parents[2]


def scope():
    return {
        "organization_id": "org-a",
        "tenant_id": "tenant-a",
        "workspace_id": "workspace-a",
        "project_id": "project-a",
        "environment_id": "test",
    }


class CountingReader(InMemoryVersionedObjectReader):
    def __init__(self, objects):
        super().__init__(objects)
        self.calls = 0

    def read_version(self, **kwargs):
        self.calls += 1
        return super().read_version(**kwargs)


class SignedArtifactReferenceTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.key = ArtifactVerificationKey(
            issuer="a1.control-plane",
            key_id="artifact-key-2026-07",
            public_key=self.private_key.public_key(),
            valid_from="2026-07-01T00:00:00Z",
            valid_until="2026-08-01T00:00:00Z",
        )
        self.connection = sqlite3.connect(":memory:")
        self.ledger = ArtifactAuthorizationLedger(self.connection)
        self.content = b"hello signed artifact"
        self.reference = self._reference()
        key = (
            self.reference["storage_provider"],
            self.reference["container_ref"],
            self.reference["object_ref"],
            self.reference["object_version"],
        )
        self.reader = CountingReader(
            {
                key: ObjectRead(
                    content=self.content,
                    object_version=self.reference["object_version"],
                    media_type=self.reference["media_type"],
                )
            }
        )

    def tearDown(self):
        self.connection.close()

    def _reference(self, **overrides):
        unsigned = {
            "schema_version": SIGNED_ARTIFACT_REFERENCE_SCHEMA_VERSION,
            "reference_id": "ref-signed-1",
            "tenant_scope": scope(),
            "artifact_id": "artifact-signed-1",
            "storage_provider": "a1-object-store",
            "container_ref": "tenant-container-1",
            "object_ref": "opaque-object-1",
            "object_version": "version-0001",
            "content_hash": "sha256:" + hashlib.sha256(self.content).hexdigest(),
            "size_bytes": len(self.content),
            "media_type": "text/plain",
            "purpose": "release-evaluation",
            "issuer": "a1.control-plane",
            "subject": "a2.release-evaluator",
            "audience": "a2-ingestion",
            "evaluation_job_id": "evaluation-job-1",
            "nonce": "MTIzNDU2Nzg5MDEyMzQ1Njc4OTA",
            "issued_at": "2026-07-12T12:00:00Z",
            "not_before": "2026-07-12T12:00:00Z",
            "expires_at": "2026-07-12T12:10:00Z",
            "algorithm": "ed25519",
            "key_id": "artifact-key-2026-07",
        }
        unsigned.update(overrides)
        return sign_artifact_reference(unsigned, private_key=self.private_key)

    def _process(self, reference=None, expected_scope=None, **kwargs):
        expected = {
            "expected_issuer": "a1.control-plane",
            "expected_audience": "a2-ingestion",
            "expected_subject": "a2.release-evaluator",
            "expected_evaluation_job_id": "evaluation-job-1",
        }
        expected.update(kwargs)
        return process_artifact_reference(
            reference or self.reference,
            reader=self.reader,
            expected_scope=expected_scope or scope(),
            expected_purpose="release-evaluation",
            now="2026-07-12T12:05:00Z",
            scanner=SignatureScanner(),
            key_resolver=lambda issuer, key_id: self.key,
            authorization_ledger=self.ledger,
            **expected,
        )

    def test_valid_signature_is_consumed_and_bound_into_snapshot(self):
        schema = json.loads(
            (ROOT / "docs/a2/schemas/artifact_reference_v2.schema.json").read_text("utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(self.reference)
        result = self._process()
        resolution = result["artifact_reference_resolution"]
        self.assertTrue(result["evaluation_eligible"])
        self.assertTrue(resolution["signature_verified"])
        self.assertTrue(resolution["revocation_checked"])
        self.assertEqual(resolution["consumption_status"], "consumed")
        self.assertTrue(resolution["authorization_receipt_hash"].startswith("sha256:"))
        self.assertNotIn(self.reference["nonce"], json.dumps(resolution))
        self.assertNotIn(self.reference["signature"], json.dumps(resolution))
        self.assertNotIn(self.reference["object_ref"], json.dumps(resolution))
        resolution_schema = json.loads(
            (
                ROOT / "docs/a2/schemas/artifact_reference_resolution_v2.schema.json"
            ).read_text("utf-8")
        )
        jsonschema.Draft202012Validator(resolution_schema).validate(resolution)
        snapshot = build_evidence_snapshot(
            {"run_id": "run-1", "final_response": "done"},
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-1",
            case_id="case-1",
            scenario_id="scenario-1",
            created_at="2026-07-12T12:05:00Z",
            required_modalities=["text"],
            artifact_pipeline_records=[result],
        )
        self.assertEqual(snapshot["completeness"], "complete")

    def test_incomplete_scope_and_missing_runtime_fail_closed_before_read(self):
        incomplete_scope = scope()
        incomplete_scope["workspace_id"] = ""
        result = self._process(expected_scope=incomplete_scope)
        self.assertIn("expected_tenant_scope_incomplete", result["blockers"])
        self.assertEqual(self.reader.calls, 0)

        result = process_artifact_reference(
            self.reference,
            reader=self.reader,
            expected_scope=scope(),
            expected_purpose="release-evaluation",
            now="2026-07-12T12:05:00Z",
            scanner=SignatureScanner(),
            expected_issuer="a1.control-plane",
            expected_audience="a2-ingestion",
            expected_subject="a2.release-evaluator",
            expected_evaluation_job_id="evaluation-job-1",
        )
        self.assertIn("signed_authorization_runtime_missing", result["blockers"])
        self.assertFalse(result["evaluation_eligible"])
        self.assertEqual(self.reader.calls, 0)

    def test_tamper_unknown_key_and_inactive_key_block_before_read(self):
        tampered = dict(self.reference)
        tampered["media_type"] = "application/json"
        result = self._process(tampered)
        self.assertIn("signature_invalid", result["blockers"])
        self.assertEqual(self.reader.calls, 0)

        result = process_artifact_reference(
            self._reference(nonce="YWJjZGVmZ2hpamtsbW5vcHFyc3Q"),
            reader=self.reader,
            expected_scope=scope(),
            expected_purpose="release-evaluation",
            now="2026-07-12T12:05:00Z",
            scanner=SignatureScanner(),
            key_resolver=lambda issuer, key_id: (_ for _ in ()).throw(KeyError(key_id)),
            authorization_ledger=self.ledger,
            expected_issuer="a1.control-plane",
            expected_audience="a2-ingestion",
            expected_subject="a2.release-evaluator",
            expected_evaluation_job_id="evaluation-job-1",
        )
        self.assertIn("verification_key_unavailable", result["blockers"])
        self.assertEqual(self.reader.calls, 0)

        inactive = ArtifactVerificationKey(
            issuer=self.key.issuer,
            key_id=self.key.key_id,
            public_key=self.key.public_key,
            status="revoked",
        )
        result = process_artifact_reference(
            self._reference(nonce="dXZ3eHl6QUJDREVGR0hJSktMTU4"),
            reader=self.reader,
            expected_scope=scope(),
            expected_purpose="release-evaluation",
            now="2026-07-12T12:05:00Z",
            scanner=SignatureScanner(),
            key_resolver=lambda issuer, key_id: inactive,
            authorization_ledger=self.ledger,
            expected_issuer="a1.control-plane",
            expected_audience="a2-ingestion",
            expected_subject="a2.release-evaluator",
            expected_evaluation_job_id="evaluation-job-1",
        )
        self.assertIn("verification_key_inactive", result["blockers"])
        self.assertEqual(self.reader.calls, 0)

    def test_wrong_binding_ttl_revocation_and_replay_block_before_second_read(self):
        for name, kwargs, blocker in (
            ("audience", {"expected_audience": "another-service"}, "audience_mismatch"),
            ("subject", {"expected_subject": "another-worker"}, "subject_mismatch"),
            ("job", {"expected_evaluation_job_id": "job-2"}, "evaluation_job_mismatch"),
        ):
            with self.subTest(name=name):
                result = self._process(**kwargs)
                self.assertIn(blocker, result["blockers"])
                self.assertEqual(self.reader.calls, 0)

        long_ttl = self._reference(
            nonce="bG9uZ3R0bG5vbmNldmFsdWUxMjM",
            expires_at="2026-07-12T13:00:00Z",
        )
        result = self._process(long_ttl)
        self.assertIn("reference_ttl_exceeded", result["blockers"])
        self.assertEqual(self.reader.calls, 0)

        self.ledger.revoke(
            revocation_type="job",
            target="evaluation-job-1",
            scope=scope(),
            reason_code="job_cancelled",
            revoked_at="2026-07-12T12:04:00Z",
        )
        revoked = self._reference(nonce="cmV2b2tlZG5vbmNldmFsdWUxMjM")
        result = self._process(revoked)
        self.assertIn("authorization_revoked:job", result["blockers"])
        self.assertEqual(self.reader.calls, 0)

        fresh_connection = sqlite3.connect(":memory:")
        try:
            fresh_ledger = ArtifactAuthorizationLedger(fresh_connection)
            first = process_artifact_reference(
                self.reference,
                reader=self.reader,
                expected_scope=scope(),
                expected_purpose="release-evaluation",
                now="2026-07-12T12:05:00Z",
                scanner=SignatureScanner(),
                key_resolver=lambda issuer, key_id: self.key,
                authorization_ledger=fresh_ledger,
                expected_issuer="a1.control-plane",
                expected_audience="a2-ingestion",
                expected_subject="a2.release-evaluator",
                expected_evaluation_job_id="evaluation-job-1",
            )
            self.assertTrue(first["evaluation_eligible"])
            calls_after_first = self.reader.calls
            second = process_artifact_reference(
                self.reference,
                reader=self.reader,
                expected_scope=scope(),
                expected_purpose="release-evaluation",
                now="2026-07-12T12:05:00Z",
                scanner=SignatureScanner(),
                key_resolver=lambda issuer, key_id: self.key,
                authorization_ledger=fresh_ledger,
                expected_issuer="a1.control-plane",
                expected_audience="a2-ingestion",
                expected_subject="a2.release-evaluator",
                expected_evaluation_job_id="evaluation-job-1",
            )
            self.assertIn("authorization_replay_detected", second["blockers"])
            self.assertEqual(self.reader.calls, calls_after_first)
        finally:
            fresh_connection.close()


if __name__ == "__main__":
    unittest.main()
