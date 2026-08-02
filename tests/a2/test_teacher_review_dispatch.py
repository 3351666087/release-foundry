from copy import deepcopy
import hashlib
import sqlite3

import pytest

from services.judge.releasefoundry_teacher_receipts import (
    build_releasefoundry_teacher_acquisition_receipt,
    settle_releasefoundry_teacher_acquisition,
)
from services.judge.preference_learning import build_governed_preference_pair
from services.judge.result_persistence import stable_hash
from services.judge.sql_store import initialize_sql_store
from services.judge.teacher_acquisition_queue import (
    claim_teacher_acquisition,
    enqueue_teacher_acquisition,
)
from services.judge.teacher_review_dispatch import (
    TeacherReviewDispatchError,
    dispatch_verified_teacher_receipt_to_preference_review,
    get_teacher_review_dispatch,
)


SCOPE = {
    "organization_id": "org-a",
    "tenant_id": "tenant-a",
    "workspace_id": "workspace-a",
    "project_id": "project-a",
    "environment_id": "test",
}
OTHER_SCOPE = {**SCOPE, "tenant_id": "tenant-b"}
CASE_MAP = {"releasefoundry-test-pass": "sample-pass"}


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


def _evaluation(
    candidate_id: str,
    *,
    rank: int,
    reward: float,
    passed: bool,
) -> dict:
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


def _pair(prefix: str = "candidate") -> dict:
    candidate_a = f"{prefix}-a"
    candidate_b = f"{prefix}-b"
    return build_governed_preference_pair(
        [_candidate(candidate_a), _candidate(candidate_b)],
        [
            _evaluation(candidate_a, rank=1, reward=0.95, passed=True),
            _evaluation(candidate_b, rank=2, reward=0.2, passed=False),
        ],
    )


def _run() -> dict:
    return {
        "id": 42,
        "dataset": 7,
        "result": {
            "status": "completed",
            "judge_version": "releasefoundry-grader-v1",
            "aggregate_metrics": {"total_tests": 1},
            "tests": [
                {
                    "test_id": "releasefoundry-test-pass",
                    "status": "completed",
                    "started_at": "2026-07-26T01:00:00Z",
                    "completed_at": "2026-07-26T01:00:01Z",
                    "action_results": [
                        {
                            "actor": "agent",
                            "action_type": "text",
                            "action_index": 1,
                            "actual_response": {"content": "safe answer"},
                            "llm_judgment": {
                                "verdict": "match",
                                "reason": "The answer is correct.",
                            },
                        }
                    ],
                }
            ],
        },
    }


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_sql_store(connection)
    yield connection
    connection.close()


def _queue_and_claim(
    db: sqlite3.Connection,
    pair: dict,
) -> tuple[dict, dict, dict]:
    payload = {"dataset": "fixed-six", "case_map": CASE_MAP}
    queued = enqueue_teacher_acquisition(
        db,
        scope=SCOPE,
        pair_id=pair["pair_id"],
        teacher_id="releasefoundry",
        request_hash=stable_hash(payload),
        idempotency_key=f"request-{pair['pair_id']}",
        priority_score=90,
        max_cost_usd=2,
        created_at="2026-07-26T00:00:00Z",
    )
    claimed = claim_teacher_acquisition(
        db,
        scope=SCOPE,
        worker_id="worker-a",
        now="2026-07-26T00:01:00Z",
    )
    assert claimed is not None
    return queued, claimed, payload


def _settled(
    db: sqlite3.Connection,
    *,
    verified: bool = True,
) -> tuple[dict, dict, dict]:
    pair = _pair()
    queued, claimed, payload = _queue_and_claim(db, pair)
    run = _run()
    if not verified:
        run["result"].pop("judge_version")
    receipt = build_releasefoundry_teacher_acquisition_receipt(
        run,
        pair_id=pair["pair_id"],
        teacher_id=queued["teacher_id"],
        request_hash=stable_hash(payload),
        case_map=CASE_MAP,
        expected_dataset_id=7,
        expected_judge_version="releasefoundry-grader-v1",
    )
    settle_releasefoundry_teacher_acquisition(
        db,
        claimed_request=claimed,
        scope=SCOPE,
        worker_id="worker-a",
        lease_generation=claimed["lease_generation"],
        settled_at="2026-07-26T00:02:00Z",
        actual_cost_usd=0.75,
        case_map=CASE_MAP,
        receipt=receipt,
    )
    return pair, queued, receipt


def _dispatch(db: sqlite3.Connection, pair: dict, queue_id: str, **kwargs):
    return dispatch_verified_teacher_receipt_to_preference_review(
        db,
        queue_id=queue_id,
        scope=SCOPE,
        pair=pair,
        reason_code=kwargs.get("reason_code", "releasefoundry_teacher_observation"),
        created_at="2026-07-26T00:03:00Z",
        required_approvals=kwargs.get("required_approvals", 1),
    )


def test_verified_receipt_opens_human_review_without_training_authority(db):
    pair, queued, _ = _settled(db)

    result = _dispatch(db, pair, queued["queue_id"])

    assert result["review_status"] == "open"
    assert result["teacher_receipt_training_authority"] is False
    assert result["human_review_required"] is True
    assert result["training_candidate_created_by_dispatch"] is False
    assert result["public_safe"] is True
    assert db.execute(
        "SELECT COUNT(*) FROM a2_preference_review_cases"
    ).fetchone()[0] == 1
    for table in (
        "a2_preference_review_resolutions",
        "a2_preference_learning_candidates",
        "a2_release_decisions",
    ):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_dispatch_replay_is_idempotent(db):
    pair, queued, _ = _settled(db)
    first = _dispatch(db, pair, queued["queue_id"])
    replay = _dispatch(db, pair, queued["queue_id"])

    assert replay["dispatch_id"] == first["dispatch_id"]
    assert replay["review_id"] == first["review_id"]
    assert replay["idempotent_replay"] is True
    assert db.execute(
        "SELECT COUNT(*) FROM a2_teacher_review_dispatches"
    ).fetchone()[0] == 1
    assert db.execute(
        "SELECT COUNT(*) FROM a2_preference_review_cases"
    ).fetchone()[0] == 1


def test_blocked_receipt_cannot_dispatch(db):
    pair, queued, _ = _settled(db, verified=False)

    with pytest.raises(
        TeacherReviewDispatchError,
        match="teacher_queue_not_completed|teacher_receipt_not_verified",
    ):
        _dispatch(db, pair, queued["queue_id"])

    assert db.execute(
        "SELECT COUNT(*) FROM a2_teacher_review_dispatches"
    ).fetchone()[0] == 0
    assert db.execute(
        "SELECT COUNT(*) FROM a2_preference_review_cases"
    ).fetchone()[0] == 0


def test_unsettled_queue_cannot_dispatch(db):
    pair = _pair()
    queued, _, _ = _queue_and_claim(db, pair)

    with pytest.raises(
        TeacherReviewDispatchError,
        match="teacher_receipt_not_found|teacher_queue_not_completed",
    ):
        _dispatch(db, pair, queued["queue_id"])


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("pair", "teacher_pair_binding_mismatch"),
        ("pair_hash", "pair_hash_mismatch"),
        ("request_hash", "teacher_request_hash_binding_mismatch"),
        ("receipt_hash", "teacher_receipt_hash_mismatch"),
    ],
)
def test_dispatch_binding_mismatches_fail_closed(db, mutation, expected_error):
    pair, queued, _ = _settled(db)
    dispatched_pair = pair
    if mutation == "pair":
        dispatched_pair = _pair("different")
    elif mutation == "pair_hash":
        dispatched_pair = deepcopy(pair)
        dispatched_pair["status"] = "review_required"
    elif mutation == "request_hash":
        db.execute(
            """
            UPDATE a2_teacher_acquisition_receipts
            SET request_hash = ?
            WHERE queue_id = ?
            """,
            (stable_hash({"different": "request"}), queued["queue_id"]),
        )
        db.commit()
    elif mutation == "receipt_hash":
        db.execute(
            """
            UPDATE a2_teacher_acquisition_queue
            SET receipt_hash = ?
            WHERE queue_id = ?
            """,
            (stable_hash({"different": "receipt"}), queued["queue_id"]),
        )
        db.commit()

    with pytest.raises(TeacherReviewDispatchError, match=expected_error):
        _dispatch(db, dispatched_pair, queued["queue_id"])


def test_training_eligible_pair_cannot_dispatch(db):
    pair, queued, _ = _settled(db)
    training_pair = deepcopy(pair)
    training_pair["training_eligible"] = True
    training_pair["pair_id"] = stable_hash(
        {key: value for key, value in training_pair.items() if key != "pair_id"}
    )

    with pytest.raises(
        TeacherReviewDispatchError,
        match="pair_training_state_invalid",
    ):
        _dispatch(db, training_pair, queued["queue_id"])


def test_dispatch_integrity_tampering_is_detected(db):
    pair, queued, _ = _settled(db)
    _dispatch(db, pair, queued["queue_id"])
    db.execute(
        """
        UPDATE a2_teacher_review_dispatches
        SET reason_code = 'tampered'
        WHERE queue_id = ?
        """,
        (queued["queue_id"],),
    )
    db.commit()

    with pytest.raises(
        TeacherReviewDispatchError,
        match="teacher_review_dispatch_integrity_mismatch",
    ):
        get_teacher_review_dispatch(db, queue_id=queued["queue_id"], scope=SCOPE)


def test_dispatch_request_conflicts_cannot_be_silently_reused(db):
    pair, queued, _ = _settled(db)
    _dispatch(db, pair, queued["queue_id"])

    with pytest.raises(
        TeacherReviewDispatchError,
        match="teacher_review_dispatch_conflict",
    ):
        _dispatch(
            db,
            pair,
            queued["queue_id"],
            required_approvals=2,
        )
    with pytest.raises(
        TeacherReviewDispatchError,
        match="teacher_review_dispatch_conflict",
    ):
        _dispatch(
            db,
            pair,
            queued["queue_id"],
            reason_code="different_reason",
        )


def test_dispatch_is_tenant_scoped(db):
    pair, queued, _ = _settled(db)
    _dispatch(db, pair, queued["queue_id"])

    with pytest.raises(
        TeacherReviewDispatchError,
        match="teacher_review_dispatch_not_found",
    ):
        get_teacher_review_dispatch(
            db,
            queue_id=queued["queue_id"],
            scope=OTHER_SCOPE,
        )
