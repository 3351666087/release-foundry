import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.a2_ollama_multimodal_latency_probe import ROOT, build_probe


def receipt(profile, *, load, prompt, token, completed=False):
    return {
        "profile": profile,
        "num_predict": 8,
        "format_mode": "plain",
        "state": "completed" if completed else "failed",
        "parse_state": "valid_json" if completed else "invalid_structured_output",
        "error_class": "" if completed else "invalid_structured_output",
        "phase_receipt": {
            "image_read_and_base64_seconds": 0.001,
            "caller_wall_seconds": load + prompt + token,
            "provider_total_seconds": load + prompt + token,
            "model_load_seconds": load,
            "prompt_eval_seconds": prompt,
            "token_eval_seconds": token,
            "transport_and_client_residual_seconds": 0.0,
        },
        "response_hash": "sha256:" + "a" * 64,
        "raw_response_included": False,
        "release_authority": False,
        "public_safe": True,
    }


class OllamaLatencyProbeTests(unittest.TestCase):
    def test_phase_diagnosis_uses_provider_timings_even_when_output_is_invalid(self):
        values = [
            receipt("cold_plain_32", load=8, prompt=57, token=3),
            receipt("warm_plain_32", load=0.5, prompt=0.1, token=3),
            receipt("warm_plain_8", load=0.5, prompt=0.1, token=0.8),
            receipt("warm_json_schema_8", load=0.5, prompt=0.1, token=0.8),
        ]
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            image = Path(directory) / "safe.png"
            image.write_bytes(b"safe")
            with patch(
                "scripts.a2_ollama_multimodal_latency_probe._unload",
                return_value="requested",
            ), patch(
                "scripts.a2_ollama_multimodal_latency_probe._probe",
                side_effect=values,
            ):
                result = build_probe(
                    base_url="http://127.0.0.1:11434",
                    model_id="qwen",
                    model_digest="sha256:" + "b" * 64,
                    image_path=image,
                    timeout_seconds=90,
                )
        self.assertIn("model_warmup_material", result["diagnosis"])
        self.assertIn("image_preprocessing_not_material", result["diagnosis"])
        self.assertNotIn(
            "bounded_timeout_or_failure_prevents_phase_attribution",
            result["diagnosis"],
        )
        self.assertEqual(result["qualification_state"], "blocked")


if __name__ == "__main__":
    unittest.main()
