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


if __name__ == "__main__":
    unittest.main()
