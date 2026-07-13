import hashlib
import hmac
import json
import sqlite3
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from services.judge.provider_gateway import (
    ProviderDefinition, ProviderGateway, StrictFakeAdapter, StrictFakeReconciliationAdapter,
)
from services.judge.artifact_pipeline import process_artifact
from services.judge.derived_evidence import build_ocr_derived_evidence
from services.judge.evaluation_quality_proof import EVALUATION_QUALITY_PROOF_SCHEMA_VERSION
from services.judge.evaluation_trust_policy import (
    normalize_evaluation_trust_policy,
    verifier_arguments,
)
from tests.a2.test_derived_evidence import qualification
from services.judge.provider_runtime import AUTHENTICATED_BUNDLE_SCHEMA_VERSION, validate_semantic_judge_output
from services.judge.release_decision_orchestrator import (
    execute_release_decision,
    reconcile_release_decision,
    recover_release_decision,
)
from services.judge.release_decision_store import (
    IdempotencyConflictError,
    authorize_provider_call,
    claim_decision_recovery,
    claim_due_provider_reconciliation,
    claim_provider_reconciliation,
    claim_decision_outbox,
    load_decision_recovery_envelope,
    migrate_evaluation_quality_v1_recovery_envelope,
    mark_operation_recovery_required,
    persist_provider_outcome,
    persist_provider_reconciliation_observation,
    persist_release_decision,
    reserve_decision_operation,
    settle_decision_outbox,
)
from services.judge.result_persistence import stable_hash
from services.judge.sql_store import initialize_sql_store
from services.judge.trusted_spine import build_evidence_snapshot


NOW = 1_750_000_000_000
KEY = b"k" * 32


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def run_result():
    return {
        "run_id": "run-1",
        "trace_completeness": 1,
        "aggregate_metrics": {"schema_version": "ashr.clone.run_result.v1"},
        "cases": [
            {
                "case_id": "case-1",
                "agent_output": {"final_response": "done"},
                "observations": [{"run_id": "run-1", "case_id": "case-1", "tool_calls": []}],
            }
        ],
    }


def signed_bundle(evidence=None):
    evidence = evidence or [run_result()]
    fields = {
        "schema_version": AUTHENTICATED_BUNDLE_SCHEMA_VERSION,
        "algorithm": "hmac-sha256",
        "key_id": "key-1",
        "bundle_id_digest": digest(b"bundle-1"),
        "tenant_digest": digest(b"tenant-a"),
        "project_digest": digest(b"project-a"),
        "evidence": evidence,
        "evidence_digest": digest(canonical(evidence)),
        "issued_at_unix_ms": NOW - 1000,
        "expires_at_unix_ms": NOW + 1000,
    }
    signing = {key: fields[key] for key in fields if key != "evidence"}
    fields["signature"] = hmac.new(KEY, canonical(signing), hashlib.sha256).hexdigest()
    return fields


def request(bundle=None):
    candidate = {
        "organization_id": "org-a",
        "tenant_id": "tenant-a",
        "workspace_id": "workspace-a",
        "project_id": "project-a",
        "environment_id": "test",
        "run_id": "run-1",
        "case_id": "case-1",
        "scenario_id": "A2-S001",
        "created_at": "2026-07-12T00:00:00Z",
        "required_modalities": ["text"],
        "provider_id": "unit",
        "model_id": "semantic-1",
        "model_digest": "sha256:" + "b" * 64,
        "rubric_version": "rubric.v1",
        "golden_dataset_digest": "sha256:" + "c" * 64,
        "calibration_thresholds_hash": "sha256:" + "d" * 64,
        "policy_version": "a2.semantic_release_policy.v1",
        "idempotency_key": "decision-1",
        "authenticated_evidence_bundle": bundle or signed_bundle(),
    }
    candidate["evaluation_quality_proof"] = signed_quality_proof(candidate)
    return candidate


def signed_quality_proof(candidate, **overrides):
    bundle = candidate["authenticated_evidence_bundle"]
    signing = {
        key: bundle[key]
        for key in (
            "schema_version", "algorithm", "key_id", "bundle_id_digest", "tenant_digest",
            "project_digest", "evidence_digest", "issued_at_unix_ms", "expires_at_unix_ms",
        )
    }
    run_payload = bundle["evidence"][0]
    snapshot = build_evidence_snapshot(
        run_payload,
        organization_id=candidate["organization_id"],
        tenant_id=candidate["tenant_id"],
        workspace_id=candidate["workspace_id"],
        project_id=candidate["project_id"],
        environment_id=candidate["environment_id"],
        run_id=candidate["run_id"],
        case_id=candidate["case_id"],
        scenario_id=candidate["scenario_id"],
        created_at=candidate["created_at"],
        required_modalities=candidate.get("required_modalities", ["text"]),
        source_schema_version=run_payload["aggregate_metrics"]["schema_version"],
        artifact_pipeline_records=candidate.get("artifact_pipeline_records", []),
        derived_evidence_records=candidate.get("derived_evidence_records", []),
    )
    proof = {
        "schema_version": EVALUATION_QUALITY_PROOF_SCHEMA_VERSION,
        "algorithm": "hmac-sha256",
        "issuer": "a2-calibration-service",
        "key_id": "key-1",
        "organization_id": candidate["organization_id"],
        "tenant_id": candidate["tenant_id"],
        "workspace_id": candidate["workspace_id"],
        "project_id": candidate["project_id"],
        "environment_id": candidate["environment_id"],
        "authenticated_bundle_digest": digest(canonical(signing)),
        "snapshot_hash": snapshot["snapshot_hash"],
        "provider_id": candidate["provider_id"],
        "model_id": candidate["model_id"],
        "model_digest": candidate["model_digest"],
        "prompt_hash": stable_hash(
            candidate.get("judge_prompt") or "Evaluate the authenticated evidence snapshot."
        ),
        "rubric_version": candidate["rubric_version"],
        "golden_dataset_digest": candidate["golden_dataset_digest"],
        "calibration_thresholds_hash": candidate["calibration_thresholds_hash"],
        "policy_version": candidate["policy_version"],
        "calibration": "passed",
        "golden_regression": "passed",
        "disagreement": "agree",
        "reviewer_identity_digest": "",
        "reviewed_at_unix_ms": 0,
        "evidence_refs": ["sha256:" + "a" * 64],
        "issued_at_unix_ms": NOW - 1000,
        "expires_at_unix_ms": NOW + 1000,
    }
    proof.update(overrides)
    proof["signature"] = hmac.new(KEY, canonical(proof), hashlib.sha256).hexdigest()
    return proof


def gateway(response=None, *, failure="", audit_writer=None):
    provider = ProviderDefinition(
        "unit", "fake", "local", "", frozenset({"text"}), frozenset({"tenant-a"}), data_residency="local"
    )
    response = response or {
        "output_text": json.dumps(
            {
                "passed": True,
                "score": 0.98,
                "reason": "evidence supports release",
                "failure_classes": [],
                "evidence_refs": ["snapshot"],
                "abstained": False,
            }
        ),
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }
    return ProviderGateway(
        [provider],
        {"fake": StrictFakeAdapter(response, failure=failure)},
        audit_writer=audit_writer,
        response_validator=validate_semantic_judge_output,
    )


class ProductionScanner:
    scanner_id = "clamav"
    scanner_version = "1.2.3"

    def scan(self, content, media_type):
        return {
            "status": "clean",
            "engine": self.scanner_id,
            "engine_version": self.scanner_version,
            "production_qualified": True,
            "signature_set": "20260712",
        }


class GroundedRecordingAdapter:
    def __init__(self):
        self.calls = 0
        self.payloads = []

    def invoke(self, model, payload, timeout_seconds):
        self.calls += 1
        self.payloads.append(payload)
        citation = payload["parts"][1]["citation_ids"][0]
        return {
            "output_text": json.dumps(
                {
                    "passed": True,
                    "score": 0.99,
                    "reason": "OCR evidence is grounded",
                    "failure_classes": [],
                    "evidence_refs": [citation],
                    "abstained": False,
                }
            ),
            "usage": {"input_tokens": 20, "output_tokens": 10},
        }


def image_pipeline_and_evidence(*, production_qualified=True, disclosure=True):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    ihdr = struct.pack(">IIBBBBB", 2, 3, 8, 2, 0, 0, 0)
    raw = b"\x00" + (b"\x00\x00\x00" * 2)
    content = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw * 3))
        + chunk(b"IEND", b"")
    )
    pipeline = process_artifact(
        {
            "tenant_scope": {
                "organization_id": "org-a",
                "tenant_id": "tenant-a",
                "workspace_id": "workspace-a",
                "project_id": "project-a",
                "environment_id": "test",
            },
            "artifact_id": "artifact-1",
            "filename": "release.png",
            "media_type": "image/png",
            "content_hash": "sha256:" + hashlib.sha256(content).hexdigest(),
            "source_ref": "object://private/artifact-1",
        },
        content,
        scanner=ProductionScanner(),
        require_production_scanner=True,
    )
    if not pipeline["evaluation_eligible"] or pipeline["blockers"]:
        raise AssertionError(f"invalid multimodal test pipeline: {pipeline['blockers']}")
    evidence = build_ocr_derived_evidence(
        tenant_scope=pipeline["tenant_scope"],
        artifact_id="artifact-1",
        content_hash=pipeline["manifest"]["content_hash"],
        media_type="image/png",
        width=2,
        height=3,
        blocks=[
            {
                "text": "RELEASE BLOCKED",
                "confidence": 0.99,
                "polygon": [[0, 0], [2, 0], [2, 2], [0, 2]],
            }
        ],
        extractor={
            "extractor_id": "rapidocr",
            "extractor_version": "3.9.1",
            "runtime_id": "onnxruntime-cpu",
            "runtime_version": "1.23.2",
            "runtime_platform": "windows-x86_64",
            "model_id": "pp-ocrv6-small",
            "model_hash": stable_hash("model"),
            "config_hash": stable_hash("config"),
            "dictionary_hash": stable_hash("dictionary"),
            "production_qualified": production_qualified,
        },
        extractor_qualification=(
            qualification(artifact_digest=stable_hash("model"))
            if production_qualified
            else None
        ),
        provider_disclosure_allowed=disclosure,
        prompt_injection_status="passed",
        redaction_status="passed",
    )
    return pipeline, evidence


def reconciliation_gateway(status="remote_pending"):
    provider = ProviderDefinition(
        "unit", "fake", "local", "", frozenset({"text"}), frozenset({"tenant-a"}),
        data_residency="local", reconciliation_mode="provider_status_lookup",
    )
    response = {"status": status}
    if status == "remote_completed":
        response["output"] = {
            "output_text": json.dumps(
                {
                    "passed": True, "score": 0.98, "reason": "verified",
                    "failure_classes": [], "evidence_refs": ["snapshot"], "abstained": False,
                }
            )
        }
    adapter = StrictFakeReconciliationAdapter(reconciliation_response=response)
    return ProviderGateway(
        [provider], {"fake": adapter}, response_validator=validate_semantic_judge_output,
    )


class ProcessInterruptedAdapter:
    calls = 0

    def invoke(self, model, payload, timeout_seconds):
        self.calls += 1
        raise KeyboardInterrupt("worker terminated during provider call")


class ReleaseDecisionOrchestratorTests(unittest.TestCase):
    def test_round33_taxonomy_policy_hash_change_conflicts_and_legacy_recovery_fails_closed(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            candidate = request()
            candidate["taxonomy_policy_hash"] = "sha256:" + "1" * 64

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("stop")

            with self.assertRaises(OSError):
                execute_release_decision(
                    candidate,
                    gateway=gateway(),
                    key_resolver=lambda _: KEY,
                    now_unix_ms=NOW,
                    persistence_connection=connection,
                    persistence_failure_injector=fail,
                )
            changed = request()
            changed["taxonomy_policy_hash"] = "sha256:" + "2" * 64
            with self.assertRaises(IdempotencyConflictError):
                execute_release_decision(
                    changed,
                    gateway=gateway(),
                    key_resolver=lambda _: KEY,
                    now_unix_ms=NOW,
                    persistence_connection=connection,
                )

            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            envelope = json.loads(
                connection.execute(
                    "SELECT recovery_envelope_json FROM a2_provider_outcomes"
                ).fetchone()[0]
            )
            envelope.pop("taxonomy_policy_hash")
            connection.execute(
                "UPDATE a2_provider_outcomes SET recovery_envelope_json = ?, recovery_envelope_hash = ?",
                (
                    json.dumps(envelope, sort_keys=True, separators=(",", ":")),
                    stable_hash(envelope),
                ),
            )
            connection.commit()
            with self.assertRaisesRegex(ValueError, "governed schema"):
                load_decision_recovery_envelope(
                    connection,
                    operation_id=operation_id,
                    scope={key: candidate[key] for key in (
                        "organization_id", "tenant_id", "workspace_id",
                        "project_id", "environment_id",
                    )},
                )
        finally:
            connection.close()

    def test_trust_policy_normalization_rejects_ungoverned_issuers_and_hashes(self):
        base = {
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": ["issuer-a"],
            "issuer_tenants": {"issuer-a": ["tenant-a"]},
            "revoked_key_ids": ["other-key", "other-key"],
            "revoked_proof_hashes": [
                "sha256:" + "e" * 64,
                "sha256:" + "e" * 64,
            ],
            "maximum_lifetime_ms": 1000,
            "maximum_review_age_ms": 1000,
        }
        invalid_issuer = {**base, "issuer_tenants": {"issuer-b": ["tenant-a"]}}
        with self.assertRaisesRegex(ValueError, "allowed issuer"):
            normalize_evaluation_trust_policy(invalid_issuer)
        invalid_hash = {**base, "revoked_proof_hashes": ["not-a-hash"]}
        with self.assertRaisesRegex(ValueError, "proof hashes"):
            normalize_evaluation_trust_policy(invalid_hash)
        invalid_key = {**base, "revoked_key_ids": ["unsafe key"]}
        with self.assertRaisesRegex(ValueError, "key ids"):
            normalize_evaluation_trust_policy(invalid_key)

    def test_empty_allowlist_is_unrestricted_and_duplicate_tenants_normalize(self):
        unrestricted = {
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": [],
            "issuer_tenants": {},
            "revoked_key_ids": [],
            "revoked_proof_hashes": [],
            "maximum_lifetime_ms": 1000,
            "maximum_review_age_ms": 1000,
        }
        self.assertIsNone(verifier_arguments(unrestricted)["allowed_issuers"])
        duplicated = {
            **unrestricted,
            "allowed_issuers": ["issuer-a"],
            "issuer_tenants": {"issuer-a": ["tenant-b", "tenant-a", "tenant-a"]},
        }
        normalized = normalize_evaluation_trust_policy(duplicated)
        self.assertEqual(normalized["issuer_tenants"]["issuer-a"], ["tenant-a", "tenant-b"])

    def test_review_receipt_age_boundary_and_negative_time(self):
        reviewer = "sha256:" + "e" * 64
        for reviewed_at, decision, blocker in (
            (NOW - 604_800_000, "allow", None),
            (NOW + 1, "block", "disagreement_review_receipt_stale"),
            (-1, "block", "disagreement_review_receipt_stale"),
        ):
            with self.subTest(reviewed_at=reviewed_at):
                candidate = request()
                candidate["evaluation_quality_proof"] = signed_quality_proof(
                    candidate, disagreement="reviewed",
                    reviewer_identity_digest=reviewer,
                    reviewed_at_unix_ms=reviewed_at,
                )
                result = execute_release_decision(
                    candidate, gateway=gateway(), key_resolver=lambda _: KEY,
                    now_unix_ms=NOW,
                )
                self.assertEqual(result["a3_consumption"]["display_decision"], decision)
                if blocker:
                    self.assertIn(blocker, result["release_gate"]["blocking_reasons"])

    def test_boolean_review_timestamp_is_not_accepted_as_an_integer(self):
        candidate = request()
        candidate["evaluation_quality_proof"] = signed_quality_proof(
            candidate,
            disagreement="reviewed",
            reviewer_identity_digest="sha256:" + "e" * 64,
            reviewed_at_unix_ms=True,
        )
        result = execute_release_decision(
            candidate, gateway=gateway(), key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
        )
        self.assertEqual(result["a3_consumption"]["display_decision"], "block")
        self.assertIn(
            "disagreement_review_receipt_invalid",
            result["release_gate"]["blocking_reasons"],
        )

    def test_revoked_key_identifier_boundaries(self):
        base = {
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": [],
            "issuer_tenants": {},
            "revoked_key_ids": [],
            "revoked_proof_hashes": [],
            "maximum_lifetime_ms": 1000,
            "maximum_review_age_ms": 1000,
        }
        for key_id in ("a", "a" * 128):
            with self.subTest(length=len(key_id)):
                candidate = {**base, "revoked_key_ids": [key_id]}
                self.assertEqual(
                    normalize_evaluation_trust_policy(candidate)["revoked_key_ids"],
                    [key_id],
                )
        for key_id in ("a" * 129, "-leading"):
            with self.subTest(key_id=key_id[:12]):
                with self.assertRaisesRegex(ValueError, "key ids"):
                    normalize_evaluation_trust_policy(
                        {**base, "revoked_key_ids": [key_id]}
                    )
    def test_issuer_tenant_authorization_fails_closed(self):
        result = execute_release_decision(
            request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
            quality_allowed_issuers=frozenset({"a2-calibration-service"}),
            quality_issuer_tenants={"a2-calibration-service": frozenset({"tenant-b"})},
        )
        self.assertEqual(result["a3_consumption"]["display_decision"], "block")
        self.assertIn(
            "quality_proof_issuer_tenant_unauthorized",
            result["release_gate"]["blocking_reasons"],
        )

    def test_malformed_ed25519_material_fails_closed(self):
        for public_key, signature in ((b"short", "00" * 64), (b"x" * 32, "not-hex")):
            with self.subTest(signature=signature):
                candidate = request()
                proof = signed_quality_proof(candidate, algorithm="ed25519", key_id="ed-key")
                proof["signature"] = signature
                candidate["evaluation_quality_proof"] = proof
                result = execute_release_decision(
                    candidate, gateway=gateway(),
                    key_resolver=lambda key_id: public_key if key_id == "ed-key" else KEY,
                    now_unix_ms=NOW,
                )
                self.assertIn(
                    "quality_proof_signature_mismatch",
                    result["release_gate"]["blocking_reasons"],
                )

    def test_disagreement_reviewer_receipt_is_strict_and_public_safe(self):
        valid_digest = "sha256:" + "e" * 64
        cases = (
            (
                {"disagreement": "reviewed", "reviewer_identity_digest": valid_digest,
                 "reviewed_at_unix_ms": NOW - 1000},
                "allow", None,
            ),
            (
                {"disagreement": "reviewed"},
                "block", "disagreement_review_receipt_invalid",
            ),
            (
                {"disagreement": "reviewed", "reviewer_identity_digest": valid_digest,
                 "reviewed_at_unix_ms": NOW - 604_800_001},
                "block", "disagreement_review_receipt_stale",
            ),
            (
                {"reviewer_identity_digest": valid_digest, "reviewed_at_unix_ms": NOW - 1000},
                "block", "disagreement_review_receipt_unexpected",
            ),
        )
        for overrides, decision, blocker in cases:
            with self.subTest(blocker=blocker):
                candidate = request()
                candidate["evaluation_quality_proof"] = signed_quality_proof(candidate, **overrides)
                result = execute_release_decision(
                    candidate, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                )
                self.assertEqual(result["a3_consumption"]["display_decision"], decision)
                if blocker:
                    self.assertIn(blocker, result["release_gate"]["blocking_reasons"])
                else:
                    quality = result["release_gate"]["evaluation_quality"]
                    self.assertEqual(quality["reviewer_identity_digest"], valid_digest)
                    self.assertEqual(quality["reviewed_at_unix_ms"], NOW - 1000)
                    self.assertNotIn("reviewer_email", json.dumps(result))

    def test_versioned_trust_policy_hash_is_replay_provenance(self):
        policy = {
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": ["a2-calibration-service"],
            "issuer_tenants": {"a2-calibration-service": ["tenant-a"]},
            "revoked_key_ids": [],
            "revoked_proof_hashes": [],
            "maximum_lifetime_ms": 86_400_000,
            "maximum_review_age_ms": 604_800_000,
        }
        result = execute_release_decision(
            request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
            quality_trust_policy=policy,
        )
        policy_hash = result["metadata"]["evaluation_trust_policy_hash"]
        self.assertRegex(policy_hash, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            result["decision_ledger"]["records"][0]["policy_hash"],
            stable_hash({
                "policy_version": "a2.semantic_release_policy.v1",
                "required_modalities": ["text"],
                "evaluation_quality": result["release_gate"]["evaluation_quality"],
                "evaluation_trust_policy_hash": policy_hash,
            }),
        )

    def test_ed25519_quality_proof_is_verified(self):
        candidate = request()
        private_key = Ed25519PrivateKey.generate()
        proof = signed_quality_proof(candidate)
        proof["algorithm"] = "ed25519"
        proof["key_id"] = "quality-ed25519-key-1"
        proof.pop("signature")
        proof["signature"] = private_key.sign(canonical(proof)).hex()
        candidate["evaluation_quality_proof"] = proof
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        result = execute_release_decision(
            candidate,
            gateway=gateway(),
            key_resolver=lambda key_id: public_key if key_id == "quality-ed25519-key-1" else KEY,
            now_unix_ms=NOW,
            quality_allowed_issuers=frozenset({"a2-calibration-service"}),
        )

        self.assertEqual(result["a3_consumption"]["display_decision"], "allow")
        self.assertEqual(result["release_gate"]["evaluation_quality"]["proof_status"], "verified")

    def test_quality_proof_trust_policy_revocations_fail_closed(self):
        candidate = request()
        cases = (
            (
                {"quality_allowed_issuers": frozenset({"different-issuer"})},
                "quality_proof_issuer_unauthorized",
            ),
            (
                {"quality_revoked_key_ids": frozenset({"key-1"})},
                "quality_proof_key_revoked",
            ),
            (
                {"quality_maximum_lifetime_ms": 100},
                "quality_proof_lifetime_exceeded",
            ),
        )
        for kwargs, blocker in cases:
            with self.subTest(blocker=blocker):
                result = execute_release_decision(
                    candidate,
                    gateway=gateway(),
                    key_resolver=lambda _: KEY,
                    now_unix_ms=NOW,
                    **kwargs,
                )
                self.assertEqual(result["a3_consumption"]["display_decision"], "block")
                self.assertIn(blocker, result["release_gate"]["blocking_reasons"])

    def test_quality_proof_hash_revocation_fails_closed(self):
        candidate = request()
        proof = candidate["evaluation_quality_proof"]
        signed_fields = {key: proof[key] for key in sorted(set(proof) - {"signature"})}
        proof_hash = "sha256:" + digest(canonical(signed_fields))
        result = execute_release_decision(
            candidate,
            gateway=gateway(),
            key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
            quality_revoked_proof_hashes=frozenset({proof_hash}),
        )
        self.assertEqual(result["a3_consumption"]["display_decision"], "block")
        self.assertIn("quality_proof_revoked", result["release_gate"]["blocking_reasons"])

    def test_quality_proof_is_bound_to_rubric_golden_data_and_thresholds(self):
        for field, value in (
            ("rubric_version", "rubric.v2"),
            ("golden_dataset_digest", "sha256:" + "e" * 64),
            ("calibration_thresholds_hash", "sha256:" + "f" * 64),
        ):
            with self.subTest(field=field):
                candidate = request()
                candidate[field] = value
                result = execute_release_decision(
                    candidate,
                    gateway=gateway(),
                    key_resolver=lambda _: KEY,
                    now_unix_ms=NOW,
                )
                self.assertEqual(result["a3_consumption"]["display_decision"], "block")
                self.assertIn(
                    "quality_proof_binding_mismatch",
                    result["release_gate"]["blocking_reasons"],
                )

    def test_multimodal_ocr_reaches_decision_with_grounded_private_disclosure(self):
        pipeline, evidence = image_pipeline_and_evidence()
        original = request()
        original.update(
            {
                "required_modalities": ["text", "image"],
                "artifact_pipeline_records": [pipeline],
                "derived_evidence_records": [evidence],
            }
        )
        original["evaluation_quality_proof"] = signed_quality_proof(original)
        adapter = GroundedRecordingAdapter()
        provider = ProviderDefinition(
            "unit", "recording", "local", "", frozenset({"text"}),
            frozenset({"tenant-a"}), data_residency="local",
        )
        result = execute_release_decision(
            original,
            gateway=ProviderGateway(
                [provider],
                {"recording": adapter},
                response_validator=validate_semantic_judge_output,
            ),
            key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
        )

        self.assertEqual(result["evidence_snapshot"]["completeness"], "complete")
        self.assertEqual(result["evidence_snapshot"]["artifact_modalities"], ["image"])
        self.assertEqual(result["evidence_snapshot"]["observed_modalities"], ["image", "text"])
        self.assertEqual(result["a3_consumption"]["display_decision"], "allow")
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(adapter.payloads[0]["parts"][1]["text"], "RELEASE BLOCKED")
        serialized = json.dumps(result, sort_keys=True)
        self.assertNotIn("RELEASE BLOCKED", serialized)
        self.assertNotIn('"text":', json.dumps(result["evidence_snapshot"]["derived_evidence"]))

    def test_nonproduction_ocr_blocks_before_provider_call(self):
        pipeline, evidence = image_pipeline_and_evidence(production_qualified=False)
        original = request()
        original.update(
            {
                "required_modalities": ["text", "image"],
                "artifact_pipeline_records": [pipeline],
                "derived_evidence_records": [evidence],
            }
        )
        provider_gateway = gateway()
        result = execute_release_decision(
            original,
            gateway=provider_gateway,
            key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
        )
        self.assertEqual(result["a3_consumption"]["display_decision"], "block")
        self.assertEqual(provider_gateway.adapters["fake"].calls, 0)
        self.assertIn(
            "derived_evidence_0_ocr_runtime_not_production_qualified",
            result["release_gate"]["blocking_reasons"],
        )

    def test_ungrounded_provider_citation_cannot_allow_release(self):
        response = {
            "output_text": json.dumps(
                {
                    "passed": True,
                    "score": 1,
                    "reason": "unsupported assertion",
                    "failure_classes": [],
                    "evidence_refs": [stable_hash("invented-evidence")],
                    "abstained": False,
                }
            ),
            "usage": {},
        }
        result = execute_release_decision(
            request(),
            gateway=gateway(response),
            key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
        )
        self.assertEqual(result["a3_consumption"]["display_decision"], "block")
        self.assertIn(
            "semantic_evidence_ref_ungrounded",
            result["release_gate"]["blocking_reasons"],
        )

    def test_multimodal_snapshot_only_citation_cannot_allow_release(self):
        pipeline, evidence = image_pipeline_and_evidence()
        original = request()
        original.update(
            {
                "required_modalities": ["text", "image"],
                "artifact_pipeline_records": [pipeline],
                "derived_evidence_records": [evidence],
            }
        )
        result = execute_release_decision(
            original,
            gateway=gateway(),
            key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
        )
        self.assertEqual(result["a3_consumption"]["display_decision"], "block")
        self.assertIn(
            "semantic_derived_evidence_ref_missing",
            result["release_gate"]["blocking_reasons"],
        )

    def test_undisclosed_multimodal_evidence_cannot_be_cited(self):
        pipeline, evidence = image_pipeline_and_evidence(disclosure=False)
        citation = evidence["blocks"][0]["citation_id"]
        response = {
            "output_text": json.dumps(
                {
                    "passed": True,
                    "score": 1,
                    "reason": "claims unseen OCR",
                    "failure_classes": [],
                    "evidence_refs": [citation],
                    "abstained": False,
                }
            ),
            "usage": {},
        }
        original = request()
        original.update(
            {
                "required_modalities": ["text", "image"],
                "artifact_pipeline_records": [pipeline],
                "derived_evidence_records": [evidence],
            }
        )
        result = execute_release_decision(
            original,
            gateway=gateway(response),
            key_resolver=lambda _: KEY,
            now_unix_ms=NOW,
        )
        self.assertEqual(result["a3_consumption"]["display_decision"], "block")
        self.assertIn(
            "semantic_evidence_ref_ungrounded",
            result["release_gate"]["blocking_reasons"],
        )

    def test_authenticated_normal_path_produces_allow_ledger_and_a3_handoff(self):
        original_request = request()
        original_json = json.dumps(original_request, sort_keys=True)
        provider_gateway = gateway()
        result = execute_release_decision(
            original_request, gateway=provider_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW
        )
        repeated = execute_release_decision(
            original_request, gateway=provider_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW
        )
        record = result["decision_ledger"]["records"][0]
        self.assertEqual(result, repeated)
        self.assertEqual(json.dumps(original_request, sort_keys=True), original_json)
        self.assertEqual(record["decision"], "allow")
        self.assertEqual(result["release_gate"]["decision"], "pass")
        self.assertFalse(result["a3_consumption"]["release_ready"])
        self.assertEqual(result["metadata"]["persistence_status"], "not_configured")
        self.assertFalse(result["a3_consumption"]["may_recompute_grade"])
        self.assertEqual(record["provider_summary"]["call_count"], 1)
        self.assertFalse(result["metadata"]["raw_evidence_included"])

    def test_provider_failure_or_invalid_json_cannot_become_pass(self):
        for candidate in (
            gateway(failure="timeout"),
            gateway({"output_text": "not-json", "usage": {}}),
        ):
            result = execute_release_decision(request(), gateway=candidate, key_resolver=lambda _: KEY, now_unix_ms=NOW)
            self.assertEqual(result["decision_ledger"]["records"][0]["decision"], "block")
            self.assertEqual(result["release_gate"]["decision"], "block")
            self.assertFalse(result["a3_consumption"]["release_ready"])

    def test_abstention_requires_review(self):
        response = {
            "output_text": json.dumps(
                {
                    "passed": False,
                    "score": 0.5,
                    "reason": "ambiguous evidence",
                    "failure_classes": [],
                    "evidence_refs": ["snapshot"],
                    "abstained": True,
                }
            ),
            "usage": {},
        }
        result = execute_release_decision(request(), gateway=gateway(response), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision_ledger"]["records"][0]["decision"], "review")
        self.assertTrue(result["a3_consumption"]["review_required"])

    def test_tampered_bundle_missing_modality_and_audit_failure_fail_closed(self):
        tampered = signed_bundle()
        tampered["evidence"][0]["run_id"] = "tampered"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            execute_release_decision(request(tampered), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)

        missing = request()
        missing["required_modalities"] = ["text", "image"]
        result = execute_release_decision(missing, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision_ledger"]["records"][0]["decision"], "block")
        self.assertIn("image", result["release_gate"]["blocking_reasons"])

        def broken_audit(_):
            raise OSError("ledger unavailable")

        result = execute_release_decision(
            request(), gateway=gateway(audit_writer=broken_audit), key_resolver=lambda _: KEY, now_unix_ms=NOW
        )
        self.assertEqual(result["decision_ledger"]["records"][0]["decision"], "block")
        self.assertIn("audit_write_failed", result["release_gate"]["blocking_reasons"])

    def test_cross_tenant_bundle_is_rejected(self):
        cross = request()
        cross["tenant_id"] = "tenant-b"
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            execute_release_decision(cross, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)

    def test_atomic_commit_is_required_before_a3_can_release(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            result = execute_release_decision(
                request(),
                gateway=gateway(),
                key_resolver=lambda _: KEY,
                now_unix_ms=NOW,
                persistence_connection=connection,
            )
            repeated = execute_release_decision(
                request(),
                gateway=gateway(),
                key_resolver=lambda _: KEY,
                now_unix_ms=NOW,
                persistence_connection=connection,
            )
            self.assertTrue(result["a3_consumption"]["release_ready"])
            self.assertTrue(result["persistence"]["committed"])
            self.assertFalse(result["persistence"]["idempotent_replay"])
            self.assertTrue(repeated["persistence"]["idempotent_replay"])
            self.assertEqual(_count(connection, "a2_release_decisions"), 1)
            self.assertEqual(_count(connection, "a2_release_decision_audit"), 1)
            self.assertEqual(_count(connection, "a2_decision_operations"), 1)
            self.assertEqual(_count(connection, "a2_decision_operation_audit"), 4)
            self.assertEqual(_count(connection, "a2_provider_outcomes"), 1)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 1)
        finally:
            connection.close()

    def test_durable_retry_after_worker_restart_does_not_call_provider_again(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            first_gateway = gateway()
            first = execute_release_decision(
                request(), gateway=first_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            second_gateway = gateway()
            replay = execute_release_decision(
                request(), gateway=second_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            self.assertEqual(first_gateway.adapters["fake"].calls, 1)
            self.assertEqual(second_gateway.adapters["fake"].calls, 0)
            self.assertTrue(replay["persistence"]["idempotent_replay"])
            self.assertEqual(replay["persistence"]["record_hash"], first["persistence"]["record_hash"])
            self.assertTrue(replay["a3_consumption"]["release_ready"])
        finally:
            connection.close()

    def test_provider_completed_crash_recovers_without_second_provider_call(self):
        crashed = sqlite3.connect(":memory:")
        normal = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(crashed)
            initialize_sql_store(normal)
            provider_gateway = gateway()

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("worker crashed after provider outcome commit")

            with self.assertRaisesRegex(OSError, "after provider outcome commit"):
                execute_release_decision(
                    request(), gateway=provider_gateway, key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=crashed,
                    persistence_failure_injector=fail,
                )
            operation_id, status = crashed.execute(
                "SELECT operation_id, status FROM a2_decision_operations"
            ).fetchone()
            self.assertEqual(status, "provider_completed")
            self.assertEqual(provider_gateway.adapters["fake"].calls, 1)

            recovered = recover_release_decision(
                crashed,
                operation_id=operation_id,
                scope={
                    "organization_id": "org-a",
                    "tenant_id": "tenant-a",
                    "workspace_id": "workspace-a",
                    "project_id": "project-a",
                    "environment_id": "test",
                },
                now="2026-07-12T00:00:01Z",
            )
            expected = execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY,
                now_unix_ms=NOW, persistence_connection=normal,
            )
            self.assertEqual(provider_gateway.adapters["fake"].calls, 1)
            self.assertEqual(
                recovered["persistence"]["record_hash"],
                expected["persistence"]["record_hash"],
            )
            self.assertEqual(
                recovered["decision_ledger"]["ledger_hash"],
                expected["decision_ledger"]["ledger_hash"],
            )
            self.assertEqual(_count(crashed, "a2_release_decisions"), 1)
            self.assertEqual(_count(crashed, "a2_decision_outbox"), 1)
            with self.assertRaisesRegex(ValueError, "cannot claim status committed"):
                recover_release_decision(
                    crashed,
                    operation_id=operation_id,
                    scope={
                        "organization_id": "org-a", "tenant_id": "tenant-a",
                        "workspace_id": "workspace-a", "project_id": "project-a",
                        "environment_id": "test",
                    },
                    now="2026-07-12T00:00:02Z",
                )
        finally:
            crashed.close()
            normal.close()

    def test_provider_completed_recovery_preserves_normalized_duplicate_policy(self):
        connection = sqlite3.connect(":memory:")
        duplicate_policy = {
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": [
                "a2-calibration-service", "a2-calibration-service",
            ],
            "issuer_tenants": {
                "a2-calibration-service": ["tenant-a", "tenant-a"],
            },
            "revoked_key_ids": [],
            "revoked_proof_hashes": [],
            "maximum_lifetime_ms": 86_400_000,
            "maximum_review_age_ms": 604_800_000,
        }
        try:
            initialize_sql_store(connection)
            provider_gateway = gateway()

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("normalized-policy recovery boundary")

            with self.assertRaisesRegex(OSError, "normalized-policy"):
                execute_release_decision(
                    request(), gateway=provider_gateway, key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                    persistence_failure_injector=fail,
                    quality_trust_policy=duplicate_policy,
                )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            recovered = recover_release_decision(
                connection,
                operation_id=operation_id,
                scope={key: request()[key] for key in (
                    "organization_id", "tenant_id", "workspace_id",
                    "project_id", "environment_id",
                )},
                now="2026-07-12T00:00:01Z",
            )
            self.assertEqual(
                recovered["metadata"]["evaluation_trust_policy_hash"],
                stable_hash(normalize_evaluation_trust_policy(duplicate_policy)),
            )
            self.assertTrue(recovered["persistence"]["committed"])
            self.assertEqual(provider_gateway.adapters["fake"].calls, 1)
            self.assertEqual(_count(connection, "a2_release_decisions"), 1)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 1)
        finally:
            connection.close()

    def test_recovery_envelope_tamper_and_active_lease_fail_closed(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("stop")

            with self.assertRaises(OSError):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                    persistence_failure_injector=fail,
                )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            scope = {
                "organization_id": "org-a", "tenant_id": "tenant-a",
                "workspace_id": "workspace-a", "project_id": "project-a",
                "environment_id": "test",
            }
            first = claim_decision_recovery(
                connection, operation_id=operation_id, scope=scope,
                worker_id="worker-1", now="2026-07-12T00:00:01Z", lease_seconds=60,
            )
            self.assertEqual(first["recovery_generation"], 1)
            with self.assertRaisesRegex(ValueError, "lease contention"):
                claim_decision_recovery(
                    connection, operation_id=operation_id, scope=scope,
                    worker_id="worker-2", now="2026-07-12T00:00:02Z", lease_seconds=60,
                )
            raw = connection.execute(
                "SELECT recovery_envelope_json FROM a2_provider_outcomes"
            ).fetchone()[0]
            envelope = json.loads(raw)
            envelope["reason"] = "Bearer secret"
            connection.execute(
                "UPDATE a2_provider_outcomes SET recovery_envelope_json = ?, "
                "recovery_envelope_hash = ?",
                (
                    json.dumps(envelope, sort_keys=True, separators=(",", ":")),
                    stable_hash(envelope),
                ),
            )
            connection.commit()
            with self.assertRaisesRegex(ValueError, "fields do not match"):
                load_decision_recovery_envelope(
                    connection, operation_id=operation_id, scope=scope,
                )
        finally:
            connection.close()

    def test_recovery_envelope_rejects_inconsistent_citation_states(self):
        for status, blockers, semantic_present, message in (
            ("grounded", ["unexpected"], True, "grounded recovery citations"),
            ("invalid", [], True, "invalid recovery citations"),
            ("not_available", [], True, "inconsistent with semantic output"),
            ("grounded", [], False, "absent semantic output"),
        ):
            connection = sqlite3.connect(":memory:")
            try:
                initialize_sql_store(connection)

                def fail(point):
                    if point == "after_provider_outcome_committed":
                        raise OSError("stop")

                with self.assertRaises(OSError):
                    execute_release_decision(
                        request(), gateway=gateway(), key_resolver=lambda _: KEY,
                        now_unix_ms=NOW, persistence_connection=connection,
                        persistence_failure_injector=fail,
                    )
                operation_id = connection.execute(
                    "SELECT operation_id FROM a2_decision_operations"
                ).fetchone()[0]
                scope = {
                    "organization_id": "org-a", "tenant_id": "tenant-a",
                    "workspace_id": "workspace-a", "project_id": "project-a",
                    "environment_id": "test",
                }
                raw = connection.execute(
                    "SELECT recovery_envelope_json FROM a2_provider_outcomes"
                ).fetchone()[0]
                envelope = json.loads(raw)
                envelope["citation_validation"]["status"] = status
                envelope["citation_validation"]["blockers"] = blockers
                if not semantic_present:
                    envelope["semantic_output"] = None
                    envelope["citation_validation"]["reference_hashes"] = []
                connection.execute(
                    "UPDATE a2_provider_outcomes SET recovery_envelope_json = ?, "
                    "recovery_envelope_hash = ?",
                    (
                        json.dumps(envelope, sort_keys=True, separators=(",", ":")),
                        stable_hash(envelope),
                    ),
                )
                connection.commit()
                with self.assertRaisesRegex(ValueError, message):
                    load_decision_recovery_envelope(
                        connection, operation_id=operation_id, scope=scope,
                    )
            finally:
                connection.close()

    def test_recovery_envelope_rejects_invalid_quality_evidence_digest(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("stop")

            with self.assertRaises(OSError):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                    persistence_failure_injector=fail,
                )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            scope = {
                "organization_id": "org-a", "tenant_id": "tenant-a",
                "workspace_id": "workspace-a", "project_id": "project-a",
                "environment_id": "test",
            }
            raw = connection.execute(
                "SELECT recovery_envelope_json FROM a2_provider_outcomes"
            ).fetchone()[0]
            envelope = json.loads(raw)
            envelope["evaluation_quality"]["evidence_refs"] = ["sha256:not-a-digest"]
            connection.execute(
                "UPDATE a2_provider_outcomes SET recovery_envelope_json = ?, "
                "recovery_envelope_hash = ?",
                (
                    json.dumps(envelope, sort_keys=True, separators=(",", ":")),
                    stable_hash(envelope),
                ),
            )
            connection.commit()
            with self.assertRaisesRegex(ValueError, "quality evidence refs"):
                load_decision_recovery_envelope(
                    connection, operation_id=operation_id, scope=scope,

                )
        finally:
            connection.close()

    def test_legacy_quality_recovery_requires_explicit_safe_migration(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("stop")

            with self.assertRaises(OSError):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                    persistence_failure_injector=fail,
                )
            raw = connection.execute(
                "SELECT recovery_envelope_json FROM a2_provider_outcomes"
            ).fetchone()[0]
            envelope = json.loads(raw)
            envelope["evaluation_quality"]["schema_version"] = "a2.evaluation_quality.v1"
            envelope["evaluation_quality"].pop("reviewer_identity_digest")
            envelope["evaluation_quality"].pop("reviewed_at_unix_ms")
            migrated = migrate_evaluation_quality_v1_recovery_envelope(
                envelope,
                evaluation_trust_policy_hash=envelope["evaluation_trust_policy_hash"],
            )
            self.assertEqual(
                migrated["evaluation_quality"]["schema_version"],
                "a2.evaluation_quality.v2",
            )
            self.assertEqual(migrated["evaluation_quality"]["reviewer_identity_digest"], "")
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            migrated["provider_outcome_hash"] = connection.execute(
                "SELECT outcome_hash FROM a2_provider_outcomes"
            ).fetchone()[0]
            connection.execute(
                "UPDATE a2_provider_outcomes SET recovery_envelope_json = ?, "
                "recovery_envelope_hash = ?",
                (
                    json.dumps(migrated, sort_keys=True, separators=(",", ":")),
                    stable_hash(migrated),
                ),
            )
            connection.commit()
            loaded = load_decision_recovery_envelope(
                connection, operation_id=operation_id,
                scope={field: request()[field] for field in (
                    "organization_id", "tenant_id", "workspace_id",
                    "project_id", "environment_id",
                )},
            )
            self.assertEqual(loaded["evaluation_quality"]["schema_version"], "a2.evaluation_quality.v2")
            self.assertEqual(loaded["evaluation_quality"]["disagreement"], "agree")
            disagree = json.loads(json.dumps(envelope))
            disagree["evaluation_quality"]["disagreement"] = "disagree"
            disagree["evaluation_quality"]["human_review_required"] = True
            disagree["evaluation_quality"]["blockers"] = ["disagreement_requires_review"]
            migrated_disagree = migrate_evaluation_quality_v1_recovery_envelope(
                disagree,
                evaluation_trust_policy_hash=envelope["evaluation_trust_policy_hash"],
            )
            self.assertTrue(migrated_disagree["evaluation_quality"]["human_review_required"])
            self.assertIn(
                "disagreement_requires_review",
                migrated_disagree["evaluation_quality"]["blockers"],
            )
            reviewed = json.loads(json.dumps(envelope))
            reviewed["evaluation_quality"]["disagreement"] = "reviewed"
            with self.assertRaisesRegex(ValueError, "reviewer receipt"):
                migrate_evaluation_quality_v1_recovery_envelope(
                    reviewed,
                    evaluation_trust_policy_hash=envelope["evaluation_trust_policy_hash"],
                )
        finally:
            connection.close()

    def test_recovery_rejects_invalid_trust_policy_hash(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("stop")

            with self.assertRaises(OSError):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                    persistence_failure_injector=fail,
                )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            envelope = json.loads(connection.execute(
                "SELECT recovery_envelope_json FROM a2_provider_outcomes"
            ).fetchone()[0])
            envelope["evaluation_trust_policy_hash"] = "sha256:not-canonical"
            connection.execute(
                "UPDATE a2_provider_outcomes SET recovery_envelope_json = ?, "
                "recovery_envelope_hash = ?",
                (json.dumps(envelope, sort_keys=True, separators=(",", ":")), stable_hash(envelope)),
            )
            connection.commit()
            with self.assertRaisesRegex(ValueError, "trust policy hash"):
                load_decision_recovery_envelope(
                    connection, operation_id=operation_id,
                    scope={field: request()[field] for field in (
                        "organization_id", "tenant_id", "workspace_id",
                        "project_id", "environment_id",
                    )},
                )
        finally:
            connection.close()

    def test_recovery_rejects_tampered_normalized_trust_policy_hash(self):
        connection = sqlite3.connect(":memory:")
        policy = {
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": [
                "a2-calibration-service", "a2-calibration-service",
            ],
            "issuer_tenants": {
                "a2-calibration-service": ["tenant-a", "tenant-a"],
            },
            "revoked_key_ids": [],
            "revoked_proof_hashes": [],
            "maximum_lifetime_ms": 86_400_000,
            "maximum_review_age_ms": 604_800_000,
        }
        try:
            initialize_sql_store(connection)

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("stop")

            with self.assertRaises(OSError):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                    persistence_failure_injector=fail,
                    quality_trust_policy=policy,
                )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            envelope = json.loads(connection.execute(
                "SELECT recovery_envelope_json FROM a2_provider_outcomes"
            ).fetchone()[0])
            expected_hash = stable_hash(normalize_evaluation_trust_policy(policy))
            self.assertEqual(envelope["evaluation_trust_policy_hash"], expected_hash)
            envelope["evaluation_trust_policy_hash"] = "sha256:" + "f" * 64
            connection.execute(
                "UPDATE a2_provider_outcomes SET recovery_envelope_json = ?, "
                "recovery_envelope_hash = ?",
                (
                    json.dumps(envelope, sort_keys=True, separators=(",", ":")),
                    stable_hash(envelope),
                ),
            )
            connection.commit()
            with self.assertRaisesRegex(
                IdempotencyConflictError, "input changed before commit"
            ):
                load_decision_recovery_envelope(
                    connection,
                    operation_id=operation_id,
                    scope={field: request()[field] for field in (
                        "organization_id", "tenant_id", "workspace_id",
                        "project_id", "environment_id",
                    )},
                )
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 0)
        finally:
            connection.close()

    def test_interrupted_provider_call_requires_recovery_and_is_not_replayed(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            provider = ProviderDefinition(
                "unit", "interrupt", "local", "", frozenset({"text"}), frozenset({"tenant-a"}),
                data_residency="local",
            )
            interrupted = ProcessInterruptedAdapter()
            interrupted_gateway = ProviderGateway(
                [provider],
                {"interrupt": interrupted},
                audit_writer=lambda _: None,
                response_validator=validate_semantic_judge_output,
            )
            with self.assertRaises(KeyboardInterrupt):
                execute_release_decision(
                    request(), gateway=interrupted_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection,
                )
            retry_gateway = gateway()
            recovery = execute_release_decision(
                request(), gateway=retry_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            status = connection.execute(
                "SELECT status FROM a2_decision_operations"
            ).fetchone()[0]
            self.assertEqual(interrupted.calls, 1)
            self.assertEqual(retry_gateway.adapters["fake"].calls, 0)
            self.assertEqual(status, "recovery_required")
            self.assertEqual(recovery["metadata"]["persistence_status"], "recovery_required")
            self.assertTrue(recovery["a3_consumption"]["review_required"])
            self.assertFalse(recovery["a3_consumption"]["release_ready"])
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
        finally:
            connection.close()

    def test_active_reservation_replay_stays_in_progress_without_provider_call(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            scope = {
                "organization_id": "org-a",
                "tenant_id": "tenant-a",
                "workspace_id": "workspace-a",
                "project_id": "project-a",
                "environment_id": "test",
            }
            first = reserve_decision_operation(
                connection,
                scope=scope,
                idempotency_key="abandoned",
                request_hash="sha256:request",
                snapshot_id="sha256:snapshot-id",
                snapshot_hash="sha256:snapshot",
                provider_id="unit",
                model_id="semantic-1",
                created_at="2026-07-12T00:00:00Z",
            )
            replay = reserve_decision_operation(
                connection,
                scope=scope,
                idempotency_key="abandoned",
                request_hash="sha256:request",
                snapshot_id="sha256:snapshot-id",
                snapshot_hash="sha256:snapshot",
                provider_id="unit",
                model_id="semantic-1",
                created_at="2026-07-12T00:01:00Z",
            )
            self.assertEqual(first["status"], "reserved")
            self.assertEqual(replay["status"], "reserved")
            self.assertFalse(replay["provider_call_allowed"])
            self.assertEqual(
                connection.execute("SELECT status FROM a2_decision_operations").fetchone()[0],
                "reserved",
            )
            self.assertEqual(_count(connection, "a2_decision_operation_audit"), 1)
        finally:
            connection.close()

    def test_reservation_failure_prevents_provider_invocation(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            provider_gateway = gateway()
            with patch(
                "services.judge.release_decision_orchestrator.reserve_decision_operation",
                side_effect=sqlite3.OperationalError("reservation unavailable"),
            ):
                with self.assertRaisesRegex(sqlite3.OperationalError, "reservation unavailable"):
                    execute_release_decision(
                        request(), gateway=provider_gateway, key_resolver=lambda _: KEY,
                        now_unix_ms=NOW, persistence_connection=connection,
                    )
            self.assertEqual(provider_gateway.adapters["fake"].calls, 0)
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_decision_operations"), 0)
        finally:
            connection.close()

    def test_write_or_audit_failure_rolls_back_everything(self):
        for failure_step in ("after_decision", "after_audit"):
            connection = sqlite3.connect(":memory:")
            try:
                initialize_sql_store(connection)

                def fail(step):
                    if step == failure_step:
                        raise OSError("injected persistence failure")

                with self.assertRaisesRegex(OSError, "injected"):
                    execute_release_decision(
                        request(),
                        gateway=gateway(),
                        key_resolver=lambda _: KEY,
                        now_unix_ms=NOW,
                        persistence_connection=connection,
                        persistence_failure_injector=fail,
                    )
                self.assertEqual(_count(connection, "a2_release_decisions"), 0)
                self.assertEqual(_count(connection, "a2_release_decision_audit"), 0)
            finally:
                connection.close()

    def test_provider_outcome_failure_cannot_commit_decision(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(step):
                if step == "after_provider_outcome":
                    raise OSError("injected provider outcome failure")

            with self.assertRaisesRegex(OSError, "provider outcome"):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection, persistence_failure_injector=fail,
                )
            self.assertEqual(_count(connection, "a2_provider_outcomes"), 0)
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 0)
            self.assertEqual(
                connection.execute("SELECT status FROM a2_decision_operations").fetchone()[0],
                "provider_running",
            )
        finally:
            connection.close()

    def test_recovery_envelope_lookup_is_bound_to_full_scope(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            wrong_scope = {
                "organization_id": "org-a", "tenant_id": "tenant-a",
                "workspace_id": "workspace-other", "project_id": "project-a",
                "environment_id": "test",
            }
            with self.assertRaisesRegex(ValueError, "binding mismatch"):
                load_decision_recovery_envelope(
                    connection, operation_id=operation_id, scope=wrong_scope,
                )
        finally:
            connection.close()

    def test_expired_recovery_lease_cannot_commit(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(point):
                if point == "after_provider_outcome_committed":
                    raise OSError("crash")

            with self.assertRaises(OSError):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection, persistence_failure_injector=fail,
                )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            scope = {key: request()[key] for key in (
                "organization_id", "tenant_id", "workspace_id", "project_id", "environment_id",
            )}
            lease = claim_decision_recovery(
                connection, operation_id=operation_id, scope=scope, worker_id="expired-worker",
                now="2026-07-12T00:00:00Z", lease_seconds=1,
            )
            envelope = load_decision_recovery_envelope(
                connection, operation_id=operation_id, scope=scope,
            )
            from services.judge.release_decision_orchestrator import _build_decision_result
            with self.assertRaisesRegex(ValueError, "recovery lease expired"):
                persist_release_decision(
                    connection, _build_decision_result(envelope),
                    idempotency_key=envelope["idempotency_key"],
                    request_hash=envelope["request_hash"], operation_id=operation_id,
                    lease=lease, commit_now="2026-07-12T00:00:02Z",
                )
        finally:
            connection.close()

    def test_outbox_failure_rolls_back_decision_operation_and_audit(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)

            def fail(step):
                if step == "after_outbox":
                    raise OSError("injected outbox failure")

            with self.assertRaisesRegex(OSError, "outbox"):
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection, persistence_failure_injector=fail,
                )
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_release_decision_audit"), 0)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 0)
            self.assertEqual(
                connection.execute("SELECT status FROM a2_decision_operations").fetchone()[0],
                "provider_completed",
            )
        finally:
            connection.close()

    def test_expired_lease_takeover_fences_old_worker(self):
        scope = {
            "organization_id": "org-a", "tenant_id": "tenant-a", "workspace_id": "workspace-a",
            "project_id": "project-a", "environment_id": "test",
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "a2-lease.sqlite"
            first_connection = sqlite3.connect(database)
            second_connection = sqlite3.connect(database)
            try:
                initialize_sql_store(first_connection)
                operation = reserve_decision_operation(
                    first_connection, scope=scope, idempotency_key="lease-case",
                    request_hash="sha256:request", snapshot_id="snapshot",
                    snapshot_hash="sha256:snapshot", provider_id="unit", model_id="semantic-1",
                    created_at="2026-07-12T00:00:00Z",
                )
                old_lease = authorize_provider_call(
                    first_connection, operation_id=operation["operation_id"], scope=scope,
                    created_at="2026-07-12T00:00:00Z", worker_id="worker-old", lease_seconds=1,
                )
                new_lease = authorize_provider_call(
                    second_connection, operation_id=operation["operation_id"], scope=scope,
                    created_at="2026-07-12T00:00:02Z", worker_id="worker-new", lease_seconds=60,
                )
                self.assertEqual(new_lease["fencing_token"], old_lease["fencing_token"] + 1)
                with self.assertRaisesRegex(ValueError, "stale fencing token"):
                    persist_provider_outcome(
                        first_connection, operation_id=operation["operation_id"], scope=scope,
                        lease=old_lease,
                        provider_result={"provider_id": "unit", "model_id": "semantic-1", "status": "ok"},
                        semantic_output={"passed": True}, completed_at="2026-07-12T00:00:03Z",
                    )
                persist_provider_outcome(
                    second_connection, operation_id=operation["operation_id"], scope=scope,
                    lease=new_lease,
                    provider_result={"provider_id": "unit", "model_id": "semantic-1", "status": "ok"},
                    semantic_output={"passed": True}, completed_at="2026-07-12T00:00:03Z",
                )
                self.assertEqual(_count(second_connection, "a2_provider_outcomes"), 1)
            finally:
                first_connection.close()
                second_connection.close()

    def test_recovery_required_never_reauthorizes_provider_call(self):
        connection = sqlite3.connect(":memory:")
        provider_gateway = ProviderGateway(
            [ProviderDefinition(
                "unit", "fake", "local", "", frozenset({"text"}), frozenset({"tenant-a"}),
                reconciliation_mode="provider_status_lookup",
            )],
            {"fake": ProcessInterruptedAdapter()},
            response_validator=validate_semantic_judge_output,
        )
        try:
            initialize_sql_store(connection)
            with self.assertRaises(KeyboardInterrupt):
                execute_release_decision(
                    request(), gateway=provider_gateway, key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection, lease_seconds=1,
                )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            with self.assertRaisesRegex(ValueError, "recovery_required"):
                authorize_provider_call(
                    connection, operation_id=operation_id, scope=request(),
                    created_at="2026-07-12T00:00:02Z", worker_id="blind-retry",
                )
            self.assertEqual(provider_gateway.adapters["fake"].calls, 1)
        finally:
            connection.close()

    def test_pending_reconciliation_is_durable_and_release_closed(self):
        connection = sqlite3.connect(":memory:")
        interrupted = ProviderGateway(
            [ProviderDefinition(
                "unit", "fake", "local", "", frozenset({"text"}), frozenset({"tenant-a"}),
                reconciliation_mode="provider_status_lookup",
            )],
            {"fake": ProcessInterruptedAdapter()},
            response_validator=validate_semantic_judge_output,
        )
        try:
            initialize_sql_store(connection)
            with self.assertRaises(KeyboardInterrupt):
                execute_release_decision(
                    request(), gateway=interrupted, key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                )
            operation_id = connection.execute(
                "SELECT operation_id FROM a2_decision_operations"
            ).fetchone()[0]
            provider_gateway = reconciliation_gateway()
            result = reconcile_release_decision(
                request(), gateway=provider_gateway, key_resolver=lambda _: KEY,
                now_unix_ms=NOW, connection=connection, operation_id=operation_id,
                now="2026-07-12T00:00:01Z", next_reconcile_at="2026-07-12T00:01:00Z",
            )
            self.assertFalse(result["a3_consumption"]["release_ready"])
            self.assertTrue(result["a3_consumption"]["review_required"])
            self.assertFalse(result["metadata"]["retry_authorized"])
            self.assertEqual(result["metadata"]["reconciliation_status"], "remote_pending")
            self.assertEqual(_count(connection, "a2_provider_reconciliation_observations"), 1)
            self.assertEqual(_count(connection, "a2_provider_outcomes"), 0)
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            row = connection.execute(
                """SELECT status, last_reconciliation_status, reconciliation_next_at
                   FROM a2_decision_operations"""
            ).fetchone()
            self.assertEqual(row, ("recovery_required", "remote_pending", "2026-07-12T00:01:00Z"))
            self.assertEqual(provider_gateway.adapters["fake"].calls, 0)
            self.assertEqual(provider_gateway.adapters["fake"].reconciliation_calls, 1)
        finally:
            connection.close()

    def test_reconciled_completion_atomically_recovers_decision(self):
        connection = sqlite3.connect(":memory:")
        interrupted = ProviderGateway(
            [ProviderDefinition(
                "unit", "fake", "local", "", frozenset({"text"}), frozenset({"tenant-a"}),
                reconciliation_mode="provider_status_lookup",
            )],
            {"fake": ProcessInterruptedAdapter()},
            response_validator=validate_semantic_judge_output,
        )
        try:
            initialize_sql_store(connection)
            with self.assertRaises(KeyboardInterrupt):
                execute_release_decision(
                    request(), gateway=interrupted, key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                )
            operation = connection.execute(
                """SELECT operation_id, provider_call_id, fencing_token
                   FROM a2_decision_operations"""
            ).fetchone()
            provider_gateway = reconciliation_gateway("remote_completed")
            adapter = provider_gateway.adapters["fake"]
            base = adapter.reconciliation_response
            base.update(
                {
                    "provider_call_id": operation[1],
                    "logical_call_id": connection.execute(
                        "SELECT logical_call_id FROM a2_decision_operations"
                    ).fetchone()[0],
                    "provider_id": "unit", "model_id": "semantic-1",
                    "snapshot_hash": connection.execute(
                        "SELECT snapshot_hash FROM a2_decision_operations"
                    ).fetchone()[0],
                    "payload_hash": connection.execute(
                        "SELECT provider_payload_hash FROM a2_decision_operations"
                    ).fetchone()[0],
                    "idempotency_key_hash": connection.execute(
                        "SELECT provider_idempotency_key_hash FROM a2_decision_operations"
                    ).fetchone()[0],
                    "provider_endpoint_hash": connection.execute(
                        "SELECT provider_endpoint_hash FROM a2_decision_operations"
                    ).fetchone()[0],
                    "scope": {field: request()[field] for field in (
                        "organization_id", "tenant_id", "workspace_id",
                        "project_id", "environment_id",
                    )},
                    "operation_id": operation[0],
                    "provider_generation": operation[2],
                }
            )
            result = reconcile_release_decision(
                request(), gateway=provider_gateway, key_resolver=lambda _: KEY,
                now_unix_ms=NOW, connection=connection, operation_id=operation[0],
                now="2026-07-12T00:00:01Z",
            )
            self.assertTrue(result["persistence"]["committed"])
            self.assertTrue(result["a3_consumption"]["release_ready"])
            self.assertEqual(_count(connection, "a2_provider_reconciliation_observations"), 1)
            self.assertEqual(_count(connection, "a2_provider_outcomes"), 1)
            self.assertEqual(_count(connection, "a2_release_decisions"), 1)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 1)
            self.assertEqual(
                connection.execute("SELECT status FROM a2_decision_operations").fetchone()[0],
                "committed",
            )
            self.assertEqual(adapter.calls, 0)
            self.assertEqual(adapter.reconciliation_calls, 1)
        finally:
            connection.close()

    def test_reconciled_remote_completion_still_honors_proof_revocation(self):
        connection = sqlite3.connect(":memory:")
        interrupted = ProviderGateway(
            [ProviderDefinition(
                "unit", "fake", "local", "", frozenset({"text"}), frozenset({"tenant-a"}),
                reconciliation_mode="provider_status_lookup",
            )],
            {"fake": ProcessInterruptedAdapter()},
            response_validator=validate_semantic_judge_output,
        )
        try:
            initialize_sql_store(connection)
            with self.assertRaises(KeyboardInterrupt):
                execute_release_decision(
                    request(), gateway=interrupted, key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                )
            operation = connection.execute(
                """SELECT operation_id, provider_call_id, fencing_token, logical_call_id,
                          snapshot_hash, provider_payload_hash,
                          provider_idempotency_key_hash, provider_endpoint_hash
                   FROM a2_decision_operations"""
            ).fetchone()
            provider_gateway = reconciliation_gateway("remote_completed")
            provider_gateway.adapters["fake"].reconciliation_response.update({
                "provider_call_id": operation[1],
                "logical_call_id": operation[3],
                "provider_id": "unit",
                "model_id": "semantic-1",
                "snapshot_hash": operation[4],
                "payload_hash": operation[5],
                "idempotency_key_hash": operation[6],
                "provider_endpoint_hash": operation[7],
                "scope": {field: request()[field] for field in (
                    "organization_id", "tenant_id", "workspace_id",
                    "project_id", "environment_id",
                )},
                "operation_id": operation[0],
                "provider_generation": operation[2],
            })
            with self.assertRaisesRegex(
                IdempotencyConflictError, "input changed before commit"
            ):
                reconcile_release_decision(
                    request(), gateway=provider_gateway, key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, connection=connection, operation_id=operation[0],
                    now="2026-07-12T00:00:01Z",
                    quality_revoked_key_ids=frozenset({"quality-key-1"}),
                )
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 0)
        finally:
            connection.close()

    def test_reconciled_remote_completion_honors_proof_hash_revocation(self):
        connection = sqlite3.connect(":memory:")
        candidate = request()
        proof_hash = stable_hash({
            key: candidate["evaluation_quality_proof"][key]
            for key in sorted(candidate["evaluation_quality_proof"])
            if key != "signature"
        })
        interrupted = ProviderGateway(
            [ProviderDefinition(
                "unit", "fake", "local", "", frozenset({"text"}),
                frozenset({"tenant-a"}),
                reconciliation_mode="provider_status_lookup",
            )],
            {"fake": ProcessInterruptedAdapter()},
            response_validator=validate_semantic_judge_output,
        )
        try:
            initialize_sql_store(connection)
            with self.assertRaises(KeyboardInterrupt):
                execute_release_decision(
                    candidate, gateway=interrupted, key_resolver=lambda _: KEY,
                    now_unix_ms=NOW, persistence_connection=connection,
                )
            operation = connection.execute(
                """SELECT operation_id, provider_call_id, fencing_token, logical_call_id,
                          snapshot_hash, provider_payload_hash,
                          provider_idempotency_key_hash, provider_endpoint_hash
                   FROM a2_decision_operations"""
            ).fetchone()
            provider_gateway = reconciliation_gateway("remote_completed")
            provider_gateway.adapters["fake"].reconciliation_response.update({
                "provider_call_id": operation[1],
                "logical_call_id": operation[3],
                "provider_id": "unit",
                "model_id": "semantic-1",
                "snapshot_hash": operation[4],
                "payload_hash": operation[5],
                "idempotency_key_hash": operation[6],
                "provider_endpoint_hash": operation[7],
                "scope": {field: candidate[field] for field in (
                    "organization_id", "tenant_id", "workspace_id",
                    "project_id", "environment_id",
                )},
                "operation_id": operation[0],
                "provider_generation": operation[2],
            })
            with self.assertRaisesRegex(
                IdempotencyConflictError, "input changed before commit"
            ):
                policy = {
                    "schema_version": "a2.evaluation_trust_policy.v1",
                    "allowed_issuers": ["a2-calibration-service"],
                    "issuer_tenants": {
                        "a2-calibration-service": ["tenant-a"],
                    },
                    "revoked_key_ids": [],
                    "revoked_proof_hashes": [proof_hash],
                    "maximum_lifetime_ms": 86_400_000,
                    "maximum_review_age_ms": 604_800_000,
                }
                reconcile_release_decision(
                    candidate, gateway=provider_gateway,
                    key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    connection=connection, operation_id=operation[0],
                    now="2026-07-12T00:00:01Z",
                    quality_trust_policy=policy,
                )
            self.assertEqual(_count(connection, "a2_release_decisions"), 0)
            self.assertEqual(_count(connection, "a2_decision_outbox"), 0)
        finally:
            connection.close()

    def test_stale_and_failed_reconciliation_writes_are_fenced_and_atomic(self):
        scope = {field: request()[field] for field in (
            "organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"
        )}
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            operation = reserve_decision_operation(
                connection, scope=scope, idempotency_key="reconcile-case",
                request_hash="sha256:request", snapshot_id="snapshot",
                snapshot_hash="sha256:snapshot", provider_id="unit", model_id="semantic-1",
                reconciliation_mode="provider_status_lookup",
                provider_endpoint_hash="sha256:endpoint",
                created_at="2026-07-12T00:00:00Z",
            )
            lease = authorize_provider_call(
                connection, operation_id=operation["operation_id"], scope=scope,
                created_at="2026-07-12T00:00:00Z", worker_id="provider", lease_seconds=1,
                logical_call_id="sha256:logical", payload_hash="sha256:payload",
                idempotency_key_hash="sha256:key",
            )
            from services.judge.release_decision_store import mark_operation_recovery_required
            mark_operation_recovery_required(
                connection, operation_id=operation["operation_id"], scope=scope,
                created_at="2026-07-12T00:00:01Z", lease=lease,
            )
            stale = claim_provider_reconciliation(
                connection, operation_id=operation["operation_id"], scope=scope,
                worker_id="reconciler-old", now="2026-07-12T00:00:01Z", lease_seconds=1,
            )
            fresh = claim_provider_reconciliation(
                connection, operation_id=operation["operation_id"], scope=scope,
                worker_id="reconciler-new", now="2026-07-12T00:00:03Z",
            )
            observation = {
                **{key: fresh[key] for key in (
                    "operation_id", "provider_call_id", "provider_id", "model_id",
                    "logical_call_id", "snapshot_hash", "payload_hash", "idempotency_key_hash",
                    "provider_endpoint_hash",
                )},
                "status": "remote_pending", "retry_authorized": False, "public_safe": True,
            }
            with self.assertRaisesRegex(ValueError, "stale|expired"):
                persist_provider_reconciliation_observation(
                    connection, operation_id=operation["operation_id"], scope=scope,
                    lease=stale, observation={**observation, "provider_call_id": stale["provider_call_id"]},
                    observed_at="2026-07-12T00:00:04Z",
                )
            persist_provider_reconciliation_observation(
                connection, operation_id=operation["operation_id"], scope=scope,
                lease=fresh, observation=observation, observed_at="2026-07-12T00:00:04Z",
            )
            self.assertEqual(_count(connection, "a2_provider_reconciliation_observations"), 1)
        finally:
            connection.close()

    def test_due_reconciliation_scheduler_respects_order_mode_and_leases(self):
        scope = {field: request()[field] for field in (
            "organization_id", "tenant_id", "workspace_id", "project_id", "environment_id"
        )}
        connection = sqlite3.connect(":memory:")

        def recovery_operation(key, created_at, *, supported=True, next_at=None):
            operation = reserve_decision_operation(
                connection, scope=scope, idempotency_key=key,
                request_hash=f"sha256:{key}", snapshot_id=f"snapshot-{key}",
                snapshot_hash=f"sha256:snapshot-{key}", provider_id="unit",
                model_id="semantic-1", created_at=created_at,
                reconciliation_mode=(
                    "provider_status_lookup" if supported else "unsupported"
                ),
                provider_endpoint_hash=("sha256:endpoint" if supported else ""),
            )
            lease = authorize_provider_call(
                connection, operation_id=operation["operation_id"], scope=scope,
                created_at=created_at, worker_id=f"provider-{key}", lease_seconds=1,
                logical_call_id=f"sha256:logical-{key}", payload_hash=f"sha256:payload-{key}",
                idempotency_key_hash=f"sha256:key-{key}",
            )
            mark_operation_recovery_required(
                connection, operation_id=operation["operation_id"], scope=scope,
                created_at=created_at, lease=lease,
            )
            if next_at is not None:
                connection.execute(
                    """UPDATE a2_decision_operations
                       SET reconciliation_next_at = ? WHERE operation_id = ?""",
                    (next_at, operation["operation_id"]),
                )
                connection.commit()
            return operation["operation_id"]

        try:
            initialize_sql_store(connection)
            oldest = recovery_operation("oldest", "2026-07-12T00:00:00Z")
            recovery_operation(
                "future", "2026-07-12T00:00:01Z",
                next_at="2026-07-12T00:10:00Z",
            )
            recovery_operation("unsupported", "2026-07-11T23:59:00Z", supported=False)

            first = claim_due_provider_reconciliation(
                connection, worker_id="worker-a", now="2026-07-12T00:01:00Z",
                lease_seconds=60,
            )
            self.assertEqual(first["operation_id"], oldest)
            self.assertIsNone(claim_due_provider_reconciliation(
                connection, worker_id="worker-b", now="2026-07-12T00:01:30Z",
            ))

            reclaimed = claim_due_provider_reconciliation(
                connection, worker_id="worker-b", now="2026-07-12T00:02:01Z",
            )
            self.assertEqual(reclaimed["operation_id"], oldest)
            self.assertGreater(
                reclaimed["reconciliation_generation"],
                first["reconciliation_generation"],
            )
        finally:
            connection.close()

    def test_outbox_delivery_is_fenced_retryable_and_idempotent(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            first = claim_decision_outbox(
                connection, worker_id="dispatcher-a", now="2026-07-12T00:00:00Z", lease_seconds=1,
            )
            self.assertIsNotNone(first)
            self.assertEqual(first["attempt_count"], 1)
            takeover = claim_decision_outbox(
                connection, worker_id="dispatcher-b", now="2026-07-12T00:00:02Z",
            )
            self.assertEqual(takeover["lease_generation"], first["lease_generation"] + 1)
            with self.assertRaisesRegex(ValueError, "stale outbox"):
                settle_decision_outbox(
                    connection, event_id=first["event_id"], worker_id="dispatcher-a",
                    lease_generation=first["lease_generation"], delivered_at="2026-07-12T00:00:03Z",
                    outcome="delivered",
                )
            settle_decision_outbox(
                connection, event_id=takeover["event_id"], worker_id="dispatcher-b",
                lease_generation=takeover["lease_generation"], delivered_at="2026-07-12T00:00:03Z",
                outcome="retry", retry_at="2026-07-12T00:01:00Z", error_class="a3_unavailable",
            )
            self.assertIsNone(
                claim_decision_outbox(connection, worker_id="dispatcher-c", now="2026-07-12T00:00:30Z")
            )
            retry = claim_decision_outbox(
                connection, worker_id="dispatcher-c", now="2026-07-12T00:01:00Z",
            )
            settle_decision_outbox(
                connection, event_id=retry["event_id"], worker_id="dispatcher-c",
                lease_generation=retry["lease_generation"], delivered_at="2026-07-12T00:01:01Z",
                outcome="delivered",
            )
            self.assertIsNone(
                claim_decision_outbox(connection, worker_id="dispatcher-d", now="2026-07-12T00:02:00Z")
            )
            stored = connection.execute(
                "SELECT delivery_status, attempt_count, delivered_at FROM a2_decision_outbox"
            ).fetchone()
            self.assertEqual(stored, ("delivered", 3, "2026-07-12T00:01:01Z"))
        finally:
            connection.close()

    def test_outbox_rejects_invalid_settlement_and_never_reclaims_dead_event(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            with self.assertRaisesRegex(ValueError, "lease_seconds must be positive"):
                claim_decision_outbox(
                    connection, worker_id="dispatcher-a", now="2026-07-12T00:00:00Z",
                    lease_seconds=0,
                )
            claimed = claim_decision_outbox(
                connection, worker_id="dispatcher-a", now="2026-07-12T00:00:00Z",
            )
            with self.assertRaisesRegex(ValueError, "outbox outcome"):
                settle_decision_outbox(
                    connection, event_id=claimed["event_id"], worker_id="dispatcher-a",
                    lease_generation=claimed["lease_generation"],
                    delivered_at="2026-07-12T00:00:01Z", outcome="unknown",
                )
            with self.assertRaisesRegex(ValueError, "retry_at is required"):
                settle_decision_outbox(
                    connection, event_id=claimed["event_id"], worker_id="dispatcher-a",
                    lease_generation=claimed["lease_generation"],
                    delivered_at="2026-07-12T00:00:01Z", outcome="retry",
                )
            settle_decision_outbox(
                connection, event_id=claimed["event_id"], worker_id="dispatcher-a",
                lease_generation=claimed["lease_generation"],
                delivered_at="2026-07-12T00:00:01Z", outcome="dead",
                error_class="invalid_a3_contract",
            )
            self.assertIsNone(
                claim_decision_outbox(
                    connection, worker_id="dispatcher-b", now="2026-07-13T00:00:00Z",
                )
            )
            stored = connection.execute(
                "SELECT delivery_status, delivered_at, last_error_class "
                "FROM a2_decision_outbox"
            ).fetchone()
            self.assertEqual(stored, ("dead", None, "invalid_a3_contract"))
        finally:
            connection.close()

    def test_two_connections_cannot_claim_the_same_outbox_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "outbox.sqlite"
            first_connection = sqlite3.connect(database_path)
            second_connection = sqlite3.connect(database_path)
            try:
                initialize_sql_store(first_connection)
                execute_release_decision(
                    request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=first_connection,
                )
                first = claim_decision_outbox(
                    first_connection, worker_id="dispatcher-a", now="2026-07-12T00:00:00Z",
                )
                self.assertIsNotNone(first)
                self.assertIsNone(
                    claim_decision_outbox(
                        second_connection, worker_id="dispatcher-b", now="2026-07-12T00:00:01Z",
                    )
                )
                stored = second_connection.execute(
                    "SELECT lease_owner, lease_generation, attempt_count "
                    "FROM a2_decision_outbox WHERE event_id = ?",
                    (first["event_id"],),
                ).fetchone()
                self.assertEqual(
                    stored,
                    ("dispatcher-a", first["lease_generation"], 1),
                )
            finally:
                first_connection.close()
                second_connection.close()

    def test_changed_request_conflicts_with_existing_idempotency_key(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            changed = request()
            changed["policy_version"] = "a2.semantic_release_policy.v2"
            with self.assertRaisesRegex(IdempotencyConflictError, "different decision"):
                execute_release_decision(
                    changed, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                    persistence_connection=connection,
                )
            self.assertEqual(_count(connection, "a2_release_decisions"), 1)
        finally:
            connection.close()

    def test_tampered_ledger_and_cross_scope_persist_nothing(self):
        base = execute_release_decision(request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        candidates = []
        tampered = json.loads(json.dumps(base))
        tampered["decision_ledger"]["records"][0]["record_hash"] = "sha256:tampered"
        candidates.append(tampered)
        cross_scope = json.loads(json.dumps(base))
        cross_scope["evidence_snapshot"]["tenant_id"] = "tenant-b"
        candidates.append(cross_scope)
        for candidate in candidates:
            connection = sqlite3.connect(":memory:")
            try:
                initialize_sql_store(connection)
                with self.assertRaises(ValueError):
                    persist_release_decision(
                        connection,
                        candidate,
                        idempotency_key="decision-1",
                        request_hash=stable_hash({"request": 1}),
                    )
                self.assertEqual(_count(connection, "a2_release_decisions"), 0)
                self.assertEqual(_count(connection, "a2_release_decision_audit"), 0)
            finally:
                connection.close()

    def test_public_store_contains_hashes_not_raw_payloads_or_paths(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            execute_release_decision(
                request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW,
                persistence_connection=connection,
            )
            dump = "\n".join(connection.iterdump())
            for forbidden in ("final_response", "output_text", "private_refs", "signed_url", "api_key", "Bearer "):
                self.assertNotIn(forbidden, dump)
            self.assertIn("a2.release_decision.committed.v1", dump)
        finally:
            connection.close()

    def test_provider_failure_is_committed_as_block_not_lost_or_allowed(self):
        connection = sqlite3.connect(":memory:")
        try:
            initialize_sql_store(connection)
            result = execute_release_decision(
                request(),
                gateway=gateway(failure="timeout"),
                key_resolver=lambda _: KEY,
                now_unix_ms=NOW,
                persistence_connection=connection,
            )
            stored = connection.execute(
                "SELECT decision FROM a2_release_decisions"
            ).fetchone()
            self.assertEqual(result["persistence"]["decision"], "block")
            self.assertEqual(stored[0], "block")
            self.assertFalse(result["a3_consumption"]["release_ready"])
            self.assertEqual(_count(connection, "a2_release_decision_audit"), 1)
        finally:
            connection.close()


def _count(connection, table):
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
