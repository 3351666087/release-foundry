"""Tenant-scoped human review for governed preference pairs.

Preference pairs are not release decisions.  This store keeps their review
lease, reviewer receipts, arbitration, and training authority in dedicated
tables so preference learning never has to manufacture an
``a2_release_decisions`` row.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .result_persistence import stable_hash


PREFERENCE_REVIEW_OUTCOMES = {"confirm", "overturn", "abstain", "escalate"}
PREFERENCE_LEARNING_PURPOSES = {
    "reward_model_training",
    "preference_optimization",
    "action_value_training",
}
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def open_preference_review_case(
    connection: sqlite3.Connection,
    *,
    scope: dict[str, str],
    pair: Mapping[str, Any],
    reason_code: str,
    created_at: str,
    required_approvals: int = 1,
) -> dict[str, Any]:
    """Open one idempotent review case for a provisional preference pair."""
    if required_approvals not in {1, 2}:
        raise ValueError("required approvals must be one or two")
    normalized_scope = _scope(scope)
    snapshot = _pair_snapshot(pair)
    created = _canonical_timestamp(created_at, "created_at")
    if pair.get("training_eligible") is True:
        raise ValueError("preference pair is already training eligible")
    review_id = stable_hash(
        {
            "pair_id": snapshot["pair_id"],
            "scope": normalized_scope,
            "reason_code": _text(reason_code, "reason_code"),
        }
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO a2_preference_review_cases (
          review_id, pair_id, pair_hash, pair_scope_hash, task_id, sample_id,
          dataset_identity_hash, prompt_version, prompt_hash,
          media_evidence_hashes_hash, machine_chosen_candidate_id,
          machine_rejected_candidate_id, organization_id, tenant_id,
          workspace_id, project_id, environment_id, reason_code, status,
          required_approvals, lease_generation, created_at, updated_at,
          public_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open',
                  ?, 0, ?, ?, 1)
        """,
        (
            review_id,
            snapshot["pair_id"],
            snapshot["pair_hash"],
            snapshot["pair_scope_hash"],
            snapshot["task_id"],
            snapshot["sample_id"],
            snapshot["dataset_identity_hash"],
            snapshot["prompt_version"],
            snapshot["prompt_hash"],
            snapshot["media_evidence_hashes_hash"],
            snapshot["machine_chosen_candidate_id"],
            snapshot["machine_rejected_candidate_id"],
            normalized_scope["organization_id"],
            normalized_scope["tenant_id"],
            normalized_scope["workspace_id"],
            normalized_scope["project_id"],
            normalized_scope["environment_id"],
            reason_code,
            required_approvals,
            created,
            created,
        ),
    )
    connection.commit()
    row = _review(connection, review_id, normalized_scope)
    _assert_case_matches_pair(row, snapshot)
    if int(row["required_approvals"]) != required_approvals:
        raise ValueError("review case approval requirement conflicts with existing case")
    return {
        "review_id": review_id,
        "pair_id": row["pair_id"],
        "pair_hash": row["pair_hash"],
        "status": row["status"],
        "machine_chosen_candidate_id": row["machine_chosen_candidate_id"],
        "machine_rejected_candidate_id": row["machine_rejected_candidate_id"],
        "required_approvals": row["required_approvals"],
    }


def claim_preference_review_case(
    connection: sqlite3.Connection,
    *,
    review_id: str,
    scope: dict[str, str],
    reviewer_id_hash: str,
    now: str,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    """Acquire a fenced reviewer lease for a preference pair."""
    if not reviewer_id_hash or lease_seconds <= 0:
        raise ValueError("reviewer identity hash and positive lease are required")
    normalized_scope = _scope(scope)
    claimed_at = _canonical_timestamp(now, "now")
    current = _timestamp(claimed_at)
    expires = (current + timedelta(seconds=lease_seconds)).isoformat().replace(
        "+00:00", "Z"
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = _review(connection, review_id, normalized_scope)
        active = row["lease_expires_at"] and _timestamp(row["lease_expires_at"]) > current
        if row["status"] in {"completed", "arbitration"}:
            raise ValueError(f"review case is {row['status']}")
        if active:
            raise ValueError("review case lease contention")
        prior_vote = connection.execute(
            """
            SELECT 1 FROM a2_preference_review_events
            WHERE review_id = ? AND reviewer_id_hash = ?
            """,
            (review_id, reviewer_id_hash),
        ).fetchone()
        if prior_vote is not None:
            raise ValueError("reviewer has already submitted a disposition")
        generation = int(row["lease_generation"]) + 1
        cursor = connection.execute(
            """
            UPDATE a2_preference_review_cases
            SET status = 'leased', lease_owner_hash = ?, lease_generation = ?,
                lease_expires_at = ?, updated_at = ?
            WHERE review_id = ? AND lease_generation = ?
            """,
            (
                reviewer_id_hash,
                generation,
                expires,
                claimed_at,
                review_id,
                row["lease_generation"],
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError("review case lease contention")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "review_id": review_id,
        "reviewer_id_hash": reviewer_id_hash,
        "lease_generation": generation,
        "lease_expires_at": expires,
    }


def submit_preference_review(
    connection: sqlite3.Connection,
    *,
    lease: Mapping[str, Any],
    scope: dict[str, str],
    pair: Mapping[str, Any],
    outcome: str,
    chosen_candidate_id: str | None,
    rejected_candidate_id: str | None,
    reason_code: str,
    reviewer_receipt_hash: str,
    submitted_at: str,
    learning: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record one reviewer disposition and resolve consensus when possible."""
    if outcome not in PREFERENCE_REVIEW_OUTCOMES:
        raise ValueError("unsupported preference review outcome")
    normalized_scope = _scope(scope)
    snapshot = _pair_snapshot(pair)
    submitted = _canonical_timestamp(submitted_at, "submitted_at")
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = _review(connection, str(lease["review_id"]), normalized_scope)
        _assert_case_matches_pair(row, snapshot)
        _assert_active_lease(row, lease, submitted)
        selected = _selected_pair(
            snapshot,
            outcome=outcome,
            chosen_candidate_id=chosen_candidate_id,
            rejected_candidate_id=rejected_candidate_id,
        )
        receipt_hash = _hash(reviewer_receipt_hash, "reviewer_receipt_hash")
        reason = _text(reason_code, "reason_code")
        event_core = {
            "review_id": row["review_id"],
            "pair_id": row["pair_id"],
            "pair_hash": row["pair_hash"],
            "reviewer_id_hash": lease["reviewer_id_hash"],
            "lease_generation": int(lease["lease_generation"]),
            "outcome": outcome,
            "chosen_candidate_id": selected["chosen_candidate_id"],
            "rejected_candidate_id": selected["rejected_candidate_id"],
            "reason_code": reason,
            "reviewer_receipt_hash": receipt_hash,
            "submitted_at": submitted,
        }
        event_hash = stable_hash(event_core)
        event_id = stable_hash({"review_id": row["review_id"], "event_hash": event_hash})
        connection.execute(
            """
            INSERT INTO a2_preference_review_events (
              event_id, review_id, pair_id, pair_hash, organization_id, tenant_id,
              workspace_id, project_id, environment_id, reviewer_id_hash,
              lease_generation, outcome, chosen_candidate_id, rejected_candidate_id,
              reason_code, reviewer_receipt_hash, event_hash, created_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                event_id,
                row["review_id"],
                row["pair_id"],
                row["pair_hash"],
                normalized_scope["organization_id"],
                normalized_scope["tenant_id"],
                normalized_scope["workspace_id"],
                normalized_scope["project_id"],
                normalized_scope["environment_id"],
                lease["reviewer_id_hash"],
                int(lease["lease_generation"]),
                outcome,
                selected["chosen_candidate_id"],
                selected["rejected_candidate_id"],
                reason,
                receipt_hash,
                event_hash,
                submitted,
            ),
        )
        resolution = _resolve_preference_review(
            connection,
            row=row,
            event_id=event_id,
            submitted_at=submitted,
        )
        learning_candidate = None
        learning_blocked_reason = None
        if resolution["status"] == "completed":
            resolution_record = _write_preference_resolution(
                connection,
                row=row,
                scope=normalized_scope,
                resolution_type="review_consensus",
                final_event_id=event_id,
                final_outcome=outcome,
                chosen_candidate_id=selected["chosen_candidate_id"],
                rejected_candidate_id=selected["rejected_candidate_id"],
                reviewer_receipt_hash=receipt_hash,
                final_reason_code=reason,
                approval_count=resolution["approval_count"],
                resolved_at=submitted,
                arbitrator_id_hash=None,
            )
            learning_candidate = _create_preference_learning_candidate(
                connection,
                resolution=resolution_record,
                review_event_id=event_id,
                scope=normalized_scope,
                learning=learning,
                created_at=submitted,
            )
        elif learning is not None:
            learning_blocked_reason = (
                "review_not_completed_or_conflict_requires_arbitration"
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "review_id": row["review_id"],
        "event_id": event_id,
        "pair_id": row["pair_id"],
        "outcome": outcome,
        "chosen_candidate_id": selected["chosen_candidate_id"],
        "rejected_candidate_id": selected["rejected_candidate_id"],
        "status": resolution["status"],
        "approval_count": resolution["approval_count"],
        "disposition_count": resolution["disposition_count"],
        "resolution": (
            get_authoritative_preference_review_resolution(
                connection, review_id=row["review_id"], scope=normalized_scope
            )
            if resolution["status"] == "completed"
            else None
        ),
        "learning_candidate": learning_candidate,
        "learning_blocked_reason": learning_blocked_reason,
    }


def resolve_preference_arbitration(
    connection: sqlite3.Connection,
    *,
    review_id: str,
    scope: dict[str, str],
    pair: Mapping[str, Any],
    arbitrator_id_hash: str,
    arbitrator_role: str,
    chosen_candidate_id: str,
    rejected_candidate_id: str,
    reviewer_receipt_hash: str,
    reason_code: str,
    resolved_at: str,
    learning: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve a conflicted preference review with an independent arbitrator."""
    if arbitrator_role != "preference_arbitrator" or not arbitrator_id_hash:
        raise ValueError("preference_arbitrator role and identity are required")
    normalized_scope = _scope(scope)
    snapshot = _pair_snapshot(pair)
    selected = _selected_pair(
        snapshot,
        outcome="overturn"
        if (
            chosen_candidate_id != snapshot["machine_chosen_candidate_id"]
            or rejected_candidate_id != snapshot["machine_rejected_candidate_id"]
        )
        else "confirm",
        chosen_candidate_id=chosen_candidate_id,
        rejected_candidate_id=rejected_candidate_id,
    )
    receipt_hash = _hash(reviewer_receipt_hash, "reviewer_receipt_hash")
    reason = _text(reason_code, "reason_code")
    resolved = _canonical_timestamp(resolved_at, "resolved_at")
    connection.execute("BEGIN IMMEDIATE")
    try:
        row = _review(connection, review_id, normalized_scope)
        _assert_case_matches_pair(row, snapshot)
        if row["status"] != "arbitration":
            raise ValueError("review case is not awaiting arbitration")
        prior = connection.execute(
            """
            SELECT 1 FROM a2_preference_review_events
            WHERE review_id = ? AND reviewer_id_hash = ?
            """,
            (review_id, arbitrator_id_hash),
        ).fetchone()
        if prior is not None:
            raise ValueError("arbitrator must be independent from prior reviewers")
        count = connection.execute(
            """
            SELECT COUNT(*) FROM a2_preference_review_events
            WHERE review_id = ? AND outcome IN ('confirm', 'overturn')
            """,
            (review_id,),
        ).fetchone()[0]
        final_outcome = (
            "confirm"
            if (
                selected["chosen_candidate_id"]
                == snapshot["machine_chosen_candidate_id"]
                and selected["rejected_candidate_id"]
                == snapshot["machine_rejected_candidate_id"]
            )
            else "overturn"
        )
        resolution = _write_preference_resolution(
            connection,
            row=row,
            scope=normalized_scope,
            resolution_type="arbitration",
            final_event_id=None,
            final_outcome=final_outcome,
            chosen_candidate_id=selected["chosen_candidate_id"],
            rejected_candidate_id=selected["rejected_candidate_id"],
            reviewer_receipt_hash=receipt_hash,
            final_reason_code=reason,
            approval_count=max(1, int(count)),
            resolved_at=resolved,
            arbitrator_id_hash=arbitrator_id_hash,
        )
        connection.execute(
            """
            UPDATE a2_preference_review_cases
            SET status = 'completed', lease_owner_hash = NULL,
                lease_expires_at = NULL, updated_at = ?
            WHERE review_id = ? AND status = 'arbitration'
            """,
            (resolved, review_id),
        )
        learning_candidate = _create_preference_learning_candidate(
            connection,
            resolution=resolution,
            review_event_id=None,
            scope=normalized_scope,
            learning=learning,
            created_at=resolved,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return {
        "review_id": review_id,
        "pair_id": row["pair_id"],
        "status": "completed",
        "resolution": get_authoritative_preference_review_resolution(
            connection, review_id=review_id, scope=normalized_scope
        ),
        "learning_candidate": learning_candidate,
    }


def get_authoritative_preference_review_resolution(
    connection: sqlite3.Connection,
    *,
    review_id: str,
    scope: dict[str, str],
    pair: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return only a completed human-gold preference resolution."""
    normalized_scope = _scope(scope)
    review = _review(connection, review_id, normalized_scope)
    if review["status"] != "completed":
        return None
    if pair is not None:
        _assert_case_matches_pair(review, _pair_snapshot(pair))
    stored = connection.execute(
        """
        SELECT * FROM a2_preference_review_resolutions
        WHERE review_id = ?
        """,
        (review_id,),
    ).fetchone()
    if stored is None:
        return None
    value = dict(stored)
    _assert_scope_row(value, normalized_scope)
    if value["pair_id"] != review["pair_id"] or value["pair_hash"] != review["pair_hash"]:
        raise ValueError("preference resolution pair hash mismatch")
    core = _resolution_core(value)
    if stable_hash(core) != value["resolution_hash"]:
        raise ValueError("preference resolution integrity mismatch")
    reviewed_at = _timestamp(value["resolved_at"])
    return {
        **core,
        "resolution_id": value["resolution_id"],
        "resolution_hash": value["resolution_hash"],
        "preference_authority": "human_gold",
        "training_eligible": True,
        "review_status": "reviewed",
        "human_adjudication": {
            "review_status": "reviewed",
            "chosen_candidate_id": value["chosen_candidate_id"],
            "rejected_candidate_id": value["rejected_candidate_id"],
            "review_id_hash": value["review_id"],
            "reviewer_receipt_hash": value["reviewer_receipt_hash"],
            "reviewed_at_unix_ms": int(reviewed_at.timestamp() * 1000),
            "review_reason_code": value["final_reason_code"],
        },
    }


def _pair_snapshot(pair: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(pair, Mapping):
        raise ValueError("preference pair must be an object")
    pair_id = _hash(pair.get("pair_id"), "pair_id")
    core = {key: value for key, value in pair.items() if key != "pair_id"}
    if stable_hash(core) != pair_id:
        raise ValueError("preference pair hash mismatch")
    pair_scope = pair.get("scope")
    if not isinstance(pair_scope, Mapping):
        raise ValueError("preference pair scope is required")
    required_scope = (
        "task_id",
        "sample_id",
        "dataset_identity_hash",
        "prompt_version",
        "prompt_hash",
        "media_evidence_hashes",
    )
    if any(not pair_scope.get(field) for field in required_scope):
        raise ValueError("preference pair scope is incomplete")
    candidates = pair.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise ValueError("preference pair candidates are incomplete")
    candidate_ids = {
        str(candidate.get("candidate_id"))
        for candidate in candidates
        if isinstance(candidate, Mapping)
    }
    if len(candidate_ids) != len(candidates) or "" in candidate_ids:
        raise ValueError("preference pair candidate ids are invalid")
    provisional = pair.get("releasefoundry_provisional_preference")
    if not isinstance(provisional, Mapping):
        raise ValueError("preference pair has no provisional machine preference")
    machine_chosen = str(provisional.get("chosen_candidate_id") or "")
    machine_rejected = str(provisional.get("rejected_candidate_id") or "")
    if (
        not machine_chosen
        or not machine_rejected
        or machine_chosen == machine_rejected
        or {machine_chosen, machine_rejected} - candidate_ids
    ):
        raise ValueError("preference pair machine preference is invalid")
    return {
        "pair_id": pair_id,
        "pair_hash": pair_id,
        "pair_scope_hash": stable_hash(dict(pair_scope)),
        "task_id": str(pair_scope["task_id"]),
        "sample_id": str(pair_scope["sample_id"]),
        "dataset_identity_hash": _hash(
            pair_scope["dataset_identity_hash"], "dataset_identity_hash"
        ),
        "prompt_version": str(pair_scope["prompt_version"]),
        "prompt_hash": _hash(pair_scope["prompt_hash"], "prompt_hash"),
        "media_evidence_hashes_hash": stable_hash(
            list(pair_scope["media_evidence_hashes"])
        ),
        "candidate_ids": candidate_ids,
        "machine_chosen_candidate_id": machine_chosen,
        "machine_rejected_candidate_id": machine_rejected,
    }


def _selected_pair(
    snapshot: Mapping[str, Any],
    *,
    outcome: str,
    chosen_candidate_id: str | None,
    rejected_candidate_id: str | None,
) -> dict[str, str | None]:
    if outcome in {"abstain", "escalate"}:
        if chosen_candidate_id is not None or rejected_candidate_id is not None:
            raise ValueError("non-conclusive review cannot select a preference pair")
        return {"chosen_candidate_id": None, "rejected_candidate_id": None}
    chosen = _text(chosen_candidate_id, "chosen_candidate_id")
    rejected = _text(rejected_candidate_id, "rejected_candidate_id")
    if chosen == rejected or {chosen, rejected} - set(snapshot["candidate_ids"]):
        raise ValueError("selected preference pair is invalid")
    machine = (
        snapshot["machine_chosen_candidate_id"],
        snapshot["machine_rejected_candidate_id"],
    )
    selected = (chosen, rejected)
    if outcome == "confirm" and selected != machine:
        raise ValueError("confirm must preserve the machine preference")
    if outcome == "overturn" and selected == machine:
        raise ValueError("overturn must change the machine preference")
    return {"chosen_candidate_id": chosen, "rejected_candidate_id": rejected}


def _resolve_preference_review(
    connection: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    event_id: str,
    submitted_at: str,
) -> dict[str, Any]:
    events = [
        dict(item)
        for item in connection.execute(
            """
            SELECT outcome, chosen_candidate_id, rejected_candidate_id
            FROM a2_preference_review_events
            WHERE review_id = ?
            ORDER BY julianday(created_at), event_id
            """,
            (row["review_id"],),
        ).fetchall()
    ]
    disposition_count = len(events)
    qualifying = [item for item in events if item["outcome"] in {"confirm", "overturn"}]
    approval_count = len(qualifying)
    required = int(row["required_approvals"])
    status = "open"
    final_event_id = None
    if disposition_count >= required:
        signatures = {
            (
                item["outcome"],
                item["chosen_candidate_id"],
                item["rejected_candidate_id"],
            )
            for item in events
        }
        if approval_count == required and len(signatures) == 1:
            status = "completed"
            final_event_id = event_id
        else:
            status = "arbitration"
    connection.execute(
        """
        UPDATE a2_preference_review_cases
        SET status = ?, lease_owner_hash = NULL, lease_expires_at = ?,
            final_event_id = ?, updated_at = ?
        WHERE review_id = ? AND lease_generation = ?
        """,
        (
            status,
            None,
            final_event_id,
            submitted_at,
            row["review_id"],
            row["lease_generation"],
        ),
    )
    return {
        "status": status,
        "approval_count": approval_count,
        "disposition_count": disposition_count,
    }


def _write_preference_resolution(
    connection: sqlite3.Connection,
    *,
    row: Mapping[str, Any],
    scope: Mapping[str, str],
    resolution_type: str,
    final_event_id: str | None,
    final_outcome: str,
    chosen_candidate_id: str,
    rejected_candidate_id: str,
    reviewer_receipt_hash: str,
    final_reason_code: str,
    approval_count: int,
    resolved_at: str,
    arbitrator_id_hash: str | None,
) -> dict[str, Any]:
    core = {
        "review_id": row["review_id"],
        "pair_id": row["pair_id"],
        "pair_hash": row["pair_hash"],
        **scope,
        "resolution_type": resolution_type,
        "final_event_id": final_event_id,
        "final_outcome": final_outcome,
        "chosen_candidate_id": chosen_candidate_id,
        "rejected_candidate_id": rejected_candidate_id,
        "machine_chosen_candidate_id": row["machine_chosen_candidate_id"],
        "machine_rejected_candidate_id": row["machine_rejected_candidate_id"],
        "reviewer_receipt_hash": reviewer_receipt_hash,
        "final_reason_code": final_reason_code,
        "approval_count": approval_count,
        "required_approvals": int(row["required_approvals"]),
        "arbitrator_id_hash": arbitrator_id_hash,
        "preference_authority": "human_gold",
        "training_eligible": True,
        "resolved_at": resolved_at,
    }
    resolution_hash = stable_hash(core)
    resolution_id = stable_hash(
        {"review_id": row["review_id"], "resolution_hash": resolution_hash}
    )
    connection.execute(
        """
        INSERT INTO a2_preference_review_resolutions (
          resolution_id, review_id, pair_id, pair_hash, organization_id, tenant_id,
          workspace_id, project_id, environment_id, resolution_type,
          final_event_id, final_outcome, chosen_candidate_id,
          rejected_candidate_id, machine_chosen_candidate_id,
          machine_rejected_candidate_id, reviewer_receipt_hash,
          final_reason_code, approval_count, required_approvals,
          arbitrator_id_hash, preference_authority, training_eligible,
          resolution_hash, resolved_at, public_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      'human_gold', 1, ?, ?, 1)
        """,
        (
            resolution_id,
            row["review_id"],
            row["pair_id"],
            row["pair_hash"],
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
            resolution_type,
            final_event_id,
            final_outcome,
            chosen_candidate_id,
            rejected_candidate_id,
            row["machine_chosen_candidate_id"],
            row["machine_rejected_candidate_id"],
            reviewer_receipt_hash,
            final_reason_code,
            approval_count,
            int(row["required_approvals"]),
            arbitrator_id_hash,
            resolution_hash,
            resolved_at,
        ),
    )
    return {
        **core,
        "resolution_id": resolution_id,
        "resolution_hash": resolution_hash,
    }


def _create_preference_learning_candidate(
    connection: sqlite3.Connection,
    *,
    resolution: Mapping[str, Any],
    review_event_id: str | None,
    scope: Mapping[str, str],
    learning: Mapping[str, Any] | None,
    created_at: str,
) -> dict[str, Any] | None:
    if learning is None:
        return None
    required = {
        "consent_id_hash",
        "purpose",
        "lineage_hash",
        "residency",
        "retention_until",
        "deletion_key_hash",
    }
    if set(learning) != required or any(not learning[field] for field in required):
        raise ValueError("learning governance metadata is incomplete")
    if learning["purpose"] not in PREFERENCE_LEARNING_PURPOSES:
        raise ValueError("unsupported preference learning purpose")
    candidate_id = stable_hash(
        {"resolution_id": resolution["resolution_id"], "purpose": learning["purpose"]}
    )
    connection.execute(
        """
        INSERT INTO a2_preference_learning_candidates (
          candidate_id, resolution_id, review_event_id, pair_id,
          organization_id, tenant_id, workspace_id, project_id, environment_id,
          consent_id_hash, purpose, lineage_hash, residency, retention_until,
          deletion_key_hash, status, cross_tenant_allowed, created_at, public_safe
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'eligible', 0, ?, 1)
        """,
        (
            candidate_id,
            resolution["resolution_id"],
            review_event_id,
            resolution["pair_id"],
            scope["organization_id"],
            scope["tenant_id"],
            scope["workspace_id"],
            scope["project_id"],
            scope["environment_id"],
            learning["consent_id_hash"],
            learning["purpose"],
            learning["lineage_hash"],
            learning["residency"],
            learning["retention_until"],
            learning["deletion_key_hash"],
            created_at,
        ),
    )
    return {
        "candidate_id": candidate_id,
        "resolution_id": resolution["resolution_id"],
        "pair_id": resolution["pair_id"],
        "status": "eligible",
        "cross_tenant_allowed": False,
    }


def _assert_active_lease(
    row: Mapping[str, Any],
    lease: Mapping[str, Any],
    submitted_at: str,
) -> None:
    if (
        row["status"] != "leased"
        or row["lease_owner_hash"] != lease["reviewer_id_hash"]
        or int(row["lease_generation"]) != int(lease["lease_generation"])
    ):
        raise ValueError("stale review lease")
    if (
        not row["lease_expires_at"]
        or _timestamp(row["lease_expires_at"]) <= _timestamp(submitted_at)
    ):
        raise ValueError("review lease expired")


def _assert_case_matches_pair(
    row: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> None:
    for field in (
        "pair_id",
        "pair_hash",
        "pair_scope_hash",
        "task_id",
        "sample_id",
        "dataset_identity_hash",
        "prompt_version",
        "prompt_hash",
        "media_evidence_hashes_hash",
        "machine_chosen_candidate_id",
        "machine_rejected_candidate_id",
    ):
        if row[field] != snapshot[field]:
            raise ValueError("preference review pair identity mismatch")


def _assert_scope_row(row: Mapping[str, Any], scope: Mapping[str, str]) -> None:
    if any(row[field] != expected for field, expected in scope.items()):
        raise ValueError("preference review scope mismatch")


def _resolution_core(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "review_id",
        "pair_id",
        "pair_hash",
        "organization_id",
        "tenant_id",
        "workspace_id",
        "project_id",
        "environment_id",
        "resolution_type",
        "final_event_id",
        "final_outcome",
        "chosen_candidate_id",
        "rejected_candidate_id",
        "machine_chosen_candidate_id",
        "machine_rejected_candidate_id",
        "reviewer_receipt_hash",
        "final_reason_code",
        "approval_count",
        "required_approvals",
        "arbitrator_id_hash",
        "preference_authority",
        "training_eligible",
        "resolved_at",
    )
    return {
        field: bool(value[field]) if field == "training_eligible" else value[field]
        for field in fields
    }


def _scope(scope: Mapping[str, Any]) -> dict[str, str]:
    fields = (
        "organization_id",
        "tenant_id",
        "workspace_id",
        "project_id",
        "environment_id",
    )
    normalized = {field: str(scope.get(field) or "") for field in fields}
    if any(not value for value in normalized.values()):
        raise ValueError("complete five-field tenant scope is required")
    return normalized


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must be a sha256 hash")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty")
    return value


def _review(
    connection: sqlite3.Connection,
    review_id: str,
    scope: Mapping[str, str],
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM a2_preference_review_cases WHERE review_id = ?",
        (review_id,),
    ).fetchone()
    if row is None:
        raise ValueError("preference review case not found")
    value = dict(row)
    _assert_scope_row(value, scope)
    return value


def _canonical_timestamp(value: Any, field: str) -> str:
    try:
        parsed = _timestamp(value)
    except ValueError as exc:
        raise ValueError(
            f"{field} must be a valid timezone-aware ISO-8601 timestamp"
        ) from exc
    return parsed.isoformat().replace("+00:00", "Z")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a timezone-aware ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "timestamp must be a valid timezone-aware ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be a timezone-aware ISO-8601 timestamp")
    return parsed.astimezone(timezone.utc)
