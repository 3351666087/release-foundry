import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from services.judge.service_wrapper import (
    A1_RELEASE_GATE_CONTRACT,
    BATCH_ENDPOINT,
    CALIBRATION_EVALUATE_ENDPOINT,
    CASE_ENDPOINT,
    REGRESSION_REPLAY_ENDPOINT,
    RELEASE_UNBLOCK_CHECKLIST_ENDPOINT,
    RELEASE_POLICY_ENDPOINT,
    RESULTS_PERSIST_ENDPOINT,
    RUN_ENDPOINT,
    SCENARIO_SELECT_ENDPOINT,
    SERVICE_VERSION,
    handle_internal_request,
    post_internal_calibration_evaluate,
    post_internal_judge_batch,
    post_internal_judge_case,
    post_internal_judge_run,
    post_internal_regression_replay,
    post_internal_release_unblock_checklist,
    post_internal_release_policy_evaluate,
    post_internal_results_persist,
    post_internal_scenarios_select,
)


ROOT = Path(__file__).resolve().parents[2]
OPENAPI_CONTRACT = ROOT / "docs/a2/openapi/a2_judge_service.openapi.json"


class A2JudgeServiceWrapperTests(unittest.TestCase):
    def test_openapi_contract_tracks_service_wrapper_routes(self):
        contract = json.loads(OPENAPI_CONTRACT.read_text(encoding="utf-8"))
        expected_routes = {
            CASE_ENDPOINT: "post_internal_judge_case",
            RUN_ENDPOINT: "post_internal_judge_run",
            BATCH_ENDPOINT: "post_internal_judge_batch",
            RELEASE_POLICY_ENDPOINT: "post_internal_release_policy_evaluate",
            RELEASE_UNBLOCK_CHECKLIST_ENDPOINT: "post_internal_release_unblock_checklist",
            REGRESSION_REPLAY_ENDPOINT: "post_internal_regression_replay",
            CALIBRATION_EVALUATE_ENDPOINT: "post_internal_calibration_evaluate",
            SCENARIO_SELECT_ENDPOINT: "post_internal_scenarios_select",
            RESULTS_PERSIST_ENDPOINT: "post_internal_results_persist",
        }
        expected_response_refs = {
            endpoint: "#/components/responses/InternalServiceEnvelope" for endpoint in expected_routes
        }
        expected_response_refs[REGRESSION_REPLAY_ENDPOINT] = (
            "#/components/responses/RegressionReplayServiceEnvelope"
        )
        expected_response_refs[RELEASE_UNBLOCK_CHECKLIST_ENDPOINT] = (
            "#/components/responses/ReleaseUnblockChecklistServiceEnvelope"
        )

        self.assertEqual(contract["openapi"], "3.1.0")
        self.assertEqual(contract["info"]["version"], SERVICE_VERSION)
        self.assertEqual(set(contract["paths"]), set(expected_routes))
        for endpoint, operation_id in expected_routes.items():
            with self.subTest(endpoint=endpoint):
                operation = contract["paths"][endpoint]["post"]
                self.assertEqual(operation["operationId"], operation_id)
                self.assertEqual(
                    operation["x-a2"]["implementation"],
                    f"services.judge.service_wrapper.{operation_id}",
                )
                self.assertEqual(operation["x-a2"]["service_version"], SERVICE_VERSION)
                self.assertTrue(operation["x-a2"]["pure_function_only"])
                self.assertFalse(operation["x-a2"]["requires_network"])
                self.assertFalse(operation["x-a2"]["requires_releasefoundry_api_key"])
                self.assertEqual(
                    operation["responses"]["200"]["$ref"],
                    expected_response_refs[endpoint],
                )

        boundary = contract["x-a2-boundary"]
        self.assertEqual(boundary["implementation_language"], "Python")
        self.assertFalse(boundary["hosted_server_in_scope"])
        self.assertTrue(boundary["sql_in_scope"])
        self.assertIn("sqlite reference adapter", boundary["sql_scope"])
        self.assertFalse(boundary["typescript_runtime_in_scope"])
        envelope = contract["components"]["schemas"]["InternalServiceEnvelope"]
        self.assertEqual(
            envelope["properties"]["grade_result"]["$ref"],
            "#/components/schemas/A1ReleaseGateBridgeGradeResult",
        )
        bridge_grade = contract["components"]["schemas"]["A1ReleaseGateBridgeGradeResult"]
        self.assertEqual(
            bridge_grade["properties"]["schema_version"]["const"],
            "a2.a1_release_gate_bridge_grade_result.v1",
        )
        for field in ("scenario_id", "passed", "score", "label", "reason", "expected", "actual", "metrics"):
            self.assertIn(field, bridge_grade["required"])
        serialized = json.dumps(contract, sort_keys=True)
        self.assertNotIn("docs/evidence/private_refs", serialized)
        self.assertNotIn("Bearer ", serialized)
        self.assertNotIn("releasefoundry_live_", serialized)

    def test_openapi_contract_covers_regression_replay_release_gate_summary(self):
        contract = json.loads(OPENAPI_CONTRACT.read_text(encoding="utf-8"))
        response_ref = contract["paths"][REGRESSION_REPLAY_ENDPOINT]["post"]["responses"]["200"]["$ref"]
        replay_envelope = contract["components"]["schemas"]["RegressionReplayServiceEnvelope"]
        replay_report = contract["components"]["schemas"]["RegressionReplayReport"]
        release_summary = contract["components"]["schemas"]["RegressionReplayReleaseGateSummary"]

        self.assertEqual(response_ref, "#/components/responses/RegressionReplayServiceEnvelope")
        self.assertEqual(
            replay_envelope["allOf"][1]["properties"]["result"]["$ref"],
            "#/components/schemas/RegressionReplayReport",
        )
        self.assertIn("release_gate_summary", replay_report["required"])
        self.assertEqual(
            replay_report["properties"]["release_gate_summary"]["$ref"],
            "#/components/schemas/RegressionReplayReleaseGateSummary",
        )
        self.assertEqual(
            release_summary["properties"]["schema_version"]["const"],
            "a2.regression_replay.release_gate_summary.v1",
        )
        self.assertEqual(release_summary["properties"]["gate"]["const"], "C5")
        for field in (
            "blocks_release",
            "action",
            "required_action",
            "blocking_count",
            "current_replay_case_count",
            "target_replay_case_count",
            "gaps",
            "evidence_refs",
        ):
            self.assertIn(field, release_summary["required"])

    def test_openapi_contract_covers_release_unblock_checklist(self):
        contract = json.loads(OPENAPI_CONTRACT.read_text(encoding="utf-8"))
        response_ref = contract["paths"][RELEASE_UNBLOCK_CHECKLIST_ENDPOINT]["post"]["responses"]["200"]["$ref"]
        envelope = contract["components"]["schemas"]["ReleaseUnblockChecklistServiceEnvelope"]
        checklist = contract["components"]["schemas"]["ReleaseUnblockChecklist"]
        action_item = contract["components"]["schemas"]["ReleaseUnblockActionItem"]

        self.assertEqual(response_ref, "#/components/responses/ReleaseUnblockChecklistServiceEnvelope")
        self.assertEqual(
            envelope["allOf"][1]["properties"]["result"]["$ref"],
            "#/components/schemas/ReleaseUnblockChecklist",
        )
        self.assertEqual(checklist["properties"]["schema_version"]["const"], "a2.release_unblock_checklist.v1")
        for field in (
            "overall_status",
            "blocked_gate_count",
            "gate_items",
            "a3_consumption_summary",
            "metadata",
        ):
            self.assertIn(field, checklist["required"])
        self.assertIn("required_evidence_source", action_item["required"])
        self.assertIn("private_evidence_required", action_item["required"])

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
        self.assertFalse(response["metadata"]["requires_releasefoundry_api_key"])
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
        self.assertEqual(response["result"]["a3_release_gate_summary"]["schema_version"], "a2.a3_release_gate_summary.v1")
        self.assertIn(
            response["result"]["a3_release_gate_summary"]["action"],
            {"approve_release", "needs_review", "block_release"},
        )
        self.assertIn("pr_gate", response["result"]["a3_release_gate_summary"])
        self.assertEqual(response["service_context"]["tenant_id"], "tenant_demo")
        self.assertEqual(response["service_context"]["release_candidate_id"], "agent-v42")
        self.assertFalse(response["metadata"]["does_not_execute_live_calls"] is False)

    def test_release_policy_endpoint_accepts_a1_release_gate_bridge_contract(self):
        payload = {
            "schema_version": "releasefoundry.saas_control_plane.v1",
            "request_id": "req-a1-bridge",
            "idempotency_key": "idem-a1-bridge",
            "tenant_id": "tenant_bridge",
            "project_id": "project_bridge",
            "run_id": "run_bridge",
            "target_contract": A1_RELEASE_GATE_CONTRACT,
            "decision_hint": "pass",
            "policy": {
                "minimum_uploads": 1,
                "minimum_trace_batches": 1,
                "api_key": "secret_should_not_persist",
            },
            "inputs": {
                "run_status": "completed",
                "upload_count": 1,
                "trace_batch_count": 1,
                "authorization": "redacted credential secret_should_not_persist",
            },
            "raw_payload_included": False,
        }

        response = post_internal_release_policy_evaluate(payload)
        dispatched = handle_internal_request(RELEASE_POLICY_ENDPOINT, payload)

        self.assertTrue(response["ok"])
        self.assertEqual(response, dispatched)
        self.assertEqual(response["endpoint"], RELEASE_POLICY_ENDPOINT)
        self.assertEqual(response["request_id"], "req-a1-bridge")
        result = response["result"]
        self.assertEqual(response["grade_result"], result)
        self.assertEqual(result["schema_version"], "a2.a1_release_gate_bridge_grade_result.v1")
        self.assertEqual(result["scenario_id"], "run_bridge")
        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 1.0)
        self.assertEqual(result["label"], "release_gate_pass")
        self.assertEqual(result["expected"]["target_contract"], A1_RELEASE_GATE_CONTRACT)
        self.assertEqual(result["expected"]["minimum_uploads"], 1)
        self.assertEqual(result["expected"]["minimum_trace_batches"], 1)
        self.assertEqual(result["actual"]["upload_count"], 1)
        self.assertEqual(result["actual"]["trace_batch_count"], 1)
        self.assertFalse(result["actual"]["raw_payload_included"])
        self.assertTrue(result["metrics"]["a1_bridge_compatible"])
        serialized = json.dumps(response, sort_keys=True)
        self.assertNotIn("secret_should_not_persist", serialized)
        self.assertNotIn("Bearer", serialized)
        for field in ("scenario_id", "passed", "score", "label", "reason", "expected", "actual", "metrics"):
            self.assertIn(field, result)

    def test_release_policy_endpoint_marks_a1_bridge_review_when_lifecycle_counts_miss_policy(self):
        response = post_internal_release_policy_evaluate(
            {
                "request_id": "req-a1-bridge-review",
                "tenant_id": "tenant_bridge",
                "project_id": "project_bridge",
                "run_id": "run_bridge_review",
                "target_contract": A1_RELEASE_GATE_CONTRACT,
                "decision_hint": "review",
                "policy": {"minimum_uploads": 1, "minimum_trace_batches": 1},
                "inputs": {"run_status": "running", "upload_count": 1, "trace_batch_count": 0},
                "raw_payload_included": False,
            }
        )

        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertFalse(result["passed"])
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["label"], "release_gate_review")
        self.assertEqual(result["actual"]["trace_batch_count"], 0)

    def test_release_policy_endpoint_applies_a1_output_policy_gate(self):
        evidence_index = json.loads((ROOT / "docs/a1/api_calibration/real_api_evidence_index.json").read_text(encoding="utf-8"))
        evidence_index["output_policy_counts"] = {
            **evidence_index["output_policy_counts"],
            "unsafe_real_nonprivate_override": 1,
            "private_required_but_not_private": 0,
        }

        response = post_internal_release_policy_evaluate(
            {
                "request_id": "svc-release-a1-output-policy",
                "tenant_id": "tenant_demo",
                "project_id": "project_enterprise",
                "environment": "prod",
                "release_candidate_id": "agent-v44",
                "a1_evidence_index": evidence_index,
            }
        )

        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertEqual(result["a1_output_policy_gate"]["status"], "blocked")
        self.assertEqual(result["a1_output_policy_blocker_count"], 1)
        self.assertTrue(any(item["type"] == "a1_output_policy_gate" for item in result["blockers"]))
        self.assertTrue(result["a3_release_gate_summary"]["blocks_merge"])
        self.assertTrue(
            any(item["id"] == "A1-OUTPUT-POLICY" for item in result["a3_release_gate_summary"]["failed_checks"])
        )

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
        self.assertEqual(response["result"]["a3_release_gate_summary"]["action"], "block_release")
        self.assertTrue(response["result"]["a3_release_gate_summary"]["blocks_merge"])

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
        self.assertEqual(response["result"]["a3_release_gate_summary"]["action"], "block_release")

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
        summary = response["result"]["release_gate_summary"]
        self.assertEqual(summary["schema_version"], "a2.regression_replay.release_gate_summary.v1")
        self.assertEqual(summary["gate"], "C5")
        self.assertIn(
            summary["action"],
            {"fix_failed_replays", "promote_more_regressions", "attach_reviewed_evidence", "ready"},
        )
        self.assertIn("blocks_release", summary)
        self.assertIn("evidence_refs", summary)

    def test_release_unblock_checklist_endpoint_returns_a3_ready_actions(self):
        payload = {
            "request_id": "svc-release-unblock",
            "tenant_id": "tenant_demo",
            "project_id": "proj_demo",
            "run_id": "run_release_unblock_demo",
        }
        response = post_internal_release_unblock_checklist(payload)
        dispatched = handle_internal_request(RELEASE_UNBLOCK_CHECKLIST_ENDPOINT, payload)

        self.assertTrue(response["ok"])
        self.assertEqual(response, dispatched)
        self.assertEqual(response["endpoint"], RELEASE_UNBLOCK_CHECKLIST_ENDPOINT)
        result = response["result"]
        self.assertEqual(result["schema_version"], "a2.release_unblock_checklist.v1")
        self.assertEqual(result["overall_status"], "blocked")
        self.assertEqual(result["blocked_gate_count"], 3)
        gates = {item["gate"]: item for item in result["gate_items"]}
        self.assertEqual(set(gates), {"C3", "C4", "C5"})
        self.assertEqual(gates["C3"]["required_actions"][0]["required_evidence_source"], "reviewed_releasefoundry_grading")
        self.assertEqual(gates["C4"]["required_actions"][0]["required_evidence_source"], "audited_semantic_judge")
        self.assertEqual(gates["C5"]["required_actions"][0]["required_evidence_source"], "reviewed_regression_replay")
        self.assertEqual(
            result["a3_consumption_summary"]["evidence_refs"],
            ["fixtures/a2/results/a2_release_unblock_checklist.json"],
        )
        serialized = json.dumps(response, sort_keys=True)
        self.assertNotIn("Bearer ", serialized)
        self.assertNotIn("releasefoundry_live_", serialized)

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
        self.assertIn("releasefoundry_grading", response["result"]["source_coverage"])

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

    def test_results_persist_endpoint_records_a1_ingestion_digest_without_raw_payload(self):
        payload = {
            "request_id": "svc-results-persist-a1",
            "tenant_id": "tenant_enterprise",
            "project_id": "project_enterprise",
            "run_id": "run_a1_upload",
            "created_at": "2026-07-07T00:00:00Z",
            "a1_ingestion": {
                "schema_version": "releasefoundry.saas_control_plane.v1",
                "operation": "run-upload",
                "upload_id": "upload_123",
                "batch_id": "batch_456",
                "trace_batch_id": "trace_batch_789",
                "payload_sha256": "abc123",
                "trace_batch_sha256": "def456",
                "payload_keys": ["run_id", "case_results", "trace_events"],
                "raw_payload_included": False,
                "raw_payload": {
                    "api_key": "fake_api_key_should_not_persist",
                    "private_ref": "private://a1-raw-upload.json",
                },
            },
        }

        response = post_internal_results_persist(payload)

        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], RESULTS_PERSIST_ENDPOINT)
        result = response["result"]
        self.assertEqual(result["schema_version"], "a2.judge_service.result_persistence_response.v1")
        self.assertEqual(result["record_type_counts"], {"a1_ingestion_digest": 1})
        record = result["records"][0]
        self.assertEqual(record["record_type"], "a1_ingestion_digest")
        self.assertEqual(record["tenant_id"], "tenant_enterprise")
        self.assertEqual(record["project"], "project_enterprise")
        self.assertEqual(record["run"], "run_a1_upload")
        self.assertEqual(record["output_summary"]["upload_id"], "upload_123")
        self.assertEqual(record["output_summary"]["batch_id"], "batch_456")
        self.assertEqual(record["output_summary"]["trace_batch_id"], "trace_batch_789")
        self.assertEqual(record["output_summary"]["payload_sha256"], "abc123")
        self.assertEqual(record["output_summary"]["trace_batch_sha256"], "def456")
        self.assertEqual(record["output_summary"]["payload_keys"], ["run_id", "case_results", "trace_events"])
        self.assertFalse(record["output_summary"]["raw_payload_included"])

        serialized = json.dumps(response, sort_keys=True)
        self.assertNotIn("fake_api_key_should_not_persist", serialized)
        self.assertNotIn("private://a1-raw-upload.json", serialized)
        self.assertNotIn('"raw_payload"', serialized)

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

    def test_cli_exposes_release_unblock_checklist_endpoint(self):
        payload = {"request_id": "cli-release-unblock"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "payload.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/a2_judge_service.py"),
                    RELEASE_UNBLOCK_CHECKLIST_ENDPOINT,
                    "--input",
                    str(input_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertTrue(response["ok"])
        self.assertEqual(response["endpoint"], RELEASE_UNBLOCK_CHECKLIST_ENDPOINT)
        self.assertEqual(response["result"]["schema_version"], "a2.release_unblock_checklist.v1")

    def test_cli_exposes_results_persist_endpoint(self):
        payload = {
            "request_id": "cli-results-persist",
            "tenant_id": "tenant_enterprise",
            "project_id": "project_enterprise",
            "run_id": "run_cli_upload",
            "created_at": "2026-07-07T00:00:00Z",
            "a1_ingestion": {
                "schema_version": "releasefoundry.saas_control_plane.v1",
                "operation": "sdk-submit",
                "upload_id": "upload_cli",
                "payload_sha256": "sha_cli",
                "payload_keys": ["request", "result"],
                "raw_payload_included": False,
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = Path(tmp_dir) / "payload.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/a2_judge_service.py"),
                    RESULTS_PERSIST_ENDPOINT,
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
        self.assertEqual(response["endpoint"], RESULTS_PERSIST_ENDPOINT)
        self.assertEqual(response["result"]["record_type_counts"], {"a1_ingestion_digest": 1})
        self.assertEqual(response["result"]["records"][0]["output_summary"]["operation"], "sdk-submit")


if __name__ == "__main__":
    unittest.main()
