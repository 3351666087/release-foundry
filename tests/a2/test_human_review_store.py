import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import jsonschema

from services.judge.human_review_store import (
    build_review_resolution_handoff,
    claim_review_case,
    claim_review_resolution_outbox,
    get_authoritative_review_resolution,
    open_review_case,
    resolve_arbitration,
    settle_review_resolution_outbox,
    submit_review,
)
from services.judge.sql_store import initialize_sql_store


SCOPE = {
    "organization_id": "org-a", "tenant_id": "tenant-a", "workspace_id": "workspace-a",
    "project_id": "project-a", "environment_id": "test",
}
ROOT = Path(__file__).resolve().parents[2]


class HumanReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        initialize_sql_store(self.db)
        self._decision("machine", "block")
        self._decision("human", "allow")

    def tearDown(self):
        self.db.close()

    def _decision(self, record_id, decision):
        self.db.execute(
            """
            INSERT INTO a2_release_decisions VALUES (
              ?, ?, ?, ?, ?, ?, ?, 'run', 'case', 'scenario', ?, ?, 'snapshot',
              'snapshot-hash', 'provider-hash', 'judge-hash', 'gate-hash', 'previous',
              ?, 'ledger', 'ledger-hash', 'request-hash', '2026-07-12T00:00:00Z', 1
            )
            """,
            (
                record_id, f"key-{record_id}", SCOPE["organization_id"], SCOPE["tenant_id"],
                SCOPE["workspace_id"], SCOPE["project_id"], SCOPE["environment_id"],
                decision, int(decision == "review"), f"record-hash-{record_id}",
            ),
        )
        self.db.commit()

    def _open(self):
        return open_review_case(
            self.db, scope=SCOPE, record_id="machine", reason_code="judge_disagreement",
            created_at="2026-07-12T00:00:00Z",
        )

    def test_overturn_preserves_machine_decision_and_creates_governed_candidate(self):
        review = self._open()
        lease = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="reviewer-hash",
            now="2026-07-12T00:01:00Z",
        )
        result = submit_review(
            self.db, lease=lease, scope=SCOPE, outcome="overturn", reason_code="false_positive",
            superseding_record_id="human", submitted_at="2026-07-12T00:02:00Z",
            learning={
                "consent_id_hash": "consent-hash", "purpose": "judge_calibration",
                "lineage_hash": "lineage-hash", "residency": "cn",
                "retention_until": "2027-07-12T00:00:00Z", "deletion_key_hash": "delete-hash",
            },
        )
        self.assertEqual(
            self.db.execute("SELECT decision FROM a2_release_decisions WHERE record_id='machine'").fetchone()[0],
            "block",
        )
        candidate = self.db.execute("SELECT * FROM a2_learning_candidates").fetchone()
        self.assertEqual(candidate["cross_tenant_allowed"], 0)
        self.assertEqual(result["superseding_record_id"], "human")

    def test_active_lease_blocks_competing_reviewer_and_expired_lease_is_fenced(self):
        review = self._open()
        stale = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="one",
            now="2026-07-12T00:00:00Z", lease_seconds=60,
        )
        with self.assertRaisesRegex(ValueError, "contention"):
            claim_review_case(
                self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="two",
                now="2026-07-12T00:00:30Z",
            )
        fresh = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="two",
            now="2026-07-12T00:02:00Z",
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            submit_review(
                self.db, lease=stale, scope=SCOPE, outcome="confirm", reason_code="agreed",
                submitted_at="2026-07-12T00:02:10Z",
            )
        submit_review(
            self.db, lease=fresh, scope=SCOPE, outcome="confirm", reason_code="agreed",
            submitted_at="2026-07-12T00:02:10Z",
        )

    def test_learning_requires_complete_governance_and_tenant_scope(self):
        review = self._open()
        lease = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="reviewer",
            now="2026-07-12T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "incomplete"):
            submit_review(
                self.db, lease=lease, scope=SCOPE, outcome="confirm", reason_code="agreed",
                submitted_at="2026-07-12T00:00:10Z", learning={"purpose": "judge_calibration"},
            )
        wrong = {**SCOPE, "tenant_id": "tenant-b"}
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            claim_review_case(
                self.db, review_id=review["review_id"], scope=wrong, reviewer_id_hash="other",
                now="2026-07-12T00:00:20Z",
            )

    def test_escalation_cannot_be_used_as_learning_label(self):
        review = self._open()
        lease = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="reviewer",
            now="2026-07-12T00:00:00Z",
        )
        result = submit_review(
            self.db, lease=lease, scope=SCOPE, outcome="escalate", reason_code="ambiguous",
            submitted_at="2026-07-12T00:00:10Z",
            learning={
                "consent_id_hash": "consent", "purpose": "judge_calibration",
                "lineage_hash": "lineage", "residency": "cn",
                "retention_until": "2027-01-01T00:00:00Z", "deletion_key_hash": "delete",
            },
        )
        self.assertEqual(result["status"], "arbitration")
        self.assertEqual(result["approval_count"], 0)
        self.assertEqual(result["disposition_count"], 1)
        self.assertIsNone(result["learning_candidate"])

    def test_confirmed_machine_block_is_authoritative_but_not_release_ready(self):
        review = self._open()
        lease = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="reviewer",
            now="2026-07-12T00:00:00Z",
        )
        submit_review(
            self.db, lease=lease, scope=SCOPE, outcome="confirm", reason_code="agreed",
            submitted_at="2026-07-12T00:00:10Z",
        )

        authority = get_authoritative_review_resolution(
            self.db, review_id=review["review_id"], scope=SCOPE
        )
        self.assertTrue(authority["release_authority"])
        self.assertEqual(authority["effective_decision"], "block")
        self.assertFalse(authority["release_ready"])
        event = self.db.execute(
            "SELECT * FROM a2_review_resolution_outbox WHERE review_id = ?",
            (review["review_id"],),
        ).fetchone()
        self.assertEqual(event["delivery_status"], "pending")
        self.assertEqual(event["automatic_unblock"], 0)
        handoff = build_review_resolution_handoff(
            self.db, event_id=event["event_id"], scope=SCOPE
        )
        schema = json.loads(
            (ROOT / "docs/a2/schemas/human_review_resolution.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(handoff)
        self.assertEqual(handoff["effective_decision"], "block")
        self.assertFalse(handoff["release_ready"])
        self.assertFalse(handoff["automatic_unblock"])
        self.assertFalse(handoff["raw_evidence_included"])
        self.assertFalse(handoff["review_reason_included"])

    def test_review_resolution_outbox_is_scoped_retryable_and_fenced(self):
        review = self._open()
        lease = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="reviewer",
            now="2026-07-12T00:00:00Z",
        )
        submit_review(
            self.db, lease=lease, scope=SCOPE, outcome="confirm", reason_code="agreed",
            submitted_at="2026-07-12T00:00:10Z",
        )
        claimed = claim_review_resolution_outbox(
            self.db, worker_id="dispatcher-a", now="2026-07-12T00:00:20Z",
            lease_seconds=10,
        )
        self.assertEqual(claimed["attempt_count"], 1)
        takeover = claim_review_resolution_outbox(
            self.db, worker_id="dispatcher-b", now="2026-07-12T00:00:31Z",
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            settle_review_resolution_outbox(
                self.db, event_id=claimed["event_id"], worker_id="dispatcher-a",
                lease_generation=claimed["lease_generation"], settled_at="2026-07-12T00:00:32Z",
                outcome="delivered",
            )
        settle_review_resolution_outbox(
            self.db, event_id=takeover["event_id"], worker_id="dispatcher-b",
            lease_generation=takeover["lease_generation"], settled_at="2026-07-12T00:00:32Z",
            outcome="retry", retry_at="2026-07-12T00:01:00Z", error_class="a3_unavailable",
        )
        self.assertIsNone(
            claim_review_resolution_outbox(
                self.db, worker_id="dispatcher-c", now="2026-07-12T00:00:59Z"
            )
        )
        retry = claim_review_resolution_outbox(
            self.db, worker_id="dispatcher-c", now="2026-07-12T00:01:00Z"
        )
        settle_review_resolution_outbox(
            self.db, event_id=retry["event_id"], worker_id="dispatcher-c",
            lease_generation=retry["lease_generation"], settled_at="2026-07-12T00:01:01Z",
            outcome="delivered",
        )
        self.assertIsNone(
            claim_review_resolution_outbox(
                self.db, worker_id="dispatcher-d", now="2026-07-12T00:02:00Z"
            )
        )
        wrong_scope = {**SCOPE, "tenant_id": "tenant-b"}
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            build_review_resolution_handoff(
                self.db, event_id=retry["event_id"], scope=wrong_scope
            )

    def test_dead_letter_tamper_and_arbitration_handoff_fail_closed(self):
        review = open_review_case(
            self.db, scope=SCOPE, record_id="machine", reason_code="high_risk_conflict",
            required_approvals=2, created_at="2026-07-12T00:00:00Z",
        )
        first = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE,
            reviewer_id_hash="reviewer-one", now="2026-07-12T00:01:00Z",
        )
        submit_review(
            self.db, lease=first, scope=SCOPE, outcome="confirm", reason_code="agree",
            submitted_at="2026-07-12T00:02:00Z",
        )
        second = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE,
            reviewer_id_hash="reviewer-two", now="2026-07-12T00:03:00Z",
        )
        submit_review(
            self.db, lease=second, scope=SCOPE, outcome="overturn", reason_code="disagree",
            superseding_record_id="human", submitted_at="2026-07-12T00:04:00Z",
        )
        resolution = resolve_arbitration(
            self.db, review_id=review["review_id"], scope=SCOPE,
            arbitrator_id_hash="arbitrator", arbitrator_role="release_arbitrator",
            final_outcome="overturn", superseding_record_id="human",
            resolved_at="2026-07-12T00:05:00Z",
        )
        event = self.db.execute(
            "SELECT * FROM a2_review_resolution_outbox WHERE review_id = ?",
            (review["review_id"],),
        ).fetchone()
        payload = build_review_resolution_handoff(
            self.db, event_id=event["event_id"], scope=SCOPE
        )
        schema = json.loads(
            (ROOT / "docs/a2/schemas/human_review_resolution.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(schema).validate(payload)
        self.assertEqual(payload["resolution_type"], "arbitration")
        self.assertEqual(payload["final_outcome"], "overturn")
        self.assertEqual(payload["effective_record_id"], "human")
        self.assertEqual(payload["effective_decision"], "allow")
        self.assertTrue(payload["release_ready"])
        self.assertEqual(payload["resolution_hash"], resolution["resolution_hash"])

        claimed = claim_review_resolution_outbox(
            self.db, worker_id="dispatcher", now="2026-07-12T00:06:00Z"
        )
        settle_review_resolution_outbox(
            self.db, event_id=claimed["event_id"], worker_id="dispatcher",
            lease_generation=claimed["lease_generation"], settled_at="2026-07-12T00:06:01Z",
            outcome="dead", error_class="contract_rejected",
        )
        self.assertIsNone(
            claim_review_resolution_outbox(
                self.db, worker_id="dispatcher-two", now="2026-07-13T00:00:00Z"
            )
        )

        self.db.execute(
            "UPDATE a2_review_resolution_outbox SET payload_hash = ? WHERE event_id = ?",
            ("sha256:" + ("0" * 64), event["event_id"]),
        )
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "payload mismatch"):
            build_review_resolution_handoff(
                self.db, event_id=event["event_id"], scope=SCOPE
            )

    def test_resolution_and_outbox_are_one_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            connection = sqlite3.connect(Path(directory) / "review.sqlite")
            try:
                connection.row_factory = sqlite3.Row
                initialize_sql_store(connection)
                self._copy_decisions(connection)
                review = open_review_case(
                    connection, scope=SCOPE, record_id="machine", reason_code="judge_disagreement",
                    created_at="2026-07-12T00:00:00Z",
                )
                lease = claim_review_case(
                    connection, review_id=review["review_id"], scope=SCOPE,
                    reviewer_id_hash="reviewer", now="2026-07-12T00:00:01Z",
                )
                connection.execute(
                    """
                    CREATE TRIGGER reject_review_resolution_outbox
                    BEFORE INSERT ON a2_review_resolution_outbox
                    BEGIN SELECT RAISE(ABORT, 'outbox rejected'); END
                    """
                )
                with self.assertRaisesRegex(sqlite3.IntegrityError, "outbox rejected"):
                    submit_review(
                        connection, lease=lease, scope=SCOPE, outcome="confirm",
                        reason_code="agreed", submitted_at="2026-07-12T00:00:02Z",
                    )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM a2_review_events").fetchone()[0], 0
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM a2_review_resolutions").fetchone()[0], 0
                )
            finally:
                connection.close()

    def test_high_risk_review_requires_two_distinct_matching_approvals(self):
        review = open_review_case(
            self.db, scope=SCOPE, record_id="machine", reason_code="high_risk_override",
            required_approvals=2, created_at="2026-07-12T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "approval requirement conflicts"):
            open_review_case(
                self.db, scope=SCOPE, record_id="machine", reason_code="high_risk_override",
                required_approvals=1, created_at="2026-07-12T00:00:01Z",
            )
        first = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="reviewer-one",
            now="2026-07-12T00:01:00Z",
        )
        first_result = submit_review(
            self.db, lease=first, scope=SCOPE, outcome="overturn", reason_code="false_positive",
            superseding_record_id="human", submitted_at="2026-07-12T00:02:00Z",
        )
        self.assertEqual(first_result["status"], "open")
        self.assertIsNone(first_result["learning_candidate"])
        with self.assertRaisesRegex(ValueError, "already submitted"):
            claim_review_case(
                self.db, review_id=review["review_id"], scope=SCOPE,
                reviewer_id_hash="reviewer-one", now="2026-07-12T00:03:00Z",
            )
        second = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="reviewer-two",
            now="2026-07-12T00:03:00Z",
        )
        result = submit_review(
            self.db, lease=second, scope=SCOPE, outcome="overturn", reason_code="false_positive",
            superseding_record_id="human", submitted_at="2026-07-12T00:04:00Z",
            learning={
                "consent_id_hash": "consent", "purpose": "judge_calibration",
                "lineage_hash": "lineage", "residency": "cn",
                "retention_until": "2027-01-01T00:00:00Z", "deletion_key_hash": "delete",
            },
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["approval_count"], 2)
        authority = get_authoritative_review_resolution(
            self.db, review_id=review["review_id"], scope=SCOPE
        )
        self.assertTrue(authority["release_authority"])
        self.assertEqual(authority["resolution_type"], "review_consensus")
        self.assertEqual(authority["superseding_record_id"], "human")
        self.assertEqual(authority["effective_decision"], "allow")
        self.assertTrue(authority["release_ready"])
        self.assertEqual(
            self.db.execute(
                "SELECT release_authority FROM a2_review_events WHERE review_id = ? LIMIT 1",
                (review["review_id"],),
            ).fetchone()[0],
            0,
        )

    def test_conflicting_high_risk_votes_require_arbitration_and_block_learning(self):
        review = open_review_case(
            self.db, scope=SCOPE, record_id="machine", reason_code="high_risk_conflict",
            required_approvals=2, created_at="2026-07-12T00:00:00Z",
        )
        first = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="one",
            now="2026-07-12T00:01:00Z",
        )
        submit_review(
            self.db, lease=first, scope=SCOPE, outcome="confirm", reason_code="agree",
            submitted_at="2026-07-12T00:02:00Z",
        )
        second = claim_review_case(
            self.db, review_id=review["review_id"], scope=SCOPE, reviewer_id_hash="two",
            now="2026-07-12T00:03:00Z",
        )
        result = submit_review(
            self.db, lease=second, scope=SCOPE, outcome="overturn", reason_code="disagree",
            superseding_record_id="human", submitted_at="2026-07-12T00:04:00Z",
            learning={
                "consent_id_hash": "consent", "purpose": "judge_calibration",
                "lineage_hash": "lineage", "residency": "cn",
                "retention_until": "2027-01-01T00:00:00Z", "deletion_key_hash": "delete",
            },
        )
        self.assertEqual(result["status"], "arbitration")
        self.assertEqual(
            result["learning_blocked_reason"],
            "review_not_completed_or_conflict_requires_arbitration",
        )
        self.assertEqual(
            self.db.execute(
                "SELECT status FROM a2_review_cases WHERE review_id = ?", (review["review_id"],)
            ).fetchone()[0],
            "arbitration",
        )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM a2_review_events WHERE review_id = ?", (review["review_id"],)
            ).fetchone()[0],
            2,
        )
        self.assertEqual(
            self.db.execute(
                """
                SELECT COUNT(*)
                FROM a2_learning_candidates AS candidate
                JOIN a2_review_events AS event
                  ON event.event_id = candidate.review_event_id
                WHERE event.review_id = ?
                """,
                (review["review_id"],),
            ).fetchone()[0],
            0,
        )
        with self.assertRaisesRegex(ValueError, "review case is arbitration"):
            claim_review_case(
                self.db, review_id=review["review_id"], scope=SCOPE,
                reviewer_id_hash="three", now="2026-07-12T00:05:00Z",
            )
        self.assertIsNone(
            get_authoritative_review_resolution(
                self.db, review_id=review["review_id"], scope=SCOPE
            )
        )
        with self.assertRaisesRegex(ValueError, "role"):
            resolve_arbitration(
                self.db, review_id=review["review_id"], scope=SCOPE,
                arbitrator_id_hash="arb", arbitrator_role="reviewer",
                final_outcome="confirm", resolved_at="2026-07-12T00:06:00Z",
            )
        with self.assertRaisesRegex(ValueError, "independent"):
            resolve_arbitration(
                self.db, review_id=review["review_id"], scope=SCOPE,
                arbitrator_id_hash="one", arbitrator_role="release_arbitrator",
                final_outcome="confirm", resolved_at="2026-07-12T00:06:00Z",
            )
        resolution = resolve_arbitration(
            self.db, review_id=review["review_id"], scope=SCOPE,
            arbitrator_id_hash="arb", arbitrator_role="release_arbitrator",
            final_outcome="overturn", superseding_record_id="human",
            resolved_at="2026-07-12T00:06:00Z",
        )
        self.assertTrue(resolution["release_authority"])
        self.assertEqual(resolution["resolution_type"], "arbitration")
        authority = get_authoritative_review_resolution(
            self.db, review_id=review["review_id"], scope=SCOPE
        )
        self.assertEqual(authority["resolution_hash"], resolution["resolution_hash"])
        self.assertEqual(authority["effective_record_id"], "human")
        self.assertTrue(authority["release_ready"])
        with self.assertRaisesRegex(ValueError, "not awaiting arbitration"):
            resolve_arbitration(
                self.db, review_id=review["review_id"], scope=SCOPE,
                arbitrator_id_hash="other-arb", arbitrator_role="release_arbitrator",
                final_outcome="confirm", resolved_at="2026-07-12T00:07:00Z",
            )

    def _copy_decisions(self, connection):
        for record_id, decision in (("machine", "block"), ("human", "allow")):
            connection.execute(
                """
                INSERT INTO a2_release_decisions VALUES (
                  ?, ?, ?, ?, ?, ?, ?, 'run', 'case', 'scenario', ?, ?, 'snapshot',
                  'snapshot-hash', 'provider-hash', 'judge-hash', 'gate-hash', 'previous',
                  ?, 'ledger', 'ledger-hash', 'request-hash', '2026-07-12T00:00:00Z', 1
                )
                """,
                (
                    record_id, f"key-{record_id}", SCOPE["organization_id"], SCOPE["tenant_id"],
                    SCOPE["workspace_id"], SCOPE["project_id"], SCOPE["environment_id"],
                    decision, int(decision == "review"), f"record-hash-{record_id}",
                ),
            )
        connection.commit()


if __name__ == "__main__":
    unittest.main()
