import json
import re
import unittest
from pathlib import Path

from services.judge.release_policy import select_release_policy
from services.judge.saas_control_plane import build_saas_control_plane_report


ROOT = Path(__file__).resolve().parents[2]
REPORT_FIXTURE = ROOT / "fixtures/a2/results/a2_saas_control_plane_report.json"
REPORT_SCHEMA = ROOT / "docs/a2/schemas/saas_control_plane.schema.json"
GRADE_REPORT = ROOT / "fixtures/a2/results/a2_g3_grade_results.json"
COVERAGE_REPORT = ROOT / "fixtures/a2/results/a2_g3_coverage_report.json"
CALIBRATION_MATRIX = ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json"
RELEASE_GATE = ROOT / "fixtures/a2/results/a2_release_gate_report.json"
SCENARIO_SELECTION = ROOT / "fixtures/a2/results/a2_scenario_selection_report.json"
RESULT_PERSISTENCE = ROOT / "fixtures/a2/results/a2_result_persistence_manifest.json"
RELEASE_POLICIES = ROOT / "fixtures/a2/config/release_policies.json"
JUDGE_VERSIONS = ROOT / "fixtures/a2/results/a2_judge_versions.json"
SCENARIO_GENERATION = ROOT / "fixtures/a2/results/a2_scenario_generation_backlog.json"

SECRET_PATTERNS = [
    re.compile("tp_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("ashr_live_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("sk-" + r"[A-Za-z0-9]"),
    re.compile("Bearer" + r"\\s+"),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class A2SaasControlPlaneTests(unittest.TestCase):
    def test_fixture_matches_builder(self):
        actual = build_saas_control_plane_report(
            grade_report=load_json(GRADE_REPORT),
            coverage_report=load_json(COVERAGE_REPORT),
            calibration_matrix=load_json(CALIBRATION_MATRIX),
            release_gate_report=load_json(RELEASE_GATE),
            scenario_selection_report=load_json(SCENARIO_SELECTION),
            result_persistence_manifest=load_json(RESULT_PERSISTENCE),
            release_policy_config=load_json(RELEASE_POLICIES),
            judge_version_registry=load_json(JUDGE_VERSIONS),
            scenario_generation_backlog=load_json(SCENARIO_GENERATION),
            source_refs={
                "grade_report": "fixtures/a2/results/a2_g3_grade_results.json",
                "coverage_report": "fixtures/a2/results/a2_g3_coverage_report.json",
                "calibration_matrix": "fixtures/a2/results/a2_g3_calibration_matrix.json",
                "release_gate": "fixtures/a2/results/a2_release_gate_report.json",
                "scenario_selection": "fixtures/a2/results/a2_scenario_selection_report.json",
                "release_unblock_checklist": "fixtures/a2/results/a2_release_unblock_checklist.json",
                "result_persistence": "fixtures/a2/results/a2_result_persistence_manifest.json",
                "judge_versions": "fixtures/a2/results/a2_judge_versions.json",
                "sql_store": "fixtures/a2/results/a2_sql_store_report.json",
                "scenario_generation": "fixtures/a2/results/a2_scenario_generation_backlog.json",
                "release_policy_config": "fixtures/a2/config/release_policies.json",
            },
        )

        self.assertEqual(actual, load_json(REPORT_FIXTURE))

    def test_schema_and_control_plane_contract_are_public_safe(self):
        report = load_json(REPORT_FIXTURE)
        schema = load_json(REPORT_SCHEMA)
        report_text = REPORT_FIXTURE.read_text(encoding="utf-8")

        self.assertEqual(schema["properties"]["schema_version"]["const"], report["schema_version"])
        self.assertLessEqual(set(schema["required"]), set(report))
        self.assertTrue(report["metadata"]["public_safe"])
        self.assertFalse(report["metadata"]["requires_network"])
        self.assertFalse(report["metadata"]["requires_ashr_api_key"])
        self.assertTrue(report["metadata"]["raw_private_evidence_not_recorded"])
        self.assertTrue(report["metadata"]["secrets_not_recorded"])

        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(report_text), pattern.pattern)

    def test_control_plane_exposes_saas_service_policy_selection_and_persistence(self):
        report = load_json(REPORT_FIXTURE)
        endpoint_paths = {endpoint["path"] for endpoint in report["service"]["endpoints"]}

        self.assertEqual(report["tenant"]["project_id"], "project_enterprise_saas_agent")
        self.assertEqual(report["tenant"]["environment"], "prod")
        self.assertTrue(report["tenant"]["tenant_scoped"])
        self.assertIn("/internal/judge/case", endpoint_paths)
        self.assertIn("/internal/judge/run", endpoint_paths)
        self.assertIn("/internal/judge/batch", endpoint_paths)
        self.assertIn("/internal/release-policy/evaluate", endpoint_paths)
        self.assertIn("/internal/release/unblock-checklist", endpoint_paths)
        self.assertIn("/internal/regression/replay", endpoint_paths)
        self.assertIn("/internal/calibration/evaluate", endpoint_paths)
        self.assertIn("/internal/scenarios/select", endpoint_paths)
        self.assertIn("/internal/results/persist", endpoint_paths)

        selected_policy = report["policy_config"]["selected_policy"]
        self.assertEqual(selected_policy["policy_id"], "release_policy_prod_strict")
        self.assertEqual(selected_policy["selection"]["match_scope"], "project_environment")
        self.assertTrue(selected_policy["policy_hash_valid"])
        self.assertTrue(report["policy_config"]["waiver_flow_supported"])

        self.assertEqual(report["release_gate"]["a3_action"], "block_release")
        self.assertTrue(report["release_gate"]["blocks_merge"])
        self.assertTrue(report["release_gate"]["needs_human_review"])
        self.assertTrue(report["release_gate"]["pr_gate"]["blocks_merge"])
        self.assertIn("fixtures/a2/results/a2_release_gate_report.json", report["release_gate"]["pr_gate"]["audit_artifacts"])

        self.assertTrue(report["result_persistence"]["public_safe"])
        self.assertTrue(report["result_persistence"]["ready_for_audit_export"])
        self.assertGreaterEqual(report["judge_versioning"]["judge_id_count"], 5)
        self.assertTrue(report["judge_versioning"]["all_records_have_policy_hash"])
        self.assertTrue(report["judge_versioning"]["all_records_have_input_hash"])
        self.assertTrue(report["judge_versioning"]["all_records_have_output_hash"])
        self.assertEqual(report["judge_version_registry"]["declared_judge_count"], 5)
        self.assertEqual(report["judge_version_registry"]["observed_judge_count"], 5)
        self.assertTrue(report["judge_version_registry"]["all_declared_judges_observed"])
        self.assertTrue(report["judge_version_registry"]["pinning_supported"])
        self.assertTrue(report["judge_version_registry"]["history_replay_supported"])
        self.assertIn("g1_trace_contract_judge@0.1.0", report["judge_version_registry"]["judge_pins"])
        self.assertEqual(report["scenario_generation"]["candidate_count"], 12)
        self.assertEqual(report["scenario_generation"]["policy_experiment_count"], 3)
        self.assertFalse(report["scenario_generation"]["may_mutate_main_pack"])
        self.assertIn("A2-GEN-001", report["scenario_generation"]["candidate_ids"])

    def test_a3_dashboard_contract_points_to_public_safe_a2_artifacts(self):
        report = load_json(REPORT_FIXTURE)
        contract = report["a3_dashboard_contract"]
        payload_keys = contract["recommended_payload_keys"]

        self.assertEqual(contract["consumer"], "A3 SaaS admin console")
        self.assertEqual(contract["status"], "ready_for_read_only_dashboard_consumption")
        self.assertFalse(contract["mutations_enabled"])
        self.assertEqual(payload_keys["a2ControlPlane"], "fixtures/a2/results/a2_saas_control_plane_report.json")
        self.assertEqual(payload_keys["resultPersistence"], "fixtures/a2/results/a2_result_persistence_manifest.json")
        self.assertEqual(payload_keys["judgeVersions"], "fixtures/a2/results/a2_judge_versions.json")
        self.assertEqual(payload_keys["sqlStore"], "fixtures/a2/results/a2_sql_store_report.json")
        self.assertEqual(
            payload_keys["scenarioGeneration"],
            "fixtures/a2/results/a2_scenario_generation_backlog.json",
        )
        self.assertEqual(
            payload_keys["releaseUnblockChecklist"],
            "fixtures/a2/results/a2_release_unblock_checklist.json",
        )
        self.assertIn("judge version and policy hash audit", contract["dashboard_can_show"])
        self.assertIn("judge registry pins and migration readiness", contract["dashboard_can_show"])
        self.assertIn("release unblock checklist owner actions", contract["dashboard_can_show"])
        self.assertIn("SQL-readable eval/calibration/golden/regression history", contract["dashboard_can_show"])
        self.assertIn("reviewable scenario generation backlog and policy experiments", contract["dashboard_can_show"])
        self.assertIn("private_input_ref", contract["private_fields_forbidden"])
        self.assertGreaterEqual(contract["local_meter"]["grade_case_count"], 30)
        self.assertEqual(contract["local_meter"]["scenario_generation_candidate_count"], 12)
        self.assertEqual(contract["selected_policy_id"], "release_policy_prod_strict")

    def test_release_policy_config_selects_saas_project_without_falling_back(self):
        policy, selection = select_release_policy(
            load_json(RELEASE_POLICIES),
            project_id="project_enterprise_saas_agent",
            environment="prod",
        )

        self.assertEqual(policy["policy_id"], "release_policy_prod_strict")
        self.assertEqual(selection["assignment_id"], "project_enterprise_saas_agent_prod")
        self.assertEqual(selection["match_scope"], "project_environment")


if __name__ == "__main__":
    unittest.main()
