"""Public-safe A2 judge result persistence manifests."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "a2.result_persistence_manifest.v1"
RECORD_SCHEMA_VERSION = "a2.result_persistence_record.v1"
DEFAULT_CREATED_AT = "2026-07-07T00:00:00Z"
DEFAULT_ORG = "org_local_demo"
DEFAULT_PROJECT = "a2_g3_calibration"
DEFAULT_MANIFEST_ID = "a2_result_persistence_manifest"
SECRET_KEY_MARKERS = (
    "api_key",
    "authorization",
    "bearer",
    "credential",
    "password",
    "secret",
    "token",
)
SECRET_VALUE_PATTERNS = (
    re.compile("sk-" + r"[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
    re.compile("tp_" + r"[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
    re.compile("ashr_live_" + r"[A-Za-z0-9_\-]{8,}", re.IGNORECASE),
    re.compile("Bearer" + r"\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
)


def build_result_persistence_manifest(
    grade_report: dict[str, Any],
    release_gate_report: dict[str, Any],
    scenario_pack: dict[str, Any],
    *,
    scenario_selection_report: dict[str, Any] | None = None,
    run_fixtures: list[dict[str, Any]] | None = None,
    org: str = DEFAULT_ORG,
    project: str = DEFAULT_PROJECT,
    run: str | None = None,
    created_at: str = DEFAULT_CREATED_AT,
    manifest_id: str = DEFAULT_MANIFEST_ID,
    source_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a SaaS-audit manifest without storing raw evidence or secrets."""
    run_id = run or str(grade_report.get("report_id") or "a2_g3_grade_results")
    source_refs = source_refs or {}
    scenarios = {
        str(scenario.get("id")): scenario
        for scenario in scenario_pack.get("scenarios", [])
        if scenario.get("id") is not None
    }
    runs_by_case = _run_fixtures_by_case(run_fixtures or [])

    records: list[dict[str, Any]] = []
    for case_result in grade_report.get("grade_results", []):
        if not isinstance(case_result, dict):
            continue
        scenario_id = str(case_result.get("scenario_id") or "")
        case_id = str(case_result.get("case_id") or scenario_id or "unknown-case")
        scenario = scenarios.get(scenario_id, {})
        run_fixture = runs_by_case.get(case_id)
        for judge_result in case_result.get("judge_results", []):
            if not isinstance(judge_result, dict):
                continue
            judge_id = str(judge_result.get("judge_mode") or "unknown_judge")
            judge_version = str(judge_result.get("judge_version") or "unknown")
            records.append(
                _base_record(
                    record_type="judge_result",
                    org=org,
                    project=project,
                    run=run_id,
                    case=case_id,
                    scenario_id=scenario_id,
                    judge_id=judge_id,
                    judge_version=judge_version,
                    policy_hash=sha256_json(_judge_policy_payload(scenario, judge_id, judge_version)),
                    input_hash=sha256_json(
                        {
                            "case": case_id,
                            "scenario_id": scenario_id,
                            "judge_id": judge_id,
                            "judge_version": judge_version,
                            "scenario_contract": _scenario_contract_for_hash(scenario),
                            "run_fixture": run_fixture or _case_input_fallback(case_result),
                        }
                    ),
                    output_hash=sha256_json(judge_result),
                    created_at=created_at,
                    extra={
                        "passed": bool(judge_result.get("passed")),
                        "score": judge_result.get("score"),
                        "primary_failure_class": _primary_failure_class(judge_result),
                        "safety_blocking": bool(
                            judge_result.get("failure_analysis", {}).get("safety_blocking")
                        ),
                        "result_schema_version": judge_result.get("schema_version"),
                    },
                )
            )

    records.append(
        _release_gate_record(
            release_gate_report,
            org=org,
            project=project,
            run=run_id,
            created_at=created_at,
        )
    )
    records.append(
        _scenario_selection_record(
            scenario_pack,
            scenario_selection_report=scenario_selection_report,
            org=org,
            project=project,
            run=run_id,
            created_at=created_at,
        )
    )

    record_type_counts = dict(sorted(Counter(record["record_type"] for record in records).items()))
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "org": org,
        "project": project,
        "run": run_id,
        "dataset_id": grade_report.get("dataset_id"),
        "created_at": created_at,
        "source_refs": {
            "grade_report": source_refs.get("grade_report", ""),
            "release_gate": source_refs.get("release_gate", ""),
            "scenario_pack": source_refs.get("scenario_pack", ""),
            "scenario_selection": source_refs.get("scenario_selection", ""),
        },
        "record_count": len(records),
        "record_type_counts": record_type_counts,
        "records": records,
        "metadata": {
            "public_safe": True,
            "hash_algorithm": "sha256",
            "canonical_json_hashing": True,
            "raw_evidence_not_recorded": True,
            "raw_private_evidence_not_recorded": True,
            "secrets_not_recorded": True,
            "intended_consumers": ["A2 release gate", "A3 reporting", "SaaS audit export"],
        },
    }


def sha256_json(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def stable_hash(value: Any) -> str:
    return sha256_json(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def build_result_record(
    payload: dict[str, Any],
    *,
    org_id: str,
    project_id: str,
    run_id: str,
    case_id: str = "",
    kind: str = "judge_result",
    judge_version: str = "",
    policy_hash: str = "",
    input_payload: dict[str, Any] | None = None,
    evidence_refs: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a JSONL-ready SaaS audit record without storing raw secrets."""
    redacted_payload = redact_payload(payload)
    redacted_input = redact_payload(input_payload or {})
    redacted_evidence_refs = redact_payload(evidence_refs or [])
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_type": kind,
        "kind": kind,
        "org": org_id,
        "project": project_id,
        "run": run_id,
        "case": case_id,
        "case_id": case_id,
        "scenario_id": payload.get("scenario_id"),
        "judge_id": str(payload.get("endpoint", kind)),
        "judge_version": judge_version,
        "policy_hash": policy_hash,
        "input_hash": stable_hash(redacted_input),
        "output_hash": stable_hash(redacted_payload),
        "created_at": created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "evidence_ref_hash": stable_hash(redacted_evidence_refs),
        "output_summary": _record_summary(redacted_payload),
        "metadata": {
            "public_safe": True,
            "raw_private_payloads_committed": False,
            "raw_payload_not_recorded": True,
            "raw_evidence_refs_not_recorded": True,
            "secrets_not_recorded": True,
        },
    }


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    destination.write_text(text, encoding="utf-8")
    return {
        "schema_version": "a2.result_persistence_jsonl_manifest.v1",
        "path": destination.as_posix(),
        "record_count": len(records),
        "file_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "record_hashes": [stable_hash(record) for record in records],
        "public_safe": True,
    }


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if _is_secret_key(str(key)):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_VALUE_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value


def _record_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary_keys = (
        "schema_version",
        "endpoint",
        "status_code",
        "ok",
        "scenario_id",
        "case_id",
        "passed",
        "score",
        "primary_failure_class",
        "decision",
        "risk_score",
        "selected_count",
    )
    summary = {key: payload[key] for key in summary_keys if key in payload}
    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("schema_version", "scenario_id", "case_id", "passed", "score", "primary_failure_class", "decision"):
            if key in result and key not in summary:
                summary[key] = result[key]
    return summary


def _base_record(
    *,
    record_type: str,
    org: str,
    project: str,
    run: str,
    case: str,
    scenario_id: str | None,
    judge_id: str,
    judge_version: str,
    policy_hash: str,
    input_hash: str,
    output_hash: str,
    created_at: str,
    extra: dict[str, Any],
) -> dict[str, Any]:
    record = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_type": record_type,
        "org": org,
        "project": project,
        "run": run,
        "case": case,
        "case_id": case,
        "scenario_id": scenario_id,
        "judge_id": judge_id,
        "judge_version": judge_version,
        "policy_hash": policy_hash,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "created_at": created_at,
    }
    record.update(extra)
    return record


def _release_gate_record(
    release_gate_report: dict[str, Any],
    *,
    org: str,
    project: str,
    run: str,
    created_at: str,
) -> dict[str, Any]:
    release_candidate = release_gate_report.get("release_candidate", {})
    policy_payload = {
        "schema_version": release_gate_report.get("schema_version"),
        "release_candidate_profile": release_candidate.get("profile"),
        "hard_gate_ids": release_gate_report.get("hard_gate_ids", []),
        "machine_contract": release_gate_report.get("machine_contract", {}),
    }
    input_payload = {
        "release_candidate": release_candidate,
        "current_commercial_gate": release_gate_report.get("current_commercial_gate"),
        "ready_for_commercial_gate": release_gate_report.get("ready_for_commercial_gate"),
        "required_evidence": release_gate_report.get("required_evidence", []),
        "evidence_refs": release_gate_report.get("evidence_refs", []),
    }
    return _base_record(
        record_type="release_gate",
        org=org,
        project=project,
        run=run,
        case="release-gate",
        scenario_id=None,
        judge_id="release_policy_engine",
        judge_version=str(release_gate_report.get("schema_version") or "a2.release_gate.v1"),
        policy_hash=sha256_json(policy_payload),
        input_hash=sha256_json(input_payload),
        output_hash=sha256_json(release_gate_report),
        created_at=created_at,
        extra={
            "decision": release_gate_report.get("decision"),
            "exit_code": release_gate_report.get("exit_code"),
            "risk_score": release_gate_report.get("risk_score"),
            "blocking_gate_count": release_gate_report.get("blocking_gate_count"),
            "evidence_blocker_count": release_gate_report.get("evidence_blocker_count"),
            "warning_count": release_gate_report.get("warning_count"),
            "ready_for_commercial_gate": bool(release_gate_report.get("ready_for_commercial_gate")),
            "result_schema_version": release_gate_report.get("schema_version"),
        },
    )


def _scenario_selection_record(
    scenario_pack: dict[str, Any],
    *,
    scenario_selection_report: dict[str, Any] | None,
    org: str,
    project: str,
    run: str,
    created_at: str,
) -> dict[str, Any]:
    scenarios = [scenario for scenario in scenario_pack.get("scenarios", []) if isinstance(scenario, dict)]
    if scenario_selection_report:
        selected = [
            scenario
            for scenario in scenario_selection_report.get("selected_scenarios", [])
            if isinstance(scenario, dict)
        ]
        selected_ids = [
            str(scenario.get("scenario_id"))
            for scenario in selected
            if scenario.get("scenario_id") is not None
        ]
        family_counts = dict(sorted(Counter(str(scenario.get("family", "unknown")) for scenario in selected).items()))
        selection_id = scenario_selection_report.get("selection_id")
        selector_version = scenario_selection_report.get("schema_version")
    else:
        selected_ids = [str(scenario.get("id")) for scenario in scenarios if scenario.get("id") is not None]
        family_counts = dict(sorted(Counter(str(scenario.get("family", "unknown")) for scenario in scenarios).items()))
        selection_id = "full-pack"
        selector_version = scenario_pack.get("schema_version")
    output_payload = {
        "pack_id": scenario_pack.get("pack_id"),
        "selection_id": selection_id,
        "selected_scenario_ids": selected_ids,
        "selected_count": len(selected_ids),
        "family_counts": family_counts,
    }
    policy_payload = {
        "selector_id": "scenario_library_selector",
        "selector_version": selector_version,
        "pack_schema_version": scenario_pack.get("schema_version"),
        "selection_profile": (scenario_selection_report or {}).get("selection_profile", {}),
        "effective_criteria": (scenario_selection_report or {}).get("effective_criteria", {}),
        "rubric_classes": scenario_pack.get("rubric_classes", []),
        "judge_modes": scenario_pack.get("judge_modes", []),
    }
    input_payload = {
        "pack_id": scenario_pack.get("pack_id"),
        "schema_version": scenario_pack.get("schema_version"),
        "scenario_count": len(scenarios),
        "scenario_summaries": [
            {
                "id": scenario.get("id"),
                "family": scenario.get("family"),
                "tags": scenario.get("tags", []),
                "difficulty": scenario.get("difficulty"),
                "primary_failure_class": scenario.get("primaryFailureClass"),
            }
            for scenario in scenarios
        ],
    }
    return _base_record(
        record_type="scenario_selection",
        org=org,
        project=project,
        run=run,
        case="scenario-selection",
        scenario_id="all",
        judge_id="scenario_library_selector",
        judge_version=str(selector_version or "a2.scenario_selection.v1"),
        policy_hash=sha256_json(policy_payload),
        input_hash=sha256_json(input_payload),
        output_hash=sha256_json(scenario_selection_report or output_payload),
        created_at=created_at,
        extra={
            "selected": True,
            "selected_count": len(selected_ids),
            "selection_id": selection_id,
            "family_counts": family_counts,
            "result_schema_version": selector_version or scenario_pack.get("schema_version"),
        },
    )


def _judge_policy_payload(scenario: dict[str, Any], judge_id: str, judge_version: str) -> dict[str, Any]:
    return {
        "judge_id": judge_id,
        "judge_version": judge_version,
        "scenario_id": scenario.get("id"),
        "tool_policy": scenario.get("toolPolicy", {}),
        "expected_behaviors": scenario.get("expectedBehaviors", []),
        "expected_facts": scenario.get("expectedFacts", []),
        "forbidden_facts": scenario.get("forbiddenFacts", []),
        "expected_tool_output_facts": scenario.get("expectedToolOutputFacts", []),
        "failure_signals": scenario.get("failureSignals", []),
        "primary_failure_class": scenario.get("primaryFailureClass"),
    }


def _scenario_contract_for_hash(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": scenario.get("id"),
        "family": scenario.get("family"),
        "tags": scenario.get("tags", []),
        "difficulty": scenario.get("difficulty"),
        "tool_policy": scenario.get("toolPolicy", {}),
        "expected_behaviors": scenario.get("expectedBehaviors", []),
        "fixture_refs": scenario.get("fixtureRefs", []),
        "primary_failure_class": scenario.get("primaryFailureClass"),
    }


def _case_input_fallback(case_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": case_result.get("schema_version"),
        "scenario_id": case_result.get("scenario_id"),
        "case_id": case_result.get("case_id"),
        "aggregate_passed": case_result.get("passed"),
        "aggregate_score": case_result.get("score"),
        "aggregate_primary_failure_class": case_result.get("primary_failure_class"),
    }


def _primary_failure_class(judge_result: dict[str, Any]) -> str:
    analysis = judge_result.get("failure_analysis", {})
    if isinstance(analysis, dict):
        return str(analysis.get("primary_failure_class") or "none")
    return "none"


def _run_fixtures_by_case(run_fixtures: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for fixture in run_fixtures:
        if not isinstance(fixture, dict):
            continue
        case_id = fixture.get("case_id")
        if case_id is None and isinstance(fixture.get("run"), dict):
            case_id = fixture["run"].get("case_id")
        if case_id is not None:
            indexed[str(case_id)] = fixture
    return indexed


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in SECRET_KEY_MARKERS)
