import unittest
from collections import Counter

from scripts.a2_generate_round48_multimodal_controls import generate


class Round48MultimodalControlsTests(unittest.TestCase):
    def test_each_rotation_and_jpeg_bucket_has_three_distinct_sources(self):
        result = generate()
        expanded = [
            case for case in result["cases"]
            if case["case_id"].startswith("round48-attack-")
        ]
        buckets = Counter()
        sources = {}
        for case in expanded:
            perturbation = case["perturbation"]
            if perturbation["kind"] == "rotation":
                bucket = f"rotation_degrees:{perturbation['rotation_degrees']}"
            else:
                bucket = f"jpeg_quality:{perturbation['jpeg_quality']}"
            buckets[bucket] += 1
            sources.setdefault(bucket, set()).add(case["source_case_id"])
        self.assertEqual(
            buckets,
            Counter({
                "rotation_degrees:5": 3,
                "rotation_degrees:10": 3,
                "jpeg_quality:40": 3,
                "jpeg_quality:60": 3,
                "jpeg_quality:80": 3,
            }),
        )
        self.assertTrue(all(len(values) == 3 for values in sources.values()))


if __name__ == "__main__":
    unittest.main()
