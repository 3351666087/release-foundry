import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from services.judge.bundle_evaluation import evaluate_a1_bundle
from services.judge.sql_store import initialize_sql_store
from tests.a2.test_release_decision_orchestrator import (KEY, NOW, GroundedRecordingAdapter, gateway, image_pipeline_and_evidence, request)
from services.judge.provider_gateway import ProviderDefinition, ProviderGateway
from services.judge.provider_runtime import validate_semantic_judge_output
from scripts.a2_evaluate_bundle import _validate_ollama_model
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
        candidate.pop("evaluation_quality")
        result = evaluate_a1_bundle(candidate, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertTrue(result["provider_called"])
        codes = {item["code"] for item in result["findings"]}
        self.assertIn("calibration_not_passed", codes)
        self.assertIn("golden_regression_not_passed", codes)

    def test_failed_calibration_blocks_model_pass(self):
        candidate = request()
        candidate["evaluation_quality"]["calibration"] = "failed"
        result = evaluate_a1_bundle(candidate, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn("calibration_not_passed", {item["code"] for item in result["findings"]})
        self.assertEqual(result["release_gate"]["evaluation_quality"]["calibration"], "failed")

    def test_disagreement_requires_human_review_before_pass(self):
        candidate = request()
        candidate["evaluation_quality"]["disagreement"] = "disagree"
        result = evaluate_a1_bundle(candidate, gateway=gateway(), key_resolver=lambda _: KEY, now_unix_ms=NOW)
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn("disagreement_requires_review", {item["code"] for item in result["findings"]})

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

    def assert_response_schema(self, result):
        schema = json.loads((ROOT / "docs/a2/schemas/bundle_evaluation.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(result)


if __name__ == "__main__":
    unittest.main()
