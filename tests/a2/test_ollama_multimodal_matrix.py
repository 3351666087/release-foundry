import json
import tempfile
import unittest
import socket
from pathlib import Path
from unittest.mock import patch
from urllib import error

import jsonschema

from scripts.a2_ollama_multimodal_matrix import (
    ROOT,
    append_trial_atomic,
    atomic_write,
    build_matrix,
    classify_public_response,
    complete_partial,
    load_partial,
    ollama_invoke,
    ollama_schema_capability_probe,
    partial_binding,
    sha256_ref,
)
from services.judge.multimodal_provider import (
    ClassifiedProviderTransportError,
    ProviderTransportReceipt,
)
from scripts.a2_generate_round36_multimodal_controls import generate


class OllamaMultimodalMatrixTests(unittest.TestCase):
    def test_round44_capability_probe_distinguishes_plain_json_only(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
            formats = []

            def invoke(_model, payload, _timeout):
                formats.append(payload["format"])
                if isinstance(payload["format"], dict):
                    raise ClassifiedProviderTransportError(
                        ProviderTransportReceipt(
                            schema_version="a2.provider_transport_receipt.v1",
                            error_class="http_client_error",
                            http_status_class="4xx",
                        )
                    )
                return {
                    "response": json.dumps(
                        {
                            "risk_present": False,
                            "taxonomy_classes": [],
                            "summary": "safe",
                        }
                    )
                }

            receipt = ollama_schema_capability_probe(
                model={
                    "model_id": "model",
                    "model_digest": "sha256:" + "a" * 64,
                },
                case={
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                },
                invoke=invoke,
                timeout_seconds=1,
            )
        self.assertEqual(formats, [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["risk_present", "taxonomy_classes", "summary"],
                "properties": {
                    "risk_present": {"type": "boolean"},
                    "taxonomy_classes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "summary": {"type": "string"},
                },
            },
            "json",
        ])
        self.assertFalse(receipt["object_schema_supported"])
        self.assertTrue(receipt["plain_json_supported"])
        self.assertEqual(receipt["probe_state"], "plain_json_only")
        self.assertEqual(len(receipt["attempt_receipts"]), 2)
        self.assertTrue(receipt["runtime_version_hash"].startswith("sha256:"))
        self.assertTrue(receipt["prompt_hash"].startswith("sha256:"))
        self.assertTrue(receipt["output_schema_hash"].startswith("sha256:"))

    def test_round45_unsupported_native_schema_skips_without_network_call(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
            calls = 0

            def invoke(*_args):
                nonlocal calls
                calls += 1
                raise AssertionError("unsupported native schema must be skipped")

            model = {
                "model_id": "model",
                "model_digest": "sha256:" + "a" * 64,
            }
            result = build_matrix(
                cases=[{
                    "case_id": "safe",
                    "taxonomy": "safe_control",
                    "expected_risk": False,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                }],
                models=[model],
                formats=["json_schema"],
                num_predict_values=[64],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=invoke,
                capability_probe_receipts=[{
                    "schema_version": "a2.ollama_schema_capability_probe.v1",
                    "model_id_hash": sha256_ref(model["model_id"]),
                    "model_digest": model["model_digest"],
                    "object_schema_supported": False,
                    "plain_json_supported": False,
                    "probe_state": "unsupported",
                    "object_schema_error_hash": "sha256:" + "c" * 64,
                    "plain_json_error_hash": "sha256:" + "d" * 64,
                    "runtime_version_hash": "sha256:" + "e" * 64,
                    "prompt_hash": "sha256:" + "f" * 64,
                    "output_schema_hash": "sha256:" + "1" * 64,
                    "configured_probe_budget_seconds": 1,
                    "wall_seconds": 0,
                    "attempt_receipts": [{
                        "format_mode": "object_schema",
                        "state": "failed",
                        "wall_seconds": 0,
                        "configured_timeout_seconds": 1,
                        "remaining_budget_at_start_seconds": 1,
                        "network_call_started": False,
                        "error_hash": "sha256:" + "c" * 64,
                    }],
                    "raw_payload_included": False,
                    "release_authority": False,
                    "public_safe": True,
                }],
            )
        self.assertEqual(calls, 0)
        trial = result["trials"][0]
        self.assertEqual(trial["error_class"], "capability_unsupported")
        self.assertFalse(trial["promotion_eligible"])
        self.assertFalse(
            trial["capability_skip_receipt"]["network_call_started"]
        )
        self.assertIsNone(trial["cancellation_receipt"])

    def test_round45_cancellation_receipt_cannot_coexist_with_completed_trial(self):
        schema = json.loads(
            (
                ROOT / "docs/a2/schemas/multimodal_runtime_matrix_v2.schema.json"
            ).read_text(encoding="utf-8")
        )
        trial_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": schema["$defs"],
            "$ref": "#/$defs/trial",
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
            result = build_matrix(
                cases=[{
                    "case_id": "safe",
                    "taxonomy": "safe_control",
                    "expected_risk": False,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                }],
                models=[{
                    "model_id": "model",
                    "model_digest": "sha256:" + "b" * 64,
                }],
                formats=["json"],
                num_predict_values=[64],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=lambda *_: {
                    "response": json.dumps({
                        "risk_present": False,
                        "taxonomy_classes": [],
                        "summary": "safe",
                    })
                },
            )
        invalid = dict(result["trials"][0])
        invalid["cancellation_receipt"] = {
            "schema_version": "a2.model_run_cancellation_receipt.v1",
            "reason": "model_run_budget_exhausted",
            "configured_budget_seconds": 1,
            "network_call_started": False,
            "promotion_eligible": False,
            "release_authority": False,
            "public_safe": True,
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(trial_schema).validate(invalid)

    def test_round44_duration_fields_and_budget_cancellation_are_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
            calls = 0

            def invoke(*_args):
                nonlocal calls
                calls += 1
                return {
                    "response": json.dumps(
                        {
                            "risk_present": False,
                            "taxonomy_classes": [],
                            "summary": "safe",
                        }
                    ),
                    "total_duration": 4_000_000_000,
                    "load_duration": 1_500_000_000,
                    "prompt_eval_duration": 500_000_000,
                    "eval_duration": 2_000_000_000,
                }

            result = build_matrix(
                cases=[{
                    "case_id": "safe",
                    "taxonomy": "safe_control",
                    "expected_risk": False,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                }],
                models=[{
                    "model_id": "model",
                    "model_digest": "sha256:" + "b" * 64,
                }],
                formats=["json"],
                num_predict_values=[64],
                repeats=2,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=invoke,
                maximum_model_run_seconds=0.000001,
            )
        self.assertEqual(calls, 0)
        self.assertEqual(len(result["trials"]), 2)
        for trial in result["trials"]:
            self.assertEqual(trial["error_class"], "model_run_budget_exhausted")
            self.assertFalse(trial["promotion_eligible"])
            self.assertIsNone(trial["observed_risk"])
            self.assertFalse(trial["cancellation_receipt"]["network_call_started"])
        self.assertEqual(result["qualification_state"], "blocked")

        # A normal call records provider-native durations separately from wall time.
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
            result = build_matrix(
                cases=[{
                    "case_id": "safe",
                    "taxonomy": "safe_control",
                    "expected_risk": False,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                }],
                models=[{
                    "model_id": "model",
                    "model_digest": "sha256:" + "c" * 64,
                }],
                formats=["json"],
                num_predict_values=[64],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=invoke,
            )
        durations = result["trials"][0]["provider_durations_seconds"]
        self.assertEqual(durations["provider_total_seconds"], 4.0)
        self.assertEqual(durations["model_load_seconds"], 1.5)
        self.assertEqual(durations["first_inference_seconds"], 2.5)

    def test_round44_schema_rejects_failed_attempt_without_error_hash(self):
        schema = json.loads(
            (
                ROOT / "docs/a2/schemas/multimodal_runtime_matrix_v2.schema.json"
            ).read_text(encoding="utf-8")
        )
        attempt_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": schema["$defs"],
            "$ref": "#/$defs/attemptReceipt",
        }
        failed = {
            "attempt": 1,
            "http_state": "failed",
            "parse_state": "not_attempted",
            "error_class": "timeout",
            "wall_seconds": 0,
            "content_hash": "",
            "thinking_hash": "",
            "content_present": False,
            "thinking_present": False,
            "parse_source": "not_attempted",
            "fallback_probe": False,
            "transport_receipt": {
                "schema_version": "a2.provider_transport_receipt.v1",
                "error_class_hash": "",
                "http_status_class": "",
                "response_body_retained": False,
            },
            "raw_payload_included": False,
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(attempt_schema).validate(failed)

    def test_round39_partial_resume_skips_completed_trial_and_marks_completed(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "attack.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\xff\x00\x00")
            case = {
                "case_id": "resume-attack",
                "taxonomy": "visual_prompt_injection",
                "expected_risk": True,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }
            manifest = {
                "schema_version": "a2.multimodal_runtime_cases.v1",
                "cases": [case],
                "provider_labels_used": False,
                "release_authority": False,
                "public_safe": True,
            }
            models = [{"model_id": "qwen3-vl:4b", "model_digest": "sha256:" + "4" * 64}]
            runtime = {
                "provider_id": "ollama-local",
                "ollama_version": "test",
                "base_url_class": "loopback",
            }
            binding = partial_binding(
                manifest,
                runtime,
                models,
                formats=["json_schema"],
                num_predict_values=[64],
            )
            partial = Path(directory) / "partial.json"
            calls = []

            def invoke(*_):
                calls.append(True)
                return {
                    "response": json.dumps(
                        {
                            "risk_present": True,
                            "taxonomy_classes": ["visual_prompt_injection"],
                            "summary": "risk",
                        }
                    )
                }

            first = build_matrix(
                cases=[case],
                models=models,
                formats=["json_schema"],
                num_predict_values=[64],
                repeats=1,
                runtime=runtime,
                invoke=invoke,
                progress_callback=lambda trial: append_trial_atomic(partial, trial, binding),
            )
            resumed = build_matrix(
                cases=[case],
                models=models,
                formats=["json_schema"],
                num_predict_values=[64],
                repeats=1,
                runtime=runtime,
                invoke=invoke,
                initial_trials=load_partial(partial, binding),
            )
            complete_partial(partial, binding, resumed["trials"])
            persisted = json.loads(partial.read_text(encoding="utf-8"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(first["trials"], resumed["trials"])
        self.assertEqual(persisted["state"], "completed")
        self.assertFalse(persisted["release_authority"])

    def test_round39_partial_binding_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "partial.json"
            binding = {
                "manifest_hash": "sha256:" + "1" * 64,
                "prompt_hash": "sha256:" + "2" * 64,
                "runtime_hash": "sha256:" + "3" * 64,
                "format_plan_hash": "sha256:" + "6" * 64,
                "token_bound_plan_hash": "sha256:" + "7" * 64,
                "model_bindings": [
                    {"model_id": "model", "model_digest": "sha256:" + "4" * 64}
                ],
            }
            complete_partial(path, binding, [])
            changed = dict(binding)
            changed["manifest_hash"] = "sha256:" + "5" * 64
            with self.assertRaisesRegex(ValueError, "binding mismatch"):
                load_partial(path, changed)

    def test_round36_committed_control_manifest_has_five_safe_and_five_attack_cases(self):
        manifest = generate()
        self.assertEqual(
            sum(not case["expected_risk"] for case in manifest["cases"]), 5
        )
        self.assertEqual(sum(case["expected_risk"] for case in manifest["cases"]), 5)
        for case in manifest["cases"]:
            path = ROOT / case["artifact_path"]
            self.assertTrue(path.is_file())
            self.assertEqual(case["artifact_hash"], sha256_ref(path.read_bytes()))
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_runtime_cases.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(manifest)

    def test_round36_distinguishes_empty_invalid_and_semantically_invalid_output(self):
        self.assertEqual(classify_public_response(""), ("empty_response", None))
        self.assertEqual(
            classify_public_response("not-json"), ("nonempty_invalid_json", None)
        )
        self.assertEqual(
            classify_public_response('{"risk_present":"no"}'),
            ("invalid_semantics", None),
        )
        self.assertEqual(
            classify_public_response(
                '{"risk_present":false,"taxonomy_classes":[],"summary":"safe"}'
            ),
            ("valid_json", False),
        )

    def test_round36_matrix_schema_validation_and_fail_closed_sample_gate(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "control.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
            case = {
                "case_id": "safe-control",
                "taxonomy": "safe_control",
                "expected_risk": False,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }

            def invoke(_model, _payload, _timeout):
                return {
                    "response": json.dumps(
                        {
                            "risk_present": False,
                            "taxonomy_classes": [],
                            "summary": "safe",
                        }
                    ),
                    "done_reason": "stop",
                    "eval_count": 4,
                }

            result = build_matrix(
                cases=[case],
                models=[
                    {
                        "model_id": "qwen3-vl:4b",
                        "model_digest": "sha256:" + "1" * 64,
                    }
                ],
                formats=["plain"],
                num_predict_values=[256],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=invoke,
            )
        self.assertEqual(result["qualification_state"], "blocked")
        self.assertIn("multimodal_safe_sample_minimum_not_met", result["blockers"])
        self.assertIn("multimodal_attack_sample_minimum_not_met", result["blockers"])
        self.assertEqual(result["trials"][0]["startup_class"], "cold")
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_runtime_matrix_v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(result)

    def test_round36_provider_failure_never_becomes_eligible(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "attack.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\xff\x00\x00")
            case = {
                "case_id": "attack-control",
                "taxonomy": "visual_prompt_injection",
                "expected_risk": True,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }
            result = build_matrix(
                cases=[case],
                models=[
                    {
                        "model_id": "llava:7b",
                        "model_digest": "sha256:" + "2" * 64,
                    }
                ],
                formats=["json_schema"],
                num_predict_values=[256],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=lambda *_: (_ for _ in ()).throw(RuntimeError("private")),
            )
        trial = result["trials"][0]
        self.assertEqual(trial["http_state"], "failed")
        self.assertEqual(trial["parse_state"], "not_attempted")
        self.assertEqual(trial["error_class"], "provider_failure")
        summary = next(iter(result["binding_summaries"].values()))
        self.assertEqual(summary["eligible_count"], 0)
        self.assertEqual(result["qualification_state"], "blocked")

    def test_round42_thinking_only_response_retries_once_and_stays_ineligible(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
            calls = []

            def invoke(*_):
                calls.append(True)
                return {"response": "", "thinking": '{"risk_present":false}'}

            result = build_matrix(
                cases=[
                    {
                        "case_id": "thinking-only",
                        "taxonomy": "safe_control",
                        "expected_risk": False,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                ],
                models=[
                    {
                        "model_id": "qwen3-vl:4b",
                        "model_digest": "sha256:" + "8" * 64,
                    }
                ],
                formats=["json_schema"],
                num_predict_values=[64],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=invoke,
                invalid_response_retries=1,
            )
        trial = result["trials"][0]
        self.assertEqual(len(calls), 2)
        self.assertEqual(trial["parse_state"], "empty_response")
        self.assertTrue(trial["thinking_present"])
        self.assertEqual(len(trial["attempt_receipts"]), 2)
        self.assertIsNone(trial["observed_risk"])

    def test_round43_json_fallback_probe_cannot_enter_metric_denominator(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "safe.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
            calls = []

            def invoke(_model, payload, _timeout):
                calls.append(payload["format"])
                if isinstance(payload["format"], dict):
                    return {"response": "invalid"}
                return {
                    "response": json.dumps(
                        {
                            "risk_present": False,
                            "taxonomy_classes": [],
                            "summary": "safe",
                        }
                    )
                }

            result = build_matrix(
                cases=[{
                    "case_id": "safe",
                    "taxonomy": "safe_control",
                    "expected_risk": False,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                }],
                models=[{
                    "model_id": "qwen3-vl:4b",
                    "model_digest": "sha256:" + "4" * 64,
                }],
                formats=["json_schema"],
                num_predict_values=[64],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=invoke,
            )
        trial = result["trials"][0]
        self.assertEqual(calls, [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["risk_present", "taxonomy_classes", "summary"],
                "properties": {
                    "risk_present": {"type": "boolean"},
                    "taxonomy_classes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "summary": {"type": "string"},
                },
            },
            "json",
        ])
        self.assertTrue(trial["fallback_probe_used"])
        self.assertFalse(trial["promotion_eligible"])
        self.assertEqual(
            next(iter(result["binding_summaries"].values()))["eligible_count"], 0
        )
        self.assertIn(
            "multimodal_fallback_probe_not_promotion_eligible", result["blockers"]
        )

    def test_round43_metrics_hidden_below_minimum_and_taxonomy_wilson_reported(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifacts = []
            cases = []
            for index, expected in enumerate((False, True)):
                artifact = Path(directory) / f"{index}.ppm"
                artifact.write_bytes(b"P6\n1 1\n255\n\x00\x00\xff")
                artifacts.append(artifact)
                cases.append({
                    "case_id": f"case-{index}",
                    "taxonomy": (
                        "safe_control" if not expected else "visual_prompt_injection"
                    ),
                    "expected_risk": expected,
                    "artifact_path": artifact.relative_to(ROOT).as_posix(),
                    "artifact_hash": sha256_ref(artifact.read_bytes()),
                })

            result = build_matrix(
                cases=cases,
                models=[{
                    "model_id": "model",
                    "model_digest": "sha256:" + "5" * 64,
                }],
                formats=["json"],
                num_predict_values=[64],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                invoke=lambda *_: {
                    "response": json.dumps({
                        "risk_present": True,
                        "taxonomy_classes": [],
                        "summary": "observation",
                    })
                },
                minimum_safe_samples=2,
                minimum_attack_samples=2,
                minimum_taxonomy_samples=1,
            )
        summary = next(iter(result["binding_summaries"].values()))
        self.assertIsNone(summary["sensitivity"])
        self.assertIsNone(summary["specificity"])
        self.assertIsNone(summary["balanced_accuracy"])
        taxonomy = summary["taxonomy_metrics"]["visual_prompt_injection"]
        self.assertEqual(taxonomy["eligible_count"], 1)
        self.assertEqual(taxonomy["sensitivity"], 1)
        self.assertEqual(len(taxonomy["sensitivity_wilson_95"]), 2)

    def test_round44_transport_receipt_classifies_failure_table_without_body(self):
        invoke = ollama_invoke("http://127.0.0.1:11434")
        cases = [
            (error.HTTPError("http://local", 400, "private body", {}, None), "http_client_error", "4xx"),
            (error.HTTPError("http://local", 401, "private body", {}, None), "authentication_error", "4xx"),
            (error.HTTPError("http://local", 404, "private body", {}, None), "http_client_error", "4xx"),
            (error.HTTPError("http://local", 429, "private body", {}, None), "rate_limited", "4xx"),
            (error.HTTPError("http://local", 500, "private body", {}, None), "http_server_error", "5xx"),
            (error.HTTPError("http://local", 503, "private body", {}, None), "http_server_error", "5xx"),
            (error.URLError(ConnectionResetError()), "connection_reset", ""),
            (error.URLError(ConnectionRefusedError()), "connection_refused", ""),
            (error.URLError(socket.timeout()), "timeout", ""),
        ]
        for failure, expected_class, expected_status_class in cases:
            with self.subTest(expected_class=expected_class, status=expected_status_class):
                with patch(
                    "scripts.a2_ollama_multimodal_matrix.request.urlopen",
                    side_effect=failure,
                ):
                    with self.assertRaises(ClassifiedProviderTransportError) as caught:
                        invoke("model", {}, 1)
                self.assertEqual(caught.exception.error_class, expected_class)
                self.assertEqual(
                    caught.exception.http_status_class, expected_status_class
                )
                self.assertNotIn("private body", str(caught.exception))
                receipt = caught.exception.receipt.public_receipt()
                self.assertTrue(receipt["error_class_hash"].startswith("sha256:"))
                self.assertFalse(receipt["response_body_retained"])

    def test_round38_timeout_receipt_is_persisted_after_each_trial(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "attack.ppm"
            artifact.write_bytes(b"P6\n1 1\n255\n\xff\x00\x00")
            partial = Path(directory) / "partial.json"
            result = build_matrix(
                cases=[
                    {
                        "case_id": "attack-control",
                        "taxonomy": "visual_prompt_injection",
                        "expected_risk": True,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                ],
                models=[
                    {
                        "model_id": "qwen3-vl:4b",
                        "model_digest": "sha256:" + "3" * 64,
                    }
                ],
                formats=["json_schema"],
                num_predict_values=[64],
                repeats=1,
                runtime={
                    "provider_id": "ollama-local",
                    "ollama_version": "test",
                    "base_url_class": "loopback",
                },
                timeout_seconds=0.01,
                invoke=lambda *_: (_ for _ in ()).throw(TimeoutError()),
                progress_callback=lambda trial: append_trial_atomic(partial, trial),
            )
            persisted = json.loads(partial.read_text(encoding="utf-8"))
            partial_schema = json.loads(
                (
                    ROOT
                    / "docs/a2/schemas/multimodal_runtime_partial.schema.json"
                ).read_text(encoding="utf-8")
            )
            jsonschema.Draft202012Validator(partial_schema).validate(persisted)
        self.assertEqual(result["trials"][0]["error_class"], "timeout")
        self.assertIn("multimodal_provider_failure_observed", result["blockers"])
        self.assertEqual(persisted["state"], "in_progress")
        self.assertEqual(len(persisted["trials"]), 1)
        self.assertEqual(persisted["trials"][0]["error_class"], "timeout")
        self.assertFalse(persisted["release_authority"])

    def test_round40_partial_duplicate_key_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "partial.json"
            binding = {
                "manifest_hash": "sha256:" + "1" * 64,
                "prompt_hash": "sha256:" + "2" * 64,
                "runtime_hash": "sha256:" + "3" * 64,
                "format_plan_hash": "sha256:" + "4" * 64,
                "token_bound_plan_hash": "sha256:" + "5" * 64,
                "model_bindings": [
                    {"model_id": "model", "model_digest": "sha256:" + "6" * 64}
                ],
            }
            trial = {
                "model_id": "model",
                "model_digest": "sha256:" + "6" * 64,
                "format_mode": "json",
                "num_predict": 64,
                "case_id": "case",
                "artifact_hash": "sha256:" + "7" * 64,
                "repeat": 1,
            }
            atomic_write(
                path,
                {
                    "schema_version": "a2.multimodal_runtime_partial.v1",
                    "state": "in_progress",
                    "binding": binding,
                    "trials": [trial, dict(trial)],
                    "release_authority": False,
                    "public_safe": True,
                },
            )
            with self.assertRaisesRegex(ValueError, "duplicate trial keys"):
                load_partial(path, binding)

    def test_round40_crash_before_partial_completion_preserves_in_progress(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "partial.json"
            binding = {
                "manifest_hash": "sha256:" + "1" * 64,
                "prompt_hash": "sha256:" + "2" * 64,
                "runtime_hash": "sha256:" + "3" * 64,
                "format_plan_hash": "sha256:" + "4" * 64,
                "token_bound_plan_hash": "sha256:" + "5" * 64,
                "model_bindings": [],
            }
            atomic_write(
                path,
                {
                    "schema_version": "a2.multimodal_runtime_partial.v1",
                    "state": "in_progress",
                    "binding": binding,
                    "trials": [],
                    "release_authority": False,
                    "public_safe": True,
                },
            )
            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                complete_partial(path, binding, [], crash_before_completion=True)
            persisted = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["state"], "in_progress")


if __name__ == "__main__":
    unittest.main()
