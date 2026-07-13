import base64
import json
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path

import jsonschema
from PIL import Image

from scripts.a2_dashscope_multimodal_calibration import build_calibration
from scripts.a2_dashscope_multimodal_calibration import (
    ProviderRateLimited,
    ProviderServerFailure,
    cloud_transport,
)
from scripts.a2_generate_round37_multimodal_controls import generate
from scripts.a2_ollama_multimodal_matrix import ROOT, sha256_ref


class DashScopeMultimodalCalibrationTests(unittest.TestCase):
    def test_round36_ppm_is_transcoded_for_cloud_transport_and_contract_requested(self):
        captured = {}
        source_ppm = b""

        def invoke(payload, _timeout):
            captured.update(payload)
            return {
                "model": "qwen-vl-plus",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "risk_present": False,
                                    "taxonomy_classes": [],
                                    "summary": "safe control",
                                }
                            )
                        }
                    }
                ],
            }

        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "control.ppm"
            Image.new("RGB", (2, 2), (20, 40, 60)).save(artifact, format="PPM")
            source_ppm = artifact.read_bytes()
            result = build_calibration(
                cases=[
                    {
                        "case_id": "safe",
                        "taxonomy": "safe_control",
                        "expected_risk": False,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                ],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
            )
        data_uri = captured["messages"][0]["content"][0]["image_url"]["url"]
        transmitted = base64.b64decode(data_uri.split(",", 1)[1])
        self.assertTrue(data_uri.startswith("data:image/png;base64,"))
        self.assertEqual(transmitted[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertEqual(result["observations"][0]["parse_state"], "valid_json")
        self.assertFalse(result["observations"][0]["observed_risk"])
        observation = result["observations"][0]
        self.assertEqual(observation["transport_artifact_hash"], sha256_ref(transmitted))
        second, _ = cloud_transport(source_ppm, ".ppm")
        self.assertEqual(transmitted, second)

    def test_round36_cloud_provider_failure_is_hash_safe_and_blocked(self):
        sentinel_secret = "unit-test-secret-value-that-must-never-be-persisted"
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "control.png"
            artifact.write_bytes(b"public-control")
            result = build_calibration(
                cases=[
                    {
                        "case_id": "safe",
                        "taxonomy": "safe_control",
                        "expected_risk": False,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                ],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=lambda *_: (_ for _ in ()).throw(RuntimeError(sentinel_secret)),
            )
        observation = result["observations"][0]
        serialized = json.dumps(result, sort_keys=True)
        self.assertEqual(observation["error_class"], "provider_failure")
        self.assertEqual(observation["parse_state"], "not_attempted")
        self.assertEqual(result["qualification_state"], "blocked")
        self.assertFalse(result["secret_included"])
        self.assertNotIn(sentinel_secret, serialized)
        self.assertNotIn("authorization", serialized.lower())
        self.assertNotIn("bearer ", serialized.lower())

    def test_round37_changed_ppm_changes_source_and_transport_bindings(self):
        first = b"P6\n1 1\n255\n\x01\x02\x03"
        second = b"P6\n1 1\n255\n\x01\x02\x04"
        first_transport, _ = cloud_transport(first, ".ppm")
        second_transport, _ = cloud_transport(second, ".ppm")
        self.assertNotEqual(sha256_ref(first), sha256_ref(second))
        self.assertNotEqual(sha256_ref(first_transport), sha256_ref(second_transport))

    def test_round37_response_identity_latency_and_error_classes_block(self):
        cases = []
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            for index in range(10):
                artifact = Path(directory) / f"{index}.png"
                Image.new("RGB", (1, 1), (index, index, index)).save(artifact)
                cases.append(
                    {
                        "case_id": str(index),
                        "taxonomy": "safe_control" if index < 5 else "attack",
                        "expected_risk": index >= 5,
                        "artifact_path": artifact.relative_to(ROOT).as_posix(),
                        "artifact_hash": sha256_ref(artifact.read_bytes()),
                    }
                )
            calls = iter(
                [
                    ProviderRateLimited(),
                    ProviderServerFailure(),
                    TimeoutError(),
                    ValueError(),
                    RuntimeError(),
                ]
            )

            def invoke(payload, _timeout):
                time.sleep(0.002)
                try:
                    raise next(calls)
                except StopIteration:
                    return {
                        "model": "wrong-model",
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "risk_present": True,
                                            "taxonomy_classes": ["attack"],
                                            "summary": "risk",
                                        }
                                    )
                                }
                            }
                        ],
                    }

            result = build_calibration(
                cases=cases,
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                invoke=invoke,
                maximum_p95_seconds=0.000000001,
            )
        error_classes = {item["error_class"] for item in result["observations"]}
        self.assertTrue(
            {"rate_limited", "provider_server_failure", "timeout", "provider_rejected_request", "provider_failure"}
            <= error_classes
        )
        self.assertIn("dashscope_response_model_identity_mismatch", result["blockers"])
        self.assertIn("dashscope_latency_qualification_not_met", result["blockers"])
        self.assertEqual(result["qualification_state"], "blocked")

    def test_round37_malformed_envelope_and_empty_content_are_explicitly_noneligible(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            artifact = Path(directory) / "control.png"
            Image.new("RGB", (1, 1), (20, 40, 60)).save(artifact)
            case = {
                "case_id": "safe",
                "taxonomy": "safe_control",
                "expected_risk": False,
                "artifact_path": artifact.relative_to(ROOT).as_posix(),
                "artifact_hash": sha256_ref(artifact.read_bytes()),
            }
            responses = iter(
                [
                    {"model": "qwen-vl-plus", "choices": []},
                    {
                        "model": "qwen-vl-plus",
                        "choices": [{"message": {"content": ""}}],
                    },
                ]
            )
            result = build_calibration(
                cases=[case],
                model_id="qwen-vl-plus",
                endpoint_region="beijing",
                repeats=2,
                invoke=lambda *_: next(responses),
            )
        malformed, empty = result["observations"]
        self.assertEqual(malformed["http_state"], "failed")
        self.assertEqual(malformed["error_class"], "malformed_envelope")
        self.assertEqual(malformed["parse_state"], "not_attempted")
        self.assertEqual(empty["http_state"], "completed")
        self.assertEqual(empty["parse_state"], "empty_response")
        self.assertIsNone(empty["observed_risk"])
        self.assertEqual(result["metrics"]["eligible_count"], 0)
        self.assertIn("dashscope_provider_failure_observed", result["blockers"])
        self.assertIn(
            "dashscope_invalid_structured_output_observed", result["blockers"]
        )

    def test_round37_control_generator_is_deterministic_and_meets_taxonomy_floor(self):
        first = generate()
        first_hashes = {
            case["case_id"]: case["artifact_hash"] for case in first["cases"]
        }
        second = generate()
        second_hashes = {
            case["case_id"]: case["artifact_hash"] for case in second["cases"]
        }
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_runtime_cases.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(second)
        counts = Counter(case["taxonomy"] for case in second["cases"])
        self.assertEqual(first_hashes, second_hashes)
        self.assertEqual(len(second["cases"]), 20)
        self.assertEqual(sum(not case["expected_risk"] for case in second["cases"]), 8)
        self.assertEqual(sum(case["expected_risk"] for case in second["cases"]), 12)
        self.assertEqual(counts["no_text_hallucination_safe"], 5)
        self.assertEqual(counts["benign_text_safe"], 3)
        for taxonomy in (
            "visual_prompt_injection",
            "cross_modal_conflict",
            "unsafe_content_evasion",
            "hallucinated_text",
        ):
            self.assertEqual(counts[taxonomy], 3)

if __name__ == "__main__":
    unittest.main()
