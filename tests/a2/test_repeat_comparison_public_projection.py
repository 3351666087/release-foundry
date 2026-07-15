import json
import unittest

import jsonschema

from scripts.a2_build_repeat_comparison_public_projection import (
    build_public_projection,
)


def comparison():
    digest = "sha256:" + "a" * 64
    return {
        "schema_version": "a2.multimodal_multi_repeat_comparison.v2",
        "policy_id": "policy",
        "policy_hash": digest,
        "repeat_count": 3,
        "binding_fields": {"model_id": "model"},
        "mismatched_binding_fields": [],
        "quality_state": "blocked",
        "quality_blockers": ["calibration_blocked"],
        "stability_state": "qualified",
        "stability_blockers": [],
        "maximum_allowed_spread": {"specificity": 0.1},
        "observed_spread_upper": {"specificity": 0.0},
        "freshness_policy": {
            "as_of": "2026-07-14T00:00:00Z",
            "maximum_repeat_age_hours": 24.0,
            "repeat_ages_hours": [0.0, 0.0, 0.0],
            "all_repeats_fresh": True,
        },
        "promotion_eligible": False,
        "provider_is_truth": False,
        "raw_provider_text_included": False,
        "release_authority": False,
        "public_safe": True,
    }


class RepeatComparisonPublicProjectionTests(unittest.TestCase):
    def test_projection_is_read_only_and_preserves_blocked_state(self):
        value = comparison()
        raw = json.dumps(value, sort_keys=True).encode()
        result = build_public_projection(
            value,
            source_path="docs/evidence/repeat.json",
            source_bytes=raw,
        )
        self.assertEqual(result["quality_state"], "blocked")
        self.assertFalse(result["release_authority"])
        self.assertFalse(result["provider_is_truth"])
        self.assertFalse(result["promotion_eligible"])

    def test_projection_rejects_authoritative_source(self):
        value = comparison()
        value["release_authority"] = True
        with self.assertRaisesRegex(ValueError, "release authority"):
            build_public_projection(
                value,
                source_path="docs/evidence/repeat.json",
                source_bytes=b"{}",
            )

    def test_projection_rejects_inconsistent_qualified_state(self):
        value = comparison()
        value["quality_state"] = "qualified"
        with self.assertRaises(jsonschema.ValidationError):
            build_public_projection(
                value,
                source_path="docs/evidence/repeat.json",
                source_bytes=b"{}",
            )

    def test_projection_rejects_inconsistent_promotion(self):
        value = comparison()
        value["promotion_eligible"] = True
        with self.assertRaises(jsonschema.ValidationError):
            build_public_projection(
                value,
                source_path="docs/evidence/repeat.json",
                source_bytes=b"{}",
            )


if __name__ == "__main__":
    unittest.main()
