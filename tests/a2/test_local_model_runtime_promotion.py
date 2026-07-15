import json
import unittest
from pathlib import Path

import jsonschema

from scripts.a2_build_local_model_runtime_promotion import build_contract


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (
        ROOT
        / "docs/a2/schemas/local_model_runtime_promotion_contract_v1.schema.json"
    ).read_text(encoding="utf-8")
)
POLICY = json.loads(
    (
        ROOT
        / "fixtures/a2/calibration/local_model_runtime_promotion_policy_round52.json"
    ).read_text(encoding="utf-8")
)
POLICY_V2 = json.loads(
    (
        ROOT
        / "fixtures/a2/calibration/local_model_runtime_promotion_policy_round53.json"
    ).read_text(encoding="utf-8")
)


def probe(*, valid=True, include_all=True, provider_is_truth=False):
    profiles = []
    names = ["warm_json_schema_16", "warm_json_schema_32"]
    if not include_all:
        names.pop()
    for name in names:
        profiles.append(
            {
                "profile": name,
                "num_predict": 16,
                "format_mode": "json_schema",
                "state": "completed" if valid else "failed",
                "parse_state": "valid_json"
                if valid
                else "invalid_structured_output",
                "error_class": "" if valid else "invalid_structured_output",
                "phase_receipt": {
                    "caller_wall_seconds": 2.0,
                },
            }
        )
    return {
        "schema_version": "a2.ollama_multimodal_latency_probe.v1",
        "model_id": "candidate:1",
        "model_digest": "sha256:" + "a" * 64,
        "profiles": profiles,
        "provider_is_truth": provider_is_truth,
        "secret_included": False,
        "release_authority": False,
        "public_safe": True,
    }


class LocalRuntimePromotionTests(unittest.TestCase):
    def build(self, value):
        raw = json.dumps(value, sort_keys=True).encode("utf-8")
        return build_contract(
            probe=value,
            probe_path="docs/evidence/probe.json",
            probe_bytes=raw,
            policy=POLICY,
        )

    def test_valid_required_profiles_qualify_runtime_only(self):
        result = self.build(probe())
        jsonschema.Draft202012Validator(SCHEMA).validate(result)
        self.assertEqual(result["runtime_promotion_state"], "qualified")
        self.assertFalse(result["release_authority"])
        self.assertFalse(result["provider_is_truth"])

    def test_invalid_structured_output_blocks(self):
        result = self.build(probe(valid=False))
        self.assertEqual(result["runtime_promotion_state"], "blocked")
        self.assertTrue(
            any("structured_output_invalid" in item for item in result["blockers"])
        )

    def test_missing_required_profile_is_incomplete(self):
        result = self.build(probe(include_all=False))
        self.assertEqual(result["runtime_promotion_state"], "incomplete")
        self.assertIn(
            "local_runtime_required_profile_missing:warm_json_schema_32",
            result["blockers"],
        )

    def test_provider_truth_claim_blocks(self):
        result = self.build(probe(provider_is_truth=True))
        self.assertEqual(result["runtime_promotion_state"], "blocked")
        self.assertIn(
            "local_runtime_provider_truth_boundary_invalid",
            result["blockers"],
        )

    def test_v2_separates_cold_warm_and_requires_consecutive_successes(self):
        value = probe()
        value["schema_version"] = "a2.ollama_multimodal_latency_probe.v2"
        value["profiles"] = []
        for index, name in enumerate(POLICY_V2["required_profiles"]):
            value["profiles"].append(
                {
                    "profile": name,
                    "num_predict": 96,
                    "format_mode": "json_schema",
                    "state": "completed" if index < 1 else "failed",
                    "parse_state": (
                        "valid_json"
                        if index < 1
                        else "invalid_structured_output"
                    ),
                    "error_class": "",
                    "phase_receipt": {"caller_wall_seconds": 2.0},
                }
            )
        raw = json.dumps(value, sort_keys=True).encode("utf-8")
        result = build_contract(
            probe=value,
            probe_path="docs/evidence/probe.json",
            probe_bytes=raw,
            policy=POLICY_V2,
        )
        self.assertEqual(result["cold_runtime_state"], "qualified")
        self.assertEqual(result["warm_runtime_state"], "blocked")
        self.assertEqual(result["maximum_consecutive_successful_profiles"], 1)
        self.assertIn(
            "local_runtime_consecutive_success_minimum_not_met",
            result["blockers"],
        )

    def test_v2_cold_latency_uses_cold_specific_blocker(self):
        value = probe()
        value["schema_version"] = "a2.ollama_multimodal_latency_probe.v2"
        value["profiles"] = []
        for name in POLICY_V2["required_profiles"]:
            value["profiles"].append(
                {
                    "profile": name,
                    "num_predict": 96,
                    "format_mode": "json_schema",
                    "state": "completed",
                    "parse_state": "valid_json",
                    "error_class": "",
                    "phase_receipt": {
                        "caller_wall_seconds": (
                            POLICY_V2["maximum_cold_caller_wall_seconds"] + 1
                            if name.startswith("cold_")
                            else 2.0
                        ),
                    },
                }
            )
        raw = json.dumps(value, sort_keys=True).encode("utf-8")
        result = build_contract(
            probe=value,
            probe_path="docs/evidence/probe.json",
            probe_bytes=raw,
            policy=POLICY_V2,
        )
        self.assertIn(
            "local_runtime_cold_latency_limit_not_met:"
            + POLICY_V2["required_profiles"][0],
            result["blockers"],
        )
        self.assertFalse(
            any(
                blocker.startswith("local_runtime_warm_latency_limit_not_met:cold_")
                for blocker in result["blockers"]
            )
        )


if __name__ == "__main__":
    unittest.main()
