"""Public-safe release unblock checklist for C3/C4/C5 gates."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "a2.release_unblock_checklist.v1"
DEFAULT_CHECKLIST_ID = "a2_release_unblock_checklist"


def build_release_unblock_checklist(
    release_gate_report: dict[str, Any],
    evidence_readiness_report: dict[str, Any],
    regression_replay_report: dict[str, Any],
    regression_promotion_queue: dict[str, Any],
) -> dict[str, Any]:
    """Build an owner/action checklist without reading private evidence."""
    gate_items = [
        _c3_item(evidence_readiness_report),
        _c4_item(evidence_readiness_report),
        _c5_item(regression_replay_report, regression_promotion_queue),
    ]
    blocked_items = [item for item in gate_items if item["blocks_release"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "checklist_id": DEFAULT_CHECKLIST_ID,
        "source_release_gate": str(release_gate_report.get("report_id", "")),
        "release_gate_decision": str(release_gate_report.get("decision", "")),
        "release_gate_exit_code": int(release_gate_report.get("exit_code", 0)),
        "release_gate_risk_score": int(release_gate_report.get("risk_score", 0)),
        "overall_status": "blocked" if blocked_items else "ready",
        "blocked_gate_count": len(blocked_items),
        "gate_items": gate_items,
        "a3_consumption_summary": {
            "schema_version": "a2.release_unblock_checklist.a3_summary.v1",
            "blocked_gate_count": len(blocked_items),
            "primary_action": blocked_items[0]["required_actions"][0]["action"] if blocked_items else "Release gates are ready.",
            "dashboard_sections": ["C3 official grading", "C4 semantic judge", "C5 regression replay"],
            "evidence_refs": ["fixtures/a2/results/a2_release_unblock_checklist.json"],
        },
        "review_workflow": {
            "required_reviewers": ["A2 evidence reviewer", "A2 case-book owner"],
            "private_evidence_boundary": "Private refs may be named as evidence anchors, but raw payloads stay under docs/evidence/private_refs/ and are not read.",
            "merge_rule": "Only reviewed public summaries may enter fixtures/a2/calibration or fixtures/a2/results.",
        },
        "evidence_refs": [
            "fixtures/a2/results/a2_release_gate_report.json",
            "fixtures/a2/results/a2_evidence_readiness_report.json",
            "fixtures/a2/results/a2_regression_replay_report.json",
            "fixtures/a2/results/a2_regression_promotion_queue.json",
        ],
        "metadata": {
            "deterministic": True,
            "public_safe": True,
            "does_not_execute_live_calls": True,
            "does_not_read_private_evidence": True,
            "purpose": "Give A1/A3 and release reviewers a machine-readable path to unblock C3/C4/C5 without exposing raw evidence.",
        },
    }


def _c3_item(evidence_readiness_report: dict[str, Any]) -> dict[str, Any]:
    merge_gate = _dict(evidence_readiness_report.get("ashr_public_merge_gate"))
    preflight = _dict(evidence_readiness_report.get("ashr_grading_preflight"))
    missing_count = int(merge_gate.get("missing_reviewed_observation_count", preflight.get("current_missing", 0)))
    safe = bool(merge_gate.get("safe_to_mark_c3_met"))
    return _gate_item(
        gate="C3",
        title="Reviewed Ashr server-side grading",
        status=str(merge_gate.get("status", "not_merged")),
        blocks_release=not safe,
        owner_role="A2 evidence reviewer",
        missing_count=missing_count,
        required_evidence_source="reviewed_ashr_grading",
        action=str(merge_gate.get("blocking_reason") or "Import reviewed Ashr grading observations."),
        commands=_string_list(merge_gate.get("required_commands") or preflight.get("commands")),
        evidence_refs=[
            "fixtures/a2/calibration/a2_g3_calibration_observations.json",
            "fixtures/a2/calibration/ashr_grading_batch_case_map.json",
            "fixtures/a2/calibration/a2_ashr_grading_collection_packet.json",
            "fixtures/a2/results/a2_evidence_readiness_report.json",
        ],
        private_input_ref=str(preflight.get("private_input_ref", merge_gate.get("reviewed_private_import_ref", ""))),
    )


def _c4_item(evidence_readiness_report: dict[str, Any]) -> dict[str, Any]:
    merge_gate = _dict(evidence_readiness_report.get("semantic_live_merge_gate"))
    preflight = _dict(evidence_readiness_report.get("semantic_judge_preflight"))
    missing_count = int(
        merge_gate.get("missing_audited_observation_count", preflight.get("missing_reviewed_live_observation_count", 0))
    )
    safe = bool(merge_gate.get("safe_to_mark_c4_met"))
    return _gate_item(
        gate="C4",
        title="Audited live semantic judge evidence",
        status=str(merge_gate.get("status", "offline_reference_only")),
        blocks_release=not safe,
        owner_role="A2 semantic judge reviewer",
        missing_count=missing_count,
        required_evidence_source="audited_semantic_judge",
        action=str(merge_gate.get("blocking_reason") or "Import audited semantic judge observations."),
        commands=_string_list(merge_gate.get("required_commands") or preflight.get("commands")),
        evidence_refs=[
            "fixtures/a2/calibration/a2_g3_calibration_observations.json",
            "fixtures/a2/calibration/a2_semantic_judge_collection_packet.json",
            "fixtures/a2/results/a2_semantic_harness_report.json",
            "fixtures/a2/results/a2_evidence_readiness_report.json",
        ],
        private_input_ref=str(preflight.get("private_input_ref", merge_gate.get("reviewed_private_import_ref", ""))),
    )


def _c5_item(
    regression_replay_report: dict[str, Any],
    regression_promotion_queue: dict[str, Any],
) -> dict[str, Any]:
    summary = _dict(regression_replay_report.get("release_gate_summary"))
    missing_count = int(summary.get("missing_replay_case_count", regression_replay_report.get("missing_replay_case_count", 0)))
    missing_evidence = int(summary.get("missing_reviewed_evidence_count", 0))
    action = str(
        _dict(regression_promotion_queue.get("release_gate_summary")).get("required_action")
        or summary.get("required_action")
        or "Promote reviewed incident/disagreement cases into C5 replay."
    )
    return _gate_item(
        gate="C5",
        title="Mature regression replay",
        status=str(summary.get("release_gate_status", "blocked")),
        blocks_release=bool(summary.get("blocks_release", missing_count > 0 or missing_evidence > 0)),
        owner_role="A2 case-book owner",
        missing_count=max(missing_count, missing_evidence),
        required_evidence_source="reviewed_regression_replay",
        action=action,
        commands=[
            "Review fixtures/a2/results/a2_regression_promotion_queue.json.",
            "Promote accepted case-book candidates, then run python scripts/a2_regenerate_fixtures.py --write.",
        ],
        evidence_refs=[
            "fixtures/a2/results/a2_case_book.json",
            "fixtures/a2/results/a2_regression_replay_report.json",
            "fixtures/a2/results/a2_regression_promotion_queue.json",
            "fixtures/a2/results/a2_incident_regression_candidates.json",
        ],
        private_input_ref="",
    )


def _gate_item(
    *,
    gate: str,
    title: str,
    status: str,
    blocks_release: bool,
    owner_role: str,
    missing_count: int,
    required_evidence_source: str,
    action: str,
    commands: list[str],
    evidence_refs: list[str],
    private_input_ref: str,
) -> dict[str, Any]:
    action_id = f"{gate.lower()}_{required_evidence_source}"
    return {
        "gate": gate,
        "title": title,
        "status": status,
        "blocks_release": blocks_release,
        "owner_role": owner_role,
        "missing_count": max(0, missing_count),
        "required_actions": [
            {
                "action_id": action_id,
                "action": action,
                "required_evidence_source": required_evidence_source,
                "missing_count": max(0, missing_count),
                "private_evidence_required": bool(private_input_ref),
                "private_input_ref": private_input_ref,
                "commands": commands,
                "evidence_refs": evidence_refs,
            }
        ],
        "evidence_refs": evidence_refs,
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
