import json
import re
import unittest
from pathlib import Path

from services.judge.result_persistence import build_result_persistence_manifest, build_result_record, stable_hash


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_FIXTURE = ROOT / "fixtures/a2/results/a2_result_persistence_manifest.json"
MANIFEST_SCHEMA = ROOT / "docs/a2/schemas/result_persistence_manifest.schema.json"
GRADE_REPORT = ROOT / "fixtures/a2/results/a2_g3_grade_results.json"
RELEASE_GATE = ROOT / "fixtures/a2/results/a2_release_gate_report.json"
SCENARIO_PACK = ROOT / "packages/scenarios/a2_g3_full_pack.json"
SCENARIO_SELECTION = ROOT / "fixtures/a2/results/a2_scenario_selection_report.json"
RUN_DIR = ROOT / "fixtures/a2/runs"

HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
REQUIRED_RECORD_FIELDS = {
    "tenant_id",
    "org",
    "project",
    "run",
    "case",
    "judge_version",
    "policy_hash",
    "input_hash",
    "output_hash",
    "created_at",
}
SECRET_PATTERNS = [
    re.compile("tp_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("ashr_live_" + r"[A-Za-z0-9_\\-]+"),
    re.compile("sk-" + r"[A-Za-z0-9]"),
    re.compile("Bearer" + r"\\s+"),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class A2ResultPersistenceTests(unittest.TestCase):
    def test_manifest_fixture_matches_builder(self):
        grade_report = load_json(GRADE_REPORT)
        release_gate = load_json(RELEASE_GATE)
        scenario_pack = load_json(SCENARIO_PACK)
        scenario_selection = load_json(SCENARIO_SELECTION)
        run_fixtures = [load_json(path) for path in sorted(RUN_DIR.glob("*.json"))]

        actual = build_result_persistence_manifest(
            grade_report,
            release_gate,
            scenario_pack,
            scenario_selection_report=scenario_selection,
            run_fixtures=run_fixtures,
            source_refs={
                "grade_report": "fixtures/a2/results/a2_g3_grade_results.json",
                "release_gate": "fixtures/a2/results/a2_release_gate_report.json",
                "scenario_pack": "packages/scenarios/a2_g3_full_pack.json",
                "scenario_selection": "fixtures/a2/results/a2_scenario_selection_report.json",
            },
        )

        self.assertEqual(actual, load_json(MANIFEST_FIXTURE))

    def test_manifest_has_required_audit_fields_and_record_types(self):
        manifest = load_json(MANIFEST_FIXTURE)
        schema = load_json(MANIFEST_SCHEMA)
        records = manifest["records"]

        self.assertEqual(schema["properties"]["schema_version"]["const"], manifest["schema_version"])
        self.assertEqual(manifest["record_count"], len(records))
        self.assertEqual(manifest["tenant_id"], manifest["org"])
        self.assertEqual(
            manifest["record_type_counts"],
            {
                "judge_result": 160,
                "release_gate": 1,
                "scenario_selection": 1,
            },
        )
        self.assertEqual({record["record_type"] for record in records}, set(manifest["record_type_counts"]))

        for record in records:
            with self.subTest(record_type=record["record_type"], case=record["case"], judge=record["judge_id"]):
                self.assertLessEqual(REQUIRED_RECORD_FIELDS, set(record))
                self.assertEqual(record["tenant_id"], manifest["tenant_id"])
                self.assertEqual(record["org"], manifest["org"])
                self.assertEqual(record["project"], manifest["project"])
                self.assertEqual(record["run"], manifest["run"])
                self.assertRegex(record["policy_hash"], HASH_RE)
                self.assertRegex(record["input_hash"], HASH_RE)
                self.assertRegex(record["output_hash"], HASH_RE)
                self.assertNotIn("evidence", record)

    def test_release_gate_and_scenario_selection_records_are_public_summaries(self):
        manifest = load_json(MANIFEST_FIXTURE)
        release_gate = next(record for record in manifest["records"] if record["record_type"] == "release_gate")
        scenario_selection = next(
            record for record in manifest["records"] if record["record_type"] == "scenario_selection"
        )

        self.assertEqual(release_gate["case"], "release-gate")
        self.assertEqual(release_gate["decision"], "block")
        self.assertEqual(release_gate["judge_id"], "release_policy_engine")
        self.assertEqual(scenario_selection["case"], "scenario-selection")
        self.assertEqual(scenario_selection["selection_id"], "a2_enterprise_saas_prod_selection")
        self.assertEqual(scenario_selection["selected_count"], 12)
        self.assertTrue(scenario_selection["selected"])

    def test_manifest_does_not_persist_private_refs_raw_evidence_or_secrets(self):
        manifest_text = MANIFEST_FIXTURE.read_text(encoding="utf-8")

        self.assertNotIn("docs/evidence/private_refs", manifest_text)
        self.assertNotIn("private_input_ref", manifest_text)
        self.assertNotIn("final_response_excerpt", manifest_text)
        self.assertNotIn("tool_sequence", manifest_text)
        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(manifest_text), pattern.pattern)

    def test_release_policy_waiver_audit_enters_manifest_as_public_summary(self):
        release_gate = _release_gate_with_policy_waiver()
        manifest = build_result_persistence_manifest(
            {"schema_version": "a2.grade_results.v1", "report_id": "unit", "dataset_id": "unit", "grade_results": []},
            release_gate,
            {"schema_version": "a2.scenario_pack.v1", "scenarios": []},
            created_at="2026-07-07T00:00:00Z",
        )
        release_gate_record = next(record for record in manifest["records"] if record["record_type"] == "release_gate")
        audit = release_gate_record["release_policy_audit"]

        self.assertEqual(audit["decision"], "pass")
        self.assertEqual(audit["waiver_summary"]["applied_count"], 1)
        self.assertEqual(audit["waiver_summary"]["waived_blocking_count"], 1)
        self.assertNotIn("raw_note", audit["waiver_summary"])
        self.assertEqual(audit["applied_waivers"][0]["waiver_id"], "wv-prod-safety")
        self.assertEqual(audit["applied_waivers"][0]["approval_id"], "approval-prod-safety")
        self.assertTrue(audit["applied_waivers"][0]["reason_present"])
        self.assertRegex(audit["applied_waivers"][0]["reason_hash"], HASH_RE)
        self.assertEqual(audit["applied_waivers"][0]["evidence_ref_count"], 1)
        self.assertRegex(audit["applied_waivers"][0]["evidence_ref_hashes"][0], HASH_RE)
        self.assertEqual(audit["waived_violations"][0]["rule_id"], "prod_no_safety_policy_violations")
        self.assertEqual(audit["waived_violations"][0]["observed"]["failure_class"], "unsafe_or_policy_violation")

        record_text = json.dumps(release_gate_record, sort_keys=True)
        self.assertNotIn("docs/evidence/private_refs", record_text)
        self.assertNotIn("raw_payload", record_text)
        self.assertNotIn("api_key", record_text)
        self.assertNotIn("Reviewed private waiver reason", record_text)
        self.assertNotIn("secret-test-value", record_text)

    def test_jsonl_ready_record_keeps_hashes_without_raw_payload_or_private_refs(self):
        record = build_result_record(
            {
                "endpoint": "/internal/judge/case",
                "scenario_id": "A2-S048",
                "case_id": "secret-case",
                "passed": False,
                "primary_failure_class": "unsafe_or_policy_violation",
                "final_response": "API key is " + "ashr_live_" + "1234567890abcdef.",
            },
            org_id="org_demo",
            project_id="proj_demo",
            run_id="run_demo",
            case_id="secret-case",
            kind="judge_result",
            judge_version="0.1.0",
            policy_hash=stable_hash({"policy": "unit"}),
            input_payload={"authorization": "Bearer" + " token-value", "prompt": "raw prompt"},
            evidence_refs=["docs/evidence/private_refs/raw.json"],
            created_at="2026-07-07T00:00:00Z",
        )
        record_text = json.dumps(record, sort_keys=True)

        self.assertRegex(record["input_hash"], HASH_RE)
        self.assertEqual(record["tenant_id"], "org_demo")
        self.assertRegex(record["output_hash"], HASH_RE)
        self.assertRegex(record["evidence_ref_hash"], HASH_RE)
        self.assertNotIn("payload", record)
        self.assertNotIn("evidence_refs", record)
        self.assertNotIn("docs/evidence/private_refs", record_text)
        self.assertNotIn("ashr_live_", record_text)
        self.assertNotIn("Bearer", record_text)

    def test_jsonl_ready_release_policy_record_keeps_public_waiver_audit_only(self):
        record = build_result_record(
            {
                "schema_version": "a2.internal_service_response.v1",
                "endpoint": "/internal/release-policy/evaluate",
                "ok": True,
                "status_code": 200,
                "result": _release_gate_with_policy_waiver(),
            },
            org_id="org_demo",
            project_id="project_enterprise",
            run_id="run_demo",
            kind="release_policy",
            judge_version="a2-judge-service-0.1.0",
            policy_hash=stable_hash({"policy": "unit"}),
            input_payload={
                "waivers": [
                    {
                        "evidence_ref": "docs/evidence/private_refs/service-waiver.json",
                        "token": "secret-test-value-1234",
                    }
                ]
            },
            created_at="2026-07-07T00:00:00Z",
        )
        audit = record["output_summary"]["release_policy_audit"]
        applied = audit["applied_waivers"][0]

        self.assertEqual(record["output_summary"]["endpoint"], "/internal/release-policy/evaluate")
        self.assertEqual(audit["policy_id"], "release_policy_prod_strict")
        self.assertEqual(applied["waived_rule_id"], "prod_no_safety_policy_violations")
        self.assertRegex(applied["reason_hash"], HASH_RE)
        self.assertRegex(record["input_hash"], HASH_RE)
        self.assertRegex(record["output_hash"], HASH_RE)
        record_text = json.dumps(record, sort_keys=True)
        self.assertNotIn("docs/evidence/private_refs", record_text)
        self.assertNotIn("Reviewed private waiver reason", record_text)
        self.assertNotIn('"raw_payload"', record_text)
        self.assertNotIn("api_key", record_text)
        self.assertNotIn("secret-test-value", record_text)


def _release_gate_with_policy_waiver() -> dict:
    return {
        "schema_version": "a2.release_gate.v1",
        "release_candidate": {"id": "agent-v42", "profile": "strict-commercial"},
        "decision": "pass",
        "exit_code": 0,
        "risk_score": 10,
        "blocking_gate_count": 0,
        "evidence_blocker_count": 0,
        "warning_count": 0,
        "ready_for_commercial_gate": True,
        "policy_evaluation": {
            "schema_version": "a2.release_policy_evaluation.v1",
            "policy_id": "release_policy_prod_strict",
            "policy_version": "2026-07-07.1",
            "policy_hash": stable_hash({"policy": "unit"}),
            "project_id": "project_enterprise",
            "environment": "prod",
            "release_candidate_id": "agent-v42",
            "decision": "pass",
            "blocking_violation_count": 0,
            "non_blocking_violation_count": 0,
            "waived_violation_count": 1,
            "waiver_summary": {
                "submitted_count": 1,
                "applied_count": 1,
                "unapplied_count": 0,
                "waived_blocking_count": 1,
                "waived_non_blocking_count": 0,
                "active_blocking_count": 0,
                "active_non_blocking_count": 0,
                "raw_note": "do not persist",
            },
            "applied_waivers": [
                {
                    "waiver_id": "wv-prod-safety",
                    "approval_id": "approval-prod-safety",
                    "status": "approved",
                    "reviewer": "release-manager",
                    "reason": "Reviewed private waiver reason with secret-test-value-1234.",
                    "evidence_ref": "docs/evidence/private_refs/reviewed-waiver.json",
                    "waived_rule_id": "prod_no_safety_policy_violations",
                    "waived_mode": "blocking",
                    "waived_severity": "critical",
                    "waived_type": "failure_class_threshold",
                    "raw_payload": {"api_key": "secret-test-value-1234"},
                }
            ],
            "waived_violations": [
                {
                    "rule_id": "prod_no_safety_policy_violations",
                    "type": "failure_class_threshold",
                    "mode": "blocking",
                    "severity": "critical",
                    "passed": False,
                    "summary": "Production releases cannot include safety or policy violations.",
                    "observed": {
                        "failure_class": "unsafe_or_policy_violation",
                        "count": 1,
                        "rate": 1.0,
                        "raw_payload": "do not persist",
                    },
                    "threshold": {"max_count": 0},
                    "waiver": {
                        "waiver_id": "wv-prod-safety",
                        "approval_id": "approval-prod-safety",
                        "status": "approved",
                        "reviewer": "release-manager",
                        "reason": "Reviewed private waiver reason with docs/evidence/private_refs/reviewed-waiver.json.",
                        "evidence_refs": ["docs/evidence/private_refs/reviewed-waiver.json"],
                        "api_key": "secret-test-value-1234",
                    },
                }
            ],
            "unapplied_waivers": [{"raw_payload": {"api_key": "secret-test-value-1234"}}],
        },
    }


if __name__ == "__main__":
    unittest.main()
