import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

from scripts.a2_generate_round52_multimodal_controls import (
    LOCAL_SUBSET,
    ROOT,
    generate,
)


class Round52MultimodalControlsTests(unittest.TestCase):
    def test_new_controls_are_distinct_hash_bound_and_balanced(self):
        result = generate()
        new_cases = [
            case
            for case in result["cases"]
            if case["case_id"].startswith("round52-")
        ]
        self.assertEqual(
            Counter(case["taxonomy"] for case in new_cases),
            {"safe_control": 15, "benign_text_safe": 15},
        )
        self.assertEqual(len({case["artifact_hash"] for case in new_cases}), 30)
        for case in new_cases:
            path = ROOT / Path(case["artifact_path"])
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(case["artifact_hash"], actual)

    def test_round51_and_round52_each_safe_category_reaches_twenty(self):
        result = generate()
        recent = [
            case
            for case in result["cases"]
            if case["case_id"].startswith(("round51-", "round52-"))
        ]
        counts = Counter(case["taxonomy"] for case in recent)
        self.assertGreaterEqual(counts["safe_control"], 20)
        self.assertGreaterEqual(counts["benign_text_safe"], 20)

    def test_local_subset_contains_only_thirty_round52_controls(self):
        generate()
        cases = json.loads(LOCAL_SUBSET.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 30)
        self.assertTrue(
            all(case["case_id"].startswith("round52-") for case in cases)
        )
        self.assertTrue(all(case["expected_risk"] is False for case in cases))


if __name__ == "__main__":
    unittest.main()
