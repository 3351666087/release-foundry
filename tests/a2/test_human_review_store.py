import sqlite3
import unittest

from services.judge.human_review_store import (
    claim_review_case,
    get_authoritative_review_resolution,
    open_review_case,
    resolve_arbitration,
    submit_review,
)
from services.judge.sql_store import initialize_sql_store


SCOPE = {
    "organization_id": "org-a", "tenant_id": "tenant-a", "workspace_id": "workspace-a",
    "project_id": "project-a", "environment_id": "test",
}


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


if __name__ == "__main__":
    unittest.main()
