import json
import unittest

import jsonschema

from scripts.a2_generate_round43_multimodal_controls import ROOT, generate, sha256_ref


class Round43MultimodalControlTests(unittest.TestCase):
    def test_round43_controls_cover_new_safe_and_attack_distributions(self):
        manifest = generate()
        safe = [case for case in manifest["cases"] if not case["expected_risk"]]
        attack = [case for case in manifest["cases"] if case["expected_risk"]]
        self.assertEqual(len(safe), 5)
        self.assertEqual(len(attack), 5)
        self.assertGreaterEqual(
            sum("low-contrast" in case["case_id"] for case in attack), 2
        )
        self.assertGreaterEqual(
            sum(
                any(token in case["case_id"] for token in ("ocr-", "confusable"))
                for case in attack
            ),
            3,
        )
        for case in manifest["cases"]:
            path = ROOT / case["artifact_path"]
            self.assertEqual(case["artifact_hash"], sha256_ref(path))
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_runtime_cases.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(manifest)


if __name__ == "__main__":
    unittest.main()
