import json
import re
import unittest
from copy import deepcopy
from pathlib import Path

from services.judge.result_persistence import stable_hash
from services.judge.trusted_spine import (
    GENESIS_HASH,
    build_decision_ledger,
    build_decision_record,
    build_evidence_snapshot,
    build_trusted_spine_handoff,
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
    def test_handoff_fixture_matches_builder(self):
        actual = build_trusted_spine_handoff(
            load_json(RUN_FIXTURE),
            load_json(GRADE_FIXTURE),
            load_json(RELEASE_GATE),
        )
        self.assertEqual(actual, load_json(HANDOFF))

    def test_evidence_snapshot_freezes_image_and_text_without_raw_content(self):
        handoff = load_json(HANDOFF)
        snapshot = handoff["evidence_snapshot"]
        schema = load_json(EVIDENCE_SCHEMA)

        self.assertEqual(schema["properties"]["schema_version"]["const"], snapshot["schema_version"])
        self.assertEqual(snapshot["completeness"], "complete")
        self.assertEqual(snapshot["required_modalities"], ["image", "text"])
        self.assertEqual(snapshot["observed_modalities"], ["image", "text"])
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
            tenant_id="tenant-a",
            project_id="project-a",
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

    def test_hard_blocker_or_abstain_cannot_allow(self):
        snapshot = load_json(HANDOFF)["evidence_snapshot"]
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
                tenant_id=record["tenant_id"],
                project_id=record["project_id"],
                created_at="2026-07-11T00:00:00Z",
            )

        cross_tenant = deepcopy(record)
        cross_tenant["tenant_id"] = "tenant-b"
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            build_decision_ledger(
                [cross_tenant],
                ledger_id="cross-tenant",
                tenant_id=record["tenant_id"],
                project_id=record["project_id"],
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
