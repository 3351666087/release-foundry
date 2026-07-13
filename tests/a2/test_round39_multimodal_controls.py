import json
import unittest
from collections import Counter

import jsonschema

from scripts.a2_generate_round39_multimodal_controls import generate
from scripts.a2_ollama_multimodal_matrix import ROOT


class Round39MultimodalControlTests(unittest.TestCase):
    def test_controls_are_deterministic_and_cover_required_variants(self):
        first = generate()
        second = generate()
        schema = json.loads((ROOT / "docs/a2/schemas/multimodal_runtime_cases.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(second)
        self.assertEqual(
            [case["artifact_hash"] for case in first["cases"]],
            [case["artifact_hash"] for case in second["cases"]],
        )
        counts = Counter(case["taxonomy"] for case in second["cases"])
        self.assertEqual(len(second["cases"]), 12)
        self.assertEqual(sum(not case["expected_risk"] for case in second["cases"]), 4)
        self.assertEqual(sum(case["expected_risk"] for case in second["cases"]), 8)
        self.assertEqual(sum("user_text" in case for case in second["cases"]), 2)
        self.assertEqual(counts["visual_prompt_injection"], 2)
        self.assertEqual(counts["cross_modal_conflict"], 2)
        self.assertEqual(counts["unsafe_content_evasion"], 2)
        self.assertEqual(counts["hallucinated_text"], 2)


if __name__ == "__main__":
    unittest.main()
