"""Public-safe SaaS control-plane summary for A2 judge products."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .release_policy import compute_policy_hash, policy_hash_matches, select_release_policy
from .service_wrapper import (
    BATCH_ENDPOINT,
    CALIBRATION_EVALUATE_ENDPOINT,
    CASE_ENDPOINT,
    REGRESSION_REPLAY_ENDPOINT,
    RELEASE_POLICY_ENDPOINT,
    RUN_ENDPOINT,
    SERVICE_VERSION,
)


SCHEMA_VERSION = "a2.saas_control_plane_report.v1"
DEFAULT_REPORT_ID = "a2_saas_control_plane_report"
DEFAULT_CREATED_AT = "2026-07-07T00:00:00Z"


def build_saas_control_plane_report(
    *,
    grade_report: dict[str, Any],
    coverage_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    release_gate_report: dict[str, Any],
    scenario_selection_report: dict[str, Any],
    result_persistence_manifest: dict[str, Any],
    release_policy_config: dict[str, Any],
    judge_version_registry: dict[str, Any] | None = None,
    source_refs: dict[str, str] | None = None,
    created_at: str = DEFAULT_CREATED_AT,
    report_id: str = DEFAULT_REPORT_ID,
) -> dict[str, Any]:
    """Build the A2 artifact A3 should consume as a SaaS control plane."""
    source_refs = source_refs or {}
    project = scenario_selection_report.get("project", {})
    if not isinstance(project, dict):
        project = {}
    project_id = str(project.get("project_id") or result_persistence_manifest.get("project") or "")
    environment = str(scenario_selection_report.get("environment") or "prod")
    selected_policy, policy_selection = select_release_policy(
        release_policy_config,
        project_id=project_id,
        environment=environment,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_id": report_id,
        "created_at": created_at,
        "tenant": _tenant_summary(result_persistence_manifest, project_id=project_id, environment=environment),
        "service": _service_summary(),
        "judge_versioning": _judge_versioning_summary(result_persistence_manifest),
        "judge_version_registry": _judge_version_registry_summary(judge_version_registry or {}),
        "policy_config": _policy_config_summary(
            release_policy_config,
            selected_policy=selected_policy,
            selection=policy_selection,
            release_gate_report=release_gate_report,
        ),
        "scenario_selection": _scenario_selection_summary(scenario_selection_report),
        "calibration": _calibration_summary(calibration_matrix),
        "result_persistence": _persistence_summary(result_persistence_manifest),
        "release_gate": _release_gate_summary(release_gate_report),
        "a3_dashboard_contract": _a3_dashboard_contract(
            grade_report=grade_report,
            coverage_report=coverage_report,
            scenario_selection_report=scenario_selection_report,
            result_persistence_manifest=result_persistence_manifest,
            selected_policy=selected_policy,
            release_gate_report=release_gate_report,
        ),
        "source_refs": {
            "grade_report": source_refs.get("grade_report", ""),
            "coverage_report": source_refs.get("coverage_report", ""),
            "calibration_matrix": source_refs.get("calibration_matrix", ""),
            "release_gate": source_refs.get("release_gate", ""),
            "scenario_selection": source_refs.get("scenario_selection", ""),
            "result_persistence": source_refs.get("result_persistence", ""),
            "judge_versions": source_refs.get("judge_versions", ""),
            "release_policy_config": source_refs.get("release_policy_config", ""),
        },
        "metadata": {
            "public_safe": True,
            "deterministic": True,
            "requires_network": False,
            "requires_ashr_api_key": False,
            "does_not_execute_live_calls": True,
            "raw_private_evidence_not_recorded": True,
            "secrets_not_recorded": True,
            "intended_consumers": ["A2 service wrapper", "A3 SaaS admin console", "release gate API"],
        },
    }


def _tenant_summary(manifest: dict[str, Any], *, project_id: str, environment: str) -> dict[str, Any]:
    org = str(manifest.get("tenant_id") or manifest.get("org") or "org_local_demo")
    return {
        "tenant_id": org,
        "org_id": org,
        "project_id": project_id,
        "environment": environment,
        "run_id": str(manifest.get("run", "")),
        "dataset_id": str(manifest.get("dataset_id") or ""),
        "tenant_scoped": bool(org and project_id),
    }


def _service_summary() -> dict[str, Any]:
    return {
        "service_version": SERVICE_VERSION,
        "mode": "deterministic_local_service_contract",
        "endpoints": [
            _endpoint("judge_case", CASE_ENDPOINT, ["scenario_id", "case_id", "run"], ["judge_result"]),
            _endpoint("judge_run", RUN_ENDPOINT, ["run_id", "cases"], ["grade_report", "run_summary"]),
            _endpoint("judge_batch", BATCH_ENDPOINT, ["cases"], ["grade_report"]),
            _endpoint(
                "release_policy_evaluate",
                RELEASE_POLICY_ENDPOINT,
                ["project_id", "environment", "grade_report"],
                ["release_gate", "policy_evaluation"],
            ),
            _endpoint(
                "regression_replay",
                REGRESSION_REPLAY_ENDPOINT,
                ["calibration_matrix", "case_book_report"],
                ["replay_report"],
            ),
            _endpoint(
                "calibration_evaluate",
                CALIBRATION_EVALUATE_ENDPOINT,
                ["pack_path", "run_dir", "observations_path"],
                ["calibration_matrix", "source_coverage"],
            ),
            _endpoint(
                "scenario_selection",
                "/internal/scenarios/select",
                ["project_id", "environment"],
                ["selected_scenario_ids", "coverage_summary"],
            ),
            _endpoint(
                "result_persistence_manifest",
                "/internal/results/persist",
                ["grade_report", "release_gate", "scenario_pack"],
                ["records", "record_type_counts"],
            ),
        ],
        "async_job_compatible": True,
        "safe_for_worker_dispatch": True,
    }


def _endpoint(endpoint_id: str, path: str, request_fields: list[str], response_fields: list[str]) -> dict[str, Any]:
    return {
        "endpoint_id": endpoint_id,
        "method": "POST",
        "path": path,
        "request_fields": request_fields,
        "response_fields": response_fields,
        "deterministic": True,
        "requires_network": False,
    }


def _judge_versioning_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    records = [record for record in manifest.get("records", []) if isinstance(record, dict)]
    judge_records = [record for record in records if record.get("record_type") == "judge_result"]
    judge_versions = sorted({str(record.get("judge_version", "")) for record in judge_records if record.get("judge_version")})
    judge_ids = sorted({str(record.get("judge_id", "")) for record in judge_records if record.get("judge_id")})
    policy_hashes = sorted({str(record.get("policy_hash", "")) for record in records if record.get("policy_hash")})
    return {
        "judge_result_record_count": len(judge_records),
        "judge_id_count": len(judge_ids),
        "judge_ids": judge_ids,
        "judge_versions": judge_versions,
        "policy_hash_count": len(policy_hashes),
        "all_records_have_policy_hash": all(bool(record.get("policy_hash")) for record in records),
        "all_records_have_input_hash": all(bool(record.get("input_hash")) for record in records),
        "all_records_have_output_hash": all(bool(record.get("output_hash")) for record in records),
        "version_fields": [
            "judge_version",
            "policy_hash",
            "input_hash",
            "output_hash",
            "result_schema_version",
        ],
    }


def _judge_version_registry_summary(registry: dict[str, Any]) -> dict[str, Any]:
    judges = [judge for judge in registry.get("judges", []) if isinstance(judge, dict)]
    migration = registry.get("migration_policy", {})
    if not isinstance(migration, dict):
        migration = {}
    return {
        "registry_id": str(registry.get("registry_id", "")),
        "registry_hash": str(registry.get("registry_hash", "")),
        "active_release": registry.get("active_release", {}),
        "declared_judge_count": int(registry.get("declared_judge_count", len(judges))),
        "observed_judge_count": int(registry.get("observed_judge_count", 0)),
        "all_declared_judges_observed": bool(registry.get("all_declared_judges_observed")),
        "pinning_supported": bool(registry.get("service_contract", {}).get("pinning_supported")),
        "history_replay_supported": bool(registry.get("service_contract", {}).get("history_replay_supported")),
        "can_compare_judge_versions": bool(migration.get("can_compare_judge_versions")),
        "can_replay_history": bool(migration.get("can_replay_history")),
        "judge_pins": [
            str(judge.get("pinning", {}).get("recommended_pin", ""))
            for judge in judges
            if judge.get("pinning", {}).get("recommended_pin")
        ],
    }


def _policy_config_summary(
    config: dict[str, Any],
    *,
    selected_policy: dict[str, Any],
    selection: dict[str, Any],
    release_gate_report: dict[str, Any],
) -> dict[str, Any]:
    policies = [policy for policy in config.get("policies", []) if isinstance(policy, dict)]
    assignments = [assignment for assignment in config.get("assignments", []) if isinstance(assignment, dict)]
    environments = sorted({str(assignment.get("environment", "")) for assignment in assignments if assignment.get("environment")})
    return {
        "config_id": str(config.get("config_id", "")),
        "default_policy_id": str(config.get("default_policy_id", "")),
        "policy_count": len(policies),
        "assignment_count": len(assignments),
        "environments": environments,
        "selected_policy": {
            "policy_id": str(selected_policy.get("policy_id", "")),
            "policy_version": str(selected_policy.get("policy_version", "")),
            "policy_hash": compute_policy_hash(selected_policy),
            "policy_hash_valid": policy_hash_matches(selected_policy),
            "rule_count": len(selected_policy.get("rules", [])) if isinstance(selected_policy.get("rules"), list) else 0,
            "selection": selection,
        },
        "waiver_flow_supported": True,
        "release_gate_decision": str(release_gate_report.get("decision", "")),
        "metadata": {
            "per_project_policy": True,
            "per_environment_policy": True,
            "policy_hash_algorithm": "sha256 over policy JSON excluding policy_hash",
        },
    }


def _scenario_selection_summary(report: dict[str, Any]) -> dict[str, Any]:
    coverage = report.get("coverage_summary", {})
    if not isinstance(coverage, dict):
        coverage = {}
    selected = [item for item in report.get("selected_scenarios", []) if isinstance(item, dict)]
    return {
        "selection_id": str(report.get("selection_id", "")),
        "source_pack_id": str(report.get("source_pack_id", "")),
        "source_scenario_count": int(report.get("source_scenario_count", 0)),
        "selected_count": int(report.get("selected_scenario_count", len(selected))),
        "selected_scenario_ids": [str(item.get("scenario_id", "")) for item in selected if item.get("scenario_id")],
        "coverage_ready": bool(coverage.get("coverage_ready")),
        "required_axes_met": {
            axis: axis not in set(coverage.get("missing_capability_axes", []))
            for axis in coverage.get("requested_capability_axes", [])
        },
        "media_or_multimodal_count": int(coverage.get("media_scenario_count", 0)),
        "missing_capability_axes": list(coverage.get("missing_capability_axes", [])),
        "missing_tenant_saas_tags": list(coverage.get("missing_tenant_saas_tags", [])),
        "risk_tier_counts": coverage.get("risk_tier_counts", {}),
    }


def _calibration_summary(matrix: dict[str, Any]) -> dict[str, Any]:
    coverage = matrix.get("source_coverage", {})
    agreements = matrix.get("agreement_summary", {})
    if not isinstance(coverage, dict):
        coverage = {}
    if not isinstance(agreements, dict):
        agreements = {}
    mismatch_count = sum(
        int(item.get("mismatch_count", 0))
        for item in agreements.values()
        if isinstance(item, dict)
    )
    ashr = coverage.get("ashr_grading", {}) if isinstance(coverage.get("ashr_grading"), dict) else {}
    llm = coverage.get("llm_judge", {}) if isinstance(coverage.get("llm_judge"), dict) else {}
    return {
        "matrix_id": str(matrix.get("matrix_id", "")),
        "case_count": int(matrix.get("case_count", 0)),
        "sources": list(matrix.get("sources", [])),
        "source_coverage": coverage,
        "agreement_mismatch_count": mismatch_count,
        "cost_ledger": matrix.get("cost_ledger", []),
        "live_evidence_gates": {
            "ashr_grading_missing": int(ashr.get("missing", 0)),
            "llm_judge_missing": int(llm.get("missing", 0)),
            "ashr_grading_ready": int(ashr.get("missing", 0)) == 0,
            "semantic_judge_ready": int(llm.get("missing", 0)) == 0,
        },
    }


def _persistence_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    metadata = manifest.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "manifest_id": str(manifest.get("manifest_id", "")),
        "record_count": int(manifest.get("record_count", 0)),
        "record_type_counts": manifest.get("record_type_counts", {}),
        "public_safe": metadata.get("public_safe") is True,
        "raw_private_evidence_not_recorded": metadata.get("raw_private_evidence_not_recorded") is True,
        "secrets_not_recorded": metadata.get("secrets_not_recorded") is True,
        "ready_for_audit_export": bool(
            metadata.get("public_safe") is True
            and metadata.get("raw_private_evidence_not_recorded") is True
            and metadata.get("secrets_not_recorded") is True
        ),
    }


def _release_gate_summary(report: dict[str, Any]) -> dict[str, Any]:
    blockers = [item for item in report.get("blockers", []) if isinstance(item, dict)]
    warnings = [item for item in report.get("warnings", []) if isinstance(item, dict)]
    return {
        "report_id": str(report.get("report_id", "")),
        "decision": str(report.get("decision", "")),
        "exit_code": report.get("exit_code"),
        "risk_score": report.get("risk_score"),
        "current_commercial_gate": str(report.get("current_commercial_gate", "")),
        "ready_for_commercial_gate": bool(report.get("ready_for_commercial_gate")),
        "blocking_gate_count": int(report.get("blocking_gate_count", len(blockers))),
        "warning_count": int(report.get("warning_count", len(warnings))),
        "blocker_type_counts": dict(sorted(Counter(str(item.get("type", "")) for item in blockers).items())),
    }


def _a3_dashboard_contract(
    *,
    grade_report: dict[str, Any],
    coverage_report: dict[str, Any],
    scenario_selection_report: dict[str, Any],
    result_persistence_manifest: dict[str, Any],
    selected_policy: dict[str, Any],
    release_gate_report: dict[str, Any],
) -> dict[str, Any]:
    coverage = scenario_selection_report.get("coverage_summary", {})
    if not isinstance(coverage, dict):
        coverage = {}
    return {
        "consumer": "A3 SaaS admin console",
        "status": "ready_for_read_only_dashboard_consumption",
        "recommended_payload_keys": {
            "gradeFixture": "fixtures/a2/results/a2_g3_grade_results.json",
            "coverage": "fixtures/a2/results/a2_g3_coverage_report.json",
            "releaseGate": "fixtures/a2/results/a2_release_gate_report.json",
            "scenarioSelection": "fixtures/a2/results/a2_scenario_selection_report.json",
            "resultPersistence": "fixtures/a2/results/a2_result_persistence_manifest.json",
            "judgeVersions": "fixtures/a2/results/a2_judge_versions.json",
            "a2ControlPlane": "fixtures/a2/results/a2_saas_control_plane_report.json",
        },
        "dashboard_can_show": [
            "tenant-scoped project/environment selection",
            "selected scenario pack coverage",
            "judge version and policy hash audit",
            "judge registry pins and migration readiness",
            "release policy decision and blocker counts",
            "public-safe persistence record counts",
            "calibration source coverage and live evidence gaps",
        ],
        "local_meter": {
            "grade_case_count": int(grade_report.get("total_cases", 0)),
            "scenario_count": int(coverage_report.get("scenario_count", 0)),
            "selected_scenario_count": int(scenario_selection_report.get("selected_scenario_count", 0)),
            "audit_record_count": int(result_persistence_manifest.get("record_count", 0)),
        },
        "selected_policy_id": str(selected_policy.get("policy_id", "")),
        "release_gate_decision": str(release_gate_report.get("decision", "")),
        "selection_coverage_ready": bool(coverage.get("coverage_ready")),
        "private_fields_forbidden": ["api_key", "authorization", "token", "private_input_ref", "raw_evidence"],
        "mutations_enabled": False,
    }
