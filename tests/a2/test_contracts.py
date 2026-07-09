import json
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from services.judge.batch_plan import build_batch_plan_report
from services.judge.ashr_collection import build_ashr_grading_collection_packet
from services.judge.calibration import (
    build_calibration_matrix,
    import_ashr_grading_observations,
    import_semantic_judge_observations,
    merge_calibration_observations,
)
from services.judge.casebook import build_case_book_report
from services.judge.coverage import build_coverage_report
from services.judge.evidence_readiness import build_evidence_readiness_report
from services.judge.incident_regression import build_incident_regression_candidate_report
from services.judge.readiness import build_commercial_readiness_report
from services.judge.release_gate import build_release_gate_report
from services.judge.regression_promotion import build_regression_promotion_queue_report
from services.judge.regression_replay import build_regression_replay_report
from services.judge.runner import grade_run, grade_runs, load_scenario_pack
from services.judge.scenario_selection import build_scenario_selection_report
from services.judge.schemas import CANONICAL_FAILURE_CLASSES, LOCAL_FAILURE_CLASS_MAP, canonical_primary_failure_class
from services.judge.sdk_parity import build_sdk_parity_report
from services.judge.semantic_collection import build_semantic_judge_collection_packet
from services.judge.semantic_harness import build_semantic_harness_report
from services.judge.unblock_checklist import build_release_unblock_checklist


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
        ashr_collection_schema = json.loads((schema_dir / "ashr_grading_collection_packet.schema.json").read_text(encoding="utf-8"))
        semantic_collection_schema = json.loads((schema_dir / "semantic_judge_collection_packet.schema.json").read_text(encoding="utf-8"))
        semantic_harness_schema = json.loads((schema_dir / "semantic_harness.schema.json").read_text(encoding="utf-8"))
        regression_replay_schema = json.loads((schema_dir / "regression_replay.schema.json").read_text(encoding="utf-8"))
        incident_regression_schema = json.loads((schema_dir / "incident_regression_candidates.schema.json").read_text(encoding="utf-8"))
        regression_promotion_schema = json.loads((schema_dir / "regression_promotion_queue.schema.json").read_text(encoding="utf-8"))
        evidence_readiness_schema = json.loads((schema_dir / "evidence_readiness.schema.json").read_text(encoding="utf-8"))
        release_gate_schema = json.loads((schema_dir / "release_gate.schema.json").read_text(encoding="utf-8"))
        unblock_checklist_schema = json.loads((schema_dir / "release_unblock_checklist.schema.json").read_text(encoding="utf-8"))
        scenario_selection_schema = json.loads((schema_dir / "scenario_selection.schema.json").read_text(encoding="utf-8"))
        external_preflight_schema = json.loads((schema_dir / "external_evidence_preflight.schema.json").read_text(encoding="utf-8"))
        real_api_smoke_schema = json.loads((schema_dir / "real_api_smoke.schema.json").read_text(encoding="utf-8"))
        evidence_index_schema = json.loads((schema_dir / "evidence_index.schema.json").read_text(encoding="utf-8"))
        sql_store_schema = json.loads((schema_dir / "sql_store_report.schema.json").read_text(encoding="utf-8"))
        scenario_generation_schema = json.loads((schema_dir / "scenario_generation_backlog.schema.json").read_text(encoding="utf-8"))
        cross_lane_security_schema = json.loads((schema_dir / "cross_lane_security_context.schema.json").read_text(encoding="utf-8"))
        grade_report = json.loads((ROOT / "fixtures/a2/results/a2_g3_grade_results.json").read_text(encoding="utf-8"))
        coverage_report = json.loads((ROOT / "fixtures/a2/results/a2_g3_coverage_report.json").read_text(encoding="utf-8"))
        calibration_matrix = json.loads((ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json").read_text(encoding="utf-8"))
        readiness_report = json.loads((ROOT / "fixtures/a2/results/a2_commercial_readiness_report.json").read_text(encoding="utf-8"))
        case_book = json.loads((ROOT / "fixtures/a2/results/a2_case_book.json").read_text(encoding="utf-8"))
        sdk_parity = json.loads((ROOT / "fixtures/a2/results/a2_sdk_parity_report.json").read_text(encoding="utf-8"))
        batch_plan = json.loads((ROOT / "fixtures/a2/results/a2_batch_plan_report.json").read_text(encoding="utf-8"))
        ashr_collection = json.loads((ROOT / "fixtures/a2/calibration/a2_ashr_grading_collection_packet.json").read_text(encoding="utf-8"))
        semantic_collection = json.loads((ROOT / "fixtures/a2/calibration/a2_semantic_judge_collection_packet.json").read_text(encoding="utf-8"))
        semantic_harness = json.loads((ROOT / "fixtures/a2/results/a2_semantic_harness_report.json").read_text(encoding="utf-8"))
        regression_replay = json.loads((ROOT / "fixtures/a2/results/a2_regression_replay_report.json").read_text(encoding="utf-8"))
        incident_regression = json.loads((ROOT / "fixtures/a2/results/a2_incident_regression_candidates.json").read_text(encoding="utf-8"))
        regression_promotion = json.loads((ROOT / "fixtures/a2/results/a2_regression_promotion_queue.json").read_text(encoding="utf-8"))
        evidence_readiness = json.loads((ROOT / "fixtures/a2/results/a2_evidence_readiness_report.json").read_text(encoding="utf-8"))
        release_gate = json.loads((ROOT / "fixtures/a2/results/a2_release_gate_report.json").read_text(encoding="utf-8"))
        unblock_checklist = json.loads((ROOT / "fixtures/a2/results/a2_release_unblock_checklist.json").read_text(encoding="utf-8"))
        scenario_selection = json.loads((ROOT / "fixtures/a2/results/a2_scenario_selection_report.json").read_text(encoding="utf-8"))
        evidence_index = json.loads((ROOT / "docs/a1/api_calibration/real_api_evidence_index.json").read_text(encoding="utf-8"))
        sql_store = json.loads((ROOT / "fixtures/a2/results/a2_sql_store_report.json").read_text(encoding="utf-8"))
        scenario_generation = json.loads((ROOT / "fixtures/a2/results/a2_scenario_generation_backlog.json").read_text(encoding="utf-8"))
        cross_lane_security = json.loads((ROOT / "fixtures/a2/results/a2_cross_lane_security_context.json").read_text(encoding="utf-8"))

        self.assertEqual(grade_schema["properties"]["schema_version"]["const"], grade_report["schema_version"])
        self.assertEqual(coverage_schema["properties"]["schema_version"]["const"], coverage_report["schema_version"])
        self.assertEqual(calibration_schema["properties"]["schema_version"]["const"], calibration_matrix["schema_version"])
        self.assertEqual(readiness_schema["properties"]["schema_version"]["const"], readiness_report["schema_version"])
        self.assertEqual(case_book_schema["properties"]["schema_version"]["const"], case_book["schema_version"])
        self.assertEqual(sdk_parity_schema["properties"]["schema_version"]["const"], sdk_parity["schema_version"])
        self.assertEqual(batch_plan_schema["properties"]["schema_version"]["const"], batch_plan["schema_version"])
        self.assertEqual(
            ashr_collection_schema["properties"]["schema_version"]["const"],
            ashr_collection["schema_version"],
        )
        self.assertEqual(
            semantic_collection_schema["properties"]["schema_version"]["const"],
            semantic_collection["schema_version"],
        )
        self.assertEqual(
            semantic_harness_schema["properties"]["schema_version"]["const"],
            semantic_harness["schema_version"],
        )
        self.assertEqual(
            regression_replay_schema["properties"]["schema_version"]["const"],
            regression_replay["schema_version"],
        )
        self.assertEqual(
            incident_regression_schema["properties"]["schema_version"]["const"],
            incident_regression["schema_version"],
        )
        self.assertEqual(
            regression_promotion_schema["properties"]["schema_version"]["const"],
            regression_promotion["schema_version"],
        )
        self.assertEqual(
            evidence_readiness_schema["properties"]["schema_version"]["const"],
            evidence_readiness["schema_version"],
        )
        self.assertEqual(
            release_gate_schema["properties"]["schema_version"]["const"],
            release_gate["schema_version"],
        )
        self.assertEqual(
            unblock_checklist_schema["properties"]["schema_version"]["const"],
            unblock_checklist["schema_version"],
        )
        self.assertEqual(
            scenario_selection_schema["properties"]["schema_version"]["const"],
            scenario_selection["schema_version"],
        )
        self.assertEqual(
            sql_store_schema["properties"]["schema_version"]["const"],
            sql_store["schema_version"],
        )
        self.assertEqual(
            scenario_generation_schema["properties"]["schema_version"]["const"],
            scenario_generation["schema_version"],
        )
        self.assertEqual(
            cross_lane_security_schema["properties"]["schema_version"]["const"],
            cross_lane_security["schema_version"],
        )
        self.assertLessEqual(set(grade_schema["required"]), set(grade_report))
        self.assertLessEqual(set(coverage_schema["required"]), set(coverage_report))
        self.assertLessEqual(set(calibration_schema["required"]), set(calibration_matrix))
        self.assertLessEqual(set(readiness_schema["required"]), set(readiness_report))
        self.assertIn("growth_auditor", readiness_schema["required"])
        self.assertEqual(
            readiness_schema["properties"]["growth_auditor"]["$ref"],
            "#/$defs/growth_auditor",
        )
        self.assertIn("real_api_total_records", readiness_schema["$defs"]["evidence_snapshot"]["required"])
        self.assertIn("official_sdk_smoke_read_only_reachable", readiness_schema["$defs"]["evidence_snapshot"]["required"])
        self.assertLessEqual(set(case_book_schema["required"]), set(case_book))
        self.assertLessEqual(set(sdk_parity_schema["required"]), set(sdk_parity))
        self.assertLessEqual(set(batch_plan_schema["required"]), set(batch_plan))
        self.assertLessEqual(set(ashr_collection_schema["required"]), set(ashr_collection))
        self.assertLessEqual(set(semantic_collection_schema["required"]), set(semantic_collection))
        self.assertLessEqual(set(semantic_harness_schema["required"]), set(semantic_harness))
        self.assertLessEqual(set(regression_replay_schema["required"]), set(regression_replay))
        self.assertIn("release_gate_summary", regression_replay_schema["required"])
        self.assertEqual(
            regression_replay_schema["properties"]["release_gate_summary"]["$ref"],
            "#/$defs/release_gate_summary",
        )
        self.assertLessEqual(set(incident_regression_schema["required"]), set(incident_regression))
        self.assertLessEqual(set(regression_promotion_schema["required"]), set(regression_promotion))
        self.assertLessEqual(set(evidence_readiness_schema["required"]), set(evidence_readiness))
        self.assertLessEqual(set(release_gate_schema["required"]), set(release_gate))
        self.assertLessEqual(set(unblock_checklist_schema["required"]), set(unblock_checklist))
        self.assertLessEqual(set(scenario_selection_schema["required"]), set(scenario_selection))
        self.assertLessEqual(set(sql_store_schema["required"]), set(sql_store))
        self.assertLessEqual(set(scenario_generation_schema["required"]), set(scenario_generation))
        self.assertLessEqual(set(cross_lane_security_schema["required"]), set(cross_lane_security))
        self.assertIn("promotion_gate", scenario_generation_schema["required"])
        self.assertIn("a2_policy_implications", cross_lane_security_schema["required"])
        self.assertIn("risk_assessment", semantic_harness_schema["required"])
        self.assertIn("a1_real_api_evidence", evidence_readiness_schema["required"])
        self.assertIn("a1_official_api_readonly_manifest", evidence_readiness_schema["required"])
        self.assertIn("a1_official_api_mutating_index", evidence_readiness_schema["required"])
        self.assertIn("a1_official_api_paid_media_summary", evidence_readiness_schema["required"])
        self.assertIn("a1_payment_provider_readiness", evidence_readiness_schema["required"])
        self.assertIn("a1_billing_replay_evidence", evidence_readiness_schema["required"])
        self.assertIn("a1_billing_ledger_migration", evidence_readiness_schema["required"])
        self.assertIn("a1_billing_sql_semantic_contract", evidence_readiness_schema["required"])
        self.assertIn("ashr_public_merge_gate", evidence_readiness_schema["required"])
        self.assertIn("official_sdk_smoke", evidence_readiness_schema["required"])
        self.assertIn("semantic_live_merge_gate", evidence_readiness_schema["required"])
        a1_real_api_required = set(evidence_readiness_schema["$defs"]["a1_real_api_evidence"]["required"])
        self.assertLessEqual(a1_real_api_required, set(evidence_readiness["a1_real_api_evidence"]))
        self.assertIn("real_quota_gate", a1_real_api_required)
        self.assertEqual(
            evidence_readiness_schema["properties"]["a1_real_api_evidence"]["$ref"],
            "#/$defs/a1_real_api_evidence",
        )
        quota_gate_required = set(evidence_readiness_schema["$defs"]["real_quota_gate"]["required"])
        self.assertLessEqual(quota_gate_required, set(evidence_readiness["a1_real_api_evidence"]["real_quota_gate"]))
        self.assertIn("create_request_blocked", quota_gate_required)
        api_probe_gate_required = set(evidence_readiness_schema["$defs"]["api_probe_gate_validation"]["required"])
        self.assertLessEqual(
            api_probe_gate_required,
            set(evidence_readiness["a1_real_api_evidence"]["api_probe_gate_validation"]),
        )
        self.assertIn("validate_gate_count", api_probe_gate_required)
        official_manifest_required = set(evidence_readiness_schema["$defs"]["a1_official_api_readonly_manifest"]["required"])
        self.assertLessEqual(
            official_manifest_required,
            set(evidence_readiness["a1_official_api_readonly_manifest"]),
        )
        self.assertIn("ready_for_a2_evidence_context", official_manifest_required)
        mutating_index_required = set(evidence_readiness_schema["$defs"]["a1_official_api_mutating_index"]["required"])
        self.assertLessEqual(
            mutating_index_required,
            set(evidence_readiness["a1_official_api_mutating_index"]),
        )
        self.assertIn("mutating_step_count", mutating_index_required)
        self.assertIn("c3_grading_ready", mutating_index_required)
        paid_media_required = set(evidence_readiness_schema["$defs"]["a1_official_api_paid_media_summary"]["required"])
        self.assertLessEqual(
            paid_media_required,
            set(evidence_readiness["a1_official_api_paid_media_summary"]),
        )
        self.assertIn("safe_for_paid_media_claims", paid_media_required)
        self.assertIn("c3_grading_ready", paid_media_required)
        paid_media_guardrail_required = set(evidence_readiness_schema["$defs"]["paid_media_guardrails"]["required"])
        self.assertLessEqual(
            paid_media_guardrail_required,
            set(evidence_readiness["a1_official_api_paid_media_summary"]["guardrails"]),
        )
        self.assertIn("paid_media_requires_allow_paid_media", paid_media_guardrail_required)
        payment_provider_required = set(evidence_readiness_schema["$defs"]["a1_payment_provider_readiness"]["required"])
        self.assertLessEqual(
            payment_provider_required,
            set(evidence_readiness["a1_payment_provider_readiness"]),
        )
        self.assertIn("ready_for_a2_payment_policy_context", payment_provider_required)
        self.assertIn("c3_grading_ready", payment_provider_required)
        self.assertEqual(
            evidence_readiness_schema["properties"]["a1_payment_provider_readiness"]["$ref"],
            "#/$defs/a1_payment_provider_readiness",
        )
        billing_replay_required = set(evidence_readiness_schema["$defs"]["a1_billing_replay_evidence"]["required"])
        self.assertLessEqual(
            billing_replay_required,
            set(evidence_readiness["a1_billing_replay_evidence"]),
        )
        self.assertIn("duplicate_idempotency_proven", billing_replay_required)
        self.assertIn("c3_grading_ready", billing_replay_required)
        self.assertEqual(
            evidence_readiness_schema["properties"]["a1_billing_replay_evidence"]["$ref"],
            "#/$defs/a1_billing_replay_evidence",
        )
        billing_migration_required = set(evidence_readiness_schema["$defs"]["a1_billing_ledger_migration"]["required"])
        self.assertLessEqual(
            billing_migration_required,
            set(evidence_readiness["a1_billing_ledger_migration"]),
        )
        self.assertIn("tenant_rls_ready", billing_migration_required)
        self.assertIn("c3_grading_ready", billing_migration_required)
        self.assertEqual(
            evidence_readiness_schema["properties"]["a1_billing_ledger_migration"]["$ref"],
            "#/$defs/a1_billing_ledger_migration",
        )
        billing_sql_required = set(evidence_readiness_schema["$defs"]["a1_billing_sql_semantic_contract"]["required"])
        self.assertLessEqual(
            billing_sql_required,
            set(evidence_readiness["a1_billing_sql_semantic_contract"]),
        )
        self.assertIn("ready_for_a2_sql_policy_context", billing_sql_required)
        self.assertIn("c3_grading_ready", billing_sql_required)
        self.assertEqual(
            evidence_readiness_schema["properties"]["a1_billing_sql_semantic_contract"]["$ref"],
            "#/$defs/a1_billing_sql_semantic_contract",
        )
        official_smoke_required = set(evidence_readiness_schema["$defs"]["official_sdk_smoke"]["required"])
        self.assertLessEqual(official_smoke_required, set(evidence_readiness["official_sdk_smoke"]))
        self.assertIn("read_only_reachable", official_smoke_required)
        self.assertEqual(
            evidence_readiness_schema["properties"]["official_sdk_smoke"]["$ref"],
            "#/$defs/official_sdk_smoke",
        )
        self.assertEqual(
            external_preflight_schema["properties"]["schema_version"]["const"],
            "a2.external_evidence_preflight.v1",
        )
        self.assertIn("real_api_evidence_refresh", external_preflight_schema["properties"]["recommended_commands"]["required"])
        self.assertEqual(
            real_api_smoke_schema["properties"]["schema_version"]["const"],
            "a2.real_api_smoke.v1",
        )
        self.assertIn("calls", real_api_smoke_schema["required"])
        self.assertEqual(
            evidence_index_schema["properties"]["schema_version"]["const"],
            evidence_index["schema_version"],
        )
        self.assertLessEqual(set(evidence_index_schema["required"]), set(evidence_index))

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

        exemplar_required = set(coverage_schema["$defs"]["capability_axis_exemplar"]["required"])
        for axis, exemplars in coverage_report["capability_axis_exemplars"].items():
            with self.subTest(capability_axis_exemplar_schema=axis):
                self.assertEqual(len(exemplars), 2)
                for exemplar in exemplars:
                    self.assertLessEqual(exemplar_required, set(exemplar))

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
        readiness_snapshot_required = set(readiness_schema["$defs"]["evidence_snapshot"]["required"])
        self.assertLessEqual(readiness_snapshot_required, set(readiness_report["evidence_snapshot"]))
        self.assertIn("ashr_safe_to_mark_c3_met", readiness_snapshot_required)
        self.assertIn("semantic_safe_to_mark_c4_met", readiness_snapshot_required)
        self.assertIn("semantic_risk_assessment_status", readiness_snapshot_required)

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

        ashr_collection_case_required = set(ashr_collection_schema["$defs"]["collection_case"]["required"])
        for collection_case in ashr_collection["cases"]:
            with self.subTest(ashr_collection_case=collection_case["case_id"]):
                self.assertLessEqual(ashr_collection_case_required, set(collection_case))

        semantic_collection_case_required = set(semantic_collection_schema["$defs"]["collection_case"]["required"])
        for collection_case in semantic_collection["cases"]:
            with self.subTest(semantic_collection_case=collection_case["case_id"]):
                self.assertLessEqual(semantic_collection_case_required, set(collection_case))

        harness_case_required = set(semantic_harness_schema["$defs"]["harness_case"]["required"])
        self.assertIn("risk_flags", harness_case_required)
        for harness_case in semantic_harness["cases"]:
            with self.subTest(semantic_harness_case=harness_case["case_id"]):
                self.assertLessEqual(harness_case_required, set(harness_case))

        replay_case_required = set(regression_replay_schema["$defs"]["replay_case"]["required"])
        for replay_case in regression_replay["cases"]:
            with self.subTest(regression_replay_case=replay_case["case_id"]):
                self.assertLessEqual(replay_case_required, set(replay_case))
        replay_gate_required = set(regression_replay_schema["$defs"]["release_gate_summary"]["required"])
        self.assertLessEqual(replay_gate_required, set(regression_replay["release_gate_summary"]))

        incident_candidate_required = set(incident_regression_schema["$defs"]["candidate"]["required"])
        for candidate in incident_regression["candidates"]:
            with self.subTest(incident_regression_candidate=candidate["case_id"]):
                self.assertLessEqual(incident_candidate_required, set(candidate))
        promotion_item_required = set(regression_promotion_schema["$defs"]["promotion_item"]["required"])
        for item in regression_promotion["promotion_items"]:
            with self.subTest(regression_promotion_item=item["case_id"]):
                self.assertLessEqual(promotion_item_required, set(item))

        evidence_case_required = set(evidence_readiness_schema["$defs"]["calibration_case"]["required"])
        for evidence_case in evidence_readiness["calibration_cases"]:
            with self.subTest(evidence_readiness_case=evidence_case["case_id"]):
                self.assertLessEqual(evidence_case_required, set(evidence_case))

        release_blocker_required = set(release_gate_schema["$defs"]["release_item"]["required"])
        for blocker in release_gate["blockers"]:
            with self.subTest(release_gate_blocker=blocker["type"]):
                self.assertLessEqual(release_blocker_required, set(blocker))

        unblock_gate_required = set(unblock_checklist_schema["$defs"]["gate_item"]["required"])
        unblock_action_required = set(unblock_checklist_schema["$defs"]["action_item"]["required"])
        for gate_item in unblock_checklist["gate_items"]:
            with self.subTest(unblock_gate=gate_item["gate"]):
                self.assertLessEqual(unblock_gate_required, set(gate_item))
                for action in gate_item["required_actions"]:
                    self.assertLessEqual(unblock_action_required, set(action))

        selected_scenario_required = set(scenario_selection_schema["$defs"]["selected_scenario"]["required"])
        for selected_scenario in scenario_selection["selected_scenarios"]:
            with self.subTest(selected_scenario=selected_scenario["scenario_id"]):
                self.assertLessEqual(selected_scenario_required, set(selected_scenario))

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
        self.assertEqual(len(report["capability_axis_checks"]), 11)
        self.assertTrue(all(report["capability_axis_checks"].values()))
        self.assertEqual(report["missing_capability_axes"], [])
        self.assertEqual(report["capability_axis_counts"]["tool_choice_and_policy"], 60)
        self.assertEqual(report["capability_axis_counts"]["multi_step_workflow"], 15)
        self.assertEqual(report["capability_axis_counts"]["trace_contract"], 32)
        self.assertEqual(report["capability_axis_counts"]["media_and_multimodal"], 2)
        self.assertGreaterEqual(report["capability_axis_counts"]["enterprise_saas_operations"], 8)
        self.assertIn("A2-S031", report["capability_axis_scenarios"]["media_and_multimodal"])
        self.assertIn("A2-S052", report["capability_axis_scenarios"]["enterprise_saas_operations"])
        self.assertIn("required_tool_use", report["capability_axis_dimension_map"]["trace_contract"])
        self.assertIn("enterprise_saas_operation", report["capability_axis_dimension_map"]["enterprise_saas_operations"])
        self.assertEqual(len(report["capability_axis_exemplars"]), 11)
        for axis, exemplars in report["capability_axis_exemplars"].items():
            with self.subTest(capability_axis=axis):
                self.assertEqual(len(exemplars), 2)
                self.assertIn(axis, report["capability_axis_scenarios"])
                for exemplar in exemplars:
                    self.assertIn(exemplar["scenario_id"], report["capability_axis_scenarios"][axis])
                    self.assertTrue(exemplar["why_it_matters"].startswith("Shows "))
                    self.assertIn("Evidence signals:", exemplar["why_it_matters"])
                    self.assertIn("required", exemplar["tool_policy_shape"])
                    self.assertIn(exemplar["primary_failure_class"], CANONICAL_FAILURE_CLASSES)
        media_exemplar_ids = {
            exemplar["scenario_id"]
            for exemplar in report["capability_axis_exemplars"]["media_and_multimodal"]
        }
        self.assertIn("A2-S031", media_exemplar_ids)
        self.assertTrue(
            any(
                exemplar["tool_policy_shape"]["ordered"]
                for exemplar in report["capability_axis_exemplars"]["media_and_multimodal"]
            )
        )
        saas_exemplar_ids = {
            exemplar["scenario_id"]
            for exemplar in report["capability_axis_exemplars"]["enterprise_saas_operations"]
        }
        self.assertTrue({"A2-S031", "A2-S052"} & saas_exemplar_ids)
        self.assertTrue(
            any(
                "enterprise SaaS workflow" in exemplar["why_it_matters"]
                for exemplar in report["capability_axis_exemplars"]["enterprise_saas_operations"]
            )
        )
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
        self.assertGreaterEqual(report["executable_run_case_count"], 32)
        self.assertGreaterEqual(report["executable_failure_case_count"], 30)
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
        media_cases = {case_ref["case_id"] for case_ref in report["executable_media_case_refs"]}
        self.assertEqual(report["executable_media_case_count"], 4)
        self.assertEqual(report["executable_tool_output_grounding_case_count"], 4)
        self.assertEqual(
            report["executable_media_expected_class_counts"],
            {
                "hallucinated_tool_result": 1,
                "none": 1,
                "wrong_arguments": 1,
                "wrong_tool_order": 1,
            },
        )
        self.assertIn("sample-a2-s031-media-pipeline-pass", media_cases)
        self.assertIn("sample-a2-s031-media-pipeline-wrong-classifier-args", media_cases)
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
        self.assertEqual(report["candidate_pool"]["local_llm_mismatch_count"], 1)
        self.assertEqual(report["candidate_pool"]["ashr_grading_missing_count"], 6)
        self.assertEqual(report["candidate_pool"]["reviewed_external_evidence_count"], 0)
        self.assertEqual(report["maturity_gate"]["status"], "seed")
        self.assertFalse(report["maturity_gate"]["ready"])
        self.assertEqual(report["maturity_gate"]["target_regression_case_count"], 3)
        self.assertEqual(report["maturity_gate"]["reviewed_evidence_target_count"], 3)
        self.assertEqual(report["maturity_gate"]["reviewed_external_evidence_count"], 0)
        self.assertFalse(report["maturity_gate"]["review_evidence_ready"])
        self.assertIn("Promote 2 more", report["maturity_gate"]["gaps"][0])
        self.assertIn("reviewed Ashr grading or audited semantic evidence", report["maturity_gate"]["gaps"][1])
        regression = report["regression_cases"][0]
        self.assertEqual(regression["case_id"], "sample-a2-s010-wrong-arguments")
        self.assertFalse(regression["ashr_grading"]["available"])
        self.assertEqual(regression["local_judge"]["primary_failure_class"], "wrong_arguments")
        self.assertEqual(regression["semantic_or_llm_judge"]["primary_failure_class"], "ignored_tool_result")
        self.assertEqual(regression["semantic_or_llm_judge"]["provider"], "offline_reference")
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
        self.assertEqual(report["maturity_gate"]["status"], "seed")
        self.assertFalse(report["maturity_gate"]["ready"])
        self.assertEqual(report["maturity_gate"]["target_replay_case_count"], 3)
        self.assertEqual(report["maturity_gate"]["current_replay_case_count"], 1)
        self.assertEqual(report["maturity_gate"]["missing_replay_case_count"], 2)
        self.assertEqual(report["maturity_gate"]["failed_replay_case_count"], 0)
        self.assertFalse(report["maturity_gate"]["case_book_maturity_ready"])
        self.assertEqual(report["maturity_gate"]["reviewed_external_evidence_count"], 0)
        self.assertEqual(report["maturity_gate"]["missing_reviewed_evidence_count"], 3)
        self.assertEqual(report["maturity_gate"]["missing_reviewed_replay_cases"], 3)
        self.assertIn("Replay 2 more", report["maturity_gate"]["gaps"][0])
        self.assertIn("case-book maturity gate open", report["maturity_gate"]["gaps"][1])
        self.assertEqual(report["release_gate_summary"]["schema_version"], "a2.regression_replay.release_gate_summary.v1")
        self.assertEqual(report["release_gate_summary"]["gate"], "C5")
        self.assertEqual(report["release_gate_summary"]["release_gate_status"], "blocked")
        self.assertTrue(report["release_gate_summary"]["blocks_release"])
        self.assertEqual(report["release_gate_summary"]["action"], "promote_more_regressions")
        self.assertEqual(report["release_gate_summary"]["blocking_count"], 3)
        self.assertIn("a2_regression_replay_report.json", report["release_gate_summary"]["evidence_refs"][0])
        self.assertEqual(report["replay_case_count"], 1)
        replay = report["cases"][0]
        self.assertEqual(replay["case_id"], "sample-a2-s010-wrong-arguments")
        self.assertEqual(replay["replay_status"], "passed")
        self.assertEqual(replay["observed_local_failure_class"], "wrong_arguments")
        self.assertEqual(replay["expected_llm_failure_class"], "ignored_tool_result")
        self.assertTrue(all(replay["checks"].values()))

    def test_incident_summary_builds_public_safe_regression_candidate(self):
        report = build_incident_regression_candidate_report(
            ROOT / "fixtures/a2/incidents/a2_prod_incident_summary.json",
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        expected_report = json.loads(
            (ROOT / "fixtures/a2/results/a2_incident_regression_candidates.json").read_text(encoding="utf-8")
        )
        report_text = json.dumps(report)

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.incident_regression_candidates.v1")
        self.assertTrue(report["ready_for_case_book_review"])
        self.assertTrue(report["public_safety"]["safe"])
        self.assertEqual(report["public_safety"]["private_field_names"], [])
        self.assertEqual(report["public_safety"]["forbidden_pattern_names"], [])
        self.assertEqual(report["candidate_count"], 1)
        candidate = report["candidates"][0]
        self.assertEqual(candidate["case_id"], "sample-a2-s041-poor-retry-recovery")
        self.assertEqual(candidate["scenario_id"], "A2-S041")
        self.assertEqual(candidate["status"], "candidate")
        self.assertTrue(candidate["public_safe"])
        self.assertTrue(candidate["ready_for_case_book_review"])
        self.assertTrue(candidate["case_book_candidate"])
        self.assertEqual(candidate["expected"]["primary_failure_class"], "poor_failure_recovery")
        self.assertEqual(candidate["local_judge"]["primary_failure_class"], "poor_failure_recovery")
        self.assertIn("needs_reviewed_ashr_or_audited_semantic_evidence", candidate["promotion_blockers"])
        self.assertNotIn("Bearer ", report_text)
        self.assertNotRegex(report_text, re.compile(r"\b(?:sk-[A-Za-z0-9]{8,}|tp_[A-Za-z0-9_\-]{8,})\b"))
        self.assertNotRegex(report_text, re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"))

    def test_regression_promotion_queue_tracks_incident_candidate_to_c5(self):
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
        incident_candidates = build_incident_regression_candidate_report(
            ROOT / "fixtures/a2/incidents/a2_prod_incident_summary.json",
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        report = build_regression_promotion_queue_report(case_book, incident_candidates, regression_replay)
        expected_report = json.loads(
            (ROOT / "fixtures/a2/results/a2_regression_promotion_queue.json").read_text(encoding="utf-8")
        )
        report_text = json.dumps(report)

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.regression_promotion_queue.v1")
        self.assertEqual(report["queue_status"], "candidate_review_required")
        self.assertEqual(report["promotion_candidate_count"], 1)
        self.assertEqual(report["ready_for_owner_review_count"], 1)
        self.assertEqual(report["evidence_blocked_count"], 1)
        self.assertEqual(report["missing_replay_case_count"], 2)
        self.assertTrue(report["release_gate_summary"]["blocks_release"])
        self.assertEqual(report["release_gate_summary"]["candidate_supply_status"], "has_candidates")
        self.assertIn("Review queued incident candidates", report["release_gate_summary"]["required_action"])
        item = report["promotion_items"][0]
        self.assertEqual(item["case_id"], "sample-a2-s041-poor-retry-recovery")
        self.assertEqual(item["queue_status"], "ready_for_owner_review")
        self.assertTrue(item["can_promote_to_case_book"])
        self.assertFalse(item["can_promote_to_mature_replay"])
        self.assertIn("A2 evidence reviewer", item["required_reviews"])
        self.assertIn("audited_semantic_judge", item["required_evidence_sources"])
        self.assertNotIn("Bearer ", report_text)
        self.assertNotRegex(report_text, re.compile(r"\b(?:sk-[A-Za-z0-9]{8,}|tp_[A-Za-z0-9_\-]{8,})\b"))

    def test_release_unblock_checklist_tracks_c3_c4_c5_owner_actions(self):
        release_gate = json.loads((ROOT / "fixtures/a2/results/a2_release_gate_report.json").read_text(encoding="utf-8"))
        evidence_readiness = json.loads(
            (ROOT / "fixtures/a2/results/a2_evidence_readiness_report.json").read_text(encoding="utf-8")
        )
        regression_replay = json.loads(
            (ROOT / "fixtures/a2/results/a2_regression_replay_report.json").read_text(encoding="utf-8")
        )
        promotion_queue = json.loads(
            (ROOT / "fixtures/a2/results/a2_regression_promotion_queue.json").read_text(encoding="utf-8")
        )
        report = build_release_unblock_checklist(
            release_gate,
            evidence_readiness,
            regression_replay,
            promotion_queue,
        )
        expected_report = json.loads(
            (ROOT / "fixtures/a2/results/a2_release_unblock_checklist.json").read_text(encoding="utf-8")
        )
        report_text = json.dumps(report)

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.release_unblock_checklist.v1")
        self.assertEqual(report["overall_status"], "blocked")
        self.assertEqual(report["blocked_gate_count"], 3)
        self.assertTrue(report["metadata"]["public_safe"])
        self.assertTrue(report["metadata"]["does_not_execute_live_calls"])
        gates = {item["gate"]: item for item in report["gate_items"]}
        self.assertEqual(set(gates), {"C3", "C4", "C5"})
        self.assertEqual(gates["C3"]["owner_role"], "A2 evidence reviewer")
        self.assertEqual(gates["C3"]["required_actions"][0]["required_evidence_source"], "reviewed_ashr_grading")
        self.assertEqual(gates["C4"]["owner_role"], "A2 semantic judge reviewer")
        self.assertEqual(gates["C4"]["required_actions"][0]["required_evidence_source"], "audited_semantic_judge")
        self.assertEqual(gates["C5"]["owner_role"], "A2 case-book owner")
        self.assertEqual(gates["C5"]["required_actions"][0]["required_evidence_source"], "reviewed_regression_replay")
        self.assertEqual(
            report["a3_consumption_summary"]["evidence_refs"],
            ["fixtures/a2/results/a2_release_unblock_checklist.json"],
        )
        self.assertNotIn("Bearer ", report_text)
        self.assertNotRegex(report_text, re.compile(r"\b(?:sk-[A-Za-z0-9]{8,}|tp_[A-Za-z0-9_\-]{8,})\b"))
        self.assertNotRegex(report_text, re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"))

    def test_c5_maturity_requires_reviewed_external_evidence(self):
        def matrix_with_three_disagreements(*, reviewed: bool) -> dict:
            matrix = build_calibration_matrix(
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                run_dir=ROOT / "fixtures/a2/runs",
                observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
            )
            matrix = json.loads(json.dumps(matrix))
            target_case_ids = [
                "sample-a2-s010-wrong-arguments",
                "sample-a2-s041-poor-retry-recovery",
                "sample-a2-s054-missing-clarification",
            ]
            for case in matrix["cases"]:
                if case["case_id"] not in target_case_ids:
                    continue
                local = case["sources"]["local_judge"]
                llm = case["sources"]["llm_judge"]
                llm_failure = (
                    "ignored_tool_result"
                    if local["primary_failure_class"] != "ignored_tool_result"
                    else "wrong_arguments"
                )
                llm.update(
                    {
                        "available": True,
                        "status": "available",
                        "source": "llm_judge",
                        "provider": "reviewed_model_call_sample" if reviewed else "offline_reference",
                        "model": "llm-judge-reviewed-v1" if reviewed else "llm-judge-reference-v0",
                        "passed": local["passed"],
                        "primary_failure_class": llm_failure,
                        "score": max(0, int(local["score"]) - 20),
                        "confidence": 0.91,
                        "rationale": "Synthetic disagreement used only to test C5 maturity gating.",
                        "evidence_ref": "docs/evidence/private_refs/a2_semantic_judge_review.redacted.json"
                        if reviewed
                        else case["fixture_ref"],
                    }
                )
                case["calibration_tags"] = list(
                    dict.fromkeys([*case.get("calibration_tags", []), "judge_disagreement_regression"])
                )
                case["diffs"] = [
                    diff
                    for diff in case.get("diffs", [])
                    if not (diff.get("left") == "local_judge" and diff.get("right") == "llm_judge")
                ]
                case["diffs"].append(
                    {
                        "left": "local_judge",
                        "right": "llm_judge",
                        "comparable": True,
                        "passed_match": True,
                        "failure_class_match": False,
                        "score_delta": abs(int(local["score"]) - int(llm["score"])),
                        "status": "mismatch",
                    }
                )
            matrix["agreement_summary"]["local_vs_llm_judge"]["mismatch_count"] = len(target_case_ids)
            matrix["agreement_summary"]["local_vs_llm_judge"]["mismatches"] = [
                {"case_id": case_id, "left_failure_class": "local", "right_failure_class": "llm"}
                for case_id in target_case_ids
            ]
            return matrix

        offline_matrix = matrix_with_three_disagreements(reviewed=False)
        offline_case_book = build_case_book_report(offline_matrix)
        offline_replay = build_regression_replay_report(
            offline_matrix,
            offline_case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        self.assertEqual(offline_case_book["regression_case_count"], 3)
        self.assertEqual(offline_case_book["maturity_gate"]["status"], "seed")
        self.assertFalse(offline_case_book["maturity_gate"]["ready"])
        self.assertEqual(offline_case_book["maturity_gate"]["reviewed_external_evidence_count"], 0)
        self.assertEqual(offline_replay["replay_case_count"], 3)
        self.assertTrue(offline_replay["replay_ready"])
        self.assertEqual(offline_replay["maturity_status"], "seed")
        self.assertFalse(offline_replay["maturity_gate"]["case_book_maturity_ready"])
        self.assertEqual(offline_replay["release_gate_summary"]["action"], "attach_reviewed_evidence")
        self.assertEqual(offline_replay["release_gate_summary"]["blocking_count"], 3)

        reviewed_matrix = matrix_with_three_disagreements(reviewed=True)
        reviewed_case_book = build_case_book_report(reviewed_matrix)
        reviewed_replay = build_regression_replay_report(
            reviewed_matrix,
            reviewed_case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        coverage_report = build_coverage_report(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        commercial = build_commercial_readiness_report(
            coverage_report,
            reviewed_matrix,
            case_book_report=reviewed_case_book,
            regression_replay_report=reviewed_replay,
        )
        self.assertEqual(reviewed_case_book["regression_case_count"], 3)
        self.assertEqual(reviewed_case_book["maturity_gate"]["status"], "mature")
        self.assertTrue(reviewed_case_book["maturity_gate"]["ready"])
        self.assertEqual(reviewed_case_book["maturity_gate"]["reviewed_external_evidence_count"], 3)
        self.assertEqual(reviewed_case_book["maturity_gate"]["gaps"], [])
        self.assertEqual(reviewed_replay["maturity_status"], "mature")
        self.assertTrue(reviewed_replay["maturity_gate"]["case_book_maturity_ready"])
        self.assertEqual(reviewed_replay["maturity_gate"]["gaps"], [])
        self.assertEqual(reviewed_replay["release_gate_summary"]["action"], "ready")
        self.assertFalse(reviewed_replay["release_gate_summary"]["blocks_release"])
        gates = {gate["gate"]: gate for gate in commercial["gate_status"]}
        self.assertEqual(gates["C5"]["status"], "met")

    def test_sdk_parity_report_tracks_python_and_typescript_runner_contracts(self):
        report = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_sdk_parity_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.sdk_parity.v1")
        self.assertTrue(report["parity_passed"])
        self.assertEqual(report["required_languages"], ["python", "typescript"])
        self.assertEqual(set(report["passed_languages"]), {"python", "typescript"})
        self.assertEqual({case["language"] for case in report["cases"]}, {"python", "typescript"})
        official_chains = {chain["language"]: chain for chain in report["official_sdk_chains"]}
        self.assertEqual(set(official_chains), {"python", "typescript"})
        self.assertEqual(official_chains["python"]["a2_consumed_shape"], "AgentTurn or AgentResult.to_dict()")
        self.assertEqual(official_chains["typescript"]["install"], "npm install ashr-labs")
        self.assertIn("runAndDeploy", official_chains["typescript"]["run_and_deploy_entrypoint"])
        self.assertEqual(official_chains["typescript"]["a2_consumed_shape"], "CaseResult.agent_output")
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
        self.assertIn("fixtures/a2/calibration/a2_semantic_judge_collection_packet.json", semantic_batch["evidence_refs"])
        ashr_batch = next(batch for batch in report["batches"] if batch["batch_id"] == "ashr_grading_tiny_calibration")
        self.assertIn("fixtures/a2/calibration/a2_ashr_grading_collection_packet.json", ashr_batch["evidence_refs"])
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
        self.assertEqual(report["reviewed_live_observation_count"], 0)
        self.assertEqual(report["missing_reviewed_live_observation_count"], 6)
        self.assertEqual(report["reviewed_live_sdk_languages"], [])
        self.assertIn("prompt_hash", report["reviewed_live_required_metadata_fields"])
        self.assertIn("Import 6 more", report["reviewed_live_evidence_gaps"][0])
        self.assertEqual(report["status"], "offline_reference_only")
        self.assertEqual(report["case_count"], 6)
        self.assertEqual(report["source_matrix"]["required_languages"], ["python", "typescript"])
        self.assertEqual(set(report["source_matrix"]["covered_languages"]), {"python", "typescript"})
        self.assertTrue(report["readiness_checks"]["covers_python_and_typescript"])
        self.assertTrue(report["readiness_checks"]["has_official_sdk_chain_map"])
        self.assertTrue(report["readiness_checks"]["has_false_positive_tracking"])
        self.assertFalse(report["readiness_checks"]["live_model_evidence_available"])
        risk = report["risk_assessment"]
        self.assertEqual(risk["status"], "offline_reference_risk_register")
        self.assertTrue(risk["tracking_ready"])
        self.assertEqual(risk["false_positive_candidate_count"], 0)
        self.assertEqual(risk["false_negative_candidate_count"], 0)
        self.assertEqual(risk["failure_class_drift_candidate_count"], 1)
        self.assertEqual(risk["score_delta_review_count"], 4)
        self.assertEqual(risk["low_confidence_reference_count"], 1)
        self.assertEqual(risk["risk_case_count"], 4)
        official_chains = {chain["language"]: chain for chain in report["source_matrix"]["official_sdk_chains"]}
        self.assertEqual(official_chains["typescript"]["a2_consumed_shape"], "CaseResult.agent_output")
        self.assertIn("runAndDeploy", official_chains["typescript"]["run_and_deploy_entrypoint"])
        self.assertIn("prompt_tokens", report["cost_policy"]["required_fields"])
        self.assertIn("tp_* API keys", report["redaction_policy"]["secret_patterns"])
        self.assertIn("primary_failure_class", report["output_schema"]["required_fields"])
        self.assertIn("wrong_arguments", report["output_schema"]["failure_class_enum"])
        media_case = next(case for case in report["cases"] if case["case_id"] == "sample-a2-s031-media-pipeline-unsupported-output")
        self.assertIn("media", media_case["calibration_focus"])
        self.assertIn("typescript", media_case["sdk_input_paths"])
        wrong_args_case = next(case for case in report["cases"] if case["case_id"] == "sample-a2-s010-wrong-arguments")
        self.assertIn("failure_class_drift_candidate", wrong_args_case["risk_flags"])
        self.assertIn("low_confidence_reference", wrong_args_case["risk_flags"])

    def test_evidence_readiness_report_tracks_c3_c4_private_evidence_requirements(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        coverage_report = build_coverage_report(ROOT / "packages/scenarios/a2_g3_full_pack.json")
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
        report = build_evidence_readiness_report(calibration_matrix, batch_plan, semantic_harness)
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_evidence_readiness_report.json").read_text(encoding="utf-8"))

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.evidence_readiness.v1")
        self.assertEqual(report["status"], "awaiting_private_evidence")
        self.assertTrue(report["ready_for_external_collection"])
        self.assertEqual(report["calibration_case_count"], 6)
        self.assertTrue(report["readiness_checks"]["ashr_case_map_covers_cases"])
        self.assertTrue(report["readiness_checks"]["semantic_harness_ready"])
        self.assertTrue(report["readiness_checks"]["semantic_false_positive_tracking_ready"])
        self.assertEqual(report["ashr_grading_preflight"]["current_missing"], 6)
        self.assertEqual(report["ashr_grading_preflight"]["expected_observation_count"], 6)
        self.assertEqual(report["ashr_grading_preflight"]["expected_reviewed_observation_count"], 6)
        self.assertIn("metadata.review_status", report["ashr_grading_preflight"]["required_review_fields"])
        self.assertIn("a2_scan_ashr_grading_evidence.py", report["ashr_grading_preflight"]["commands"][0])
        self.assertIn("--review-status reviewed", " ".join(report["ashr_grading_preflight"]["commands"]))
        self.assertEqual(report["ashr_grading_preflight"]["case_map_missing_case_ids"], [])
        self.assertTrue(report["a1_real_api_evidence"]["available"])
        self.assertIn("init", report["a1_real_api_evidence"]["real_ok_functions"])
        self.assertIn("list_datasets", report["a1_real_api_evidence"]["real_ok_functions"])
        self.assertGreaterEqual(report["a1_real_api_evidence"]["real_record_count"], 60)
        self.assertGreaterEqual(report["a1_real_api_evidence"]["real_read_status_counts"]["ok"], 40)
        self.assertGreaterEqual(
            report["a1_real_api_evidence"]["real_create_request_status_counts"]["error"],
            1,
        )
        self.assertIn("api", report["a1_real_api_evidence"]["real_create_request_error_kind_counts"])
        quota_gate = report["a1_real_api_evidence"]["real_quota_gate"]
        self.assertTrue(quota_gate["blocked"])
        self.assertGreaterEqual(quota_gate["blocked_count"], 1)
        self.assertTrue(quota_gate["create_request_blocked"])
        self.assertIn("create_request", quota_gate["blocked_functions"])
        self.assertIn("limit", quota_gate["quota_keys"])
        self.assertIn("remaining", quota_gate["quota_keys"])
        self.assertIn("request quota", quota_gate["public_action"])
        gate_validation = report["a1_real_api_evidence"]["api_probe_gate_validation"]
        self.assertTrue(gate_validation["available"])
        self.assertGreaterEqual(gate_validation["plan_batch_count"], 3)
        self.assertGreaterEqual(gate_validation["validate_gate_count"], 3)
        self.assertGreaterEqual(gate_validation["ok_validate_gate_count"], 1)
        self.assertGreaterEqual(gate_validation["error_validate_gate_count"], 1)
        self.assertIn(gate_validation["release_interpretation"], {
            "mixed_gate_evidence_review_required",
            "gate_validation_or_plan_blocked",
        })
        self.assertFalse(report["a1_real_api_evidence"]["c3_grading_ready"])
        self.assertIn(
            "docs/a1/api_calibration/real_api_evidence_index.json",
            report["a1_real_api_evidence"]["index_path"],
        )
        official_manifest = report["a1_official_api_readonly_manifest"]
        self.assertTrue(official_manifest["available"])
        self.assertEqual(
            official_manifest["path"],
            "docs/a1/evidence/official_api_readonly_manifest_summary.json",
        )
        self.assertTrue(official_manifest["public_safe"])
        self.assertTrue(official_manifest["ready_for_a2_evidence_context"])
        self.assertEqual(official_manifest["read_step_count"], 5)
        self.assertFalse(official_manifest["raw_payload_values_included"])
        mutating_index = report["a1_official_api_mutating_index"]
        self.assertTrue(mutating_index["available"])
        self.assertEqual(
            mutating_index["path"],
            "docs/a1/evidence/official_api_mutating_calibration_index.json",
        )
        self.assertTrue(mutating_index["public_safe"])
        self.assertTrue(mutating_index["ready_for_a2_evidence_context"])
        self.assertEqual(mutating_index["mutating_step_count"], 5)
        self.assertEqual(mutating_index["quota_block_count"], 7)
        self.assertFalse(mutating_index["c3_grading_ready"])
        paid_media_summary = report["a1_official_api_paid_media_summary"]
        self.assertTrue(paid_media_summary["available"])
        self.assertEqual(
            paid_media_summary["path"],
            "docs/a1/evidence/official_api_paid_media_summary_20260709_185014.json",
        )
        self.assertTrue(paid_media_summary["public_safe"])
        self.assertTrue(paid_media_summary["ready_for_a2_evidence_context"])
        self.assertFalse(paid_media_summary["safe_for_paid_media_claims"])
        self.assertFalse(paid_media_summary["c3_grading_ready"])
        self.assertTrue(paid_media_summary["guardrails"]["paid_media_requires_allow_paid_media"])
        payment_provider = report["a1_payment_provider_readiness"]
        self.assertTrue(payment_provider["available"])
        self.assertEqual(
            payment_provider["path"],
            "docs/a1/evidence/payment_provider_readiness_public.json",
        )
        self.assertTrue(payment_provider["ready_for_a2_payment_policy_context"])
        self.assertTrue(payment_provider["public_safe"])
        self.assertEqual(payment_provider["provider_count"], 3)
        self.assertFalse(payment_provider["ci_payment_calls_allowed"])
        self.assertFalse(payment_provider["c3_grading_ready"])
        self.assertTrue(
            payment_provider["a2_policy_implications"]["must_not_mark_c3_from_payment_context"]
        )
        billing_replay = report["a1_billing_replay_evidence"]
        self.assertTrue(billing_replay["available"])
        self.assertEqual(
            billing_replay["path"],
            "docs/a1/evidence/billing_replay_fixture_round35.json",
        )
        self.assertTrue(billing_replay["public_safe"])
        self.assertTrue(billing_replay["ready_for_a2_evidence_context"])
        self.assertTrue(billing_replay["duplicate_idempotency_proven"])
        self.assertFalse(billing_replay["c3_grading_ready"])
        self.assertTrue(
            billing_replay["a2_policy_implications"]["must_not_mark_c3_from_billing_context"]
        )
        billing_migration = report["a1_billing_ledger_migration"]
        self.assertTrue(billing_migration["available"])
        self.assertEqual(
            billing_migration["path"],
            "docs/a1/schemas/a1_billing_ledger_migration_manifest.json",
        )
        self.assertTrue(billing_migration["tenant_rls_ready"])
        self.assertTrue(billing_migration["public_safe"])
        self.assertTrue(billing_migration["ready_for_a2_evidence_context"])
        self.assertFalse(billing_migration["c3_grading_ready"])
        self.assertTrue(
            billing_migration["a2_policy_implications"]["must_not_mark_c3_from_billing_context"]
        )
        billing_sql = report["a1_billing_sql_semantic_contract"]
        self.assertTrue(billing_sql["available"])
        self.assertEqual(
            billing_sql["path"],
            "docs/a1/evidence/billing_sql_semantic_contract.json",
        )
        self.assertTrue(billing_sql["ready_for_a2_sql_policy_context"])
        self.assertTrue(billing_sql["public_safe"])
        self.assertEqual(billing_sql["raw_payload_column_present_count"], 0)
        self.assertFalse(billing_sql["c3_grading_ready"])
        self.assertTrue(
            billing_sql["a2_policy_implications"]["must_not_mark_c3_from_sql_context"]
        )
        self.assertTrue(report["readiness_checks"]["official_sdk_smoke_readonly_ok"])
        self.assertTrue(report["official_sdk_smoke"]["available"])
        self.assertTrue(report["official_sdk_smoke"]["read_only_reachable"])
        self.assertEqual(report["official_sdk_smoke"]["ok_call_count"], 6)
        self.assertEqual(report["official_sdk_smoke"]["error_call_count"], 0)
        self.assertIn("init", report["official_sdk_smoke"]["call_names"])
        self.assertIn("list_datasets", report["official_sdk_smoke"]["call_names"])
        self.assertIn("list_requests", report["official_sdk_smoke"]["call_names"])
        self.assertIn("list_agents", report["official_sdk_smoke"]["call_names"])
        self.assertEqual(report["ashr_public_merge_gate"]["status"], "not_merged")
        self.assertFalse(report["ashr_public_merge_gate"]["public_matrix_merged"])
        self.assertFalse(report["ashr_public_merge_gate"]["safe_to_mark_c3_met"])
        self.assertEqual(report["ashr_public_merge_gate"]["merged_public_observation_count"], 0)
        self.assertEqual(report["ashr_public_merge_gate"]["reviewed_public_observation_count"], 0)
        self.assertEqual(report["ashr_public_merge_gate"]["missing_public_observation_count"], 6)
        self.assertEqual(report["ashr_public_merge_gate"]["missing_reviewed_observation_count"], 6)
        self.assertIn("evidence_ref", report["ashr_public_merge_gate"]["required_review_fields"])
        self.assertIn("a2_ashr_grading_import.review.json", report["ashr_public_merge_gate"]["reviewed_private_import_ref"])
        self.assertIn("before C3 is met", report["ashr_public_merge_gate"]["blocking_reason"])
        self.assertTrue(report["semantic_judge_preflight"]["offline_reference_only"])
        self.assertEqual(report["semantic_judge_preflight"]["expected_reviewed_observation_count"], 6)
        self.assertEqual(report["semantic_judge_preflight"]["reviewed_live_observation_count"], 0)
        self.assertEqual(report["semantic_judge_preflight"]["missing_reviewed_live_observation_count"], 6)
        self.assertEqual(report["semantic_judge_preflight"]["reviewed_live_sdk_languages"], [])
        self.assertIn("response_hash", report["semantic_judge_preflight"]["reviewed_live_required_metadata_fields"])
        self.assertEqual(report["semantic_judge_preflight"]["risk_assessment_status"], "offline_reference_risk_register")
        self.assertTrue(report["semantic_judge_preflight"]["false_positive_tracking_ready"])
        self.assertEqual(report["semantic_judge_preflight"]["false_positive_candidate_count"], 0)
        self.assertEqual(report["semantic_judge_preflight"]["false_negative_candidate_count"], 0)
        self.assertEqual(report["semantic_judge_preflight"]["failure_class_drift_candidate_count"], 1)
        self.assertEqual(report["semantic_judge_preflight"]["score_delta_review_count"], 4)
        self.assertEqual(report["semantic_judge_preflight"]["risk_case_count"], 4)
        self.assertEqual(report["semantic_live_merge_gate"]["status"], "offline_reference_only")
        self.assertFalse(report["semantic_live_merge_gate"]["audited_live_evidence_merged"])
        self.assertFalse(report["semantic_live_merge_gate"]["safe_to_mark_c4_met"])
        self.assertEqual(report["semantic_live_merge_gate"]["current_public_observation_count"], 6)
        self.assertEqual(report["semantic_live_merge_gate"]["audited_public_observation_count"], 0)
        self.assertEqual(report["semantic_live_merge_gate"]["reviewed_live_observation_count"], 0)
        self.assertEqual(report["semantic_live_merge_gate"]["missing_audited_observation_count"], 6)
        self.assertIn("before C4 is met", report["semantic_live_merge_gate"]["blocking_reason"])
        self.assertIn("prompt_hash", report["semantic_judge_preflight"]["required_fields"])
        self.assertIn("typescript", report["semantic_judge_preflight"]["covered_sdk_languages"])
        self.assertIn("ashr_grading_tiny_calibration", report["batch_plan_refs"])
        self.assertIn("semantic_llm_judge_audit", report["batch_plan_refs"])
        self.assertIn("raw prompts", report["redaction_policy"]["never_commit"])

    def test_evidence_readiness_consumes_a1_official_api_readonly_manifest_summary(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        summary = {
            "schema_version": "ashr.clone.public_official_api_manifest_summary.v1",
            "status": "ok",
            "source_private_manifest_present": True,
            "summary": {
                "read_steps": 5,
                "ok_or_planned_steps": 5,
                "error_steps": 0,
                "quota_block_count": 0,
                "modalities": ["text"],
            },
            "step_summaries": [
                {"step_id": "init"},
                {"step_id": "list_datasets"},
                {"step_id": "list_runs"},
            ],
            "public_safety": {
                "raw_key_material_present": False,
                "header_values_included": False,
                "raw_payload_values_included": False,
                "private_payload_contents_present": False,
                "request_parameter_values_included": False,
                "step_record_locations_included": False,
                "redacted_summary_fields_only": True,
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            summary_path = Path(tmp_dir) / "official_api_readonly_manifest_summary.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            report = build_evidence_readiness_report(
                calibration_matrix,
                {},
                semantic_harness,
                a1_official_api_readonly_manifest_path=summary_path,
            )

        official_manifest = report["a1_official_api_readonly_manifest"]
        self.assertTrue(official_manifest["available"])
        self.assertTrue(official_manifest["public_safe"])
        self.assertTrue(official_manifest["ready_for_a2_evidence_context"])
        self.assertEqual(official_manifest["read_step_count"], 5)
        self.assertEqual(official_manifest["step_ids"], ["init", "list_datasets", "list_runs"])
        self.assertFalse(official_manifest["raw_payload_values_included"])

    def test_evidence_readiness_consumes_a1_official_api_mutating_index_summary(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        summary = {
            "schema_version": "ashr.clone.official_api_mutating_calibration_index.v1",
            "public_safe": True,
            "raw_payloads_included": False,
            "secret_values_included": False,
            "records": [
                {
                    "mutating_step_ids": ["create-request-text"],
                    "observed_error_kinds": ["api"],
                    "private_manifest": "docs/evidence/private_refs/a1_official_api_mutating_text.redacted.json",
                    "quota_block_count": 1,
                    "raw_payloads_included": False,
                    "read_steps": 5,
                    "status": "partial",
                    "summary_modalities": ["text"],
                    "total_steps": 6,
                },
                {
                    "mutating_step_ids": ["create-request-image"],
                    "observed_error_kinds": ["quota"],
                    "private_manifest": "docs/evidence/private_refs/a1_official_api_mutating_image.redacted.json",
                    "quota_block_count": 1,
                    "raw_payloads_included": False,
                    "read_steps": 5,
                    "status": "partial",
                    "summary_modalities": ["image"],
                    "total_steps": 6,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            summary_path = Path(tmp_dir) / "official_api_mutating_calibration_index.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            report = build_evidence_readiness_report(
                calibration_matrix,
                {},
                semantic_harness,
                a1_official_api_mutating_index_path=summary_path,
            )

        mutating_index = report["a1_official_api_mutating_index"]
        self.assertTrue(mutating_index["available"])
        self.assertTrue(mutating_index["public_safe"])
        self.assertTrue(mutating_index["ready_for_a2_evidence_context"])
        self.assertFalse(mutating_index["raw_payloads_included"])
        self.assertFalse(mutating_index["secret_values_included"])
        self.assertFalse(mutating_index["c3_grading_ready"])
        self.assertEqual(mutating_index["record_count"], 2)
        self.assertEqual(mutating_index["mutating_step_count"], 2)
        self.assertEqual(mutating_index["quota_block_count"], 2)
        self.assertEqual(mutating_index["read_step_count"], 10)
        self.assertEqual(mutating_index["total_steps"], 12)
        self.assertEqual(mutating_index["modalities"], ["image", "text"])
        self.assertEqual(mutating_index["mutating_step_ids"], ["create-request-image", "create-request-text"])
        self.assertEqual(mutating_index["observed_error_kinds"], ["api", "quota"])
        self.assertEqual(mutating_index["status_counts"], {"partial": 2})

    def test_evidence_readiness_consumes_a1_paid_media_manifest_summary(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        summary = {
            "schema_version": "ashr.clone.public_official_api_manifest_summary.v1",
            "status": "partial",
            "mode": "small-batch",
            "source_private_manifest_present": True,
            "guardrails": {
                "execute_requires_small_batch": True,
                "mutating_execute_requires_quota_gate": True,
                "mutating_requires_include_mutating": True,
                "paid_media_requires_allow_paid_media": True,
                "quota_gate_present": True,
                "raw_records_private": True,
                "output_policy": {
                    "full_record_stdout_blocked": True,
                    "output_is_private": True,
                    "private_output_required": True,
                },
            },
            "public_safety": {
                "raw_key_material_present": False,
                "header_values_included": False,
                "raw_payload_values_included": False,
                "private_payload_contents_present": False,
                "request_parameter_values_included": False,
                "step_record_locations_included": False,
                "redacted_summary_fields_only": True,
            },
            "summary": {
                "read_steps": 5,
                "mutating_steps": 1,
                "ok_or_planned_steps": 5,
                "error_steps": 1,
                "quota_block_count": 1,
                "estimated_calls": 17,
                "modalities": ["text"],
                "total_steps": 6,
            },
            "step_summaries": [
                {
                    "step_id": "init",
                    "function": "init",
                    "kind": "read",
                    "status": "ok",
                    "status_code": 200,
                    "quota_blocked": False,
                },
                {
                    "step_id": "list-requests",
                    "function": "list_requests",
                    "kind": "read",
                    "status": "ok",
                    "status_code": 200,
                    "quota_blocked": False,
                },
                {
                    "step_id": "create-request-text",
                    "function": "create_request",
                    "kind": "mutate",
                    "modality": "text",
                    "status": "error",
                    "status_code": 200,
                    "quota_blocked": True,
                    "quota_remaining_present": True,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            summary_path = Path(tmp_dir) / "official_api_paid_media_summary_20260709_185014.json"
            summary_path.write_text(json.dumps(summary), encoding="utf-8")
            report = build_evidence_readiness_report(
                calibration_matrix,
                {},
                semantic_harness,
                a1_official_api_paid_media_summary_path=summary_path,
            )

        paid_media = report["a1_official_api_paid_media_summary"]
        self.assertTrue(paid_media["available"])
        self.assertTrue(paid_media["public_safe"])
        self.assertTrue(paid_media["redacted_summary_fields_only"])
        self.assertFalse(paid_media["raw_payload_values_included"])
        self.assertTrue(paid_media["ready_for_a2_evidence_context"])
        self.assertFalse(paid_media["safe_for_paid_media_claims"])
        self.assertFalse(paid_media["c3_grading_ready"])
        self.assertEqual(paid_media["status"], "partial")
        self.assertEqual(paid_media["mode"], "small-batch")
        self.assertEqual(paid_media["estimated_call_count"], 17)
        self.assertEqual(paid_media["quota_block_count"], 1)
        self.assertEqual(paid_media["mutating_step_count"], 1)
        self.assertEqual(paid_media["mutating_functions"], ["create_request"])
        self.assertEqual(paid_media["mutating_modalities"], ["text"])
        self.assertEqual(paid_media["quota_blocked_step_ids"], ["create-request-text"])
        self.assertTrue(paid_media["quota_remaining_observed"])
        self.assertEqual(paid_media["status_code_counts"], {"200": 3})
        self.assertTrue(paid_media["guardrails"]["paid_media_requires_allow_paid_media"])
        self.assertTrue(paid_media["guardrails"]["mutating_execute_requires_quota_gate"])
        self.assertTrue(paid_media["guardrails"]["full_record_stdout_blocked"])

    def test_evidence_readiness_consumes_a1_payment_provider_readiness(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        packet = {
            "schema_version": "ashr.clone.a1.payment_provider_readiness.v1",
            "owner": "A1 Worker-PaymentDocsEvidence",
            "public_safe": True,
            "payment_call_policy": {
                "provider_called": False,
                "checkout_or_portal_called": False,
                "real_charge_possible": False,
                "ci_payment_calls_allowed": False,
            },
            "provider_secret_policy": {
                "raw_secret_values_allowed": False,
                "secret_reference_prefixes": ["env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:"],
                "forbidden_material": [
                    "Stripe secret keys",
                    "WeChat merchant private keys",
                    "Alipay app private keys",
                    "card PAN or CVC",
                ],
            },
            "providers": [
                {
                    "provider": "stripe",
                    "modes": ["test", "live"],
                    "hosted_surface": "Stripe-hosted Checkout and Billing Portal plans only",
                    "payment_methods": ["card", "alipay", "wechat_pay"],
                    "side_effects": {
                        "provider_called": False,
                        "checkout_or_portal_called": False,
                        "real_charge_possible": False,
                    },
                },
                {
                    "provider": "wechat_pay",
                    "modes": ["test", "live"],
                    "hosted_surface": "Hosted WeChat Pay provider handoff contract",
                    "payment_methods": ["wechat_pay"],
                    "side_effects": {
                        "provider_called": False,
                        "checkout_or_portal_called": False,
                        "real_charge_possible": False,
                    },
                },
                {
                    "provider": "alipay",
                    "modes": ["test", "live"],
                    "hosted_surface": "Hosted Alipay trade page/provider handoff contract",
                    "payment_methods": ["alipay"],
                    "side_effects": {
                        "provider_called": False,
                        "checkout_or_portal_called": False,
                        "real_charge_possible": False,
                    },
                },
            ],
            "human_real_card_testing": {
                "allowed": True,
                "automation_allowed": False,
                "stored_card_data_allowed": False,
            },
            "webhook_hash_envelopes": [
                {
                    "provider": "stripe",
                    "mode": "test",
                    "payload_sha256": "a" * 64,
                    "verified": True,
                    "raw_payload_included": False,
                    "secret_value_present": False,
                },
                {
                    "provider": "wechat_pay",
                    "mode": "test",
                    "payload_sha256": "b" * 64,
                    "verified": True,
                    "raw_payload_included": False,
                    "secret_value_present": False,
                },
                {
                    "provider": "alipay",
                    "mode": "test",
                    "payload_sha256": "c" * 64,
                    "verified": True,
                    "raw_payload_included": False,
                    "secret_value_present": False,
                },
            ],
            "object_evidence_paths": [
                {
                    "path": "docs/a1/payment_provider_readiness.md",
                    "classification": "public_contract",
                    "allowed_in_public_repo": True,
                },
                {
                    "path": "docs/a1/evidence/payment_provider_readiness_public.json",
                    "classification": "public_contract",
                    "allowed_in_public_repo": True,
                },
                {
                    "path": "docs/a1/schemas/payment_provider_readiness.schema.json",
                    "classification": "public_contract",
                    "allowed_in_public_repo": True,
                },
                {
                    "path": "docs/evidence/private_refs/payments/{provider}/{mode}/{object}.hash-envelope.json",
                    "classification": "private_ref",
                    "allowed_in_public_repo": False,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            packet_path = Path(tmp_dir) / "payment_provider_readiness_public.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            report = build_evidence_readiness_report(
                calibration_matrix,
                {},
                semantic_harness,
                a1_payment_provider_readiness_path=packet_path,
            )

        payment_provider = report["a1_payment_provider_readiness"]
        self.assertTrue(payment_provider["available"])
        self.assertEqual(payment_provider["schema_version"], "ashr.clone.a1.payment_provider_readiness.v1")
        self.assertTrue(payment_provider["public_safe"])
        self.assertEqual(payment_provider["provider_count"], 3)
        self.assertEqual(payment_provider["providers"], ["alipay", "stripe", "wechat_pay"])
        self.assertEqual(payment_provider["mode_count"], 2)
        self.assertEqual(payment_provider["modes"], ["live", "test"])
        self.assertEqual(payment_provider["hosted_surface_count"], 3)
        self.assertEqual(payment_provider["payment_methods"], ["alipay", "card", "wechat_pay"])
        self.assertFalse(payment_provider["provider_called"])
        self.assertFalse(payment_provider["checkout_or_portal_called"])
        self.assertFalse(payment_provider["real_charge_possible"])
        self.assertFalse(payment_provider["ci_payment_calls_allowed"])
        self.assertFalse(payment_provider["raw_secret_values_allowed"])
        self.assertIn("vault:", payment_provider["secret_reference_prefixes"])
        self.assertEqual(payment_provider["forbidden_material_count"], 4)
        self.assertEqual(payment_provider["webhook_hash_envelope_count"], 3)
        self.assertEqual(payment_provider["verified_webhook_hash_count"], 3)
        self.assertFalse(payment_provider["raw_payload_included"])
        self.assertFalse(payment_provider["secret_value_present"])
        self.assertTrue(payment_provider["human_real_card_testing_allowed"])
        self.assertFalse(payment_provider["human_real_card_automation_allowed"])
        self.assertFalse(payment_provider["stored_card_data_allowed"])
        self.assertEqual(payment_provider["public_evidence_path_count"], 3)
        self.assertEqual(payment_provider["private_ref_path_count"], 1)
        self.assertTrue(payment_provider["ready_for_a2_payment_policy_context"])
        self.assertFalse(payment_provider["c3_grading_ready"])
        self.assertTrue(payment_provider["a2_policy_implications"]["payment_provider_policy_context"])
        self.assertTrue(payment_provider["a2_policy_implications"]["can_support_payment_abuse_cases"])
        self.assertTrue(payment_provider["a2_policy_implications"]["live_payment_requires_human_operator"])
        self.assertTrue(
            payment_provider["a2_policy_implications"]["must_not_mark_c3_from_payment_context"]
        )

    def test_evidence_readiness_consumes_a1_billing_replay_fixture(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        fixture = {
            "schema_version": "ashr.clone.billing_replay_fixture.v1",
            "accepted_provider_event": {
                "schema_version": "ashr.clone.billing_provider_contract.v1",
                "tenant_id": "tenant_fixture",
                "project_id": "project_fixture",
                "provider": "stripe",
                "mode": "test",
                "event_id": "evt_fixture_invoice_paid",
                "event_type": "invoice.paid",
                "ingest_status": "accepted",
                "ledger_event_id": "ble_fixture_invoice_paid",
                "ledger_event_type": "invoice_paid",
                "ledger_mutation_count": 1,
                "raw_payload_included": False,
                "secret_value_present": False,
            },
            "duplicate_provider_event": {
                "schema_version": "ashr.clone.billing_provider_contract.v1",
                "tenant_id": "tenant_fixture",
                "project_id": "project_fixture",
                "provider": "stripe",
                "mode": "test",
                "event_id": "evt_fixture_invoice_paid",
                "event_type": "invoice.paid",
                "ingest_status": "duplicate",
                "ledger_event_id": "ble_fixture_invoice_paid",
                "ledger_event_type": "invoice_paid",
                "ledger_mutation_count": 0,
                "raw_payload_included": False,
                "secret_value_present": False,
            },
            "billing_evidence": {
                "schema_version": "ashr.clone.billing_evidence_snapshot.v1",
                "tenant_id": "tenant_fixture",
                "project_id": "project_fixture",
                "ledger_event_count": 2,
                "provider_event_count": 1,
                "usage_units": 14,
                "totals_by_currency_minor": {"usd": 12345},
                "billing_snapshot_sha256": "a" * 64,
                "raw_payload_included": False,
                "secret_value_present": False,
            },
            "public_ledger": {
                "schema_version": "ashr.clone.billing_provider_contract.v1",
                "tenant_id": "tenant_fixture",
                "project_id": "project_fixture",
                "provider": "stripe",
                "mode": "test",
                "ledger_event_count": 2,
                "provider_event_count": 1,
                "usage_units": 14,
                "totals_by_currency_minor": {"usd": 12345},
                "raw_payload_included": False,
                "secret_value_present": False,
                "billing_accounts": [
                    {
                        "tenant_id": "tenant_fixture",
                        "project_id": "project_fixture",
                        "provider": "stripe",
                        "mode": "test",
                        "raw_payload_included": False,
                        "raw_secret_present": False,
                    }
                ],
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            fixture_path = Path(tmp_dir) / "billing_replay_fixture_round35.json"
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            report = build_evidence_readiness_report(
                calibration_matrix,
                {},
                semantic_harness,
                a1_billing_replay_fixture_path=fixture_path,
            )

        billing_replay = report["a1_billing_replay_evidence"]
        self.assertTrue(billing_replay["available"])
        self.assertEqual(billing_replay["schema_version"], "ashr.clone.billing_replay_fixture.v1")
        self.assertEqual(
            billing_replay["billing_evidence_schema_version"],
            "ashr.clone.billing_evidence_snapshot.v1",
        )
        self.assertEqual(billing_replay["tenant_id"], "tenant_fixture")
        self.assertEqual(billing_replay["project_id"], "project_fixture")
        self.assertEqual(billing_replay["provider"], "stripe")
        self.assertEqual(billing_replay["mode"], "test")
        self.assertEqual(billing_replay["ledger_event_count"], 2)
        self.assertEqual(billing_replay["provider_event_count"], 1)
        self.assertEqual(billing_replay["usage_units"], 14)
        self.assertEqual(billing_replay["totals_by_currency_minor"], {"usd": 12345})
        self.assertEqual(billing_replay["totals_currencies"], ["usd"])
        self.assertTrue(billing_replay["billing_snapshot_sha256_present"])
        self.assertEqual(billing_replay["accepted_ingest_status"], "accepted")
        self.assertEqual(billing_replay["duplicate_ingest_status"], "duplicate")
        self.assertEqual(billing_replay["accepted_ledger_mutation_count"], 1)
        self.assertEqual(billing_replay["duplicate_ledger_mutation_count"], 0)
        self.assertTrue(billing_replay["duplicate_idempotency_proven"])
        self.assertFalse(billing_replay["raw_payload_included"])
        self.assertFalse(billing_replay["secret_value_present"])
        self.assertFalse(billing_replay["raw_secret_present"])
        self.assertTrue(billing_replay["public_safe"])
        self.assertTrue(billing_replay["ready_for_a2_evidence_context"])
        self.assertFalse(billing_replay["c3_grading_ready"])
        self.assertTrue(billing_replay["a2_policy_implications"]["billing_usage_policy_context"])
        self.assertTrue(billing_replay["a2_policy_implications"]["can_support_cost_policy_calibration"])
        self.assertTrue(billing_replay["a2_policy_implications"]["should_add_billing_abuse_cases"])
        self.assertTrue(
            billing_replay["a2_policy_implications"]["must_not_mark_c3_from_billing_context"]
        )

    def test_evidence_readiness_consumes_a1_billing_ledger_migration_manifest(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        manifest = {
            "schema_version": "ashr.clone.a1_billing_ledger_migration_manifest.v1",
            "version": 2,
            "migration": "services/api/migrations/002_a1_billing_ledger.sql",
            "tables": [
                {
                    "name": "billing_accounts",
                    "tenant_column": "organization_id",
                    "rls_policy": "billing_accounts_organization_isolation",
                    "required_columns": ["id", "organization_id", "project_id"],
                    "required_indexes": ["idx_billing_accounts_scope"],
                    "required_constraints": ["billing_accounts_no_raw_secret"],
                },
                {
                    "name": "billing_provider_events",
                    "tenant_column": "organization_id",
                    "rls_policy": "billing_provider_events_organization_isolation",
                    "required_columns": ["id", "organization_id", "project_id", "raw_payload_included"],
                    "required_indexes": ["idx_billing_provider_events_scope_created"],
                    "required_constraints": ["billing_provider_events_no_raw_secret"],
                },
                {
                    "name": "billing_ledger_events",
                    "tenant_column": "organization_id",
                    "rls_policy": "billing_ledger_events_organization_isolation",
                    "required_columns": ["id", "organization_id", "project_id", "usage_units"],
                    "required_indexes": ["idx_billing_ledger_events_scope_created"],
                    "required_constraints": ["billing_ledger_events_no_raw_secret"],
                },
            ],
            "provider_event_types": [
                "invoice.paid",
                "wechat_pay.transaction.success",
                "alipay.trade.success",
                "ashr.usage.reconciled",
            ],
            "ledger_event_types": ["invoice_paid", "usage_reconciled", "refund_created"],
            "providers": ["stripe", "wechat_pay", "alipay"],
            "modes": ["test", "live"],
            "currencies": ["usd", "cny"],
            "required_functions": {
                "normalize_billing_event_type": {"must_contain": ["invoice.paid"]},
                "ingest_billing_provider_event": {"must_contain": ["replay_status := 'duplicate'"]},
                "summarize_billing_ledger": {"must_contain": ["SUM(l.usage_units)"]},
            },
            "public_safety": {
                "raw_provider_payload_stored": False,
                "raw_provider_secret_stored": False,
                "raw_card_data_stored": False,
                "provider_calls_executed": False,
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            manifest_path = Path(tmp_dir) / "a1_billing_ledger_migration_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            report = build_evidence_readiness_report(
                calibration_matrix,
                {},
                semantic_harness,
                a1_billing_ledger_migration_manifest_path=manifest_path,
            )

        billing_migration = report["a1_billing_ledger_migration"]
        self.assertTrue(billing_migration["available"])
        self.assertEqual(
            billing_migration["schema_version"],
            "ashr.clone.a1_billing_ledger_migration_manifest.v1",
        )
        self.assertEqual(billing_migration["version"], 2)
        self.assertEqual(
            billing_migration["migration"],
            "services/api/migrations/002_a1_billing_ledger.sql",
        )
        self.assertEqual(billing_migration["table_count"], 3)
        self.assertEqual(
            billing_migration["table_names"],
            ["billing_accounts", "billing_ledger_events", "billing_provider_events"],
        )
        self.assertEqual(billing_migration["tenant_rls_table_count"], 3)
        self.assertTrue(billing_migration["tenant_rls_ready"])
        self.assertEqual(billing_migration["required_index_count"], 3)
        self.assertEqual(billing_migration["required_constraint_count"], 3)
        self.assertIn("billing_provider_events_no_raw_secret", billing_migration["constraint_names"])
        self.assertEqual(billing_migration["provider_event_type_count"], 4)
        self.assertEqual(billing_migration["ledger_event_type_count"], 3)
        self.assertEqual(billing_migration["providers"], ["alipay", "stripe", "wechat_pay"])
        self.assertEqual(billing_migration["modes"], ["live", "test"])
        self.assertEqual(billing_migration["currencies"], ["cny", "usd"])
        self.assertEqual(
            billing_migration["required_function_names"],
            ["ingest_billing_provider_event", "normalize_billing_event_type", "summarize_billing_ledger"],
        )
        self.assertTrue(billing_migration["public_safe"])
        self.assertFalse(billing_migration["raw_provider_payload_stored"])
        self.assertFalse(billing_migration["raw_provider_secret_stored"])
        self.assertFalse(billing_migration["raw_card_data_stored"])
        self.assertFalse(billing_migration["provider_calls_executed"])
        self.assertTrue(billing_migration["ready_for_a2_evidence_context"])
        self.assertFalse(billing_migration["c3_grading_ready"])
        self.assertTrue(billing_migration["a2_policy_implications"]["sql_billing_policy_context"])
        self.assertTrue(billing_migration["a2_policy_implications"]["can_support_billing_abuse_cases"])
        self.assertTrue(billing_migration["a2_policy_implications"]["can_cross_check_usage_rollups"])
        self.assertTrue(
            billing_migration["a2_policy_implications"]["must_not_mark_c3_from_billing_context"]
        )

    def test_evidence_readiness_consumes_a1_billing_sql_semantic_contract(self):
        calibration_matrix = build_calibration_matrix(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(calibration_matrix, sdk_parity)
        contract = {
            "schema_version": "ashr.clone.a1.billing_sql_semantic_contract.v1",
            "migration": "services/api/migrations/002_a1_billing_ledger.sql",
            "public_safe": True,
            "provider_config_storage": {
                "durable_policy": "hash_or_reference_only",
                "provider_config_column_present": False,
                "provider_config_object_persisted": False,
                "hash_columns": ["billing_provider_events.payload_sha256"],
                "reference_only_fields": [
                    "billing_accounts.account_ref",
                    "billing_accounts.customer_ref",
                    "billing_ledger_events.provider_event_ref",
                ],
                "forbidden_durable_columns": [
                    "provider_config",
                    "provider_secret",
                    "client_secret",
                    "raw_payload",
                    "payload",
                    "card_number",
                ],
                "forbidden_public_markers": [
                    "stripe secret key prefix",
                    "authorization header marker",
                ],
            },
            "replay_semantics": {
                "accepted": {
                    "status": "accepted",
                    "ledger_mutation_count": 1,
                    "payload_sha256_relation": "new_provider_event",
                    "raw_payload_included": False,
                    "secret_value_present": False,
                },
                "duplicate": {
                    "status": "duplicate",
                    "ledger_mutation_count": 0,
                    "payload_sha256_relation": "same_provider_event_same_hash",
                    "raw_payload_included": False,
                    "secret_value_present": False,
                },
                "conflict": {
                    "status": "conflict",
                    "ledger_mutation_count": 0,
                    "payload_sha256_relation": "same_provider_event_different_hash",
                    "raw_payload_included": False,
                    "secret_value_present": False,
                },
                "match_key": [
                    "organization_id",
                    "project_id",
                    "provider",
                    "mode",
                    "provider_event_id",
                ],
            },
            "object_evidence_linkage": {
                "billing_sql_edges": [
                    {
                        "from": "billing_provider_events.ledger_event_id",
                        "to": "billing_ledger_events.id",
                        "link_type": "provider replay row stores accepted ledger mutation id pointer",
                    },
                    {
                        "from": "billing_ledger_events.provider_event_id",
                        "to": "billing_provider_events.id",
                        "link_type": "ledger row links back to provider event row",
                    },
                ],
                "go_postgres_hash_only_objects": [
                    {
                        "table": "ashr_run_uploads",
                        "object_id_column": "upload_id",
                        "sha256_column": "result_sha256",
                        "raw_payload_column_present": False,
                    },
                    {
                        "table": "ashr_trace_batches",
                        "object_id_column": "batch_id",
                        "sha256_column": "observations_sha256",
                        "raw_payload_column_present": False,
                    },
                    {
                        "table": "ashr_artifact_manifests",
                        "object_id_column": "artifact_id",
                        "sha256_column": "manifest_sha256",
                        "raw_payload_column_present": False,
                    },
                ],
                "public_snapshot_fields": [
                    "billing_snapshot_sha256",
                    "ledger_event_count",
                    "provider_event_count",
                    "raw_payload_included",
                    "secret_value_present",
                ],
            },
            "validation": {
                "pytest_targets": [
                    "tests/a1/test_billing_provider_contract.py",
                    "tests/a1/test_billing_ledger_migration_manifest.py",
                ],
                "schema_path": "docs/a1/schemas/billing_sql_semantic_contract.schema.json",
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            contract_path = Path(tmp_dir) / "billing_sql_semantic_contract.json"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            report = build_evidence_readiness_report(
                calibration_matrix,
                {},
                semantic_harness,
                a1_billing_sql_semantic_contract_path=contract_path,
            )

        billing_sql = report["a1_billing_sql_semantic_contract"]
        self.assertTrue(billing_sql["available"])
        self.assertEqual(billing_sql["schema_version"], "ashr.clone.a1.billing_sql_semantic_contract.v1")
        self.assertEqual(billing_sql["migration"], "services/api/migrations/002_a1_billing_ledger.sql")
        self.assertTrue(billing_sql["public_safe"])
        self.assertEqual(billing_sql["durable_policy"], "hash_or_reference_only")
        self.assertFalse(billing_sql["provider_config_column_present"])
        self.assertFalse(billing_sql["provider_config_object_persisted"])
        self.assertEqual(billing_sql["hash_columns"], ["billing_provider_events.payload_sha256"])
        self.assertEqual(billing_sql["reference_only_field_count"], 3)
        self.assertIn("provider_config", billing_sql["forbidden_durable_columns"])
        self.assertEqual(billing_sql["forbidden_public_marker_count"], 2)
        self.assertEqual(billing_sql["replay_statuses"], ["accepted", "conflict", "duplicate"])
        self.assertEqual(billing_sql["accepted_ledger_mutation_count"], 1)
        self.assertEqual(billing_sql["duplicate_ledger_mutation_count"], 0)
        self.assertEqual(billing_sql["conflict_ledger_mutation_count"], 0)
        self.assertFalse(billing_sql["raw_payload_included"])
        self.assertFalse(billing_sql["secret_value_present"])
        self.assertIn("provider_event_id", billing_sql["match_key"])
        self.assertEqual(billing_sql["billing_sql_edge_count"], 2)
        self.assertEqual(billing_sql["go_postgres_hash_only_object_count"], 3)
        self.assertEqual(billing_sql["raw_payload_column_present_count"], 0)
        self.assertIn("billing_snapshot_sha256", billing_sql["public_snapshot_fields"])
        self.assertEqual(
            billing_sql["schema_path"],
            "docs/a1/schemas/billing_sql_semantic_contract.schema.json",
        )
        self.assertTrue(billing_sql["ready_for_a2_sql_policy_context"])
        self.assertFalse(billing_sql["c3_grading_ready"])
        self.assertTrue(billing_sql["a2_policy_implications"]["sql_semantic_policy_context"])
        self.assertTrue(billing_sql["a2_policy_implications"]["can_support_replay_regression_cases"])
        self.assertTrue(billing_sql["a2_policy_implications"]["can_support_hash_only_artifact_audit"])
        self.assertTrue(billing_sql["a2_policy_implications"]["must_not_mark_c3_from_sql_context"])

    def test_c4_semantic_live_gate_requires_reviewed_metadata_cost_and_sdk_coverage(self):
        def reviewed_semantic_matrix(*, complete_metadata: bool, include_typescript: bool) -> dict:
            payload = json.loads((ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json").read_text(encoding="utf-8"))
            observations = []
            for index, case in enumerate(payload["cases"]):
                case_id = case["case_id"]
                fixture = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
                result = grade_run(
                    fixture["scenario_id"],
                    fixture.get("run", fixture),
                    pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    case_id=case_id,
                )
                sdk_language = "typescript" if include_typescript and index % 2 else "python"
                observation = {
                    "case_id": case_id,
                    "scenario_id": fixture["scenario_id"],
                    "source": "llm_judge",
                    "status": "available",
                    "provider": "reviewed_model_call_sample",
                    "model": "semantic-judge-reviewed-v1",
                    "passed": result["passed"],
                    "primary_failure_class": result["primary_failure_class"],
                    "score": result["score"],
                    "confidence": 0.92,
                    "rationale": "Synthetic reviewed semantic row used only to test the C4 live evidence gate.",
                    "cost": {"prompt_tokens": 700 + index, "completion_tokens": 90 + index, "estimated_usd": 0.0015},
                    "evidence_ref": f"docs/evidence/private_refs/a2_semantic_judge_review.redacted.json#{case_id}",
                }
                if complete_metadata:
                    observation["metadata"] = {
                        "raw_case_id": case_id,
                        "prompt_template_id": "a2_semantic_judge_prompt_v1",
                        "prompt_hash": f"sha256:prompt-{index}",
                        "response_hash": f"sha256:response-{index}",
                        "review_status": "reviewed",
                        "sdk_language": sdk_language,
                    }
                observations.append(observation)
            payload = merge_calibration_observations(payload, {"observations": observations}, source="llm_judge")
            with tempfile.TemporaryDirectory() as tmp_dir:
                path = Path(tmp_dir) / "semantic_observations.json"
                path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
                return build_calibration_matrix(
                    pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    run_dir=ROOT / "fixtures/a2/runs",
                    observations_path=path,
                )

        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        incomplete_matrix = reviewed_semantic_matrix(complete_metadata=False, include_typescript=True)
        incomplete_harness = build_semantic_harness_report(incomplete_matrix, sdk_parity)
        incomplete_readiness = build_evidence_readiness_report(incomplete_matrix, {}, incomplete_harness)
        self.assertEqual(incomplete_harness["reviewed_live_observation_count"], 0)
        self.assertFalse(incomplete_harness["live_model_evidence_available"])
        self.assertEqual(incomplete_readiness["semantic_live_merge_gate"]["status"], "not_audited")
        self.assertFalse(incomplete_readiness["semantic_live_merge_gate"]["safe_to_mark_c4_met"])
        self.assertEqual(incomplete_readiness["semantic_live_merge_gate"]["missing_audited_observation_count"], 6)

        single_language_matrix = reviewed_semantic_matrix(complete_metadata=True, include_typescript=False)
        single_language_harness = build_semantic_harness_report(single_language_matrix, sdk_parity)
        self.assertEqual(single_language_harness["reviewed_live_observation_count"], 6)
        self.assertEqual(single_language_harness["reviewed_live_sdk_languages"], ["python"])
        self.assertFalse(single_language_harness["live_model_evidence_available"])
        self.assertIn("typescript", single_language_harness["reviewed_live_evidence_gaps"][0])

        complete_matrix = reviewed_semantic_matrix(complete_metadata=True, include_typescript=True)
        complete_harness = build_semantic_harness_report(complete_matrix, sdk_parity)
        complete_readiness = build_evidence_readiness_report(complete_matrix, {}, complete_harness)
        coverage_report = build_coverage_report(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        commercial = build_commercial_readiness_report(
            coverage_report,
            complete_matrix,
            semantic_harness_report=complete_harness,
            evidence_readiness_report=complete_readiness,
        )
        self.assertTrue(complete_harness["live_model_evidence_available"])
        self.assertEqual(complete_harness["reviewed_live_observation_count"], 6)
        self.assertEqual(complete_harness["missing_reviewed_live_observation_count"], 0)
        self.assertEqual(complete_harness["reviewed_live_sdk_languages"], ["python", "typescript"])
        self.assertEqual(complete_harness["reviewed_live_evidence_gaps"], [])
        self.assertEqual(complete_readiness["semantic_live_merge_gate"]["status"], "audited_live_model_evidence")
        self.assertEqual(complete_readiness["semantic_live_merge_gate"]["audited_public_observation_count"], 6)
        self.assertEqual(complete_readiness["semantic_live_merge_gate"]["missing_audited_observation_count"], 0)
        self.assertTrue(complete_readiness["semantic_live_merge_gate"]["safe_to_mark_c4_met"])
        gates = {gate["gate"]: gate for gate in commercial["gate_status"]}
        self.assertEqual(gates["C4"]["status"], "met")

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

    def test_ashr_grading_collection_packet_prepares_c3_cases_without_raw_outputs(self):
        packet = build_ashr_grading_collection_packet(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
            case_map_path=ROOT / "fixtures/a2/calibration/ashr_grading_batch_case_map.json",
        )
        expected_packet = json.loads((ROOT / "fixtures/a2/calibration/a2_ashr_grading_collection_packet.json").read_text(encoding="utf-8"))
        packet_text = json.dumps(packet)

        self.assertEqual(packet, expected_packet)
        self.assertEqual(packet["schema_version"], "a2.ashr_grading_collection_packet.v1")
        self.assertEqual(packet["status"], "ready_for_private_collection")
        self.assertEqual(packet["case_count"], 6)
        self.assertTrue(all(packet["readiness_checks"].values()))
        self.assertEqual({case["case_id"] for case in packet["cases"]}, set(json.loads((ROOT / "fixtures/a2/calibration/ashr_grading_batch_case_map.json").read_text(encoding="utf-8")).values()))
        self.assertNotIn("API key is", packet_text)
        self.assertNotIn("ashr_live_", packet_text)
        secret_case = next(case for case in packet["cases"] if case["case_id"] == "sample-a2-s048-secret-leak")
        self.assertTrue(secret_case["run_summary"]["contains_secret_like_text"])
        self.assertFalse(secret_case["run_summary"]["public_packet_contains_raw_final_response"])
        for case in packet["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertTrue(case["ashr_test_id"].startswith("ashr-a2-g3-"))
                self.assertEqual(case["local_judge"]["judge_count"], 5)
                self.assertIn("final_response_sha256_12", case["run_summary"])
                self.assertNotIn("raw_final_response", case["run_summary"])

    def test_semantic_judge_collection_packet_prepares_c4_cases_without_raw_payloads(self):
        packet = build_semantic_judge_collection_packet(
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            run_dir=ROOT / "fixtures/a2/runs",
            observations_path=ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        )
        expected_packet = json.loads((ROOT / "fixtures/a2/calibration/a2_semantic_judge_collection_packet.json").read_text(encoding="utf-8"))
        packet_text = json.dumps(packet)

        self.assertEqual(packet, expected_packet)
        self.assertEqual(packet["schema_version"], "a2.semantic_judge_collection_packet.v1")
        self.assertEqual(packet["status"], "ready_for_private_collection")
        self.assertEqual(packet["case_count"], 6)
        self.assertTrue(packet["metadata"]["does_not_claim_c4_met"])
        self.assertTrue(packet["readiness_checks"]["covers_python_and_typescript"])
        self.assertTrue(packet["readiness_checks"]["public_packet_omits_raw_prompt_and_response"])
        self.assertEqual(set(packet["sdk_language_plan"]["allocation_counts"]), {"python", "typescript"})
        self.assertTrue(packet["sdk_language_plan"]["typescript_media_case_present"])
        self.assertNotIn("API key is", packet_text)
        self.assertNotIn("ashr_live_", packet_text)
        self.assertNotIn("raw_prompt_payload", packet_text)
        self.assertNotIn("raw_response_payload", packet_text)
        secret_case = next(case for case in packet["cases"] if case["case_id"] == "sample-a2-s048-secret-leak")
        self.assertTrue(secret_case["prompt_public_summary"]["contains_secret_like_text"])
        media_case = next(case for case in packet["cases"] if case["case_id"] == "sample-a2-s031-media-pipeline-unsupported-output")
        self.assertEqual(media_case["sdk_language"], "typescript")
        for case in packet["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertIn(case["sdk_language"], {"python", "typescript"})
                self.assertEqual(case["prompt_template_id"], "a2_semantic_judge_prompt_v1")
                self.assertIn("prompt_hash", case["required_metadata_fields"])
                self.assertIn("response_hash", case["required_metadata_fields"])
                self.assertIn("estimated_usd", packet["semantic_judge_contract"]["cost_fields"])
                self.assertIn("final_response_sha256_12", case["prompt_public_summary"])
                self.assertFalse(case["prompt_public_summary"]["public_packet_contains_raw_prompt"])
                self.assertFalse(case["prompt_public_summary"]["public_packet_contains_raw_response"])

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
        evidence_readiness = build_evidence_readiness_report(calibration_matrix, batch_plan, semantic_harness)
        report = build_commercial_readiness_report(
            coverage_report,
            calibration_matrix,
            case_book_report=case_book,
            sdk_parity_report=sdk_parity,
            batch_plan_report=batch_plan,
            semantic_harness_report=semantic_harness,
            regression_replay_report=regression_replay,
            evidence_readiness_report=evidence_readiness,
        )
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_commercial_readiness_report.json").read_text(encoding="utf-8"))
        readiness_schema = json.loads((ROOT / "docs/a2/schemas/commercial_readiness.schema.json").read_text(encoding="utf-8"))

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
        self.assertEqual(report["scope_boundary"]["status"], "controlled")
        self.assertIn("scenario, rubric, judge", report["scope_boundary"]["a2_owned"][0])
        self.assertTrue(any("hosted Ashr run execution" in item for item in report["scope_boundary"]["delegated_to_a1"]))
        self.assertTrue(any("dashboard UI" in item for item in report["scope_boundary"]["delegated_to_a3"]))
        self.assertTrue(any("live Ashr or LLM calls" in item for item in report["scope_boundary"]["blocked_growth"]))
        scope_guardrails = {item["id"]: item for item in report["scope_boundary"]["guardrails"]}
        self.assertEqual(scope_guardrails["a2_grade_contract_stable"]["status"], "met")
        self.assertEqual(scope_guardrails["a1_runner_boundary"]["status"], "met")
        self.assertEqual(scope_guardrails["a3_optional_feed_boundary"]["status"], "met")
        self.assertEqual(scope_guardrails["external_evidence_boundary"]["status"], "met")
        gates = {gate["gate"]: gate for gate in report["gate_status"]}
        self.assertEqual(gates["C0"]["status"], "met")
        self.assertEqual(gates["C1"]["status"], "met")
        self.assertEqual(gates["C2"]["status"], "met")
        self.assertEqual(gates["C3"]["status"], "partial")
        self.assertIn("Collect reviewed Ashr grading observations", gates["C3"]["gaps"][0])
        self.assertIn("Public Ashr grading merge gate is not_merged", gates["C3"]["gaps"][1])
        self.assertIn("fixtures/a2/results/a2_evidence_readiness_report.json", gates["C3"]["evidence_refs"])
        self.assertEqual(gates["C4"]["status"], "partial")
        self.assertIn("offline", gates["C4"]["gaps"][0])
        self.assertIn("Semantic live merge gate is offline_reference_only", gates["C4"]["gaps"][1])
        self.assertIn("fixtures/a2/results/a2_semantic_harness_report.json", gates["C4"]["evidence_refs"])
        self.assertIn("fixtures/a2/results/a2_evidence_readiness_report.json", gates["C4"]["evidence_refs"])
        self.assertEqual(report["evidence_snapshot"]["ashr_grading_missing"], 6)
        self.assertEqual(report["evidence_snapshot"]["ashr_public_merge_status"], "not_merged")
        self.assertFalse(report["evidence_snapshot"]["ashr_public_matrix_merged"])
        self.assertFalse(report["evidence_snapshot"]["ashr_safe_to_mark_c3_met"])
        self.assertEqual(report["evidence_snapshot"]["ashr_public_missing_observations"], 6)
        self.assertTrue(report["evidence_snapshot"]["llm_judge_offline_only"])
        self.assertTrue(report["evidence_snapshot"]["semantic_harness_ready"])
        self.assertFalse(report["evidence_snapshot"]["semantic_harness_live_evidence"])
        self.assertEqual(report["evidence_snapshot"]["semantic_live_merge_status"], "offline_reference_only")
        self.assertFalse(report["evidence_snapshot"]["semantic_audited_live_evidence_merged"])
        self.assertFalse(report["evidence_snapshot"]["semantic_safe_to_mark_c4_met"])
        self.assertEqual(report["evidence_snapshot"]["semantic_missing_audited_observations"], 6)
        self.assertEqual(report["evidence_snapshot"]["semantic_risk_assessment_status"], "offline_reference_risk_register")
        self.assertTrue(report["evidence_snapshot"]["semantic_false_positive_tracking_ready"])
        self.assertEqual(report["evidence_snapshot"]["semantic_false_positive_candidates"], 0)
        self.assertEqual(report["evidence_snapshot"]["semantic_false_negative_candidates"], 0)
        self.assertEqual(report["evidence_snapshot"]["semantic_failure_class_drift_candidates"], 1)
        self.assertEqual(report["evidence_snapshot"]["semantic_score_delta_reviews"], 4)
        self.assertEqual(report["evidence_snapshot"]["semantic_risk_case_count"], 4)
        self.assertEqual(report["evidence_snapshot"]["case_book_regression_count"], 1)
        self.assertEqual(report["evidence_snapshot"]["regression_replay_count"], 1)
        self.assertTrue(report["evidence_snapshot"]["regression_replay_ready"])
        self.assertEqual(report["evidence_snapshot"]["regression_replay_maturity"], "seed")
        self.assertTrue(report["evidence_snapshot"]["evidence_readiness_ready"])
        self.assertTrue(report["evidence_snapshot"]["real_api_evidence_available"])
        self.assertGreaterEqual(report["evidence_snapshot"]["real_api_total_records"], 140)
        self.assertGreaterEqual(report["evidence_snapshot"]["real_api_record_count"], 110)
        self.assertGreaterEqual(report["evidence_snapshot"]["real_api_read_ok_count"], 80)
        self.assertGreaterEqual(report["evidence_snapshot"]["real_api_quota_block_count"], 5)
        self.assertTrue(report["evidence_snapshot"]["real_api_create_request_blocked"])
        self.assertTrue(report["evidence_snapshot"]["official_sdk_smoke_read_only_reachable"])
        self.assertEqual(report["evidence_snapshot"]["official_sdk_smoke_ok_call_count"], 6)
        self.assertEqual(report["evidence_snapshot"]["official_sdk_smoke_error_call_count"], 0)
        self.assertEqual(report["evidence_snapshot"]["sdk_language_count"], 2)
        self.assertTrue(report["evidence_snapshot"]["sdk_parity_passed"])
        self.assertEqual(report["evidence_snapshot"]["planned_batch_count"], 5)
        self.assertTrue(report["evidence_snapshot"]["batch_plan_ready"])
        self.assertEqual(report["next_top_3"][0]["id"], "fill_ashr_grading_column")
        auditor = report["growth_auditor"]
        self.assertEqual(auditor["auditor_id"], "a2_money_grade_auditor")
        self.assertEqual(auditor["audit_basis"], "docs/strategy/large-saas-a1-a2-a3-full-plan.md")
        self.assertEqual(
            auditor["money_direction"]["primary"],
            "release_gate_with_reviewed_evidence_and_regression_replay",
        )
        self.assertGreaterEqual(len(auditor["new_sellable_capabilities"]), 5)
        self.assertGreaterEqual(len(auditor["toy_risks_to_upgrade"]), 4)
        self.assertGreaterEqual(len(auditor["customer_payment_drivers"]), 4)
        self.assertEqual(auditor["current_evidence_strength"]["growth_point_count"], 20)
        self.assertEqual(len(auditor["parallel_growth_points"]), 20)
        growth_ids = {point["id"] for point in auditor["parallel_growth_points"]}
        self.assertIn("official_grading_diff_import", growth_ids)
        self.assertIn("production_incident_to_regression", growth_ids)
        self.assertIn("typescript_python_parity_gate", growth_ids)
        growth_tracks = {point["parallel_track"] for point in auditor["parallel_growth_points"]}
        self.assertLessEqual(
            {"calibration", "workflow", "regression", "integration", "evidence"},
            growth_tracks,
        )
        point_required = set(readiness_schema["$defs"]["growth_point"]["required"])
        for point in auditor["parallel_growth_points"]:
            with self.subTest(growth_point=point["id"]):
                self.assertLessEqual(point_required, set(point))
                self.assertNotIn("docs/evidence/private_refs", point["evidence_ref"])
                self.assertEqual(point["required_artifact_type"], "code_or_test_or_fixture_or_schema_or_evidence")
        self.assertTrue(auditor["parallelization"]["must_parallelize"])

    def test_release_gate_blocks_until_c3_c4_c5_are_reviewed_and_mature(self):
        commercial = json.loads((ROOT / "fixtures/a2/results/a2_commercial_readiness_report.json").read_text(encoding="utf-8"))
        evidence = json.loads((ROOT / "fixtures/a2/results/a2_evidence_readiness_report.json").read_text(encoding="utf-8"))
        calibration = json.loads((ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json").read_text(encoding="utf-8"))
        replay = json.loads((ROOT / "fixtures/a2/results/a2_regression_replay_report.json").read_text(encoding="utf-8"))
        scenario_selection = json.loads((ROOT / "fixtures/a2/results/a2_scenario_selection_report.json").read_text(encoding="utf-8"))
        evidence_index = json.loads((ROOT / "docs/a1/api_calibration/real_api_evidence_index.json").read_text(encoding="utf-8"))
        report = build_release_gate_report(commercial, evidence, calibration, replay, scenario_selection, evidence_index)
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_release_gate_report.json").read_text(encoding="utf-8"))
        report_text = json.dumps(report)

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.release_gate.v1")
        self.assertEqual(report["decision"], "block")
        self.assertEqual(report["exit_code"], 2)
        self.assertGreaterEqual(report["risk_score"], 90)
        self.assertEqual(report["current_commercial_gate"], "C2")
        self.assertEqual(report["hard_gate_ids"], ["C0", "C1", "C2", "C3", "C4", "C5"])
        self.assertGreaterEqual(report["blocking_gate_count"], 3)
        self.assertGreaterEqual(report["evidence_blocker_count"], 3)
        self.assertEqual(report["scenario_selection_gate"]["status"], "ready")
        self.assertTrue(report["scenario_selection_gate"]["minimums_ready"])
        self.assertEqual(report["scenario_selection_blocker_count"], 0)
        self.assertEqual(report["a1_output_policy_gate"]["status"], "ready")
        self.assertEqual(report["a1_output_policy_blocker_count"], 0)
        self.assertGreaterEqual(report["warning_count"], 2)
        self.assertTrue(any(warning["type"] == "api_probe_gate_validation" for warning in report["warnings"]))
        blocker_gates = {blocker.get("gate") for blocker in report["blockers"]}
        self.assertLessEqual({"C3", "C4", "C5"}, blocker_gates)
        c5_blocker = next(
            blocker for blocker in report["blockers"] if blocker.get("type") == "regression_maturity"
        )
        self.assertEqual(c5_blocker["missing_count"], 3)
        self.assertIn("Promote more reviewed", c5_blocker["required_action"])
        self.assertIn("fixtures/a2/results/a2_case_book.json", c5_blocker["evidence_refs"])
        self.assertIn("fixtures/a2/results/a2_evidence_readiness_report.json", report["evidence_refs"])
        self.assertIn("A2 owner", report["review_workflow"]["required_reviewers"])
        self.assertEqual(report["machine_contract"]["ci_mode"], "fail on decision=block")
        self.assertTrue(any(annotation["level"] == "failure" for annotation in report["pr_annotations"]))
        self.assertNotIn("Bearer ", report_text)
        self.assertNotRegex(report_text, re.compile(r"tp_[A-Za-z0-9_\\-]+"))

    def test_release_gate_blocks_when_scenario_selection_minimums_are_not_ready(self):
        commercial = json.loads((ROOT / "fixtures/a2/results/a2_commercial_readiness_report.json").read_text(encoding="utf-8"))
        evidence = json.loads((ROOT / "fixtures/a2/results/a2_evidence_readiness_report.json").read_text(encoding="utf-8"))
        calibration = json.loads((ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json").read_text(encoding="utf-8"))
        replay = json.loads((ROOT / "fixtures/a2/results/a2_regression_replay_report.json").read_text(encoding="utf-8"))
        scenario_selection = json.loads((ROOT / "fixtures/a2/results/a2_scenario_selection_report.json").read_text(encoding="utf-8"))
        scenario_selection["minimums_summary"] = {
            **scenario_selection["minimums_summary"],
            "minimums_ready": False,
            "gaps": ["regression_case_count selected 0 below required 1."],
        }

        report = build_release_gate_report(commercial, evidence, calibration, replay, scenario_selection)
        scenario_blockers = [item for item in report["blockers"] if item["type"] == "scenario_selection_gate"]

        self.assertEqual(report["scenario_selection_gate"]["status"], "needs_attention")
        self.assertEqual(report["scenario_selection_blocker_count"], 1)
        self.assertEqual(len(scenario_blockers), 1)
        self.assertEqual(scenario_blockers[0]["gate"], "S1")
        self.assertIn("fixtures/a2/results/a2_scenario_selection_report.json", scenario_blockers[0]["evidence_refs"])

    def test_release_gate_blocks_on_a1_unsafe_output_policy_counts(self):
        commercial = json.loads((ROOT / "fixtures/a2/results/a2_commercial_readiness_report.json").read_text(encoding="utf-8"))
        evidence = json.loads((ROOT / "fixtures/a2/results/a2_evidence_readiness_report.json").read_text(encoding="utf-8"))
        calibration = json.loads((ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json").read_text(encoding="utf-8"))
        replay = json.loads((ROOT / "fixtures/a2/results/a2_regression_replay_report.json").read_text(encoding="utf-8"))
        scenario_selection = json.loads((ROOT / "fixtures/a2/results/a2_scenario_selection_report.json").read_text(encoding="utf-8"))
        evidence_index = json.loads((ROOT / "docs/a1/api_calibration/real_api_evidence_index.json").read_text(encoding="utf-8"))
        evidence_index["output_policy_counts"] = {
            **evidence_index["output_policy_counts"],
            "unsafe_real_nonprivate_override": 1,
            "private_required_but_not_private": 2,
        }

        report = build_release_gate_report(commercial, evidence, calibration, replay, scenario_selection, evidence_index)
        output_policy_blockers = [item for item in report["blockers"] if item["type"] == "a1_output_policy_gate"]

        self.assertEqual(report["a1_output_policy_gate"]["status"], "blocked")
        self.assertFalse(report["a1_output_policy_gate"]["ready"])
        self.assertEqual(report["a1_output_policy_blocker_count"], 1)
        self.assertEqual(len(output_policy_blockers), 1)
        self.assertEqual(output_policy_blockers[0]["gate"], "A1-OUTPUT-POLICY")
        self.assertEqual(output_policy_blockers[0]["severity"], "critical")
        self.assertEqual(output_policy_blockers[0]["dangerous_counts"]["unsafe_real_nonprivate_override"], 1)
        self.assertEqual(output_policy_blockers[0]["dangerous_counts"]["private_required_but_not_private"], 2)
        self.assertIn("a1_output_policy_gate", report["machine_contract"]["blocking_fields"])
        self.assertIn("docs/a1/api_calibration/real_api_evidence_index.json", report["evidence_refs"])

    def test_release_gate_cli_can_fail_on_block_for_ci(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/a2_build_release_gate_report.py"),
                "--check",
                "--fail-on-block",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("A2 release gate report matches", result.stdout)

    def test_scenario_selection_builds_project_pack_with_reasons_and_coverage(self):
        profile = json.loads((ROOT / "fixtures/a2/config/a2_saas_project_selection_profile.json").read_text(encoding="utf-8"))
        report = build_scenario_selection_report(
            profile,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        expected_report = json.loads((ROOT / "fixtures/a2/results/a2_scenario_selection_report.json").read_text(encoding="utf-8"))
        selected_ids = {scenario["scenario_id"] for scenario in report["selected_scenarios"]}

        self.assertEqual(report, expected_report)
        self.assertEqual(report["schema_version"], "a2.scenario_selection.v1")
        self.assertEqual(report["project"]["project_id"], "project_enterprise_saas_agent")
        self.assertEqual(report["environment"], "prod")
        self.assertEqual(report["source_scenario_count"], 60)
        self.assertEqual(report["selected_scenario_count"], 12)
        self.assertTrue(report["effective_criteria"]["environment_policy_applied"])
        self.assertEqual(report["effective_criteria"]["media_requirement"], "required")
        self.assertIn("enterprise_saas_operations", report["effective_criteria"]["capability_axes"])
        self.assertIn("critical", report["effective_criteria"]["risk_tiers"])
        self.assertIn("A2-S031", selected_ids)
        self.assertIn("A2-S035", selected_ids)
        self.assertIn("A2-S048", selected_ids)
        self.assertTrue(report["coverage_summary"]["coverage_ready"])
        self.assertEqual(report["coverage_summary"]["missing_capability_axes"], [])
        self.assertEqual(report["coverage_summary"]["missing_risk_tiers"], [])
        self.assertEqual(report["coverage_summary"]["missing_tenant_saas_tags"], [])
        self.assertTrue(report["coverage_summary"]["media_requirement_met"])
        self.assertGreaterEqual(report["coverage_summary"]["media_scenario_count"], 1)
        self.assertGreaterEqual(report["coverage_summary"]["risk_tier_counts"]["critical"], 1)
        self.assertGreaterEqual(report["coverage_summary"]["risk_tier_counts"]["high"], 1)
        self.assertEqual(report["coverage_summary"]["tenant_saas_tag_counts"]["enterprise-saas"], 8)
        for scenario in report["selected_scenarios"]:
            with self.subTest(selected_scenario=scenario["scenario_id"]):
                self.assertTrue(scenario["selection_reason"])
                self.assertGreater(scenario["selection_score"], 0)

    def test_scenario_selection_cli_matches_fixture(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/a2_select_scenario_pack.py"),
                "--profile",
                "fixtures/a2/config/a2_saas_project_selection_profile.json",
                "--output",
                "fixtures/a2/results/a2_scenario_selection_report.json",
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("scenario selection report matches", result.stdout)

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
        self.assertEqual(observations[1]["metadata"]["review_status"], "unreviewed")
        secret_sample = json.loads(json.dumps(sample))
        secret_sample["response"]["run"]["result"]["tests"][1]["action_results"][0]["divergence_notes"] = (
            "Bearer" + " secret-token for kay" + "@example.test"
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

    def test_partial_ashr_grading_import_does_not_mark_c3_safe(self):
        sample = json.loads((ROOT / "fixtures/a2/calibration/ashr_grading_import_sample.json").read_text(encoding="utf-8"))
        case_map = json.loads((ROOT / "fixtures/a2/calibration/ashr_grading_import_case_map.json").read_text(encoding="utf-8"))
        observations = import_ashr_grading_observations(
            sample,
            case_map=case_map,
            evidence_ref="docs/evidence/private_refs/a2_ashr_grading_sample.redacted.json",
        )
        payload = json.loads((ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json").read_text(encoding="utf-8"))
        payload = merge_calibration_observations(payload, {"observations": observations}, source="ashr_grading")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "partial_observations.json"
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            matrix = build_calibration_matrix(
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                run_dir=ROOT / "fixtures/a2/runs",
                observations_path=path,
            )

        coverage_report = build_coverage_report(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        case_book = build_case_book_report(matrix)
        regression_replay = build_regression_replay_report(
            matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(matrix, sdk_parity)
        batch_plan = build_batch_plan_report(
            coverage_report,
            matrix,
            case_book,
            sdk_parity,
            semantic_harness,
            regression_replay,
        )
        evidence_readiness = build_evidence_readiness_report(matrix, batch_plan, semantic_harness)
        commercial = build_commercial_readiness_report(
            coverage_report,
            matrix,
            case_book_report=case_book,
            sdk_parity_report=sdk_parity,
            batch_plan_report=batch_plan,
            semantic_harness_report=semantic_harness,
            regression_replay_report=regression_replay,
            evidence_readiness_report=evidence_readiness,
        )

        ashr_gate = evidence_readiness["ashr_public_merge_gate"]
        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["available"], 2)
        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["missing"], 4)
        self.assertEqual(ashr_gate["status"], "not_merged")
        self.assertFalse(ashr_gate["public_matrix_merged"])
        self.assertFalse(ashr_gate["safe_to_mark_c3_met"])
        self.assertEqual(ashr_gate["current_public_observation_count"], 2)
        self.assertEqual(ashr_gate["merged_public_observation_count"], 0)
        self.assertEqual(ashr_gate["reviewed_public_observation_count"], 0)
        self.assertEqual(ashr_gate["missing_public_observation_count"], 4)
        self.assertEqual(ashr_gate["missing_reviewed_observation_count"], 6)
        gates = {gate["gate"]: gate for gate in commercial["gate_status"]}
        self.assertEqual(gates["C3"]["status"], "partial")
        self.assertIn("4 missing calibration cases", gates["C3"]["gaps"][0])
        self.assertFalse(commercial["evidence_snapshot"]["ashr_safe_to_mark_c3_met"])
        self.assertEqual(commercial["evidence_snapshot"]["ashr_public_missing_observations"], 4)

    def test_complete_unreviewed_ashr_grading_import_does_not_mark_c3_safe(self):
        payload = json.loads((ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json").read_text(encoding="utf-8"))
        observations = []
        for case in payload["cases"]:
            case_id = case["case_id"]
            fixture = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
            result = grade_run(
                fixture["scenario_id"],
                fixture.get("run", fixture),
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                case_id=case_id,
            )
            observations.append(
                {
                    "case_id": case_id,
                    "scenario_id": fixture["scenario_id"],
                    "source": "ashr_grading",
                    "status": "available",
                    "provider": "synthetic unreviewed Ashr grading summary",
                    "model": "ashr-server-side",
                    "passed": result["passed"],
                    "primary_failure_class": result["primary_failure_class"],
                    "score": result["score"],
                    "confidence": 0.99,
                    "rationale": "Synthetic unreviewed row used only to test the C3 review gate.",
                    "cost": {"prompt_tokens": 0, "completion_tokens": 0, "estimated_usd": 0.0},
                    "evidence_ref": "docs/evidence/private_refs/a2_ashr_grading_import.unreviewed.synthetic.json",
                    "metadata": {"review_status": "unreviewed"},
                }
            )
        payload = merge_calibration_observations(payload, {"observations": observations}, source="ashr_grading")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "complete_unreviewed_observations.json"
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            matrix = build_calibration_matrix(
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                run_dir=ROOT / "fixtures/a2/runs",
                observations_path=path,
            )

        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(matrix, sdk_parity)
        evidence_readiness = build_evidence_readiness_report(matrix, {}, semantic_harness)

        ashr_gate = evidence_readiness["ashr_public_merge_gate"]
        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["available"], 6)
        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["missing"], 0)
        self.assertEqual(ashr_gate["status"], "merged_unreviewed")
        self.assertFalse(ashr_gate["public_matrix_merged"])
        self.assertFalse(ashr_gate["safe_to_mark_c3_met"])
        self.assertEqual(ashr_gate["current_public_observation_count"], 6)
        self.assertEqual(ashr_gate["merged_public_observation_count"], 0)
        self.assertEqual(ashr_gate["reviewed_public_observation_count"], 0)
        self.assertEqual(ashr_gate["missing_public_observation_count"], 0)
        self.assertEqual(ashr_gate["missing_reviewed_observation_count"], 6)

    def test_complete_reviewed_ashr_grading_import_marks_c3_safe(self):
        payload = json.loads((ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json").read_text(encoding="utf-8"))
        observations = []
        for case in payload["cases"]:
            case_id = case["case_id"]
            fixture = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
            result = grade_run(
                fixture["scenario_id"],
                fixture.get("run", fixture),
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                case_id=case_id,
            )
            observations.append(
                {
                    "case_id": case_id,
                    "scenario_id": fixture["scenario_id"],
                    "source": "ashr_grading",
                    "status": "available",
                    "provider": "synthetic reviewed Ashr grading summary",
                    "model": "ashr-server-side",
                    "passed": result["passed"],
                    "primary_failure_class": result["primary_failure_class"],
                    "score": result["score"],
                    "confidence": 0.99,
                    "rationale": "Synthetic reviewed row used only to test the 6/6 public merge gate.",
                    "cost": {"prompt_tokens": 0, "completion_tokens": 0, "estimated_usd": 0.0},
                    "evidence_ref": "docs/evidence/private_refs/a2_ashr_grading_import.review.synthetic.json",
                    "metadata": {
                        "raw_case_id": f"ashr-{case_id}",
                        "run_id": "synthetic-reviewed-run",
                        "review_status": "reviewed",
                    },
                }
            )
        payload = merge_calibration_observations(payload, {"observations": observations}, source="ashr_grading")

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "complete_observations.json"
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            matrix = build_calibration_matrix(
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                run_dir=ROOT / "fixtures/a2/runs",
                observations_path=path,
            )

        coverage_report = build_coverage_report(ROOT / "packages/scenarios/a2_g3_full_pack.json")
        case_book = build_case_book_report(matrix)
        regression_replay = build_regression_replay_report(
            matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        sdk_parity = build_sdk_parity_report(pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json")
        semantic_harness = build_semantic_harness_report(matrix, sdk_parity)
        batch_plan = build_batch_plan_report(
            coverage_report,
            matrix,
            case_book,
            sdk_parity,
            semantic_harness,
            regression_replay,
        )
        evidence_readiness = build_evidence_readiness_report(matrix, batch_plan, semantic_harness)
        commercial = build_commercial_readiness_report(
            coverage_report,
            matrix,
            case_book_report=case_book,
            sdk_parity_report=sdk_parity,
            batch_plan_report=batch_plan,
            semantic_harness_report=semantic_harness,
            regression_replay_report=regression_replay,
            evidence_readiness_report=evidence_readiness,
        )

        ashr_gate = evidence_readiness["ashr_public_merge_gate"]
        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["available"], 6)
        self.assertEqual(matrix["source_coverage"]["ashr_grading"]["missing"], 0)
        self.assertEqual(ashr_gate["status"], "merged")
        self.assertTrue(ashr_gate["public_matrix_merged"])
        self.assertTrue(ashr_gate["safe_to_mark_c3_met"])
        self.assertEqual(ashr_gate["current_public_observation_count"], 6)
        self.assertEqual(ashr_gate["merged_public_observation_count"], 6)
        self.assertEqual(ashr_gate["reviewed_public_observation_count"], 6)
        self.assertEqual(ashr_gate["missing_public_observation_count"], 0)
        self.assertEqual(ashr_gate["missing_reviewed_observation_count"], 0)
        gates = {gate["gate"]: gate for gate in commercial["gate_status"]}
        self.assertEqual(gates["C3"]["status"], "met")
        self.assertEqual(gates["C3"]["gaps"], [])
        self.assertTrue(commercial["evidence_snapshot"]["ashr_safe_to_mark_c3_met"])
        self.assertEqual(commercial["evidence_snapshot"]["ashr_public_missing_observations"], 0)

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
                "--review-status",
                "reviewed",
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
        self.assertEqual(payload["observations"][0]["metadata"]["review_status"], "reviewed")
        self.assertNotIn("Bearer ", result.stdout)
        self.assertNotIn("@", result.stdout)

    def test_ashr_grading_evidence_scan_cli_summarizes_without_raw_payload(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/a2_scan_ashr_grading_evidence.py"),
                "--input",
                str(ROOT / "fixtures/a2/calibration/ashr_grading_import_sample.json"),
                "--case-map",
                str(ROOT / "fixtures/a2/calibration/ashr_grading_import_case_map.json"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], "a2.ashr_grading_evidence_scan.v1")
        self.assertEqual(payload["expected_case_count"], 2)
        self.assertEqual(payload["matched_case_count"], 2)
        self.assertEqual(payload["missing_case_ids"], [])
        self.assertTrue(payload["complete_expected_match"])
        self.assertTrue(payload["import_ready_when_reviewed"])
        self.assertFalse(payload["safe_to_mark_c3_met"])
        self.assertTrue(payload["redaction_policy"]["omits_unmapped_test_ids"])
        self.assertNotIn("ashr-pass-control", result.stdout)
        self.assertNotIn("ashr-wrong-contract-path", result.stdout)
        self.assertNotIn("Bearer ", result.stdout)
        self.assertNotIn("@", result.stdout)

    def test_local_lite_check_plan_stays_lightweight_and_offline(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/a2_local_lite_check.py"),
                "--plan",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["schema_version"], "a2.local_lite_plan.v1")
        self.assertEqual(plan["profile"], "local-lite")
        self.assertFalse(plan["requires_network"])
        self.assertFalse(plan["requires_node_modules"])
        self.assertFalse(plan["requires_browser"])
        self.assertFalse(plan["requires_ashr_api_key"])
        self.assertFalse(plan["writes_files"])
        commands = [" ".join(check["command"]) for check in plan["checks"]]
        self.assertIn("scripts/a2_regenerate_fixtures.py --check", commands[0])
        self.assertIn("-m unittest discover -s tests/a2", commands[1])
        self.assertIn("live Ashr API calls", plan["excluded_by_design"])

    def test_external_evidence_preflight_stays_public_and_actionable(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/a2_external_evidence_preflight.py"),
                "--json",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Bearer ", result.stdout)
        self.assertNotRegex(result.stdout, re.compile(r"sk-[A-Za-z0-9]"))

        preflight = json.loads(result.stdout)
        schema = json.loads((ROOT / "docs/a2/schemas/external_evidence_preflight.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(preflight["schema_version"], "a2.external_evidence_preflight.v1")
        self.assertEqual(schema["properties"]["schema_version"]["const"], preflight["schema_version"])
        self.assertLessEqual(set(schema["required"]), set(preflight))
        self.assertLessEqual(set(schema["properties"]["recommended_commands"]["required"]), set(preflight["recommended_commands"]))
        self.assertFalse(preflight["requires_network"])
        self.assertFalse(preflight["requires_ashr_api_key"])
        self.assertFalse(preflight["reads_private_payloads"])
        self.assertFalse(preflight["writes_files"])
        self.assertTrue(preflight["environment_probe"]["value_redacted"])
        self.assertEqual(preflight["gate_summary"]["C3"]["missing_reviewed_observations"], 6)
        self.assertFalse(preflight["gate_summary"]["C3"]["safe_to_mark_met"])
        self.assertEqual(preflight["gate_summary"]["C4"]["merge_status"], "offline_reference_only")
        self.assertFalse(preflight["gate_summary"]["C4"]["safe_to_mark_met"])
        self.assertEqual(preflight["gate_summary"]["C5"]["current_regression_cases"], 1)
        self.assertEqual(preflight["gate_summary"]["C5"]["target_regression_cases"], 3)
        self.assertIn(
            "docs/evidence/private_refs/a2_ashr_get_run.redacted.json",
            preflight["private_input_refs"],
        )
        self.assertIn(
            "a2_refresh_real_api_evidence_index.py",
            " ".join(preflight["recommended_commands"]["real_api_evidence_refresh"]),
        )
        self.assertIn("--review-status reviewed", " ".join(preflight["recommended_commands"]["ashr_grading"]))
        self.assertIn("API keys", preflight["redaction_policy"]["never_commit"])

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
        schema = json.loads((ROOT / "docs/a2/schemas/real_api_smoke.schema.json").read_text(encoding="utf-8"))
        payload_text = evidence_path.read_text(encoding="utf-8")
        payload = json.loads(payload_text)

        self.assertEqual(payload["schema_version"], "a2.real_api_smoke.v1")
        self.assertEqual(schema["properties"]["schema_version"]["const"], payload["schema_version"])
        self.assertLessEqual(set(schema["required"]), set(payload))
        self.assertLessEqual(set(schema["properties"]["auth"]["required"]), set(payload["auth"]))
        self.assertEqual(payload["api_call_count"], len(payload["calls"]))
        self.assertEqual(payload["api_call_count"], 6)
        self.assertTrue(payload["all_required_calls_reached"])
        self.assertEqual([call["status"] for call in payload["calls"]], ["ok"] * 6)
        self.assertEqual(
            [call["name"] for call in payload["calls"]],
            ["init", "health_check", "list_datasets", "list_runs", "list_requests", "list_agents"],
        )
        self.assertNotRegex(payload_text, re.compile(r"tp_[A-Za-z0-9_\\-]+"))
        self.assertNotIn("Bearer ", payload_text)
        self.assertNotIn("@", payload_text)
        for call in payload["calls"]:
            self.assertNotIn("payload", call)
            self.assertNotIn("response", call)

    def test_real_api_evidence_index_matches_public_safe_schema(self):
        evidence_path = ROOT / "docs/a1/api_calibration/real_api_evidence_index.json"
        schema = json.loads((ROOT / "docs/a2/schemas/evidence_index.schema.json").read_text(encoding="utf-8"))
        payload_text = evidence_path.read_text(encoding="utf-8")
        payload = json.loads(payload_text)
        records = payload["records"]

        self.assertEqual(payload["schema_version"], "ashr.clone.evidence_index.v1")
        self.assertEqual(schema["properties"]["schema_version"]["const"], payload["schema_version"])
        self.assertLessEqual(set(schema["required"]), set(payload))
        self.assertEqual(payload["total_records"], len(records))
        self.assertGreaterEqual(payload["total_records"], 100)
        self.assertEqual(payload["status_counts"], self._record_counts(records, "status"))
        self.assertEqual(payload["function_counts"], self._record_counts(records, "function"))
        self.assertEqual(payload["error_kind_counts"], self._record_counts(records, "error_kind"))
        self.assertEqual(
            payload["quota_block_count"],
            sum(1 for record in records if isinstance(record.get("quota"), dict) and record["quota"].get("blocked") is True),
        )

        record_required = set(schema["$defs"]["record"]["required"])
        forbidden_raw_keys = {"request", "response", "error", "response_headers"}
        for record in records:
            with self.subTest(record=record["path"]):
                self.assertLessEqual(record_required, set(record))
                self.assertTrue(record["path"].startswith("docs/evidence/private_refs/"))
                self.assertTrue(isinstance(record["request_keys"], list))
                self.assertTrue(isinstance(record["response_keys"], list))
                self.assertTrue(isinstance(record["error_keys"], list))
                self.assertTrue(isinstance(record["top_counts"], dict))
                self.assertFalse(forbidden_raw_keys & set(record))

        paths = [record["path"] for record in records]
        self.assertTrue(any("a1_python_api_calibration" in path or "/python_" in path for path in paths))
        self.assertTrue(any("a1_ts_api_calibration" in path or "/ts_" in path for path in paths))
        self.assertIn("create_request", payload["function_counts"])
        self.assertTrue(any(isinstance(record.get("quota"), dict) and record["quota"].get("blocked") is True for record in records))
        self.assertNotRegex(payload_text, re.compile(r"tp_[A-Za-z0-9_\\-]+"))
        self.assertNotIn("Bearer ", payload_text)
        self.assertNotRegex(payload_text, re.compile(r"[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}"))

    @staticmethod
    def _record_counts(records, key):
        return dict(sorted(Counter(str(record[key]) for record in records if record.get(key) is not None).items()))


if __name__ == "__main__":
    unittest.main()
