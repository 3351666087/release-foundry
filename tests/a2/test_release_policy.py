import copy
import json
import unittest
from pathlib import Path

from services.judge.release_policy import (
    ReleasePolicyError,
    compute_policy_hash,
    evaluate_release_policy,
    evaluate_release_policy_config,
    select_release_policy,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional local validation dependency.
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[2]
POLICY_FIXTURE = ROOT / "fixtures/a2/config/release_policies.json"
POLICY_SCHEMA = ROOT / "docs/a2/schemas/release_policy.schema.json"
GRADE_REPORT = ROOT / "fixtures/a2/results/a2_g3_grade_results.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def grade_report(rows: list[dict]) -> dict:
    return {
        "schema_version": "a2.grade_results.v1",
        "report_id": "unit_policy_grade_report",
        "dataset_id": "unit-policy",
        "scenario_pack": "unit",
        "total_cases": len(rows),
        "passed": sum(1 for row in rows if row["passed"]),
        "failed": sum(1 for row in rows if not row["passed"]),
        "grade_results": rows,
    }


def case_row(case_id: str, passed: bool, score: float, failure_class: str = "none") -> dict:
    return {
        "schema_version": "a2.local_judge_run.v1",
        "scenario_id": "A2-S001",
        "case_id": case_id,
        "passed": passed,
        "score": score,
        "primary_failure_class": failure_class,
        "judge_results": [],
    }


def prod_report_with_one_safety_failure() -> dict:
    rows = [case_row(f"pass-{index}", True, 100.0) for index in range(99)]
    rows.append(case_row("safety-failure", False, 70.0, "unsafe_or_policy_violation"))
    return grade_report(rows)


class A2ReleasePolicyTests(unittest.TestCase):
    def test_fixture_matches_schema_and_policy_hashes(self):
        config = load_json(POLICY_FIXTURE)
        schema = load_json(POLICY_SCHEMA)

        self.assertEqual(schema["properties"]["schema_version"]["const"], config["schema_version"])
        if Draft202012Validator is not None:
            Draft202012Validator(schema).validate(config)

        policy_ids = {policy["policy_id"] for policy in config["policies"]}
        self.assertIn(config["default_policy_id"], policy_ids)
        for assignment in config["assignments"]:
            self.assertIn(assignment["policy_id"], policy_ids)
        self.assertTrue(any("branch" in item or "branches" in item for item in config["assignments"]))
        for policy in config["policies"]:
            with self.subTest(policy=policy["policy_id"]):
                self.assertEqual(policy["policy_hash"], compute_policy_hash(policy))
                self.assertTrue(policy["policy_version"])
                self.assertIn(policy["blocking_mode"], {"enforce", "warn_only", "observe"})
                self.assertIn("risk_thresholds", policy)
                self.assertIn("waiver_policy", policy)
                self.assertIn("approval_policy", policy)

    def test_project_environment_selection_prefers_exact_assignment(self):
        config = load_json(POLICY_FIXTURE)

        policy, selection = select_release_policy(
            config,
            project_id="project_enterprise",
            environment="prod",
        )

        self.assertEqual(policy["policy_id"], "release_policy_prod_strict")
        self.assertEqual(selection["assignment_id"], "project_enterprise_prod")
        self.assertEqual(selection["match_scope"], "project_environment")

    def test_branch_specific_selection_prefers_branch_assignment(self):
        config = load_json(POLICY_FIXTURE)

        policy, selection = select_release_policy(
            config,
            project_id="project_enterprise",
            environment="prod",
            branch="main",
        )

        self.assertEqual(policy["policy_id"], "release_policy_prod_strict")
        self.assertEqual(selection["assignment_id"], "project_enterprise_main_prod")
        self.assertEqual(selection["match_scope"], "project_environment_branch")
        self.assertEqual(selection["branch_pattern"], "main")

    def test_prod_policy_blocks_failure_class_and_metric_thresholds(self):
        config = load_json(POLICY_FIXTURE)
        report = load_json(GRADE_REPORT)

        evaluation = evaluate_release_policy_config(
            config,
            project_id="project_enterprise",
            environment="prod",
            release_candidate_id="agent-v42",
            grade_report=report,
        )

        self.assertEqual(evaluation["schema_version"], "a2.release_policy_evaluation.v1")
        self.assertEqual(evaluation["policy_id"], "release_policy_prod_strict")
        self.assertEqual(evaluation["decision"], "block")
        self.assertGreaterEqual(evaluation["blocking_violation_count"], 1)
        self.assertEqual(evaluation["release_candidate_id"], "agent-v42")
        self.assertFalse(evaluation["metadata"]["requires_network"])
        violation_ids = {item["rule_id"] for item in evaluation["violations"]}
        self.assertIn("prod_min_pass_rate", violation_ids)
        self.assertIn("prod_no_safety_policy_violations", violation_ids)
        self.assertEqual(evaluation["a3_gate_summary"]["status"], "BLOCK")
        self.assertIn("decision_evidence", evaluation)
        self.assertIn("risk", evaluation)
        self.assertIn("a3_release_gate_fields", evaluation["consumer_contract"])

    def test_prod_policy_blocks_saas_surface_risks_from_frontend_mapping(self):
        config = load_json(POLICY_FIXTURE)
        report = grade_report([case_row("pass", True, 100.0)])

        evaluation = evaluate_release_policy_config(
            config,
            project_id="project_enterprise_saas_agent",
            environment="prod",
            branch="main",
            release_candidate_id="agent-v43",
            grade_report=report,
            metrics={
                "usage_quota_blocked": 1,
                "trust_publishability_blocked": 1,
                "api_key_boundary_violations": 1,
                "server_side_grading_stale": 1,
            },
        )

        self.assertEqual(evaluation["decision"], "block")
        violation_ids = {item["rule_id"] for item in evaluation["violations"]}
        self.assertLessEqual(
            {
                "prod_usage_quota_not_blocked",
                "prod_no_api_key_boundary_violations",
                "prod_trust_publishability_not_blocked",
                "prod_server_side_grading_fresh",
            },
            violation_ids,
        )
        self.assertEqual(evaluation["metrics"]["usage_quota_blocked"], 1)
        self.assertEqual(evaluation["metrics"]["trust_publishability_blocked"], 1)
        self.assertEqual(evaluation["metrics"]["api_key_boundary_violations"], 1)
        self.assertEqual(evaluation["metrics"]["server_side_grading_stale"], 1)
        self.assertTrue(all(item["mode"] == "blocking" for item in evaluation["violations"]))
        self.assertIn("docs/a2/frontend_mirror_saas_mapping_20260707.md", json.dumps(evaluation["evaluated_rules"]))

    def test_staging_policy_can_warn_without_blocking(self):
        config = load_json(POLICY_FIXTURE)
        rows = [case_row(f"pass-{index}", True, 100.0) for index in range(9)]
        rows.append(case_row("wrong-arguments", False, 60.0, "wrong_arguments"))

        evaluation = evaluate_release_policy_config(
            config,
            project_id="project_enterprise",
            environment="staging",
            grade_report=grade_report(rows),
        )

        self.assertEqual(evaluation["policy_id"], "release_policy_staging_balanced")
        self.assertEqual(evaluation["decision"], "warn")
        self.assertEqual(evaluation["blocking_violation_count"], 0)
        self.assertEqual(evaluation["non_blocking_violation_count"], 1)
        self.assertEqual(evaluation["violations"][0]["mode"], "non_blocking")
        self.assertEqual(evaluation["violations"][0]["observed"]["failure_class"], "wrong_arguments")
        self.assertEqual(evaluation["metrics"]["pass_rate"], 90.0)

    def test_staging_policy_warns_on_saas_readiness_but_blocks_api_key_boundary(self):
        config = load_json(POLICY_FIXTURE)
        report = grade_report([case_row("pass", True, 100.0)])

        readiness_warning = evaluate_release_policy_config(
            config,
            project_id="project_enterprise_saas_agent",
            environment="staging",
            grade_report=report,
            metrics={
                "usage_quota_blocked": 1,
                "trust_publishability_blocked": 1,
                "server_side_grading_stale": 1,
            },
        )
        api_key_block = evaluate_release_policy_config(
            config,
            project_id="project_enterprise_saas_agent",
            environment="staging",
            grade_report=report,
            metrics={"api_key_boundary_violations": 1},
        )

        self.assertEqual(readiness_warning["decision"], "warn")
        self.assertEqual(readiness_warning["blocking_violation_count"], 0)
        warning_ids = {item["rule_id"] for item in readiness_warning["violations"]}
        self.assertLessEqual(
            {
                "staging_usage_quota_watch",
                "staging_trust_publishability_watch",
                "staging_server_side_grading_freshness_watch",
            },
            warning_ids,
        )
        self.assertEqual(api_key_block["decision"], "block")
        self.assertIn(
            "staging_no_api_key_boundary_violations",
            {item["rule_id"] for item in api_key_block["violations"]},
        )

    def test_dev_policy_uses_wildcard_assignment_and_passes_clean_report(self):
        config = load_json(POLICY_FIXTURE)
        report = grade_report([case_row("pass", True, 100.0)])

        evaluation = evaluate_release_policy_config(
            config,
            project_id="project_unknown",
            environment="dev",
            grade_report=report,
        )

        self.assertEqual(evaluation["policy_id"], "release_policy_dev_observe")
        self.assertEqual(evaluation["decision"], "pass")
        self.assertEqual(evaluation["selection"]["match_scope"], "environment_default_project")
        self.assertEqual(evaluation["metrics"]["average_score"], 100.0)

    def test_policy_hash_mismatch_rejects_stale_policy(self):
        config = load_json(POLICY_FIXTURE)
        policy = copy.deepcopy(config["policies"][0])
        policy["rules"][0]["max_count"] = 99

        with self.assertRaises(ReleasePolicyError):
            evaluate_release_policy(
                policy,
                grade_report=grade_report([case_row("pass", True, 100.0)]),
                project_id="project_enterprise",
                environment="prod",
            )

    def test_approved_waiver_suppresses_matching_blocking_violation(self):
        config = load_json(POLICY_FIXTURE)

        evaluation = evaluate_release_policy_config(
            config,
            project_id="project_enterprise",
            environment="prod",
            release_candidate_id="agent-v42",
            grade_report=prod_report_with_one_safety_failure(),
            waivers=[
                {
                    "waiver_id": "wv-prod-safety-reviewed",
                    "approval_id": "approval-123",
                    "status": "approved",
                    "rule_id": "prod_no_safety_policy_violations",
                    "project_id": "project_enterprise",
                    "environment": "prod",
                    "release_candidate_id": "agent-v42",
                    "reviewer": "release-manager",
                    "reason": "Known reviewed fixture used to validate waiver workflow.",
                    "evidence_ref": "docs/evidence/private_refs/reviewed-waiver-123.json",
                }
            ],
        )

        self.assertEqual(evaluation["decision"], "pass")
        self.assertEqual(evaluation["blocking_violation_count"], 0)
        self.assertEqual(evaluation["waived_violation_count"], 1)
        self.assertEqual(evaluation["waiver_summary"]["applied_count"], 1)
        self.assertEqual(evaluation["waiver_summary"]["waived_blocking_count"], 1)
        self.assertEqual(evaluation["waived_violations"][0]["rule_id"], "prod_no_safety_policy_violations")
        self.assertTrue(evaluation["evaluated_rules"][0]["waived"])

    def test_unapproved_or_mismatched_waiver_does_not_suppress_block(self):
        config = load_json(POLICY_FIXTURE)

        evaluation = evaluate_release_policy_config(
            config,
            project_id="project_enterprise",
            environment="prod",
            release_candidate_id="agent-v42",
            grade_report=prod_report_with_one_safety_failure(),
            waivers=[
                {
                    "waiver_id": "wv-pending",
                    "approval_id": "approval-pending",
                    "status": "requested",
                    "rule_id": "prod_no_safety_policy_violations",
                    "reviewer": "release-manager",
                    "reason": "Still pending.",
                },
                {
                    "waiver_id": "wv-wrong-env",
                    "approval_id": "approval-wrong-env",
                    "status": "approved",
                    "rule_id": "prod_no_safety_policy_violations",
                    "environment": "staging",
                    "reviewer": "release-manager",
                    "reason": "Approved for staging only.",
                },
            ],
        )

        self.assertEqual(evaluation["decision"], "block")
        self.assertEqual(evaluation["blocking_violation_count"], 1)
        self.assertEqual(evaluation["waiver_summary"]["applied_count"], 0)
        self.assertEqual(evaluation["waiver_summary"]["unapplied_count"], 2)
        self.assertEqual(
            {item["unapplied_reason"] for item in evaluation["unapplied_waivers"]},
            {"status_not_approved", "environment_scope_mismatch"},
        )

    def test_waiver_audit_output_is_public_safe(self):
        config = load_json(POLICY_FIXTURE)

        evaluation = evaluate_release_policy_config(
            config,
            project_id="project_enterprise",
            environment="prod",
            release_candidate_id="agent-v42",
            grade_report=prod_report_with_one_safety_failure(),
            waivers=[
                {
                    "waiver_id": "wv-public-safe",
                    "approval_id": "approval-public-safe",
                    "status": "approved",
                    "failure_class": "unsafe_or_policy_violation",
                    "reviewer": "release-manager",
                    "reason": "Reviewed against private evidence bundle.",
                    "evidence_refs": ["docs/evidence/private_refs/reviewed-waiver-456.json"],
                    "secret_value": "do-not-emit",
                    "raw_payload": {"token": "do-not-emit"},
                    "api_key": "do-not-emit",
                }
            ],
        )

        serialized = json.dumps(
            {
                "applied": evaluation["applied_waivers"],
                "waived": evaluation["waived_violations"],
                "unapplied": evaluation["unapplied_waivers"],
            },
            sort_keys=True,
        )
        self.assertNotIn("do-not-emit", serialized)
        self.assertNotIn("secret_value", serialized)
        self.assertNotIn("raw_payload", serialized)
        self.assertNotIn("api_key", serialized)

    def test_risk_threshold_can_block_accumulated_non_blocking_risk(self):
        policy = {
            "policy_id": "unit_risk_policy",
            "policy_version": "unit",
            "blocking_mode": "enforce",
            "risk_thresholds": {"warn_threshold": 5, "block_threshold": 25},
            "approval_policy": {"block_on_missing_approvals": False, "requirements": []},
            "waiver_policy": {"allowed": True},
            "rules": [
                {
                    "rule_id": "unit_quality_floor",
                    "type": "metric_threshold",
                    "mode": "non_blocking",
                    "severity": "medium",
                    "metric": "pass_rate",
                    "operator": ">=",
                    "threshold": 100,
                    "risk_weight": 60,
                }
            ],
        }

        evaluation = evaluate_release_policy(
            policy,
            project_id="project_enterprise",
            environment="staging",
            grade_report=grade_report(
                [case_row("pass", True, 100.0), case_row("quality-fail", False, 60.0, "wrong_arguments")]
            ),
        )

        self.assertEqual(evaluation["risk"]["threshold_decision"], "block")
        self.assertEqual(evaluation["decision"], "block")
        self.assertIn("risk_threshold_block", {item["rule_id"] for item in evaluation["violations"]})

    def test_missing_required_approval_blocks_when_policy_enforces_it(self):
        policy = {
            "policy_id": "unit_approval_policy",
            "policy_version": "unit",
            "blocking_mode": "enforce",
            "risk_thresholds": {"warn_threshold": 25, "block_threshold": 75},
            "waiver_policy": {"allowed": True},
            "approval_policy": {
                "block_on_missing_approvals": True,
                "requirements": [
                    {
                        "requirement_id": "prod_release_manager_signoff",
                        "when": ["prod_release"],
                        "approval_type": "release_manager_signoff",
                        "min_count": 1,
                        "summary": "Production release requires release manager signoff.",
                    }
                ],
            },
            "rules": [
                {
                    "rule_id": "unit_min_pass_rate",
                    "type": "metric_threshold",
                    "mode": "blocking",
                    "severity": "critical",
                    "metric": "pass_rate",
                    "operator": ">=",
                    "threshold": 100,
                }
            ],
        }
        report = grade_report([case_row("pass", True, 100.0)])

        missing = evaluate_release_policy(
            policy,
            project_id="project_enterprise",
            environment="prod",
            branch="main",
            release_candidate_id="agent-v42",
            grade_report=report,
        )
        approved = evaluate_release_policy(
            policy,
            project_id="project_enterprise",
            environment="prod",
            branch="main",
            release_candidate_id="agent-v42",
            grade_report=report,
            approvals=[
                {
                    "approval_id": "approval-prod-signoff",
                    "approval_type": "release_manager_signoff",
                    "status": "approved",
                    "environment": "prod",
                    "branch": "main",
                    "release_candidate_id": "agent-v42",
                    "approver": "release-manager",
                    "reason": "Reviewed release gate.",
                    "evidence_ref": "docs/evidence/private_refs/prod-signoff.json",
                }
            ],
        )

        self.assertEqual(missing["decision"], "block")
        self.assertEqual(missing["approval_summary"]["status"], "missing")
        self.assertIn("approval_required::prod_release_manager_signoff", {item["rule_id"] for item in missing["violations"]})
        self.assertEqual(approved["decision"], "pass")
        self.assertEqual(approved["approval_summary"]["status"], "approved")

    def test_warn_only_blocking_mode_demotes_blockers(self):
        policy = {
            "policy_id": "unit_warn_only_policy",
            "policy_version": "unit",
            "blocking_mode": "warn_only",
            "risk_thresholds": {"warn_threshold": 80, "block_threshold": 100},
            "approval_policy": {"block_on_missing_approvals": False, "requirements": []},
            "waiver_policy": {"allowed": True},
            "rules": [
                {
                    "rule_id": "unit_no_safety",
                    "type": "failure_class_threshold",
                    "mode": "blocking",
                    "severity": "critical",
                    "failure_class": "unsafe_or_policy_violation",
                    "max_count": 0,
                }
            ],
        }

        evaluation = evaluate_release_policy(
            policy,
            project_id="project_unknown",
            environment="dev",
            grade_report=prod_report_with_one_safety_failure(),
        )

        self.assertEqual(evaluation["decision"], "warn")
        self.assertEqual(evaluation["blocking_violation_count"], 0)
        self.assertEqual(evaluation["non_blocking_violation_count"], 1)
        self.assertEqual(evaluation["blocking_mode_summary"]["demoted_blocking_count"], 1)


if __name__ == "__main__":
    unittest.main()
