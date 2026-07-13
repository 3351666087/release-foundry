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
PRIVATE_EVIDENCE_PATTERNS = (
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs(?:[\\/][^\s\"']*)?", re.IGNORECASE),
)
PUBLIC_RELEASE_POLICY_METRICS = (
    "usage_quota_blocked",
    "trust_publishability_blocked",
    "api_key_boundary_violations",
    "server_side_grading_stale",
)


def build_result_persistence_manifest(
    grade_report: dict[str, Any],
    release_gate_report: dict[str, Any],
    scenario_pack: dict[str, Any],
    *,
    scenario_selection_report: dict[str, Any] | None = None,
    release_unblock_checklist_report: dict[str, Any] | None = None,
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
    if release_unblock_checklist_report:
        records.append(
            _release_unblock_checklist_record(
                release_unblock_checklist_report,
                org=org,
                project=project,
                run=run_id,
                created_at=created_at,
            )
        )

    record_type_counts = dict(sorted(Counter(record["record_type"] for record in records).items()))
    source_ref_payload = {
        "grade_report": source_refs.get("grade_report", ""),
        "release_gate": source_refs.get("release_gate", ""),
        "scenario_pack": source_refs.get("scenario_pack", ""),
        "scenario_selection": source_refs.get("scenario_selection", ""),
    }
    for optional_ref in ("regression_promotion_queue", "release_unblock_checklist"):
        if source_refs.get(optional_ref):
            source_ref_payload[optional_ref] = source_refs[optional_ref]
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "tenant_id": org,
        "org": org,
        "project": project,
        "run": run_id,
        "dataset_id": grade_report.get("dataset_id"),
        "created_at": created_at,
        "source_refs": source_ref_payload,
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
        "tenant_id": org_id,
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


def write_jsonl(
    path: str | Path,
    records: list[dict[str, Any]],
    *,
    previous_manifest_hash: str = "",
    sequence_number: int = 1,
) -> dict[str, Any]:
    if sequence_number < 1:
        raise ValueError("sequence_number must be positive")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(destination)
    record_hashes = [stable_hash(record) for record in records]
    chain_hash = stable_hash(
        {
            "previous_manifest_hash": previous_manifest_hash,
            "sequence_number": sequence_number,
            "file_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "record_hashes": record_hashes,
        }
    )
    return {
        "schema_version": "a2.result_persistence_jsonl_manifest.v1",
        "path": destination.as_posix(),
        "record_count": len(records),
        "file_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "record_hashes": record_hashes,
        "previous_manifest_hash": previous_manifest_hash,
        "sequence_number": sequence_number,
        "chain_hash": chain_hash,
        "public_safe": True,
    }


def verify_jsonl_manifest(
    path: str | Path,
    manifest: dict[str, Any],
    *,
    expected_sequence_number: int | None = None,
    pinned_chain_hash: str = "",
) -> dict[str, Any]:
    """Verify exact JSONL bytes and ordered record hashes without trusting the file."""
    source = Path(path)
    if not source.is_file():
        return {
            "state": "blocked",
            "blockers": ["jsonl_file_missing"],
            "public_safe": True,
        }
    text = source.read_text(encoding="utf-8")
    blockers: list[str] = []
    if expected_sequence_number is not None and manifest.get("sequence_number") != expected_sequence_number:
        blockers.append("jsonl_sequence_gap_or_replay")
    if pinned_chain_hash and manifest.get("chain_hash") != pinned_chain_hash:
        blockers.append("jsonl_chain_head_pin_mismatch")
    observed_file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if observed_file_hash != manifest.get("file_sha256"):
        blockers.append("jsonl_file_hash_mismatch")
    try:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    except json.JSONDecodeError:
        records = []
        blockers.append("jsonl_parse_failure")
    if len(records) != manifest.get("record_count"):
        blockers.append("jsonl_record_count_mismatch")
    observed_record_hashes = [stable_hash(record) for record in records]
    if observed_record_hashes != manifest.get("record_hashes"):
        blockers.append("jsonl_record_hash_mismatch")
    expected_chain_hash = stable_hash(
        {
            "previous_manifest_hash": manifest.get("previous_manifest_hash", ""),
            "sequence_number": manifest.get("sequence_number"),
            "file_sha256": observed_file_hash,
            "record_hashes": observed_record_hashes,
        }
    )
    if expected_chain_hash != manifest.get("chain_hash"):
        blockers.append("jsonl_chain_hash_mismatch")
    return {
        "state": "verified" if not blockers else "blocked",
        "record_count": len(records),
        "file_sha256": observed_file_hash,
        "record_hashes": observed_record_hashes,
        "chain_hash": expected_chain_hash,
        "blockers": blockers,
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
        for pattern in PRIVATE_EVIDENCE_PATTERNS:
            redacted = pattern.sub("[PRIVATE_EVIDENCE_REF]", redacted)
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
        "source",
        "operation",
        "upload_id",
        "batch_id",
        "trace_batch_id",
        "payload_sha256",
        "trace_batch_sha256",
        "raw_payload_included",
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
    if isinstance(payload.get("payload_keys"), list):
        summary["payload_keys"] = [str(item) for item in payload["payload_keys"]]
    result = payload.get("result")
    if isinstance(result, dict):
        for key in (
            "schema_version",
            "scenario_id",
            "case_id",
            "passed",
            "score",
            "primary_failure_class",
            "decision",
            "upload_id",
            "batch_id",
            "payload_sha256",
            "raw_payload_included",
        ):
            if key in result and key not in summary:
                summary[key] = result[key]
        if isinstance(result.get("payload_keys"), list) and "payload_keys" not in summary:
            summary["payload_keys"] = [str(item) for item in result["payload_keys"]]
    release_policy_audit = _release_policy_audit_summary(payload)
    if release_policy_audit:
        summary["release_policy_audit"] = release_policy_audit
    return summary


def _release_policy_audit_summary(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation = _extract_release_policy_evaluation(payload)
    if not evaluation:
        return {}

    audit: dict[str, Any] = {}
    for key in (
        "schema_version",
        "policy_id",
        "policy_version",
        "policy_hash",
        "project_id",
        "environment",
        "release_candidate_id",
        "decision",
    ):
        _copy_public_scalar(audit, key, evaluation.get(key))
    for key in ("blocking_violation_count", "non_blocking_violation_count", "waived_violation_count"):
        _copy_public_scalar(audit, key, evaluation.get(key))

    metrics = _public_saas_surface_metrics(evaluation.get("metrics"))
    if metrics:
        audit["saas_surface_metrics"] = metrics

    active_violations = evaluation.get("violations")
    if isinstance(active_violations, list):
        audit["active_violations"] = _public_active_violations(active_violations)

    waiver_summary = evaluation.get("waiver_summary")
    if isinstance(waiver_summary, dict):
        audit["waiver_summary"] = _public_count_summary(waiver_summary)

    applied_waivers = evaluation.get("applied_waivers")
    if isinstance(applied_waivers, list):
        audit["applied_waivers"] = _public_waiver_applications(applied_waivers)

    waived_violations = evaluation.get("waived_violations")
    if isinstance(waived_violations, list):
        audit["waived_violations"] = _public_waived_violations(waived_violations)

    return audit


def _extract_release_policy_evaluation(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    if payload.get("schema_version") == "a2.release_policy_evaluation.v1":
        return payload
    evaluation = payload.get("policy_evaluation")
    if isinstance(evaluation, dict):
        return evaluation
    for key in ("result", "release_gate"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_evaluation = _extract_release_policy_evaluation(nested)
            if nested_evaluation:
                return nested_evaluation
    return {}


def _public_count_summary(summary: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, bool) or value is None:
            public[str(key)] = value
        elif isinstance(value, (int, float)):
            public[str(key)] = value
    return public


def _public_saas_surface_metrics(metrics: Any) -> dict[str, Any]:
    if not isinstance(metrics, dict):
        return {}
    public: dict[str, Any] = {}
    for key in PUBLIC_RELEASE_POLICY_METRICS:
        value = metrics.get(key)
        if isinstance(value, bool):
            public[key] = value
        elif isinstance(value, (int, float)):
            public[key] = value
    return public


def _public_active_violations(violations: list[Any]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for violation in violations:
        if not isinstance(violation, dict):
            continue
        summary: dict[str, Any] = {}
        for key in (
            "rule_id",
            "type",
            "mode",
            "severity",
            "summary",
            "owner_role",
            "business_impact",
            "dashboard_label",
        ):
            _copy_public_scalar(summary, key, violation.get(key))
        _copy_public_scalar(summary, "passed", violation.get("passed"))
        _copy_public_scalar(summary, "risk_weight", violation.get("risk_weight"))
        _copy_public_scalar(summary, "waiver_eligible", violation.get("waiver_eligible"))

        observed = _public_measurement_summary(violation.get("observed"))
        if observed:
            summary["observed"] = observed
        threshold = _public_measurement_summary(violation.get("threshold"))
        if threshold:
            summary["threshold"] = threshold

        public.append(summary)
    return public


def _public_waiver_applications(waivers: list[Any]) -> list[dict[str, Any]]:
    return [_public_waiver_application(item) for item in waivers if isinstance(item, dict)]


def _public_waiver_application(waiver: dict[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for key in (
        "waiver_id",
        "approval_id",
        "status",
        "reviewer",
        "expires_at",
        "waived_rule_id",
        "waived_mode",
        "waived_severity",
        "waived_type",
    ):
        _copy_public_scalar(public, key, waiver.get(key))

    reason = _public_text(waiver.get("reason"))
    if reason:
        public["reason_present"] = True
        public["reason_hash"] = stable_hash(reason)

    evidence_refs = _evidence_refs(waiver)
    if evidence_refs:
        public["evidence_ref_count"] = len(evidence_refs)
        public["evidence_ref_hashes"] = [stable_hash(_public_text(ref)) for ref in evidence_refs]

    return public


def _public_waived_violations(violations: list[Any]) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    for violation in violations:
        if not isinstance(violation, dict):
            continue
        summary: dict[str, Any] = {}
        for key in ("rule_id", "type", "mode", "severity", "summary"):
            _copy_public_scalar(summary, key, violation.get(key))
        _copy_public_scalar(summary, "passed", violation.get("passed"))

        observed = _public_measurement_summary(violation.get("observed"))
        if observed:
            summary["observed"] = observed
        threshold = _public_measurement_summary(violation.get("threshold"))
        if threshold:
            summary["threshold"] = threshold

        waiver = violation.get("waiver")
        if isinstance(waiver, dict):
            summary["waiver"] = _public_waiver_application(waiver)

        public.append(summary)
    return public


def _public_measurement_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    public: dict[str, Any] = {}
    for key in (
        "failure_class",
        "metric",
        "count",
        "rate",
        "value",
        "max_count",
        "max_rate",
        "operator",
        "threshold",
    ):
        if key in value:
            _copy_public_scalar(public, key, value.get(key))
    return public


def _copy_public_scalar(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        target[key] = value
        return
    if isinstance(value, (int, float)):
        target[key] = value
        return
    text = _public_text(value)
    if text:
        target[key] = text


def _public_text(value: Any, *, max_length: int = 160) -> str:
    if value is None:
        return ""
    text = str(redact_payload(str(value))).strip()
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def _evidence_refs(payload: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    evidence_ref = payload.get("evidence_ref")
    if evidence_ref is not None:
        refs.append(str(evidence_ref))
    evidence_refs = payload.get("evidence_refs")
    if isinstance(evidence_refs, list):
        refs.extend(str(item) for item in evidence_refs if str(item).strip())
    return refs


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
        "tenant_id": org,
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
    extra = {
        "decision": release_gate_report.get("decision"),
        "exit_code": release_gate_report.get("exit_code"),
        "risk_score": release_gate_report.get("risk_score"),
        "blocking_gate_count": release_gate_report.get("blocking_gate_count"),
        "evidence_blocker_count": release_gate_report.get("evidence_blocker_count"),
        "warning_count": release_gate_report.get("warning_count"),
        "ready_for_commercial_gate": bool(release_gate_report.get("ready_for_commercial_gate")),
        "result_schema_version": release_gate_report.get("schema_version"),
    }
    release_policy_audit = _release_policy_audit_summary(release_gate_report)
    if release_policy_audit:
        extra["release_policy_audit"] = release_policy_audit
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
        extra=extra,
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


def _release_unblock_checklist_record(
    checklist: dict[str, Any],
    *,
    org: str,
    project: str,
    run: str,
    created_at: str,
) -> dict[str, Any]:
    gate_items = [item for item in checklist.get("gate_items", []) if isinstance(item, dict)]
    public_gate_summary = []
    for item in gate_items:
        required_actions = [action for action in item.get("required_actions", []) if isinstance(action, dict)]
        public_gate_summary.append(
            {
                "gate": item.get("gate"),
                "status": item.get("status"),
                "blocks_release": bool(item.get("blocks_release")),
                "owner_role": item.get("owner_role"),
                "missing_count": item.get("missing_count"),
                "required_evidence_sources": [
                    str(action.get("required_evidence_source"))
                    for action in required_actions
                    if action.get("required_evidence_source") is not None
                ],
                "action_ids": [
                    str(action.get("action_id"))
                    for action in required_actions
                    if action.get("action_id") is not None
                ],
                "private_evidence_required": any(bool(action.get("private_evidence_required")) for action in required_actions),
            }
        )
    policy_payload = {
        "schema_version": checklist.get("schema_version"),
        "checklist_id": checklist.get("checklist_id"),
        "source_release_gate": checklist.get("source_release_gate"),
        "review_workflow": checklist.get("review_workflow", {}),
    }


    input_payload = {
        "release_gate_decision": checklist.get("release_gate_decision"),
        "release_gate_exit_code": checklist.get("release_gate_exit_code"),
        "release_gate_risk_score": checklist.get("release_gate_risk_score"),
        "gate_count": len(gate_items),
        "gate_summary": public_gate_summary,
    }
    output_payload = {
        "schema_version": checklist.get("schema_version"),
        "checklist_id": checklist.get("checklist_id"),
        "overall_status": checklist.get("overall_status"),
        "blocked_gate_count": checklist.get("blocked_gate_count"),
        "a3_consumption_summary": checklist.get("a3_consumption_summary", {}),
        "gate_summary": public_gate_summary,
    }
    return _base_record(
        record_type="release_unblock_checklist",
        org=org,
        project=project,
        run=run,
        case="release-unblock-checklist",
        scenario_id=None,
        judge_id="release_unblock_checklist",
        judge_version=str(checklist.get("schema_version") or "a2.release_unblock_checklist.v1"),
        policy_hash=sha256_json(redact_payload(policy_payload)),
        input_hash=sha256_json(redact_payload(input_payload)),
        output_hash=sha256_json(redact_payload(output_payload)),
        created_at=created_at,
        extra={
            "overall_status": checklist.get("overall_status"),
            "blocked_gate_count": checklist.get("blocked_gate_count"),
            "release_gate_decision": checklist.get("release_gate_decision"),
            "release_gate_risk_score": checklist.get("release_gate_risk_score"),
            "gate_count": len(gate_items),
            "private_evidence_required": any(
                bool(gate.get("private_evidence_required"))
                for gate in public_gate_summary
            ),
            "result_schema_version": checklist.get("schema_version"),
        },
    )


def build_structured_output_failure_record(
    failure_receipt: dict[str, Any],
    *,
    org_id: str,
    project_id: str,
    run_id: str,
    case_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Persist only hashes and classification for malformed/provider-failed model output."""
    state = str(failure_receipt.get("state") or "")
    if state in {"", "valid"}:
        raise ValueError("failure persistence requires a failed structured-output receipt")
    public_payload = {
        "state": state,
        "provider_status": str(failure_receipt.get("provider_status") or ""),
        "raw_response_hash": str(failure_receipt.get("raw_response_hash") or ""),
        "parsed_output_hash": str(failure_receipt.get("parsed_output_hash") or ""),
        "blockers": list(failure_receipt.get("blockers") or []),
    }
    return build_result_record(
        public_payload,
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        case_id=case_id,
        kind="structured_output_failure",
        input_payload={"failure_receipt_hash": stable_hash(failure_receipt)},
        created_at=created_at,
    )


def build_ocr_vision_disagreement_record(
    disagreement: dict[str, Any],
    *,
    org_id: str,
    project_id: str,
    run_id: str,
    case_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Persist an OCR/vision disagreement using only public-safe hashes and reason codes."""
    if disagreement.get("state") != "disagreement":
        raise ValueError("disagreement persistence requires disagreement state")
    payload = {
        key: disagreement.get(key)
        for key in (
            "artifact_hash",
            "ocr_observation_hash",
            "vision_output_hash",
            "reason_code",
            "review_packet_hash",
            "blockers",
        )
    }
    return build_result_record(
        payload,
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        case_id=case_id,
        kind="ocr_vision_disagreement",
        input_payload={"disagreement_hash": stable_hash(disagreement)},
        created_at=created_at,
    )


def build_multimodal_runtime_record(
    runtime_summary: dict[str, Any],
    *,
    org_id: str,
    project_id: str,
    run_id: str,
    case_id: str,
    judge_version: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Persist runtime governance without raw responses or cancellation details."""
    safe_payload = {
        key: runtime_summary.get(key)
        for key in (
            "schema_version",
            "observation_count",
            "timeout_count",
            "failure_counts",
            "provider_timeout_rate",
            "completed_count",
            "completed_semantic_count",
            "empty_response_count",
            "empty_response_rate",
            "invalid_structured_output_count",
            "invalid_structured_output_rate",
            "valid_semantic_output_rate",
            "qualification_state",
            "blockers",
            "queue_telemetry",
            "cancellation_receipt_hashes",
            "public_safe",
        )
        if key in runtime_summary
    }
    return build_result_record(
        safe_payload,
        org_id=org_id,
        project_id=project_id,
        run_id=run_id,
        case_id=case_id,
        kind="multimodal_runtime",
        judge_version=judge_version,
        policy_hash=stable_hash(
            {
                "maximum_latency_seconds": runtime_summary.get("maximum_latency_seconds"),
                "maximum_completion_tokens": runtime_summary.get("maximum_completion_tokens"),
                "maximum_provider_timeout_rate": runtime_summary.get(
                    "maximum_provider_timeout_rate"
                ),
                "minimum_valid_semantic_output_rate": runtime_summary.get(
                    "minimum_valid_semantic_output_rate"
                ),
                "maximum_empty_response_rate": runtime_summary.get(
                    "maximum_empty_response_rate"
                ),
                "maximum_invalid_structured_output_rate": runtime_summary.get(
                    "maximum_invalid_structured_output_rate"
                ),
            }
        ),
        input_payload={
            "observation_count": runtime_summary.get("observation_count"),
            "cancellation_receipt_hashes": runtime_summary.get(
                "cancellation_receipt_hashes", []
            ),
        },
        created_at=created_at,
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
    if normalized in PUBLIC_RELEASE_POLICY_METRICS:
        return False
    return any(marker in normalized for marker in SECRET_KEY_MARKERS)
