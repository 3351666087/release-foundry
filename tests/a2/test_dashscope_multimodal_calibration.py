import tempfile
import unittest
import json
import base64
from pathlib import Path

from PIL import Image

from scripts.a2_dashscope_multimodal_calibration import build_calibration
from scripts.a2_ollama_multimodal_matrix import ROOT, sha256_ref


class DashScopeMultimodalCalibrationTests(unittest.TestCase):
    def test_round36_ppm_is_transcoded_for_cloud_transport_and_contract_requested(self):
        captured = {}

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
                endpoint_class="unit",
                invoke=invoke,
            )
        data_uri = captured["messages"][0]["content"][0]["image_url"]["url"]
        transmitted = base64.b64decode(data_uri.split(",", 1)[1])
        self.assertTrue(data_uri.startswith("data:image/png;base64,"))
        self.assertEqual(transmitted[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(captured["response_format"], {"type": "json_object"})
        self.assertEqual(result["observations"][0]["parse_state"], "valid_json")
        self.assertFalse(result["observations"][0]["observed_risk"])

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
                endpoint_class="unit",
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


if __name__ == "__main__":
    unittest.main()
