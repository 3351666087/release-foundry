import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from services.judge.service_wrapper import (
    BATCH_ENDPOINT,
    CALIBRATION_EVALUATE_ENDPOINT,
    CASE_ENDPOINT,
    REGRESSION_REPLAY_ENDPOINT,
    RELEASE_POLICY_ENDPOINT,
    RUN_ENDPOINT,
    SCENARIO_SELECT_ENDPOINT,
    handle_internal_request,
    post_internal_calibration_evaluate,
    post_internal_judge_batch,
    post_internal_judge_case,
    post_internal_judge_run,
    post_internal_regression_replay,
    post_internal_release_policy_evaluate,
    post_internal_scenarios_select,
)


ROOT = Path(__file__).resolve().parents[2]


class A2JudgeServiceWrapperTests(unittest.TestCase):
    def test_case_endpoint_grades_single_case_without_external_api(self):
        response = post_internal_judge_case(
            {
                "request_id": "svc-case-smoke",
                "tenant_id": "tenant_demo",
                "project_id": "proj_demo",
                "run_id": "run_demo",
                "scenario_id": "A2-S001",
                "case_id": "svc-a2-s001-pass",
                "run": {
                    "tool_calls": [],
                    "final_response": "I need a little more information before I can complete your request.",
                },
            }
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], CASE_ENDPOINT)
        self.assertEqual(response["status_code"], 200)
        self.assertFalse(response["metadata"]["requires_ashr_api_key"])
        self.assertFalse(response["metadata"]["requires_network"])
        self.assertTrue(response["result"]["passed"])
        self.assertEqual(response["result"]["primary_failure_class"], "none")
        self.assertEqual(len(response["result"]["judge_results"]), 5)
        self.assertEqual(response["service_context"]["tenant_id"], "tenant_demo")
        self.assertEqual(response["service_context"]["project_id"], "proj_demo")
        self.assertEqual(response["service_context"]["run_id"], "run_demo")

    def test_batch_endpoint_grades_multiple_cases(self):
        pass_case = json.loads((ROOT / "fixtures/a2/runs/a2_s001_pass.json").read_text(encoding="utf-8"))
        fail_case = json.loads((ROOT / "fixtures/a2/runs/a2_s004_missing_tool.json").read_text(encoding="utf-8"))

        response = post_internal_judge_batch(
            {
                "request_id": "svc-batch-smoke",
                "tenant_id": "tenant_demo",
                "project_id": "proj_demo",
                "run_id": "run_batch_demo",
                "dataset_id": "svc-dataset",
                "report_id": "svc-report",
                "cases": [pass_case, fail_case],
            }
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], BATCH_ENDPOINT)
        self.assertEqual(response["result"]["schema_version"], "a2.grade_results.v1")
        self.assertEqual(response["result"]["total_cases"], 2)
        self.assertEqual(response["result"]["passed"], 1)
        self.assertEqual(response["result"]["failed"], 1)
        failure_classes = {item["primary_failure_class"] for item in response["result"]["grade_results"]}
        self.assertIn("missing_required_tool", failure_classes)

    def test_run_endpoint_grades_run_cases_with_summary(self):
        pass_case = json.loads((ROOT / "fixtures/a2/runs/a2_s001_pass.json").read_text(encoding="utf-8"))
        fail_case = json.loads((ROOT / "fixtures/a2/runs/a2_s004_missing_tool.json").read_text(encoding="utf-8"))

        response = post_internal_judge_run(
            {
                "request_id": "svc-run-smoke",
                "tenant_id": "tenant_demo",
                "project_id": "proj_demo",
                "run_id": "run_service_demo",
                "cases": [pass_case, fail_case],
            }
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], RUN_ENDPOINT)
        self.assertEqual(response["result"]["schema_version"], "a2.judge_service.run_response.v1")
        self.assertEqual(response["result"]["total_cases"], 2)
        self.assertEqual(response["result"]["passed"], 1)
        self.assertEqual(response["result"]["failed"], 1)
        self.assertEqual(response["result"]["run_summary"]["pass_rate"], 50.0)
        self.assertEqual(response["result"]["run_summary"]["primary_failure_class_counts"]["none"], 1)
        self.assertEqual(
            response["result"]["run_summary"]["primary_failure_class_counts"]["missing_required_tool"],
            1,
        )

    def test_release_policy_endpoint_wraps_existing_gate_report(self):
        response = post_internal_release_policy_evaluate(
            {
                "request_id": "svc-release-smoke",
                "tenant_id": "tenant_demo",
                "project_id": "proj_demo",
                "release_candidate_id": "agent-v42",
                "policy_id": "strict-commercial",
            }
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], RELEASE_POLICY_ENDPOINT)
        self.assertEqual(response["result"]["schema_version"], "a2.release_gate.v1")
        self.assertIn(response["result"]["decision"], {"pass", "warn", "block"})
        self.assertEqual(response["service_context"]["tenant_id"], "tenant_demo")
        self.assertEqual(response["service_context"]["release_candidate_id"], "agent-v42")
        self.assertFalse(response["metadata"]["does_not_execute_live_calls"] is False)

    def test_release_policy_endpoint_applies_public_waiver(self):
        grade_results = [
            {
                "schema_version": "a2.local_judge_run.v1",
                "scenario_id": "A2-S001",
                "case_id": f"pass-{index}",
                "passed": True,
                "score": 100.0,
                "primary_failure_class": "none",
                "judge_results": [],
            }
            for index in range(99)
        ]
        grade_results.append(
            {
                "schema_version": "a2.local_judge_run.v1",
                "scenario_id": "A2-S012",
                "case_id": "safety-failure",
                "passed": False,
                "score": 70.0,
                "primary_failure_class": "unsafe_or_policy_violation",
                "judge_results": [],
            }
        )

        response = post_internal_release_policy_evaluate(
            {
                "request_id": "svc-release-waiver",
                "tenant_id": "tenant_enterprise",
                "project_id": "project_enterprise",
                "environment": "prod",
                "release_candidate_id": "agent-v42",
                "grade_report": {
                    "schema_version": "a2.grade_results.v1",
                    "report_id": "svc-waiver-report",
                    "dataset_id": "svc-waiver",
                    "scenario_pack": "unit",
                    "total_cases": len(grade_results),
                    "passed": 99,
                    "failed": 1,
                    "grade_results": grade_results,
                },
                "waivers": [
                    {
                        "waiver_id": "wv-service-public",
                        "approval_id": "approval-service-public",
                        "status": "approved",
                        "rule_id": "prod_no_safety_policy_violations",
                        "project_id": "project_enterprise",
                        "environment": "prod",
                        "release_candidate_id": "agent-v42",
                        "reviewer": "release-manager",
                        "reason": "Reviewed through service wrapper contract.",
                        "evidence_ref": "docs/evidence/private_refs/service-waiver.json",
                    }
                ],
            }
        )

        self.assertTrue(response["ok"])
        policy_evaluation = response["result"]["policy_evaluation"]
        self.assertEqual(policy_evaluation["decision"], "pass")
        self.assertEqual(policy_evaluation["waiver_summary"]["applied_count"], 1)
        self.assertEqual(policy_evaluation["waiver_summary"]["waived_blocking_count"], 1)

    def test_release_policy_endpoint_passes_branch_and_approvals(self):
        grade_results = [
            {
                "schema_version": "a2.local_judge_run.v1",
                "scenario_id": "A2-S001",
                "case_id": f"pass-{index}",
                "passed": True,
                "score": 100.0,
                "primary_failure_class": "none",
                "judge_results": [],
            }
            for index in range(99)
        ]
        grade_results.append(
            {
                "schema_version": "a2.local_judge_run.v1",
                "scenario_id": "A2-S012",
                "case_id": "prod-main-safety-failure",
                "passed": False,
                "score": 70.0,
                "primary_failure_class": "unsafe_or_policy_violation",
                "judge_results": [],
            }
        )

        response = post_internal_release_policy_evaluate(
            {
                "request_id": "svc-release-approval",
                "tenant_id": "tenant_enterprise",
                "project_id": "project_enterprise",
                "environment": "prod",
                "branch": "main",
                "release_candidate_id": "agent-v43",
                "grade_report": {
                    "schema_version": "a2.grade_results.v1",
                    "report_id": "svc-approval-report",
                    "dataset_id": "svc-approval",
                    "scenario_pack": "unit",
                    "total_cases": len(grade_results),
                    "passed": 99,
                    "failed": 1,
                    "grade_results": grade_results,
                },
                "waivers": [
                    {
                        "waiver_id": "wv-prod-main-safety",
                        "approval_id": "approval-waiver-ref",
                        "status": "approved",
                        "rule_id": "prod_no_safety_policy_violations",
                        "project_id": "project_enterprise",
                        "environment": "prod",
                        "branch": "main",
                        "release_candidate_id": "agent-v43",
                        "reviewer": "release-manager",
                        "reason": "Reviewed production main safety fixture.",
                        "evidence_ref": "docs/evidence/private_refs/prod-main-waiver.json",
                    }
                ],
                "approvals": [
                    {
                        "approval_id": "approval-prod-main-exception",
                        "approval_type": "release_exception",
                        "status": "approved",
                        "project_id": "project_enterprise",
                        "environment": "prod",
                        "branch": "main",
                        "release_candidate_id": "agent-v43",
                        "approver": "release-manager",
                        "reason": "Reviewed production main release exception.",
                        "evidence_ref": "docs/evidence/private_refs/prod-main-exception.json",
                    }
                ],
            }
        )

        self.assertTrue(response["ok"])
        policy_evaluation = response["result"]["policy_evaluation"]
        self.assertEqual(policy_evaluation["selection"]["assignment_id"], "project_enterprise_main_prod")
        self.assertEqual(policy_evaluation["selection"]["match_scope"], "project_environment_branch")
        self.assertEqual(policy_evaluation["branch"], "main")
        self.assertEqual(policy_evaluation["decision"], "pass")
        self.assertEqual(policy_evaluation["waiver_summary"]["applied_count"], 1)
        self.assertEqual(policy_evaluation["approval_summary"]["status"], "approved")
        self.assertEqual(policy_evaluation["approval_summary"]["applied_count"], 1)
        self.assertEqual(policy_evaluation["applied_approvals"][0]["approval_id"], "approval-prod-main-exception")
        self.assertIn("waiver_applied", policy_evaluation["decision_evidence"]["approval_triggers"])

    def test_regression_replay_endpoint_returns_replay_report(self):
        response = post_internal_regression_replay(
            {
                "request_id": "svc-regression-replay",
                "tenant_id": "tenant_demo",
                "project_id": "proj_demo",
                "run_id": "run_regression_demo",
            }
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], REGRESSION_REPLAY_ENDPOINT)
        self.assertEqual(response["result"]["schema_version"], "a2.regression_replay.v1")
        self.assertIn("replay_ready", response["result"])
        self.assertIn("maturity_gate", response["result"])

    def test_calibration_evaluate_endpoint_returns_public_matrix(self):
        response = post_internal_calibration_evaluate(
            {
                "request_id": "svc-calibration",
                "tenant_id": "tenant_demo",
                "project_id": "proj_demo",
                "run_id": "run_calibration_demo",
            }
        )

        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], CALIBRATION_EVALUATE_ENDPOINT)
        self.assertEqual(response["result"]["schema_version"], "a2.calibration_matrix.v1")
        self.assertEqual(response["result"]["case_count"], 6)
        self.assertEqual(response["result"]["source_coverage"]["local_judge"]["available"], 6)
        self.assertIn("ashr_grading", response["result"]["source_coverage"])

    def test_scenarios_select_endpoint_returns_a3_ready_project_selection(self):
        payload = {
            "request_id": "svc-scenarios-select",
            "tenant_id": "tenant_demo",
            "project_id": "proj_enterprise_support",
            "environment": "prod",
        }

        response = post_internal_scenarios_select(payload)
        dispatched = handle_internal_request(SCENARIO_SELECT_ENDPOINT, payload, method="POST")

        self.assertTrue(response["ok"])
        self.assertTrue(dispatched["ok"])
        self.assertEqual(response["endpoint"], SCENARIO_SELECT_ENDPOINT)
        self.assertEqual(dispatched["endpoint"], SCENARIO_SELECT_ENDPOINT)
        self.assertEqual(response["service_context"]["tenant_id"], "tenant_demo")
        result = response["result"]
        self.assertEqual(result["schema_version"], "a2.project_scenario_selection.v1")
        self.assertIn("tenant_id", result["tenant"])
        self.assertEqual(result["project"]["project_id"], "proj_enterprise_support")
        self.assertEqual(result["environment"], "prod")
        self.assertTrue(result["minimums_summary"]["minimums_ready"])
        self.assertEqual(result["a3_consumption_summary"]["scenario_count"], result["selected_count"])

    def test_dispatcher_rejects_unknown_internal_route(self):
        response = handle_internal_request("/internal/judge/unknown", {}, method="POST")

        self.assertFalse(response["ok"])
        self.assertEqual(response["status_code"], 404)
        self.assertEqual(response["error"]["code"], "route_not_found")

    def test_cli_exposes_case_endpoint(self):
        payload = {
            "scenario_id": "A2-S001",
            "case_id": "cli-a2-s001-pass",
            "run": {
                "tool_calls": [],
                "final_response": "I need a little more information before I can complete your request.",
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "payload.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/a2_judge_service.py"),
                    "/internal/judge/case",
                    "--input",
                    str(input_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        response = json.loads(result.stdout)
        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], CASE_ENDPOINT)
        self.assertEqual(response["result"]["case_id"], "cli-a2-s001-pass")

    def test_cli_exposes_calibration_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "payload.json"
            input_path.write_text(json.dumps({"request_id": "cli-calibration"}), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/a2_judge_service.py"),
                    CALIBRATION_EVALUATE_ENDPOINT,
                    "--input",
                    str(input_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        response = json.loads(result.stdout)
        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], CALIBRATION_EVALUATE_ENDPOINT)
        self.assertEqual(response["result"]["schema_version"], "a2.calibration_matrix.v1")

    def test_cli_exposes_scenarios_select_endpoint(self):
        payload = {
            "request_id": "cli-scenarios-select",
            "project_id": "proj_enterprise_support",
            "environment": "prod",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "payload.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/a2_judge_service.py"),
                    SCENARIO_SELECT_ENDPOINT,
                    "--input",
                    str(input_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        response = json.loads(result.stdout)
        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], SCENARIO_SELECT_ENDPOINT)
        self.assertEqual(response["result"]["schema_version"], "a2.project_scenario_selection.v1")
        self.assertEqual(response["result"]["project"]["project_id"], "proj_enterprise_support")


if __name__ == "__main__":
    unittest.main()
