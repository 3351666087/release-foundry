import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import jsonschema

from services.judge.bundle_evaluation import evaluate_a1_bundle
from services.judge.evaluation_trust_policy import evaluation_trust_policy_hash
from services.judge.sql_store import initialize_sql_store
from tests.a2.test_release_decision_orchestrator import (
    KEY, NOW, GroundedRecordingAdapter, gateway, image_pipeline_and_evidence, request,
    signed_quality_proof,
)
from services.judge.provider_gateway import ProviderDefinition, ProviderGateway
from services.judge.provider_runtime import validate_semantic_judge_output
from scripts.a2_evaluate_bundle import (
    _validate_local_runtime_paths,
    _validate_model_storage,
    _validate_ollama_model,
)
from services.judge.provider_runtime import ModelRecord


ROOT = Path(__file__).resolve().parents[2]


class BundleEvaluationTests(unittest.TestCase):
    def connection(self):
        connection = sqlite3.connect(":memory:")
        initialize_sql_store(connection)
        return connection

    def test_authenticated_bundle_reaches_real_gateway_and_committed_pass(self):
        connection = self.connection()
        try:
            result = evaluate_a1_bundle(request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW, persistence_connection=connection)
            self.assertEqual(result["decision"], "PASS")
            self.assertTrue(result["evidence_complete"])
            self.assertTrue(result["provider_called"])
            self.assertTrue(result["release_ready"])
            self.assertTrue(result["reproducibility"]["persisted"])
            self.assertRegex(
                result["reproducibility"]["evaluation_trust_policy_hash"],
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertTrue(result["decision_record_hash"].startswith("sha256:"))
            self.assert_response_schema(result)
        finally:
            connection.close()

    def test_provider_failure_never_becomes_pass(self):
        connection = self.connection()
        try:
            result = evaluate_a1_bundle(request(), gateway=gateway(failure="timeout"), key_resolver=lambda _: KEY, now_unix_ms=NOW, persistence_connection=connection)
            self.assertEqual(result["decision"], "BLOCK")
            self.assertFalse(result["release_ready"])
            self.assertTrue(result["provider_called"])
            self.assertIn("provider_error", {item["code"] for item in result["findings"]})
            self.assertEqual(connection.execute("SELECT decision FROM a2_release_decisions").fetchone()[0], "block")
            self.assert_response_schema(result)
        finally:
            connection.close()

    def test_invalid_bundle_is_structured_incomplete_and_skips_provider(self):
        candidate = request()
        candidate["authenticated_evidence_bundle"]["evidence_digest"] = "tampered"
        adapter_gateway = gateway()
        result = evaluate_a1_bundle(candidate, gateway=adapter_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "INCOMPLETE")
        self.assertFalse(result["provider_called"])
        self.assertEqual(adapter_gateway.adapters["fake"].calls, 0)
        self.assertEqual(result["findings"][0]["source"], "evidence_verifier")
        self.assert_response_schema(result)
        self.assertRegex(
            result["reproducibility"]["evaluation_trust_policy_hash"],
            r"^sha256:[0-9a-f]{64}$",
        )

    def test_multimodal_qualified_evidence_reaches_judge_and_passes(self):
        pipeline, evidence = image_pipeline_and_evidence()
        candidate = request()
        candidate.update({"required_modalities": ["text", "image"], "artifact_pipeline_records": [pipeline], "derived_evidence_records": [evidence]})
        candidate["evaluation_quality_proof"] = signed_quality_proof(candidate)
        adapter = GroundedRecordingAdapter()
        provider = ProviderDefinition("unit", "recording", "local", "", frozenset({"text"}), frozenset({"tenant-a"}), data_residency="local")
        result = evaluate_a1_bundle(candidate, gateway=ProviderGateway([provider], {"recording": adapter}, response_validator=validate_semantic_judge_output), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "PASS")
        self.assertEqual(adapter.calls, 1)
        self.assertTrue(result["evidence_complete"])

    def test_unqualified_multimodal_evidence_blocks_without_provider_call(self):
        pipeline, evidence = image_pipeline_and_evidence(production_qualified=False)
        candidate = request()
        candidate.update({"required_modalities": ["text", "image"], "artifact_pipeline_records": [pipeline], "derived_evidence_records": [evidence]})
        provider_gateway = gateway()
        result = evaluate_a1_bundle(candidate, gateway=provider_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertFalse(result["provider_called"])
        self.assertEqual(provider_gateway.adapters["fake"].calls, 0)

    def test_same_version_and_idempotency_key_replays_committed_decision(self):
        connection = self.connection()
        try:
            first = evaluate_a1_bundle(request(), gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW, persistence_connection=connection)
            second_gateway = gateway(failure="must-not-call")
            second = evaluate_a1_bundle(request(), gateway=second_gateway, key_resolver=lambda _: KEY, now_unix_ms=NOW, persistence_connection=connection)
            self.assertEqual(second["decision"], "PASS")
            self.assertTrue(second["reproducibility"]["idempotent_replay"])
            self.assertEqual(second_gateway.adapters["fake"].calls, 0)
            self.assertEqual(first["reproducibility"]["record_id"], second["reproducibility"]["record_id"])
            self.assertEqual(first["request_fingerprint"], second["request_fingerprint"])
        finally:
            connection.close()

    def test_missing_quality_evidence_blocks_model_pass(self):
        candidate = request()
        candidate.pop("evaluation_quality_proof")
        result = evaluate_a1_bundle(candidate, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertTrue(result["provider_called"])
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("quality_proof_missing", codes)

    def test_failed_calibration_blocks_model_pass(self):
        candidate = request()
        candidate["evaluation_quality_proof"] = signed_quality_proof(
            candidate, calibration="failed"
        )
        result = evaluate_a1_bundle(candidate, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn("calibration_not_passed", {item["code"] for item in result["findings"]})
        self.assertEqual(result["release_gate"]["evaluation_quality"]["calibration"], "failed")

    def test_disagreement_requires_human_review_before_pass(self):
        candidate = request()
        candidate["evaluation_quality_proof"] = signed_quality_proof(
            candidate, disagreement="disagree"
        )
        result = evaluate_a1_bundle(candidate, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn("disagreement_requires_review", {item["code"] for item in result["findings"]})

    def test_quality_proof_cannot_be_replayed_across_model_or_policy(self):
        for field, value in (
            ("model_id", "semantic-2"),
            ("policy_version", "a2.semantic_release_policy.v2"),
        ):
            candidate = request()
            candidate[field] = value
            result = evaluate_a1_bundle(
                candidate, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW
            )
            self.assertEqual(result["decision"], "BLOCK")
            self.assertIn(
                "quality_proof_binding_mismatch",
                {item["code"] for item in result["findings"]},
            )

    def test_quality_proof_tamper_and_expiry_fail_closed(self):
        tampered = request()
        tampered["evaluation_quality_proof"]["calibration"] = "failed"
        result = evaluate_a1_bundle(
            tampered, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW
        )
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn(
            "quality_proof_signature_mismatch",
            {item["code"] for item in result["findings"]},
        )

        expired = request()
        expired["evaluation_quality_proof"] = signed_quality_proof(
            expired, issued_at_unix_ms=NOW - 2000, expires_at_unix_ms=NOW - 1
        )
        result = evaluate_a1_bundle(
            expired, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW
        )
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn(
            "quality_proof_outside_validity_window",
            {item["code"] for item in result["findings"]},
        )

    def test_quality_proof_schema_accepts_signed_fixture(self):
        candidate = request()
        schema = json.loads(
            (ROOT / "docs/a2/schemas/evaluation_quality_proof.schema.json").read_text()
        )
        jsonschema.validate(candidate["evaluation_quality_proof"], schema)

    def test_trust_policy_schema_accepts_governed_fixture(self):
        schema = json.loads(
            (ROOT / "docs/a2/schemas/evaluation_trust_policy.schema.json").read_text()
        )
        jsonschema.validate({
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": ["a2-calibration-service"],
            "issuer_tenants": {"a2-calibration-service": ["tenant-a"]},
            "revoked_key_ids": [],
            "revoked_proof_hashes": ["sha256:" + "a" * 64],
            "maximum_lifetime_ms": 86_400_000,
            "maximum_review_age_ms": 604_800_000,
        }, schema)

    def test_facade_binds_normalized_trust_policy_hash_to_reproducibility(self):
        policy = {
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": ["a2-calibration-service"],
            "issuer_tenants": {"a2-calibration-service": ["tenant-a", "tenant-a"]},
            "revoked_key_ids": [],
            "revoked_proof_hashes": [],
            "maximum_lifetime_ms": 86_400_000,
            "maximum_review_age_ms": 604_800_000,
        }
        connection = self.connection()
        try:
            result = evaluate_a1_bundle(
                request(), gateway=gateway(), key_resolver=lambda _: KEY,
                now_unix_ms=NOW, persistence_connection=connection,
                quality_trust_policy=policy,
            )
            self.assertEqual(
                result["reproducibility"]["evaluation_trust_policy_hash"],
                evaluation_trust_policy_hash(policy),
            )
            self.assert_response_schema(result)
        finally:
            connection.close()

    def test_cli_valid_trust_policy_reaches_provider_end_to_end(self):
        completed, calls = self.run_complete_cli_with_policy(self.trust_policy())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(calls(), 1)
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["reproducibility"]["evaluation_trust_policy_hash"],
            evaluation_trust_policy_hash(self.trust_policy()),
        )

    def test_cli_same_policy_replays_record_and_hash_without_provider_call(self):
        completed, calls = self.run_complete_cli_with_policy(
            self.trust_policy(), repetitions=2
        )
        self.assertEqual([item.returncode for item in completed], [0, 0])
        first, second = (json.loads(item.stdout) for item in completed)
        expected_hash = evaluation_trust_policy_hash(self.trust_policy())
        self.assertEqual(calls(), 1)
        self.assertEqual(
            first["reproducibility"]["evaluation_trust_policy_hash"], expected_hash
        )
        self.assertEqual(
            second["reproducibility"]["evaluation_trust_policy_hash"], expected_hash
        )
        self.assertEqual(
            first["reproducibility"]["record_id"],
            second["reproducibility"]["record_id"],
        )
        self.assertFalse(first["reproducibility"]["idempotent_replay"])
        self.assertTrue(second["reproducibility"]["idempotent_replay"])

    def test_cli_equivalent_reordered_policy_replays_without_provider_call(self):
        first_policy = self.trust_policy()
        first_policy["allowed_issuers"] = ["unused-issuer", "a2-calibration-service"]
        first_policy["issuer_tenants"]["unused-issuer"] = ["tenant-z", "tenant-y"]
        reordered = {
            **first_policy,
            "allowed_issuers": list(reversed(first_policy["allowed_issuers"])),
            "issuer_tenants": {
                "unused-issuer": ["tenant-y", "tenant-z"],
                "a2-calibration-service": ["tenant-a"],
            },
        }
        completed, calls = self.run_complete_cli_with_policy(
            [first_policy, reordered]
        )
        self.assertEqual([item.returncode for item in completed], [0, 0])
        first, second = (json.loads(item.stdout) for item in completed)
        self.assertEqual(calls(), 1)
        self.assertEqual(
            first["reproducibility"]["evaluation_trust_policy_hash"],
            second["reproducibility"]["evaluation_trust_policy_hash"],
        )
        self.assertTrue(second["reproducibility"]["idempotent_replay"])

    def test_cli_duplicate_revocations_normalize_and_replay_without_provider_call(self):
        duplicated = self.trust_policy()
        duplicated["revoked_key_ids"] = ["other-key", "other-key"]
        duplicated["revoked_proof_hashes"] = [
            "sha256:" + "e" * 64,
            "sha256:" + "e" * 64,
        ]
        normalized = self.trust_policy()
        normalized["revoked_key_ids"] = ["other-key"]
        normalized["revoked_proof_hashes"] = ["sha256:" + "e" * 64]
        completed, calls = self.run_complete_cli_with_policy([duplicated, normalized])
        self.assertEqual([item.returncode for item in completed], [0, 0])
        first, second = (json.loads(item.stdout) for item in completed)
        self.assertEqual(calls(), 1)
        self.assertEqual(
            first["reproducibility"]["evaluation_trust_policy_hash"],
            second["reproducibility"]["evaluation_trust_policy_hash"],
        )
        self.assertTrue(second["reproducibility"]["idempotent_replay"])

    def test_cli_changed_revocation_set_conflicts_without_second_provider_call(self):
        first_policy = self.trust_policy()
        changed = self.trust_policy()
        changed["revoked_key_ids"] = ["other-key"]
        completed, calls = self.run_complete_cli_with_policy([first_policy, changed])
        self.assertEqual(completed[0].returncode, 0)
        self.assertNotEqual(completed[1].returncode, 0)
        self.assertEqual(calls(), 1)
        first, second = (json.loads(item.stdout) for item in completed)
        self.assertEqual(second["decision"], "INCOMPLETE")
        self.assertFalse(second["provider_called"])
        self.assertFalse(second["reproducibility"]["persisted"])
        self.assertNotEqual(
            first["reproducibility"]["evaluation_trust_policy_hash"],
            second["reproducibility"]["evaluation_trust_policy_hash"],
        )

    def test_cli_changed_maximum_review_age_conflicts_without_second_provider_call(self):
        first_policy = self.trust_policy()
        changed = self.trust_policy()
        changed["maximum_review_age_ms"] -= 1
        completed, calls = self.run_complete_cli_with_policy([first_policy, changed])
        self.assertEqual(completed[0].returncode, 0)
        self.assertNotEqual(completed[1].returncode, 0)
        self.assertEqual(calls(), 1)
        first, second = (json.loads(item.stdout) for item in completed)
        self.assertEqual(second["decision"], "INCOMPLETE")
        self.assertFalse(second["provider_called"])
        self.assertFalse(second["reproducibility"]["persisted"])
        self.assertNotEqual(
            first["reproducibility"]["evaluation_trust_policy_hash"],
            second["reproducibility"]["evaluation_trust_policy_hash"],
        )

    def test_cli_invalid_trust_policy_fails_before_provider_invocation(self):
        invalid = self.trust_policy()
        invalid["revoked_key_ids"] = ["contains whitespace"]
        completed, calls = self.run_complete_cli_with_policy(invalid)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(calls(), 0)
        self.assertIn("revoked key ids are invalid", completed.stderr)

    def test_cli_malformed_trust_policy_error_is_sanitized(self):
        completed = self.run_policy_file_cli('{"secret":"must-not-echo",')
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("trust policy could not be loaded as JSON", completed.stderr)
        self.assertNotIn("must-not-echo", completed.stdout + completed.stderr)

    def test_cli_missing_trust_policy_fails_before_provider(self):
        completed = self.run_policy_file_cli(None)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("trust policy could not be loaded as JSON", completed.stderr)
        self.assertNotIn("Connection refused", completed.stderr)

    def test_cli_malformed_quality_proof_error_is_sanitized(self):
        completed = self.run_json_file_cli(
            input_text=json.dumps({"tenant_id": "tenant-a"}),
            proof_text='{"secret":"quality-must-not-echo",',
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("quality proof could not be loaded as JSON", completed.stderr)
        self.assertNotIn("quality-must-not-echo", completed.stdout + completed.stderr)

    def test_cli_malformed_bundle_error_is_sanitized(self):
        completed = self.run_json_file_cli(
            input_text='{"secret":"bundle-must-not-echo",',
            proof_text=None,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("input could not be loaded as JSON", completed.stderr)
        self.assertNotIn("bundle-must-not-echo", completed.stdout + completed.stderr)

    def test_cli_missing_quality_proof_fails_before_provider(self):
        completed = self.run_json_file_cli(
            input_text=json.dumps({"tenant_id": "tenant-a"}),
            proof_text=None,
            include_proof_argument=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("quality proof could not be loaded as JSON", completed.stderr)
        self.assertNotIn("Connection refused", completed.stderr)

    def test_cli_missing_bundle_key_fails_without_leaking_provider_secret(self):
        completed = self.run_cli(
            "ollama",
            environment={"UNRELATED_SECRET": "must-not-appear"},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("verification key environment variable is unavailable", completed.stderr)
        self.assertNotIn("must-not-appear", completed.stdout + completed.stderr)

    def test_cli_missing_provider_credential_fails_without_leaking_bundle_key(self):
        completed = self.run_cli(
            "openai-compatible",
            extra_arguments=["--credential-env", "A2_TEST_PROVIDER_KEY"],
            environment={"A1_EVIDENCE_HMAC_KEY": "bundle-secret-must-not-appear"},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Provider credential environment variable is unavailable", completed.stderr)
        self.assertNotIn("bundle-secret-must-not-appear", completed.stdout + completed.stderr)

    def test_qwen_preset_uses_dashscope_url_and_standard_environment_key(self):
        completed = self.run_cli(
            "qwen",
            environment={"A1_EVIDENCE_HMAC_KEY": "bundle-key"},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Provider credential environment variable is unavailable", completed.stderr)
        self.assertNotIn("bundle-key", completed.stdout + completed.stderr)

    def test_qwen_default_url_is_the_dashscope_compatible_endpoint(self):
        source = (ROOT / "scripts/a2_evaluate_bundle.py").read_text(encoding="utf-8")
        self.assertIn("https://dashscope.aliyuncs.com/compatible-mode/v1", source)
        self.assertIn('credential_env or "DASHSCOPE_API_KEY"', source)

    def test_cli_exit_codes_pass_block_and_incomplete_through_http_protocol(self):
        class Handler(BaseHTTPRequestHandler):
            status = 200

            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                body = {
                    "id": "stub-request",
                    "choices": [{"message": {"content": json.dumps({
                        "passed": True,
                        "score": 0.97,
                        "reason": "stub judge accepted evidence",
                        "failure_classes": [],
                        "evidence_refs": ["snapshot"],
                        "abstained": False,
                    })}}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 3},
                }
                encoded = json.dumps(body).encode()
                self.send_response(self.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}/v1"
            self.assertEqual(self.run_complete_cli(base_url).returncode, 0)
            Handler.status = 500
            blocked = self.run_complete_cli(base_url)
            self.assertEqual(blocked.returncode, 2)
            self.assertEqual(json.loads(blocked.stdout)["decision"], "BLOCK")
            Handler.status = 200
            incomplete = self.run_complete_cli(base_url, tamper_bundle=True)
            self.assertEqual(incomplete.returncode, 3)
            self.assertEqual(json.loads(incomplete.stdout)["decision"], "INCOMPLETE")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def run_complete_cli(self, base_url, *, tamper_bundle=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = request()
            candidate["provider_id"] = "local-judge"
            candidate["model_id"] = "test-model"
            candidate["evaluation_quality_proof"] = signed_quality_proof(candidate)
            if tamper_bundle:
                candidate["authenticated_evidence_bundle"]["evidence_digest"] = "tampered"
            proof = candidate.pop("evaluation_quality_proof")
            input_path = root / "bundle.json"
            proof_path = root / "quality-proof.json"
            input_path.write_text(json.dumps(candidate), encoding="utf-8")
            proof_path.write_text(json.dumps(proof), encoding="utf-8")
            command = [
                sys.executable, "-B", "scripts/a2_evaluate_bundle.py",
                "--input", str(input_path),
                "--quality-proof", str(proof_path),
                "--database", str(root / "decisions.sqlite"),
                "--provider", "openai-compatible",
                "--provider-id", "local-judge",
                "--model", "test-model",
                "--base-url", base_url,
                "--credential-env", "A2_TEST_PROVIDER_KEY",
                "--now-unix-ms", str(NOW),
            ]
            environment = dict(os.environ)
            environment.update({
                "A1_EVIDENCE_HMAC_KEY": KEY.decode(),
                "A2_TEST_PROVIDER_KEY": "stub-only-secret",
            })
            return subprocess.run(
                command, cwd=ROOT, env=environment, capture_output=True, text=True, check=False
            )

    def run_complete_cli_with_policy(self, policy, *, repetitions=1):
        class Handler(BaseHTTPRequestHandler):
            calls = 0

            def do_POST(self):
                type(self).calls += 1
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                content = json.dumps({
                    "passed": True, "score": 0.97, "reason": "policy reached judge",
                    "failure_classes": [], "evidence_refs": ["snapshot"], "abstained": False,
                })
                body = json.dumps({
                    "id": "stub-request",
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 3},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                candidate = request()
                candidate["provider_id"] = "local-judge"
                candidate["model_id"] = "test-model"
                candidate["evaluation_quality_proof"] = signed_quality_proof(candidate)
                proof = candidate.pop("evaluation_quality_proof")
                policies = policy if isinstance(policy, list) else [policy] * repetitions
                for name, value in (
                    ("bundle.json", candidate), ("quality-proof.json", proof),
                ):
                    (root / name).write_text(json.dumps(value), encoding="utf-8")
                command = [
                    sys.executable, "-B", "scripts/a2_evaluate_bundle.py",
                    "--input", str(root / "bundle.json"),
                    "--quality-proof", str(root / "quality-proof.json"),
                    "--trust-policy", str(root / "trust-policy.json"),
                    "--database", str(root / "decisions.sqlite"),
                    "--provider", "openai-compatible",
                    "--provider-id", "local-judge",
                    "--model", "test-model",
                    "--base-url", f"http://127.0.0.1:{server.server_port}/v1",
                    "--credential-env", "A2_TEST_PROVIDER_KEY",
                    "--now-unix-ms", str(NOW),
                ]
                environment = dict(os.environ)
                environment.update({
                    "A1_EVIDENCE_HMAC_KEY": KEY.decode(),
                    "A2_TEST_PROVIDER_KEY": "stub-only-secret",
                })
                completed = []
                for current_policy in policies:
                    (root / "trust-policy.json").write_text(
                        json.dumps(current_policy), encoding="utf-8"
                    )
                    completed.append(subprocess.run(
                        command, cwd=ROOT, env=environment,
                        capture_output=True, text=True, check=False,
                    ))
                return (
                    completed[0] if len(completed) == 1 else completed,
                    lambda: Handler.calls,
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def run_json_file_cli(
        self, *, input_text, proof_text, include_proof_argument=False
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "bundle.json"
            proof_path = root / "quality-proof.json"
            input_path.write_text(input_text, encoding="utf-8")
            if proof_text is not None:
                proof_path.write_text(proof_text, encoding="utf-8")
            command = [
                sys.executable, "-B", "scripts/a2_evaluate_bundle.py",
                "--input", str(input_path),
                "--database", str(root / "decisions.sqlite"),
                "--provider", "openai-compatible",
                "--model", "test-model",
                "--base-url", "http://127.0.0.1:1",
                "--credential-env", "A2_TEST_PROVIDER_KEY",
                "--now-unix-ms", str(NOW),
            ]
            if proof_text is not None or include_proof_argument:
                command.extend(["--quality-proof", str(proof_path)])
            return subprocess.run(
                command, cwd=ROOT,
                env={
                    **os.environ,
                    "A1_EVIDENCE_HMAC_KEY": KEY.decode(),
                    "A2_TEST_PROVIDER_KEY": "stub-only-secret",
                },
                capture_output=True, text=True, check=False,
            )

    def run_policy_file_cli(self, policy_text):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "bundle.json"
            policy_path = root / "trust-policy.json"
            input_path.write_text(json.dumps({"tenant_id": "tenant-a"}), encoding="utf-8")
            if policy_text is not None:
                policy_path.write_text(policy_text, encoding="utf-8")
            command = [
                sys.executable, "-B", "scripts/a2_evaluate_bundle.py",
                "--input", str(input_path),
                "--trust-policy", str(policy_path),
                "--database", str(root / "decisions.sqlite"),
                "--provider", "openai-compatible",
                "--model", "test-model",
                "--base-url", "http://127.0.0.1:1",
                "--credential-env", "A2_TEST_PROVIDER_KEY",
                "--now-unix-ms", str(NOW),
            ]
            environment = dict(os.environ)
            environment.update({
                "A1_EVIDENCE_HMAC_KEY": KEY.decode(),
                "A2_TEST_PROVIDER_KEY": "stub-only-secret",
            })
            return subprocess.run(
                command, cwd=ROOT, env=environment,
                capture_output=True, text=True, check=False,
            )

    @staticmethod
    def trust_policy():
        return {
            "schema_version": "a2.evaluation_trust_policy.v1",
            "allowed_issuers": ["a2-calibration-service"],
            "issuer_tenants": {"a2-calibration-service": ["tenant-a"]},
            "revoked_key_ids": [],
            "revoked_proof_hashes": [],
            "maximum_lifetime_ms": 86_400_000,
            "maximum_review_age_ms": 604_800_000,
        }

    def run_cli(self, provider, *, extra_arguments=None, environment=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "bundle.json"
            input_path.write_text(json.dumps({"tenant_id": "tenant-a"}), encoding="utf-8")
            command = [
                sys.executable,
                "-B",
                "scripts/a2_evaluate_bundle.py",
                "--input",
                str(input_path),
                "--database",
                str(root / "decisions.sqlite"),
                "--provider",
                provider,
                "--model",
                "test-model",
                "--base-url",
                "http://127.0.0.1:1",
                "--now-unix-ms",
                str(NOW),
                *(extra_arguments or []),
            ]
            clean_environment = {
                key: value
                for key, value in os.environ.items()
                if key not in {
                    "A1_EVIDENCE_HMAC_KEY",
                    "A2_TEST_PROVIDER_KEY",
                    "DASHSCOPE_API_KEY",
                }
            }
            clean_environment.update(environment or {})
            return subprocess.run(command, cwd=Path(__file__).resolve().parents[2], env=clean_environment, capture_output=True, text=True, check=False)

    def test_ollama_discovery_requires_configured_model_and_modalities(self):
        vision = ModelRecord("ollama-local", "vision", "digest", frozenset({"text", "image"}), local=True)
        with patch("scripts.a2_evaluate_bundle.OllamaDiscovery.discover", return_value=[vision]):
            _validate_ollama_model({"required_modalities": ["image"]}, "vision", "http://local")
            with self.assertRaisesRegex(SystemExit, "was not discovered"):
                _validate_ollama_model({}, "missing", "http://local")
            with self.assertRaisesRegex(SystemExit, "lacks required modalities: audio"):
                _validate_ollama_model({"required_modalities": ["audio"]}, "vision", "http://local")

    def test_ollama_discovery_failure_is_fail_closed(self):
        with patch("scripts.a2_evaluate_bundle.OllamaDiscovery.discover", side_effect=TimeoutError):
            with self.assertRaisesRegex(SystemExit, "capability discovery is unavailable"):
                _validate_ollama_model({}, "vision", "http://local")

    def test_model_storage_preflight_rejects_capacity_shortfall(self):
        with tempfile.TemporaryDirectory() as directory:
            _validate_model_storage(Path(directory) / "models", 0)
            with self.assertRaisesRegex(SystemExit, "insufficient free space"):
                _validate_model_storage(Path(directory), 10 ** 9)

    def test_local_runtime_paths_must_exist_and_share_a_drive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ollama.exe"
            executable.write_bytes(b"test")
            _validate_local_runtime_paths(executable, root / "models")
            with self.assertRaisesRegex(SystemExit, "does not exist"):
                _validate_local_runtime_paths(root / "missing.exe", root / "models")

    def test_ollama_installer_dry_run_performs_no_download_or_writes(self):
        script = ROOT / "scripts/a2_install_ollama_d_drive.ps1"
        text = script.read_text(encoding="utf-8")
        dry_run_index = text.index("if ($DryRun)")
        download_index = text.index("Invoke-WebRequest")
        write_index = text.index("New-Item -ItemType Directory")
        environment_index = text.index("[Environment]::SetEnvironmentVariable")
        self.assertLess(dry_run_index, download_index)
        self.assertLess(dry_run_index, write_index)
        self.assertLess(dry_run_index, environment_index)
        self.assertIn("[switch]$DryRun", text)

    @unittest.skipUnless(os.name == "nt", "PowerShell installer is Windows-only")
    def test_ollama_installer_dry_run_does_not_create_target_directories(self):
        root = Path("D:/Ashr/a2-installer-dry-run-test")
        install = root / "runtime"
        models = root / "models"
        if root.exists():
            self.skipTest("reserved dry-run test root already exists")
        completed = subprocess.run([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "scripts/a2_install_ollama_d_drive.ps1"),
            "-ArchiveUrl", "https://example.invalid/ollama.zip",
            "-Sha256", "a" * 64,
            "-InstallRoot", str(install),
            "-ModelRoot", str(models),
            "-DryRun",
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(root.exists())

    @unittest.skipUnless(os.name == "nt", "PowerShell installer is Windows-only")
    def test_ollama_installer_rejects_non_d_roots(self):
        cases = (
            ("C:\\Ashr\\ollama", "D:\\Ashr\\models"),
            ("D:\\Ashr\\ollama", "C:\\Ashr\\models"),
        )
        for install, models in cases:
            with self.subTest(install=install, models=models):
                completed = subprocess.run([
                    "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(ROOT / "scripts/a2_install_ollama_d_drive.ps1"),
                    "-ArchiveUrl", "https://example.invalid/ollama.zip",
                    "-Sha256", "a" * 64,
                    "-InstallRoot", install,
                    "-ModelRoot", models,
                    "-DryRun",
                ], cwd=ROOT, capture_output=True, text=True, check=False)
                self.assertNotEqual(completed.returncode, 0)
                self.assertIn("must both remain on D", completed.stderr)

    @unittest.skipUnless(os.name == "nt", "PowerShell installer is Windows-only")
    def test_ollama_installer_rejects_non_d_download_path(self):
        completed = subprocess.run([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "scripts/a2_install_ollama_d_drive.ps1"),
            "-ArchiveUrl", "https://example.invalid/ollama.zip",
            "-Sha256", "a" * 64,
            "-DownloadPath", "C:\\Temp\\ollama.zip",
            "-DryRun",
        ], cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("archive staging must remain on D", completed.stderr)

    @unittest.skipUnless(os.name == "nt", "PowerShell installer is Windows-only")
    def test_ollama_installer_checksum_mismatch_removes_download(self):
        root = Path("D:/Ashr/a2-checksum-test")
        if not Path("D:/").exists():
            self.skipTest("Ollama installer test requires a D: drive")
        if shutil.disk_usage("D:/").free < 20 * 1024**3:
            self.skipTest("Ollama installer test requires at least 20 GiB free on D:")
        if root.exists():
            self.skipTest("reserved checksum test root already exists")
        try:
            root.mkdir(parents=True)
            source = root / "source.zip"
            download = root / "download.zip"
            source.write_bytes(b"not-an-ollama-archive")
            completed = subprocess.run([
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "scripts/a2_install_ollama_d_drive.ps1"),
                "-ArchiveUrl", source.as_uri(),
                "-Sha256", "a" * 64,
                "-InstallRoot", "D:\\Ashr\\a2-checksum-test\\runtime",
                "-ModelRoot", "D:\\Ashr\\a2-checksum-test\\models",
                "-DownloadPath", str(download),
            ], cwd=ROOT, capture_output=True, text=True, check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("checksum mismatch", completed.stderr)
            self.assertFalse(download.exists())
            self.assertTrue(source.exists())
            self.assertEqual(source.read_bytes(), b"not-an-ollama-archive")
        finally:
            if root.exists():
                import shutil as test_shutil
                test_shutil.rmtree(root)

    def assert_response_schema(self, result):
        schema = json.loads((ROOT / "docs/a2/schemas/bundle_evaluation.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(result)


if __name__ == "__main__":
    unittest.main()
