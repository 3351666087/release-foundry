import json
import unittest
from pathlib import Path

import jsonschema

from scripts.a2_generate_round40_multimodal_controls import MANIFEST, ROOT, generate
from scripts.a2_ollama_multimodal_matrix import sha256_ref


class Round40MultimodalControlsTests(unittest.TestCase):
    def test_controls_are_deterministic_bound_and_schema_valid(self):
        first = generate()
        first_bytes = {
            case["artifact_path"]: (ROOT / case["artifact_path"]).read_bytes()
            for case in first["cases"]
        }
        second = generate()
        self.assertEqual(first, second)
        self.assertEqual(len(second["cases"]), 12)
        self.assertEqual(
            {
                case["artifact_path"]: (ROOT / case["artifact_path"]).read_bytes()
                for case in second["cases"]
            },
            first_bytes,
        )
        self.assertEqual(
            {case["source_case_id"] for case in second["cases"]},
            {"round37-hallucination-1", "round37-hallucination-2"},
        )
        self.assertEqual(
            {case["perturbation"]["kind"] for case in second["cases"]},
            {"jpeg_compression", "rescaling"},
        )
        for case in second["cases"]:
            self.assertEqual(
                sha256_ref((ROOT / case["artifact_path"]).read_bytes()),
                case["artifact_hash"],
            )
        schema = json.loads(
            (
                ROOT / "docs/a2/schemas/multimodal_runtime_cases.schema.json"
            ).read_text(encoding="utf-8")
        )
        jsonschema.Draft202012Validator(schema).validate(second)
        self.assertEqual(json.loads(MANIFEST.read_text(encoding="utf-8")), second)


if __name__ == "__main__":
    unittest.main()
