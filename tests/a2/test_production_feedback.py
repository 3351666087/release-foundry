import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from services.judge.casebook import (
    build_case_book_report,
    promote_incident_candidates_to_case_book,
)
from services.judge.production_feedback import (
    ProductionFeedbackError,
    create_reviewed_feedback_regression_candidate,
    get_production_feedback,
    get_production_feedback_private_ref,
    get_production_feedback_review,
    get_reviewed_feedback_regression_candidate,
    ingest_production_feedback,
    list_pending_production_feedback,
    review_production_feedback,
)
from services.judge.result_persistence import stable_hash
from services.judge.sql_store import initialize_sql_store


ROOT = Path(__file__).resolve().parents[2]
SCOPE = {
    "organization_id": "org-a",
    "tenant_id": "tenant-a",
    "workspace_id": "workspace-a",
    "project_id": "project-a",
    "environment_id": "production",
}
OTHER_SCOPE = {**SCOPE, "tenant_id": "tenant-b"}


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_sql_store(connection)
    yield connection
    connection.close()


def _ingest(db: sqlite3.Connection, **overrides):
    event_type = overrides.pop("event_type", "complaint")
    source = overrides.pop("source", event_type)
    return ingest_production_feedback(
        db,
        scope=overrides.pop("scope", SCOPE),
        event_type=event_type,
        source_event_hash=overrides.pop("source_event_hash", _hash(source)),
        subject_hash=overrides.pop("subject_hash", _hash(f"subject-{source}")),
        idempotency_key=overrides.pop("idempotency_key", f"feedback-{source}"),
        public_summary=overrides.pop(
            "public_summary",
            {
                "title": "Tool result was ignored",
                "reason_code": "ignored_tool_result",
                "severity": "high",
                "failure_action": "weather.lookup",
                "evidence_location": {"action_index": 1},
            },
        ),
        private_evidence_ref=overrides.pop(
            "private_evidence_ref",
            f"docs/evidence/private_refs/{source}.json#event",
        ),
        occurred_at=overrides.pop("occurred_at", "2026-07-27T01:00:00Z"),
        received_at=overrides.pop("received_at", "2026-07-27T01:01:00Z"),
        case_id=overrides.pop(
            "case_id",
            "sample-a2-s012-ignored-tool-result",
        ),
        scenario_id=overrides.pop("scenario_id", "A2-S012"),
        fixture_ref=overrides.pop(
            "fixture_ref",
            "fixtures/a2/runs/a2_s012_ignored_tool_result.json",
        ),
        **overrides,
    )


def _review(
    db: sqlite3.Connection,
    created: dict,
    *,
    scope=SCOPE,
    **overrides,
):
    return review_production_feedback(
        db,
        feedback_id=created["feedback_id"],
        scope=scope,
        expected_event_hash=overrides.pop(
            "expected_event_hash",
            created["event_hash"],
        ),
        decision=overrides.pop("decision", "accept"),
        reason_code=overrides.pop("reason_code", "confirmed_failure"),
        reviewer_id_hash=overrides.pop(
            "reviewer_id_hash",
            _hash("reviewer-a"),
        ),
        reviewer_receipt_hash=overrides.pop(
            "reviewer_receipt_hash",
            _hash("feedback-review-receipt-a"),
        ),
        reviewed_at=overrides.pop(
            "reviewed_at",
            "2026-07-27T01:02:00Z",
        ),
        **overrides,
    )


def test_ingestion_is_idempotent_and_public_projection_excludes_private_ref(db):
    created = _ingest(db)
    replayed = _ingest(db)

    assert created["status"] == "pending_review"
    assert created["review_priority"] == 95
    assert created["public_safe"] is True
    assert created["training_eligible"] is False
    assert created["human_gold"] is False
    assert created["permanent_regression"] is False
    assert created["private_evidence_ref_present"] is True
    assert "private_evidence_ref" not in created
    assert replayed["feedback_id"] == created["feedback_id"]
    assert replayed["idempotent_replay"] is True
    assert (
        db.execute(
            "SELECT COUNT(*) FROM a2_production_feedback_events"
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM a2_production_feedback_private_refs"
        ).fetchone()[0]
        == 1
    )

    private_ref = get_production_feedback_private_ref(
        db,
        feedback_id=created["feedback_id"],
        scope=SCOPE,
    )
    assert private_ref["private_evidence_ref"].startswith(
        "docs/evidence/private_refs/"
    )
    assert private_ref["private_evidence_ref_hash"] == created[
        "private_evidence_ref_hash"
    ]


def test_idempotency_and_source_event_reuse_conflicts_fail_closed(db):
    _ingest(db)

    with pytest.raises(ProductionFeedbackError, match="idempotency_key_reuse_conflict"):
        _ingest(
            db,
            source_event_hash=_hash("different-source"),
            public_summary={"title": "Different event", "severity": "medium"},
        )

    with pytest.raises(ProductionFeedbackError, match="source_event_hash_reuse_conflict"):
        _ingest(
            db,
            idempotency_key="different-idempotency-key",
            public_summary={"title": "Changed event", "severity": "critical"},
        )


@pytest.mark.parametrize(
    "summary",
    [
        {"raw_prompt": "do not store me", "severity": "high"},
        {"response": "raw model response", "severity": "high"},
        {"summary": "contact person@example.com", "severity": "high"},
        {"summary": "Authorization: Bearer secret-token-value", "severity": "high"},
        {
            "summary": (
                "https://objects.example/file?"
                "X-Amz-Signature=0123456789abcdef"
            ),
            "severity": "high",
        },
    ],
)
def test_public_summary_rejects_private_or_secret_like_content(db, summary):
    with pytest.raises(ProductionFeedbackError, match="public_summary_contains"):
        _ingest(db, public_summary=summary)


@pytest.mark.parametrize(
    "private_ref",
    [
        "https://example.com/private.json",
        "C:/private/evidence.json",
        "docs/evidence/private_refs/../secret.json",
        "/docs/evidence/private_refs/event.json",
        "docs/evidence/event.json",
    ],
)
def test_private_evidence_ref_must_be_canonical_controlled_reference(db, private_ref):
    with pytest.raises(
        ProductionFeedbackError,
        match="private_evidence_ref_must_be_canonical",
    ):
        _ingest(db, private_evidence_ref=private_ref)


def test_reads_and_pending_queries_are_fully_tenant_scoped(db):
    created = _ingest(db)

    with pytest.raises(ProductionFeedbackError, match="scope_mismatch"):
        get_production_feedback(
            db,
            feedback_id=created["feedback_id"],
            scope=OTHER_SCOPE,
        )
    with pytest.raises(ProductionFeedbackError, match="scope_mismatch"):
        get_production_feedback_private_ref(
            db,
            feedback_id=created["feedback_id"],
            scope=OTHER_SCOPE,
        )
    assert list_pending_production_feedback(db, scope=OTHER_SCOPE) == []


def test_review_queue_prioritizes_incidents_and_keeps_success_reward_only(db):
    success = _ingest(
        db,
        event_type="successful_completion",
        source="success",
        case_id=None,
        scenario_id=None,
        fixture_ref=None,
        public_summary={
            "title": "Task completed without a user retry",
            "reward_signal": "successful_completion",
        },
    )
    retry = _ingest(db, event_type="retry", source="retry")
    incident = _ingest(db, event_type="incident", source="incident")

    pending = list_pending_production_feedback(db, scope=SCOPE)

    assert [item["feedback_id"] for item in pending] == [
        incident["feedback_id"],
        retry["feedback_id"],
        success["feedback_id"],
    ]
    assert success["review_priority"] == 10
    assert success["training_eligible"] is False
    assert success["human_gold"] is False
    assert success["permanent_regression"] is False


def test_stored_public_summary_and_event_hash_are_integrity_checked(db):
    created = _ingest(db)
    db.execute(
        """
        UPDATE a2_production_feedback_events
        SET public_summary_json = ?
        WHERE feedback_id = ?
        """,
        (json.dumps({"title": "tampered"}), created["feedback_id"]),
    )
    db.commit()

    with pytest.raises(ProductionFeedbackError, match="summary_integrity_mismatch"):
        get_production_feedback(
            db,
            feedback_id=created["feedback_id"],
            scope=SCOPE,
        )


def test_complete_five_field_scope_and_public_fixture_are_required(db):
    with pytest.raises(ProductionFeedbackError, match="complete_five_field_scope"):
        _ingest(db, scope={**SCOPE, "environment_id": ""})
    with pytest.raises(ProductionFeedbackError, match="public_a2_run_reference"):
        _ingest(db, fixture_ref="../private.json")


def test_accept_review_is_idempotent_but_grants_no_learning_authority(db):
    created = _ingest(db)

    reviewed = _review(db, created)
    replayed = _review(db, created)
    stored = get_production_feedback_review(
        db,
        feedback_id=created["feedback_id"],
        scope=SCOPE,
    )
    event = get_production_feedback(
        db,
        feedback_id=created["feedback_id"],
        scope=SCOPE,
    )

    assert reviewed["decision"] == "accept"
    assert reviewed["human_gold"] is False
    assert reviewed["training_eligible"] is False
    assert reviewed["permanent_regression"] is False
    assert replayed["review_id"] == reviewed["review_id"]
    assert replayed["idempotent_replay"] is True
    assert stored["decision_hash"] == reviewed["decision_hash"]
    assert event["status"] == "reviewed_accept"
    assert list_pending_production_feedback(db, scope=SCOPE) == []


def test_review_hash_scope_and_conflict_checks_fail_closed(db):
    created = _ingest(db)

    with pytest.raises(ProductionFeedbackError, match="event_hash_mismatch"):
        _review(db, created, expected_event_hash=_hash("wrong-event"))
    with pytest.raises(ProductionFeedbackError, match="review_precedes_receipt"):
        _review(db, created, reviewed_at="2026-07-27T00:59:00Z")
    with pytest.raises(ProductionFeedbackError, match="scope_mismatch"):
        _review(db, created, scope=OTHER_SCOPE)

    _review(db, created)
    with pytest.raises(ProductionFeedbackError, match="review_conflict"):
        _review(
            db,
            created,
            decision="reject",
            reason_code="different_decision",
        )
    with pytest.raises(ProductionFeedbackError, match="scope_mismatch"):
        get_production_feedback_review(
            db,
            feedback_id=created["feedback_id"],
            scope=OTHER_SCOPE,
        )


@pytest.mark.parametrize("decision", ["reject", "abstain", "escalate"])
def test_non_accept_reviews_cannot_create_regression_candidates(db, decision):
    created = _ingest(db, source=decision)
    _review(
        db,
        created,
        decision=decision,
        reviewer_receipt_hash=_hash(f"receipt-{decision}"),
    )

    with pytest.raises(
        ProductionFeedbackError,
        match="only_accepted_feedback",
    ):
        create_reviewed_feedback_regression_candidate(
            db,
            feedback_id=created["feedback_id"],
            scope=SCOPE,
            created_at="2026-07-27T01:03:00Z",
        )


def test_reward_only_and_incomplete_feedback_cannot_create_candidates(db):
    success = _ingest(
        db,
        event_type="successful_completion",
        source="accepted-success",
        case_id=None,
        scenario_id=None,
        fixture_ref=None,
        public_summary={
            "title": "Task completed",
            "reward_signal": "successful_completion",
        },
    )
    _review(db, success, reviewer_receipt_hash=_hash("success-receipt"))
    with pytest.raises(
        ProductionFeedbackError,
        match="event_type_not_regression_eligible",
    ):
        create_reviewed_feedback_regression_candidate(
            db,
            feedback_id=success["feedback_id"],
            scope=SCOPE,
            created_at="2026-07-27T01:03:00Z",
        )

    incomplete = _ingest(
        db,
        event_type="incident",
        source="accepted-incomplete",
        case_id=None,
        scenario_id=None,
        fixture_ref=None,
    )
    _review(
        db,
        incomplete,
        reviewer_receipt_hash=_hash("incomplete-receipt"),
    )
    with pytest.raises(
        ProductionFeedbackError,
        match="missing_replay_identity",
    ):
        create_reviewed_feedback_regression_candidate(
            db,
            feedback_id=incomplete["feedback_id"],
            scope=SCOPE,
            created_at="2026-07-27T01:03:00Z",
        )


def test_accepted_feedback_creates_idempotent_pending_owner_candidate(db):
    created = _ingest(db, event_type="incident", source="candidate")
    review = _review(db, created)

    with pytest.raises(ProductionFeedbackError, match="candidate_precedes_review"):
        create_reviewed_feedback_regression_candidate(
            db,
            feedback_id=created["feedback_id"],
            scope=SCOPE,
            created_at="2026-07-27T01:01:30Z",
        )
    with pytest.raises(ProductionFeedbackError, match="scope_mismatch"):
        create_reviewed_feedback_regression_candidate(
            db,
            feedback_id=created["feedback_id"],
            scope=OTHER_SCOPE,
            created_at="2026-07-27T01:03:00Z",
        )

    candidate = create_reviewed_feedback_regression_candidate(
        db,
        feedback_id=created["feedback_id"],
        scope=SCOPE,
        created_at="2026-07-27T01:03:00Z",
    )
    replayed = create_reviewed_feedback_regression_candidate(
        db,
        feedback_id=created["feedback_id"],
        scope=SCOPE,
        created_at="2026-07-27T02:03:00Z",
    )
    stored = get_reviewed_feedback_regression_candidate(
        db,
        feedback_id=created["feedback_id"],
        scope=SCOPE,
    )

    assert candidate["review_id"] == review["review_id"]
    assert candidate["status"] == "pending_owner_review"
    assert candidate["owner_review_required"] is True
    assert candidate["training_eligible"] is False
    assert candidate["human_gold"] is False
    assert candidate["permanent_regression"] is False
    assert candidate["report"]["ready_for_case_book_review"] is True
    assert candidate["report"]["candidate_count"] == 1
    assert "inline" not in candidate["report"]["candidates"][0]["evidence_refs"]
    assert replayed["candidate_id"] == candidate["candidate_id"]
    assert replayed["idempotent_replay"] is True
    assert stored["candidate_hash"] == candidate["candidate_hash"]

    with pytest.raises(ProductionFeedbackError, match="scope_mismatch"):
        get_reviewed_feedback_regression_candidate(
            db,
            feedback_id=created["feedback_id"],
            scope=OTHER_SCOPE,
        )


@pytest.mark.parametrize(
    ("column", "tampered_value"),
    [
        ("candidate_json", json.dumps({"case_id": "tampered"})),
        ("candidate_hash", _hash("tampered-candidate-hash")),
        ("candidate_id", _hash("tampered-candidate-id")),
    ],
)
def test_candidate_integrity_tampering_fails_closed(
    db,
    column,
    tampered_value,
):
    created = _ingest(db, event_type="incident", source="tamper")
    _review(db, created)
    candidate = create_reviewed_feedback_regression_candidate(
        db,
        feedback_id=created["feedback_id"],
        scope=SCOPE,
        created_at="2026-07-27T01:03:00Z",
    )
    db.execute(
        f"""
        UPDATE a2_production_feedback_regression_candidates
        SET {column} = ?
        WHERE candidate_id = ?
        """,
        (tampered_value, candidate["candidate_id"]),
    )
    db.commit()

    with pytest.raises(
        ProductionFeedbackError,
        match="candidate_(?:integrity|id)_mismatch",
    ):
        get_reviewed_feedback_regression_candidate(
            db,
            feedback_id=created["feedback_id"],
            scope=SCOPE,
        )


def test_owner_review_is_required_and_does_not_satisfy_external_evidence_gate(db):
    created = _ingest(db, event_type="incident", source="promotion")
    _review(db, created)
    candidate = create_reviewed_feedback_regression_candidate(
        db,
        feedback_id=created["feedback_id"],
        scope=SCOPE,
        created_at="2026-07-27T01:03:00Z",
    )
    matrix = json.loads(
        (ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    case_book = build_case_book_report(matrix)

    unchanged = promote_incident_candidates_to_case_book(
        case_book,
        candidate["report"],
    )
    assert unchanged == case_book

    promoted = promote_incident_candidates_to_case_book(
        case_book,
        candidate["report"],
        [
            {
                "case_id": created["case_id"],
                "decision": "approved",
                "reviewer_receipt": _hash("owner-approval"),
                "reviewed_at_unix_ms": 1785100000000,
                "source_incident_candidates_hash": candidate["report"][
                    "artifact_hash"
                ],
                "candidate_hash": stable_hash(
                    candidate["report"]["candidates"][0]
                ),
                "evidence_refs": [],
            }
        ],
    )

    assert promoted["regression_case_count"] == case_book["regression_case_count"] + 1
    assert promoted["metadata"]["promotion_audit"][0]["outcome"] == "promoted"
    assert promoted["maturity_gate"]["ready"] is False
    assert (
        promoted["maturity_gate"]["reviewed_external_evidence_count"]
        == case_book["maturity_gate"]["reviewed_external_evidence_count"]
    )
