import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from services.judge.service_wrapper import (
    BATCH_ENDPOINT,
    CASE_ENDPOINT,
    RELEASE_POLICY_ENDPOINT,
    handle_internal_request,
    post_internal_judge_batch,
    post_internal_judge_case,
    post_internal_release_policy_evaluate,
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


if __name__ == "__main__":
    unittest.main()
