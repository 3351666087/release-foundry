import json
import subprocess
import sys
import unittest
from pathlib import Path

from services.judge.scenario_selection import (
    build_project_scenario_selection,
    build_scenario_selection_report,
)


ROOT = Path(__file__).resolve().parents[2]


class ScenarioSelectionSaaSContractTests(unittest.TestCase):
    def test_report_exposes_tenant_policy_minimums_and_a3_summary(self):
        profile = json.loads((ROOT / "fixtures/a2/config/a2_saas_project_selection_profile.json").read_text(encoding="utf-8"))

        report = build_scenario_selection_report(
            profile,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        selected_ids = {scenario["scenario_id"] for scenario in report["selected_scenarios"]}

        self.assertEqual(report["tenant"]["tenant_id"], "tenant_enterprise_saas")
        self.assertEqual(report["project"]["project_id"], "project_enterprise_saas_agent")
        self.assertEqual(report["environment"], "prod")
        self.assertEqual(report["policy_profile"]["policy_id"], "release_policy_enterprise_prod")
        self.assertEqual(report["policy_profile"]["blocking_mode"], "block_on_critical")
        self.assertTrue(report["coverage_summary"]["coverage_ready"])
        self.assertTrue(report["minimums_summary"]["minimums_ready"])
        self.assertGreaterEqual(report["minimums_summary"]["observed"]["golden_case_count"], 4)
        self.assertGreaterEqual(report["minimums_summary"]["observed"]["failure_class_count"], 6)
        self.assertGreaterEqual(report["minimums_summary"]["observed"]["regression_case_count"], 1)
        self.assertIn("A2-S041", selected_ids)
        self.assertIn("A2-S031", report["coverage_summary"]["media_scenario_ids"])
        self.assertEqual(
            report["a3_consumption_summary"]["release_gate_inputs"]["policy_id"],
            "release_policy_enterprise_prod",
        )
        self.assertEqual(
            report["a3_consumption_summary"]["tenant_project_environment"]["tenant"]["tenant_id"],
            "tenant_enterprise_saas",
        )

    def test_project_selection_uses_config_profile_for_prod(self):
        config = json.loads((ROOT / "fixtures/a2/config/a2_project_scenario_selection.json").read_text(encoding="utf-8"))

        selection = build_project_scenario_selection(
            project_id="proj_enterprise_support",
            environment="prod",
            selection_config=config,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        self.assertEqual(selection["schema_version"], "a2.project_scenario_selection.v1")
        self.assertEqual(selection["profile_id"], "profile_enterprise_prod")
        self.assertEqual(selection["policy_profile"]["environment"], "prod")
        self.assertTrue(selection["coverage_summary"]["coverage_ready"])
        self.assertTrue(selection["minimums_summary"]["minimums_ready"])
        self.assertGreaterEqual(selection["coverage_summary"]["required_tag_counts"]["enterprise-saas"], 4)
        self.assertGreaterEqual(selection["coverage_summary"]["requested_capability_axis_counts"]["media_and_multimodal"], 1)
        self.assertEqual(
            selection["a3_consumption_summary"]["scenario_count"],
            selection["selected_count"],
        )

    def test_cli_can_emit_project_selection_contract(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/a2_select_scenario_pack.py"),
                "--selection-config",
                "fixtures/a2/config/a2_project_scenario_selection.json",
                "--project-id",
                "proj_enterprise_support",
                "--environment",
                "prod",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], "a2.project_scenario_selection.v1")
        self.assertEqual(payload["project_id"], "proj_enterprise_support")
        self.assertEqual(payload["a3_consumption_summary"]["policy_profile"]["release_gate_decision"], "eligible")


if __name__ == "__main__":
    unittest.main()
