import sqlite3
import unittest

from services.judge.result_persistence import stable_hash
from services.judge.sql_store import initialize_sql_store
from services.judge.teacher_acquisition_queue import (
    claim_teacher_acquisition,
    enqueue_teacher_acquisition,
    enqueue_preference_teacher_acquisition,
    get_teacher_acquisition,
    settle_teacher_acquisition,
)


SCOPE = {
    "organization_id": "org-a",
    "tenant_id": "tenant-a",
    "workspace_id": "workspace-a",
    "project_id": "project-a",
    "environment_id": "test",
}
OTHER_SCOPE = {**SCOPE, "tenant_id": "tenant-b"}


class TeacherAcquisitionQueueTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        initialize_sql_store(self.db)

    def tearDown(self):
        self.db.close()

    def _enqueue(
        self,
        *,
        scope=SCOPE,
        pair_id="pair-a",
        teacher_id="releasefoundry",
        request_payload=None,
        idempotency_key="paid-call-a",
        priority_score=50,
        max_cost_usd=1,
        max_attempts=1,
        created_at="2026-07-12T00:00:00Z",
    ):
        return enqueue_teacher_acquisition(
            self.db,
            scope=scope,
            pair_id=pair_id,
            teacher_id=teacher_id,
            request_hash=stable_hash(request_payload or {"pair_id": pair_id}),
            idempotency_key=idempotency_key,
            priority_score=priority_score,
            max_cost_usd=max_cost_usd,
            max_attempts=max_attempts,
            created_at=created_at,
        )

    def test_enqueue_is_idempotent_and_does_not_store_raw_paid_key(self):
        first = self._enqueue()
        replay = self._enqueue()

        self.assertEqual(first["queue_id"], replay["queue_id"])
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        self.assertNotIn("paid-call-a", str(replay))
        stored = self.db.execute(
            "SELECT * FROM a2_teacher_acquisition_queue WHERE queue_id = ?",
            (first["queue_id"],),
        ).fetchone()
        self.assertNotIn("paid-call-a", str(dict(stored)))
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM a2_teacher_acquisition_queue").fetchone()[0],
            1,
        )

        with self.assertRaisesRegex(ValueError, "idempotency_key_reuse_conflict"):
            self._enqueue(request_payload={"changed": True})

    def test_preference_bridge_uses_active_learning_score_and_hashes_payload(self):
        pair = {
            "pair_id": stable_hash({"pair": "a2-sample-1"}),
            "status": "review_required",
            "training_eligible": False,
            "review_required": True,
            "releasefoundry_provisional_preference": {
                "chosen_candidate_id": "candidate-a",
                "rejected_candidate_id": "candidate-b",
            },
            "active_learning": {"score": 87.5},
        }
        payload = {
            "dataset_identity_hash": stable_hash({"dataset": "fixed-six"}),
            "case_id": "a2-sample-1",
            "private_token": "must-not-enter-queue-row",
        }
        first = enqueue_preference_teacher_acquisition(
            self.db,
            scope=SCOPE,
            preference_pair=pair,
            teacher_id="releasefoundry",
            request_payload=payload,
            max_cost_usd=2,
            created_at="2026-07-12T00:00:00Z",
        )
        replay = enqueue_preference_teacher_acquisition(
            self.db,
            scope=SCOPE,
            preference_pair=pair,
            teacher_id="releasefoundry",
            request_payload=payload,
            max_cost_usd=2,
            created_at="2026-07-12T00:00:00Z",
        )

        self.assertEqual(first["priority_score"], 87.5)
        self.assertEqual(first["request_hash"], stable_hash(payload))
        self.assertEqual(first["queue_id"], replay["queue_id"])
        self.assertTrue(replay["idempotent_replay"])
        stored = self.db.execute(
            "SELECT * FROM a2_teacher_acquisition_queue WHERE queue_id = ?",
            (first["queue_id"],),
        ).fetchone()
        self.assertNotIn("must-not-enter-queue-row", str(dict(stored)))

    def test_preference_bridge_rejects_non_provisional_or_unresolved_pairs(self):
        pair = {
            "pair_id": stable_hash({"pair": "a2-sample-2"}),
            "status": "blocked",
            "training_eligible": False,
            "review_required": True,
            "releasefoundry_provisional_preference": {
                "chosen_candidate_id": "candidate-a",
                "rejected_candidate_id": "candidate-b",
            },
            "active_learning": {"score": 90},
        }
        with self.assertRaisesRegex(ValueError, "not_reviewable"):
            enqueue_preference_teacher_acquisition(
                self.db,
                scope=SCOPE,
                preference_pair=pair,
                teacher_id="releasefoundry",
                request_payload={"case_id": "blocked"},
                max_cost_usd=1,
                created_at="2026-07-12T00:00:00Z",
            )

    def test_claim_orders_by_priority_and_isolated_by_scope(self):
        low = self._enqueue(pair_id="low", idempotency_key="low", priority_score=10)
        high = self._enqueue(pair_id="high", idempotency_key="high", priority_score=90)
        other = self._enqueue(
            scope=OTHER_SCOPE,
            pair_id="other",
            idempotency_key="other",
            priority_score=100,
        )

        claimed = claim_teacher_acquisition(
            self.db, scope=SCOPE, worker_id="worker-a", now="2026-07-12T00:01:00Z"
        )
        self.assertEqual(claimed["queue_id"], high["queue_id"])
        self.assertNotEqual(claimed["queue_id"], other["queue_id"])
        settle_teacher_acquisition(
            self.db,
            queue_id=claimed["queue_id"],
            scope=SCOPE,
            worker_id="worker-a",
            lease_generation=claimed["lease_generation"],
            settled_at="2026-07-12T00:02:00Z",
            outcome="completed",
            receipt_hash=stable_hash({"receipt": "high"}),
            actual_cost_usd=0.25,
        )
        next_claim = claim_teacher_acquisition(
            self.db, scope=SCOPE, worker_id="worker-a", now="2026-07-12T00:03:00Z"
        )
        self.assertEqual(next_claim["queue_id"], low["queue_id"])

    def test_claim_compares_timezone_offsets_by_instant(self):
        queued = self._enqueue()
        self.db.execute(
            """
            UPDATE a2_teacher_acquisition_queue
            SET available_at = ?, created_at = ?
            WHERE queue_id = ?
            """,
            (
                "2026-07-12T00:01:00-05:00",
                "2026-07-12T00:00:00-05:00",
                queued["queue_id"],
            ),
        )
        self.db.commit()

        self.assertIsNone(
            claim_teacher_acquisition(
                self.db,
                scope=SCOPE,
                worker_id="worker",
                now="2026-07-12T05:00:59Z",
            )
        )
        claimed = claim_teacher_acquisition(
            self.db,
            scope=SCOPE,
            worker_id="worker",
            now="2026-07-12T05:01:00Z",
        )
        self.assertEqual(claimed["queue_id"], queued["queue_id"])

    def test_expired_lease_is_reclaimed_and_stale_worker_is_fenced(self):
        queued = self._enqueue(max_attempts=3)
        first = claim_teacher_acquisition(
            self.db,
            scope=SCOPE,
            worker_id="worker-a",
            now="2026-07-12T00:00:00Z",
            lease_seconds=10,
        )
        second = claim_teacher_acquisition(
            self.db,
            scope=SCOPE,
            worker_id="worker-b",
            now="2026-07-12T00:00:11Z",
            lease_seconds=10,
        )
        self.assertEqual(second["queue_id"], queued["queue_id"])
        self.assertEqual(second["lease_generation"], first["lease_generation"] + 1)
        with self.assertRaisesRegex(ValueError, "stale_queue_fencing_generation"):
            settle_teacher_acquisition(
                self.db,
                queue_id=first["queue_id"],
                scope=SCOPE,
                worker_id="worker-a",
                lease_generation=first["lease_generation"],
                settled_at="2026-07-12T00:00:12Z",
                outcome="completed",
                receipt_hash=stable_hash({"receipt": "stale"}),
                actual_cost_usd=0.25,
            )

        result = settle_teacher_acquisition(
            self.db,
            queue_id=second["queue_id"],
            scope=SCOPE,
            worker_id="worker-b",
            lease_generation=second["lease_generation"],
            settled_at="2026-07-12T00:00:13Z",
            outcome="retry",
            retry_at="2026-07-12T00:01:00Z",
            error_class="provider_unavailable",
        )
        self.assertEqual(result["status"], "retry")

    def test_retry_time_must_be_later_than_settlement(self):
        queued = self._enqueue(max_attempts=2)
        lease = claim_teacher_acquisition(
            self.db,
            scope=SCOPE,
            worker_id="worker",
            now="2026-07-12T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "retry_at_must_be_later"):
            settle_teacher_acquisition(
                self.db,
                queue_id=queued["queue_id"],
                scope=SCOPE,
                worker_id="worker",
                lease_generation=lease["lease_generation"],
                settled_at="2026-07-12T00:00:30Z",
                outcome="retry",
                retry_at="2026-07-11T19:00:29-05:00",
                error_class="provider_unavailable",
            )
        row = self.db.execute(
            "SELECT status, lease_owner FROM a2_teacher_acquisition_queue WHERE queue_id = ?",
            (queued["queue_id"],),
        ).fetchone()
        self.assertEqual(row["status"], "leased")
        self.assertEqual(row["lease_owner"], "worker")

    def test_retry_is_explicit_and_exhaustion_fails_closed_to_dead(self):
        queued = self._enqueue(max_attempts=2)
        first = claim_teacher_acquisition(
            self.db, scope=SCOPE, worker_id="worker", now="2026-07-12T00:00:00Z"
        )
        retry = settle_teacher_acquisition(
            self.db,
            queue_id=queued["queue_id"],
            scope=SCOPE,
            worker_id="worker",
            lease_generation=first["lease_generation"],
            settled_at="2026-07-12T00:00:01Z",
            outcome="retry",
            retry_at="2026-07-12T00:01:00Z",
            error_class="rate_limited",
        )
        self.assertEqual(retry["status"], "retry")
        second = claim_teacher_acquisition(
            self.db, scope=SCOPE, worker_id="worker", now="2026-07-12T00:01:00Z"
        )
        exhausted = settle_teacher_acquisition(
            self.db,
            queue_id=queued["queue_id"],
            scope=SCOPE,
            worker_id="worker",
            lease_generation=second["lease_generation"],
            settled_at="2026-07-12T00:01:01Z",
            outcome="retry",
            retry_at="2026-07-12T00:02:00Z",
            error_class="rate_limited",
        )
        self.assertEqual(exhausted["status"], "dead")
        self.assertEqual(exhausted["last_error_class"], "max_attempts_exhausted")
        self.assertIsNone(
            claim_teacher_acquisition(
                self.db, scope=SCOPE, worker_id="worker", now="2026-07-12T00:02:00Z"
            )
        )

    def test_completion_requires_verified_receipt_and_respects_budget(self):
        queued = self._enqueue(max_cost_usd=0.5)
        lease = claim_teacher_acquisition(
            self.db, scope=SCOPE, worker_id="worker", now="2026-07-12T00:00:00Z"
        )
        with self.assertRaisesRegex(ValueError, "receipt_hash"):
            settle_teacher_acquisition(
                self.db,
                queue_id=queued["queue_id"],
                scope=SCOPE,
                worker_id="worker",
                lease_generation=lease["lease_generation"],
                settled_at="2026-07-12T00:00:01Z",
                outcome="completed",
                actual_cost_usd=0.25,
            )
        with self.assertRaisesRegex(ValueError, "exceeds_reserved_budget"):
            settle_teacher_acquisition(
                self.db,
                queue_id=queued["queue_id"],
                scope=SCOPE,
                worker_id="worker",
                lease_generation=lease["lease_generation"],
                settled_at="2026-07-12T00:00:01Z",
                outcome="completed",
                receipt_hash=stable_hash({"receipt": "over-budget"}),
                actual_cost_usd=0.75,
            )
        completed = settle_teacher_acquisition(
            self.db,
            queue_id=queued["queue_id"],
            scope=SCOPE,
            worker_id="worker",
            lease_generation=lease["lease_generation"],
            settled_at="2026-07-12T00:00:02Z",
            outcome="completed",
            receipt_hash=stable_hash({"receipt": "valid"}),
            actual_cost_usd=0.5,
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["actual_cost_usd"], 0.5)

    def test_scope_is_required_for_reads_and_settlement(self):
        queued = self._enqueue()
        with self.assertRaisesRegex(ValueError, "scope_mismatch"):
            get_teacher_acquisition(
                self.db, queue_id=queued["queue_id"], scope=OTHER_SCOPE
            )
        lease = claim_teacher_acquisition(
            self.db, scope=SCOPE, worker_id="worker", now="2026-07-12T00:00:00Z"
        )
        with self.assertRaisesRegex(ValueError, "scope_mismatch"):
            settle_teacher_acquisition(
                self.db,
                queue_id=queued["queue_id"],
                scope=OTHER_SCOPE,
                worker_id="worker",
                lease_generation=lease["lease_generation"],
                settled_at="2026-07-12T00:00:01Z",
                outcome="dead",
                error_class="scope_test",
            )


if __name__ == "__main__":
    unittest.main()
