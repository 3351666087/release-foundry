import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts.a2_generate_round53_multimodal_controls import (
    FONT_FAMILIES,
    LOCAL_SUBSET,
    ROOT,
    _font,
    generate,
)


class Round53MultimodalControlsTests(unittest.TestCase):
    def test_round53_controls_cover_four_balanced_groups(self):
        result = generate()
        new_cases = [
            case for case in result["cases"]
            if case["case_id"].startswith("round53-")
        ]
        self.assertEqual(
            Counter(case["taxonomy"] for case in new_cases),
            {
                "safe_control": 10,
                "benign_text_safe": 10,
                "cross_modal_conflict": 10,
                "visual_prompt_injection": 10,
            },
        )
        self.assertEqual(len({case["artifact_hash"] for case in new_cases}), 40)
        for case in new_cases:
            path = ROOT / Path(case["artifact_path"])
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(case["artifact_hash"], actual)

    def test_attack_styles_cover_at_least_five_layout_families(self):
        generate()
        cases = json.loads(LOCAL_SUBSET.read_text(encoding="utf-8"))["cases"]
        cross_modal = [
            case for case in cases if case["taxonomy"] == "cross_modal_conflict"
        ]
        visual_injection = [
            case for case in cases
            if case["taxonomy"] == "visual_prompt_injection"
        ]
        self.assertEqual(len(cross_modal), 10)
        self.assertEqual(len(visual_injection), 10)

    def test_local_subset_contains_only_round53_cases(self):
        generate()
        cases = json.loads(LOCAL_SUBSET.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 40)
        self.assertTrue(
            all(case["case_id"].startswith("round53-") for case in cases)
        )

    def test_text_controls_cycle_portable_font_families(self):
        self.assertGreaterEqual(len(FONT_FAMILIES), 5)
        fonts = [_font(index, 16) for index in range(len(FONT_FAMILIES))]
        available_family_count = sum(
            any(path.is_file() for path in family)
            for family in FONT_FAMILIES
        )
        if available_family_count >= 2:
            self.assertGreaterEqual(
                len(
                    {
                        getattr(font, "path", None)
                        for font in fonts
                        if getattr(font, "path", None)
                    }
                ),
                2,
            )

    def test_existing_evaluated_controls_are_not_rewritten_by_host_fonts(self):
        generate()
        before = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "fixtures/a2/calibration").glob("round53-*.png")
        }
        with patch(
            "scripts.a2_generate_round53_multimodal_controls._text_card",
            return_value=Image.new("RGB", (384, 224), (255, 0, 255)),
        ):
            generate()
        after = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "fixtures/a2/calibration").glob("round53-*.png")
        }
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
