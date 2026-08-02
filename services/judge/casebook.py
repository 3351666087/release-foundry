"""Reviewer-facing case book for A2 calibration regressions."""

from __future__ import annotations

import copy
import re
from typing import Any

from .calibration import (
    validate_releasefoundry_run_receipt_binding,
    validate_semantic_review_receipt_binding,
)
from .evidence_readiness import (
    is_verified_reviewed_releasefoundry_source,
    is_verified_reviewed_semantic_source,
)
from .incident_regression import verify_incident_regression_candidate_report
from .result_persistence import stable_hash


MATURE_REGRESSION_CASE_TARGET = 3
_SHA256_REF = re.compile(r"^sha256:[a-f0-9]{64}$")
_REVIEWER_RECEIPT = _SHA256_REF
_OWNER_REVIEW_DECISIONS = frozenset({"approved", "rejected", "pending"})
EXTERNAL_EVIDENCE_RECEIPT_BINDINGS_FIELD = (
    "external_evidence_receipt_bindings"
)


def build_case_book_report(calibration_matrix: dict[str, Any]) -> dict[str, Any]:
    """Build a durable case-book seed from calibration disagreement candidates."""
    calibration_cases = _validated_calibration_cases(
        calibration_matrix.get("cases")
    )
    regression_cases = [
        _regression_case(case)
        for case in calibration_cases
        if "judge_disagreement_regression" in case.get("calibration_tags", [])
    ]
    _validate_unique_case_ids(regression_cases, context="case-book")
    receipt_bindings = build_case_book_receipt_bindings(calibration_matrix)
    report = {
        "schema_version": "a2.case_book.v1",
        "case_book_id": "a2_case_book",
        "source_matrix": calibration_matrix.get("matrix_id", ""),
        "source_matrix_hash": stable_hash(calibration_matrix),
        "dataset_id": calibration_matrix.get("dataset_id", ""),
        "regression_case_count": len(regression_cases),
        EXTERNAL_EVIDENCE_RECEIPT_BINDINGS_FIELD: receipt_bindings,
        "candidate_pool": _candidate_pool(
            calibration_matrix,
            regression_cases,
            receipt_bindings,
        ),
        "maturity_gate": _maturity_gate(regression_cases, receipt_bindings),
        "regression_cases": regression_cases,
        "metadata": {
            "deterministic": True,
            "purpose": "Promote calibration disagreements into reviewer-visible regression seeds.",
            "notes": [
                "This report is additive and does not change local judge scores.",
                "Live ReleaseFoundry or LLM evidence should update calibration observations first, then regenerate this case book.",
            ],
        },
    }
    return _seal_case_book_artifact(report)


def build_case_book_receipt_bindings(
    calibration_matrix: dict[str, Any],
) -> dict[str, Any]:
    """Revalidate retained C3/C4 receipts before C5 counts copied source rows."""
    cases = _validated_calibration_cases(calibration_matrix.get("cases"))
    expected_case_ids = [
        str(case.get("case_id", "")).strip()
        for case in cases
        if isinstance(case, dict) and str(case.get("case_id", "")).strip()
    ]
    releasefoundry_binding = validate_releasefoundry_run_receipt_binding(
        [
            {
                "case_id": case.get("case_id"),
                "metadata": (
                    case.get("sources", {})
                    .get("releasefoundry_grading", {})
                    .get("metadata")
                ),
            }
            for case in cases
            if isinstance(case, dict)
        ],
        calibration_matrix.get("releasefoundry_run_terminal_receipt"),
        expected_case_ids=expected_case_ids,
    )
    semantic_binding = validate_semantic_review_receipt_binding(
        [
            _semantic_observation_projection(case)
            for case in cases
            if isinstance(case, dict)
        ],
        calibration_matrix.get("semantic_human_review_receipt"),
        expected_case_ids=expected_case_ids,
    )
    return {
        "releasefoundry_grading": {
            **releasefoundry_binding,
            "source_summary_hashes": _source_summary_hashes(
                cases,
                source_key="releasefoundry_grading",
            ),
        },
        "semantic_or_llm_judge": {
            **semantic_binding,
            "source_summary_hashes": _source_summary_hashes(
                cases,
                source_key="llm_judge",
            ),
        },
    }


def verify_case_book_artifact(case_book_report: dict[str, Any]) -> str:
    """Verify and return the case-book content hash."""
    if not isinstance(case_book_report, dict):
        raise TypeError("case-book artifact must be an object")
    artifact_hash = case_book_report.get("artifact_hash")
    if not isinstance(artifact_hash, str) or not _SHA256_REF.fullmatch(artifact_hash):
        raise ValueError("case-book artifact_hash must be a canonical sha256 reference")
    core = {
        key: value
        for key, value in case_book_report.items()
        if key != "artifact_hash"
    }
    if stable_hash(core) != artifact_hash:
        raise ValueError("case-book artifact_hash does not match case-book content")
    return artifact_hash


def promote_incident_candidates_to_case_book(
    case_book_report: dict[str, Any],
    incident_candidates_report: dict[str, Any],
    owner_review_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Promote only explicitly approved, public-safe incident candidates.

    Owner review is intentionally separate from external evidence review. An
    approved candidate may enter the executable replay set, but it cannot make
    the C5 maturity gate ready without reviewed ReleaseFoundry or audited semantic
    evidence.
    """
    promoted_report = copy.deepcopy(case_book_report)
    verify_case_book_artifact(promoted_report)
    source_incident_candidates_hash = (
        verify_incident_regression_candidate_report(incident_candidates_report)
    )
    candidates = _incident_candidates_by_case_id(incident_candidates_report)
    regression_cases = list(promoted_report.get("regression_cases", []))
    _validate_unique_case_ids(regression_cases, context="existing case-book")
    if owner_review_decisions is None or not owner_review_decisions:
        return promoted_report
    if not isinstance(owner_review_decisions, list):
        raise TypeError("owner_review_decisions must be a list")

    existing_case_ids = {
        str(case.get("case_id", ""))
        for case in regression_cases
        if isinstance(case, dict)
    }
    seen_case_ids: set[str] = set()
    audit: list[dict[str, Any]] = []

    for decision in owner_review_decisions:
        _validate_owner_review_decision(decision)
        case_id = str(decision["case_id"]).strip()
        if case_id in seen_case_ids:
            raise ValueError(f"duplicate owner review decision for case {case_id!r}")
        seen_case_ids.add(case_id)
        candidate = candidates.get(case_id)
        if candidate is None:
            raise ValueError(f"owner review references unknown incident candidate {case_id!r}")
        candidate_hash = stable_hash(candidate)
        _validate_owner_review_binding(
            decision,
            source_incident_candidates_hash=source_incident_candidates_hash,
            candidate_hash=candidate_hash,
        )

        decision_name = str(decision["decision"]).strip().lower()
        audit_item = _audit_item(decision, candidate)
        if decision_name != "approved":
            audit_item["outcome"] = "not_promoted"
            audit.append(audit_item)
            continue
        if (
            candidate.get("public_safe") is not True
            or candidate.get("ready_for_case_book_review") is not True
            or not _is_canonical_sha256_ref(candidate.get("fixture_sha256"))
        ):
            audit_item["outcome"] = "blocked"
            audit_item["blockers"] = [
                "candidate_not_public_safe_or_content_bound",
                "owner_approval_does_not_override_safety",
            ]
            audit.append(audit_item)
            continue
        if case_id in existing_case_ids:
            audit_item["outcome"] = "already_in_case_book"
            audit.append(audit_item)
            continue

        regression_cases.append(_incident_regression_case(candidate, decision))
        existing_case_ids.add(case_id)
        audit_item["outcome"] = "promoted"
        audit.append(audit_item)

    promoted_report["regression_cases"] = regression_cases
    promoted_report["regression_case_count"] = len(regression_cases)
    receipt_bindings = promoted_report.get(
        EXTERNAL_EVIDENCE_RECEIPT_BINDINGS_FIELD,
        {},
    )
    candidate_pool = dict(promoted_report.get("candidate_pool", {}))
    candidate_pool["promoted_regression_case_count"] = len(regression_cases)
    candidate_pool["reviewed_external_evidence_count"] = reviewed_external_evidence_count(
        regression_cases,
        receipt_bindings,
    )
    candidate_pool["owner_review_promotion_count"] = sum(
        1 for item in audit if item.get("outcome") == "promoted"
    )
    promoted_report["candidate_pool"] = candidate_pool
    promoted_report["maturity_gate"] = _maturity_gate(
        regression_cases,
        receipt_bindings,
    )
    metadata = dict(promoted_report.get("metadata", {}))
    metadata["promotion_audit"] = audit
    promoted_report["metadata"] = metadata
    return _seal_case_book_artifact(promoted_report)


def _seal_case_book_artifact(case_book_report: dict[str, Any]) -> dict[str, Any]:
    core = {
        key: value
        for key, value in case_book_report.items()
        if key != "artifact_hash"
    }
    return {**core, "artifact_hash": stable_hash(core)}


def _validate_owner_review_decision(decision: dict[str, Any]) -> None:
    if not isinstance(decision, dict):
        raise TypeError("each owner review decision must be an object")
    case_id = str(decision.get("case_id", "")).strip()
    if not case_id:
        raise ValueError("owner review decision requires case_id")
    decision_name = str(decision.get("decision", "")).strip().lower()
    if decision_name not in _OWNER_REVIEW_DECISIONS:
        raise ValueError(
            f"owner review decision for {case_id!r} must be one of "
            f"{sorted(_OWNER_REVIEW_DECISIONS)}"
        )
    receipt = decision.get("reviewer_receipt")
    if not isinstance(receipt, str) or not _REVIEWER_RECEIPT.fullmatch(receipt):
        raise ValueError(
            f"owner review decision for {case_id!r} requires a canonical reviewer_receipt"
        )
    reviewed_at = decision.get("reviewed_at_unix_ms")
    if isinstance(reviewed_at, bool) or not isinstance(reviewed_at, int) or reviewed_at <= 0:
        raise ValueError(
            f"owner review decision for {case_id!r} requires reviewed_at_unix_ms > 0"
        )
    evidence_refs = decision.get("evidence_refs", [])
    if not isinstance(evidence_refs, list) or any(
        not isinstance(ref, str) or not ref.strip() for ref in evidence_refs
    ):
        raise ValueError(
            f"owner review decision for {case_id!r} has invalid evidence_refs"
        )
    for field in ("source_incident_candidates_hash", "candidate_hash"):
        value = decision.get(field)
        if not isinstance(value, str) or not _SHA256_REF.fullmatch(value):
            raise ValueError(
                f"owner review decision for {case_id!r} requires a canonical {field}"
            )


def _validate_owner_review_binding(
    decision: dict[str, Any],
    *,
    source_incident_candidates_hash: str,
    candidate_hash: str,
) -> None:
    case_id = str(decision["case_id"]).strip()
    if decision["source_incident_candidates_hash"] != source_incident_candidates_hash:
        raise ValueError(
            f"owner review decision for {case_id!r} does not bind the current incident candidate report"
        )
    if decision["candidate_hash"] != candidate_hash:
        raise ValueError(
            f"owner review decision for {case_id!r} does not bind the current candidate content"
        )


def _validate_unique_case_ids(regression_cases: list[Any], *, context: str) -> None:
    seen: set[str] = set()
    for regression in regression_cases:
        if not isinstance(regression, dict):
            raise TypeError(f"{context} regression cases must be objects")
        case_id = str(regression.get("case_id", "")).strip()
        if not case_id:
            raise ValueError(f"{context} regression case requires case_id")
        if case_id in seen:
            raise ValueError(f"duplicate {context} regression case_id {case_id!r}")
        seen.add(case_id)


def _validated_calibration_cases(cases: Any) -> list[dict[str, Any]]:
    if not isinstance(cases, list):
        raise ValueError("case-book calibration cases must be a list")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(
                f"case-book calibration cases[{index}] must be an object"
            )
        case_id = str(case.get("case_id", "")).strip()
        if not case_id:
            raise ValueError(
                f"case-book calibration cases[{index}] requires case_id"
            )
        if case_id in seen:
            raise ValueError(
                f"duplicate case-book calibration case_id {case_id!r}"
            )
        calibration_tags = case.get("calibration_tags", [])
        if not isinstance(calibration_tags, list):
            raise ValueError(
                f"case-book calibration cases[{index}].calibration_tags must be a list"
            )
        seen_tags: set[str] = set()
        for tag_index, tag in enumerate(calibration_tags):
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(
                    f"case-book calibration cases[{index}].calibration_tags"
                    f"[{tag_index}] must be a non-empty string"
                )
            normalized_tag = tag.strip()
            if normalized_tag in seen_tags:
                raise ValueError(
                    f"case-book calibration cases[{index}].calibration_tags "
                    f"contains duplicate tag {normalized_tag!r}"
                )
            seen_tags.add(normalized_tag)
        diffs = case.get("diffs", [])
        if not isinstance(diffs, list):
            raise ValueError(
                f"case-book calibration cases[{index}].diffs must be a list"
            )
        for diff_index, diff in enumerate(diffs):
            if not isinstance(diff, dict):
                raise ValueError(
                    f"case-book calibration cases[{index}].diffs"
                    f"[{diff_index}] must be an object"
                )
        sources = case.get("sources", {})
        if not isinstance(sources, dict):
            raise ValueError(
                f"case-book calibration cases[{index}].sources must be an object"
            )
        for source_key in ("local_judge", "releasefoundry_grading", "llm_judge"):
            if source_key in sources and not isinstance(sources[source_key], dict):
                raise ValueError(
                    f"case-book calibration cases[{index}].sources."
                    f"{source_key} must be an object"
                )
        seen.add(case_id)
        validated.append(case)
    return validated


def _incident_candidates_by_case_id(
    incident_candidates_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    candidate_items = incident_candidates_report.get("candidates")
    if not isinstance(candidate_items, list):
        raise ValueError("incident candidate report candidates must be a list")
    candidates: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidate_items):
        if not isinstance(candidate, dict):
            raise ValueError(
                f"incident candidate report candidates[{index}] must be an object"
            )
        case_id = str(candidate.get("case_id", "")).strip()
        if not case_id:
            raise ValueError(
                f"incident candidate report candidates[{index}] requires case_id"
            )
        if case_id in candidates:
            raise ValueError(f"duplicate incident candidate case_id {case_id!r}")
        for field in (
            "expected",
            "local_judge",
            "releasefoundry_grading",
            "semantic_or_llm_judge",
        ):
            if not isinstance(candidate.get(field, {}), dict):
                raise ValueError(
                    f"incident candidate report candidates[{index}].{field} "
                    "must be an object"
                )
        for field in (
            "calibration_focus",
            "disagreement_pairs",
            "evidence_refs",
        ):
            value = candidate.get(field, [])
            if not isinstance(value, list):
                raise ValueError(
                    f"incident candidate report candidates[{index}].{field} "
                    "must be a list"
                )
            for item_index, item in enumerate(value):
                if field == "disagreement_pairs":
                    if not isinstance(item, dict):
                        raise ValueError(
                            f"incident candidate report candidates[{index}].{field}"
                            f"[{item_index}] must be an object"
                        )
                elif not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"incident candidate report candidates[{index}].{field}"
                        f"[{item_index}] must be a non-empty string"
                    )
        candidates[case_id] = candidate
    return candidates


def _audit_item(decision: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(decision["case_id"]).strip(),
        "incident_id": str(candidate.get("incident_id", "")),
        "decision": str(decision["decision"]).strip().lower(),
        "reviewer_receipt": str(decision["reviewer_receipt"]),
        "reviewed_at_unix_ms": int(decision["reviewed_at_unix_ms"]),
        "source_incident_candidates_hash": str(
            decision["source_incident_candidates_hash"]
        ),
        "candidate_hash": str(decision["candidate_hash"]),
        "evidence_refs": sorted(
            {
                str(ref)
                for ref in [*candidate.get("evidence_refs", []), *decision.get("evidence_refs", [])]
                if str(ref).strip()
            }
        ),
    }


def _incident_regression_case(
    candidate: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "regression_id": str(candidate.get("regression_id", "")),
        "case_id": str(candidate.get("case_id", "")),
        "scenario_id": str(candidate.get("scenario_id", "")),
        "fixture_ref": str(candidate.get("fixture_ref", "")),
        "fixture_sha256": str(candidate.get("fixture_sha256", "")),
        "status": "open",
        "severity": str(candidate.get("severity", "medium")),
        "source": str(candidate.get("source", "production_incident")),
        "incident_id": str(candidate.get("incident_id", "")),
        "environment": str(candidate.get("environment", "")),
        "calibration_focus": [
            str(item)
            for item in candidate.get("calibration_focus", [])
            if str(item).strip()
        ],
        "expected": dict(candidate.get("expected", {})),
        "local_judge": dict(candidate.get("local_judge", {})),
        "releasefoundry_grading": dict(candidate.get("releasefoundry_grading", {})),
        "semantic_or_llm_judge": dict(candidate.get("semantic_or_llm_judge", {})),
        "disagreement_pairs": list(candidate.get("disagreement_pairs", [])),
        "regression_assertion": str(candidate.get("regression_assertion", "")),
        "reviewer_note": str(candidate.get("reviewer_note", "")),
        "evidence_refs": sorted(
            {
                str(ref)
                for ref in [*candidate.get("evidence_refs", []), *decision.get("evidence_refs", [])]
                if str(ref).strip()
            }
        ),
        "promotion": {
            "source": "incident_candidate",
            "decision": "approved",
            "replay_input_approved": True,
            "reviewer_receipt": str(decision["reviewer_receipt"]),
            "reviewed_at_unix_ms": int(decision["reviewed_at_unix_ms"]),
            "source_incident_candidates_hash": str(
                decision["source_incident_candidates_hash"]
            ),
            "candidate_hash": str(decision["candidate_hash"]),
            "external_evidence_status": "missing",
        },
    }


def _is_canonical_sha256_ref(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_REF.fullmatch(value) is not None


def _candidate_pool(
    calibration_matrix: dict[str, Any],
    regression_cases: list[dict[str, Any]],
    receipt_bindings: Any,
) -> dict[str, Any]:
    agreement = calibration_matrix.get("agreement_summary", {}).get("local_vs_llm_judge", {})
    releasefoundry_coverage = calibration_matrix.get("source_coverage", {}).get("releasefoundry_grading", {})
    return {
        "calibration_case_count": int(calibration_matrix.get("case_count", 0)),
        "comparable_local_llm_count": int(agreement.get("comparable", 0)),
        "local_llm_mismatch_count": int(agreement.get("mismatch_count", 0)),
        "releasefoundry_grading_missing_count": int(releasefoundry_coverage.get("missing", 0)),
        "promoted_regression_case_count": len(regression_cases),
        "reviewed_external_evidence_count": reviewed_external_evidence_count(
            regression_cases,
            receipt_bindings,
        ),
    }


def _maturity_gate(
    regression_cases: list[dict[str, Any]],
    receipt_bindings: Any,
) -> dict[str, Any]:
    current_count = len(regression_cases)
    reviewed_count = reviewed_external_evidence_count(
        regression_cases,
        receipt_bindings,
    )
    ready = current_count >= MATURE_REGRESSION_CASE_TARGET and reviewed_count >= MATURE_REGRESSION_CASE_TARGET
    return {
        "status": "mature" if ready else "seed",
        "ready": ready,
        "target_regression_case_count": MATURE_REGRESSION_CASE_TARGET,
        "current_regression_case_count": current_count,
        "reviewed_evidence_target_count": MATURE_REGRESSION_CASE_TARGET,
        "reviewed_external_evidence_count": reviewed_count,
        "review_evidence_ready": reviewed_count >= MATURE_REGRESSION_CASE_TARGET,
        "gaps": _maturity_gaps(current_count, reviewed_count),
    }


def _maturity_gaps(current_count: int, reviewed_count: int) -> list[str]:
    gaps = []
    remaining = MATURE_REGRESSION_CASE_TARGET - current_count
    if remaining > 0:
        gaps.append(f"Promote {remaining} more reviewed disagreement case(s) before marking the C5 case book mature.")
    reviewed_remaining = MATURE_REGRESSION_CASE_TARGET - reviewed_count
    if reviewed_remaining > 0:
        gaps.append(
            f"Attach reviewed ReleaseFoundry grading or audited semantic evidence to {reviewed_remaining} regression case(s) before closing C5."
        )
    return gaps


def _regression_case(case: dict[str, Any]) -> dict[str, Any]:
    disagreement_pairs = [diff for diff in case.get("diffs", []) if diff.get("status") == "mismatch"]
    sources = case.get("sources", {})
    local = sources.get("local_judge", {})
    releasefoundry = sources.get("releasefoundry_grading", {})
    llm = sources.get("llm_judge", {})
    return {
        "regression_id": f"regression-{case.get('case_id', '')}",
        "case_id": case.get("case_id", ""),
        "scenario_id": case.get("scenario_id", ""),
        "fixture_ref": case.get("fixture_ref", ""),
        "status": "open",
        "severity": "medium",
        "calibration_focus": case.get("calibration_focus", []),
        "expected": case.get("expected", {}),
        "local_judge": _source_summary(local),
        "releasefoundry_grading": _source_summary(releasefoundry),
        "semantic_or_llm_judge": _source_summary(llm),
        "disagreement_pairs": disagreement_pairs,
        "regression_assertion": _regression_assertion(local, llm),
        "reviewer_note": _reviewer_note(case, local, llm),
        "evidence_refs": _evidence_refs(case, local, llm),
    }


def _source_summary(source: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "available": source.get("available") is True,
        "status": source.get("status", ""),
        "source": source.get("source", ""),
        "provider": source.get("provider", ""),
        "model": source.get("model", ""),
        "passed": source.get("passed"),
        "primary_failure_class": source.get("primary_failure_class", ""),
        "score": source.get("score"),
        "confidence": source.get("confidence"),
        "rationale": source.get("rationale", ""),
        "evidence_ref": source.get("evidence_ref", ""),
    }
    if isinstance(source.get("cost"), dict):
        summary["cost"] = copy.deepcopy(source["cost"])
    if isinstance(source.get("metadata"), dict):
        summary["metadata"] = copy.deepcopy(source["metadata"])
    return summary


def _semantic_observation_projection(case: dict[str, Any]) -> dict[str, Any]:
    source = (
        case.get("sources", {}).get("llm_judge", {})
        if isinstance(case.get("sources"), dict)
        else {}
    )
    source = source if isinstance(source, dict) else {}
    return {
        "case_id": case.get("case_id"),
        "scenario_id": case.get("scenario_id"),
        "provider": source.get("provider"),
        "model": source.get("model"),
        "passed": source.get("passed"),
        "primary_failure_class": source.get("primary_failure_class"),
        "score": source.get("score"),
        "confidence": source.get("confidence"),
        "rationale": source.get("rationale"),
        "evidence_ref": source.get("evidence_ref"),
        "metadata": source.get("metadata"),
    }


def _source_summary_hashes(
    cases: list[Any],
    *,
    source_key: str,
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id", "")).strip()
        sources = case.get("sources")
        source = sources.get(source_key) if isinstance(sources, dict) else {}
        if case_id and isinstance(source, dict):
            hashes[case_id] = stable_hash(_source_summary(source))
    return hashes


def _regression_assertion(local: dict[str, Any], llm: dict[str, Any]) -> str:
    return (
        f"Keep local primary_failure_class={local.get('primary_failure_class', '')} visible when semantic/LLM "
        f"judge reports {llm.get('primary_failure_class', '')} for the same case."
    )


def _reviewer_note(case: dict[str, Any], local: dict[str, Any], llm: dict[str, Any]) -> str:
    return (
        f"{case.get('case_id', '')} is a calibration disagreement: local_judge identifies "
        f"{local.get('primary_failure_class', '')}, while the semantic/LLM reference identifies "
        f"{llm.get('primary_failure_class', '')}. Keep it as a regression seed until reviewed ReleaseFoundry or live LLM "
        "evidence resolves whether this is a judge-boundary issue or an expected semantic ambiguity."
    )


def _evidence_refs(case: dict[str, Any], local: dict[str, Any], llm: dict[str, Any]) -> list[str]:
    refs = [str(case.get("fixture_ref", "")), str(local.get("evidence_ref", "")), str(llm.get("evidence_ref", ""))]
    return sorted({ref for ref in refs if ref})


def reviewed_external_evidence_count(
    regression_cases: list[dict[str, Any]],
    receipt_bindings: Any = None,
) -> int:
    return sum(
        1
        for regression in regression_cases
        if _has_reviewed_external_evidence(regression, receipt_bindings)
    )


def _has_reviewed_external_evidence(
    regression: dict[str, Any],
    receipt_bindings: Any,
) -> bool:
    case_id = str(regression.get("case_id", "")).strip()
    if not case_id:
        return False
    releasefoundry = regression.get("releasefoundry_grading", {})
    if (
        _source_receipt_binding_matches(
            receipt_bindings,
            lane="releasefoundry_grading",
            case_id=case_id,
            source=releasefoundry,
        )
        and is_verified_reviewed_releasefoundry_source(releasefoundry)
    ):
        return True

    semantic = regression.get("semantic_or_llm_judge", {})
    return (
        _source_receipt_binding_matches(
            receipt_bindings,
            lane="semantic_or_llm_judge",
            case_id=case_id,
            source=semantic,
        )
        and is_verified_reviewed_semantic_source(semantic)
    )


def _source_receipt_binding_matches(
    receipt_bindings: Any,
    *,
    lane: str,
    case_id: str,
    source: Any,
) -> bool:
    if not isinstance(receipt_bindings, dict) or not isinstance(source, dict):
        return False
    binding = receipt_bindings.get(lane)
    if not isinstance(binding, dict) or binding.get("valid") is not True:
        return False
    source_hashes = binding.get("source_summary_hashes")
    return (
        isinstance(source_hashes, dict)
        and source_hashes.get(case_id) == stable_hash(source)
    )
