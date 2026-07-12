import json
import re
import unittest
from copy import deepcopy
from pathlib import Path

import jsonschema

from services.judge.result_persistence import redact_payload, stable_hash
from services.judge.trusted_spine import (
    GENESIS_HASH,
    build_decision_ledger,
    build_decision_record,
    build_evidence_snapshot,
    build_trusted_spine_handoff,
    build_trusted_spine_candidate_manifest,
    validate_trusted_spine_candidate,
)


ROOT = Path(__file__).resolve().parents[2]
RUN_FIXTURE = ROOT / "fixtures/a2/runs/a2_s031_media_pipeline_pass.json"
GRADE_FIXTURE = ROOT / "fixtures/a2/results/a2_s031_media_pipeline_pass_grade.json"
RELEASE_GATE = ROOT / "fixtures/a2/results/a2_release_gate_report.json"
HANDOFF = ROOT / "fixtures/a2/results/a2_trusted_spine_handoff.json"
EVIDENCE_SCHEMA = ROOT / "docs/a2/schemas/evidence_snapshot.schema.json"
LEDGER_SCHEMA = ROOT / "docs/a2/schemas/decision_ledger.schema.json"
HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
SECRET_PATTERNS = [
    re.compile(r"tp_[A-Za-z0-9_-]+"),
    re.compile(r"ashr_live_[A-Za-z0-9_-]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"Bearer\s+"),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs", re.IGNORECASE),
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class A2TrustedSpineTests(unittest.TestCase):
    def assert_schema(self, name, value):
        jsonschema.Draft202012Validator(
            load_json(ROOT / "docs/a2/schemas" / name),
            format_checker=jsonschema.FormatChecker(),
        ).validate(value)

    def test_candidate_rejects_stale_a2_and_decision_binding(self):
        candidate = build_trusted_spine_candidate_manifest(
            a1_sha="1" * 40,
            a2_sha="2" * 40,
            a3_sha="3" * 40,
            decision_hash="sha256:" + "4" * 64,
            grades_hash="sha256:" + "5" * 64,
            created_at="2026-07-13T00:00:00Z",
        )
        result = validate_trusted_spine_candidate(
            candidate,
            expected_a2_sha="6" * 40,
            expected_decision_hash="sha256:" + "7" * 64,
        )
        self.assertEqual(result["status"], "rejected")
        self.assertIn("trusted_spine_candidate_a2_sha_stale", result["blockers"])
        self.assert_schema("trusted_spine_candidate.schema.json", candidate)
        self.assert_schema("trusted_spine_candidate_validation.schema.json", result)

    def test_handoff_fixture_matches_builder(self):
        actual = build_trusted_spine_handoff(
            load_json(RUN_FIXTURE),
            load_json(GRADE_FIXTURE),
            load_json(RELEASE_GATE),
        )
        self.assertEqual(actual, load_json(HANDOFF))

    def test_evidence_snapshot_freezes_artifacts_without_treating_them_as_semantic_evidence(self):
        handoff = load_json(HANDOFF)
        snapshot = handoff["evidence_snapshot"]
        schema = load_json(EVIDENCE_SCHEMA)
        resolver = jsonschema.RefResolver(
            EVIDENCE_SCHEMA.as_uri(),
            schema,
            store={
                (EVIDENCE_SCHEMA.parent / "derived_evidence.schema.json").as_uri():
                    load_json(EVIDENCE_SCHEMA.parent / "derived_evidence.schema.json")
            },
        )

        jsonschema.validate(snapshot, schema, resolver=resolver)
        self.assertEqual(schema["properties"]["schema_version"]["const"], snapshot["schema_version"])
        self.assertEqual(snapshot["completeness"], "evidence_missing")
        self.assertEqual(snapshot["required_modalities"], ["image", "text"])
        self.assertEqual(snapshot["artifact_modalities"], ["image"])
        self.assertEqual(snapshot["observed_modalities"], ["text"])
        self.assertEqual(snapshot["missing_modalities"], ["image"])
        self.assertEqual(snapshot["derived_evidence"], [])
        self.assertGreaterEqual(len(snapshot["artifacts"]), 1)
        self.assertRegex(snapshot["snapshot_id"], HASH_RE)
        self.assertRegex(snapshot["snapshot_hash"], HASH_RE)
        self.assertTrue(snapshot["security"]["tenant_scoped"])
        self.assertFalse(snapshot["security"]["raw_evidence_included"])
        self.assertFalse(snapshot["security"]["artifact_content_included"])
        for artifact in snapshot["artifacts"]:
            self.assertFalse(artifact["content_included"])
            self.assertRegex(artifact["reference_hash"], HASH_RE)
            self.assertRegex(artifact["content_hash"], HASH_RE)

    def test_missing_required_modality_is_fail_closed(self):
        snapshot = build_evidence_snapshot(
            {"final_response": "text only", "tool_calls": []},
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-a",
            case_id="case-a",
            scenario_id="A2-S031",
            created_at="2026-07-11T00:00:00Z",
            required_modalities=["text", "video"],
        )
        self.assertEqual(snapshot["completeness"], "evidence_missing")
        self.assertEqual(snapshot["missing_modalities"], ["video"])
        with self.assertRaisesRegex(ValueError, "incomplete evidence"):
            build_decision_record(
                snapshot,
                decision="allow",
                release_gate_report={"decision": "pass"},
                judge_results=[],
                policy_version="unit",
                policy_hash=stable_hash({"policy": "unit"}),
                model_versions=["unit:model"],
                created_at="2026-07-11T00:00:00Z",
            )

    def test_a1_native_run_result_is_selected_and_validated(self):
        native_run = {
            "run_id": "run-native",
            "trace_completeness": 1,
            "aggregate_metrics": {"schema_version": "ashr.clone.run_result.v1"},
            "cases": [{
                "case_id": "case-native",
                "scenario_id": "A2-S031",
                "observations": [{
                    "observation_id": "obs-1",
                    "run_id": "run-native",
                    "case_id": "case-native",
                    "tool_calls": [{"name": "inspect_image", "arguments": {"path": "asset.png"}}],
                }],
                "agent_output": {"content": "image inspected"},
            }],
        }
        snapshot = build_evidence_snapshot(
            native_run,
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-native",
            case_id="case-native",
            scenario_id="A2-S031",
            created_at="2026-07-11T00:00:00Z",
            required_modalities=["text", "image"],
            source_schema_version="ashr.clone.run_result.v1",
        )
        self.assertEqual(snapshot["completeness"], "evidence_missing")
        self.assertEqual(snapshot["validation_errors"], [])
        self.assertEqual(snapshot["tool_call_count"], 1)
        self.assertEqual(snapshot["artifact_modalities"], ["image"])
        self.assertEqual(snapshot["observed_modalities"], ["text"])
        self.assertEqual(snapshot["missing_modalities"], ["image"])

        invalid = deepcopy(native_run)
        invalid["cases"][0]["observations"][0]["case_id"] = "other-case"
        invalid["trace_completeness"] = 0.5
        invalid_snapshot = build_evidence_snapshot(
            invalid,
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-native",
            case_id="case-native",
            scenario_id="A2-S031",
            created_at="2026-07-11T00:00:00Z",
        )
        self.assertEqual(invalid_snapshot["completeness"], "invalid")
        self.assertEqual(
            invalid_snapshot["validation_errors"],
            ["observation_case_id_mismatch", "trace_incomplete"],
        )

    def test_hard_blocker_or_abstain_cannot_allow(self):
        snapshot = self._complete_text_snapshot()
        with self.assertRaisesRegex(ValueError, "hard blockers or abstentions"):
            build_decision_record(
                snapshot,
                decision="allow",
                release_gate_report={"decision": "block"},
                judge_results=[{"judge_id": "semantic", "judge_version": "1", "outcome": "abstain"}],
                policy_version="unit",
                policy_hash=stable_hash({"policy": "unit"}),
                model_versions=["unit:model"],
                created_at="2026-07-11T00:00:00Z",
            )

    def test_decision_record_binds_provider_provenance_and_rejects_cross_scope_or_blocked_allow(self):
        snapshot = self._complete_text_snapshot()
        scope = {
            field: snapshot[field]
            for field in ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
        }
        provenance = {
            "schema_version": "a2.provider_provenance_handoff.v1",
            "status": "ready",
            "tenant_scope": scope,
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_hash": snapshot["snapshot_hash"],
            "logical_call_id": stable_hash("provider-call"),
            "provider_id": "dashscope",
            "model_id": "qwen-vl",
            "evaluation_eligible": True,
            "release_authority": False,
            "decision_authority": "a2.release_gate.v1",
            "blockers": [],
            "raw_payload_included": False,
            "secret_included": False,
        }
        record = build_decision_record(
            snapshot,
            decision="block",
            release_gate_report={"decision": "block"},
            judge_results=[],
            provider_provenance=[provenance],
            policy_version="1",
            policy_hash=stable_hash("policy"),
            model_versions=["dashscope:qwen-vl"],
            created_at="2026-07-11T00:00:00Z",
        )
        self.assertEqual(record["provider_summary"]["providers"], ["dashscope"])
        self.assertEqual(record["provider_summary"]["models"], ["qwen-vl"])
        self.assertEqual(record["provider_summary"]["blocked_call_count"], 0)
        self.assertEqual(record["provider_provenance_hashes"], [stable_hash(redact_payload(provenance))])

        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            build_decision_record(
                snapshot,
                decision="block",
                release_gate_report={"decision": "block"},
                judge_results=[],
                provider_provenance=[{**provenance, "tenant_scope": {**scope, "project_id": "other"}}],
                policy_version="1",
                policy_hash=stable_hash("policy"),
                model_versions=["dashscope:qwen-vl"],
                created_at="2026-07-11T00:00:00Z",
            )

        blocked = {
            **provenance,
            "status": "blocked",
            "evaluation_eligible": False,
            "blockers": ["timeout"],
        }
        with self.assertRaisesRegex(ValueError, "blocked provider provenance"):
            build_decision_record(
                snapshot,
                decision="allow",
                release_gate_report={"decision": "pass"},
                judge_results=[],
                provider_provenance=[blocked],
                policy_version="1",
                policy_hash=stable_hash("policy"),
                model_versions=["dashscope:qwen-vl"],
                created_at="2026-07-11T00:00:00Z",
            )

    def _complete_text_snapshot(self):
        return build_evidence_snapshot(
            {"final_response": "release evidence", "tool_calls": []},
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-text",
            case_id="case-text",
            scenario_id="A2-S001",
            created_at="2026-07-11T00:00:00Z",
            required_modalities=["text"],
        )

    def test_ledger_rejects_tampering_and_cross_tenant_records(self):
        ledger = load_json(HANDOFF)["decision_ledger"]
        schema = load_json(LEDGER_SCHEMA)
        record = ledger["records"][0]

        self.assertEqual(schema["properties"]["schema_version"]["const"], ledger["schema_version"])
        self.assertEqual(record["previous_record_hash"], GENESIS_HASH)
        self.assertEqual(ledger["head_hash"], record["record_hash"])
        self.assertTrue(ledger["metadata"]["append_only"])
        self.assertTrue(ledger["metadata"]["chain_verified"])

        tampered = deepcopy(record)
        tampered["decision"] = "allow"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            build_decision_ledger(
                [tampered],
                ledger_id="tampered",
                organization_id=record["organization_id"],
                tenant_id=record["tenant_id"],
                workspace_id=record["workspace_id"],
                project_id=record["project_id"],
                environment_id=record["environment_id"],
                created_at="2026-07-11T00:00:00Z",
            )

        cross_tenant = deepcopy(record)
        cross_tenant["tenant_id"] = "tenant-b"
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            build_decision_ledger(
                [cross_tenant],
                ledger_id="cross-tenant",
                organization_id=record["organization_id"],
                tenant_id=record["tenant_id"],
                workspace_id=record["workspace_id"],
                project_id=record["project_id"],
                environment_id=record["environment_id"],
                created_at="2026-07-11T00:00:00Z",
            )

    def test_a3_consumption_is_provenance_bound_and_public_safe(self):
        handoff = load_json(HANDOFF)
        decision = handoff["decision_ledger"]["records"][0]
        consumption = handoff["a3_consumption"]
        handoff_text = HANDOFF.read_text(encoding="utf-8")

        self.assertFalse(consumption["release_ready"])
        self.assertTrue(consumption["decision_record_required"])
        self.assertFalse(consumption["may_recompute_grade"])
        self.assertEqual(consumption["display_decision"], decision["decision"])
        self.assertEqual(consumption["display_provenance_hash"], decision["record_hash"])
        self.assertFalse(handoff["metadata"]["raw_evidence_included"])
        for pattern in SECRET_PATTERNS:
            self.assertIsNone(pattern.search(handoff_text), pattern.pattern)


if __name__ == "__main__":
    unittest.main()
