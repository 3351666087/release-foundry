"""Public-safe C5 regression promotion queue."""

from __future__ import annotations

from typing import Any


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
    case_book_ids = {
        str(case.get("case_id", ""))
        for case in case_book_report.get("regression_cases", [])
        if isinstance(case, dict)
    }
    replay_case_ids = {
        str(case.get("case_id", ""))
        for case in regression_replay_report.get("cases", [])
        if isinstance(case, dict)
    }
    promotion_items = [
        _promotion_item(candidate, case_book_ids, replay_case_ids)
        for candidate in incident_candidates_report.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    promotion_items = [item for item in promotion_items if item]
    review_ready_items = [item for item in promotion_items if item["queue_status"] == "ready_for_owner_review"]
    evidence_blocked_items = [
        item for item in promotion_items if "needs_reviewed_releasefoundry_or_audited_semantic_evidence" in item["promotion_blockers"]
    ]
    replay_maturity = regression_replay_report.get("maturity_gate", {})
    release_gate_summary = regression_replay_report.get("release_gate_summary", {})
    current_replay_count = int(replay_maturity.get("current_replay_case_count", regression_replay_report.get("replay_case_count", 0)))
    target_count = int(replay_maturity.get("target_replay_case_count", TARGET_MATURE_REPLAY_CASE_COUNT))
    missing_replay_count = max(0, target_count - current_replay_count)
    return {
        "schema_version": SCHEMA_VERSION,
        "queue_id": DEFAULT_QUEUE_ID,
        "source_case_book": str(case_book_report.get("case_book_id", "")),
        "source_incident_candidates": str(incident_candidates_report.get("report_id", "")),
        "source_regression_replay": str(regression_replay_report.get("replay_id", "")),
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


def _promotion_item(
    candidate: dict[str, Any],
    case_book_ids: set[str],
    replay_case_ids: set[str],
) -> dict[str, Any]:
    case_id = str(candidate.get("case_id", ""))
    blockers = [str(blocker) for blocker in candidate.get("promotion_blockers", []) if str(blocker).strip()]
    in_case_book = case_id in case_book_ids
    in_replay = case_id in replay_case_ids
    public_safe = bool(candidate.get("public_safe"))
    ready_for_case_book_review = bool(candidate.get("ready_for_case_book_review"))
    queue_status = _item_status(
        in_replay=in_replay,
        in_case_book=in_case_book,
        public_safe=public_safe,
        ready_for_case_book_review=ready_for_case_book_review,
    )
    return {
        "promotion_id": f"promotion-{candidate.get('regression_id', case_id)}",
        "queue_status": queue_status,
        "case_id": case_id,
        "scenario_id": str(candidate.get("scenario_id", "")),
        "fixture_ref": str(candidate.get("fixture_ref", "")),
        "source": str(candidate.get("source", "")),
        "incident_id": str(candidate.get("incident_id", "")),
        "severity": str(candidate.get("severity", "")),
        "primary_failure_class": str(candidate.get("expected", {}).get("primary_failure_class", "")),
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
        "evidence_refs": [str(ref) for ref in candidate.get("evidence_refs", []) if str(ref).strip()],
    }


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
    return {
        "schema_version": "a2.regression_promotion.release_gate_summary.v1",
        "gate": "C5",
        "blocks_release": bool(replay_release_gate.get("blocks_release", missing_replay_count > 0)),
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
