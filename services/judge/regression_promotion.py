"""Public-safe C5 regression promotion queue."""

from __future__ import annotations

from typing import Any

from .casebook import verify_case_book_artifact
from .incident_regression import verify_incident_regression_candidate_report
from .regression_replay import verify_regression_replay_artifact
from .result_persistence import stable_hash


SCHEMA_VERSION = "a2.regression_promotion_queue.v1"
DEFAULT_QUEUE_ID = "a2_regression_promotion_queue"
TARGET_MATURE_REPLAY_CASE_COUNT = 3
QUEUE_REF = "fixtures/a2/results/a2_regression_promotion_queue.json"
CASE_BOOK_REF = "fixtures/a2/results/a2_case_book.json"
INCIDENT_CANDIDATES_REF = "fixtures/a2/results/a2_incident_regression_candidates.json"
REGRESSION_REPLAY_REF = "fixtures/a2/results/a2_regression_replay_report.json"


def build_regression_promotion_queue_report(
    case_book_report: dict[str, Any],
    incident_candidates_report: dict[str, Any],
    regression_replay_report: dict[str, Any],
) -> dict[str, Any]:
    """Turn open incident candidates into a release-gate-friendly C5 promotion queue."""
    case_book_report = _object(case_book_report, field="case_book_report")
    incident_candidates_report = _object(
        incident_candidates_report,
        field="incident_candidates_report",
    )
    regression_replay_report = _object(
        regression_replay_report,
        field="regression_replay_report",
    )
    regression_cases = _object_list(
        case_book_report.get("regression_cases", []),
        field="case_book_report.regression_cases",
    )
    replay_cases = _object_list(
        regression_replay_report.get("cases", []),
        field="regression_replay_report.cases",
    )
    candidates = _object_list(
        incident_candidates_report.get("candidates", []),
        field="incident_candidates_report.candidates",
    )
    source_case_book_hash = verify_case_book_artifact(case_book_report)
    source_incident_candidates_hash = (
        verify_incident_regression_candidate_report(incident_candidates_report)
    )
    source_regression_replay_hash = verify_regression_replay_artifact(
        regression_replay_report
    )
    case_book_ids = {
        str(case.get("case_id", ""))
        for case in regression_cases
    }
    replay_case_ids = {
        str(case.get("case_id", ""))
        for case in replay_cases
    }
    promotion_items = [
        _promotion_item(
            candidate,
            case_book_ids,
            replay_case_ids,
            source_incident_candidates_hash=source_incident_candidates_hash,
        )
        for candidate in candidates
    ]
    review_ready_items = [item for item in promotion_items if item["queue_status"] == "ready_for_owner_review"]
    evidence_blocked_items = [
        item for item in promotion_items if "needs_reviewed_releasefoundry_or_audited_semantic_evidence" in item["promotion_blockers"]
    ]
    replay_maturity = _object(
        regression_replay_report.get("maturity_gate", {}),
        field="regression_replay_report.maturity_gate",
    )
    release_gate_summary = _object(
        regression_replay_report.get("release_gate_summary", {}),
        field="regression_replay_report.release_gate_summary",
    )
    current_replay_count = _non_negative_count(
        replay_maturity.get(
            "current_replay_case_count",
            regression_replay_report.get("replay_case_count", 0),
        ),
        field="current_replay_case_count",
    )
    target_count = _non_negative_count(
        replay_maturity.get(
            "target_replay_case_count",
            TARGET_MATURE_REPLAY_CASE_COUNT,
        ),
        field="target_replay_case_count",
    )
    if target_count < TARGET_MATURE_REPLAY_CASE_COUNT:
        raise ValueError(
            "regression promotion target_replay_case_count "
            f"must be at least {TARGET_MATURE_REPLAY_CASE_COUNT}"
        )
    missing_replay_count = max(0, target_count - current_replay_count)
    report = {
        "schema_version": SCHEMA_VERSION,
        "queue_id": DEFAULT_QUEUE_ID,
        "source_case_book": str(case_book_report.get("case_book_id", "")),
        "source_case_book_hash": source_case_book_hash,
        "source_incident_candidates": str(incident_candidates_report.get("report_id", "")),
        "source_incident_candidates_hash": source_incident_candidates_hash,
        "source_regression_replay": str(regression_replay_report.get("replay_id", "")),
        "source_regression_replay_hash": source_regression_replay_hash,
        "target_mature_replay_case_count": target_count,
        "current_replay_case_count": current_replay_count,
        "missing_replay_case_count": missing_replay_count,
        "promotion_candidate_count": len(promotion_items),
        "ready_for_owner_review_count": len(review_ready_items),
        "evidence_blocked_count": len(evidence_blocked_items),
        "queue_status": _queue_status(missing_replay_count, promotion_items, evidence_blocked_items),
        "release_gate_summary": _release_gate_summary(release_gate_summary, missing_replay_count, promotion_items),
        "promotion_items": promotion_items,
        "next_actions": _next_actions(missing_replay_count, review_ready_items, evidence_blocked_items),
        "evidence_refs": [
            CASE_BOOK_REF,
            INCIDENT_CANDIDATES_REF,
            REGRESSION_REPLAY_REF,
        ],
        "metadata": {
            "deterministic": True,
            "purpose": "Make production incident to C5 regression promotion explicit, reviewable, and public-safe.",
            "does_not_execute_live_calls": True,
            "does_not_read_private_evidence": True,
            "private_evidence_boundary": "Private evidence refs may be named, but raw private payloads stay under docs/evidence/private_refs/ and are not read.",
        },
    }
    return {**report, "artifact_hash": stable_hash(report)}


def _promotion_item(
    candidate: dict[str, Any],
    case_book_ids: set[str],
    replay_case_ids: set[str],
    *,
    source_incident_candidates_hash: str,
) -> dict[str, Any]:
    case_id = _non_empty_string(candidate.get("case_id"), field="candidate.case_id")
    blockers = _string_list(
        candidate.get("promotion_blockers", []),
        field=f"candidate[{case_id}].promotion_blockers",
    )
    in_case_book = case_id in case_book_ids
    in_replay = case_id in replay_case_ids
    public_safe = candidate.get("public_safe") is True
    ready_for_case_book_review = candidate.get("ready_for_case_book_review") is True
    queue_status = _item_status(
        in_replay=in_replay,
        in_case_book=in_case_book,
        public_safe=public_safe,
        ready_for_case_book_review=ready_for_case_book_review,
    )
    return {
        "promotion_id": f"promotion-{candidate.get('regression_id', case_id)}",
        "source_incident_candidates_hash": source_incident_candidates_hash,
        "candidate_hash": stable_hash(candidate),
        "queue_status": queue_status,
        "case_id": case_id,
        "scenario_id": str(candidate.get("scenario_id", "")),
        "fixture_ref": str(candidate.get("fixture_ref", "")),
        "source": str(candidate.get("source", "")),
        "incident_id": str(candidate.get("incident_id", "")),
        "severity": str(candidate.get("severity", "")),
        "primary_failure_class": str(
            _object(
                candidate.get("expected", {}),
                field=f"candidate[{case_id}].expected",
            ).get("primary_failure_class", "")
        ),
        "public_safe": public_safe,
        "ready_for_case_book_review": ready_for_case_book_review,
        "already_in_case_book": in_case_book,
        "already_in_regression_replay": in_replay,
        "can_promote_to_case_book": public_safe and ready_for_case_book_review and not in_case_book,
        "can_promote_to_mature_replay": False,
        "promotion_blockers": blockers,
        "required_reviews": _required_reviews(blockers),
        "required_evidence_sources": _required_evidence_sources(blockers),
        "reviewer_note": str(candidate.get("reviewer_note", "")),
        "evidence_refs": _string_list(
            candidate.get("evidence_refs", []),
            field=f"candidate[{case_id}].evidence_refs",
        ),
    }


def _object(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"regression promotion {field} must be an object")
    return value


def _object_list(value: Any, *, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise TypeError(f"regression promotion {field} must be a list")
    if any(not isinstance(item, dict) for item in value):
        raise TypeError(f"regression promotion {field} entries must be objects")
    return value


def _string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"regression promotion {field} must be a list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(
            f"regression promotion {field} entries must be non-empty strings"
        )
    return [item.strip() for item in value]


def _non_empty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"regression promotion {field} must be a non-empty string")
    return value.strip()


def _non_negative_count(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"regression promotion {field} must be a non-negative integer"
        )
    return value


def _item_status(
    *,
    in_replay: bool,
    in_case_book: bool,
    public_safe: bool,
    ready_for_case_book_review: bool,
) -> str:
    if in_replay:
        return "already_replayed"
    if in_case_book:
        return "in_case_book_waiting_for_replay_maturity"
    if public_safe and ready_for_case_book_review:
        return "ready_for_owner_review"
    return "blocked_before_review"


def _required_reviews(blockers: list[str]) -> list[str]:
    reviews = []
    if "needs_case_book_owner_review" in blockers:
        reviews.append("A2 case-book owner")
    if "needs_reviewed_releasefoundry_or_audited_semantic_evidence" in blockers:
        reviews.append("A2 evidence reviewer")
    return reviews


def _required_evidence_sources(blockers: list[str]) -> list[str]:
    if "needs_reviewed_releasefoundry_or_audited_semantic_evidence" not in blockers:
        return []
    return ["reviewed_releasefoundry_grading", "audited_semantic_judge"]


def _queue_status(
    missing_replay_count: int,
    promotion_items: list[dict[str, Any]],
    evidence_blocked_items: list[dict[str, Any]],
) -> str:
    if missing_replay_count == 0:
        return "replay_target_met"
    if not promotion_items:
        return "no_candidates"
    if evidence_blocked_items:
        return "candidate_review_required"
    return "ready_to_promote"


def _release_gate_summary(
    replay_release_gate: dict[str, Any],
    missing_replay_count: int,
    promotion_items: list[dict[str, Any]],
) -> dict[str, Any]:
    blocks_release = replay_release_gate.get(
        "blocks_release",
        missing_replay_count > 0,
    )
    if not isinstance(blocks_release, bool):
        raise ValueError(
            "regression promotion release_gate_summary.blocks_release "
            "must be a boolean"
        )
    return {
        "schema_version": "a2.regression_promotion.release_gate_summary.v1",
        "gate": "C5",
        "blocks_release": blocks_release,
        "upstream_replay_status": str(replay_release_gate.get("release_gate_status", "")),
        "candidate_supply_status": "has_candidates" if promotion_items else "missing_candidates",
        "missing_replay_case_count": missing_replay_count,
        "promotion_candidate_count": len(promotion_items),
        "required_action": _required_release_action(missing_replay_count, promotion_items),
        "evidence_refs": [QUEUE_REF, REGRESSION_REPLAY_REF, INCIDENT_CANDIDATES_REF],
    }


def _required_release_action(missing_replay_count: int, promotion_items: list[dict[str, Any]]) -> str:
    if missing_replay_count == 0:
        return "No C5 promotion action required."
    if not promotion_items:
        return "Add production incident or disagreement candidates before C5 can mature."
    return "Review queued incident candidates, attach reviewed external evidence, then promote accepted cases into replay."


def _next_actions(
    missing_replay_count: int,
    review_ready_items: list[dict[str, Any]],
    evidence_blocked_items: list[dict[str, Any]],
) -> list[str]:
    actions = []
    if missing_replay_count > 0:
        actions.append(f"Promote {missing_replay_count} more reviewed C5 regression case(s).")
    if review_ready_items:
        actions.append("Run A2 case-book owner review for queued production incident candidates.")
    if evidence_blocked_items:
        actions.append("Attach reviewed ReleaseFoundry grading or audited semantic judge evidence before marking C5 mature.")
    if not actions:
        actions.append("Keep replay suite under regression monitoring.")
    return actions
