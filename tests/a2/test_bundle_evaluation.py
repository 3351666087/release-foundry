import json
import os
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
from services.judge.sql_store import initialize_sql_store
from tests.a2.test_release_decision_orchestrator import (
    KEY, NOW, GroundedRecordingAdapter, gateway, image_pipeline_and_evidence, request,
    signed_quality_proof,
)
from services.judge.provider_gateway import ProviderDefinition, ProviderGateway
from services.judge.provider_runtime import validate_semantic_judge_output
from scripts.a2_evaluate_bundle import _validate_model_storage, _validate_ollama_model
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
                if key not in {"A1_EVIDENCE_HMAC_KEY", "A2_TEST_PROVIDER_KEY"}
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

    def assert_response_schema(self, result):
        schema = json.loads((ROOT / "docs/a2/schemas/bundle_evaluation.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(result)


if __name__ == "__main__":
    unittest.main()
