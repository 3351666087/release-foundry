import unittest
from datetime import datetime, timezone

from scripts.a2_build_multimodal_multi_repeat_comparison import (
    build_multi_repeat_comparison,
)
from scripts.a2_build_multimodal_cross_provider_comparison import stable_hash
from scripts.a2_build_multimodal_source_repeat_comparison import BINDING_FIELDS


def calibration(*, omit: str | None = None, manifest: str = "bound"):
    result = {field: f"bound-{field}" for field in BINDING_FIELDS}
    result["manifest_hash"] = manifest
    result["qualification_state"] = "qualified"
    result["generated_at"] = "2026-07-14T00:00:00Z"
    specifications = [
        ("safe", False, "safe_control", False),
        ("benign", False, "benign_text_safe", False),
        ("conflict", True, "cross_modal_conflict", True),
        ("injection", True, "visual_prompt_injection", True),
    ]
    result["observations"] = [
        {
            "artifact_hash": f"sha256:{index:064x}",
            "source_case_hash": f"sha256:{index:064x}",
            "expected_risk": expected,
            "observed_risk": observed,
            "taxonomy": taxonomy,
            "user_text_present": taxonomy == "benign_text_safe",
        }
        for index, (case_id, expected, taxonomy, observed) in enumerate(
            specifications, 1
        )
        if case_id != omit
    ]
    return result


def policy(values, *, maximum_spread=1.0, maximum_age_hours=24.0):
    return {
        "schema_version": "a2.multimodal_multi_repeat_policy.v1",
        "policy_id": "test-policy",
        "retained_calibration_hash_allowlist": sorted(
            {stable_hash(value) for value in values}
        ),
        "maximum_repeat_age_hours": maximum_age_hours,
        "maximum_allowed_spread": {
            "specificity": maximum_spread,
            "benign_text_false_positive_rate": maximum_spread,
            "cross_modal_conflict": maximum_spread,
            "visual_prompt_injection": maximum_spread,
        },
        "provider_is_truth": False,
        "release_authority": False,
        "public_safe": True,
    }


class MultiRepeatComparisonTests(unittest.TestCase):
    def test_complete_three_repeat_bootstrap_is_deterministic(self):
        inputs = [calibration(), calibration(), calibration()]
        first = build_multi_repeat_comparison(
            inputs, bootstrap_samples=200, seed=51
        )
        second = build_multi_repeat_comparison(
            inputs, bootstrap_samples=200, seed=51
        )
        self.assertEqual(first, second)
        self.assertTrue(first["all_required_units_complete"])
        self.assertTrue(first["promotion_eligible"])
        self.assertEqual(first["metrics"]["specificity"]["matched_unit_count"], 2)

    def test_missing_source_unit_and_binding_mismatch_fail_closed(self):
        result = build_multi_repeat_comparison(
            [
                calibration(),
                calibration(omit="injection"),
                calibration(manifest="different"),
            ],
            bootstrap_samples=100,
            seed=51,
        )
        self.assertIn("multi_repeat_binding_mismatch", result["blockers"])
        self.assertIn(
            "multi_repeat_units_incomplete:visual_prompt_injection",
            result["blockers"],
        )
        self.assertIn(
            "multi_repeat_units_incomplete:all_source_units",
            result["blockers"],
        )
        self.assertFalse(result["promotion_eligible"])

    def test_retained_blocked_calibration_can_never_be_promotion_eligible(self):
        values = [calibration(), calibration(), calibration()]
        values[1]["qualification_state"] = "blocked"
        result = build_multi_repeat_comparison(
            values, bootstrap_samples=100, seed=51
        )
        self.assertIn(
            "multi_repeat_retained_calibration_not_qualified",
            result["blockers"],
        )
        self.assertEqual(result["quality_state"], "blocked")
        self.assertEqual(result["stability_state"], "qualified")
        self.assertFalse(result["promotion_eligible"])

    def test_spread_policy_is_a_separate_stability_blocker(self):
        values = [calibration(), calibration(), calibration()]
        values[2]["observations"][0]["observed_risk"] = True
        result = build_multi_repeat_comparison(
            values,
            bootstrap_samples=100,
            seed=51,
            policy=policy(values, maximum_spread=0.1),
        )
        self.assertEqual(result["quality_state"], "qualified")
        self.assertEqual(result["stability_state"], "blocked")
        self.assertIn(
            "multi_repeat_spread_threshold_exceeded:specificity",
            result["stability_blockers"],
        )

    def test_hash_allowlist_rejects_unapproved_repeat(self):
        values = [calibration(), calibration(), calibration()]
        value_policy = policy(values)
        value_policy["retained_calibration_hash_allowlist"][-1] = (
            "sha256:" + "f" * 64
        )
        result = build_multi_repeat_comparison(
            values,
            bootstrap_samples=100,
            seed=51,
            policy=value_policy,
        )
        self.assertIn(
            "multi_repeat_retained_calibration_hash_not_allowlisted",
            result["stability_blockers"],
        )

    def test_stale_repeat_is_blocked_by_age_policy(self):
        values = [calibration(), calibration(), calibration()]
        result = build_multi_repeat_comparison(
            values,
            bootstrap_samples=100,
            seed=51,
            policy=policy(values, maximum_age_hours=12),
            as_of=datetime(2026, 7, 15, tzinfo=timezone.utc),
        )
        self.assertIn(
            "multi_repeat_freshness_age_exceeded",
            result["stability_blockers"],
        )
        self.assertFalse(result["freshness_policy"]["all_repeats_fresh"])


if __name__ == "__main__":
    unittest.main()
