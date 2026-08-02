"""Public-safe release unblock checklist for C3/C4/C5 gates."""

from __future__ import annotations

from typing import Any

from .evidence_readiness import verify_evidence_readiness_artifact
from .release_gate import (
    build_release_gate_report,
    verify_release_gate_artifact,
)
from .result_persistence import stable_hash


SCHEMA_VERSION = "a2.release_unblock_checklist.v1"
DEFAULT_CHECKLIST_ID = "a2_release_unblock_checklist"


def build_release_unblock_checklist(
    release_gate_report: dict[str, Any],
    evidence_readiness_report: dict[str, Any],
    regression_replay_report: dict[str, Any],
    regression_promotion_queue: dict[str, Any],
    *,
    release_gate_sources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an owner/action checklist without reading private evidence."""
    release_gate_report = _dict(release_gate_report)
    evidence_readiness_report = _dict(evidence_readiness_report)
    regression_replay_report = _dict(regression_replay_report)
    regression_promotion_queue = _dict(regression_promotion_queue)
    release_gate_snapshot_hash = stable_hash(release_gate_report)
    release_gate_artifact_hash = _string_value(
        release_gate_report.get("artifact_hash")
    )
    try:
        _verify_release_gate_authority(
            release_gate_report,
            release_gate_sources,
        )
        release_gate_artifact_verified = True
    except (TypeError, ValueError):
        release_gate_artifact_verified = False
    release_gate_decision = release_gate_report.get("decision")
    if (
        not isinstance(release_gate_decision, str)
        or release_gate_decision not in {"block", "warn", "pass"}
    ):
        release_gate_decision = "block"
    release_gate_exit_code = _nonnegative_count(
        release_gate_report.get("exit_code")
    )
    release_gate_risk_score = _nonnegative_count(
        release_gate_report.get("risk_score")
    )
    gate_items = [
        _c3_item(evidence_readiness_report),
        _c4_item(evidence_readiness_report),
        _c5_item(regression_replay_report, regression_promotion_queue),
    ]
    blocked_items = [item for item in gate_items if item["blocks_release"]]
    overall_blocked = (
        not release_gate_artifact_verified
        or bool(blocked_items)
        or release_gate_decision == "block"
    )
    if not release_gate_artifact_verified:
        primary_action = (
            "Regenerate and verify the sealed source release gate from the "
            "current authoritative source artifacts before using this checklist."
        )
    elif blocked_items:
        primary_action = blocked_items[0]["required_actions"][0]["action"]
    elif overall_blocked:
        primary_action = "Resolve source release gate blockers before release."
    else:
        primary_action = "Release gates are ready."
    return {
        "schema_version": SCHEMA_VERSION,
        "checklist_id": DEFAULT_CHECKLIST_ID,
        "source_release_gate": str(release_gate_report.get("report_id", "")),
        "source_release_gate_artifact_hash": release_gate_artifact_hash,
        "source_release_gate_snapshot_hash": release_gate_snapshot_hash,
        "release_gate_artifact_verified": release_gate_artifact_verified,
        "release_gate_decision": release_gate_decision,
        "release_gate_exit_code": release_gate_exit_code,
        "release_gate_risk_score": release_gate_risk_score,
        "overall_status": "blocked" if overall_blocked else "ready",
        "blocked_gate_count": len(blocked_items),
        "gate_items": gate_items,
        "a3_consumption_summary": {
            "schema_version": "a2.release_unblock_checklist.a3_summary.v1",
            "blocked_gate_count": len(blocked_items),
            "release_gate_artifact_verified": release_gate_artifact_verified,
            "primary_action": primary_action,
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


def _verify_release_gate_authority(
    release_gate_report: dict[str, Any],
    release_gate_sources: dict[str, Any] | None,
) -> str:
    artifact_hash = verify_release_gate_artifact(release_gate_report)
    if release_gate_report.get("decision") == "block":
        return artifact_hash
    if not isinstance(release_gate_sources, dict):
        raise ValueError(
            "non-blocking release gate requires authoritative source artifacts"
        )

    required_sources = (
        "commercial_readiness_report",
        "evidence_readiness_report",
        "calibration_matrix",
        "batch_plan_report",
        "semantic_harness_report",
        "releasefoundry_case_map",
        "semantic_collection_packet",
        "regression_replay_report",
        "case_book_report",
        "scenario_selection_report",
        "a1_evidence_index",
        "judge_version_registry",
    )
    missing_sources = [
        source
        for source in required_sources
        if not isinstance(release_gate_sources.get(source), dict)
    ]
    if missing_sources:
        raise ValueError(
            "non-blocking release gate is missing authoritative sources: "
            + ", ".join(missing_sources)
        )

    verify_evidence_readiness_artifact(
        release_gate_sources["evidence_readiness_report"],
        calibration_matrix=release_gate_sources["calibration_matrix"],
        batch_plan_report=release_gate_sources["batch_plan_report"],
        semantic_harness_report=release_gate_sources[
            "semantic_harness_report"
        ],
        releasefoundry_case_map=release_gate_sources["releasefoundry_case_map"],
        semantic_collection_packet=release_gate_sources[
            "semantic_collection_packet"
        ],
    )
    verify_release_gate_artifact(
        release_gate_report,
        commercial_readiness_report=release_gate_sources[
            "commercial_readiness_report"
        ],
        evidence_readiness_report=release_gate_sources[
            "evidence_readiness_report"
        ],
        calibration_matrix=release_gate_sources["calibration_matrix"],
        regression_replay_report=release_gate_sources[
            "regression_replay_report"
        ],
        case_book_report=release_gate_sources["case_book_report"],
        scenario_selection_report=release_gate_sources[
            "scenario_selection_report"
        ],
        a1_evidence_index=release_gate_sources["a1_evidence_index"],
        modality_scope=release_gate_sources.get("modality_scope"),
        multimodal_qualification=release_gate_sources.get(
            "multimodal_qualification"
        ),
        multimodal_expected_bindings=release_gate_sources.get(
            "multimodal_expected_bindings"
        ),
        judge_version_registry=release_gate_sources[
            "judge_version_registry"
        ],
    )
    rebuilt = build_release_gate_report(
        release_gate_sources["commercial_readiness_report"],
        release_gate_sources["evidence_readiness_report"],
        release_gate_sources["calibration_matrix"],
        release_gate_sources["regression_replay_report"],
        release_gate_sources["scenario_selection_report"],
        release_gate_sources["a1_evidence_index"],
        modality_scope=release_gate_sources.get("modality_scope"),
        multimodal_qualification=release_gate_sources.get(
            "multimodal_qualification"
        ),
        multimodal_expected_bindings=release_gate_sources.get(
            "multimodal_expected_bindings"
        ),
        judge_version_registry=release_gate_sources[
            "judge_version_registry"
        ],
        case_book_report=release_gate_sources["case_book_report"],
    )
    if rebuilt["artifact_hash"] != artifact_hash:
        raise ValueError(
            "release gate does not match the deterministic authoritative-source "
            "rebuild"
        )
    return artifact_hash


def _c3_item(evidence_readiness_report: dict[str, Any]) -> dict[str, Any]:
    evidence_readiness_report = _dict(evidence_readiness_report)
    merge_gate = _dict(evidence_readiness_report.get("releasefoundry_public_merge_gate"))
    preflight = _dict(evidence_readiness_report.get("releasefoundry_grading_preflight"))
    missing_count, missing_count_valid = _strict_nonnegative_count(
        merge_gate.get(
            "missing_reviewed_observation_count",
            preflight.get("current_missing", 0),
        )
    )
    safe = merge_gate.get("safe_to_mark_c3_met") is True
    item = _gate_item(
        gate="C3",
        title="Reviewed ReleaseFoundry server-side grading",
        status=str(merge_gate.get("status", "not_merged")),
        blocks_release=not safe or not missing_count_valid,
        owner_role="A2 evidence reviewer",
        missing_count=max(missing_count, int(not missing_count_valid)),
        required_evidence_source="reviewed_releasefoundry_grading",
        action=str(merge_gate.get("blocking_reason") or "Import reviewed ReleaseFoundry grading observations."),
        commands=_string_list(merge_gate.get("required_commands") or preflight.get("commands")),
        evidence_refs=[
            "fixtures/a2/calibration/a2_g3_calibration_observations.json",
            "fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json",
            "fixtures/a2/calibration/a2_releasefoundry_grading_collection_packet.json",
            "fixtures/a2/results/a2_evidence_readiness_report.json",
        ],
        private_input_ref=_string_value(
            preflight.get(
                "private_input_ref",
                merge_gate.get("reviewed_private_import_ref", ""),
            )
        ),
    )
    if not missing_count_valid:
        item["invalid_count_fields"] = ["missing_reviewed_observation_count"]
    return item


def _c4_item(evidence_readiness_report: dict[str, Any]) -> dict[str, Any]:
    evidence_readiness_report = _dict(evidence_readiness_report)
    merge_gate = _dict(evidence_readiness_report.get("semantic_live_merge_gate"))
    preflight = _dict(evidence_readiness_report.get("semantic_judge_preflight"))
    missing_count, missing_count_valid = _strict_nonnegative_count(
        merge_gate.get("missing_audited_observation_count", preflight.get("missing_reviewed_live_observation_count", 0))
    )
    safe = merge_gate.get("safe_to_mark_c4_met") is True
    item = _gate_item(
        gate="C4",
        title="Audited live semantic judge evidence",
        status=str(merge_gate.get("status", "offline_reference_only")),
        blocks_release=not safe or not missing_count_valid,
        owner_role="A2 semantic judge reviewer",
        missing_count=max(missing_count, int(not missing_count_valid)),
        required_evidence_source="audited_semantic_judge",
        action=str(merge_gate.get("blocking_reason") or "Import audited semantic judge observations."),
        commands=_string_list(merge_gate.get("required_commands") or preflight.get("commands")),
        evidence_refs=[
            "fixtures/a2/calibration/a2_g3_calibration_observations.json",
            "fixtures/a2/calibration/a2_semantic_judge_collection_packet.json",
            "fixtures/a2/results/a2_semantic_harness_report.json",
            "fixtures/a2/results/a2_evidence_readiness_report.json",
        ],
        private_input_ref=_string_value(
            preflight.get(
                "private_input_ref",
                merge_gate.get("reviewed_private_import_ref", ""),
            )
        ),
    )
    if not missing_count_valid:
        item["invalid_count_fields"] = ["missing_audited_observation_count"]
    return item


def _c5_item(
    regression_replay_report: dict[str, Any],
    regression_promotion_queue: dict[str, Any],
) -> dict[str, Any]:
    regression_replay_report = _dict(regression_replay_report)
    regression_promotion_queue = _dict(regression_promotion_queue)
    summary = _dict(regression_replay_report.get("release_gate_summary"))
    missing_count, missing_count_valid = _strict_nonnegative_count(
        summary.get(
            "missing_replay_case_count",
            regression_replay_report.get("missing_replay_case_count", 0),
        )
    )
    missing_evidence, missing_evidence_valid = _strict_nonnegative_count(
        summary.get("missing_reviewed_evidence_count", 0)
    )
    invalid_count_fields = []
    if not missing_count_valid:
        invalid_count_fields.append("missing_replay_case_count")
    if not missing_evidence_valid:
        invalid_count_fields.append("missing_reviewed_evidence_count")
    action = str(
        _dict(regression_promotion_queue.get("release_gate_summary")).get("required_action")
        or summary.get("required_action")
        or "Promote reviewed incident/disagreement cases into C5 replay."
    )
    item = _gate_item(
        gate="C5",
        title="Mature regression replay",
        status=str(summary.get("release_gate_status", "blocked")),
        blocks_release=(
            summary.get("blocks_release") is not False
            or missing_count > 0
            or missing_evidence > 0
            or bool(invalid_count_fields)
        ),
        owner_role="A2 case-book owner",
        missing_count=max(missing_count, missing_evidence, len(invalid_count_fields)),
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
    if invalid_count_fields:
        item["invalid_count_fields"] = invalid_count_fields
    return item


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
    return [item for item in value if isinstance(item, str) and item.strip()]


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _nonnegative_count(value: Any) -> int:
    count, valid = _strict_nonnegative_count(value)
    return count if valid else 0


def _strict_nonnegative_count(value: Any) -> tuple[int, bool]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0, False
    return value, True
