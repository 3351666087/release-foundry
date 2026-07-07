import json
import re
import unittest
from pathlib import Path

from services.judge.versioning import build_judge_version_registry


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_FIXTURE = ROOT / "fixtures/a2/results/a2_judge_versions.json"
REGISTRY_SCHEMA = ROOT / "docs/a2/schemas/judge_versions.schema.json"
SCENARIO_PACK = ROOT / "packages/scenarios/a2_g3_full_pack.json"
GRADE_REPORT = ROOT / "fixtures/a2/results/a2_g3_grade_results.json"

HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
SECRET_PATTERNS = [
    re.compile("tp_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("ashr_live_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("sk-" + r"[A-Za-z0-9]"),
    re.compile("Bearer" + r"\\s+"),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class A2JudgeVersioningTests(unittest.TestCase):
    def test_fixture_matches_builder(self):
        actual = build_judge_version_registry(
            scenario_pack=load_json(SCENARIO_PACK),
            grade_report=load_json(GRADE_REPORT),
        )

        self.assertEqual(actual, load_json(REGISTRY_FIXTURE))

    def test_registry_schema_and_public_safety(self):
        registry = load_json(REGISTRY_FIXTURE)
        schema = load_json(REGISTRY_SCHEMA)
        text = REGISTRY_FIXTURE.read_text(encoding="utf-8")

        self.assertEqual(schema["properties"]["schema_version"]["const"], registry["schema_version"])
        self.assertLessEqual(set(schema["required"]), set(registry))
        self.assertEqual(registry["schema_version"], "a2.judge_versions.v1")
        self.assertRegex(registry["registry_hash"], HASH_RE)
        self.assertTrue(registry["metadata"]["public_safe"])
        self.assertFalse(registry["metadata"]["requires_network"])
        self.assertFalse(registry["metadata"]["requires_ashr_api_key"])
        self.assertTrue(registry["metadata"]["raw_private_evidence_not_recorded"])
        self.assertTrue(registry["metadata"]["secrets_not_recorded"])
        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(text), pattern.pattern)

    def test_registry_tracks_all_five_declared_judges_and_pins(self):
        registry = load_json(REGISTRY_FIXTURE)
        judges = registry["judges"]
        judge_ids = {judge["judge_id"] for judge in judges}

        self.assertEqual(registry["declared_judge_count"], 5)
        self.assertEqual(registry["observed_judge_count"], 5)
        self.assertTrue(registry["all_declared_judges_observed"])
        self.assertEqual(registry["undeclared_observed_judges"], [])
        self.assertEqual(len(judges), 5)
        self.assertEqual(
            judge_ids,
            {
                "g1_trace_contract_judge",
                "g2_output_contract_judge",
                "g3_replay_sandbox_judge",
                "g3_semantic_reference_judge",
                "g3_safety_boundary_judge",
            },
        )
        for judge in judges:
            with self.subTest(judge=judge["judge_id"]):
                self.assertEqual(judge["current_version"], "0.1.0")
                self.assertEqual(judge["observed_versions"], {"0.1.0": 32})
                self.assertEqual(judge["observed_result_count"], 32)
                self.assertTrue(judge["pinning"]["pin_supported"])
                self.assertTrue(judge["pinning"]["pin_required_for_prod"])
                self.assertEqual(judge["pinning"]["recommended_pin"], f"{judge['judge_id']}@0.1.0")
                self.assertTrue(judge["migration"]["history_replay_supported"])
                self.assertTrue(judge["migration"]["compare_before_after_supported"])
                self.assertEqual(judge["migration"]["deprecation_status"], "not_deprecated")
                self.assertRegex(judge["judge_contract_hash"], HASH_RE)

    def test_registry_supports_enterprise_version_migration_contract(self):
        registry = load_json(REGISTRY_FIXTURE)
        service_contract = registry["service_contract"]
        migration = registry["migration_policy"]

        self.assertTrue(registry["active_release"]["pinning_required_for_prod"])
        self.assertTrue(service_contract["pinning_supported"])
        self.assertTrue(service_contract["history_replay_supported"])
        self.assertTrue(service_contract["safe_to_compare_versions"])
        self.assertTrue(migration["requires_registry_hash_on_release_gate"])
        self.assertTrue(migration["requires_calibration_before_major_upgrade"])
        self.assertTrue(migration["requires_history_replay_before_prod_unpin"])
        self.assertTrue(migration["can_compare_judge_versions"])
        self.assertTrue(migration["can_replay_history"])
        self.assertEqual(migration["deprecated_judge_count"], 0)


if __name__ == "__main__":
    unittest.main()
