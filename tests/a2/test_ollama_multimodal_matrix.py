import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from scripts.a2_ollama_multimodal_matrix import (
    ROOT,
    append_trial_atomic,
    atomic_write,
    build_matrix,
    classify_public_response,
    complete_partial,
    load_partial,
    partial_binding,
    sha256_ref,
)
from scripts.a2_generate_round36_multimodal_controls import generate


class OllamaMultimodalMatrixTests(unittest.TestCase):
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
