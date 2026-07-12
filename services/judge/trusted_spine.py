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
    organization_id: str,
    tenant_id: str,
    workspace_id: str,
    project_id: str,
    environment_id: str,
    run_id: str,
    case_id: str,
    scenario_id: str,
    created_at: str,
    required_modalities: list[str] | None = None,
    source_schema_version: str = "unknown",
    artifact_pipeline_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Freeze public-safe A1 evidence metadata without storing raw evidence."""
    normalized = redact_payload(deepcopy(run_payload))
    scope = {
        "organization_id": organization_id,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "environment_id": environment_id,
    }
    if not all(scope.values()):
        raise ValueError("complete five-field tenant scope is required")

    source_run_id = str(normalized.get("run_id") or run_id)
    selected_case, validation_errors = _select_case(normalized, case_id)
    source = selected_case or normalized
    tool_calls = _tool_calls(source)
    artifacts = _artifact_descriptors(tool_calls)
    pipeline_artifacts, pipeline_extractors, pipeline_errors = _artifact_pipeline_evidence(
        artifact_pipeline_records or [],
        scope=scope,
    )
    artifacts.extend(pipeline_artifacts)
    validation_errors.extend(pipeline_errors)
    observed_modalities = sorted(
        {
            str(item["modality"])
            for item in artifacts
            if item.get("modality")
        }
        | ({"text"} if _final_text(source) else set())
    )
    required = sorted(set(required_modalities or ["text"]))
    missing = sorted(set(required) - set(observed_modalities))
    trace_completeness = normalized.get("trace_completeness")
    if trace_completeness is not None and float(trace_completeness) < 1:
        validation_errors.append("trace_incomplete")
    if source_run_id != run_id:
        validation_errors.append("run_id_mismatch")
    completeness = "invalid" if validation_errors else ("evidence_missing" if missing else "complete")
    snapshot_core = {
        "schema_version": EVIDENCE_SNAPSHOT_SCHEMA_VERSION,
        **scope,
        "run_id": run_id,
        "case_id": case_id,
        "scenario_id": scenario_id,
        "created_at": created_at,
        "source_schema_version": source_schema_version,
        "source_payload_hash": stable_hash(normalized),
        "required_modalities": required,
        "observed_modalities": observed_modalities,
        "completeness": completeness,
        "validation_errors": sorted(set(validation_errors)),
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
        ]
        + pipeline_extractors,
        "security": {
            "tenant_scoped": True,
            "scope_complete": True,
            "raw_evidence_included": False,
            "private_evidence_included": False,
            "secrets_included": False,
            "artifact_content_included": False,
        },
    }
    snapshot_core["snapshot_id"] = stable_hash(snapshot_core)
    snapshot_core["snapshot_hash"] = stable_hash(snapshot_core)
    return snapshot_core


def _artifact_pipeline_evidence(
    records: list[dict[str, Any]],
    *,
    scope: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    artifacts: list[dict[str, Any]] = []
    extractors: list[dict[str, Any]] = []
    errors: list[str] = []
    for position, record in enumerate(records):
        prefix = f"artifact_pipeline_{position}"
        if record.get("schema_version") != "a2.multimodal_artifact_pipeline.v1":
            errors.append(f"{prefix}_schema_invalid")
            continue
        if record.get("tenant_scope") != scope:
            errors.append(f"{prefix}_scope_mismatch")
            continue
        if record.get("pipeline_record_hash") != _pipeline_record_hash(record):
            errors.append(f"{prefix}_integrity_invalid")
            continue
        resolution = record.get("artifact_reference_resolution")
        if resolution is not None:
            if not isinstance(resolution, dict):
                errors.append(f"{prefix}_reference_resolution_contract_invalid")
                continue
            resolution_core = {
                key: value for key, value in resolution.items() if key != "resolution_hash"
            }
            if (
                resolution.get("schema_version")
                != "a2.artifact_reference_resolution.v1"
                or resolution.get("tenant_scope") != scope
                or resolution.get("status") != "verified"
                or resolution.get("resolution_hash") != stable_hash(resolution_core)
            ):
                errors.append(f"{prefix}_reference_resolution_integrity_invalid")
                continue
        manifest = record.get("manifest")
        extraction = record.get("extraction")
        if not isinstance(manifest, dict) or not isinstance(extraction, dict):
            errors.append(f"{prefix}_contract_invalid")
            continue
        blockers = record.get("blockers")
        if not isinstance(blockers, list):
            blockers = ["pipeline_blockers_invalid"]
        eligible = record.get("evaluation_eligible") is True and not blockers
        artifacts.append(
            {
                "artifact_id": str(manifest.get("artifact_id") or ""),
                "modality": str(manifest.get("modality") or "file"),
                "producer_tool": "a2.artifact_pipeline",
                "reference_hash": str(manifest.get("manifest_id") or ""),
                "reference_resolution_hash": str(
                    (record.get("artifact_reference_resolution") or {}).get("resolution_hash")
                    or ""
                ),
                "content_hash": str(manifest.get("content_hash") or ""),
                "content_included": False,
                "collection_status": "complete" if eligible else "invalid",
            }
        )
        extractors.append(
            {
                "extractor_id": str(extraction.get("extractor_id") or ""),
                "extractor_version": str(extraction.get("extractor_version") or ""),
                "input_hash": str(extraction.get("input_hash") or ""),
                "status": str(extraction.get("status") or "invalid"),
            }
        )
        if not eligible:
            errors.extend(f"{prefix}_{blocker}" for blocker in blockers)
            if not blockers:
                errors.append(f"{prefix}_not_evaluation_eligible")
    return artifacts, extractors, errors


def _pipeline_record_hash(record: dict[str, Any]) -> str:
    core = {key: value for key, value in record.items() if key != "pipeline_record_hash"}
    return stable_hash(core)


def build_decision_record(
    evidence_snapshot: dict[str, Any],
    *,
    decision: str,
    release_gate_report: dict[str, Any],
    judge_results: list[dict[str, Any]],
    provider_provenance: list[dict[str, Any]] | None = None,
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
    safe_provider_provenance = [
        _validate_provider_provenance(evidence_snapshot, redact_payload(deepcopy(item)))
        for item in (provider_provenance or [])
    ]
    abstain_count = sum(1 for item in safe_judges if str(item.get("outcome")) == "abstain")
    failed_judges = [
        str(item.get("judge_id") or item.get("judge_mode") or "unknown")
        for item in safe_judges
        if item.get("passed") is False or str(item.get("outcome")) == "fail"
    ]
    hard_blockers = _hard_blockers(safe_gate)
    record_core = {
        "schema_version": DECISION_RECORD_SCHEMA_VERSION,
        "organization_id": str(evidence_snapshot.get("organization_id") or ""),
        "tenant_id": str(evidence_snapshot.get("tenant_id") or ""),
        "workspace_id": str(evidence_snapshot.get("workspace_id") or ""),
        "project_id": str(evidence_snapshot.get("project_id") or ""),
        "environment_id": str(evidence_snapshot.get("environment_id") or ""),
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
        "provider_provenance_hashes": [stable_hash(item) for item in safe_provider_provenance],
        "provider_summary": {
            "call_count": len(safe_provider_provenance),
            "providers": sorted(
                {
                    str(item.get("provider_id") or "unknown")
                    for item in safe_provider_provenance
                }
            ),
            "models": sorted(
                {
                    str(item.get("model_id") or "unknown")
                    for item in safe_provider_provenance
                }
            ),
            "blocked_call_count": sum(
                1
                for item in safe_provider_provenance
                if item.get("status") != "ready" or item.get("evaluation_eligible") is not True
            ),
        },
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
    if decision == "allow" and record_core["provider_summary"]["blocked_call_count"]:
        raise ValueError("blocked provider provenance cannot produce an allow decision")
    record_core["record_id"] = stable_hash(record_core)
    record_core["record_hash"] = stable_hash(record_core)
    return record_core


def _validate_provider_provenance(
    evidence_snapshot: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    expected_scope = {
        field: str(evidence_snapshot.get(field) or "")
        for field in ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
    }
    actual_scope = provenance.get("tenant_scope")
    if not isinstance(actual_scope, dict) or {
        field: str(actual_scope.get(field) or "")
        for field in expected_scope
    } != expected_scope:
        raise ValueError("provider provenance five-field scope mismatch")
    if provenance.get("snapshot_id") != evidence_snapshot.get("snapshot_id"):
        raise ValueError("provider provenance snapshot id mismatch")
    if provenance.get("snapshot_hash") != evidence_snapshot.get("snapshot_hash"):
        raise ValueError("provider provenance snapshot hash mismatch")
    if provenance.get("release_authority") is not False:
        raise ValueError("provider provenance cannot claim release authority")
    required = ("logical_call_id", "provider_id", "model_id")
    if any(not provenance.get(field) for field in required):
        raise ValueError("provider provenance identity is incomplete")
    return provenance


def build_decision_ledger(
    records: list[dict[str, Any]],
    *,
    ledger_id: str,
    organization_id: str,
    tenant_id: str,
    workspace_id: str,
    project_id: str,
    environment_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Build and validate a tenant-scoped append-only decision chain."""
    previous_hash = GENESIS_HASH
    normalized_records: list[dict[str, Any]] = []
    for position, item in enumerate(records):
        record = deepcopy(item)
        expected_scope = (organization_id, tenant_id, workspace_id, project_id, environment_id)
        record_scope = tuple(
            record.get(field)
            for field in ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
        )
        if record_scope != expected_scope:
            raise ValueError("decision record five-field scope mismatch")
        if record.get("previous_record_hash") != previous_hash:
            raise ValueError(f"decision ledger chain mismatch at position {position}")
        if record.get("record_hash") != _record_hash(record):
            raise ValueError(f"decision record hash mismatch at position {position}")
        normalized_records.append(record)
        previous_hash = str(record["record_hash"])

    ledger = {
        "schema_version": DECISION_LEDGER_SCHEMA_VERSION,
        "ledger_id": ledger_id,
        "organization_id": organization_id,
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "environment_id": environment_id,
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
        organization_id="org_local_demo",
        tenant_id="org_local_demo",
        workspace_id="workspace_local_demo",
        project_id="a2_g3_calibration",
        environment_id="local",
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
        organization_id="org_local_demo",
        tenant_id="org_local_demo",
        workspace_id="workspace_local_demo",
        project_id="a2_g3_calibration",
        environment_id="local",
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
    if not candidate and isinstance(payload.get("observations"), list):
        candidate = [
            call
            for observation in payload["observations"]
            if isinstance(observation, dict)
            for call in observation.get("tool_calls", [])
            if isinstance(call, dict)
        ]
    return [item for item in candidate if isinstance(item, dict)]


def _final_text(payload: dict[str, Any]) -> str:
    agent_output = payload.get("agent_output") if isinstance(payload.get("agent_output"), dict) else {}
    return str(
        payload.get("final_response")
        or payload.get("text")
        or agent_output.get("final_response")
        or agent_output.get("text")
        or agent_output.get("content")
        or ""
    )


def _select_case(payload: dict[str, Any], case_id: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Select and validate one case from an A1 RunResult without guessing."""
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return None, []
    matches = [item for item in cases if isinstance(item, dict) and str(item.get("case_id")) == case_id]
    if len(matches) != 1:
        return None, ["case_not_found" if not matches else "duplicate_case_id"]
    selected = matches[0]
    errors: list[str] = []
    run_id = str(payload.get("run_id") or "")
    for observation in selected.get("observations", []):
        if not isinstance(observation, dict):
            errors.append("invalid_observation")
            continue
        if str(observation.get("run_id") or "") != run_id:
            errors.append("observation_run_id_mismatch")
        if str(observation.get("case_id") or "") != case_id:
            errors.append("observation_case_id_mismatch")
    return selected, errors


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
                "reference_resolution_hash": "",
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
