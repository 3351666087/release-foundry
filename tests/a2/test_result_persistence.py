import json
import jsonschema
import re
import unittest
import tempfile
from pathlib import Path

from services.judge.result_persistence import (
    build_result_persistence_manifest,
    build_result_record,
    build_ocr_vision_disagreement_record,
    build_multimodal_runtime_record,
    build_structured_output_failure_record,
    stable_hash,
    verify_jsonl_manifest,
    verify_jsonl_manifest_predecessor,
    write_jsonl,
)
from services.judge.ocr_contract import run_optional_ocr_adapter
from services.judge.local_multimodal_calibration import validate_prompt_lineage


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_FIXTURE = ROOT / "fixtures/a2/results/a2_result_persistence_manifest.json"
MANIFEST_SCHEMA = ROOT / "docs/a2/schemas/result_persistence_manifest.schema.json"
GRADE_REPORT = ROOT / "fixtures/a2/results/a2_g3_grade_results.json"
RELEASE_GATE = ROOT / "fixtures/a2/results/a2_release_gate_report.json"
RELEASE_UNBLOCK_CHECKLIST = ROOT / "fixtures/a2/results/a2_release_unblock_checklist.json"
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
    def test_jsonl_manifest_round_trip_and_tamper_detection(self):
        records = [{"case": "one", "result": "BLOCK"}, {"case": "two", "result": "PASS"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.jsonl"
            manifest = write_jsonl(path, records)
            jsonschema.validate(
                manifest,
                load_json(ROOT / "docs/a2/schemas/result_persistence_jsonl_manifest.schema.json"),
            )
            verified = verify_jsonl_manifest(path, manifest)
            self.assertEqual(verified["state"], "verified")
            path.write_text(path.read_text(encoding="utf-8").replace("PASS", "BLOCK"), encoding="utf-8")
            tampered = verify_jsonl_manifest(path, manifest)
            self.assertEqual(tampered["state"], "blocked")
            self.assertIn("jsonl_file_hash_mismatch", tampered["blockers"])
            self.assertIn("jsonl_record_hash_mismatch", tampered["blockers"])
            self.assertIn("jsonl_chain_hash_mismatch", tampered["blockers"])

    def test_round30_predecessor_and_failed_replace_preserve_old_bytes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.jsonl"
            second_path = Path(temp_dir) / "second.jsonl"
            first = write_jsonl(first_path, [{"case": "one"}])
            second = write_jsonl(
                second_path,
                [{"case": "two"}],
                sequence_number=2,
                previous_sequence_number=1,
                previous_manifest_hash=stable_hash(first),
                writer_build_hash="sha256:" + "1" * 64,
            )
            self.assertEqual(
                verify_jsonl_manifest_predecessor(
                    manifest=second, previous_manifest=first
                )["state"],
                "verified",
            )
            old = b'{"old": true}\n'
            target = Path(temp_dir) / "atomic.jsonl"
            target.write_bytes(old)
            with self.assertRaisesRegex(OSError, "injected"):
                write_jsonl(
                    target,
                    [{"new": True}],
                    replace_function=lambda *_: (_ for _ in ()).throw(OSError("injected")),
                )
            self.assertEqual(target.read_bytes(), old)
            self.assertFalse(target.with_name(target.name + ".tmp").exists())

    def test_jsonl_manifest_chains_batches_and_blocks_truncated_line(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.jsonl"
            second_path = Path(directory) / "second.jsonl"
            first = write_jsonl(first_path, [{"case": "one"}])
            second = write_jsonl(
                second_path,
                [{"case": "two"}],
                previous_manifest_hash=stable_hash(first),
                previous_sequence_number=1,
                sequence_number=2,
            )
            self.assertEqual(second["previous_manifest_hash"], stable_hash(first))
            self.assertEqual(verify_jsonl_manifest(second_path, second)["state"], "verified")
            second_path.write_text('{"case":"two"}\n{"case":', encoding="utf-8")
            truncated = verify_jsonl_manifest(second_path, second)
            self.assertEqual(truncated["state"], "blocked")
            self.assertIn("jsonl_parse_failure", truncated["blockers"])

    def test_jsonl_sequence_pin_and_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "batch.jsonl"
            path.write_text('{"stale": true}\n', encoding="utf-8")
            manifest = write_jsonl(
                path, [{"case": "fresh"}], sequence_number=3, previous_sequence_number=2
            )
            self.assertFalse(path.with_name(path.name + ".tmp").exists())
            replay = verify_jsonl_manifest(
                path,
                manifest,
                expected_sequence_number=4,
                pinned_chain_hash="sha256:" + "0" * 64,
            )
            self.assertIn("jsonl_sequence_gap_or_replay", replay["blockers"])
            self.assertIn("jsonl_chain_head_pin_mismatch", replay["blockers"])
            verified = verify_jsonl_manifest(
                path,
                manifest,
                expected_sequence_number=3,
                pinned_chain_hash=manifest["chain_hash"],
            )
            self.assertEqual(verified["state"], "verified")

    def test_multimodal_runtime_timeout_receipts_persist_hash_only(self):
        receipt = "sha256:" + "9" * 64
        record = build_multimodal_runtime_record(
            {
                "schema_version": "a2.multimodal_runtime_policy.v1",
                "observation_count": 2,
                "maximum_latency_seconds": 30,
                "maximum_completion_tokens": 48,
                "maximum_provider_timeout_rate": 0.1,
                "minimum_valid_semantic_output_rate": 0.9,
                "timeout_count": 1,
                "provider_timeout_rate": 0.5,
                "completed_count": 1,
                "completed_semantic_count": 0,
                "empty_response_count": 1,
                "valid_semantic_output_rate": 0,
                "qualification_state": "blocked",
                "blockers": ["multimodal_runtime_provider_timeout"],
                "queue_telemetry": {"state": "not_exposed", "maximum_depth": None},
                "cancellation_receipt_hashes": [receipt],
                "public_safe": True,
                "raw_response": "must-not-persist",
            },
            org_id="org",
            project_id="project",
            run_id="run",
            case_id="case",
            judge_version="a2-runtime-v1",
            created_at="2026-07-13T00:00:00Z",
        )
        text = json.dumps(record)
        self.assertEqual(record["record_type"], "multimodal_runtime")
        self.assertNotIn("must-not-persist", text)
        self.assertNotIn(receipt, text)
        self.assertTrue(HASH_RE.fullmatch(record["output_hash"]))

    def test_ocr_vision_disagreement_record_is_hash_only(self):
        disagreement = {"state": "disagreement", "artifact_hash": "sha256:" + "1" * 64, "ocr_observation_hash": "sha256:" + "2" * 64, "vision_output_hash": "sha256:" + "3" * 64, "reason_code": "vision_hallucinated_text", "review_packet_hash": "sha256:" + "4" * 64, "blockers": ["ocr_vision_text_disagreement"], "raw_text": "do not persist"}
        record = build_ocr_vision_disagreement_record(disagreement, org_id="org", project_id="project", run_id="run", case_id="case", created_at="2026-07-13T00:00:00Z")
        self.assertEqual(record["record_type"], "ocr_vision_disagreement")
        self.assertNotIn("do not persist", json.dumps(record))

    def test_structured_output_failure_record_is_hash_only(self):
        receipt = {
            "state": "invalid_json",
            "provider_status": "completed",
            "raw_response_hash": "sha256:" + "a" * 64,
            "parsed_output_hash": "",
            "blockers": ["structured_output_invalid_json"],
            "raw_secret": "must-not-persist",
        }
        record = build_structured_output_failure_record(
            receipt,
            org_id="org",
            project_id="project",
            run_id="run",
            case_id="case",
            created_at="2026-07-13T00:00:00Z",
        )
        self.assertEqual(record["record_type"], "structured_output_failure")
        self.assertNotIn("must-not-persist", json.dumps(record))
    def test_prompt_supersession_persists_as_hash_only_audit_record(self):
        current = "sha256:" + "a" * 64
        previous = "sha256:" + "b" * 64
        observation = validate_prompt_lineage(
            current_prompt_hash=current,
            supersedes_prompt_hash=previous,
            known_lineage={},
            maximum_lineage_depth=8,
        )
        record = build_result_record(
            observation,
            org_id="org-a2",
            project_id="project-a2",
            run_id="run-prompt-supersession",
            kind="prompt_supersession",
            judge_version="a2-prompt-lineage-v1",
        )
        self.assertTrue(observation["lineage_valid"])
        self.assertEqual(record["record_type"], "prompt_supersession")
        self.assertTrue(HASH_RE.fullmatch(record["output_hash"]))
        self.assertNotIn(current, json.dumps(record))
        self.assertNotIn(previous, json.dumps(record))

    def test_ocr_failure_observation_persists_as_hash_only_audit_record(self):
        observation = run_optional_ocr_adapter(
            image_path="missing.png",
            adapter_id="offline-test",
            adapter_version_hash="sha256:" + "1" * 64,
            adapter=lambda _: (_ for _ in ()).throw(RuntimeError("provider unavailable")),
        )
        record = build_result_record(
            observation,
            org_id="org-a2",
            project_id="project-a2",
            run_id="run-ocr-failure",
            kind="ocr_observation",
            judge_version="a2-ocr-contract-v1",
        )
        self.assertEqual(observation["state"], "failed")
        self.assertEqual(record["record_type"], "ocr_observation")
        self.assertTrue(HASH_RE.fullmatch(record["output_hash"]))
        self.assertNotIn("provider unavailable", json.dumps(record))
        self.assertTrue(record["metadata"]["raw_payload_not_recorded"])

    def test_manifest_fixture_matches_builder(self):
        grade_report = load_json(GRADE_REPORT)
        release_gate = load_json(RELEASE_GATE)
        release_unblock_checklist = load_json(RELEASE_UNBLOCK_CHECKLIST)
        scenario_pack = load_json(SCENARIO_PACK)
        scenario_selection = load_json(SCENARIO_SELECTION)
        run_fixtures = [load_json(path) for path in sorted(RUN_DIR.glob("*.json"))]

        actual = build_result_persistence_manifest(
            grade_report,
            release_gate,
            scenario_pack,
            scenario_selection_report=scenario_selection,
            release_unblock_checklist_report=release_unblock_checklist,
            run_fixtures=run_fixtures,
            source_refs={
                "grade_report": "fixtures/a2/results/a2_g3_grade_results.json",
                "release_gate": "fixtures/a2/results/a2_release_gate_report.json",
                "scenario_pack": "packages/scenarios/a2_g3_full_pack.json",
                "scenario_selection": "fixtures/a2/results/a2_scenario_selection_report.json",
                "regression_promotion_queue": "fixtures/a2/results/a2_regression_promotion_queue.json",
                "release_unblock_checklist": "fixtures/a2/results/a2_release_unblock_checklist.json",
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
            manifest["source_refs"]["regression_promotion_queue"],
            "fixtures/a2/results/a2_regression_promotion_queue.json",
        )
        self.assertEqual(
            manifest["source_refs"]["release_unblock_checklist"],
            "fixtures/a2/results/a2_release_unblock_checklist.json",
        )
        self.assertEqual(
            manifest["record_type_counts"],
            {
                "judge_result": 160,
                "release_gate": 1,
                "release_unblock_checklist": 1,
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
        release_unblock = next(
            record for record in manifest["records"] if record["record_type"] == "release_unblock_checklist"
        )

        self.assertEqual(release_gate["case"], "release-gate")
        self.assertEqual(release_gate["decision"], "block")
        self.assertEqual(release_gate["judge_id"], "release_policy_engine")
        self.assertEqual(release_unblock["case"], "release-unblock-checklist")
        self.assertEqual(release_unblock["judge_id"], "release_unblock_checklist")
        self.assertEqual(release_unblock["overall_status"], "blocked")
        self.assertEqual(release_unblock["blocked_gate_count"], 3)
        self.assertTrue(release_unblock["private_evidence_required"])
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

    def test_release_policy_saas_surface_audit_persists_public_safe_summary(self):
        release_gate = _release_gate_with_saas_surface_violations()
        manifest = build_result_persistence_manifest(
            {"schema_version": "a2.grade_results.v1", "report_id": "unit", "dataset_id": "unit", "grade_results": []},
            release_gate,
            {"schema_version": "a2.scenario_pack.v1", "scenarios": []},
            created_at="2026-07-07T00:00:00Z",
        )
        release_gate_record = next(record for record in manifest["records"] if record["record_type"] == "release_gate")
        audit = release_gate_record["release_policy_audit"]

        self.assertEqual(
            audit["saas_surface_metrics"],
            {
                "usage_quota_blocked": 1,
                "trust_publishability_blocked": 1,
                "api_key_boundary_violations": 1,
                "server_side_grading_stale": 1,
            },
        )
        self.assertEqual(len(audit["active_violations"]), 4)
        active_by_metric = {
            violation["observed"]["metric"]: violation for violation in audit["active_violations"]
        }
        self.assertEqual(active_by_metric["api_key_boundary_violations"]["mode"], "blocking")
        self.assertEqual(active_by_metric["api_key_boundary_violations"]["severity"], "critical")
        self.assertEqual(active_by_metric["usage_quota_blocked"]["owner_role"], "billing_admin")
        self.assertEqual(active_by_metric["server_side_grading_stale"]["dashboard_label"], "Server-side grading stale")
        self.assertNotIn("raw_account_payload", audit["saas_surface_metrics"])

        jsonl_record = build_result_record(
            {
                "schema_version": "a2.internal_service_response.v1",
                "endpoint": "/internal/release-policy/evaluate",
                "ok": True,
                "status_code": 200,
                "result": release_gate,
            },
            org_id="org_demo",
            project_id="project_enterprise",
            run_id="run_demo",
            kind="release_policy",
            judge_version="a2-judge-service-0.1.0",
            policy_hash=stable_hash({"policy": "unit"}),
            input_payload={"authorization": "Bearer" + " secret-test-value-1234"},
            created_at="2026-07-07T00:00:00Z",
        )
        jsonl_audit = jsonl_record["output_summary"]["release_policy_audit"]
        self.assertEqual(jsonl_audit["saas_surface_metrics"], audit["saas_surface_metrics"])
        self.assertEqual(len(jsonl_audit["active_violations"]), 4)

        record_text = json.dumps({"release_gate": release_gate_record, "jsonl": jsonl_record}, sort_keys=True)
        self.assertNotIn("docs/evidence/private_refs", record_text)
        self.assertNotIn("raw_account_payload", record_text)
        self.assertNotIn("raw_request_body", record_text)
        self.assertNotIn("should-not-persist", record_text)
        self.assertNotIn("Bearer", record_text)
        self.assertNotIn("ashr_live_", record_text)
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


def _release_gate_with_saas_surface_violations() -> dict:
    return {
        "schema_version": "a2.release_gate.v1",
        "release_candidate": {"id": "agent-v43", "profile": "strict-commercial"},
        "decision": "block",
        "exit_code": 2,
        "risk_score": 95,
        "blocking_gate_count": 4,
        "evidence_blocker_count": 0,
        "warning_count": 0,
        "ready_for_commercial_gate": False,
        "policy_evaluation": {
            "schema_version": "a2.release_policy_evaluation.v1",
            "policy_id": "release_policy_prod_strict",
            "policy_version": "2026-07-07.1",
            "policy_hash": stable_hash({"policy": "unit-saas-surface"}),
            "project_id": "project_enterprise",
            "environment": "prod",
            "release_candidate_id": "agent-v43",
            "decision": "block",
            "blocking_violation_count": 4,
            "non_blocking_violation_count": 0,
            "waived_violation_count": 0,
            "metrics": {
                "usage_quota_blocked": 1,
                "trust_publishability_blocked": 1,
                "api_key_boundary_violations": 1,
                "server_side_grading_stale": 1,
                "raw_account_payload": "should-not-persist",
            },
            "violations": [
                _saas_metric_violation(
                    "prod_usage_quota_available",
                    "usage_quota_blocked",
                    "blocking",
                    "high",
                    "billing_admin",
                    "Usage quota blocks release evaluation.",
                    "Usage quota blocked",
                    45,
                ),
                _saas_metric_violation(
                    "prod_no_api_key_boundary_violations",
                    "api_key_boundary_violations",
                    "blocking",
                    "critical",
                    "security_admin",
                    "Release boundary leaked credential handling.",
                    "API key boundary violation",
                    45,
                ),
                _saas_metric_violation(
                    "prod_trust_page_publishable",
                    "trust_publishability_blocked",
                    "blocking",
                    "high",
                    "release_manager",
                    "Trust page is not publishable for enterprise review.",
                    "Trust publishability blocked",
                    25,
                ),
                _saas_metric_violation(
                    "prod_server_side_grading_current",
                    "server_side_grading_stale",
                    "blocking",
                    "high",
                    "evaluation_owner",
                    "Server-side grading evidence is stale.",
                    "Server-side grading stale",
                    25,
                ),
            ],
        },
    }


def _saas_metric_violation(
    rule_id: str,
    metric: str,
    mode: str,
    severity: str,
    owner_role: str,
    business_impact: str,
    dashboard_label: str,
    risk_weight: int,
) -> dict:
    return {
        "rule_id": rule_id,
        "type": "metric_threshold",
        "mode": mode,
        "severity": severity,
        "passed": False,
        "summary": f"{metric} failed == 0.",
        "owner_role": owner_role,
        "business_impact": business_impact,
        "dashboard_label": dashboard_label,
        "risk_weight": risk_weight,
        "waiver_eligible": False,
        "observed": {
            "metric": metric,
            "value": 1,
            "raw_request_body": "should-not-persist",
        },
        "threshold": {"operator": "==", "threshold": 0},
        "evidence_refs": ["docs/evidence/private_refs/saas-surface.json"],
        "raw_payload": {"token": "ashr" + "_live_should_not_persist"},
    }


if __name__ == "__main__":
    unittest.main()
