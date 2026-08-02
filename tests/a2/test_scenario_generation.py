import json
import re
import unittest
from pathlib import Path

from services.judge.scenario_generation import build_scenario_generation_backlog


ROOT = Path(__file__).resolve().parents[2]
COVERAGE_REPORT = ROOT / "fixtures/a2/results/a2_g3_coverage_report.json"
CALIBRATION_MATRIX = ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json"
SQL_STORE = ROOT / "fixtures/a2/results/a2_sql_store_report.json"
REGRESSION_REPLAY = ROOT / "fixtures/a2/results/a2_regression_replay_report.json"
RELEASE_UNBLOCK_CHECKLIST = ROOT / "fixtures/a2/results/a2_release_unblock_checklist.json"
BACKLOG_FIXTURE = ROOT / "fixtures/a2/results/a2_scenario_generation_backlog.json"
BACKLOG_SCHEMA = ROOT / "docs/a2/schemas/scenario_generation_backlog.schema.json"

SECRET_PATTERNS = [
    re.compile("tp_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("releasefoundry_live_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("sk-" + r"[A-Za-z0-9]"),
    re.compile("Bearer" + r"\\s+"),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class A2ScenarioGenerationTests(unittest.TestCase):
    def test_backlog_fixture_matches_builder_and_schema(self):
        report = build_scenario_generation_backlog(
            load_json(COVERAGE_REPORT),
            load_json(CALIBRATION_MATRIX),
            load_json(SQL_STORE),
            load_json(REGRESSION_REPLAY),
            load_json(RELEASE_UNBLOCK_CHECKLIST),
        )
        fixture = load_json(BACKLOG_FIXTURE)
        schema = load_json(BACKLOG_SCHEMA)

        self.assertEqual(report, fixture)
        self.assertEqual(schema["properties"]["schema_version"]["const"], report["schema_version"])
        self.assertLessEqual(set(schema["required"]), set(report))
        self.assertEqual(report["candidate_count"], 12)
        self.assertEqual(report["candidate_count"], len(report["candidates"]))
        self.assertEqual(report["policy_experiment_count"], len(report["policy_experiments"]))
        self.assertFalse(report["promotion_gate"]["may_mutate_main_pack"])
        self.assertFalse(report["metadata"]["scenario_pack_mutated"])
        self.assertTrue(report["metadata"]["public_safe"])
        self.assertTrue(report["metadata"]["does_not_read_private_evidence"])

    def test_backlog_prioritizes_real_saas_gaps_without_mutating_main_pack(self):
        backlog = load_json(BACKLOG_FIXTURE)
        candidates = backlog["candidates"]
        candidate_ids = [candidate["candidate_id"] for candidate in candidates]
        titles = {candidate["title"] for candidate in candidates}
        tags = {tag for candidate in candidates for tag in candidate["tags"]}
        experiment_targets = {experiment["target_gate"] for experiment in backlog["policy_experiments"]}

        self.assertEqual(len(candidate_ids), len(set(candidate_ids)))
        self.assertIn("Media Evidence Grounding", titles)
        self.assertIn("Enterprise Approval RBAC Boundary", titles)
        self.assertIn("Official Grading Diff Requires Review", titles)
        self.assertIn("Production Incident Becomes Regression", titles)
        self.assertIn("media", tags)
        self.assertIn("enterprise-saas", tags)
        self.assertLessEqual({"C3", "C4", "C5"}, experiment_targets)
        self.assertEqual(
            backlog["promotion_gate"]["output_path_if_accepted"],
            "packages/scenarios/a2_g3_full_pack.json",
        )

    def test_backlog_draft_scenarios_are_public_safe_and_reviewable(self):
        backlog_text = BACKLOG_FIXTURE.read_text(encoding="utf-8")
        backlog = json.loads(backlog_text)

        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(backlog_text), pattern.pattern)

        for candidate in backlog["candidates"]:
            with self.subTest(candidate=candidate["candidate_id"]):
                draft = candidate["draft_scenario"]
                acceptance = candidate["acceptance_plan"]
                self.assertEqual(draft["id"], candidate["candidate_id"])
                self.assertEqual(draft["primaryFailureClass"], candidate["target_failure_class"])
                self.assertIn(candidate["target_failure_class"], draft["failureSignals"])
                self.assertEqual(draft["fixtureRefs"], [])
                self.assertTrue(acceptance["required_fixture"].startswith("fixtures/a2/runs/"))
                self.assertTrue(acceptance["required_golden_case"].startswith("GC-A2-GEN-"))
                self.assertGreaterEqual(len(acceptance["required_judge_modes"]), 3)
                self.assertEqual(
                    candidate["evidence_refs"],
                    [
                        "fixtures/a2/results/a2_g3_coverage_report.json",
                        "fixtures/a2/results/a2_sql_store_report.json",
                        "fixtures/a2/results/a2_release_unblock_checklist.json",
                    ],
                )


if __name__ == "__main__":
    unittest.main()
