"""Fail-closed uncertainty and escalation routing for A2 judge labels."""

from __future__ import annotations

import math
import re
from typing import Any

from .probability_calibration import (
    DEFAULT_ECE_THRESHOLD,
    DEFAULT_MINIMUM_CASES,
    DEFAULT_MINIMUM_CLASS_CASES,
    SCHEMA_VERSION as CALIBRATION_REPORT_SCHEMA_VERSION,
)
from .result_persistence import stable_hash
from .unified_label import (
    UnifiedJudgeLabelError,
    verify_unified_judge_label,
)


SCHEMA_VERSION = "a2.uncertainty_route.v1"
DEFAULT_LOCAL_CONFIDENCE_THRESHOLD = 0.80
DEFAULT_LOCAL_PROBABILITY_MARGIN = 0.20

HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
PUBLIC_TEXT_PATTERNS = (
    re.compile(r"\b(?:sk|tp|releasefoundry_live)[-_][A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(
        r"[?&](?:signature|sig|token|key|credential|x-amz-signature)=",
        re.IGNORECASE,
    ),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs", re.IGNORECASE),
    re.compile(r"(?:^|[\s\"'])(?:[A-Za-z]:[\\/]|/Users/|/home/|/private/|/tmp/)"),
)
VALID_RELEASEFOUNDRY_COMPARISONS = frozenset({"not_observed", "agrees", "disagrees"})
VALID_TEACHER_STATES = frozenset({"not_evaluated", "consensus", "conflict"})
VALID_DESTINATIONS = frozenset({"local_judge", "releasefoundry_teacher", "human_review"})

_REPORT_FIELDS = frozenset(
    {
        "schema_version",
        "report_id",
        "calibrator",
        "holdout",
        "thresholds",
        "metrics",
        "calibration_gate",
        "observation_bindings",
        "metadata",
        "report_hash",
    }
)
_CALIBRATOR_FIELDS = frozenset(
    {
        "calibrator_id",
        "calibrator_version",
        "method",
        "model_version",
        "artifact_hash",
        "fitted_parameter_hash",
        "fit_dataset_id",
        "fit_dataset_hash",
        "fit_receipt_hash",
        "fit_receipt_verified",
    }
)
_HOLDOUT_FIELDS = frozenset(
    {
        "manifest_id",
        "manifest_hash",
        "dataset_id",
        "dataset_hash",
        "case_count",
        "failed_count",
        "passed_count",
        "gold_authority",
        "gold_receipt_hash",
        "gold_receipt_verified",
        "source_isolation_receipt_hash",
        "source_isolation_verified",
    }
)
_THRESHOLD_FIELDS = frozenset(
    {"ece", "minimum_cases", "minimum_class_cases", "bin_count"}
)
_GATE_FIELDS = frozenset(
    {
        "status",
        "eligible_for_unified_label_calibrated_status",
        "blockers",
        "automatic_model_promotion_allowed",
        "requires_blind_version_comparison",
    }
)
_METRIC_FIELDS = frozenset(
    {
        "case_count",
        "expected_calibration_error",
        "maximum_calibration_error",
        "brier_score",
        "negative_log_likelihood",
        "mean_probability",
        "empirical_rate",
        "reliability_bins",
    }
)
_OBSERVATION_BINDING_FIELDS = frozenset(
    {"case_id", "source_hash", "source_group_hash", "prediction_hash"}
)


class UncertaintyRoutingError(ValueError):
    """Raised when routing inputs are unsafe, inconsistent, or untrusted."""


def build_uncertainty_route(
    *,
    label: dict[str, Any],
    calibration_report: dict[str, Any] | None,
    releasefoundry_available: bool,
    releasefoundry_comparison: str = "not_observed",
    teacher_state: str = "not_evaluated",
    evidence_complete: bool = True,
    out_of_scope: bool = False,
    historical_critical_regression: bool = False,
    novel_failure_type: bool = False,
    route_id: str = "a2_uncertainty_route",
    local_confidence_threshold: float = DEFAULT_LOCAL_CONFIDENCE_THRESHOLD,
    local_probability_margin: float = DEFAULT_LOCAL_PROBABILITY_MARGIN,
) -> dict[str, Any]:
    """Choose local, ReleaseFoundry-teacher, or human handling without making live calls.

    The router never authorizes a paid mutation. An ``releasefoundry_teacher`` destination
    means that a separate dataset-identity, receipt, privacy, and spend gate must
    authorize the external call.
    """
    normalized_label = _verified_label(label)
    normalized_releasefoundry_available = _boolean(releasefoundry_available, "releasefoundry_available")
    normalized_releasefoundry_comparison = _enum(
        releasefoundry_comparison,
        VALID_RELEASEFOUNDRY_COMPARISONS,
        "releasefoundry_comparison",
    )
    normalized_teacher_state = _enum(
        teacher_state,
        VALID_TEACHER_STATES,
        "teacher_state",
    )
    normalized_evidence_complete = _boolean(
        evidence_complete,
        "evidence_complete",
    )
    normalized_out_of_scope = _boolean(out_of_scope, "out_of_scope")
    normalized_historical_critical = _boolean(
        historical_critical_regression,
        "historical_critical_regression",
    )
    normalized_novel_failure = _boolean(
        novel_failure_type,
        "novel_failure_type",
    )
    confidence_threshold = _probability(
        local_confidence_threshold,
        "local_confidence_threshold",
    )
    probability_margin_threshold = _probability_margin(
        local_probability_margin,
    )
    calibration = _calibration_summary(
        normalized_label,
        calibration_report,
    )

    probability = normalized_label["failure_probability"]
    decision_margin = round(abs(probability - 0.5), 12)
    locally_confident = bool(
        normalized_label["confidence"] >= confidence_threshold
        and decision_margin >= probability_margin_threshold
    )
    hard_review_reasons = _hard_review_reasons(
        label=normalized_label,
        releasefoundry_comparison=normalized_releasefoundry_comparison,
        teacher_state=normalized_teacher_state,
        evidence_complete=normalized_evidence_complete,
        historical_critical_regression=normalized_historical_critical,
    )
    local_blockers = _local_resolution_blockers(
        label=normalized_label,
        calibration=calibration,
        locally_confident=locally_confident,
        evidence_complete=normalized_evidence_complete,
        out_of_scope=normalized_out_of_scope,
        historical_critical_regression=normalized_historical_critical,
        novel_failure_type=normalized_novel_failure,
        releasefoundry_comparison=normalized_releasefoundry_comparison,
        teacher_state=normalized_teacher_state,
    )

    if hard_review_reasons:
        destination = "human_review"
        resolution_state = "uncertain"
        resolution_basis = "hard_review_gate"
        reason_codes = hard_review_reasons
    elif not local_blockers:
        destination = "local_judge"
        resolution_state = "resolved"
        resolution_basis = "calibrated_local_judge"
        reason_codes = ["calibrated_low_risk_local_resolution"]
    elif (
        normalized_releasefoundry_comparison == "agrees"
        and not normalized_out_of_scope
        and not normalized_novel_failure
    ):
        destination = "local_judge"
        resolution_state = "resolved"
        resolution_basis = "local_releasefoundry_agreement"
        reason_codes = ["releasefoundry_agreement_resolved_non_high_risk_case"]
    elif normalized_releasefoundry_available and normalized_releasefoundry_comparison == "not_observed":
        destination = "releasefoundry_teacher"
        resolution_state = "uncertain"
        resolution_basis = "external_teacher_needed"
        reason_codes = list(local_blockers)
    else:
        destination = "human_review"
        resolution_state = "uncertain"
        resolution_basis = "releasefoundry_unavailable_or_insufficient"
        reason_codes = list(local_blockers)
        if normalized_releasefoundry_comparison == "agrees":
            _append_unique(reason_codes, "releasefoundry_agreement_insufficient_for_case")
        elif not normalized_releasefoundry_available:
            _append_unique(reason_codes, "releasefoundry_unavailable")
        else:
            _append_unique(reason_codes, "releasefoundry_result_missing")

    release_recommendation = _release_recommendation(
        label=normalized_label,
        destination=destination,
        resolution_basis=resolution_basis,
        evidence_complete=normalized_evidence_complete,
        historical_critical_regression=normalized_historical_critical,
    )
    local_auto_resolution = resolution_basis == "calibrated_local_judge"
    automatic_release_allowed = bool(
        local_auto_resolution
        and release_recommendation == "allow"
        and calibration["status"] == "qualified"
    )
    active_learning = _active_learning_priority(
        label=normalized_label,
        calibration=calibration,
        decision_margin=decision_margin,
        releasefoundry_comparison=normalized_releasefoundry_comparison,
        teacher_state=normalized_teacher_state,
        evidence_complete=normalized_evidence_complete,
        out_of_scope=normalized_out_of_scope,
        historical_critical_regression=normalized_historical_critical,
        novel_failure_type=normalized_novel_failure,
    )
    core = {
        "schema_version": SCHEMA_VERSION,
        "route_id": _public_text(route_id, "route_id"),
        "case_id": normalized_label["case_id"],
        "label_hash": normalized_label["label_hash"],
        "calibration_report_hash": calibration["report_hash"],
        "signals": {
            "modality": normalized_label["modality"],
            "severity": normalized_label["severity"],
            "failure_type": normalized_label["failure_type"],
            "confidence": normalized_label["confidence"],
            "failure_probability": probability,
            "decision_margin": decision_margin,
            "releasefoundry_available": normalized_releasefoundry_available,
            "releasefoundry_comparison": normalized_releasefoundry_comparison,
            "teacher_state": normalized_teacher_state,
            "evidence_complete": normalized_evidence_complete,
            "out_of_scope": normalized_out_of_scope,
            "historical_critical_regression": normalized_historical_critical,
            "novel_failure_type": normalized_novel_failure,
        },
        "calibration": calibration,
        "local_resolution_gate": {
            "eligible": not local_blockers,
            "confidence_threshold": confidence_threshold,
            "probability_margin_threshold": probability_margin_threshold,
            "locally_confident": locally_confident,
            "blockers": local_blockers,
        },
        "decision": {
            "resolution_state": resolution_state,
            "next_destination": destination,
            "resolution_basis": resolution_basis,
            "reason_codes": reason_codes,
            "release_recommendation": release_recommendation,
            "local_auto_resolution": local_auto_resolution,
            "releasefoundry_teacher_call_recommended": destination == "releasefoundry_teacher",
            "paid_releasefoundry_call_authorized": False,
            "requires_external_mutation_gate": destination == "releasefoundry_teacher",
            "human_review_required": destination == "human_review",
            "automatic_release_allowed": automatic_release_allowed,
        },
        "active_learning": active_learning,
        "metadata": {
            "public_safe": True,
            "deterministic": True,
            "local_label_preserved_when_releasefoundry_unavailable": True,
            "releasefoundry_output_is_human_gold": False,
            "router_makes_live_calls": False,
            "router_authorizes_paid_calls": False,
            "uncertain_cases_may_not_claim_automatic_release": True,
        },
    }
    _validate_public_safe(core)
    return {**core, "route_hash": stable_hash(core)}


def _verified_label(value: Any) -> dict[str, Any]:
    try:
        verify_unified_judge_label(value)
    except UnifiedJudgeLabelError as exc:
        raise UncertaintyRoutingError("unified_label_invalid") from exc
    return value


def _calibration_summary(
    label: dict[str, Any],
    report: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if label["probability_calibration"]["status"] != "calibrated":
        blockers.append("label_probability_uncalibrated")
    if report is None:
        blockers.append("calibration_report_missing")
        return {
            "status": "unqualified",
            "report_hash": None,
            "artifact_hash": label["probability_calibration"]["artifact_hash"],
            "calibrator_version": label["probability_calibration"]["version"],
            "model_version": label["model_version"],
            "blockers": blockers,
        }

    expected_report_blockers = _validate_calibration_report(report)
    calibrator = report["calibrator"]
    label_calibration = label["probability_calibration"]
    if calibrator["model_version"] != label["model_version"]:
        raise UncertaintyRoutingError("calibration_model_version_mismatch")
    if label_calibration["status"] == "calibrated":
        if calibrator["artifact_hash"] != label_calibration["artifact_hash"]:
            raise UncertaintyRoutingError("calibration_artifact_hash_mismatch")
        if calibrator["calibrator_version"] != label_calibration["version"]:
            raise UncertaintyRoutingError("calibrator_version_mismatch")
        if calibrator["method"] != label_calibration["method"]:
            raise UncertaintyRoutingError("calibration_method_mismatch")

    gate = report["calibration_gate"]
    if expected_report_blockers:
        blockers.append("calibration_report_not_qualified")
    if not gate["eligible_for_unified_label_calibrated_status"]:
        blockers.append("calibration_report_label_status_ineligible")
    if expected_report_blockers:
        blockers.extend(
            f"calibration_report:{item}"
            for item in expected_report_blockers
        )
    return {
        "status": "qualified" if not blockers else "unqualified",
        "report_hash": report["report_hash"],
        "artifact_hash": calibrator["artifact_hash"],
        "calibrator_version": calibrator["calibrator_version"],
        "model_version": calibrator["model_version"],
        "blockers": blockers,
    }


def _validate_calibration_report(report: Any) -> list[str]:
    _exact_fields(report, _REPORT_FIELDS, "calibration_report")
    if report["schema_version"] != CALIBRATION_REPORT_SCHEMA_VERSION:
        raise UncertaintyRoutingError("unsupported_calibration_report_schema")
    declared_hash = _hash(report["report_hash"], "calibration_report_hash")
    core = {key: value for key, value in report.items() if key != "report_hash"}
    if stable_hash(core) != declared_hash:
        raise UncertaintyRoutingError("calibration_report_hash_mismatch")
    _exact_fields(report["calibrator"], _CALIBRATOR_FIELDS, "calibrator")
    _exact_fields(report["holdout"], _HOLDOUT_FIELDS, "holdout")
    _exact_fields(report["thresholds"], _THRESHOLD_FIELDS, "thresholds")
    _exact_fields(report["calibration_gate"], _GATE_FIELDS, "calibration_gate")

    calibrator = report["calibrator"]
    holdout = report["holdout"]
    thresholds = report["thresholds"]
    gate = report["calibration_gate"]
    _public_text(report["report_id"], "calibration_report_id")
    for field in (
        "calibrator_id",
        "calibrator_version",
        "method",
        "model_version",
        "fit_dataset_id",
    ):
        _public_text(calibrator[field], f"calibrator_{field}")
    for field in ("manifest_id", "dataset_id"):
        _public_text(holdout[field], f"holdout_{field}")
    for field in (
        "artifact_hash",
        "fitted_parameter_hash",
        "fit_dataset_hash",
        "fit_receipt_hash",
    ):
        _hash(calibrator[field], f"calibrator_{field}")
    for field in (
        "manifest_hash",
        "dataset_hash",
        "gold_receipt_hash",
        "source_isolation_receipt_hash",
    ):
        _hash(holdout[field], f"holdout_{field}")
    if holdout["gold_authority"] != "human_adjudicated":
        raise UncertaintyRoutingError("calibration_holdout_not_human_gold")
    fit_receipt_verified = _boolean(
        calibrator["fit_receipt_verified"],
        "fit_receipt_verified",
    )
    gold_receipt_verified = _boolean(
        holdout["gold_receipt_verified"],
        "gold_receipt_verified",
    )
    source_isolation_verified = _boolean(
        holdout["source_isolation_verified"],
        "source_isolation_verified",
    )
    case_count = _positive_integer(holdout["case_count"], "holdout_case_count")
    failed_count = _non_negative_integer(
        holdout["failed_count"],
        "holdout_failed_count",
    )
    passed_count = _non_negative_integer(
        holdout["passed_count"],
        "holdout_passed_count",
    )
    if failed_count + passed_count != case_count:
        raise UncertaintyRoutingError("calibration_holdout_count_mismatch")
    ece_threshold = _probability(
        thresholds["ece"],
        "calibration_ece_threshold",
    )
    if ece_threshold > DEFAULT_ECE_THRESHOLD:
        raise UncertaintyRoutingError("calibration_ece_threshold_too_permissive")
    minimum_cases = _positive_integer(thresholds["minimum_cases"], "minimum_cases")
    if minimum_cases < DEFAULT_MINIMUM_CASES:
        raise UncertaintyRoutingError("calibration_case_threshold_too_permissive")
    minimum_class_cases = _positive_integer(
        thresholds["minimum_class_cases"],
        "minimum_class_cases",
    )
    if minimum_class_cases < DEFAULT_MINIMUM_CLASS_CASES:
        raise UncertaintyRoutingError(
            "calibration_class_threshold_too_permissive"
        )
    _positive_integer(thresholds["bin_count"], "bin_count")
    metrics = report["metrics"]
    if not isinstance(metrics, dict):
        raise UncertaintyRoutingError("calibration_metrics_must_be_object")
    overall_ece = _metric_ece(
        metrics.get("overall"),
        "overall",
        expected_case_count=case_count,
    )
    class_conditional = metrics.get("class_conditional")
    if not isinstance(class_conditional, dict) or set(class_conditional) != {
        "fail",
        "pass",
    }:
        raise UncertaintyRoutingError(
            "calibration_class_conditional_metrics_invalid"
        )
    failure_ece = _metric_ece(
        class_conditional["fail"],
        "failure_class",
        expected_case_count=failed_count,
    )
    pass_ece = _metric_ece(
        class_conditional["pass"],
        "pass_class",
        expected_case_count=passed_count,
    )
    for slice_name in ("per_modality", "per_severity"):
        if not isinstance(metrics.get(slice_name), dict):
            raise UncertaintyRoutingError(
                f"calibration_{slice_name}_metrics_invalid"
            )
    observation_bindings = report["observation_bindings"]
    if not isinstance(observation_bindings, list):
        raise UncertaintyRoutingError(
            "calibration_observation_bindings_must_be_list"
        )
    if len(observation_bindings) != case_count:
        raise UncertaintyRoutingError(
            "calibration_observation_binding_count_mismatch"
        )
    observed_case_ids: set[str] = set()
    for index, binding in enumerate(observation_bindings):
        _exact_fields(
            binding,
            _OBSERVATION_BINDING_FIELDS,
            f"observation_binding_{index}",
        )
        case_id = _public_text(
            binding["case_id"],
            f"observation_binding_{index}_case_id",
        )
        if case_id in observed_case_ids:
            raise UncertaintyRoutingError(
                "calibration_duplicate_observation_binding_case_id"
            )
        observed_case_ids.add(case_id)
        for field in ("source_hash", "source_group_hash", "prediction_hash"):
            _hash(
                binding[field],
                f"observation_binding_{index}_{field}",
            )

    expected_blockers: list[str] = []
    if not fit_receipt_verified:
        expected_blockers.append("fit_receipt_not_verified")
    if not gold_receipt_verified:
        expected_blockers.append("human_gold_receipt_not_verified")
    if not source_isolation_verified:
        expected_blockers.append("source_isolation_not_verified")
    if case_count < minimum_cases:
        expected_blockers.append("heldout_case_count_below_minimum")
    if failed_count < minimum_class_cases:
        expected_blockers.append("heldout_failure_count_below_minimum")
    if passed_count < minimum_class_cases:
        expected_blockers.append("heldout_pass_count_below_minimum")
    if overall_ece is not None and overall_ece > ece_threshold:
        expected_blockers.append("overall_ece_above_threshold")
    if failure_ece is not None and failure_ece > ece_threshold:
        expected_blockers.append("failure_class_ece_above_threshold")
    if pass_ece is not None and pass_ece > ece_threshold:
        expected_blockers.append("pass_class_ece_above_threshold")
    expected_blockers = sorted(expected_blockers)

    gate_status = _enum(
        gate["status"],
        frozenset({"calibrated", "uncalibrated"}),
        "calibration_gate_status",
    )
    eligible = _boolean(
        gate["eligible_for_unified_label_calibrated_status"],
        "calibration_gate_eligible",
    )
    blockers = gate["blockers"]
    if not isinstance(blockers, list) or any(
        not isinstance(item, str) or not item for item in blockers
    ):
        raise UncertaintyRoutingError("calibration_gate_blockers_invalid")
    if blockers != expected_blockers:
        raise UncertaintyRoutingError("calibration_gate_blockers_inconsistent")
    expected_status = "calibrated" if not expected_blockers else "uncalibrated"
    if gate_status != expected_status or eligible != (not expected_blockers):
        raise UncertaintyRoutingError("calibration_gate_inconsistent")
    if _boolean(
        gate["automatic_model_promotion_allowed"],
        "automatic_model_promotion_allowed",
    ):
        raise UncertaintyRoutingError("calibration_report_auto_promotion_forbidden")
    if not _boolean(
        gate["requires_blind_version_comparison"],
        "requires_blind_version_comparison",
    ):
        raise UncertaintyRoutingError("blind_version_comparison_requirement_missing")
    metadata = report["metadata"]
    if not isinstance(metadata, dict):
        raise UncertaintyRoutingError("calibration_metadata_must_be_object")
    if metadata.get("public_safe") is not True:
        raise UncertaintyRoutingError("calibration_public_safe_boundary_missing")
    if metadata.get("does_not_fit_or_promote_models") is not True:
        raise UncertaintyRoutingError(
            "calibration_promotion_boundary_missing"
        )
    if metadata.get("calibration_requires_human_gold") is not True:
        raise UncertaintyRoutingError("calibration_human_gold_boundary_missing")
    if metadata.get("train_holdout_source_overlap_allowed") is not False:
        raise UncertaintyRoutingError("calibration_source_isolation_boundary_missing")
    _validate_public_safe(report)
    return expected_blockers


def _metric_ece(
    value: Any,
    field: str,
    *,
    expected_case_count: int,
) -> float | None:
    _exact_fields(value, _METRIC_FIELDS, f"{field}_metrics")
    case_count = _non_negative_integer(
        value["case_count"],
        f"{field}_case_count",
    )
    if case_count != expected_case_count:
        raise UncertaintyRoutingError(f"{field}_case_count_mismatch")
    ece = value["expected_calibration_error"]
    if case_count == 0:
        if ece is not None:
            raise UncertaintyRoutingError(f"{field}_empty_ece_must_be_null")
        return None
    return _probability(ece, f"{field}_expected_calibration_error")


def _hard_review_reasons(
    *,
    label: dict[str, Any],
    releasefoundry_comparison: str,
    teacher_state: str,
    evidence_complete: bool,
    historical_critical_regression: bool,
) -> list[str]:
    reasons: list[str] = []
    if historical_critical_regression:
        reasons.append("historical_critical_regression")
    if label["severity"] == "critical":
        reasons.append("critical_severity")
    elif label["severity"] == "high":
        reasons.append("high_severity")
    if teacher_state == "conflict":
        reasons.append("teacher_conflict")
    if releasefoundry_comparison == "disagrees":
        reasons.append("local_releasefoundry_disagreement")
    if not evidence_complete:
        reasons.append("evidence_incomplete")
    if label["release_recommendation"] == "human_review":
        reasons.append("label_requests_human_review")
    elif label["release_recommendation"] == "block":
        reasons.append("label_requests_block")
    return reasons


def _local_resolution_blockers(
    *,
    label: dict[str, Any],
    calibration: dict[str, Any],
    locally_confident: bool,
    evidence_complete: bool,
    out_of_scope: bool,
    historical_critical_regression: bool,
    novel_failure_type: bool,
    releasefoundry_comparison: str,
    teacher_state: str,
) -> list[str]:
    blockers: list[str] = []
    if calibration["status"] != "qualified":
        blockers.append("calibration_unqualified")
    if not locally_confident:
        blockers.append("local_probability_uncertain")
    if label["severity"] not in {"none", "low"}:
        blockers.append("risk_above_local_threshold")
    if not evidence_complete:
        blockers.append("evidence_incomplete")
    if out_of_scope:
        blockers.append("local_judge_out_of_scope")
    if historical_critical_regression:
        blockers.append("historical_critical_regression")
    if novel_failure_type:
        blockers.append("novel_failure_type")
    if releasefoundry_comparison == "disagrees":
        blockers.append("local_releasefoundry_disagreement")
    if teacher_state == "conflict":
        blockers.append("teacher_conflict")
    if label["release_recommendation"] in {"human_review", "block"}:
        blockers.append("label_requires_nonlocal_resolution")
    return blockers


def _release_recommendation(
    *,
    label: dict[str, Any],
    destination: str,
    resolution_basis: str,
    evidence_complete: bool,
    historical_critical_regression: bool,
) -> str:
    if (
        historical_critical_regression
        or label["severity"] in {"high", "critical"}
        or label["release_recommendation"] == "block"
    ):
        return "block"
    if destination == "local_judge":
        return label["release_recommendation"]
    if not evidence_complete or destination == "releasefoundry_teacher":
        return "retest"
    if resolution_basis in {"hard_review_gate", "releasefoundry_unavailable_or_insufficient"}:
        return "human_review"
    return "human_review"


def _active_learning_priority(
    *,
    label: dict[str, Any],
    calibration: dict[str, Any],
    decision_margin: float,
    releasefoundry_comparison: str,
    teacher_state: str,
    evidence_complete: bool,
    out_of_scope: bool,
    historical_critical_regression: bool,
    novel_failure_type: bool,
) -> dict[str, Any]:
    components: dict[str, float] = {}
    reasons: list[str] = []
    uncertainty = round((1.0 - min(1.0, decision_margin / 0.5)) * 35.0, 6)
    components["local_uncertainty"] = uncertainty
    if uncertainty >= 10.0:
        reasons.append("local_probability_uncertain")
    if calibration["status"] != "qualified":
        components["calibration_gap"] = 15.0
        reasons.append("calibration_unqualified")
    if releasefoundry_comparison == "disagrees":
        components["local_releasefoundry_disagreement"] = 30.0
        reasons.append("local_releasefoundry_disagreement")
    if teacher_state == "conflict":
        components["teacher_conflict"] = 25.0
        reasons.append("teacher_conflict")
    severity_score = {
        "none": 0.0,
        "low": 4.0,
        "medium": 10.0,
        "high": 18.0,
        "critical": 25.0,
    }[label["severity"]]
    components["severity"] = severity_score
    if severity_score:
        reasons.append(f"{label['severity']}_severity")
    if historical_critical_regression:
        components["historical_critical_regression"] = 30.0
        reasons.append("historical_critical_regression")
    if not evidence_complete:
        components["evidence_gap"] = 15.0
        reasons.append("evidence_incomplete")
    if out_of_scope:
        components["out_of_scope"] = 15.0
        reasons.append("local_judge_out_of_scope")
    if novel_failure_type:
        components["novel_failure_type"] = 10.0
        reasons.append("novel_failure_type")
    score = round(min(100.0, sum(components.values())), 6)
    if historical_critical_regression or label["severity"] == "critical":
        band = "critical"
    elif score >= 75.0:
        band = "critical"
    elif score >= 50.0:
        band = "high"
    elif score >= 25.0:
        band = "medium"
    else:
        band = "low"
    return {
        "score": score,
        "band": band,
        "components": components,
        "reasons": reasons,
        "priority_policy": (
            "prefer uncertain, disagreeing, novel, high-risk, and historical "
            "critical cases for paid teacher or human labels"
        ),
    }


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _exact_fields(value: Any, expected: frozenset[str], field: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise UncertaintyRoutingError(f"{field}_fields_mismatch")


def _enum(value: Any, allowed: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise UncertaintyRoutingError(f"{field}_invalid")
    return value


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise UncertaintyRoutingError(f"{field}_invalid")
    return value


def _public_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise UncertaintyRoutingError(f"{field}_invalid")
    if any(pattern.search(value) for pattern in PUBLIC_TEXT_PATTERNS):
        raise UncertaintyRoutingError("private_or_secret_material_rejected")
    return value


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UncertaintyRoutingError(f"{field}_must_be_probability")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise UncertaintyRoutingError(f"{field}_must_be_probability")
    return normalized


def _probability_margin(value: Any) -> float:
    normalized = _probability(value, "local_probability_margin")
    if normalized > 0.5:
        raise UncertaintyRoutingError(
            "local_probability_margin_must_not_exceed_half"
        )
    return normalized


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise UncertaintyRoutingError(f"{field}_must_be_positive_integer")
    return value


def _non_negative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UncertaintyRoutingError(f"{field}_must_be_non_negative_integer")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise UncertaintyRoutingError(f"{field}_must_be_boolean")
    return value


def _validate_public_safe(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_public_safe(key)
            _validate_public_safe(item)
    elif isinstance(value, list):
        for item in value:
            _validate_public_safe(item)
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in PUBLIC_TEXT_PATTERNS):
            raise UncertaintyRoutingError("private_or_secret_material_rejected")
