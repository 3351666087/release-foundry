"""Release gate report for A2 commercial readiness artifacts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


HARD_GATES = ("C0", "C1", "C2", "C3", "C4", "C5")
A1_EVIDENCE_INDEX_REF = "docs/a1/api_calibration/real_api_evidence_index.json"
OUTPUT_POLICY_BLOCKING_COUNTERS = (
    "unsafe_real_nonprivate_override",
    "private_required_but_not_private",
)


def build_release_gate_report(
    commercial_readiness_report: dict[str, Any],
    evidence_readiness_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    regression_replay_report: dict[str, Any] | None = None,
    scenario_selection_report: dict[str, Any] | None = None,
    a1_evidence_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert readiness evidence into a machine-readable PR/release gate."""
    gates = {str(gate.get("gate", "")): gate for gate in commercial_readiness_report.get("gate_status", [])}
    blocking_gates = [
        _gate_blocker(gate_id, gates.get(gate_id, {}))
        for gate_id in HARD_GATES
        if gates.get(gate_id, {}).get("status") != "met"
    ]
    blocking_gates = [item for item in blocking_gates if item]
    evidence_blockers = _evidence_blockers(evidence_readiness_report, calibration_matrix, regression_replay_report or {})
    scenario_selection_gate = _scenario_selection_gate(scenario_selection_report or {})
    scenario_selection_blockers = _scenario_selection_blockers(scenario_selection_gate)
    a1_output_policy_gate = build_a1_output_policy_gate(a1_evidence_index)
    output_policy_blockers = _a1_output_policy_blockers(a1_output_policy_gate)
    blockers = blocking_gates + evidence_blockers + scenario_selection_blockers + output_policy_blockers
    warnings = _warnings(commercial_readiness_report, evidence_readiness_report) + _scenario_selection_warnings(
        scenario_selection_gate
    )
    decision = "block" if blockers else "warn" if warnings else "pass"
    risk_score = _risk_score(blockers, warnings)
    return {
        "schema_version": "a2.release_gate.v1",
        "report_id": "a2_release_gate",
        "release_candidate": {
            "id": "a2_g3_commercial_default",
            "profile": "strict-commercial",
            "scope": "A2 scenario/judge/calibration evidence for agent release readiness",
        },
        "decision": decision,
        "exit_code": 2 if decision == "block" else 1 if decision == "warn" else 0,
        "risk_score": risk_score,
        "hard_gate_ids": list(HARD_GATES),
        "current_commercial_gate": commercial_readiness_report.get("current_gate", ""),
        "ready_for_commercial_gate": bool(commercial_readiness_report.get("ready_for_commercial_gate")),
        "blocking_gate_count": len(blocking_gates),
        "evidence_blocker_count": len(evidence_blockers),
        "scenario_selection_blocker_count": len(scenario_selection_blockers),
        "a1_output_policy_blocker_count": len(output_policy_blockers),
        "warning_count": len(warnings),
        "scenario_selection_gate": scenario_selection_gate,
        "a1_output_policy_gate": a1_output_policy_gate,
        "blockers": blockers,
        "warnings": warnings,
        "required_evidence": _required_evidence(evidence_readiness_report),
        "pr_annotations": _pr_annotations(blockers, warnings),
        "review_workflow": {
            "required_reviewers": ["A2 owner", "A1 API/runtime owner", "A3 dashboard/report owner"],
            "required_before_unblock": [
                "reviewed Ashr grading rows imported for all six calibration cases",
                "audited live semantic judge rows imported for all six calibration cases",
                "case book/regression replay maturity reaches mature",
                "per-project scenario selection coverage and minimums remain ready",
                "secret scan and deterministic fixture checks pass after import",
            ],
            "private_evidence_boundary": "Raw API/model payloads stay under docs/evidence/private_refs/ and are never committed.",
        },
        "machine_contract": {
            "ci_mode": "fail on decision=block",
            "blocking_fields": [
                "decision",
                "blockers",
                "required_evidence",
                "scenario_selection_gate",
                "a1_output_policy_gate",
            ],
            "stable_join_keys": ["case_id", "scenario_id", "gate"],
            "a3_consumption": "A3 may render this as a PR/release gate without reading private evidence.",
        },
        "evidence_refs": [
            "fixtures/a2/results/a2_commercial_readiness_report.json",
            "fixtures/a2/results/a2_evidence_readiness_report.json",
            "fixtures/a2/results/a2_g3_calibration_matrix.json",
            "fixtures/a2/results/a2_regression_replay_report.json",
            "fixtures/a2/results/a2_scenario_selection_report.json",
            A1_EVIDENCE_INDEX_REF,
        ],
        "metadata": {
            "deterministic": True,
            "purpose": "Block unsafe agent releases until A2 replay, judge, evidence, review, and regression gates are proven.",
            "does_not_execute_live_calls": True,
        },
    }


def apply_a1_output_policy_gate(report: dict[str, Any], evidence_index: dict[str, Any] | None) -> dict[str, Any]:
    """Return a release gate report with A1 public output-policy evidence applied."""
    patched = deepcopy(report)
    gate = build_a1_output_policy_gate(evidence_index)
    output_policy_blockers = _a1_output_policy_blockers(gate)
    blockers = [
        item
        for item in patched.get("blockers", [])
        if not (isinstance(item, dict) and item.get("type") == "a1_output_policy_gate")
    ]
    blockers.extend(output_policy_blockers)
    warnings = [item for item in patched.get("warnings", []) if isinstance(item, dict)]
    decision = "block" if blockers else "warn" if warnings else "pass"

    patched["a1_output_policy_gate"] = gate
    patched["a1_output_policy_blocker_count"] = len(output_policy_blockers)
    patched["blockers"] = blockers
    patched["decision"] = decision
    patched["exit_code"] = 2 if decision == "block" else 1 if decision == "warn" else 0
    patched["risk_score"] = _risk_score(blockers, warnings)
    patched["pr_annotations"] = _pr_annotations(blockers, warnings)
    patched["warning_count"] = len(warnings)
    patched["evidence_refs"] = _append_unique_string(patched.get("evidence_refs", []), A1_EVIDENCE_INDEX_REF)
    machine_contract = patched.get("machine_contract")
    if isinstance(machine_contract, dict):
        machine_contract["blocking_fields"] = _append_unique_string(
            machine_contract.get("blocking_fields", []),
            "a1_output_policy_gate",
        )
    return patched


def build_a1_output_policy_gate(evidence_index: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize A1 output policy counters into a public release-gate input."""
    if not isinstance(evidence_index, dict):
        return {
            "status": "not_evaluated",
            "ready": True,
            "source_schema_version": "",
            "label": "",
            "index_path": A1_EVIDENCE_INDEX_REF,
            "total_records": 0,
            "dangerous_counts": {key: 0 for key in OUTPUT_POLICY_BLOCKING_COUNTERS},
            "safe_counts": {},
            "evidence_refs": [],
        }

    counts = evidence_index.get("output_policy_counts")
    if not isinstance(counts, dict):
        counts = {}
    dangerous_counts = {
        key: _int_count(counts.get(key))
        for key in OUTPUT_POLICY_BLOCKING_COUNTERS
    }
    ready = all(value == 0 for value in dangerous_counts.values())
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "source_schema_version": str(evidence_index.get("schema_version", "")),
        "label": str(evidence_index.get("label", "")),
        "index_path": A1_EVIDENCE_INDEX_REF,
        "total_records": _int_count(evidence_index.get("total_records")),
        "dangerous_counts": dangerous_counts,
        "safe_counts": {
            "private_required": _int_count(counts.get("private_required")),
            "private_file": _int_count(counts.get("private_file")),
            "stdout_full_record_blocked": _int_count(counts.get("stdout_full_record_blocked")),
            "present": _int_count(counts.get("present")),
        },
        "evidence_refs": [A1_EVIDENCE_INDEX_REF],
    }


def _scenario_selection_gate(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {
            "status": "not_evaluated",
            "ready": True,
            "coverage_ready": True,
            "minimums_ready": True,
            "selection_id": "",
            "project_id": "",
            "environment": "",
            "selected_scenario_count": 0,
            "gaps": [],
            "evidence_refs": [],
        }

    coverage = report.get("coverage_summary", {})
    if not isinstance(coverage, dict):
        coverage = {}
    minimums = report.get("minimums_summary", {})
    if not isinstance(minimums, dict):
        minimums = {}
    project = report.get("project", {})
    if not isinstance(project, dict):
        project = {}
    a3_summary = report.get("a3_consumption_summary", {})
    if not isinstance(a3_summary, dict):
        a3_summary = {}

    coverage_ready = bool(coverage.get("coverage_ready"))
    minimums_ready = bool(minimums.get("minimums_ready"))
    gaps = [str(gap) for gap in minimums.get("gaps", []) if str(gap).strip()]
    if not coverage_ready:
        gaps.append("scenario selection coverage is not ready")
    ready = coverage_ready and minimums_ready
    return {
        "status": "ready" if ready else "needs_attention",
        "ready": ready,
        "coverage_ready": coverage_ready,
        "minimums_ready": minimums_ready,
        "selection_id": str(report.get("selection_id", "")),
        "project_id": str(project.get("project_id", "")),
        "environment": str(report.get("environment", "")),
        "selected_scenario_count": int(report.get("selected_scenario_count", 0)),
        "observed_minimums": minimums.get("observed", {}),
        "release_gate_inputs": a3_summary.get("release_gate_inputs", {}),
        "gaps": gaps,
        "evidence_refs": ["fixtures/a2/results/a2_scenario_selection_report.json"],
    }


def _scenario_selection_blockers(gate: dict[str, Any]) -> list[dict[str, Any]]:
    if gate.get("status") != "needs_attention":
        return []
    return [
        {
            "type": "scenario_selection_gate",
            "gate": "S1",
            "status": str(gate.get("status", "needs_attention")),
            "severity": "high",
            "summary": "Per-project scenario selection coverage or minimums are not release-ready.",
            "required_action": "Fix scenario selection gaps before using this pack as a release gate baseline.",
            "missing_count": len(gate.get("gaps", [])),
            "evidence_refs": gate.get("evidence_refs", []),
        }
    ]


def _a1_output_policy_blockers(gate: dict[str, Any]) -> list[dict[str, Any]]:
    if gate.get("status") != "blocked":
        return []
    dangerous_counts = gate.get("dangerous_counts", {})
    if not isinstance(dangerous_counts, dict):
        dangerous_counts = {}
    nonzero = {
        key: _int_count(dangerous_counts.get(key))
        for key in OUTPUT_POLICY_BLOCKING_COUNTERS
        if _int_count(dangerous_counts.get(key)) > 0
    }
    if not nonzero:
        return []
    return [
        {
            "type": "a1_output_policy_gate",
            "gate": "A1-OUTPUT-POLICY",
            "status": "blocked",
            "severity": "critical",
            "summary": "A1 public evidence index reports unsafe output-policy counters.",
            "required_action": "Fix output policy evidence so private-required API records stay private before release.",
            "missing_count": sum(nonzero.values()),
            "dangerous_counts": nonzero,
            "evidence_refs": gate.get("evidence_refs", []),
        }
    ]


def _scenario_selection_warnings(gate: dict[str, Any]) -> list[dict[str, Any]]:
    if gate.get("status") != "not_evaluated":
        return []
    return [
        {
            "type": "scenario_selection_gate",
            "severity": "medium",
            "summary": "Scenario selection gate was not evaluated for this release report.",
            "count": 1,
            "evidence_refs": [],
        }
    ]


def _gate_blocker(gate_id: str, gate: dict[str, Any]) -> dict[str, Any]:
    gaps = [str(gap) for gap in gate.get("gaps", []) if str(gap).strip()]
    return {
        "type": "commercial_gate",
        "gate": gate_id,
        "status": str(gate.get("status", "missing")),
        "severity": "high" if gate_id in {"C3", "C4", "C5"} else "critical",
        "summary": str(gate.get("name") or f"{gate_id} gate is not met"),
        "required_action": gaps[0] if gaps else f"Bring {gate_id} to met before release.",
        "gaps": gaps,
        "evidence_refs": gate.get("evidence_refs", []),
    }


def _evidence_blockers(
    evidence_readiness_report: dict[str, Any],
    calibration_matrix: dict[str, Any],
    regression_replay_report: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    ashr_gate = evidence_readiness_report.get("ashr_public_merge_gate", {})
    if not ashr_gate.get("safe_to_mark_c3_met"):
        blockers.append(
            {
                "type": "evidence_gate",
                "gate": "C3",
                "status": str(ashr_gate.get("status", "unknown")),
                "severity": "high",
                "summary": "Ashr server-side grading evidence is not publicly merge-safe.",
                "required_action": str(ashr_gate.get("blocking_reason") or "Import reviewed Ashr grading rows."),
                "missing_count": int(ashr_gate.get("missing_reviewed_observation_count", 0)),
                "evidence_refs": [ashr_gate.get("public_matrix_path", "")],
            }
        )

    semantic_gate = evidence_readiness_report.get("semantic_live_merge_gate", {})
    if not semantic_gate.get("safe_to_mark_c4_met"):
        blockers.append(
            {
                "type": "evidence_gate",
                "gate": "C4",
                "status": str(semantic_gate.get("status", "unknown")),
                "severity": "high",
                "summary": "Audited live semantic judge evidence is not merged.",
                "required_action": str(
                    semantic_gate.get("blocking_reason")
                    or "Import audited semantic judge summaries with prompt/model/cost metadata."
                ),
                "missing_count": int(semantic_gate.get("missing_audited_observation_count", 0)),
                "evidence_refs": [semantic_gate.get("public_matrix_path", "")],
            }
        )

    source_coverage = calibration_matrix.get("source_coverage", {})
    if int(source_coverage.get("ashr_grading", {}).get("missing", 0)) > 0:
        blockers.append(
            {
                "type": "calibration_gap",
                "gate": "C3",
                "status": "missing_source",
                "severity": "high",
                "summary": "Calibration matrix lacks Ashr grading rows.",
                "required_action": "Collect, review, import, and regenerate Ashr grading observations.",
                "missing_count": int(source_coverage.get("ashr_grading", {}).get("missing", 0)),
                "evidence_refs": ["fixtures/a2/results/a2_g3_calibration_matrix.json"],
            }
        )

    maturity = str(regression_replay_report.get("maturity_status", "missing"))
    if maturity != "mature":
        replay_gate = regression_replay_report.get("release_gate_summary", {})
        if not isinstance(replay_gate, dict):
            replay_gate = {}
        replay_refs = replay_gate.get("evidence_refs")
        if not isinstance(replay_refs, list):
            replay_refs = ["fixtures/a2/results/a2_regression_replay_report.json"]
        blockers.append(
            {
                "type": "regression_maturity",
                "gate": "C5",
                "status": maturity,
                "severity": "medium",
                "summary": "Regression replay is not mature enough to unblock release.",
                "required_action": str(
                    replay_gate.get("required_action")
                    or "Promote more reviewed disagreement or incident cases into replayable regressions."
                ),
                "missing_count": int(
                    replay_gate.get(
                        "blocking_count",
                        regression_replay_report.get("maturity_gate", {}).get("missing_reviewed_replay_cases", 0),
                    )
                ),
                "evidence_refs": replay_refs,
            }
        )
    return blockers


def _warnings(
    commercial_readiness_report: dict[str, Any],
    evidence_readiness_report: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings = []
    snapshot = commercial_readiness_report.get("evidence_snapshot", {})
    if int(snapshot.get("semantic_score_delta_reviews", 0)) > 0:
        warnings.append(
            {
                "type": "judge_risk",
                "severity": "medium",
                "summary": "Semantic score-delta review candidates remain open.",
                "count": int(snapshot.get("semantic_score_delta_reviews", 0)),
                "evidence_refs": ["fixtures/a2/results/a2_semantic_harness_report.json"],
            }
        )
    api_evidence = evidence_readiness_report.get("a1_real_api_evidence", {})
    if api_evidence.get("real_quota_gate", {}).get("blocked"):
        warnings.append(
            {
                "type": "quota_risk",
                "severity": "medium",
                "summary": "Real API quota gate is currently blocking mutating request calibration.",
                "count": int(api_evidence.get("real_quota_gate", {}).get("blocked_count", 0)),
                "evidence_refs": [api_evidence.get("index_path", "")],
            }
        )
    gate_validation = api_evidence.get("api_probe_gate_validation", {})
    if gate_validation.get("release_interpretation") in {
        "mixed_gate_evidence_review_required",
        "gate_validation_or_plan_blocked",
    }:
        warnings.append(
            {
                "type": "api_probe_gate_validation",
                "severity": "medium",
                "summary": "A1 API probe quota gate validation evidence needs review before mutating release calibration.",
                "count": int(gate_validation.get("error_validate_gate_count", 0))
                + int(gate_validation.get("blocked_plan_batch_count", 0)),
                "evidence_refs": [api_evidence.get("index_path", ""), gate_validation.get("schema_ref", "")],
            }
        )
    return warnings


def _required_evidence(evidence_readiness_report: dict[str, Any]) -> list[dict[str, Any]]:
    ashr = evidence_readiness_report.get("ashr_grading_preflight", {})
    semantic = evidence_readiness_report.get("semantic_judge_preflight", {})
    return [
        {
            "source": "ashr_grading",
            "required_count": int(ashr.get("expected_reviewed_observation_count", 0)),
            "current_available": int(ashr.get("current_available", 0)),
            "private_input_ref": ashr.get("private_input_ref", ""),
            "collection_packet_ref": "fixtures/a2/calibration/a2_ashr_grading_collection_packet.json",
            "commands": ashr.get("commands", []),
        },
        {
            "source": "llm_judge",
            "required_count": int(semantic.get("expected_reviewed_observation_count", 0)),
            "current_available": int(semantic.get("reviewed_live_observation_count", 0)),
            "private_input_ref": semantic.get("private_input_ref", ""),
            "collection_packet_ref": semantic.get("collection_packet_ref", ""),
            "commands": semantic.get("commands", []),
        },
    ]


def _pr_annotations(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotations = []
    for item in blockers:
        annotations.append(
            {
                "level": "failure",
                "title": f"{item.get('gate', 'A2')} blocks release",
                "message": item.get("required_action", ""),
                "evidence_refs": item.get("evidence_refs", []),
            }
        )
    for item in warnings:
        annotations.append(
            {
                "level": "warning",
                "title": item.get("summary", "A2 release warning"),
                "message": item.get("summary", ""),
                "evidence_refs": item.get("evidence_refs", []),
            }
        )
    return annotations


def _risk_score(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> int:
    severity_weight = {"critical": 35, "high": 25, "medium": 12, "low": 5}
    score = 0
    for item in blockers:
        score += severity_weight.get(str(item.get("severity", "")), 10)
    for item in warnings:
        score += severity_weight.get(str(item.get("severity", "")), 5)
    return min(score, 100)


def _int_count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(float(value)))
        except ValueError:
            return 0
    return 0


def _append_unique_string(values: Any, value: str) -> list[str]:
    result = [str(item) for item in values] if isinstance(values, list) else []
    if value not in result:
        result.append(value)
    return result
