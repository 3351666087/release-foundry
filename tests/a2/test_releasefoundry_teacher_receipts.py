from copy import deepcopy
import json
import sqlite3

import pytest

from services.judge.releasefoundry_teacher_receipts import (
    ReleaseFoundryTeacherReceiptError,
    build_releasefoundry_teacher_acquisition_receipt,
    settle_releasefoundry_teacher_acquisition,
)
from services.judge.result_persistence import stable_hash
from services.judge.sql_store import initialize_sql_store
from services.judge.teacher_acquisition_queue import (
    claim_teacher_acquisition,
    enqueue_teacher_acquisition,
    get_teacher_acquisition_receipt,
)


SCOPE = {
    "organization_id": "org-a",
    "tenant_id": "tenant-a",
    "workspace_id": "workspace-a",
    "project_id": "project-a",
    "environment_id": "test",
}
CASE_MAP = {
    "releasefoundry-test-pass": "sample-pass",
    "releasefoundry-test-fail": "sample-fail",
}


def _run() -> dict:
    return {
        "id": 42,
        "dataset": 7,
        "result": {
            "status": "completed_with_failures",
            "judge_version": "releasefoundry-grader-v1",
            "aggregate_metrics": {"total_tests": 2},
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
                },
                {
                    "test_id": "releasefoundry-test-fail",
                    "status": "failed",
                    "started_at": "2026-07-26T01:00:02Z",
                    "completed_at": "2026-07-26T01:00:03Z",
                    "action_results": [
                        {
                            "actor": "agent",
                            "action_type": "tool_call",
                            "action_index": 1,
                            "tool_calls": [
                                {
                                    "actual": {
                                        "tool_name": "weather",
                                        "arguments": {"city": "wrong"},
                                    },
                                    "expected": {
                                        "tool_name": "weather",
                                        "arguments": {"city": "right"},
                                    },
                                    "argument_comparison": {
                                        "status": "mismatch",
                                        "actual_args": {"city": "wrong"},
                                        "expected_args": {"city": "right"},
                                        "exact_match": False,
                                    },
                                }
                            ],
                        }
                    ],
                },
            ],
        },
    }


def _queue_and_claim(db: sqlite3.Connection) -> tuple[dict, dict, dict]:
    payload = {"dataset": "fixed-six", "case_map": CASE_MAP}
    request_hash = stable_hash(payload)
    queued = enqueue_teacher_acquisition(
        db,
        scope=SCOPE,
        pair_id="pair-a",
        teacher_id="releasefoundry",
        request_hash=request_hash,
        idempotency_key="request-a",
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


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_sql_store(connection)
    yield connection
    connection.close()


def test_verified_receipt_is_stored_redacted_and_completes_queue(db):
    queued, claimed, payload = _queue_and_claim(db)
    receipt = build_releasefoundry_teacher_acquisition_receipt(
        _run(),
        pair_id=queued["pair_id"],
        teacher_id=queued["teacher_id"],
        request_hash=stable_hash(payload),
        case_map=CASE_MAP,
        expected_dataset_id=7,
        expected_judge_version="releasefoundry-grader-v1",
    )

    settled = settle_releasefoundry_teacher_acquisition(
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

    assert settled["status"] == "completed"
    assert settled["receipt_hash"] == receipt["receipt_hash"]
    stored = get_teacher_acquisition_receipt(
        db,
        queue_id=queued["queue_id"],
        scope=SCOPE,
    )
    assert stored["verification_state"] == "verified"
    assert stored["public_receipt"]["public_safe"] is True
    assert stored["public_receipt"]["raw_private_receipt_included"] is False
    rendered = json.dumps(stored, sort_keys=True)
    assert '"run_id"' not in rendered
    assert '"dataset_id"' not in rendered
    assert "safe answer" not in rendered
    assert "weather" not in rendered
    assert "private_receipt" not in stored["public_receipt"]

    replay = settle_releasefoundry_teacher_acquisition(
        db,
        claimed_request=claimed,
        scope=SCOPE,
        worker_id="worker-a",
        lease_generation=claimed["lease_generation"],
        settled_at="2026-07-26T00:03:00Z",
        actual_cost_usd=0.75,
        case_map=CASE_MAP,
        receipt=receipt,
    )
    assert replay["idempotent_replay"] is True
    assert db.execute(
        "SELECT COUNT(*) FROM a2_teacher_acquisition_receipts"
    ).fetchone()[0] == 1


def test_blocked_receipt_is_durable_but_cannot_complete_or_train(db):
    queued, claimed, payload = _queue_and_claim(db)
    run = _run()
    run["result"].pop("judge_version")
    receipt = build_releasefoundry_teacher_acquisition_receipt(
        run,
        pair_id=queued["pair_id"],
        teacher_id=queued["teacher_id"],
        request_hash=stable_hash(payload),
        case_map=CASE_MAP,
        expected_dataset_id=7,
    )
    assert receipt["verification_state"] == "blocked"
    assert receipt["private_receipt"]["receipt_complete"] is False

    settled = settle_releasefoundry_teacher_acquisition(
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

    assert settled["status"] == "blocked"
    assert settled["last_error_class"] == "releasefoundry_receipt_blocked"
    stored = get_teacher_acquisition_receipt(
        db,
        queue_id=queued["queue_id"],
        scope=SCOPE,
    )
    assert stored["verification_state"] == "blocked"
    assert stored["public_receipt"]["public_releasefoundry_receipt"]["receipt_complete"] is False


def test_receipt_projection_and_case_binding_are_fail_closed(db):
    queued, claimed, payload = _queue_and_claim(db)
    receipt = build_releasefoundry_teacher_acquisition_receipt(
        _run(),
        pair_id=queued["pair_id"],
        teacher_id=queued["teacher_id"],
        request_hash=stable_hash(payload),
        case_map=CASE_MAP,
        expected_dataset_id=7,
    )
    tampered = deepcopy(receipt)
    tampered["public_receipt"]["blockers"] = ["operator_override"]
    with pytest.raises(
        ReleaseFoundryTeacherReceiptError, match="public_receipt_projection_mismatch"
    ):
        settle_releasefoundry_teacher_acquisition(
            db,
            claimed_request=claimed,
            scope=SCOPE,
            worker_id="worker-a",
            lease_generation=claimed["lease_generation"],
            settled_at="2026-07-26T00:02:00Z",
            actual_cost_usd=0.75,
            case_map=CASE_MAP,
            receipt=tampered,
        )

    with pytest.raises(
        ReleaseFoundryTeacherReceiptError, match="receipt_case_map_hash_mismatch"
    ):
        settle_releasefoundry_teacher_acquisition(
            db,
            claimed_request=claimed,
            scope=SCOPE,
            worker_id="worker-a",
            lease_generation=claimed["lease_generation"],
            settled_at="2026-07-26T00:02:00Z",
            actual_cost_usd=0.75,
            case_map={"releasefoundry-test-pass": "different"},
            receipt=receipt,
        )


def test_receipt_request_identity_and_budget_are_enforced(db):
    queued, claimed, payload = _queue_and_claim(db)
    receipt = build_releasefoundry_teacher_acquisition_receipt(
        _run(),
        pair_id=queued["pair_id"],
        teacher_id=queued["teacher_id"],
        request_hash=stable_hash(payload),
        case_map=CASE_MAP,
        expected_dataset_id=7,
    )
    bad_request = deepcopy(receipt)
    bad_request["request_hash"] = stable_hash({"other": "request"})
    with pytest.raises(ReleaseFoundryTeacherReceiptError, match="receipt_request_hash_mismatch"):
        settle_releasefoundry_teacher_acquisition(
            db,
            claimed_request=claimed,
            scope=SCOPE,
            worker_id="worker-a",
            lease_generation=claimed["lease_generation"],
            settled_at="2026-07-26T00:02:00Z",
            actual_cost_usd=0.75,
            case_map=CASE_MAP,
            receipt=bad_request,
        )

    with pytest.raises(ReleaseFoundryTeacherReceiptError, match="exceeds_reserved_budget"):
        settle_releasefoundry_teacher_acquisition(
            db,
            claimed_request=claimed,
            scope=SCOPE,
            worker_id="worker-a",
            lease_generation=claimed["lease_generation"],
            settled_at="2026-07-26T00:02:00Z",
            actual_cost_usd=2.01,
            case_map=CASE_MAP,
            receipt=receipt,
        )
