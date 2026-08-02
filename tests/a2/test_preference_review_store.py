import hashlib
import sqlite3
import unittest

from services.judge.preference_learning import build_governed_preference_pair
from services.judge.preference_review_store import (
    claim_preference_review_case,
    get_authoritative_preference_review_resolution,
    open_preference_review_case,
    resolve_preference_arbitration,
    submit_preference_review,
)
from services.judge.sql_store import initialize_sql_store


SCOPE = {
    "organization_id": "org-a",
    "tenant_id": "tenant-a",
    "workspace_id": "workspace-a",
    "project_id": "project-a",
    "environment_id": "test",
}


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate(candidate_id: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "task_id": "task-1",
        "sample_id": "sample-1",
        "dataset_identity_hash": _hash("dataset"),
        "prompt_version": "prompt-v1",
        "prompt_hash": _hash("prompt"),
        "media_evidence_hashes": [_hash("image-1")],
        "model_version": f"model-{candidate_id}",
        "trace_hash": _hash(f"trace-{candidate_id}"),
        "final_answer_hash": _hash(f"answer-{candidate_id}"),
    }


def _evaluation(candidate_id: str, *, rank: int, reward: float, passed: bool) -> dict:
    failure_type = "none" if passed else "wrong_arguments"
    evidence_location = {} if passed else {"action_index": 0, "field": "city"}
    reason = "" if passed else "The required city argument was omitted."
    return {
        "candidate_id": candidate_id,
        "action_scores": [
            {
                "action_index": 0,
                "score": 1.0 if passed else 0.2,
                "passed": passed,
                "failure_type": failure_type,
                "evidence_location": evidence_location,
                "reason": reason,
            }
        ],
        "final_answer_score": 0.95 if passed else 0.25,
        "overall_reward": reward,
        "rank": rank,
        "failure_type": failure_type,
        "severity": "none" if passed else "high",
        "failure_action": "" if passed else "weather.lookup",
        "evidence_location": evidence_location,
        "failure_reason": reason,
        "confidence": 0.93,
        "receipt_hash": _hash(f"receipt-{candidate_id}"),
        "receipt_verified": True,
    }


def _pair() -> tuple[dict, list[dict], list[dict]]:
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    evaluations = [
        _evaluation("candidate-a", rank=1, reward=0.95, passed=True),
        _evaluation("candidate-b", rank=2, reward=0.2, passed=False),
    ]
    return build_governed_preference_pair(candidates, evaluations), candidates, evaluations


class PreferenceReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        initialize_sql_store(self.db)

    def tearDown(self):
        self.db.close()

    def _open(self, pair, *, required_approvals=1):
        return open_preference_review_case(
            self.db,
            scope=SCOPE,
            pair=pair,
            reason_code="releasefoundry_teacher_disagreement",
            created_at="2026-07-26T00:00:00Z",
            required_approvals=required_approvals,
        )

    def test_consensus_creates_human_gold_without_release_decision(self):
        pair, candidates, evaluations = _pair()
        review = self._open(pair)
        lease = claim_preference_review_case(
            self.db,
            review_id=review["review_id"],
            scope=SCOPE,
            reviewer_id_hash="reviewer-a",
            now="2026-07-26T00:01:00Z",
        )
        result = submit_preference_review(
            self.db,
            lease=lease,
            scope=SCOPE,
            pair=pair,
            outcome="confirm",
            chosen_candidate_id="candidate-a",
            rejected_candidate_id="candidate-b",
            reason_code="human_gold_confirmed",
            reviewer_receipt_hash=_hash("review-receipt"),
            submitted_at="2026-07-26T00:02:00Z",
            learning={
                "consent_id_hash": _hash("consent"),
                "purpose": "preference_optimization",
                "lineage_hash": _hash("lineage"),
                "residency": "cn",
                "retention_until": "2027-07-26T00:00:00Z",
                "deletion_key_hash": _hash("deletion"),
            },
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["resolution"]["preference_authority"], "human_gold")
        self.assertTrue(result["resolution"]["training_eligible"])
        self.assertEqual(
            result["resolution"]["human_adjudication"]["chosen_candidate_id"],
            "candidate-a",
        )
        self.assertIsNotNone(result["learning_candidate"])
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM a2_release_decisions").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM a2_preference_learning_candidates"
            ).fetchone()[0],
            1,
        )

        rebuilt = build_governed_preference_pair(
            candidates,
            evaluations,
            human_adjudication=result["resolution"]["human_adjudication"],
        )
        self.assertEqual(rebuilt["preference_authority"], "human_gold")
        self.assertTrue(rebuilt["training_eligible"])

    def test_pair_hash_and_scope_mismatch_fail_closed(self):
        pair, _, _ = _pair()
        tampered = {**pair, "status": "training_eligible"}
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self._open(tampered)

        review = self._open(pair)
        with self.assertRaisesRegex(ValueError, "scope mismatch"):
            claim_preference_review_case(
                self.db,
                review_id=review["review_id"],
                scope={**SCOPE, "tenant_id": "tenant-b"},
                reviewer_id_hash="reviewer-a",
                now="2026-07-26T00:01:00Z",
            )

        lease = claim_preference_review_case(
            self.db,
            review_id=review["review_id"],
            scope=SCOPE,
            reviewer_id_hash="reviewer-a",
            now="2026-07-26T00:01:00Z",
        )
        tampered_after_open = {**pair, "prompt_version": "prompt-v2"}
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            submit_preference_review(
                self.db,
                lease=lease,
                scope=SCOPE,
                pair=tampered_after_open,
                outcome="confirm",
                chosen_candidate_id="candidate-a",
                rejected_candidate_id="candidate-b",
                reason_code="tampered",
                reviewer_receipt_hash=_hash("receipt"),
                submitted_at="2026-07-26T00:02:00Z",
            )

    def test_conflict_requires_independent_arbitration(self):
        pair, _, _ = _pair()
        review = self._open(pair, required_approvals=2)
        first = claim_preference_review_case(
            self.db,
            review_id=review["review_id"],
            scope=SCOPE,
            reviewer_id_hash="reviewer-a",
            now="2026-07-26T00:01:00Z",
        )
        first_result = submit_preference_review(
            self.db,
            lease=first,
            scope=SCOPE,
            pair=pair,
            outcome="confirm",
            chosen_candidate_id="candidate-a",
            rejected_candidate_id="candidate-b",
            reason_code="confirm",
            reviewer_receipt_hash=_hash("receipt-a"),
            submitted_at="2026-07-26T00:02:00Z",
        )
        self.assertEqual(first_result["status"], "open")

        second = claim_preference_review_case(
            self.db,
            review_id=review["review_id"],
            scope=SCOPE,
            reviewer_id_hash="reviewer-b",
            now="2026-07-26T00:03:00Z",
        )
        second_result = submit_preference_review(
            self.db,
            lease=second,
            scope=SCOPE,
            pair=pair,
            outcome="overturn",
            chosen_candidate_id="candidate-b",
            rejected_candidate_id="candidate-a",
            reason_code="overturn",
            reviewer_receipt_hash=_hash("receipt-b"),
            submitted_at="2026-07-26T00:04:00Z",
            learning={
                "consent_id_hash": _hash("consent"),
                "purpose": "reward_model_training",
                "lineage_hash": _hash("lineage"),
                "residency": "cn",
                "retention_until": "2027-07-26T00:00:00Z",
                "deletion_key_hash": _hash("deletion"),
            },
        )
        self.assertEqual(second_result["status"], "arbitration")
        self.assertIsNone(second_result["learning_candidate"])
        self.assertEqual(
            second_result["learning_blocked_reason"],
            "review_not_completed_or_conflict_requires_arbitration",
        )

        with self.assertRaisesRegex(ValueError, "independent"):
            resolve_preference_arbitration(
                self.db,
                review_id=review["review_id"],
                scope=SCOPE,
                pair=pair,
                arbitrator_id_hash="reviewer-a",
                arbitrator_role="preference_arbitrator",
                chosen_candidate_id="candidate-b",
                rejected_candidate_id="candidate-a",
                reviewer_receipt_hash=_hash("arbitrator-receipt"),
                reason_code="arbitrated",
                resolved_at="2026-07-26T00:05:00Z",
            )

        arbitration = resolve_preference_arbitration(
            self.db,
            review_id=review["review_id"],
            scope=SCOPE,
            pair=pair,
            arbitrator_id_hash="arbitrator-a",
            arbitrator_role="preference_arbitrator",
            chosen_candidate_id="candidate-b",
            rejected_candidate_id="candidate-a",
            reviewer_receipt_hash=_hash("arbitrator-receipt"),
            reason_code="arbitrated",
            resolved_at="2026-07-26T00:05:00Z",
        )
        self.assertEqual(arbitration["status"], "completed")
        self.assertEqual(
            arbitration["resolution"]["final_outcome"],
            "overturn",
        )
        self.assertTrue(arbitration["resolution"]["training_eligible"])

    def test_unresolved_review_has_no_authoritative_resolution(self):
        pair, _, _ = _pair()
        review = self._open(pair, required_approvals=2)
        lease = claim_preference_review_case(
            self.db,
            review_id=review["review_id"],
            scope=SCOPE,
            reviewer_id_hash="reviewer-a",
            now="2026-07-26T00:01:00Z",
        )
        result = submit_preference_review(
            self.db,
            lease=lease,
            scope=SCOPE,
            pair=pair,
            outcome="escalate",
            chosen_candidate_id=None,
            rejected_candidate_id=None,
            reason_code="ambiguous",
            reviewer_receipt_hash=_hash("receipt"),
            submitted_at="2026-07-26T00:02:00Z",
        )
        self.assertEqual(result["status"], "open")
        self.assertIsNone(
            get_authoritative_preference_review_resolution(
                self.db, review_id=review["review_id"], scope=SCOPE, pair=pair
            )
        )

    def test_review_timestamps_are_timezone_aware_and_canonical(self):
        pair, _, _ = _pair()
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            open_preference_review_case(
                self.db,
                scope=SCOPE,
                pair=pair,
                reason_code="releasefoundry_teacher_disagreement",
                created_at="2026-07-26T00:00:00",
            )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM a2_preference_review_cases"
            ).fetchone()[0],
            0,
        )

        review = open_preference_review_case(
            self.db,
            scope=SCOPE,
            pair=pair,
            reason_code="releasefoundry_teacher_disagreement",
            created_at="2026-07-26T08:00:00+08:00",
        )
        row = self.db.execute(
            """
            SELECT status, created_at, updated_at
            FROM a2_preference_review_cases
            WHERE review_id = ?
            """,
            (review["review_id"],),
        ).fetchone()
        self.assertEqual(row["created_at"], "2026-07-26T00:00:00Z")
        self.assertEqual(row["updated_at"], "2026-07-26T00:00:00Z")

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            claim_preference_review_case(
                self.db,
                review_id=review["review_id"],
                scope=SCOPE,
                reviewer_id_hash="reviewer-a",
                now="2026-07-26T00:01:00",
            )
        self.assertEqual(
            self.db.execute(
                """
                SELECT status FROM a2_preference_review_cases
                WHERE review_id = ?
                """,
                (review["review_id"],),
            ).fetchone()["status"],
            "open",
        )

        lease = claim_preference_review_case(
            self.db,
            review_id=review["review_id"],
            scope=SCOPE,
            reviewer_id_hash="reviewer-a",
            now="2026-07-26T08:01:00+08:00",
        )
        self.assertEqual(lease["lease_expires_at"], "2026-07-26T00:06:00Z")
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            submit_preference_review(
                self.db,
                lease=lease,
                scope=SCOPE,
                pair=pair,
                outcome="confirm",
                chosen_candidate_id="candidate-a",
                rejected_candidate_id="candidate-b",
                reason_code="human_gold_confirmed",
                reviewer_receipt_hash=_hash("review-receipt"),
                submitted_at="2026-07-26T00:02:00",
            )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM a2_preference_review_events"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.db.execute(
                """
                SELECT status FROM a2_preference_review_cases
                WHERE review_id = ?
                """,
                (review["review_id"],),
            ).fetchone()["status"],
            "leased",
        )

        result = submit_preference_review(
            self.db,
            lease=lease,
            scope=SCOPE,
            pair=pair,
            outcome="confirm",
            chosen_candidate_id="candidate-a",
            rejected_candidate_id="candidate-b",
            reason_code="human_gold_confirmed",
            reviewer_receipt_hash=_hash("review-receipt"),
            submitted_at="2026-07-26T08:02:00+08:00",
        )
        self.assertEqual(
            result["resolution"]["resolved_at"], "2026-07-26T00:02:00Z"
        )


if __name__ == "__main__":
    unittest.main()
