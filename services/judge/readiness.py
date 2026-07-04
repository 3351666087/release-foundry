"""Commercial readiness reporting for A2 evaluation artifacts."""

from __future__ import annotations

from typing import Any


COMMERCIAL_GOAL_SOURCE = "Ashr_Commercial_Grade_Goals_CN.pdf"


def build_commercial_readiness_report(
    coverage_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    case_book_report: dict[str, Any] | None = None,
    sdk_parity_report: dict[str, Any] | None = None,
    batch_plan_report: dict[str, Any] | None = None,
    semantic_harness_report: dict[str, Any] | None = None,
    regression_replay_report: dict[str, Any] | None = None,
    evidence_readiness_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize A2's commercial-grade readiness from deterministic fixtures."""
    coverage_stable = _coverage_stable(coverage_report)
    source_coverage = calibration_matrix.get("source_coverage", {})
    ashr_available = _source_available(source_coverage, "ashr_grading")
    ashr_missing = _source_missing(source_coverage, "ashr_grading")
    ashr_ratio = _source_ratio(source_coverage, "ashr_grading")
    llm_ratio = _source_ratio(source_coverage, "llm_judge")
    llm_cost_ready = _llm_cost_ready(calibration_matrix)
    llm_confidence_ready = _llm_confidence_ready(calibration_matrix)
    llm_is_offline_only = _llm_is_offline_only(calibration_matrix)
    local_llm_mismatches = calibration_matrix.get("agreement_summary", {}).get("local_vs_llm_judge", {}).get(
        "mismatch_count", 0
    )
    has_regression_candidates = any(
        "judge_disagreement_regression" in case.get("calibration_tags", [])
        for case in calibration_matrix.get("cases", [])
    )
    case_book_count = int((case_book_report or {}).get("regression_case_count", 0))
    sdk_parity_passed = bool((sdk_parity_report or {}).get("parity_passed"))
    sdk_language_count = int((sdk_parity_report or {}).get("sdk_language_count", 0))
    batch_plan_ready = bool((batch_plan_report or {}).get("plan_ready"))
    planned_batch_count = int((batch_plan_report or {}).get("batch_count", 0))
    semantic_harness_ready = bool((semantic_harness_report or {}).get("harness_ready"))
    semantic_live_evidence = bool((semantic_harness_report or {}).get("live_model_evidence_available"))
    regression_replay_ready = bool((regression_replay_report or {}).get("replay_ready"))
    regression_replay_count = int((regression_replay_report or {}).get("replay_case_count", 0))
    regression_replay_maturity = str((regression_replay_report or {}).get("maturity_status", "missing"))
    evidence_readiness_ready = bool((evidence_readiness_report or {}).get("ready_for_external_collection"))
    ashr_public_merge_gate = (evidence_readiness_report or {}).get("ashr_public_merge_gate", {})
    ashr_public_merge_status = str(ashr_public_merge_gate.get("status", "unknown"))
    ashr_public_matrix_merged = bool(ashr_public_merge_gate.get("public_matrix_merged"))
    ashr_safe_to_mark_c3_met = bool(ashr_public_merge_gate.get("safe_to_mark_c3_met"))
    ashr_public_missing = int(ashr_public_merge_gate.get("missing_public_observation_count", ashr_missing))
    semantic_live_merge_gate = (evidence_readiness_report or {}).get("semantic_live_merge_gate", {})
    semantic_live_merge_status = str(semantic_live_merge_gate.get("status", "unknown"))
    semantic_audited_live_evidence_merged = bool(semantic_live_merge_gate.get("audited_live_evidence_merged"))
    semantic_safe_to_mark_c4_met = bool(semantic_live_merge_gate.get("safe_to_mark_c4_met"))
    semantic_missing_audited = int(semantic_live_merge_gate.get("missing_audited_observation_count", 0))

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
            bool(calibration_matrix.get("cost_ledger")) and batch_plan_ready,
            bool(calibration_matrix.get("cost_ledger")) or planned_batch_count > 0,
            [
                "fixtures/a2/results/a2_g3_calibration_matrix.json::cost_ledger",
                "fixtures/a2/results/a2_batch_plan_report.json",
            ],
            [] if batch_plan_ready else ["Add a real quota-aware batch generation plan tied to A1 request/run evidence."],
        ),
        _gate(
            "C3",
            "Paid batch calibration",
            "Ashr grading diff and LLM judge diff are both comparable",
            ashr_ratio == 1.0 and llm_ratio == 1.0 and ashr_safe_to_mark_c3_met,
            llm_ratio > 0 or ashr_available > 0,
            [
                "calibration_matrix.agreement_summary.local_vs_ashr_grading",
                "calibration_matrix.agreement_summary.local_vs_llm_judge",
                "fixtures/a2/results/a2_evidence_readiness_report.json",
            ],
            _c3_gaps(ashr_missing, ashr_public_merge_status, ashr_safe_to_mark_c3_met),
        ),
        _gate(
            "C4",
            "Semantic judge",
            "semantic/LLM judge evidence includes cost, confidence, false-positive tracking, and model provenance",
            llm_cost_ready
            and llm_confidence_ready
            and semantic_live_evidence
            and not llm_is_offline_only
            and semantic_safe_to_mark_c4_met,
            llm_cost_ready and llm_confidence_ready and semantic_harness_ready,
            [
                "calibration_matrix.cost_ledger",
                "calibration_matrix.cases[].sources.llm_judge.confidence",
                "calibration_matrix.cases[].calibration_tags",
                "fixtures/a2/results/a2_semantic_harness_report.json",
                "fixtures/a2/results/a2_evidence_readiness_report.json",
            ],
            _c4_gaps(
                llm_is_offline_only,
                semantic_harness_ready,
                semantic_live_evidence,
                semantic_live_merge_status,
                semantic_safe_to_mark_c4_met,
            ),
        ),
        _gate(
            "C5",
            "Case book and regression suite",
            "judge disagreements become durable regression fixtures and a reviewer-facing case book",
            regression_replay_ready and regression_replay_maturity == "mature",
            has_regression_candidates and regression_replay_ready,
            [
                "calibration_tags.judge_disagreement_regression",
                "fixtures/a2/results/a2_case_book.json",
                "fixtures/a2/results/a2_regression_replay_report.json",
            ],
            _c5_gaps(case_book_count, regression_replay_ready, regression_replay_maturity),
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
            ashr_ratio=ashr_ratio,
            llm_ratio=llm_ratio,
            llm_cost_ready=llm_cost_ready,
            llm_is_offline_only=llm_is_offline_only,
            has_regression_candidates=has_regression_candidates,
        ),
        "contract_invariants": _contract_invariants(),
        "gate_status": gates,
        "evidence_snapshot": {
            "assignment_minimums_green": bool(coverage_report.get("meets_assignment_minimums")),
            "scenario_count": coverage_report.get("scenario_count", 0),
            "golden_case_count": coverage_report.get("golden_case_count", 0),
            "executable_run_case_count": coverage_report.get("executable_run_case_count", 0),
            "failure_class_count": len(coverage_report.get("required_failure_classes_covered", [])),
            "calibration_case_count": calibration_matrix.get("case_count", 0),
            "ashr_grading_available": ashr_available,
            "ashr_grading_missing": ashr_missing,
            "ashr_public_merge_status": ashr_public_merge_status,
            "ashr_public_matrix_merged": ashr_public_matrix_merged,
            "ashr_safe_to_mark_c3_met": ashr_safe_to_mark_c3_met,
            "ashr_public_missing_observations": ashr_public_missing,
            "llm_judge_coverage_ratio": llm_ratio,
            "llm_judge_offline_only": llm_is_offline_only,
            "local_vs_llm_mismatch_count": local_llm_mismatches,
            "case_book_regression_count": case_book_count,
            "regression_replay_count": regression_replay_count,
            "regression_replay_ready": regression_replay_ready,
            "regression_replay_maturity": regression_replay_maturity,
            "evidence_readiness_ready": evidence_readiness_ready,
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
        },
        "next_top_3": _next_top_3(
            ashr_missing=ashr_missing,
            llm_is_offline_only=llm_is_offline_only,
            has_regression_candidates=has_regression_candidates,
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
        "grade_run remains deterministic and local; live Ashr or LLM calls enter calibration/readiness only.",
        "a2.grade_results.v1 required fields, 0-100 score scale, and case_id join remain stable.",
        "top-level primary_failure_class remains one of the canonical A2 failure classes or none.",
        "calibration sources remain local_judge, ashr_grading, and llm_judge.",
        "new commercial artifacts are additive and optional for A3 consumers.",
    ]


def _coverage_stable(report: dict[str, Any]) -> bool:
    return (
        bool(report.get("meets_assignment_minimums"))
        and not report.get("coverage_warnings")
        and not report.get("scenario_quality_warnings")
    )


def _source_available(source_coverage: dict[str, Any], source: str) -> int:
    return int(source_coverage.get(source, {}).get("available", 0))


def _source_missing(source_coverage: dict[str, Any], source: str) -> int:
    return int(source_coverage.get(source, {}).get("missing", 0))


def _source_ratio(source_coverage: dict[str, Any], source: str) -> float:
    return float(source_coverage.get(source, {}).get("coverage_ratio", 0.0))


def _llm_cost_ready(matrix: dict[str, Any]) -> bool:
    for row in matrix.get("cost_ledger", []):
        if row.get("source") == "llm_judge":
            return int(row.get("sample_count", 0)) > 0 and float(row.get("estimated_usd", 0.0)) > 0
    return False


def _llm_confidence_ready(matrix: dict[str, Any]) -> bool:
    llm_sources = [
        case.get("sources", {}).get("llm_judge", {})
        for case in matrix.get("cases", [])
        if case.get("sources", {}).get("llm_judge", {}).get("available")
    ]
    return bool(llm_sources) and all(isinstance(source.get("confidence"), (int, float)) for source in llm_sources)


def _llm_is_offline_only(matrix: dict[str, Any]) -> bool:
    providers = set()
    for row in matrix.get("cost_ledger", []):
        if row.get("source") == "llm_judge":
            providers.update(str(provider) for provider in row.get("provider_counts", {}))
    return providers == {"offline_reference"}


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
) -> list[str]:
    gaps = []
    if not semantic_harness_ready:
        gaps.append("Add a semantic judge harness with prompt, output schema, cost, redaction, and SDK-chain coverage.")
    if llm_is_offline_only or not semantic_live_evidence:
        gaps.append(
            "Replace offline llm_judge references by running the semantic harness with audited live model calls and prompt/model/cost metadata."
        )
    if not semantic_safe_to_mark_c4_met:
        gaps.append(
            f"Semantic live merge gate is {semantic_live_merge_status}; import audited semantic judge summaries before marking C4 met."
        )
    return gaps


def _c3_gaps(ashr_missing: int, ashr_public_merge_status: str, ashr_safe_to_mark_c3_met: bool) -> list[str]:
    gaps = []
    if ashr_missing:
        gaps.append(f"Collect reviewed Ashr grading observations for {ashr_missing} missing calibration cases.")
    if not ashr_safe_to_mark_c3_met:
        gaps.append(
            f"Public Ashr grading merge gate is {ashr_public_merge_status}; import, merge, and regenerate before marking C3 met."
        )
    return gaps


def _c5_gaps(case_book_count: int, regression_replay_ready: bool, regression_replay_maturity: str) -> list[str]:
    gaps = []
    if case_book_count == 0:
        gaps.append("Promote local-vs-LLM disagreements into regression fixtures and write the case book.")
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
    ashr_ratio: float,
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
            "status": "met" if ashr_ratio == 1.0 and llm_ratio == 1.0 and not llm_is_offline_only else "partial",
            "evidence": "Calibration matrix compares local_judge, ashr_grading, and llm_judge sources.",
            "gap": "Ashr grading is missing or LLM evidence is offline-only.",
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
    ashr_missing: int,
    llm_is_offline_only: bool,
    has_regression_candidates: bool,
) -> list[dict[str, Any]]:
    candidates = [
        {
            "id": "fill_ashr_grading_column",
            "title": "Collect and import a tiny reviewed Ashr grading batch",
            "why_now": f"{ashr_missing} calibration cases still lack server-side Ashr grading evidence.",
            "scores": {
                "evaluation_value": 4,
                "calibration_value": 5,
                "false_positive_risk": 2,
                "contract_impact": 2,
                "effort": 3,
            },
            "smallest_delivery": [
                "private redacted get-run/list-runs evidence",
                "reviewed ashr_grading observations",
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
