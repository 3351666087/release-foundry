import json
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from services.judge.batch_plan import build_batch_plan_report
from services.judge.calibration import (
    build_calibration_matrix,
    import_ashr_grading_observations,
    import_semantic_judge_observations,
    merge_calibration_observations,
)
from services.judge.casebook import build_case_book_report
from services.judge.coverage import build_coverage_report
from services.judge.readiness import build_commercial_readiness_report
from services.judge.regression_replay import build_regression_replay_report
from services.judge.runner import grade_run, grade_runs, load_scenario_pack
from services.judge.schemas import CANONICAL_FAILURE_CLASSES, LOCAL_FAILURE_CLASS_MAP, canonical_primary_failure_class
from services.judge.sdk_parity import build_sdk_parity_report
from services.judge.semantic_harness import build_semantic_harness_report


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

    def test_runner_accepts_typescript_case_result_shape(self):
        result = grade_run(
            "A2-S005",
            {
                "case_id": "typescript-case-result-smoke",
                "scenario_id": "A2-S005",
                "status": "passed",
                "agent_output": {
                    "schema_version": "ashr.clone.agent_turn.v1",
                    "text": "- Launch risk is dependency timing.\n- Mitigation is owner review.\n- Next step is Friday signoff.",
                    "tool_calls": [
                        {
                            "name": "file.read",
                            "arguments": {"path": "fixtures/a2/notes/launch-review.md"},
                            "id": "ts-call-1",
                        }
                    ],
                    "status": "ok",
                    "latency_ms": 0,
                    "metadata": {"sdk_language": "typescript", "runner_id": "ts-local-runner"},
                },
                "metadata": {"sdk_language": "typescript"},
            },
            pack_path=ROOT / "packages/scenarios/a2_g2_seed_pack.json",
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["case_id"], "typescript-case-result-smoke")
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
        for scenario_id in {"A2-S016", "A2-S018", "A2-S019", "A2-S031", "A2-S033", "A2-S041"}:
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

    def test_generated_a2_fixtures_are_reproducible(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/a2_regenerate_fixtures.py"), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("A2 generated fixture files match", result.stdout)

    def test_a2_schema_snapshots_match_committed_fixtures(self):
        schema_dir = ROOT / "docs/a2/schemas"
        grade_schema = json.loads((schema_dir / "grade_results.schema.json").read_text(encoding="utf-8"))
        coverage_schema = json.loads((schema_dir / "coverage_report.schema.json").read_text(encoding="utf-8"))
        calibration_schema = json.loads((schema_dir / "calibration_matrix.schema.json").read_text(encoding="utf-8"))
        readiness_schema = json.loads((schema_dir / "commercial_readiness.schema.json").read_text(encoding="utf-8"))
        case_book_schema = json.loads((schema_dir / "case_book.schema.json").read_text(encoding="utf-8"))
        sdk_parity_schema = json.loads((schema_dir / "sdk_parity.schema.json").read_text(encoding="utf-8"))
        batch_plan_schema = json.loads((schema_dir / "batch_plan.schema.json").read_text(encoding="utf-8"))
        semantic_harness_schema = json.loads((schema_dir / "semantic_harness.schema.json").read_text(encoding="utf-8"))
        regression_replay_schema = json.loads((schema_dir / "regression_replay.schema.json").read_text(encoding="utf-8"))
        grade_report = json.loads((ROOT / "fixtures/a2/results/a2_g3_grade_results.json").read_text(encoding="utf-8"))
        coverage_report = json.loads((ROOT / "fixtures/a2/results/a2_g3_coverage_report.json").read_text(encoding="utf-8"))
        calibration_matrix = json.loads((ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json").read_text(encoding="utf-8"))
        readiness_report = json.loads((ROOT / "fixtures/a2/results/a2_commercial_readiness_report.json").read_text(encoding="utf-8"))
        case_book = json.loads((ROOT / "fixtures/a2/results/a2_case_book.json").read_text(encoding="utf-8"))
        sdk_parity = json.loads((ROOT / "fixtures/a2/results/a2_sdk_parity_report.json").read_text(encoding="utf-8"))
        batch_plan = json.loads((ROOT / "fixtures/a2/results/a2_batch_plan_report.json").read_text(encoding="utf-8"))
        semantic_harness = json.loads((ROOT / "fixtures/a2/results/a2_semantic_harness_report.json").read_text(encoding="utf-8"))
        regression_replay = json.loads((ROOT / "fixtures/a2/results/a2_regression_replay_report.json").read_text(encoding="utf-8"))

        self.assertEqual(grade_schema["properties"]["schema_version"]["const"], grade_report["schema_version"])
        self.assertEqual(coverage_schema["properties"]["schema_version"]["const"], coverage_report["schema_version"])
        self.assertEqual(calibration_schema["properties"]["schema_version"]["const"], calibration_matrix["schema_version"])
        self.assertEqual(readiness_schema["properties"]["schema_version"]["const"], readiness_report["schema_version"])
        self.assertEqual(case_book_schema["properties"]["schema_version"]["const"], case_book["schema_version"])
        self.assertEqual(sdk_parity_schema["properties"]["schema_version"]["const"], sdk_parity["schema_version"])
        self.assertEqual(batch_plan_schema["properties"]["schema_version"]["const"], batch_plan["schema_version"])
        self.assertEqual(
            semantic_harness_schema["properties"]["schema_version"]["const"],
            semantic_harness["schema_version"],
        )
        self.assertEqual(
            regression_replay_schema["properties"]["schema_version"]["const"],
            regression_replay["schema_version"],
        )
        self.assertLessEqual(set(grade_schema["required"]), set(grade_report))
        self.assertLessEqual(set(coverage_schema["required"]), set(coverage_report))
        self.assertLessEqual(set(calibration_schema["required"]), set(calibration_matrix))
        self.assertLessEqual(set(readiness_schema["required"]), set(readiness_report))
        self.assertLessEqual(set(case_book_schema["required"]), set(case_book))
        self.assertLessEqual(set(sdk_parity_schema["required"]), set(sdk_parity))
        self.assertLessEqual(set(batch_plan_schema["required"]), set(batch_plan))
        self.assertLessEqual(set(semantic_harness_schema["required"]), set(semantic_harness))
        self.assertLessEqual(set(regression_replay_schema["required"]), set(regression_replay))

        local_run_required = set(grade_schema["$defs"]["local_judge_run"]["required"])
        judge_required = set(grade_schema["$defs"]["grade_result"]["required"])
        failure_required = set(grade_schema["$defs"]["failure_analysis"]["required"])
        rubric_required = set(grade_schema["$defs"]["rubric_score"]["required"])
        for grade in grade_report["grade_results"]:
            with self.subTest(grade_case=grade["case_id"]):
                self.assertLessEqual(local_run_required, set(grade))
                self.assertEqual(grade["schema_version"], "a2.local_judge_run.v1")
                self.assertIn(grade["primary_failure_class"], CANONICAL_FAILURE_CLASSES | {"none"})
                for judge in grade["judge_results"]:
                    self.assertLessEqual(judge_required, set(judge))
                    self.assertEqual(judge["schema_version"], "a2.grade_result.v1")
                    self.assertLessEqual(failure_required, set(judge["failure_analysis"]))
                    self.assertEqual(judge["failure_analysis"]["schema_version"], "a2.failure_analysis.v1")
                    self.assertIn(
                        judge["failure_analysis"]["primary_failure_class"],
                        CANONICAL_FAILURE_CLASSES | {"none"},
                    )
                    for rubric in judge["rubric_scores"]:
                        self.assertLessEqual(rubric_required, set(rubric))

        case_ref_required = set(coverage_schema["$defs"]["case_ref"]["required"])
        for source in ("golden_failure_class_cases", "executable_failure_class_cases"):
            for failure_class, refs in coverage_report[source].items():
                with self.subTest(coverage_source=source, failure_class=failure_class):
                    self.assertIn(failure_class, CANONICAL_FAILURE_CLASSES)
                    self.assertGreaterEqual(len(refs), 2)
                    for ref in refs:
                        self.assertLessEqual(case_ref_required, set(ref))

        calibration_case_required = set(calibration_schema["$defs"]["calibration_case"]["required"])
        source_result_required = set(calibration_schema["$defs"]["source_result"]["required"])
        for case in calibration_matrix["cases"]:
            with self.subTest(calibration_case=case["case_id"]):
                self.assertLessEqual(calibration_case_required, set(case))
                self.assertEqual(set(case["sources"]), {"local_judge", "ashr_grading", "llm_judge"})
                for source_result in case["sources"].values():
                    self.assertLessEqual(source_result_required, set(source_result))

        gate_required = set(readiness_schema["$defs"]["gate_status"]["required"])
        for gate in readiness_report["gate_status"]:
            with self.subTest(readiness_gate=gate["gate"]):
                self.assertLessEqual(gate_required, set(gate))

        regression_case_required = set(case_book_schema["$defs"]["regression_case"]["required"])
        for regression_case in case_book["regression_cases"]:
            with self.subTest(case_book_case=regression_case["case_id"]):
                self.assertLessEqual(regression_case_required, set(regression_case))

        sdk_contract_required = set(sdk_parity_schema["$defs"]["source_contract"]["required"])
        for contract in sdk_parity["source_contracts"]:
            with self.subTest(sdk_parity_contract=contract["language"]):
                self.assertLessEqual(sdk_contract_required, set(contract))

        sdk_case_required = set(sdk_parity_schema["$defs"]["parity_case"]["required"])
        for parity_case in sdk_parity["cases"]:
            with self.subTest(sdk_parity_case=parity_case["case_id"]):
                self.assertLessEqual(sdk_case_required, set(parity_case))

        batch_required = set(batch_plan_schema["$defs"]["batch"]["required"])
        for batch in batch_plan["batches"]:
            with self.subTest(batch_plan_batch=batch["batch_id"]):
                self.assertLessEqual(batch_required, set(batch))

        harness_case_required = set(semantic_harness_schema["$defs"]["harness_case"]["required"])
        for harness_case in semantic_harness["cases"]:
            with self.subTest(semantic_harness_case=harness_case["case_id"]):
                self.assertLessEqual(harness_case_required, set(harness_case))

        replay_case_required = set(regression_replay_schema["$defs"]["replay_case"]["required"])
        for replay_case in regression_replay["cases"]:
            with self.subTest(regression_replay_case=replay_case["case_id"]):
                self.assertLessEqual(replay_case_required, set(replay_case))

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
        self.assertTrue(all(report["scenario_dimension_checks"].values()))
        self.assertEqual(report["thin_scenario_dimensions"], {})
        self.assertEqual(report["scenario_dimension_counts"]["required_tool_use"], 24)
        self.assertEqual(report["scenario_dimension_counts"]["fixture_grounding"], 30)
        self.assertEqual(report["scenario_dimension_counts"]["ordered_tool_sequence"], 5)
        self.assertEqual(report["scenario_dimension_counts"]["tool_output_grounding"], 1)
        self.assertEqual(report["scenario_dimension_scenarios"]["tool_output_grounding"], ["A2-S031"])
        self.assertEqual(report["difficulty_counts"]["D4"], 2)
        self.assertEqual(report["multi_turn_scenario_count"], 4)
        self.assertEqual(report["environment_counts"]["local"], 38)
        self.assertEqual(report["tool_policy_shape_counts"]["ordered_tools"], 5)
        self.assertEqual(report["required_tool_counts"]["web.search"], 6)
        self.assertEqual(report["required_tool_counts"]["web.open"], 5)
        self.assertEqual(report["ordered_tool_pairs"]["web.search -> web.open"], 3)
        self.assertEqual(report["ordered_tool_pairs"]["file.read -> file.read"], 1)
        self.assertEqual(report["ordered_tool_pairs"]["media.fetch -> image.view"], 1)
        self.assertEqual(report["ordered_tool_pairs"]["image.view -> media.classify"], 1)
        self.assertEqual(report["fixture_scenario_count"], 30)
        self.assertEqual(report["fixture_type_counts"]["web"], 9)
        self.assertEqual(report["fixture_type_counts"]["calculator"], 1)
        self.assertEqual(report["fixture_type_counts"]["media"], 1)
        self.assertEqual(report["scenario_quality_warnings"], [])
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
                self.assertGreaterEqual(len(report["golden_failure_class_cases"][failure_class]), 2)
                for case_ref in report["golden_failure_class_cases"][failure_class]:
                    self.assertIn("case_id", case_ref)
                    self.assertIn("scenario_id", case_ref)
        golden_wrong_arguments = {
            case_ref["case_id"]
            for case_ref in report["golden_failure_class_cases"]["wrong_arguments"]
        }
        self.assertIn("GC-A2-S033-fail-wrong-calculator-arguments", golden_wrong_arguments)
        self.assertLessEqual(set(report["golden_failure_class_counts"]), CANONICAL_FAILURE_CLASSES)
        self.assertGreaterEqual(report["executable_run_case_count"], 31)
        self.assertGreaterEqual(report["executable_failure_case_count"], 29)
        self.assertEqual(report["executable_failure_classes_missing"], [])
        self.assertEqual(report["thin_executable_failure_classes"], {})
        for failure_class in CANONICAL_FAILURE_CLASSES:
            with self.subTest(executable_failure_class=failure_class):
                self.assertGreaterEqual(report["executable_failure_class_counts"][failure_class], 2)
                self.assertGreaterEqual(len(report["executable_failure_class_cases"][failure_class]), 2)
                for case_ref in report["executable_failure_class_cases"][failure_class]:
                    self.assertIn("case_id", case_ref)
                    self.assertIn("scenario_id", case_ref)
        executable_missing_tool = {
            case_ref["case_id"]
            for case_ref in report["executable_failure_class_cases"]["missing_required_tool"]
        }
        self.assertIn("sample-a2-s029-missing-required-search", executable_missing_tool)
        executable_hallucinated = {
            case_ref["case_id"]
            for case_ref in report["executable_failure_class_cases"]["hallucinated_tool_result"]
        }
        self.assertIn("sample-a2-s031-media-pipeline-unsupported-output", executable_hallucinated)
        executable_wrong_order = {
            case_ref["case_id"]
            for case_ref in report["executable_failure_class_cases"]["wrong_tool_order"]
        }
        self.assertIn("sample-a2-s042-wrong-read-order", executable_wrong_order)
        self.assertIn("sample-a2-s031-media-pipeline-wrong-order", executable_wrong_order)
        self.assertEqual(report["coverage_warnings"], [])
        self.assertLessEqual(set(report["executable_failure_class_counts"]), CANONICAL_FAILURE_CLASSES)

    def test_g3_calibration_matrix_tracks_local_ashr_llm_sources(self):
        matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        expected_matrix = json.loads((ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json").read_text(encoding="utf-8"))
        self.assertEqual(matrix, expected_matrix)
        self.assertEqual(matrix["schema_version"], "a2.calibration_matrix.v1")
        self.assertEqual(matrix["sources"], ["local_judge", "ashr_grading", "llm_judge"])
        self.assertEqual(matrix["case_count"], 6)
        self.assertEqual(matrix["source_coverage"]["local_judge"]["available"], 6)
        self.assertEqual(matrix["source_coverage"]["llm_judge"]["available"], 6)
        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["missing"], 6)
        self.assertEqual(matrix["agreement_summary"]["local_vs_llm_judge"]["comparable"], 6)
        self.assertEqual(matrix["agreement_summary"]["local_vs_llm_judge"]["mismatch_count"], 1)
        self.assertEqual(
            matrix["agreement_summary"]["local_vs_llm_judge"]["mismatches"][0]["case_id"],
            "sample-a2-s010-wrong-arguments",
        )
        cost_ledger = {row["source"]: row for row in matrix["cost_ledger"]}
        self.assertEqual(cost_ledger["llm_judge"]["sample_count"], 6)
        self.assertGreater(cost_ledger["llm_judge"]["prompt_tokens"], 0)
        self.assertGreater(cost_ledger["llm_judge"]["estimated_usd"], 0)
        self.assertIn("needs_ashr_grading", matrix["cases"][0]["calibration_tags"])
        disagreement = next(
            case for case in matrix["cases"] if case["case_id"] == "sample-a2-s010-wrong-arguments"
        )
        self.assertIn("judge_disagreement_regression", disagreement["calibration_tags"])

    def test_case_book_promotes_calibration_disagreement_regressions(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        report = build_case_book_report(calibration_matrix)
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_case_book.json").read_text(encoding="utf-8"))
        case_book_text = (ROOT / "docs/a2/case_book.md").read_text(encoding="utf-8")

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.case_book.v1")
        self.assertEqual(report["regression_case_count"], 1)
        regression = report["regression_cases"][0]
        self.assertEqual(regression["case_id"], "sample-a2-s010-wrong-arguments")
        self.assertEqual(regression["local_judge"]["primary_failure_class"], "wrong_arguments")
        self.assertEqual(regression["semantic_or_llm_judge"]["primary_failure_class"], "ignored_tool_result")
        self.assertEqual(regression["disagreement_pairs"][0]["status"], "mismatch")
        self.assertIn("sample-a2-s010-wrong-arguments", case_book_text)
        self.assertIn("wrong_arguments", case_book_text)
        self.assertIn("ignored_tool_result", case_book_text)

    def test_regression_replay_keeps_case_book_seed_executable(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        case_book = build_case_book_report(calibration_matrix)
        report = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_regression_replay_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.regression_replay.v1")
        self.assertTrue(report["replay_ready"])
        self.assertEqual(report["maturity_status"], "seed")
        self.assertEqual(report["replay_case_count"], 1)
        replay = report["cases"][0]
        self.assertEqual(replay["case_id"], "sample-a2-s010-wrong-arguments")
        self.assertEqual(replay["replay_status"], "passed")
        self.assertEqual(replay["observed_local_failure_class"], "wrong_arguments")
        self.assertEqual(replay["expected_llm_failure_class"], "ignored_tool_result")
        self.assertTrue(all(replay["checks"].values()))

    def test_sdk_parity_report_tracks_python_and_typescript_runner_contracts(self):
        report = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_sdk_parity_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.sdk_parity.v1")
        self.assertTrue(report["parity_passed"])
        self.assertEqual(report["required_languages"], ["python", "typescript"])
        self.assertEqual(set(report["passed_languages"]), {"python", "typescript"})
        self.assertEqual({case["language"] for case in report["cases"]}, {"python", "typescript"})
        for case in report["cases"]:
            with self.subTest(language=case["language"]):
                self.assertTrue(case["a2_grade"]["passed"])
                self.assertEqual(case["a2_grade"]["primary_failure_class"], "none")
                self.assertEqual(case["a2_grade"]["judge_count"], 5)

    def test_batch_plan_report_tracks_c2_quota_and_calibration_batches(self):
        coverage_report = build_coverage_report(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        case_book = build_case_book_report(calibration_matrix)
        regression_replay = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        report = build_batch_plan_report(
            coverage_report,
            calibration_matrix,
            case_book,
            sdk_parity,
            semantic_harness,
            regression_replay,
        )
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_batch_plan_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.batch_plan.v1")
        self.assertTrue(report["plan_ready"])
        self.assertEqual(report["batch_count"], 5)
        self.assertEqual({batch["batch_id"] for batch in report["batches"]}, {
            "local_full_pack_regression",
            "sdk_parity_smoke",
            "ashr_grading_tiny_calibration",
            "semantic_llm_judge_audit",
            "case_book_regression_replay",
        })
        self.assertEqual(report["quota_plan"]["queue_status_flow"], ["queued", "running", "completed"])
        self.assertIn("failed", report["quota_plan"]["failure_statuses_to_preserve"])
        self.assertEqual(report["quota_plan"]["planned_quota_units"]["run.submit"], 5)
        self.assertGreater(report["quota_plan"]["planned_quota_units"]["observation.write"], 0)
        self.assertTrue(report["readiness_checks"]["has_cost_ledger"])
        semantic_batch = next(batch for batch in report["batches"] if batch["batch_id"] == "semantic_llm_judge_audit")
        self.assertIn("fixtures/a2/results/a2_semantic_harness_report.json", semantic_batch["evidence_refs"])
        replay_batch = next(batch for batch in report["batches"] if batch["batch_id"] == "case_book_regression_replay")
        self.assertIn("fixtures/a2/results/a2_regression_replay_report.json", replay_batch["evidence_refs"])

    def test_semantic_harness_tracks_prompt_cost_redaction_and_dual_sdk_chains(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        report = build_semantic_harness_report(calibration_matrix, sdk_parity)
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_semantic_harness_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.semantic_harness.v1")
        self.assertTrue(report["harness_ready"])
        self.assertFalse(report["live_model_evidence_available"])
        self.assertEqual(report["status"], "offline_reference_only")
        self.assertEqual(report["case_count"], 6)
        self.assertEqual(report["source_matrix"]["required_languages"], ["python", "typescript"])
        self.assertEqual(set(report["source_matrix"]["covered_languages"]), {"python", "typescript"})
        self.assertTrue(report["readiness_checks"]["covers_python_and_typescript"])
        self.assertFalse(report["readiness_checks"]["live_model_evidence_available"])
        self.assertIn("prompt_tokens", report["cost_policy"]["required_fields"])
        self.assertIn("tp_* API keys", report["redaction_policy"]["secret_patterns"])
        self.assertIn("primary_failure_class", report["output_schema"]["required_fields"])
        self.assertIn("wrong_arguments", report["output_schema"]["failure_class_enum"])
        media_case = next(case for case in report["cases"] if case["case_id"] == "sample-a2-s031-media-pipeline-unsupported-output")
        self.assertIn("media", media_case["calibration_focus"])
        self.assertIn("typescript", media_case["sdk_input_paths"])

    def test_ashr_grading_batch_case_map_covers_calibration_cases(self):
        observations_payload = json.loads(
            (ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json").read_text(encoding="utf-8")
        )
        case_map = json.loads((ROOT / "fixtures/a2/calibration/ashr_grading_batch_case_map.json").read_text(encoding="utf-8"))

        calibration_cases = {case["case_id"] for case in observations_payload["cases"]}
        self.assertEqual(set(case_map.values()), calibration_cases)
        self.assertEqual(len(case_map), 6)
        for raw_case_id in case_map:
            with self.subTest(raw_case_id=raw_case_id):
                self.assertTrue(raw_case_id.startswith("ashr-a2-g3-"))

    def test_commercial_readiness_report_tracks_pdf_gates(self):
        coverage_report = build_coverage_report(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        case_book = build_case_book_report(calibration_matrix)
        regression_replay = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        batch_plan = build_batch_plan_report(
            coverage_report,
            calibration_matrix,
            case_book,
            sdk_parity,
            semantic_harness,
            regression_replay,
        )
        report = build_commercial_readiness_report(
            coverage_report,
            calibration_matrix,
            case_book_report=case_book,
            sdk_parity_report=sdk_parity,
            batch_plan_report=batch_plan,
            semantic_harness_report=semantic_harness,
            regression_replay_report=regression_replay,
        )
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_commercial_readiness_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.commercial_readiness.v1")
        self.assertEqual(report["source_goal"]["artifact"], "Ashr_Commercial_Grade_Goals_CN.pdf")
        self.assertEqual(report["current_gate"], "C2")
        self.assertFalse(report["ready_for_commercial_gate"])
        self.assertIn(
            "grade_run remains deterministic and local; live Ashr or LLM calls enter calibration/readiness only.",
            report["contract_invariants"],
        )
        self.assertIn(
            "top-level primary_failure_class remains one of the canonical A2 failure classes or none.",
            report["contract_invariants"],
        )
        gates = {gate["gate"]: gate for gate in report["gate_status"]}
        self.assertEqual(gates["C0"]["status"], "met")
        self.assertEqual(gates["C1"]["status"], "met")
        self.assertEqual(gates["C2"]["status"], "met")
        self.assertEqual(gates["C3"]["status"], "partial")
        self.assertIn("Collect reviewed Ashr grading observations", gates["C3"]["gaps"][0])
        self.assertEqual(gates["C4"]["status"], "partial")
        self.assertIn("offline", gates["C4"]["gaps"][0])
        self.assertIn("fixtures/a2/results/a2_semantic_harness_report.json", gates["C4"]["evidence_refs"])
        self.assertEqual(report["evidence_snapshot"]["ashr_grading_missing"], 6)
        self.assertTrue(report["evidence_snapshot"]["llm_judge_offline_only"])
        self.assertTrue(report["evidence_snapshot"]["semantic_harness_ready"])
        self.assertFalse(report["evidence_snapshot"]["semantic_harness_live_evidence"])
        self.assertEqual(report["evidence_snapshot"]["case_book_regression_count"], 1)
        self.assertEqual(report["evidence_snapshot"]["regression_replay_count"], 1)
        self.assertTrue(report["evidence_snapshot"]["regression_replay_ready"])
        self.assertEqual(report["evidence_snapshot"]["regression_replay_maturity"], "seed")
        self.assertEqual(report["evidence_snapshot"]["sdk_language_count"], 2)
        self.assertTrue(report["evidence_snapshot"]["sdk_parity_passed"])
        self.assertEqual(report["evidence_snapshot"]["planned_batch_count"], 5)
        self.assertTrue(report["evidence_snapshot"]["batch_plan_ready"])
        self.assertEqual(report["next_top_3"][0]["id"], "fill_ashr_grading_column")

    def test_ashr_grading_import_can_fill_calibration_matrix_source(self):
        sample = json.loads((ROOT / "fixtures/a2/calibration/ashr_grading_import_sample.json").read_text(encoding="utf-8"))
        case_map = json.loads((ROOT / "fixtures/a2/calibration/ashr_grading_import_case_map.json").read_text(encoding="utf-8"))
        observations = import_ashr_grading_observations(
            sample,
            case_map=case_map,
            evidence_ref="docs/evidence/private_refs/a2_ashr_grading_sample.redacted.json",
        )
        self.assertEqual(len(observations), 2)
        self.assertEqual([observation["source"] for observation in observations], ["ashr_grading", "ashr_grading"])
        self.assertEqual(observations[0]["case_id"], "sample-a2-s001-pass")
        self.assertEqual(observations[0]["primary_failure_class"], "none")
        self.assertEqual(observations[1]["case_id"], "sample-a2-s010-wrong-arguments")
        self.assertEqual(observations[1]["primary_failure_class"], "wrong_arguments")
        self.assertEqual(observations[1]["metadata"]["raw_case_id"], "ashr-wrong-contract-path")
        secret_sample = json.loads(json.dumps(sample))
        secret_sample["response"]["run"]["result"]["tests"][1]["action_results"][0]["divergence_notes"] = (
            "Bearer secret-token for kay@example.test"
        )
        redacted = import_ashr_grading_observations(secret_sample, case_map=case_map)
        self.assertNotIn("Bearer ", redacted[1]["rationale"])
        self.assertNotIn("@", redacted[1]["rationale"])

        payload = json.loads((ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json").read_text(encoding="utf-8"))
        payload = merge_calibration_observations(payload, {"observations": observations})
        merged_ashr = [observation for observation in payload["observations"] if observation["source"] == "ashr_grading"]
        self.assertEqual(len(merged_ashr), 2)
        self.assertEqual(merged_ashr[0]["scenario_id"], "A2-S001")
        self.assertEqual(merged_ashr[1]["scenario_id"], "A2-S010")
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "observations.json"
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            matrix = build_calibration_matrix(
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                run_dir=ROOT / "fixtures/a2/runs",
                observations_path=path,
            )

        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["available"], 2)
        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["missing"], 4)
        self.assertEqual(matrix["agreement_summary"]["local_vs_ashr_grading"]["comparable"], 2)
        self.assertEqual(matrix["agreement_summary"]["local_vs_ashr_grading"]["mismatch_count"], 0)

    def test_ashr_grading_merge_cli_outputs_reviewed_calibration_payload(self):
        sample = json.loads((ROOT / "fixtures/a2/calibration/ashr_grading_import_sample.json").read_text(encoding="utf-8"))
        case_map = json.loads((ROOT / "fixtures/a2/calibration/ashr_grading_import_case_map.json").read_text(encoding="utf-8"))
        observations = import_ashr_grading_observations(sample, case_map=case_map)

        with tempfile.TemporaryDirectory() as tmp_dir:
            incoming = Path(tmp_dir) / "incoming.json"
            incoming.write_text(json.dumps({"observations": observations}, indent=2) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/a2_merge_calibration_observations.py"),
                    "--base",
                    str(ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json"),
                    "--incoming",
                    str(incoming),
                    "--source",
                    "ashr_grading",
                    "--min-count",
                    "2",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        merged = json.loads(result.stdout)
        self.assertEqual(merged["schema_version"], "a2.calibration_observations.v1")
        self.assertEqual(sum(1 for item in merged["observations"] if item["source"] == "ashr_grading"), 2)
        self.assertIn("sample-a2-s010-wrong-arguments", {item["case_id"] for item in merged["observations"]})

    def test_ashr_grading_import_cli_outputs_redacted_observations(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/a2_import_ashr_grading.py"),
                "--input",
                str(ROOT / "fixtures/a2/calibration/ashr_grading_import_sample.json"),
                "--case-map",
                str(ROOT / "fixtures/a2/calibration/ashr_grading_import_case_map.json"),
                "--evidence-ref",
                "docs/evidence/private_refs/a2_ashr_grading_sample.redacted.json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], "a2.ashr_grading_import.v1")
        self.assertEqual(payload["observation_count"], 2)
        self.assertNotIn("Bearer ", result.stdout)
        self.assertNotIn("@", result.stdout)

    def test_semantic_judge_import_can_replace_offline_llm_rows(self):
        sample = json.loads((ROOT / "fixtures/a2/calibration/semantic_judge_import_sample.json").read_text(encoding="utf-8"))
        observations = import_semantic_judge_observations(
            sample,
            evidence_ref="docs/evidence/private_refs/a2_semantic_judge_sample.redacted.json",
        )
        self.assertEqual(len(observations), 2)
        self.assertEqual([observation["source"] for observation in observations], ["llm_judge", "llm_judge"])
        self.assertEqual(observations[0]["case_id"], "sample-a2-s001-pass")
        self.assertEqual(observations[0]["primary_failure_class"], "none")
        self.assertEqual(observations[1]["case_id"], "sample-a2-s031-media-pipeline-unsupported-output")
        self.assertEqual(observations[1]["primary_failure_class"], "hallucinated_tool_result")
        self.assertEqual(observations[1]["metadata"]["sdk_language"], "typescript")
        self.assertNotIn("Bearer ", observations[1]["rationale"])
        self.assertNotIn("@", observations[1]["rationale"])

        payload = json.loads((ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json").read_text(encoding="utf-8"))
        payload = merge_calibration_observations(payload, {"observations": observations}, source="llm_judge")
        merged_llm = [observation for observation in payload["observations"] if observation["source"] == "llm_judge"]
        self.assertEqual(len(merged_llm), 6)
        merged_by_case = {observation["case_id"]: observation for observation in merged_llm}
        self.assertEqual(merged_by_case["sample-a2-s031-media-pipeline-unsupported-output"]["provider"], "reviewed_model_call_sample")
        self.assertEqual(merged_by_case["sample-a2-s031-media-pipeline-unsupported-output"]["scenario_id"], "A2-S031")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "observations.json"
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            matrix = build_calibration_matrix(
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                run_dir=ROOT / "fixtures/a2/runs",
                observations_path=path,
            )

        cost_ledger = {row["source"]: row for row in matrix["cost_ledger"]}
        self.assertEqual(cost_ledger["llm_judge"]["sample_count"], 6)
        self.assertIn("reviewed_model_call_sample", cost_ledger["llm_judge"]["provider_counts"])
        self.assertIn("offline_reference", cost_ledger["llm_judge"]["provider_counts"])

    def test_semantic_judge_import_cli_outputs_redacted_observations(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/a2_import_semantic_judge.py"),
                "--input",
                str(ROOT / "fixtures/a2/calibration/semantic_judge_import_sample.json"),
                "--evidence-ref",
                "docs/evidence/private_refs/a2_semantic_judge_sample.redacted.json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], "a2.semantic_judge_import.v1")
        self.assertEqual(payload["observation_count"], 2)
        self.assertNotIn("Bearer ", result.stdout)
        self.assertNotIn("@", result.stdout)

    def test_real_api_smoke_evidence_is_redacted(self):
        evidence_path = ROOT / "docs/evidence/a2_real_api_smoke.json"
        payload_text = evidence_path.read_text(encoding="utf-8")
        payload = json.loads(payload_text)

        self.assertEqual(payload["schema_version"], "a2.real_api_smoke.v1")
        self.assertEqual(payload["api_call_count"], 6)
        self.assertTrue(payload["all_required_calls_reached"])
        self.assertEqual([call["status"] for call in payload["calls"]], ["ok"] * 6)
        self.assertNotRegex(payload_text, re.compile(r"tp_[A-Za-z0-9_\\-]+"))
        self.assertNotIn("Bearer ", payload_text)
        self.assertNotIn("@", payload_text)
        for call in payload["calls"]:
            self.assertNotIn("payload", call)
            self.assertNotIn("response", call)


if __name__ == "__main__":
    unittest.main()
