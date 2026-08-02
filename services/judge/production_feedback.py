"""Tenant-scoped, public-safe production feedback ingestion for A2."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import sqlite3
from typing import Any, Mapping

from .calibration import is_canonical_private_evidence_ref
from .incident_regression import (
    build_incident_regression_candidate_report,
    seal_incident_regression_candidate_report,
)
from .result_persistence import canonical_json, stable_hash


SCOPE_FIELDS = (
    "organization_id",
    "tenant_id",
    "workspace_id",
    "project_id",
    "environment_id",
)
EVENT_TYPES = frozenset(
    {
        "retry",
        "abandonment",
        "correction",
        "complaint",
        "misclassification",
        "incident",
        "successful_completion",
    }
)
REVIEW_PRIORITIES = {
    "incident": 100,
    "complaint": 95,
    "misclassification": 90,
    "correction": 75,
    "abandonment": 60,
    "retry": 50,
    "successful_completion": 10,
}
PENDING_STATUS = "pending_review"
REVIEW_DECISIONS = frozenset({"accept", "reject", "abstain", "escalate"})
STATUS_BY_REVIEW_DECISION = {
    "accept": "reviewed_accept",
    "reject": "reviewed_reject",
    "abstain": "reviewed_abstain",
    "escalate": "reviewed_escalate",
}
REGRESSION_SOURCE_EVENT_TYPES = frozenset(EVENT_TYPES - {"successful_completion"})
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PRIVATE_FIELD_NAMES = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "email",
        "file_bytes",
        "image",
        "input",
        "media",
        "prompt",
        "raw_audio",
        "raw_file",
        "raw_image",
        "raw_media",
        "raw_prompt",
        "raw_request",
        "raw_response",
        "raw_video",
        "request",
        "request_payload",
        "response",
        "response_payload",
        "secret",
        "signed_url",
        "token",
        "video",
    }
)
FORBIDDEN_TEXT_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/\-=]+", re.IGNORECASE),
    re.compile(r"\b(?:sk-|tp_)[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    re.compile(
        r"(?:x-amz-signature|x-goog-signature|signature|access_token|auth_token)=",
        re.IGNORECASE,
    ),
)
PUBLIC_SUMMARY_MAX_BYTES = 16_384
PUBLIC_FIXTURE_PREFIX = "fixtures/a2/runs/"


class ProductionFeedbackError(ValueError):
    """Raised when production feedback cannot be stored safely."""


def ingest_production_feedback(
    connection: sqlite3.Connection,
    *,
    scope: Mapping[str, Any],
    event_type: str,
    source_event_hash: str,
    subject_hash: str,
    idempotency_key: str,
    public_summary: Mapping[str, Any],
    private_evidence_ref: str,
    occurred_at: str,
    received_at: str,
    case_id: str | None = None,
    scenario_id: str | None = None,
    fixture_ref: str | None = None,
) -> dict[str, Any]:
    """Ingest one redacted feedback event without granting learning authority."""
    normalized_scope = _scope(scope)
    normalized_event_type = _event_type(event_type)
    _hash(source_event_hash, "source_event_hash")
    _hash(subject_hash, "subject_hash")
    _text(idempotency_key, "idempotency_key")
    summary = _public_summary(public_summary)
    private_ref = _private_ref(private_evidence_ref)
    normalized_case_id = _optional_text(case_id, "case_id")
    normalized_scenario_id = _optional_text(scenario_id, "scenario_id")
    normalized_fixture_ref = _fixture_ref(fixture_ref)
    occurred = _canonical_timestamp(occurred_at, "occurred_at")
    received = _canonical_timestamp(received_at, "received_at")
    if _timestamp(received) < _timestamp(occurred):
        raise ProductionFeedbackError("received_at_precedes_occurred_at")

    summary_json = canonical_json(summary)
    summary_hash = stable_hash(summary)
    private_ref_hash = stable_hash({"private_evidence_ref": private_ref})
    idempotency_key_hash = stable_hash({"idempotency_key": idempotency_key})
    core = {
        "scope": normalized_scope,
        "event_type": normalized_event_type,
        "source_event_hash": source_event_hash,
        "subject_hash": subject_hash,
        "case_id": normalized_case_id,
        "scenario_id": normalized_scenario_id,
        "fixture_ref": normalized_fixture_ref,
        "public_summary_hash": summary_hash,
        "private_evidence_ref_hash": private_ref_hash,
        "occurred_at": occurred,
        "received_at": received,
    }
    event_hash = stable_hash(core)
    feedback_id = stable_hash(
        {
            "scope": normalized_scope,
            "event_type": normalized_event_type,
            "source_event_hash": source_event_hash,
        }
    )

    connection.execute("BEGIN IMMEDIATE")
    try:
        existing = _find_by_idempotency(
            connection,
            normalized_scope,
            idempotency_key_hash,
        )
        if existing is not None:
            if existing["event_hash"] != event_hash:
                raise ProductionFeedbackError("idempotency_key_reuse_conflict")
            _assert_private_ref_integrity(
                connection,
                existing,
                normalized_scope,
                expected_ref=private_ref,
            )
            connection.commit()
            return _public_row(existing, idempotent_replay=True)

        source_existing = _find_by_source_event(
            connection,
            normalized_scope,
            source_event_hash,
        )
        if source_existing is not None:
            if source_existing["event_hash"] != event_hash:
                raise ProductionFeedbackError("source_event_hash_reuse_conflict")
            _assert_private_ref_integrity(
                connection,
                source_existing,
                normalized_scope,
                expected_ref=private_ref,
            )
            connection.commit()
            return _public_row(source_existing, idempotent_replay=True)

        connection.execute(
            """
            INSERT INTO a2_production_feedback_events (
              feedback_id, event_type, source_event_hash, subject_hash,
              idempotency_key_hash, organization_id, tenant_id, workspace_id,
              project_id, environment_id, case_id, scenario_id, fixture_ref,
              public_summary_json, public_summary_hash,
              private_evidence_ref_hash, review_priority, status,
              training_eligible, human_gold, permanent_regression,
              event_hash, occurred_at, received_at, updated_at, public_safe
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review',
              0, 0, 0, ?, ?, ?, ?, 1
            )
            """,
            (
                feedback_id,
                normalized_event_type,
                source_event_hash,
                subject_hash,
                idempotency_key_hash,
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
                normalized_case_id,
                normalized_scenario_id,
                normalized_fixture_ref,
                summary_json,
                summary_hash,
                private_ref_hash,
                REVIEW_PRIORITIES[normalized_event_type],
                event_hash,
                occurred,
                received,
                received,
            ),
        )
        connection.execute(
            """
            INSERT INTO a2_production_feedback_private_refs (
              feedback_id, organization_id, tenant_id, workspace_id, project_id,
              environment_id, private_evidence_ref, private_evidence_ref_hash,
              created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
                private_ref,
                private_ref_hash,
                received,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _public_row(
        _feedback(connection, feedback_id, normalized_scope),
        idempotent_replay=False,
    )


def get_production_feedback(
    connection: sqlite3.Connection,
    *,
    feedback_id: str,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Read one public projection without exposing the private evidence reference."""
    normalized_scope = _scope(scope)
    _text(feedback_id, "feedback_id")
    return _public_row(
        _feedback(connection, feedback_id, normalized_scope),
        idempotent_replay=False,
    )


def get_production_feedback_private_ref(
    connection: sqlite3.Connection,
    *,
    feedback_id: str,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Read the controlled private evidence reference through a scoped API."""
    normalized_scope = _scope(scope)
    _text(feedback_id, "feedback_id")
    event = _feedback(connection, feedback_id, normalized_scope)
    row = _private_ref_row(connection, feedback_id, normalized_scope)
    if row is None:
        raise ProductionFeedbackError("production_feedback_private_ref_not_found")
    _assert_private_ref_row(event, row)
    return {
        "feedback_id": feedback_id,
        "scope": dict(normalized_scope),
        "private_evidence_ref": row["private_evidence_ref"],
        "private_evidence_ref_hash": row["private_evidence_ref_hash"],
        "created_at": row["created_at"],
    }


def list_pending_production_feedback(
    connection: sqlite3.Connection,
    *,
    scope: Mapping[str, Any],
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List pending feedback by review priority within one complete tenant scope."""
    normalized_scope = _scope(scope)
    normalized_limit = _positive_int(limit, "limit")
    rows = connection.execute(
        """
        SELECT *
        FROM a2_production_feedback_events
        WHERE organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ?
          AND status = 'pending_review'
        ORDER BY review_priority DESC, occurred_at ASC, feedback_id ASC
        LIMIT ?
        """,
        (
            normalized_scope["organization_id"],
            normalized_scope["tenant_id"],
            normalized_scope["workspace_id"],
            normalized_scope["project_id"],
            normalized_scope["environment_id"],
            normalized_limit,
        ),
    ).fetchall()
    return [
        _public_row(dict(row), idempotent_replay=False)
        for row in rows
    ]


def review_production_feedback(
    connection: sqlite3.Connection,
    *,
    feedback_id: str,
    scope: Mapping[str, Any],
    expected_event_hash: str,
    decision: str,
    reason_code: str,
    reviewer_id_hash: str,
    reviewer_receipt_hash: str,
    reviewed_at: str,
) -> dict[str, Any]:
    """Record one canonical review without granting gold or training authority."""
    normalized_scope = _scope(scope)
    _text(feedback_id, "feedback_id")
    _hash(expected_event_hash, "expected_event_hash")
    normalized_decision = _review_decision(decision)
    _text(reason_code, "reason_code")
    _hash(reviewer_id_hash, "reviewer_id_hash")
    _hash(reviewer_receipt_hash, "reviewer_receipt_hash")
    reviewed = _canonical_timestamp(reviewed_at, "reviewed_at")

    core = {
        "feedback_id": feedback_id,
        "scope": normalized_scope,
        "event_hash": expected_event_hash,
        "decision": normalized_decision,
        "reason_code": reason_code,
        "reviewer_id_hash": reviewer_id_hash,
        "reviewer_receipt_hash": reviewer_receipt_hash,
        "reviewed_at": reviewed,
    }
    decision_hash = stable_hash(core)
    review_id = stable_hash(
        {
            "feedback_id": feedback_id,
            "reviewer_receipt_hash": reviewer_receipt_hash,
        }
    )

    connection.execute("BEGIN IMMEDIATE")
    try:
        event = _feedback(connection, feedback_id, normalized_scope)
        if event["event_hash"] != expected_event_hash:
            raise ProductionFeedbackError("production_feedback_event_hash_mismatch")
        if _timestamp(reviewed) < _timestamp(event["received_at"]):
            raise ProductionFeedbackError(
                "production_feedback_review_precedes_receipt"
            )
        existing = _review_row(connection, feedback_id, normalized_scope)
        if existing is not None:
            if existing["decision_hash"] != decision_hash:
                raise ProductionFeedbackError("production_feedback_review_conflict")
            connection.commit()
            return _review_public(existing, idempotent_replay=True)
        if event["status"] != PENDING_STATUS:
            raise ProductionFeedbackError("production_feedback_already_reviewed")

        connection.execute(
            """
            INSERT INTO a2_production_feedback_reviews (
              review_id, feedback_id, organization_id, tenant_id, workspace_id,
              project_id, environment_id, event_hash, decision, reason_code,
              reviewer_id_hash, reviewer_receipt_hash, decision_hash,
              reviewed_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                review_id,
                feedback_id,
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
                expected_event_hash,
                normalized_decision,
                reason_code,
                reviewer_id_hash,
                reviewer_receipt_hash,
                decision_hash,
                reviewed,
            ),
        )
        connection.execute(
            """
            UPDATE a2_production_feedback_events
            SET status = ?, updated_at = ?
            WHERE feedback_id = ? AND status = 'pending_review'
              AND organization_id = ? AND tenant_id = ? AND workspace_id = ?
              AND project_id = ? AND environment_id = ?
            """,
            (
                STATUS_BY_REVIEW_DECISION[normalized_decision],
                reviewed,
                feedback_id,
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
            ),
        )
        if connection.execute("SELECT changes()").fetchone()[0] != 1:
            raise ProductionFeedbackError("production_feedback_review_state_conflict")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _review_public(
        _review(connection, feedback_id, normalized_scope),
        idempotent_replay=False,
    )


def get_production_feedback_review(
    connection: sqlite3.Connection,
    *,
    feedback_id: str,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Read one canonical feedback review through the complete tenant scope."""
    normalized_scope = _scope(scope)
    _text(feedback_id, "feedback_id")
    _feedback(connection, feedback_id, normalized_scope)
    return _review_public(
        _review(connection, feedback_id, normalized_scope),
        idempotent_replay=False,
    )


def create_reviewed_feedback_regression_candidate(
    connection: sqlite3.Connection,
    *,
    feedback_id: str,
    scope: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Create an idempotent pending owner-review candidate from accepted feedback."""
    normalized_scope = _scope(scope)
    _text(feedback_id, "feedback_id")
    created = _canonical_timestamp(created_at, "created_at")
    event = _feedback(connection, feedback_id, normalized_scope)
    review = _review(connection, feedback_id, normalized_scope)
    if _timestamp(created) < _timestamp(review["reviewed_at"]):
        raise ProductionFeedbackError(
            "production_feedback_candidate_precedes_review"
        )
    if review["decision"] != "accept":
        raise ProductionFeedbackError(
            "only_accepted_feedback_can_create_regression_candidate"
        )
    if event["event_type"] not in REGRESSION_SOURCE_EVENT_TYPES:
        raise ProductionFeedbackError(
            "feedback_event_type_not_regression_eligible"
        )
    if not event["case_id"] or not event["scenario_id"] or not event["fixture_ref"]:
        raise ProductionFeedbackError(
            "reviewed_feedback_missing_replay_identity"
        )
    private_ref = get_production_feedback_private_ref(
        connection,
        feedback_id=feedback_id,
        scope=normalized_scope,
    )
    incident_report = build_incident_regression_candidate_report(
        _incident_summary(event, review, private_ref["private_evidence_ref"])
    )
    candidates = incident_report.get("candidates", [])
    if (
        len(candidates) != 1
        or candidates[0].get("ready_for_case_book_review") is not True
    ):
        raise ProductionFeedbackError(
            "reviewed_feedback_not_replayable_for_case_book"
        )
    candidate = dict(candidates[0])
    candidate["source"] = "production_feedback_review"
    candidate["evidence_refs"] = sorted(
        {
            str(ref)
            for ref in candidate.get("evidence_refs", [])
            if str(ref).strip() and str(ref) != "inline"
        }
    )
    candidate["feedback_review"] = {
        "feedback_id": feedback_id,
        "review_id": review["review_id"],
        "decision": review["decision"],
        "reason_code": review["reason_code"],
        "reviewer_receipt_hash": review["reviewer_receipt_hash"],
        "reviewed_at": review["reviewed_at"],
        "decision_hash": review["decision_hash"],
        "status": "pending_owner_review",
        "owner_review_required": True,
        "training_eligible": False,
        "human_gold": False,
        "permanent_regression": False,
    }
    candidate_hash = stable_hash(candidate)
    candidate_id = stable_hash(
        {
            "feedback_id": feedback_id,
            "review_id": review["review_id"],
            "candidate_hash": candidate_hash,
        }
    )
    candidate_json = canonical_json(candidate)

    connection.execute("BEGIN IMMEDIATE")
    try:
        current_event = _feedback(connection, feedback_id, normalized_scope)
        current_review = _review(connection, feedback_id, normalized_scope)
        if (
            current_event["event_hash"] != event["event_hash"]
            or current_review["decision_hash"] != review["decision_hash"]
        ):
            raise ProductionFeedbackError(
                "production_feedback_changed_during_candidate_generation"
            )
        existing = _candidate_row(connection, feedback_id, normalized_scope)
        if existing is not None:
            if (
                existing["candidate_hash"] != candidate_hash
                or existing["review_id"] != review["review_id"]
            ):
                raise ProductionFeedbackError(
                    "production_feedback_candidate_conflict"
                )
            connection.commit()
            return _candidate_public(existing, idempotent_replay=True)
        connection.execute(
            """
            INSERT INTO a2_production_feedback_regression_candidates (
              candidate_id, feedback_id, review_id, organization_id, tenant_id,
              workspace_id, project_id, environment_id, event_hash,
              decision_hash, case_id, candidate_json, candidate_hash, status,
              owner_review_required, training_eligible, human_gold,
              permanent_regression, created_at, public_safe
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_owner_review',
              1, 0, 0, 0, ?, 1
            )
            """,
            (
                candidate_id,
                feedback_id,
                review["review_id"],
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
                event["event_hash"],
                review["decision_hash"],
                candidate["case_id"],
                candidate_json,
                candidate_hash,
                created,
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _candidate_public(
        _candidate(connection, feedback_id, normalized_scope),
        idempotent_replay=False,
    )


def get_reviewed_feedback_regression_candidate(
    connection: sqlite3.Connection,
    *,
    feedback_id: str,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    """Read a persisted pending owner-review regression candidate."""
    normalized_scope = _scope(scope)
    _text(feedback_id, "feedback_id")
    _feedback(connection, feedback_id, normalized_scope)
    _review(connection, feedback_id, normalized_scope)
    return _candidate_public(
        _candidate(connection, feedback_id, normalized_scope),
        idempotent_replay=False,
    )


def _incident_summary(
    event: Mapping[str, Any],
    review: Mapping[str, Any],
    private_evidence_ref: str,
) -> dict[str, Any]:
    summary = _stored_public_summary(event)
    failure_type = str(
        summary.get("failure_type")
        or summary.get("reason_code")
        or review["reason_code"]
    )
    assertion = str(
        summary.get("regression_assertion")
        or (
            f"Keep accepted production feedback {event['feedback_id']} "
            f"replayable with failure_type={failure_type}."
        )
    )
    return {
        "schema_version": "a2.production_feedback_incident.v1",
        "incident_id": event["feedback_id"],
        "environment": event["environment_id"],
        "reported_at": event["occurred_at"],
        "title": str(summary.get("title") or event["event_type"]),
        "summary": str(summary.get("summary") or review["reason_code"]),
        "severity": str(summary.get("severity") or "high"),
        "failed_case": {
            "case_id": event["case_id"],
            "scenario_id": event["scenario_id"],
            "fixture_ref": event["fixture_ref"],
            "expected_primary_failure_class": failure_type,
        },
        "evidence_refs": [event["fixture_ref"]],
        "redaction": {
            "public_safe": True,
            "private_evidence_ref": private_evidence_ref,
        },
        "regression_intent": {
            "assertion": assertion,
            "calibration_focus": [
                "production_feedback",
                str(event["event_type"]),
            ],
        },
    }


def _review_public(
    row: Mapping[str, Any],
    *,
    idempotent_replay: bool,
) -> dict[str, Any]:
    core = {
        "feedback_id": row["feedback_id"],
        "scope": {field: row[field] for field in SCOPE_FIELDS},
        "event_hash": row["event_hash"],
        "decision": row["decision"],
        "reason_code": row["reason_code"],
        "reviewer_id_hash": row["reviewer_id_hash"],
        "reviewer_receipt_hash": row["reviewer_receipt_hash"],
        "reviewed_at": row["reviewed_at"],
    }
    if stable_hash(core) != row["decision_hash"]:
        raise ProductionFeedbackError(
            "stored_production_feedback_review_integrity_mismatch"
        )
    if stable_hash(
        {
            "feedback_id": row["feedback_id"],
            "reviewer_receipt_hash": row["reviewer_receipt_hash"],
        }
    ) != row["review_id"]:
        raise ProductionFeedbackError(
            "stored_production_feedback_review_id_mismatch"
        )
    if (
        row["decision"] not in REVIEW_DECISIONS
        or int(row["public_safe"]) != 1
    ):
        raise ProductionFeedbackError(
            "stored_production_feedback_review_state_invalid"
        )
    return {
        "review_id": row["review_id"],
        **core,
        "decision_hash": row["decision_hash"],
        "public_safe": True,
        "human_gold": False,
        "training_eligible": False,
        "permanent_regression": False,
        "idempotent_replay": idempotent_replay,
    }


def _candidate_public(
    row: Mapping[str, Any],
    *,
    idempotent_replay: bool,
) -> dict[str, Any]:
    try:
        candidate = json.loads(row["candidate_json"])
    except (TypeError, ValueError) as exc:
        raise ProductionFeedbackError(
            "stored_production_feedback_candidate_invalid"
        ) from exc
    if not isinstance(candidate, dict) or stable_hash(candidate) != row["candidate_hash"]:
        raise ProductionFeedbackError(
            "stored_production_feedback_candidate_integrity_mismatch"
        )
    if stable_hash(
        {
            "feedback_id": row["feedback_id"],
            "review_id": row["review_id"],
            "candidate_hash": row["candidate_hash"],
        }
    ) != row["candidate_id"]:
        raise ProductionFeedbackError(
            "stored_production_feedback_candidate_id_mismatch"
        )
    if (
        row["status"] != "pending_owner_review"
        or int(row["owner_review_required"]) != 1
        or int(row["training_eligible"]) != 0
        or int(row["human_gold"]) != 0
        or int(row["permanent_regression"]) != 0
        or int(row["public_safe"]) != 1
    ):
        raise ProductionFeedbackError(
            "stored_production_feedback_candidate_state_invalid"
        )
    feedback_review = candidate.get("feedback_review", {})
    if (
        candidate.get("case_id") != row["case_id"]
        or not isinstance(feedback_review, dict)
        or feedback_review.get("feedback_id") != row["feedback_id"]
        or feedback_review.get("review_id") != row["review_id"]
        or feedback_review.get("decision") != "accept"
        or feedback_review.get("decision_hash") != row["decision_hash"]
        or feedback_review.get("status") != "pending_owner_review"
        or feedback_review.get("owner_review_required") is not True
        or feedback_review.get("training_eligible") is not False
        or feedback_review.get("human_gold") is not False
        or feedback_review.get("permanent_regression") is not False
    ):
        raise ProductionFeedbackError(
            "stored_production_feedback_candidate_binding_mismatch"
        )
    report = seal_incident_regression_candidate_report({
        "schema_version": "a2.production_feedback_regression_candidates.v1",
        "report_id": stable_hash(
            {
                "feedback_id": row["feedback_id"],
                "candidate_hash": row["candidate_hash"],
            }
        ),
        "source_feedback_id": row["feedback_id"],
        "candidate_count": 1,
        "ready_candidate_count": 1,
        "ready_for_case_book_review": True,
        "candidates": [candidate],
        "metadata": {
            "deterministic": True,
            "owner_review_required": True,
            "does_not_grant_human_gold": True,
            "does_not_grant_training_eligibility": True,
            "does_not_grant_permanent_regression_status": True,
        },
    })
    return {
        "candidate_id": row["candidate_id"],
        "feedback_id": row["feedback_id"],
        "review_id": row["review_id"],
        "scope": {field: row[field] for field in SCOPE_FIELDS},
        "event_hash": row["event_hash"],
        "decision_hash": row["decision_hash"],
        "case_id": row["case_id"],
        "candidate_hash": row["candidate_hash"],
        "status": row["status"],
        "owner_review_required": True,
        "training_eligible": False,
        "human_gold": False,
        "permanent_regression": False,
        "created_at": row["created_at"],
        "public_safe": True,
        "report": report,
        "idempotent_replay": idempotent_replay,
    }


def _public_row(
    row: Mapping[str, Any],
    *,
    idempotent_replay: bool,
) -> dict[str, Any]:
    summary = _stored_public_summary(row)
    _assert_event_integrity(row)
    return {
        "feedback_id": row["feedback_id"],
        "event_type": row["event_type"],
        "source_event_hash": row["source_event_hash"],
        "subject_hash": row["subject_hash"],
        "scope": {field: row[field] for field in SCOPE_FIELDS},
        "case_id": row["case_id"],
        "scenario_id": row["scenario_id"],
        "fixture_ref": row["fixture_ref"],
        "public_summary": summary,
        "public_summary_hash": row["public_summary_hash"],
        "private_evidence_ref_present": True,
        "private_evidence_ref_hash": row["private_evidence_ref_hash"],
        "review_priority": int(row["review_priority"]),
        "status": row["status"],
        "training_eligible": bool(row["training_eligible"]),
        "human_gold": bool(row["human_gold"]),
        "permanent_regression": bool(row["permanent_regression"]),
        "event_hash": row["event_hash"],
        "occurred_at": row["occurred_at"],
        "received_at": row["received_at"],
        "updated_at": row["updated_at"],
        "public_safe": bool(row["public_safe"]),
        "idempotent_replay": idempotent_replay,
    }


def _stored_public_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    try:
        summary = json.loads(row["public_summary_json"])
    except (TypeError, ValueError) as exc:
        raise ProductionFeedbackError("stored_public_summary_invalid") from exc
    normalized = _public_summary(summary)
    if stable_hash(normalized) != row["public_summary_hash"]:
        raise ProductionFeedbackError("stored_public_summary_integrity_mismatch")
    return normalized


def _assert_event_integrity(row: Mapping[str, Any]) -> None:
    core = {
        "scope": {field: row[field] for field in SCOPE_FIELDS},
        "event_type": row["event_type"],
        "source_event_hash": row["source_event_hash"],
        "subject_hash": row["subject_hash"],
        "case_id": row["case_id"],
        "scenario_id": row["scenario_id"],
        "fixture_ref": row["fixture_ref"],
        "public_summary_hash": row["public_summary_hash"],
        "private_evidence_ref_hash": row["private_evidence_ref_hash"],
        "occurred_at": row["occurred_at"],
        "received_at": row["received_at"],
    }
    if stable_hash(core) != row["event_hash"]:
        raise ProductionFeedbackError("stored_feedback_event_integrity_mismatch")
    if (
        row["status"] not in {PENDING_STATUS, *STATUS_BY_REVIEW_DECISION.values()}
        or int(row["training_eligible"]) != 0
        or int(row["human_gold"]) != 0
        or int(row["permanent_regression"]) != 0
        or int(row["public_safe"]) != 1
    ):
        raise ProductionFeedbackError("stored_feedback_governance_state_invalid")


def _assert_private_ref_integrity(
    connection: sqlite3.Connection,
    event: Mapping[str, Any],
    scope: Mapping[str, str],
    *,
    expected_ref: str,
) -> None:
    row = _private_ref_row(connection, str(event["feedback_id"]), scope)
    if row is None:
        raise ProductionFeedbackError("production_feedback_private_ref_not_found")
    _assert_private_ref_row(event, row)
    if row["private_evidence_ref"] != expected_ref:
        raise ProductionFeedbackError("production_feedback_private_ref_conflict")


def _assert_private_ref_row(
    event: Mapping[str, Any],
    private_row: Mapping[str, Any],
) -> None:
    private_ref = _private_ref(private_row["private_evidence_ref"])
    expected_hash = stable_hash({"private_evidence_ref": private_ref})
    if (
        private_row["feedback_id"] != event["feedback_id"]
        or private_row["private_evidence_ref_hash"] != expected_hash
        or event["private_evidence_ref_hash"] != expected_hash
    ):
        raise ProductionFeedbackError("stored_private_evidence_ref_integrity_mismatch")


def _feedback(
    connection: sqlite3.Connection,
    feedback_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM a2_production_feedback_events WHERE feedback_id = ?",
        (feedback_id,),
    ).fetchone()
    if row is None:
        raise ProductionFeedbackError("production_feedback_not_found")
    value = dict(row)
    _assert_scope_row(value, scope)
    _assert_event_integrity(value)
    review = _review_row(connection, feedback_id, scope)
    if value["status"] == PENDING_STATUS:
        if review is not None:
            raise ProductionFeedbackError(
                "pending_production_feedback_has_review"
            )
    else:
        if review is None:
            raise ProductionFeedbackError(
                "reviewed_production_feedback_missing_review"
            )
        expected_status = STATUS_BY_REVIEW_DECISION.get(review["decision"])
        if (
            expected_status != value["status"]
            or review["event_hash"] != value["event_hash"]
            or review["reviewed_at"] != value["updated_at"]
        ):
            raise ProductionFeedbackError(
                "production_feedback_review_binding_mismatch"
            )
    return value


def _review(
    connection: sqlite3.Connection,
    feedback_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any]:
    row = _review_row(connection, feedback_id, scope)
    if row is None:
        raise ProductionFeedbackError("production_feedback_review_not_found")
    _review_public(row, idempotent_replay=False)
    return row


def _review_row(
    connection: sqlite3.Connection,
    feedback_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT *
        FROM a2_production_feedback_reviews
        WHERE feedback_id = ?
          AND organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ?
        """,
        (
            feedback_id,
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
        ),
    ).fetchone()
    return dict(row) if row is not None else None


def _candidate(
    connection: sqlite3.Connection,
    feedback_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any]:
    row = _candidate_row(connection, feedback_id, scope)
    if row is None:
        raise ProductionFeedbackError(
            "production_feedback_regression_candidate_not_found"
        )
    return row


def _candidate_row(
    connection: sqlite3.Connection,
    feedback_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT *
        FROM a2_production_feedback_regression_candidates
        WHERE feedback_id = ?
          AND organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ?
        """,
        (
            feedback_id,
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
        ),
    ).fetchone()
    return dict(row) if row is not None else None


def _find_by_idempotency(
    connection: sqlite3.Connection,
    scope: Mapping[str, str],
    idempotency_key_hash: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT *
        FROM a2_production_feedback_events
        WHERE organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ?
          AND idempotency_key_hash = ?
        """,
        (
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
            idempotency_key_hash,
        ),
    ).fetchone()
    return dict(row) if row is not None else None


def _find_by_source_event(
    connection: sqlite3.Connection,
    scope: Mapping[str, str],
    source_event_hash: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT *
        FROM a2_production_feedback_events
        WHERE organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ?
          AND source_event_hash = ?
        """,
        (
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
            source_event_hash,
        ),
    ).fetchone()
    return dict(row) if row is not None else None


def _private_ref_row(
    connection: sqlite3.Connection,
    feedback_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT *
        FROM a2_production_feedback_private_refs
        WHERE feedback_id = ?
          AND organization_id = ? AND tenant_id = ? AND workspace_id = ?
          AND project_id = ? AND environment_id = ?
        """,
        (
            feedback_id,
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
        ),
    ).fetchone()
    return dict(row) if row is not None else None


def _scope(scope: Mapping[str, Any]) -> dict[str, str]:
    normalized = {field: str(scope.get(field) or "") for field in SCOPE_FIELDS}
    if any(not value for value in normalized.values()):
        raise ProductionFeedbackError("complete_five_field_scope_required")
    return normalized


def _assert_scope_row(
    row: Mapping[str, Any],
    scope: Mapping[str, str],
) -> None:
    if any(row[field] != expected for field, expected in scope.items()):
        raise ProductionFeedbackError("production_feedback_scope_mismatch")


def _event_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in EVENT_TYPES:
        raise ProductionFeedbackError("unsupported_production_feedback_event_type")
    return normalized


def _review_decision(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in REVIEW_DECISIONS:
        raise ProductionFeedbackError(
            "unsupported_production_feedback_review_decision"
        )
    return normalized


def _public_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionFeedbackError("public_summary_must_be_object")
    summary = dict(value)
    if not summary:
        raise ProductionFeedbackError("public_summary_must_be_non_empty")
    private_fields = sorted(_private_field_names(summary))
    if private_fields:
        raise ProductionFeedbackError(
            "public_summary_contains_private_fields:" + ",".join(private_fields)
        )
    try:
        serialized = canonical_json(summary)
    except (TypeError, ValueError) as exc:
        raise ProductionFeedbackError("public_summary_must_be_json") from exc
    if len(serialized.encode("utf-8")) > PUBLIC_SUMMARY_MAX_BYTES:
        raise ProductionFeedbackError("public_summary_too_large")
    if any(pattern.search(serialized) for pattern in FORBIDDEN_TEXT_PATTERNS):
        raise ProductionFeedbackError("public_summary_contains_forbidden_text")
    return summary


def _private_field_names(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in PRIVATE_FIELD_NAMES:
                found.add(normalized_key)
            found.update(_private_field_names(nested))
    elif isinstance(value, list):
        for item in value:
            found.update(_private_field_names(item))
    return found


def _private_ref(value: Any) -> str:
    if not is_canonical_private_evidence_ref(value):
        raise ProductionFeedbackError(
            "private_evidence_ref_must_be_canonical_repository_reference"
        )
    return str(value)


def _fixture_ref(value: Any) -> str | None:
    normalized = _optional_text(value, "fixture_ref")
    if normalized is None:
        return None
    if (
        "\\" in normalized
        or not normalized.startswith(PUBLIC_FIXTURE_PREFIX)
        or any(segment in {"", ".", ".."} for segment in normalized.split("/"))
    ):
        raise ProductionFeedbackError("fixture_ref_must_be_public_a2_run_reference")
    return normalized


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ProductionFeedbackError(f"{label}_must_be_non_empty_trimmed_text")
    return value


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise ProductionFeedbackError(f"{label}_must_be_sha256")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProductionFeedbackError(f"{label}_must_be_positive_integer")
    return value


def _canonical_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ProductionFeedbackError(f"{label}_must_be_iso_timestamp")
    try:
        return _timestamp(value).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError) as exc:
        raise ProductionFeedbackError(f"{label}_must_be_iso_timestamp") from exc


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone required")
    return parsed.astimezone(timezone.utc)
