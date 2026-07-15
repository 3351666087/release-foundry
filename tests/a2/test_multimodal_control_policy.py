import json
import unittest
from pathlib import Path

import jsonschema

from scripts.a2_assess_multimodal_control_policy import build_assessment


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (
        ROOT
        / "docs/a2/schemas/multimodal_control_policy_assessment_v1.schema.json"
    ).read_text(encoding="utf-8")
)
POLICY = json.loads(
    (
        ROOT
        / "fixtures/a2/calibration/multimodal_control_policy_round52.json"
    ).read_text(encoding="utf-8")
)
POLICY_V2 = json.loads(
    (
        ROOT
        / "fixtures/a2/calibration/multimodal_control_policy_round53.json"
    ).read_text(encoding="utf-8")
)


def calibration(*, false_positives=0, attack_detections=5, safe_count=10):
    observations = []
    for index in range(safe_count):
        observations.append(
            {
                "case_id": f"safe-{index}",
                "taxonomy": "safe_control",
                "expected_risk": False,
                "observed_risk": index < false_positives,
                "http_state": "completed",
                "parse_state": "valid_json",
            }
        )
    for index in range(5):
        observations.append(
            {
                "case_id": f"attack-{index}",
                "taxonomy": "cross_modal_conflict",
                "expected_risk": True,
                "observed_risk": index < attack_detections,
                "http_state": "completed",
                "parse_state": "valid_json",
            }
        )
    return {
        "schema_version": "a2.dashscope_multimodal_calibration.v5",
        "observations": observations,
        "secret_included": False,
        "release_authority": False,
        "public_safe": True,
    }


class MultimodalControlPolicyTests(unittest.TestCase):
    def build(self, source):
        raw = json.dumps(source, sort_keys=True).encode("utf-8")
        return build_assessment(
            calibration=source,
            calibration_path="docs/evidence/calibration.json",
            calibration_bytes=raw,
            policy=POLICY,
        )

    def test_safe_count_and_taxonomy_threshold_can_qualify(self):
        result = self.build(calibration())
        jsonschema.Draft202012Validator(SCHEMA).validate(result)
        self.assertEqual(result["quality_state"], "qualified")
        self.assertEqual(
            result["safe_control_assessment"]["false_positive_count"], 0
        )

    def test_one_false_positive_blocks_exact_count_policy(self):
        result = self.build(calibration(false_positives=1))
        self.assertEqual(result["quality_state"], "blocked")
        self.assertIn(
            "multimodal_safe_control_false_positive_count_exceeded",
            result["quality_blockers"],
        )

    def test_safety_guidance_conflict_sensitivity_blocks(self):
        result = self.build(calibration(attack_detections=3))
        self.assertEqual(result["quality_state"], "blocked")
        self.assertIn(
            "multimodal_taxonomy_sensitivity_threshold_not_met:cross_modal_conflict",
            result["quality_blockers"],
        )

    def test_missing_safe_controls_is_incomplete(self):
        result = self.build(calibration(safe_count=9))
        self.assertEqual(result["quality_state"], "incomplete")

    def test_v2_wilson_bounds_fail_closed_for_small_or_weak_samples(self):
        source = calibration(
            false_positives=0,
            attack_detections=4,
            safe_count=20,
        )
        source["observations"].extend(
            {
                "case_id": f"injection-{index}",
                "taxonomy": "visual_prompt_injection",
                "expected_risk": True,
                "observed_risk": index < 8,
                "http_state": "completed",
                "parse_state": "valid_json",
            }
            for index in range(10)
        )
        raw = json.dumps(source, sort_keys=True).encode("utf-8")
        result = build_assessment(
            calibration=source,
            calibration_path="docs/evidence/calibration.json",
            calibration_bytes=raw,
            policy=POLICY_V2,
        )
        self.assertEqual(result["quality_state"], "incomplete")
        self.assertLess(
            result["taxonomy_assessments"]["cross_modal_conflict"][
                "sensitivity_wilson_lower"
            ],
            POLICY_V2["taxonomy_policies"]["cross_modal_conflict"][
                "minimum_sensitivity_wilson_lower"
            ],
        )

    def test_v2_safe_false_positive_wilson_upper_is_enforced(self):
        source = calibration(false_positives=0, safe_count=20)
        source["observations"].extend(
            {
                "case_id": f"injection-{index}",
                "taxonomy": "visual_prompt_injection",
                "expected_risk": True,
                "observed_risk": True,
                "http_state": "completed",
                "parse_state": "valid_json",
            }
            for index in range(10)
        )
        strict = json.loads(json.dumps(POLICY_V2))
        strict["safe_controls"]["maximum_false_positive_wilson_upper"] = 0.1
        raw = json.dumps(source, sort_keys=True).encode("utf-8")
        result = build_assessment(
            calibration=source,
            calibration_path="docs/evidence/calibration.json",
            calibration_bytes=raw,
            policy=strict,
        )
        self.assertIn(
            "multimodal_safe_control_false_positive_wilson_upper_exceeded",
            result["quality_blockers"],
        )


if __name__ == "__main__":
    unittest.main()
