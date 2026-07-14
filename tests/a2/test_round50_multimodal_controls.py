import hashlib
import unittest
from collections import defaultdict
from pathlib import Path

from scripts.a2_generate_round50_multimodal_controls import (
    REPLACED_DUPLICATE_CASE_ID,
    REVIEW_MANIFEST,
    ROOT,
    generate,
)


class Round50MultimodalControlsTests(unittest.TestCase):
    def test_manifest_closes_distinct_source_gaps_without_duplicate_inflation(self):
        result = generate()
        self.assertNotIn(
            REPLACED_DUPLICATE_CASE_ID,
            {case["case_id"] for case in result["cases"]},
        )

        buckets = defaultdict(list)
        for case in result["cases"]:
            perturbation = case.get("perturbation")
            if not perturbation:
                continue
            if perturbation["kind"] == "rotation":
                bucket = f"rotation_degrees:{perturbation['rotation_degrees']}"
            else:
                bucket = f"jpeg_quality:{perturbation['jpeg_quality']}"
            buckets[bucket].append(case)

        expected_minimums = {
            "rotation_degrees:2": 3,
            "rotation_degrees:6": 3,
            "rotation_degrees:10": 4,
            "jpeg_quality:43": 3,
            "jpeg_quality:53": 3,
            "jpeg_quality:60": 4,
        }
        for bucket, minimum in expected_minimums.items():
            values = buckets[bucket]
            source_hashes = {case["source_case_hash"] for case in values}
            self.assertGreaterEqual(len(values), minimum, bucket)
            self.assertEqual(len(values), len(source_hashes), bucket)

    def test_new_taxonomy_and_safe_controls_are_distinct_and_hash_bound(self):
        result = generate()
        new_cases = [
            case for case in result["cases"] if case["case_id"].startswith("round50-")
        ]
        safe = [
            case
            for case in new_cases
            if not case["expected_risk"] and case["taxonomy"] == "safe_control"
        ]
        visual = [
            case
            for case in new_cases
            if case["case_id"].startswith(
                "round50-attack-visual_prompt_injection-"
            )
            and "source_case_id" not in case
        ]
        conflict = [
            case
            for case in new_cases
            if case["case_id"].startswith("round50-attack-cross_modal_conflict-")
            and "source_case_id" not in case
        ]
        self.assertEqual(len(safe), 5)
        self.assertEqual(len(visual), 5)
        self.assertEqual(len(conflict), 5)

        all_source_cases = safe + visual + conflict
        hashes = {case["artifact_hash"] for case in all_source_cases}
        self.assertEqual(len(hashes), 15)
        for case in all_source_cases:
            path = ROOT / Path(case["artifact_path"])
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(case["artifact_hash"], actual)

    def test_every_round50_transform_binds_real_source_bytes(self):
        result = generate()
        by_id = {case["case_id"]: case for case in result["cases"]}
        transformed = [
            case
            for case in result["cases"]
            if case["case_id"].startswith("round50-attack-")
            and "source_case_id" in case
        ]
        self.assertEqual(len(transformed), 10)
        for case in transformed:
            source = by_id[case["source_case_id"]]
            self.assertEqual(case["source_case_hash"], source["artifact_hash"])
            self.assertTrue(case["artifact_hash"].startswith("sha256:"))

    def test_review_subset_contains_five_safe_and_each_expanded_taxonomy(self):
        generate()
        import json

        subset = json.loads(REVIEW_MANIFEST.read_text(encoding="utf-8"))["cases"]
        self.assertEqual(len(subset), 15)
        counts = defaultdict(int)
        for case in subset:
            counts[case["taxonomy"]] += 1
            self.assertNotIn("source_case_id", case)
        self.assertEqual(counts["safe_control"], 5)
        self.assertEqual(counts["visual_prompt_injection"], 5)
        self.assertEqual(counts["cross_modal_conflict"], 5)


if __name__ == "__main__":
    unittest.main()
