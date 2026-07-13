import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from scripts.a2_ollama_multimodal_matrix import (
    ROOT,
    build_matrix,
    classify_public_response,
    sha256_ref,
)
from scripts.a2_generate_round36_multimodal_controls import generate


class OllamaMultimodalMatrixTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
