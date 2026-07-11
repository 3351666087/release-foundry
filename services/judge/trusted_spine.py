"""Trusted evidence and decision provenance contracts for A2."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .result_persistence import redact_payload, stable_hash


EVIDENCE_SNAPSHOT_SCHEMA_VERSION = "a2.evidence_snapshot.v1"
DECISION_RECORD_SCHEMA_VERSION = "a2.decision_record.v1"
DECISION_LEDGER_SCHEMA_VERSION = "a2.decision_ledger.v1"
TRUSTED_SPINE_HANDOFF_SCHEMA_VERSION = "a2.trusted_spine_handoff.v1"
GENESIS_HASH = "sha256:" + ("0" * 64)
VALID_COMPLETENESS = {"complete", "partial", "evidence_missing", "invalid"}
VALID_DECISIONS = {"allow", "block", "review"}


def build_evidence_snapshot(
    run_payload: dict[str, Any],
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    case_id: str,
    scenario_id: str,
    created_at: str,
    required_modalities: list[str] | None = None,
    source_schema_version: str = "unknown",
) -> dict[str, Any]:
    """Freeze public-safe A1 evidence metadata without storing raw evidence."""
    normalized = redact_payload(deepcopy(run_payload))
    tool_calls = _tool_calls(normalized)
    artifacts = _artifact_descriptors(tool_calls)
    observed_modalities = sorted(
        {
            str(item["modality"])
            for item in artifacts
            if item.get("modality")
        }
        | ({"text"} if _final_text(normalized) else set())
    )
    required = sorted(set(required_modalities or ["text"]))
    missing = sorted(set(required) - set(observed_modalities))
    completeness = "evidence_missing" if missing else "complete"
    snapshot_core = {
        "schema_version": EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run_id,
        "case_id": case_id,
        "scenario_id": scenario_id,
        "created_at": created_at,
        "source_schema_version": source_schema_version,
        "source_payload_hash": stable_hash(normalized),
        "required_modalities": required,
        "observed_modalities": observed_modalities,
        "completeness": completeness,
        "missing_modalities": missing,
        "tool_call_count": len(tool_calls),
        "tool_sequence": [str(call.get("tool") or call.get("name") or "") for call in tool_calls],
        "artifacts": artifacts,
        "extractor_provenance": [
            {
                "extractor_id": "a2.public_safe_run_normalizer",
                "extractor_version": "1.0.0",
                "input_hash": stable_hash(normalized),
                "status": "complete",
            }
        ],
        "security": {
            "tenant_scoped": bool(tenant_id),
            "raw_evidence_included": False,
            "private_evidence_included": False,
            "secrets_included": False,
            "artifact_content_included": False,
        },
    }
    snapshot_core["snapshot_id"] = stable_hash(snapshot_core)
    snapshot_core["snapshot_hash"] = stable_hash(snapshot_core)
    return snapshot_core


def build_decision_record(
    evidence_snapshot: dict[str, Any],
    *,
    decision: str,
    release_gate_report: dict[str, Any],
    judge_results: list[dict[str, Any]],
    policy_version: str,
    policy_hash: str,
    model_versions: list[str],
    created_at: str,
    previous_record_hash: str = GENESIS_HASH,
    review_required: bool | None = None,
) -> dict[str, Any]:
    """Build one immutable decision record bound to evidence and versions."""
    if decision not in VALID_DECISIONS:
        raise ValueError(f"unsupported decision: {decision}")
    completeness = str(evidence_snapshot.get("completeness") or "invalid")
    if completeness not in VALID_COMPLETENESS:
        raise ValueError(f"unsupported evidence completeness: {completeness}")
    if decision == "allow" and completeness != "complete":
        raise ValueError("incomplete evidence cannot produce an allow decision")

    safe_gate = redact_payload(deepcopy(release_gate_report))
    safe_judges = [redact_payload(deepcopy(item)) for item in judge_results]
    abstain_count = sum(1 for item in safe_judges if str(item.get("outcome")) == "abstain")
    failed_judges = [
        str(item.get("judge_id") or item.get("judge_mode") or "unknown")
        for item in safe_judges
        if item.get("passed") is False or str(item.get("outcome")) == "fail"
    ]
    hard_blockers = _hard_blockers(safe_gate)
    record_core = {
        "schema_version": DECISION_RECORD_SCHEMA_VERSION,
        "tenant_id": str(evidence_snapshot.get("tenant_id") or ""),
        "project_id": str(evidence_snapshot.get("project_id") or ""),
        "run_id": str(evidence_snapshot.get("run_id") or ""),
        "case_id": str(evidence_snapshot.get("case_id") or ""),
        "scenario_id": str(evidence_snapshot.get("scenario_id") or ""),
        "created_at": created_at,
        "evidence_snapshot_id": str(evidence_snapshot.get("snapshot_id") or ""),
        "evidence_snapshot_hash": str(evidence_snapshot.get("snapshot_hash") or ""),
        "evidence_completeness": completeness,
        "decision": decision,
        "review_required": decision == "review" if review_required is None else bool(review_required),
        "policy_version": policy_version,
        "policy_hash": policy_hash,
        "model_versions": sorted(set(model_versions)),
        "judge_versions": sorted(
            {
                f"{item.get('judge_id') or item.get('judge_mode') or 'unknown'}:"
                f"{item.get('judge_version') or 'unknown'}"
                for item in safe_judges
            }
        ),
        "judge_result_hashes": [stable_hash(item) for item in safe_judges],
        "judge_summary": {
            "judge_count": len(safe_judges),
            "failed_judges": failed_judges,
            "abstain_count": abstain_count,
            "disagreement": bool(failed_judges) and len(failed_judges) < len(safe_judges),
        },
        "release_gate_hash": stable_hash(safe_gate),
        "hard_blockers": hard_blockers,
        "previous_record_hash": previous_record_hash,
        "public_safe": True,
    }
    if decision == "allow" and (hard_blockers or abstain_count):
        raise ValueError("hard blockers or abstentions cannot produce an allow decision")
    record_core["record_id"] = stable_hash(record_core)
    record_core["record_hash"] = stable_hash(record_core)
    return record_core


def build_decision_ledger(
    records: list[dict[str, Any]],
    *,
    ledger_id: str,
    tenant_id: str,
    project_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Build and validate a tenant-scoped append-only decision chain."""
    previous_hash = GENESIS_HASH
    normalized_records: list[dict[str, Any]] = []
    for position, item in enumerate(records):
        record = deepcopy(item)
        if record.get("tenant_id") != tenant_id or record.get("project_id") != project_id:
            raise ValueError("decision record tenant/project scope mismatch")
        if record.get("previous_record_hash") != previous_hash:
            raise ValueError(f"decision ledger chain mismatch at position {position}")
        if record.get("record_hash") != _record_hash(record):
            raise ValueError(f"decision record hash mismatch at position {position}")
        normalized_records.append(record)
        previous_hash = str(record["record_hash"])

    ledger = {
        "schema_version": DECISION_LEDGER_SCHEMA_VERSION,
        "ledger_id": ledger_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "created_at": created_at,
        "record_count": len(normalized_records),
        "genesis_hash": GENESIS_HASH,
        "head_hash": previous_hash,
        "records": normalized_records,
        "metadata": {
            "append_only": True,
            "public_safe": True,
            "chain_verified": True,
            "human_overrides_are_linked_records": True,
        },
    }
    ledger["ledger_hash"] = stable_hash(ledger)
    return ledger


def build_trusted_spine_handoff(
    run_fixture: dict[str, Any],
    grade_result: dict[str, Any],
    release_gate_report: dict[str, Any],
    *,
    created_at: str = "2026-07-11T00:00:00Z",
) -> dict[str, Any]:
    """Build the deterministic public A1 -> A2 -> A3 trusted-spine fixture."""
    run_id = "a2_trusted_spine_demo"
    case_id = str(run_fixture.get("case_id") or "unknown-case")
    scenario_id = str(run_fixture.get("scenario_id") or "")
    snapshot = build_evidence_snapshot(
        run_fixture.get("run", run_fixture),
        tenant_id="org_local_demo",
        project_id="a2_g3_calibration",
        run_id=run_id,
        case_id=case_id,
        scenario_id=scenario_id,
        created_at=created_at,
        required_modalities=["text", "image"],
        source_schema_version="a1.run_fixture.v1",
    )
    judge_results = [
        {
            "judge_id": result.get("judge_mode"),
            "judge_version": result.get("judge_version"),
            "passed": result.get("passed"),
            "score": result.get("score"),
        }
        for result in grade_result.get("judge_results", [])
        if isinstance(result, dict)
    ]
    policy_hash = stable_hash(
        {
            "policy_version": "a2.release_policy.v1",
            "release_gate_schema": release_gate_report.get("schema_version"),
        }
    )
    decision_record = build_decision_record(
        snapshot,
        decision="block",
        release_gate_report=release_gate_report,
        judge_results=judge_results,
        policy_version="a2.release_policy.v1",
        policy_hash=policy_hash,
        model_versions=["deterministic:a2-local-judges"],
        created_at=created_at,
    )
    ledger = build_decision_ledger(
        [decision_record],
        ledger_id="a2_trusted_spine_demo_ledger",
        tenant_id="org_local_demo",
        project_id="a2_g3_calibration",
        created_at=created_at,
    )
    return {
        "schema_version": TRUSTED_SPINE_HANDOFF_SCHEMA_VERSION,
        "evidence_snapshot": snapshot,
        "decision_ledger": ledger,
        "a3_consumption": {
            "release_ready": False,
            "decision_record_required": True,
            "may_recompute_grade": False,
            "review_queue_status": "blocked",
            "display_decision": decision_record["decision"],
            "display_provenance_hash": decision_record["record_hash"],
        },
        "metadata": {
            "public_safe": True,
            "raw_evidence_included": False,
            "secrets_included": False,
            "requires_network": False,
        },
    }


def _record_hash(record: dict[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key not in {"record_hash"}}
    return stable_hash(payload)


def _tool_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidate = payload.get("tool_calls")
    if not isinstance(candidate, list):
        candidate = payload.get("agent_output", {}).get("tool_calls", []) if isinstance(payload.get("agent_output"), dict) else []
    return [item for item in candidate if isinstance(item, dict)]


def _final_text(payload: dict[str, Any]) -> str:
    return str(payload.get("final_response") or payload.get("text") or "")


def _artifact_descriptors(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts = []
    for index, call in enumerate(tool_calls):
        tool = str(call.get("tool") or call.get("name") or "")
        args = call.get("args") if isinstance(call.get("args"), dict) else call.get("arguments", {})
        output = call.get("output") if isinstance(call.get("output"), dict) else {}
        modality = str(output.get("modality") or _modality_from_tool(tool, args))
        if not modality:
            continue
        safe_ref = str(args.get("path") or args.get("asset_id") or output.get("media_uri") or "")
        artifacts.append(
            {
                "artifact_id": f"artifact-{index + 1}",
                "modality": modality,
                "producer_tool": tool,
                "reference_hash": stable_hash(safe_ref),
                "content_hash": stable_hash(output),
                "content_included": False,
                "collection_status": "complete",
            }
        )
    return artifacts


def _modality_from_tool(tool: str, args: dict[str, Any]) -> str:
    lowered = tool.lower()
    for modality in ("image", "audio", "video", "file"):
        if modality in lowered:
            return modality
    path = str(args.get("path") or "").lower()
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return "image"
    if path.endswith((".wav", ".mp3", ".m4a", ".flac")):
        return "audio"
    if path.endswith((".mp4", ".mov", ".webm", ".mkv")):
        return "video"
    if path:
        return "file"
    return ""


def _hard_blockers(release_gate_report: dict[str, Any]) -> list[str]:
    blockers = []
    decision = str(release_gate_report.get("decision") or "")
    if decision == "block":
        blockers.append("release_gate_blocked")
    for item in release_gate_report.get("blocking_reasons", []):
        if isinstance(item, str):
            blockers.append(item)
        elif isinstance(item, dict):
            blockers.append(str(item.get("reason_id") or item.get("rule_id") or "policy_blocker"))
    return sorted(set(blockers))
