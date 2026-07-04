import json
import unittest
from collections import Counter
from pathlib import Path

from services.judge.coverage import build_coverage_report
from services.judge.runner import grade_run, grade_runs, load_scenario_pack
from services.judge.schemas import CANONICAL_FAILURE_CLASSES, LOCAL_FAILURE_CLASS_MAP, canonical_primary_failure_class


ROOT = Path(__file__).resolve().parents[2]


class A2ContractTests(unittest.TestCase):
    def test_seed_pack_has_20_scenarios_with_tool_policy(self):
        pack = load_scenario_pack(ROOT / "packages/scenarios/a2_g2_seed_pack.json")
        scenarios = pack["scenarios"]
        self.assertEqual(len(scenarios), 20)
        self.assertEqual(len({scenario["id"] for scenario in scenarios}), 20)
        for scenario in scenarios:
            with self.subTest(scenario=scenario["id"]):
                self.assertIn("toolPolicy", scenario)
                policy = scenario["toolPolicy"]
                self.assertIn("required", policy)
                self.assertIn("optional", policy)
                self.assertIn("forbidden", policy)
                self.assertIn("expectedBehaviors", scenario)

    def test_g3_full_pack_has_60_scenarios_and_5_judges(self):
        pack = load_scenario_pack(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        scenarios = pack["scenarios"]
        self.assertEqual(len(scenarios), 60)
        self.assertEqual(len({scenario["id"] for scenario in scenarios}), 60)
        self.assertEqual(len(pack["rubric_classes"]), 5)
        self.assertEqual(len(pack["judge_modes"]), 5)
        self.assertEqual(Counter(scenario["family"] for scenario in scenarios), {
            "direct_answer": 10,
            "retrieval_grounding": 10,
            "tool_execution": 10,
            "workflow_planning": 10,
            "safety_policy": 10,
            "ambiguous_or_conflicting": 10,
        })
        for scenario in scenarios:
            with self.subTest(scenario=scenario["id"]):
                self.assertIn("toolPolicy", scenario)
                self.assertIn("expectedBehaviors", scenario)
                self.assertIn("failureSignals", scenario)
                self.assertIn(scenario["primaryFailureClass"], CANONICAL_FAILURE_CLASSES)
                self.assertLessEqual(
                    set(scenario["failureSignals"]),
                    CANONICAL_FAILURE_CLASSES | set(LOCAL_FAILURE_CLASS_MAP),
                )
                canonical_signals = {
                    canonical_primary_failure_class([signal])
                    for signal in scenario["failureSignals"]
                }
                self.assertIn(scenario["primaryFailureClass"], canonical_signals)

    def test_all_fixture_refs_exist(self):
        pack = load_scenario_pack(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        missing = []
        for scenario in pack["scenarios"]:
            for ref in scenario.get("fixtureRefs", []):
                if not (ROOT / ref).exists():
                    missing.append((scenario["id"], ref))
        self.assertEqual(missing, [])

    def test_golden_cases_cover_seed_scenarios(self):
        pack = load_scenario_pack(ROOT / "packages/scenarios/a2_g2_seed_pack.json")
        full_pack = load_scenario_pack(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        golden = json.loads((ROOT / "fixtures/golden/a2_g2_golden_cases.json").read_text(encoding="utf-8"))
        scenario_ids = {scenario["id"] for scenario in pack["scenarios"]}
        full_scenario_ids = {scenario["id"] for scenario in full_pack["scenarios"]}
        golden_ids = {case["scenario_id"] for case in golden["goldenCases"]}
        case_ids = [case["case_id"] for case in golden["goldenCases"]]
        self.assertGreaterEqual(len(golden["goldenCases"]), 20)
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertLessEqual(scenario_ids, golden_ids)
        self.assertLessEqual(golden_ids, full_scenario_ids)
        for case in golden["goldenCases"]:
            with self.subTest(case=case["case_id"]):
                self.assertIn(case["expected_primary_failure_class"], CANONICAL_FAILURE_CLASSES | {"none"})

    def test_failure_taxonomy_lists_12_required_classes(self):
        text = (ROOT / "docs/a2/failure_taxonomy_v0.md").read_text(encoding="utf-8")
        expected = [
            "wrong_intent",
            "missing_required_tool",
            "unnecessary_tool_call",
            "forbidden_tool_call",
            "wrong_tool",
            "wrong_arguments",
            "wrong_tool_order",
            "missing_clarification",
            "hallucinated_tool_result",
            "ignored_tool_result",
            "unsafe_or_policy_violation",
            "poor_failure_recovery",
        ]
        for failure_class in expected:
            with self.subTest(failure_class=failure_class):
                self.assertIn(failure_class, text)

    def test_runner_returns_combined_result(self):
        result = grade_run(
            "A2-S001",
            {
                "tool_calls": [],
                "final_response": "I need a little more information before I can complete your request.",
            },
            pack_path=ROOT / "packages/scenarios/a2_g2_seed_pack.json",
            case_id="contract-smoke",
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["primary_failure_class"], "none")
        self.assertEqual(len(result["judge_results"]), 5)

    def test_runner_accepts_a1_agent_output_shape(self):
        result = grade_run(
            "A2-S005",
            {
                "schema_version": "ashr.clone.agent_turn.v1",
                "text": "- Launch risk is dependency timing.\n- Mitigation is owner review.\n- Next step is Friday signoff.",
                "tool_calls": [
                    {
                        "name": "file.read",
                        "arguments": {"path": "fixtures/a2/notes/launch-review.md"},
                        "call_id": "a1-call-1",
                    }
                ],
                "status": "ok",
                "latency_ms": 0,
                "metadata": {"adapter_name": "A1Agent"},
            },
            pack_path=ROOT / "packages/scenarios/a2_g2_seed_pack.json",
            case_id="a1-agent-output-smoke",
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["primary_failure_class"], "none")
        self.assertEqual(result["judge_results"][0]["evidence"]["tool_call_ids"], ["a1-call-1"])

    def test_runner_accepts_a1_case_result_shape_and_case_id(self):
        result = grade_run(
            "A2-S004",
            {
                "case_id": "a1-case-result-smoke",
                "scenario_id": "A2-S004",
                "status": "passed",
                "agent_output": {
                    "schema_version": "ashr.clone.agent_turn.v1",
                    "text": "The official product page lists the Acme MiniDock at $79.",
                    "tool_calls": [
                        {
                            "name": "web.search",
                            "arguments": {"query": "Acme MiniDock official price"},
                            "output": {"url": "https://example.test/acme-minidock"},
                        }
                    ],
                    "status": "ok",
                    "latency_ms": 0,
                    "metadata": {},
                },
                "observations": [],
                "expected": {},
                "metadata": {},
            },
            pack_path=ROOT / "packages/scenarios/a2_g2_seed_pack.json",
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["case_id"], "a1-case-result-smoke")
        self.assertEqual(result["primary_failure_class"], "none")

    def test_runner_accepts_function_style_tool_calls(self):
        result = grade_run(
            "A2-S005",
            {
                "final_response": "- Launch risk is dependency timing.\n- Mitigation is owner review.\n- Next step is Friday signoff.",
                "tool_calls": [
                    {
                        "id": "call-function-1",
                        "function": {
                            "name": "file.read",
                            "arguments": "{\"path\":\"fixtures/a2/notes/launch-review.md\"}",
                        },
                    }
                ],
            },
            pack_path=ROOT / "packages/scenarios/a2_g2_seed_pack.json",
            case_id="function-tool-call-smoke",
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["primary_failure_class"], "none")

    def test_sample_run_fixtures_grade_as_expected(self):
        run_dir = ROOT / "fixtures/a2/runs"
        for path in sorted(run_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(run_fixture=path.name):
                result = grade_run(
                    payload["scenario_id"],
                    payload["run"],
                    pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    case_id=payload["case_id"],
                )
                self.assertEqual(result["passed"], payload["expected"]["passed"])
                self.assertEqual(result["primary_failure_class"], payload["expected"]["primary_failure_class"])

    def test_g3_tool_scenarios_have_executable_calibration(self):
        run_dir = ROOT / "fixtures/a2/runs"
        fixtures = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(run_dir.glob("*.json"))]
        by_scenario = {fixture["scenario_id"]: fixture for fixture in fixtures}
        for scenario_id in {"A2-S016", "A2-S018", "A2-S019", "A2-S033", "A2-S041"}:
            with self.subTest(scenario=scenario_id):
                self.assertIn(scenario_id, by_scenario)
                self.assertFalse(by_scenario[scenario_id]["expected"]["passed"])

    def test_sample_grade_results_match_runner(self):
        run_dir = ROOT / "fixtures/a2/runs"
        result_dir = ROOT / "fixtures/a2/results"
        for path in sorted(run_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            expected_result = json.loads((result_dir / f"{path.stem}_grade.json").read_text(encoding="utf-8"))
            with self.subTest(result_fixture=path.name):
                actual_result = grade_run(
                    payload["scenario_id"],
                    payload["run"],
                    pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    case_id=payload["case_id"],
                )
                self.assertEqual(actual_result, expected_result)

    def test_g3_aggregate_grade_report_matches_runner_and_a3_shape(self):
        run_dir = ROOT / "fixtures/a2/runs"
        fixtures = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(run_dir.glob("*.json"))]
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_g3_grade_results.json").read_text(encoding="utf-8"))
        actual_report = grade_runs(
            fixtures,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            report_id="a2_g3_grade_results",
            dataset_id="a2-g3-calibration",
        )
        self.assertEqual(actual_report, expected_report)
        self.assertIn("grade_results", actual_report)
        self.assertEqual(actual_report["total_cases"], len(fixtures))
        failure_classes = {result["primary_failure_class"] for result in actual_report["grade_results"]}
        self.assertLessEqual(CANONICAL_FAILURE_CLASSES | {"none"}, failure_classes)

    def test_g3_coverage_report_meets_assignment_minimums(self):
        report = build_coverage_report(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_g3_coverage_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report, expected_report)
        self.assertEqual(report["scenario_count"], 60)
        self.assertTrue(report["meets_assignment_minimums"])
        self.assertTrue(all(report["assignment_checks"].values()))
        self.assertEqual(report["assignment_minimums"]["scenario_count"], 60)
        self.assertEqual(report["assignment_minimums"]["golden_case_count"], 20)
        self.assertEqual(len(report["rubric_classes"]), 5)
        self.assertEqual(len(report["judge_modes"]), 5)
        self.assertEqual(report["required_failure_classes_missing"], [])
        self.assertEqual(set(report["family_counts"].values()), {10})
        self.assertEqual(set(report["primary_rubric_counts"].values()), {12})
        self.assertEqual(len(report["primary_failure_class_counts"]), 12)
        self.assertEqual(sum(report["primary_failure_class_counts"].values()), 60)
        self.assertLessEqual(set(report["primary_failure_class_counts"]), CANONICAL_FAILURE_CLASSES)
        self.assertGreaterEqual(report["golden_case_count"], 32)
        self.assertGreaterEqual(report["golden_failure_case_count"], 27)
        self.assertGreaterEqual(report["golden_pass_case_count"], 1)
        self.assertEqual(
            sum(report["golden_failure_class_counts"].values()),
            report["golden_failure_case_count"],
        )
        self.assertEqual(report["golden_failure_classes_missing"], [])
        self.assertEqual(report["thin_golden_failure_classes"], {})
        for failure_class in CANONICAL_FAILURE_CLASSES:
            with self.subTest(golden_failure_class=failure_class):
                self.assertGreaterEqual(report["golden_failure_class_counts"][failure_class], 2)
        self.assertLessEqual(set(report["golden_failure_class_counts"]), CANONICAL_FAILURE_CLASSES)
        self.assertGreaterEqual(report["executable_run_case_count"], 18)
        self.assertGreaterEqual(report["executable_failure_case_count"], 17)
        self.assertEqual(report["executable_failure_classes_missing"], [])
        self.assertEqual(report["executable_failure_class_counts"]["hallucinated_tool_result"], 3)
        self.assertEqual(report["executable_failure_class_counts"]["wrong_arguments"], 3)
        self.assertEqual(report["executable_failure_class_counts"]["poor_failure_recovery"], 2)
        self.assertEqual(len(report["thin_executable_failure_classes"]), 9)
        self.assertNotIn("hallucinated_tool_result", report["thin_executable_failure_classes"])
        self.assertNotIn("wrong_arguments", report["thin_executable_failure_classes"])
        self.assertNotIn("poor_failure_recovery", report["thin_executable_failure_classes"])
        self.assertEqual(report["coverage_warnings"], ["9 executable failure classes have fewer than 2 run fixtures."])
        self.assertLessEqual(set(report["executable_failure_class_counts"]), CANONICAL_FAILURE_CLASSES)


if __name__ == "__main__":
    unittest.main()
