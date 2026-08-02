"""Commercial readiness reporting for A2 evaluation artifacts."""

from __future__ import annotations

import math
from typing import Any

from .evidence_readiness import verify_evidence_readiness_artifact
from .regression_replay import verify_regression_replay_artifact


COMMERCIAL_GOAL_SOURCE = "ReleaseFoundry_Commercial_Grade_Goals_CN.pdf"


def build_commercial_readiness_report(
    coverage_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    case_book_report: dict[str, Any] | None = None,
    sdk_parity_report: dict[str, Any] | None = None,
    batch_plan_report: dict[str, Any] | None = None,
    semantic_harness_report: dict[str, Any] | None = None,
    regression_replay_report: dict[str, Any] | None = None,
    evidence_readiness_report: dict[str, Any] | None = None,
    releasefoundry_case_map: dict[str, Any] | None = None,
    semantic_collection_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize A2's commercial-grade readiness from deterministic fixtures."""
    coverage_report = _as_dict(coverage_report)
    calibration_matrix = _as_dict(calibration_matrix)
    case_book_report = _as_dict(case_book_report)
    sdk_parity_report = _as_dict(sdk_parity_report)
    batch_plan_report = _as_dict(batch_plan_report)
    semantic_harness_report = _as_dict(semantic_harness_report)
    regression_replay_report = _as_dict(regression_replay_report)
    evidence_readiness_report = _as_dict(evidence_readiness_report)
    evidence_readiness_integrity_verified = False
    try:
        verify_evidence_readiness_artifact(
            evidence_readiness_report,
            calibration_matrix=calibration_matrix,
            batch_plan_report=batch_plan_report,
            semantic_harness_report=semantic_harness_report,
            releasefoundry_case_map=releasefoundry_case_map,
            semantic_collection_packet=semantic_collection_packet,
        )
        evidence_readiness_integrity_verified = True
    except (TypeError, ValueError):
        pass
    regression_replay_integrity_verified = False
    try:
        verify_regression_replay_artifact(
            regression_replay_report,
            calibration_matrix=calibration_matrix,
            case_book_report=case_book_report,
        )
        regression_replay_integrity_verified = True
    except (OSError, TypeError, ValueError, KeyError):
        pass

    coverage_stable = _coverage_stable(coverage_report)
    source_coverage = _as_dict(calibration_matrix.get("source_coverage"))
    releasefoundry_available = _source_available(source_coverage, "releasefoundry_grading")
    releasefoundry_missing = _source_missing(source_coverage, "releasefoundry_grading")
    releasefoundry_ratio = _source_ratio(source_coverage, "releasefoundry_grading")
    llm_ratio = _source_ratio(source_coverage, "llm_judge")
    cost_ledger_present = _cost_ledger_present(calibration_matrix)
    llm_cost_ready = _llm_cost_ready(calibration_matrix)
    llm_confidence_ready = _llm_confidence_ready(calibration_matrix)
    llm_is_offline_only = _llm_is_offline_only(calibration_matrix)
    agreement_summary = _as_dict(calibration_matrix.get("agreement_summary"))
    local_llm_agreement = _as_dict(agreement_summary.get("local_vs_llm_judge"))
    local_llm_mismatches = _non_negative_int(
        local_llm_agreement.get("mismatch_count")
    )
    has_regression_candidates = any(
        "judge_disagreement_regression" in _string_list(case.get("calibration_tags"))
        for case in _dict_rows(calibration_matrix.get("cases"))
    )
    case_book_count = _non_negative_int(case_book_report.get("regression_case_count"))
    sdk_parity_passed = _explicit_true(sdk_parity_report.get("parity_passed"))
    sdk_language_count = _non_negative_int(sdk_parity_report.get("sdk_language_count"))
    batch_plan_ready = _explicit_true(batch_plan_report.get("plan_ready"))
    planned_batch_count = _non_negative_int(batch_plan_report.get("batch_count"))
    semantic_harness_ready = _explicit_true(semantic_harness_report.get("harness_ready"))
    semantic_live_evidence = _explicit_true(semantic_harness_report.get("live_model_evidence_available"))
    regression_replay_ready = (
        regression_replay_integrity_verified
        and _explicit_true(regression_replay_report.get("replay_ready"))
    )
    regression_replay_count = _non_negative_int(regression_replay_report.get("replay_case_count"))
    regression_replay_maturity = (
        _string_value(regression_replay_report.get("maturity_status"), "missing")
        if regression_replay_integrity_verified
        else "invalid"
    )
    evidence_readiness_ready = (
        evidence_readiness_integrity_verified
        and _explicit_true(evidence_readiness_report.get("ready_for_external_collection"))
    )
    a1_real_api_evidence = _as_dict(evidence_readiness_report.get("a1_real_api_evidence"))
    real_quota_gate = _as_dict(a1_real_api_evidence.get("real_quota_gate"))
    official_sdk_smoke = _as_dict(evidence_readiness_report.get("official_sdk_smoke"))
    releasefoundry_public_merge_gate = _as_dict(evidence_readiness_report.get("releasefoundry_public_merge_gate"))
    releasefoundry_public_merge_status = _string_value(releasefoundry_public_merge_gate.get("status"), "unknown")
    releasefoundry_public_matrix_merged = _explicit_true(releasefoundry_public_merge_gate.get("public_matrix_merged"))
    releasefoundry_safe_to_mark_c3_met = (
        evidence_readiness_integrity_verified
        and _explicit_true(releasefoundry_public_merge_gate.get("safe_to_mark_c3_met"))
    )
    releasefoundry_public_missing = _non_negative_int(
        releasefoundry_public_merge_gate.get("missing_public_observation_count"),
        default=releasefoundry_missing,
    )
    semantic_live_merge_gate = _as_dict(evidence_readiness_report.get("semantic_live_merge_gate"))
    semantic_live_merge_status = _string_value(semantic_live_merge_gate.get("status"), "unknown")
    semantic_audited_live_evidence_merged = _explicit_true(
        semantic_live_merge_gate.get("audited_live_evidence_merged")
    )
    semantic_safe_to_mark_c4_met = (
        evidence_readiness_integrity_verified
        and _explicit_true(semantic_live_merge_gate.get("safe_to_mark_c4_met"))
    )
    semantic_missing_audited = _non_negative_int(
        semantic_live_merge_gate.get("missing_audited_observation_count")
    )
    semantic_risk = _as_dict(semantic_harness_report.get("risk_assessment"))
    semantic_false_positive_tracking_ready = _explicit_true(semantic_risk.get("tracking_ready"))
    semantic_risk_status = _string_value(semantic_risk.get("status"), "unknown")
    semantic_false_positive_candidates = _non_negative_int(
        semantic_risk.get("false_positive_candidate_count")
    )
    semantic_false_negative_candidates = _non_negative_int(
        semantic_risk.get("false_negative_candidate_count")
    )
    semantic_failure_class_drift_candidates = _non_negative_int(
        semantic_risk.get("failure_class_drift_candidate_count")
    )
    semantic_score_delta_reviews = _non_negative_int(semantic_risk.get("score_delta_review_count"))
    semantic_risk_case_count = _non_negative_int(semantic_risk.get("risk_case_count"))
    real_api_total_records = _non_negative_int(a1_real_api_evidence.get("total_records"))
    real_api_record_count = _non_negative_int(a1_real_api_evidence.get("real_record_count"))
    real_api_status_counts = _as_dict(a1_real_api_evidence.get("real_read_status_counts"))
    real_api_read_ok_count = _non_negative_int(real_api_status_counts.get("ok"))
    real_api_quota_block_count = _non_negative_int(a1_real_api_evidence.get("quota_block_count"))
    official_sdk_smoke_ok_count = _non_negative_int(official_sdk_smoke.get("ok_call_count"))
    official_sdk_smoke_error_count = _non_negative_int(official_sdk_smoke.get("error_call_count"))

    gates = [
        _gate(
            "C0",
            "Baseline stable",
            "coverage/golden/executable fixtures do not regress",
            coverage_stable,
            False,
            [
                "coverage_report.meets_assignment_minimums",
                "coverage_report.coverage_warnings",
                "coverage_report.scenario_quality_warnings",
            ],
            [] if coverage_stable else ["Restore assignment, coverage, or scenario-quality checks."],
        ),
        _gate(
            "C1",
            "SDK runner consumption",
            "scenario outputs can be consumed through both Python and TypeScript SDK runner contracts",
            coverage_stable and sdk_parity_passed,
            coverage_stable or sdk_language_count > 0,
            [
                "tests/a2/test_contracts.py::test_runner_accepts_a1_agent_output_shape",
                "tests/a2/test_contracts.py::test_runner_accepts_a1_case_result_shape_and_case_id",
                "fixtures/a2/results/a2_sdk_parity_report.json",
            ],
            []
            if sdk_parity_passed
            else ["Add Python and TypeScript SDK parity evidence for A2 runner consumption."],
        ),
        _gate(
            "C2",
            "Batch plan and cost ledger",
            "batch generation plan and judge cost ledger exist",
            cost_ledger_present and batch_plan_ready,
            cost_ledger_present or planned_batch_count > 0,
            [
                "fixtures/a2/results/a2_g3_calibration_matrix.json::cost_ledger",
                "fixtures/a2/results/a2_batch_plan_report.json",
            ],
            [] if batch_plan_ready else ["Add a real quota-aware batch generation plan tied to A1 request/run evidence."],
        ),
        _gate(
            "C3",
            "Paid batch calibration",
            "ReleaseFoundry grading diff and LLM judge diff are both comparable",
            releasefoundry_ratio == 1.0 and llm_ratio == 1.0 and releasefoundry_safe_to_mark_c3_met,
            llm_ratio > 0 or releasefoundry_available > 0,
            [
                "calibration_matrix.agreement_summary.local_vs_releasefoundry_grading",
                "calibration_matrix.agreement_summary.local_vs_llm_judge",
                "fixtures/a2/results/a2_evidence_readiness_report.json",
            ],
            _c3_gaps(releasefoundry_missing, releasefoundry_public_merge_status, releasefoundry_safe_to_mark_c3_met),
        ),
        _gate(
            "C4",
            "Semantic judge",
            "semantic/LLM judge evidence includes cost, confidence, false-positive tracking, and model provenance",
            llm_cost_ready
            and llm_confidence_ready
            and semantic_live_evidence
            and not llm_is_offline_only
            and semantic_false_positive_tracking_ready
            and semantic_safe_to_mark_c4_met,
            llm_cost_ready and llm_confidence_ready and semantic_harness_ready and semantic_false_positive_tracking_ready,
            [
                "calibration_matrix.cost_ledger",
                "calibration_matrix.cases[].sources.llm_judge.confidence",
                "calibration_matrix.cases[].calibration_tags",
                "fixtures/a2/results/a2_semantic_harness_report.json",
                "fixtures/a2/results/a2_semantic_harness_report.json::risk_assessment",
                "fixtures/a2/results/a2_evidence_readiness_report.json",
            ],
            _c4_gaps(
                llm_is_offline_only,
                semantic_harness_ready,
                semantic_live_evidence,
                semantic_live_merge_status,
                semantic_safe_to_mark_c4_met,
                semantic_false_positive_tracking_ready,
            ),
        ),
        _gate(
            "C5",
            "Case book and regression suite",
            "judge disagreements become durable regression fixtures and a reviewer-facing case book",
            regression_replay_ready and regression_replay_maturity == "mature",
            has_regression_candidates
            and (case_book_count > 0 or regression_replay_integrity_verified),
            [
                "calibration_tags.judge_disagreement_regression",
                "fixtures/a2/results/a2_case_book.json",
                "fixtures/a2/results/a2_regression_replay_report.json",
            ],
            _c5_gaps(
                case_book_count,
                regression_replay_ready,
                regression_replay_maturity,
                regression_replay_integrity_verified,
            ),
        ),
        _gate(
            "C6",
            "Final hardening",
            "scoring boundaries, approximation boundaries, budgets, and evidence safety are final-deliverable ready",
            False,
            coverage_stable and llm_cost_ready,
            ["docs/a2/failure_taxonomy_v0.md", "docs/a2/scenario_coverage_plan.md"],
            ["Finish boundary docs after C3-C5 evidence is no longer partial."],
        ),
    ]

    return {
        "schema_version": "a2.commercial_readiness.v1",
        "report_id": "a2_commercial_readiness",
        "source_goal": {
            "artifact": COMMERCIAL_GOAL_SOURCE,
            "a2_summary": "Scenario, Judge, and open-ended semantic evaluation commercial growth.",
            "success_sentence": (
                "The clone can fail real agents for the right reasons and explain those reasons "
                "under calibration evidence."
            ),
        },
        "current_gate": _current_gate(gates),
        "ready_for_commercial_gate": False,
        "commercial_dimensions": _commercial_dimensions(
            coverage_stable=coverage_stable,
            releasefoundry_ratio=releasefoundry_ratio,
            llm_ratio=llm_ratio,
            llm_cost_ready=llm_cost_ready,
            llm_is_offline_only=llm_is_offline_only,
            has_regression_candidates=has_regression_candidates,
        ),
        "contract_invariants": _contract_invariants(),
        "scope_boundary": _scope_boundary(
            coverage_stable=coverage_stable,
            sdk_parity_passed=sdk_parity_passed,
            batch_plan_ready=batch_plan_ready,
            evidence_readiness_ready=evidence_readiness_ready,
        ),
        "gate_status": gates,
        "evidence_snapshot": {
            "assignment_minimums_green": _explicit_true(coverage_report.get("meets_assignment_minimums")),
            "scenario_count": _non_negative_int(coverage_report.get("scenario_count")),
            "golden_case_count": _non_negative_int(coverage_report.get("golden_case_count")),
            "executable_run_case_count": _non_negative_int(
                coverage_report.get("executable_run_case_count")
            ),
            "failure_class_count": len(_string_list(coverage_report.get("required_failure_classes_covered"))),
            "calibration_case_count": _non_negative_int(calibration_matrix.get("case_count")),
            "releasefoundry_grading_available": releasefoundry_available,
            "releasefoundry_grading_missing": releasefoundry_missing,
            "releasefoundry_public_merge_status": releasefoundry_public_merge_status,
            "releasefoundry_public_matrix_merged": releasefoundry_public_matrix_merged,
            "releasefoundry_safe_to_mark_c3_met": releasefoundry_safe_to_mark_c3_met,
            "releasefoundry_public_missing_observations": releasefoundry_public_missing,
            "llm_judge_coverage_ratio": llm_ratio,
            "llm_judge_offline_only": llm_is_offline_only,
            "local_vs_llm_mismatch_count": local_llm_mismatches,
            "case_book_regression_count": case_book_count,
            "regression_replay_count": regression_replay_count,
            "regression_replay_integrity_verified": regression_replay_integrity_verified,
            "regression_replay_ready": regression_replay_ready,
            "regression_replay_maturity": regression_replay_maturity,
            "evidence_readiness_integrity_verified": evidence_readiness_integrity_verified,
            "evidence_readiness_ready": evidence_readiness_ready,
            "real_api_evidence_available": _explicit_true(a1_real_api_evidence.get("available")),
            "real_api_total_records": real_api_total_records,
            "real_api_record_count": real_api_record_count,
            "real_api_read_ok_count": real_api_read_ok_count,
            "real_api_quota_block_count": real_api_quota_block_count,
            "real_api_create_request_blocked": _explicit_true(real_quota_gate.get("create_request_blocked")),
            "official_sdk_smoke_read_only_reachable": _explicit_true(
                official_sdk_smoke.get("read_only_reachable")
            ),
            "official_sdk_smoke_ok_call_count": official_sdk_smoke_ok_count,
            "official_sdk_smoke_error_call_count": official_sdk_smoke_error_count,
            "sdk_language_count": sdk_language_count,
            "sdk_parity_passed": sdk_parity_passed,
            "planned_batch_count": planned_batch_count,
            "batch_plan_ready": batch_plan_ready,
            "semantic_harness_ready": semantic_harness_ready,
            "semantic_harness_live_evidence": semantic_live_evidence,
            "semantic_live_merge_status": semantic_live_merge_status,
            "semantic_audited_live_evidence_merged": semantic_audited_live_evidence_merged,
            "semantic_safe_to_mark_c4_met": semantic_safe_to_mark_c4_met,
            "semantic_missing_audited_observations": semantic_missing_audited,
            "semantic_risk_assessment_status": semantic_risk_status,
            "semantic_false_positive_tracking_ready": semantic_false_positive_tracking_ready,
            "semantic_false_positive_candidates": semantic_false_positive_candidates,
            "semantic_false_negative_candidates": semantic_false_negative_candidates,
            "semantic_failure_class_drift_candidates": semantic_failure_class_drift_candidates,
            "semantic_score_delta_reviews": semantic_score_delta_reviews,
            "semantic_risk_case_count": semantic_risk_case_count,
        },
        "next_top_3": _next_top_3(
            releasefoundry_missing=releasefoundry_missing,
            llm_is_offline_only=llm_is_offline_only,
            has_regression_candidates=has_regression_candidates,
        ),
        "growth_auditor": _growth_auditor(
            releasefoundry_missing=releasefoundry_missing,
            llm_is_offline_only=llm_is_offline_only,
            semantic_live_evidence=semantic_live_evidence,
            case_book_count=case_book_count,
            regression_replay_maturity=regression_replay_maturity,
            real_api_record_count=real_api_record_count,
        ),
        "metadata": {
            "deterministic": True,
            "inputs": [
                "fixtures/a2/results/a2_g3_coverage_report.json",
                "fixtures/a2/results/a2_g3_calibration_matrix.json",
                "fixtures/a2/results/a2_sdk_parity_report.json",
                "fixtures/a2/results/a2_batch_plan_report.json",
                "fixtures/a2/results/a2_semantic_harness_report.json",
                "fixtures/a2/results/a2_regression_replay_report.json",
                "fixtures/a2/results/a2_evidence_readiness_report.json",
            ],
            "notes": [
                "This report encodes the July 4 commercial goal PDF as a deterministic A2 planning artifact.",
                "It is a readiness overlay and does not replace the A2 grade, coverage, or calibration schemas.",
            ],
        },
    }


def _contract_invariants() -> list[str]:
    return [
        "grade_run remains deterministic and local; live ReleaseFoundry or LLM calls enter calibration/readiness only.",
        "a2.grade_results.v1 required fields, 0-100 score scale, and case_id join remain stable.",
        "top-level primary_failure_class remains one of the canonical A2 failure classes or none.",
        "calibration sources remain local_judge, releasefoundry_grading, and llm_judge.",
        "new commercial artifacts are additive and optional for A3 consumers.",
    ]


def _scope_boundary(
    *,
    coverage_stable: bool,
    sdk_parity_passed: bool,
    batch_plan_ready: bool,
    evidence_readiness_ready: bool,
) -> dict[str, Any]:
    guardrails = [
        {
            "id": "a2_grade_contract_stable",
            "status": "met" if coverage_stable else "blocked",
            "evidence_ref": "fixtures/a2/results/a2_g3_grade_results.json",
        },
        {
            "id": "a1_runner_boundary",
            "status": "met" if sdk_parity_passed else "partial",
            "evidence_ref": "fixtures/a2/results/a2_sdk_parity_report.json",
        },
        {
            "id": "a3_optional_feed_boundary",
            "status": "met" if batch_plan_ready and evidence_readiness_ready else "partial",
            "evidence_ref": "services/report/report_builder.mjs optional A2 fixture loaders",
        },
        {
            "id": "external_evidence_boundary",
            "status": "met" if evidence_readiness_ready else "partial",
            "evidence_ref": "fixtures/a2/results/a2_evidence_readiness_report.json",
        },
    ]
    return {
        "status": "controlled" if all(item["status"] == "met" for item in guardrails) else "watch",
        "why_a2_is_larger": (
            "A2 owns scenario definitions, deterministic judges, calibration fixtures, and evidence gates; "
            "those artifacts are intentionally test-heavy so A1/A3 can consume stable results."
        ),
        "a2_owned": [
            "scenario, rubric, judge, golden case, and failure taxonomy contracts",
            "deterministic local grading and executable calibration fixtures",
            "calibration, evidence readiness, case-book, and commercial-readiness feeds",
            "A1/A3 handoff contracts for runner output and report input shapes",
        ],
        "delegated_to_a1": [
            "hosted ReleaseFoundry run execution and queue/runtime behavior",
            "raw SDK calls, account authentication, and private API payload collection",
            "cloud worker or TypeScript runtime implementation details",
        ],
        "delegated_to_a3": [
            "dashboard UI, report layout, filtering, and presentation UX",
            "cross-run visual analysis and final stakeholder export packaging",
        ],
        "allowed_growth": [
            "additive schema fields that improve auditability without changing grade-result joins",
            "deterministic fixtures and tests that prove existing judge behavior",
            "evidence gates that prevent unreviewed external data from being counted as complete",
        ],
        "blocked_growth": [
            "live ReleaseFoundry or LLM calls inside deterministic local tests",
            "A1 runner orchestration or A3 dashboard ownership inside A2 modules",
            "breaking changes to a2.grade_results.v1 without coordinated A1/A3 migration",
        ],
        "guardrails": guardrails,
    }


def _growth_auditor(
    *,
    releasefoundry_missing: int,
    llm_is_offline_only: bool,
    semantic_live_evidence: bool,
    case_book_count: int,
    regression_replay_maturity: str,
    real_api_record_count: int,
) -> dict[str, Any]:
    growth_points = _growth_points()
    return {
        "auditor_id": "a2_money_grade_auditor",
        "audit_basis": "docs/strategy/large-saas-a1-a2-a3-full-plan.md",
        "money_direction": {
            "primary": "release_gate_with_reviewed_evidence_and_regression_replay",
            "secondary": [
                "official_grading_diff",
                "semantic_judge_calibration",
                "production_incident_to_regression",
                "enterprise_audit_export",
            ],
            "why": (
                "The highest willingness-to-pay path is blocking risky agent releases with "
                "reviewable evidence, replayable failures, and approval records."
            ),
        },
        "new_sellable_capabilities": [
            "internal judge service boundary for case, batch, and release policy evaluation",
            "project-aware scenario selection for tenant/project risk profiles",
            "public-safe result persistence with input/output hashes",
            "release policy waiver audit fields for approval workflow integration",
            "C3/C4/C5 evidence gates that prevent unreviewed data from being counted as complete",
        ],
        "toy_risks_to_upgrade": [
            "offline llm_judge rows are useful references but cannot sell as audited semantic evidence",
            "case-book regression suite is still seed maturity, not enterprise incident coverage",
            "server-side ReleaseFoundry grading column is prepared but still missing reviewed public rows",
            "service wrapper is deterministic library code until A1 mounts it behind worker/API infrastructure",
        ],
        "customer_payment_drivers": [
            "fail PR/release gates before unsafe or hallucinated agent behavior ships",
            "turn judge disagreements and production incidents into durable regression tests",
            "show managers and auditors a public-safe chain from case to evidence to approval",
            "support different project/environment policies without forking judge code",
        ],
        "enterprise_readiness": {
            "audit": "public summaries keep private evidence refs without raw payloads",
            "self_host": "deterministic local judging has no network dependency",
            "compliance": "C3/C4 gates require reviewed evidence before commercial claims",
            "current_gaps": [
                f"{releasefoundry_missing} ReleaseFoundry grading calibration rows still need reviewed evidence",
                "semantic judge evidence is still offline-only"
                if llm_is_offline_only
                else "semantic judge evidence needs more live samples",
                f"case book has {case_book_count} regression case(s) and maturity={regression_replay_maturity}",
            ],
        },
        "current_evidence_strength": {
            "real_api_record_count": real_api_record_count,
            "semantic_live_evidence_available": semantic_live_evidence,
            "releasefoundry_missing_reviewed_observations": releasefoundry_missing,
            "growth_point_count": len(growth_points),
        },
        "parallel_growth_points": growth_points,
        "parallelization": {
            "must_parallelize": True,
            "tracks": sorted({point["parallel_track"] for point in growth_points}),
            "integration_rule": (
                "A2 may add public-safe reports and additive schema fields; "
                "A1 owns hosted execution and A3 owns UI."
            ),
        },
    }


def _growth_points() -> list[dict[str, Any]]:
    return [
        _growth_point(
            "official_grading_diff_import",
            "Import six reviewed ReleaseFoundry server-side grading rows into calibration.",
            "calibration",
            "Customers trust gates more when local failures match official grading.",
            "fixtures/a2/calibration/a2_g3_calibration_observations.json",
        ),
        _growth_point(
            "semantic_live_judge_audit",
            "Replace offline llm_judge references with audited live model-call summaries.",
            "calibration",
            "Audited semantic evidence supports high-value false-positive review.",
            "fixtures/a2/results/a2_semantic_harness_report.json",
        ),
        _growth_point(
            "production_incident_to_regression",
            "Convert incident summaries into reviewed regression candidates.",
            "regression",
            "Incident replay is a direct enterprise painkiller after agent failures.",
            "fixtures/a2/results/a2_case_book.json",
        ),
        _growth_point(
            "failure_cluster_report",
            "Group failures by class, scenario family, SDK language, and owner role.",
            "intelligence",
            "Teams pay for root-cause grouping, not only pass/fail rows.",
            "fixtures/a2/results/a2_g3_grade_results.json",
        ),
        _growth_point(
            "reviewer_feedback_queue",
            "Capture judge override, waiver, and reviewer notes as calibration inputs.",
            "workflow",
            "Human review feedback makes the judge improve with customer use.",
            "fixtures/a2/results/a2_release_gate_report.json",
        ),
        _growth_point(
            "enterprise_policy_templates",
            "Ship prod, staging, regulated, and experimental release policy templates.",
            "policy",
            "Per-team policy templates increase enterprise fit and deal size.",
            "fixtures/a2/config/release_policies.json",
        ),
        _growth_point(
            "approval_chain_export",
            "Expose waiver approvals, reviewers, reasons, and evidence refs in reports.",
            "workflow",
            "Managers need sign-off history before accepting release gates.",
            "fixtures/a2/results/a2_release_gate_report.json",
        ),
        _growth_point(
            "judge_version_comparison",
            "Compare policy, taxonomy, scenario, and judge versions across runs.",
            "intelligence",
            "Versioned judge history answers why scores changed after upgrades.",
            "fixtures/a2/results/a2_result_persistence_manifest.json",
        ),
        _growth_point(
            "flaky_case_detection",
            "Mark cases that disagree across local, official, and semantic judges.",
            "calibration",
            "Flaky-case isolation lowers false block risk for paying teams.",
            "fixtures/a2/results/a2_g3_calibration_matrix.json",
        ),
        _growth_point(
            "media_eval_expansion",
            "Expand media/tool-output grounding beyond the current A2-S031 seed.",
            "scenario",
            "Media-capable agent products need image and artifact evidence checks.",
            "fixtures/a2/results/a2_g3_coverage_report.json",
        ),
        _growth_point(
            "api_error_shape_fixture",
            "Capture official API error/quota/status shapes as public-safe fixtures.",
            "evidence",
            "Real error semantics make the clone more faithful than guesses.",
            "docs/a1/api_calibration/real_api_evidence_index.json",
        ),
        _growth_point(
            "cost_ledger_per_tenant",
            "Break judge and semantic cost ledger down by tenant/project/run.",
            "billing",
            "Usage-based billing needs per-tenant cost and volume evidence.",
            "fixtures/a2/results/a2_batch_plan_report.json",
        ),
        _growth_point(
            "scenario_pack_marketplace",
            "Define industry packs with owners, difficulty, tags, and review status.",
            "scenario",
            "Pack libraries turn A2 from static tests into configurable product inventory.",
            "packages/scenarios/a2_g3_full_pack.json",
        ),
        _growth_point(
            "a3_dashboard_contract",
            "Publish A2 dashboard-ready fields for gates, waivers, regressions, and costs.",
            "integration",
            "A3 can sell the workflow only if A2 outputs stable product data.",
            "docs/a2/schemas",
        ),
        _growth_point(
            "self_host_evidence_bundle",
            "Produce a self-host bundle with deterministic checks and no API dependency.",
            "enterprise",
            "Enterprise buyers often need self-host or offline verification.",
            "scripts/a2_local_lite_check.py",
        ),
        _growth_point(
            "pr_gate_annotations",
            "Make release gate blockers actionable as PR annotations with owner hints.",
            "workflow",
            "PR gates enter the customer's release workflow where budget is justified.",
            "fixtures/a2/results/a2_release_gate_report.json",
        ),
        _growth_point(
            "calibration_drift_report",
            "Track precision, recall, mismatch, and drift by failure class over time.",
            "calibration",
            "Judge quality metrics reduce buyer fear of false positives.",
            "fixtures/a2/results/a2_g3_calibration_matrix.json",
        ),
        _growth_point(
            "golden_case_promotion",
            "Promote reviewed failures into golden cases with reviewer status.",
            "regression",
            "Customer incidents become compounding regression assets.",
            "fixtures/golden/a2_g2_golden_cases.json",
        ),
        _growth_point(
            "private_evidence_redaction_gate",
            "Block public merges unless evidence refs are reviewed and raw payloads stay private.",
            "evidence",
            "Compliance requires proof that secrets and account payloads are not leaked.",
            "fixtures/a2/results/a2_evidence_readiness_report.json",
        ),
        _growth_point(
            "typescript_python_parity_gate",
            "Keep Python and TypeScript SDK chains visible in every C3/C4 evidence path.",
            "integration",
            "Dual SDK parity matters because official ReleaseFoundry exposes both languages.",
            "fixtures/a2/results/a2_sdk_parity_report.json",
        ),
    ]


def _growth_point(
    point_id: str,
    title: str,
    parallel_track: str,
    commercial_value: str,
    evidence_ref: str,
) -> dict[str, Any]:
    return {
        "id": point_id,
        "title": title,
        "parallel_track": parallel_track,
        "commercial_value": commercial_value,
        "evidence_ref": evidence_ref,
        "required_artifact_type": "code_or_test_or_fixture_or_schema_or_evidence",
    }


def _coverage_stable(report: dict[str, Any]) -> bool:
    return (
        _explicit_true(report.get("meets_assignment_minimums"))
        and report.get("coverage_warnings") == []
        and report.get("scenario_quality_warnings") == []
    )


def _source_available(source_coverage: dict[str, Any], source: str) -> int:
    return _non_negative_int(_as_dict(source_coverage.get(source)).get("available"))


def _source_missing(source_coverage: dict[str, Any], source: str) -> int:
    return _non_negative_int(_as_dict(source_coverage.get(source)).get("missing"))


def _source_ratio(source_coverage: dict[str, Any], source: str) -> float:
    value = _finite_number(_as_dict(source_coverage.get(source)).get("coverage_ratio"))
    return value if value is not None and 0.0 <= value <= 1.0 else 0.0


def _cost_ledger_present(matrix: dict[str, Any]) -> bool:
    ledger = matrix.get("cost_ledger")
    return isinstance(ledger, list) and any(isinstance(row, dict) for row in ledger)


def _llm_cost_ready(matrix: dict[str, Any]) -> bool:
    for row in _dict_rows(matrix.get("cost_ledger")):
        if row.get("source") == "llm_judge":
            estimated_usd = _finite_number(row.get("estimated_usd"))
            return (
                _non_negative_int(row.get("sample_count")) > 0
                and estimated_usd is not None
                and estimated_usd > 0.0
            )
    return False


def _llm_confidence_ready(matrix: dict[str, Any]) -> bool:
    llm_sources = []
    for case in _dict_rows(matrix.get("cases")):
        source = _as_dict(_as_dict(case.get("sources")).get("llm_judge"))
        if _explicit_true(source.get("available")):
            llm_sources.append(source)
    return bool(llm_sources) and all(
        (confidence := _finite_number(source.get("confidence"))) is not None
        and 0.0 <= confidence <= 1.0
        for source in llm_sources
    )


def _llm_is_offline_only(matrix: dict[str, Any]) -> bool:
    providers = set()
    for row in _dict_rows(matrix.get("cost_ledger")):
        if row.get("source") == "llm_judge":
            providers.update(str(provider) for provider in _as_dict(row.get("provider_counts")))
    return providers == {"offline_reference"}


def _explicit_true(value: Any) -> bool:
    return value is True


def _non_negative_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return default
    return value


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_value(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _gate(
    gate_id: str,
    name: str,
    requirement: str,
    met: bool,
    partial: bool,
    evidence_refs: list[str],
    gaps: list[str],
) -> dict[str, Any]:
    status = "met" if met else "partial" if partial else "blocked"
    return {
        "gate": gate_id,
        "name": name,
        "status": status,
        "requirement": requirement,
        "evidence_refs": evidence_refs,
        "gaps": gaps,
    }


def _c4_gaps(
    llm_is_offline_only: bool,
    semantic_harness_ready: bool,
    semantic_live_evidence: bool,
    semantic_live_merge_status: str = "unknown",
    semantic_safe_to_mark_c4_met: bool = False,
    semantic_false_positive_tracking_ready: bool = False,
) -> list[str]:
    gaps = []
    if not semantic_harness_ready:
        gaps.append("Add a semantic judge harness with prompt, output schema, cost, redaction, and SDK-chain coverage.")
    if not semantic_false_positive_tracking_ready:
        gaps.append("Add semantic judge false-positive/false-negative risk tracking before using C4 evidence.")
    if llm_is_offline_only or not semantic_live_evidence:
        gaps.append(
            "Replace offline llm_judge references by running the semantic harness with audited live model calls and prompt/model/cost metadata."
        )
    if not semantic_safe_to_mark_c4_met:
        gaps.append(
            f"Semantic live merge gate is {semantic_live_merge_status}; import audited semantic judge summaries before marking C4 met."
        )
    return gaps


def _c3_gaps(releasefoundry_missing: int, releasefoundry_public_merge_status: str, releasefoundry_safe_to_mark_c3_met: bool) -> list[str]:
    gaps = []
    if releasefoundry_missing:
        gaps.append(f"Collect reviewed ReleaseFoundry grading observations for {releasefoundry_missing} missing calibration cases.")
    if not releasefoundry_safe_to_mark_c3_met:
        gaps.append(
            f"Public ReleaseFoundry grading merge gate is {releasefoundry_public_merge_status}; import, merge, and regenerate before marking C3 met."
        )
    return gaps


def _c5_gaps(
    case_book_count: int,
    regression_replay_ready: bool,
    regression_replay_maturity: str,
    regression_replay_integrity_verified: bool,
) -> list[str]:
    gaps = []
    if case_book_count == 0:
        gaps.append("Promote local-vs-LLM disagreements into regression fixtures and write the case book.")
    if not regression_replay_integrity_verified:
        gaps.append(
            "Rebuild regression replay from the current calibration matrix and case book before using it for C5."
        )
    if not regression_replay_ready:
        gaps.append("Add executable replay evidence for every case-book regression seed.")
    if regression_replay_maturity != "mature":
        gaps.append("Expand the case book beyond the current seed into a mature regression suite.")
    return gaps


def _current_gate(gates: list[dict[str, Any]]) -> str:
    current = "C0"
    for gate in gates:
        if gate["status"] == "met":
            current = gate["gate"]
            continue
        break
    return current


def _commercial_dimensions(
    *,
    coverage_stable: bool,
    releasefoundry_ratio: float,
    llm_ratio: float,
    llm_cost_ready: bool,
    llm_is_offline_only: bool,
    has_regression_candidates: bool,
) -> list[dict[str, Any]]:
    return [
        {
            "dimension": "operability",
            "weight": 25,
            "status": "met" if coverage_stable else "blocked",
            "evidence": "A2 deterministic fixtures, coverage, and local tests stay reproducible.",
        },
        {
            "dimension": "high_fidelity",
            "weight": 25,
            "status": "met" if releasefoundry_ratio == 1.0 and llm_ratio == 1.0 and not llm_is_offline_only else "partial",
            "evidence": "Calibration matrix compares local_judge, releasefoundry_grading, and llm_judge sources.",
            "gap": "ReleaseFoundry grading is missing or LLM evidence is offline-only.",
        },
        {
            "dimension": "product_workflow",
            "weight": 20,
            "status": "partial",
            "evidence": "A2 publishes coverage and calibration feeds for A3 dashboard/report consumption.",
            "gap": "Case book and product workflow evidence are not mature yet.",
        },
        {
            "dimension": "evaluation_quality",
            "weight": 20,
            "status": "partial" if has_regression_candidates or llm_cost_ready else "blocked",
            "evidence": "Judge disagreement candidates, confidence, and cost metadata are visible.",
            "gap": "Semantic judge harness is not yet backed by audited live model calls.",
        },
        {
            "dimension": "collaboration",
            "weight": 10,
            "status": "partial",
            "evidence": "A2 handoff docs and generated fixtures make A1/A3 integration explicit.",
            "gap": "Peer branch impact and PR readiness still need to be refreshed every round.",
        },
    ]


def _next_top_3(
    *,
    releasefoundry_missing: int,
    llm_is_offline_only: bool,
    has_regression_candidates: bool,
) -> list[dict[str, Any]]:
    candidates = [
        {
            "id": "fill_releasefoundry_grading_column",
            "title": "Collect and import a tiny reviewed ReleaseFoundry grading batch",
            "why_now": f"{releasefoundry_missing} calibration cases still lack server-side ReleaseFoundry grading evidence.",
            "scores": {
                "evaluation_value": 4,
                "calibration_value": 5,
                "false_positive_risk": 2,
                "contract_impact": 2,
                "effort": 3,
            },
            "smallest_delivery": [
                "private redacted get-run/list-runs evidence",
                "reviewed releasefoundry_grading observations",
                "merged calibration observations payload",
                "regenerated calibration matrix",
            ],
        },
        {
            "id": "audited_llm_judge_harness",
            "title": "Replace offline LLM references with audited semantic judge calls",
            "why_now": "C4 needs prompt/model/cost/confidence evidence instead of offline reference samples."
            if llm_is_offline_only
            else "LLM evidence is present; expand model matrix and prompt audit coverage.",
            "scores": {
                "evaluation_value": 5,
                "calibration_value": 4,
                "false_positive_risk": 3,
                "contract_impact": 2,
                "effort": 4,
            },
            "smallest_delivery": [
                "semantic judge prompt template",
                "model/cost ledger rows",
                "redacted eval evidence summary",
            ],
        },
        {
            "id": "promote_disagreement_regressions",
            "title": "Turn judge disagreements into regression fixtures and a case book seed",
            "why_now": "The matrix already exposes disagreement candidates."
            if has_regression_candidates
            else "The case book can start from high-risk calibration examples.",
            "scores": {
                "evaluation_value": 4,
                "calibration_value": 4,
                "false_positive_risk": 2,
                "contract_impact": 1,
                "effort": 2,
            },
            "smallest_delivery": [
                "regression fixture for the current local-vs-LLM mismatch",
                "case-book markdown entry",
                "test asserting the regression remains visible",
            ],
        },
    ]
    return candidates
