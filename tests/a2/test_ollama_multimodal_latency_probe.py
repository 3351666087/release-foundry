import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.a2_ollama_multimodal_latency_probe import ROOT, build_probe


def receipt(
    profile,
    *,
    load,
    prompt,
    token,
    completed=False,
    num_predict=8,
    format_mode="plain",
):
    return {
        "profile": profile,
        "num_predict": num_predict,
        "format_mode": format_mode,
        "schema_mode": "full",
        "input_mode": "image",
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
        "response_length_bytes": 32,
        "first_nonempty_character_class": "object_open",
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

    def test_text_only_minimal_schema_profile_is_public_safe(self):
        values = [
            {
                **receipt(
                    "warm_minimal_enum_32",
                    load=0.1,
                    prompt=0.1,
                    token=0.3,
                    completed=True,
                    num_predict=32,
                    format_mode="json_schema",
                ),
                "schema_mode": "minimal_enum",
                "input_mode": "text_only_control",
            }
        ]
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
                image_path=None,
                timeout_seconds=90,
                profiles=(
                    (
                        "warm_minimal_enum_32",
                        32,
                        "json_schema",
                        "minimal_enum",
                    ),
                ),
            )
        self.assertEqual(result["input_mode"], "text_only_control")
        self.assertIsNone(result["artifact_hash"])
        self.assertEqual(result["completed_profile_count"], 1)

    def test_custom_json_schema_token_sweep_is_supported(self):
        values = [
            receipt(
                "warm_json_schema_16",
                load=0.1,
                prompt=0.1,
                token=1,
                num_predict=16,
                format_mode="json_schema",
            ),
            receipt(
                "warm_json_schema_32",
                load=0.1,
                prompt=0.1,
                token=2,
                num_predict=32,
                format_mode="json_schema",
            ),
            receipt(
                "warm_json_schema_64",
                load=0.1,
                prompt=0.1,
                token=4,
                num_predict=64,
                format_mode="json_schema",
            ),
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
                    profiles=(
                        ("warm_json_schema_16", 16, "json_schema"),
                        ("warm_json_schema_32", 32, "json_schema"),
                        ("warm_json_schema_64", 64, "json_schema"),
                    ),
                )
        self.assertEqual(len(result["profiles"]), 3)
        self.assertEqual(
            [item["num_predict"] for item in result["profiles"]],
            [16, 32, 64],
        )
        self.assertEqual(result["qualification_state"], "blocked")


if __name__ == "__main__":
    unittest.main()
