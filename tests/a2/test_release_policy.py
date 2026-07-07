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
        for policy in config["policies"]:
            with self.subTest(policy=policy["policy_id"]):
                self.assertEqual(policy["policy_hash"], compute_policy_hash(policy))
                self.assertTrue(policy["policy_version"])

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


if __name__ == "__main__":
    unittest.main()
