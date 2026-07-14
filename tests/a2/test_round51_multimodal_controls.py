import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

from scripts.a2_generate_round51_multimodal_controls import (
    LOCAL_SUBSET,
    ROOT,
    generate,
)


class Round51MultimodalControlsTests(unittest.TestCase):
    def test_new_controls_are_distinct_hash_bound_and_balanced(self):
        result = generate()
        new_cases = [
            case
            for case in result["cases"]
            if case["case_id"].startswith("round51-")
        ]
        counts = Counter(case["taxonomy"] for case in new_cases)
        self.assertEqual(
            counts,
            {
                "safe_control": 5,
                "benign_text_safe": 5,
                "cross_modal_conflict": 5,
            },
        )
        self.assertEqual(len({case["artifact_hash"] for case in new_cases}), 15)
        for case in new_cases:
            path = ROOT / Path(case["artifact_path"])
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(case["artifact_hash"], actual)

    def test_local_subset_contains_only_the_fifteen_round51_cases(self):
        generate()
        cases = json.loads(LOCAL_SUBSET.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(cases), 15)
        self.assertTrue(
            all(case["case_id"].startswith("round51-") for case in cases)
        )


if __name__ == "__main__":
    unittest.main()
