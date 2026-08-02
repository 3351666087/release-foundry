"""Strict cross-modality label contract for A2 judge outputs.

The contract keeps a binary decision separate from probability-calibration
provenance. An uncalibrated score may be recorded for analysis, but it cannot
be presented as a calibrated probability or authorize an automatic release.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .release_actions import CANONICAL_RELEASE_ACTIONS
from .result_persistence import stable_hash
from .schemas import CANONICAL_FAILURE_CLASSES, GradeResult


SCHEMA_VERSION = "a2.unified_judge_label.v1"
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

VALID_MODALITIES = frozenset(
    {"text", "tool", "image", "audio", "video", "document", "multimodal"}
)
EVIDENCE_MODALITIES = VALID_MODALITIES - {"multimodal"}
VALID_SEVERITIES = frozenset({"none", "low", "medium", "high", "critical"})
VALID_RELEASE_RECOMMENDATIONS = frozenset(CANONICAL_RELEASE_ACTIONS)
VALID_CALIBRATION_STATUSES = frozenset({"calibrated", "uncalibrated"})
MULTIMODAL_FAILURE_CLASSES = frozenset(
    {
        "cross_modal_conflict_ignored",
        "evidence_location_invalid",
        "evidence_not_grounded",
        "malicious_document_execution",
        "media_decode_failure",
        "modality_mismatch",
        "prompt_injection_followed",
        "temporal_reasoning_error",
        "uncertain_out_of_scope",
        "unsupported_or_corrupt_input",
    }
)
VALID_FAILURE_CLASSES = (
    frozenset(CANONICAL_FAILURE_CLASSES)
    | MULTIMODAL_FAILURE_CLASSES
    | {"none"}
)

_COMMON_FIELDS = frozenset({"modality", "source_hash"})
_EVIDENCE_ALLOWED_FIELDS = {
    "text": _COMMON_FIELDS
    | {"start_char", "end_char", "start_token", "end_token"},
    "image": _COMMON_FIELDS
    | {"x", "y", "width", "height", "coordinate_space"},
    "audio": _COMMON_FIELDS | {"start_ms", "end_ms", "speaker"},
    "video": _COMMON_FIELDS
    | {"start_ms", "end_ms", "start_frame", "end_frame"},
    "document": _COMMON_FIELDS
    | {
        "document_type",
        "page",
        "paragraph",
        "table",
        "sheet",
        "cell",
        "row",
        "column",
        "slide",
        "selector",
        "entry_path",
        "field",
    },
    "tool": _COMMON_FIELDS
    | {"action_index", "tool_name", "argument_path"},
}
_DOCUMENT_LOCATORS = frozenset(
    {
        "page",
        "paragraph",
        "table",
        "sheet",
        "cell",
        "row",
        "column",
        "slide",
        "selector",
        "entry_path",
        "field",
    }
)
_CALIBRATION_FIELDS = frozenset(
    {"status", "method", "version", "artifact_hash"}
)
_GRADE_SEVERITY_MAP = {
    "none": "none",
    "info": "none",
    "minor": "low",
    "low": "low",
    "major": "high",
    "medium": "medium",
    "high": "high",
    "critical": "critical",
}


class UnifiedJudgeLabelError(ValueError):
    """Raised when a unified judge label is incomplete or unsafe."""


def build_unified_judge_label(
    *,
    label_id: str,
    case_id: str,
    modality: str,
    passed: bool,
    failure_type: str,
    failure_types: list[str],
    severity: str,
    failed_action: str,
    evidence_locations: list[dict[str, Any]],
    confidence: float,
    failure_probability: float,
    probability_calibration: dict[str, Any],
    release_recommendation: str,
    reason: str,
    judge_id: str,
    judge_version: str,
    model_version: str,
    prompt_version: str,
    input_hash: str,
    output_hash: str,
) -> dict[str, Any]:
    """Build one hash-bound, public-safe A2 judge label."""
    normalized_modality = _enum(modality, VALID_MODALITIES, "modality")
    normalized_failure_type = _failure_class(failure_type, "failure_type")
    normalized_failure_types = _failure_classes(failure_types)
    normalized_severity = _enum(severity, VALID_SEVERITIES, "severity")
    normalized_failed_action = _public_text(
        failed_action,
        "failed_action",
        allow_empty=True,
        max_length=512,
    )
    normalized_evidence = _evidence_locations(
        evidence_locations,
        label_modality=normalized_modality,
    )
    normalized_confidence = _probability(confidence, "confidence")
    normalized_failure_probability = _probability(
        failure_probability,
        "failure_probability",
    )
    calibration = _probability_calibration(probability_calibration)
    recommendation = _enum(
        release_recommendation,
        VALID_RELEASE_RECOMMENDATIONS,
        "release_recommendation",
    )

    _validate_decision_consistency(
        passed=passed,
        failure_type=normalized_failure_type,
        failure_types=normalized_failure_types,
        severity=normalized_severity,
        failed_action=normalized_failed_action,
        failure_probability=normalized_failure_probability,
        calibration_status=calibration["status"],
        release_recommendation=recommendation,
    )

    evidence_hash = stable_hash(normalized_evidence)
    core = {
        "schema_version": SCHEMA_VERSION,
        "label_id": _public_text(label_id, "label_id"),
        "case_id": _public_text(case_id, "case_id"),
        "modality": normalized_modality,
        "label": "pass" if passed else "fail",
        "passed": passed,
        "failure_type": normalized_failure_type,
        "failure_types": normalized_failure_types,
        "severity": normalized_severity,
        "failed_action": normalized_failed_action,
        "evidence_locations": normalized_evidence,
        "confidence": normalized_confidence,
        "failure_probability": normalized_failure_probability,
        "calibrated_failure_probability": (
            normalized_failure_probability
            if calibration["status"] == "calibrated"
            else None
        ),
        "probability_calibration": calibration,
        "release_recommendation": recommendation,
        "reason": _public_text(reason, "reason", max_length=4096),
        "judge_id": _public_text(judge_id, "judge_id"),
        "judge_version": _public_text(judge_version, "judge_version"),
        "model_version": _public_text(model_version, "model_version"),
        "prompt_version": _public_text(prompt_version, "prompt_version"),
        "input_hash": _hash(input_hash, "input_hash"),
        "output_hash": _hash(output_hash, "output_hash"),
        "evidence_hash": evidence_hash,
        "metadata": {
            "public_safe": True,
            "raw_input_recorded": False,
            "raw_output_recorded": False,
            "raw_evidence_recorded": False,
            "automatic_release_authority": recommendation == "allow",
        },
    }
    _validate_public_safe(core)
    return {**core, "label_hash": stable_hash(core)}


def adapt_grade_result_to_unified_label(
    grade_result: GradeResult | dict[str, Any],
    *,
    label_id: str,
    modality: str,
    failed_action: str,
    evidence_locations: list[dict[str, Any]],
    confidence: float,
    failure_probability: float,
    probability_calibration: dict[str, Any],
    release_recommendation: str,
    judge_id: str,
    model_version: str,
    prompt_version: str,
    input_hash: str,
    output_hash: str,
) -> dict[str, Any]:
    """Adapt an existing GradeResult without inventing missing evidence.

    Evidence locations, probability provenance, release recommendation, and
    model/prompt hashes remain explicit caller inputs because legacy
    GradeResult records do not establish those facts.
    """
    source = grade_result.to_dict() if isinstance(grade_result, GradeResult) else grade_result
    if not isinstance(source, dict):
        raise UnifiedJudgeLabelError("grade_result_must_be_object")
    analysis = source.get("failure_analysis")
    if not isinstance(analysis, dict):
        raise UnifiedJudgeLabelError("grade_result_failure_analysis_missing")
    passed = source.get("passed")
    if not isinstance(passed, bool):
        raise UnifiedJudgeLabelError("grade_result_passed_must_be_boolean")
    source_severity = analysis.get("severity")
    if source_severity not in _GRADE_SEVERITY_MAP:
        raise UnifiedJudgeLabelError("grade_result_severity_not_supported")
    failure_type = analysis.get("primary_failure_class")
    failure_types = analysis.get("failure_classes")
    if not isinstance(failure_types, list):
        raise UnifiedJudgeLabelError("grade_result_failure_classes_must_be_list")
    if passed:
        failure_type = "none"
        failure_types = ["none"]
    summary = analysis.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise UnifiedJudgeLabelError("grade_result_summary_missing")
    case_id = source.get("case_id")
    judge_version = source.get("judge_version")
    return build_unified_judge_label(
        label_id=label_id,
        case_id=case_id,
        modality=modality,
        passed=passed,
        failure_type=failure_type,
        failure_types=failure_types,
        severity=_GRADE_SEVERITY_MAP[source_severity],
        failed_action=failed_action,
        evidence_locations=evidence_locations,
        confidence=confidence,
        failure_probability=failure_probability,
        probability_calibration=probability_calibration,
        release_recommendation=release_recommendation,
        reason=summary,
        judge_id=judge_id,
        judge_version=judge_version,
        model_version=model_version,
        prompt_version=prompt_version,
        input_hash=input_hash,
        output_hash=output_hash,
    )


def verify_unified_judge_label(label: dict[str, Any]) -> None:
    """Verify a persisted label by rebuilding it and checking both hashes."""
    if not isinstance(label, dict):
        raise UnifiedJudgeLabelError("label_must_be_object")
    if label.get("schema_version") != SCHEMA_VERSION:
        raise UnifiedJudgeLabelError("unsupported_schema_version")
    declared_label_hash = _hash(label.get("label_hash"), "label_hash")
    expected_fields = {
        "schema_version",
        "label_id",
        "case_id",
        "modality",
        "label",
        "passed",
        "failure_type",
        "failure_types",
        "severity",
        "failed_action",
        "evidence_locations",
        "confidence",
        "failure_probability",
        "calibrated_failure_probability",
        "probability_calibration",
        "release_recommendation",
        "reason",
        "judge_id",
        "judge_version",
        "model_version",
        "prompt_version",
        "input_hash",
        "output_hash",
        "evidence_hash",
        "metadata",
        "label_hash",
    }
    if set(label) != expected_fields:
        raise UnifiedJudgeLabelError("label_fields_mismatch")
    rebuilt = build_unified_judge_label(
        label_id=label["label_id"],
        case_id=label["case_id"],
        modality=label["modality"],
        passed=label["passed"],
        failure_type=label["failure_type"],
        failure_types=label["failure_types"],
        severity=label["severity"],
        failed_action=label["failed_action"],
        evidence_locations=label["evidence_locations"],
        confidence=label["confidence"],
        failure_probability=label["failure_probability"],
        probability_calibration=label["probability_calibration"],
        release_recommendation=label["release_recommendation"],
        reason=label["reason"],
        judge_id=label["judge_id"],
        judge_version=label["judge_version"],
        model_version=label["model_version"],
        prompt_version=label["prompt_version"],
        input_hash=label["input_hash"],
        output_hash=label["output_hash"],
    )
    if rebuilt["evidence_hash"] != label["evidence_hash"]:
        raise UnifiedJudgeLabelError("evidence_hash_mismatch")
    if rebuilt["label_hash"] != declared_label_hash:
        raise UnifiedJudgeLabelError("label_hash_mismatch")
    if rebuilt != label:
        raise UnifiedJudgeLabelError("label_payload_mismatch")


def _evidence_locations(
    value: Any,
    *,
    label_modality: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise UnifiedJudgeLabelError("evidence_locations_must_be_non_empty_list")
    normalized = [
        _evidence_location(item, index=index)
        for index, item in enumerate(value)
    ]
    observed = {item["modality"] for item in normalized}
    if label_modality == "multimodal":
        if len(observed) < 2:
            raise UnifiedJudgeLabelError(
                "multimodal_label_requires_multiple_evidence_modalities"
            )
    elif label_modality not in observed:
        raise UnifiedJudgeLabelError("label_modality_missing_from_evidence")
    return normalized


def _evidence_location(value: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise UnifiedJudgeLabelError(f"evidence_location_{index}_must_be_object")
    modality = _enum(
        value.get("modality"),
        EVIDENCE_MODALITIES,
        f"evidence_location_{index}_modality",
    )
    allowed = _EVIDENCE_ALLOWED_FIELDS[modality]
    if set(value) - allowed:
        raise UnifiedJudgeLabelError(
            f"evidence_location_{index}_contains_unknown_fields"
        )
    source_hash = _hash(
        value.get("source_hash"),
        f"evidence_location_{index}_source_hash",
    )
    normalized = {"modality": modality, "source_hash": source_hash}

    if modality == "text":
        char_pair = _optional_range(value, "start_char", "end_char", index)
        token_pair = _optional_range(value, "start_token", "end_token", index)
        if char_pair is None and token_pair is None:
            raise UnifiedJudgeLabelError(
                f"evidence_location_{index}_text_span_missing"
            )
        if char_pair is not None:
            normalized.update(char_pair)
        if token_pair is not None:
            normalized.update(token_pair)
    elif modality == "image":
        normalized.update(
            {
                "x": _non_negative_number(value.get("x"), f"evidence_location_{index}_x"),
                "y": _non_negative_number(value.get("y"), f"evidence_location_{index}_y"),
                "width": _positive_number(
                    value.get("width"),
                    f"evidence_location_{index}_width",
                ),
                "height": _positive_number(
                    value.get("height"),
                    f"evidence_location_{index}_height",
                ),
                "coordinate_space": _enum(
                    value.get("coordinate_space"),
                    frozenset({"pixels", "normalized"}),
                    f"evidence_location_{index}_coordinate_space",
                ),
            }
        )
        if normalized["coordinate_space"] == "normalized" and any(
            float(normalized[field]) > 1.0
            for field in ("x", "y", "width", "height")
        ):
            raise UnifiedJudgeLabelError(
                f"evidence_location_{index}_normalized_coordinates_out_of_range"
            )
    elif modality == "audio":
        normalized.update(
            _required_range(value, "start_ms", "end_ms", index)
        )
        if "speaker" in value:
            normalized["speaker"] = _public_text(
                value["speaker"],
                f"evidence_location_{index}_speaker",
            )
    elif modality == "video":
        normalized.update(
            _required_range(value, "start_ms", "end_ms", index)
        )
        normalized.update(
            _required_range(value, "start_frame", "end_frame", index)
        )
    elif modality == "document":
        normalized["document_type"] = _enum(
            value.get("document_type"),
            frozenset(
                {"pdf", "docx", "xlsx", "pptx", "csv", "html", "archive", "other"}
            ),
            f"evidence_location_{index}_document_type",
        )
        locators = [field for field in _DOCUMENT_LOCATORS if field in value]
        if not locators:
            raise UnifiedJudgeLabelError(
                f"evidence_location_{index}_document_locator_missing"
            )
        for field in sorted(locators):
            item = value[field]
            if field in {"page", "paragraph", "table", "row", "column", "slide"}:
                normalized[field] = _non_negative_integer(
                    item,
                    f"evidence_location_{index}_{field}",
                )
            else:
                normalized[field] = _public_text(
                    item,
                    f"evidence_location_{index}_{field}",
                )
    elif modality == "tool":
        normalized.update(
            {
                "action_index": _non_negative_integer(
                    value.get("action_index"),
                    f"evidence_location_{index}_action_index",
                ),
                "tool_name": _public_text(
                    value.get("tool_name"),
                    f"evidence_location_{index}_tool_name",
                ),
            }
        )
        if "argument_path" in value:
            normalized["argument_path"] = _public_text(
                value["argument_path"],
                f"evidence_location_{index}_argument_path",
            )
    return normalized


def _probability_calibration(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _CALIBRATION_FIELDS:
        raise UnifiedJudgeLabelError("probability_calibration_fields_mismatch")
    status = _enum(
        value.get("status"),
        VALID_CALIBRATION_STATUSES,
        "probability_calibration_status",
    )
    method = _public_text(
        value.get("method"),
        "probability_calibration_method",
        allow_empty=True,
    )
    version = _public_text(
        value.get("version"),
        "probability_calibration_version",
        allow_empty=True,
    )
    artifact_hash = value.get("artifact_hash")
    if status == "calibrated":
        if not method or not version:
            raise UnifiedJudgeLabelError("calibrated_probability_provenance_missing")
        artifact_hash = _hash(
            artifact_hash,
            "probability_calibration_artifact_hash",
        )
    elif method or version or artifact_hash is not None:
        raise UnifiedJudgeLabelError(
            "uncalibrated_probability_has_calibration_provenance"
        )
    return {
        "status": status,
        "method": method,
        "version": version,
        "artifact_hash": artifact_hash,
    }


def _validate_decision_consistency(
    *,
    passed: Any,
    failure_type: str,
    failure_types: list[str],
    severity: str,
    failed_action: str,
    failure_probability: float,
    calibration_status: str,
    release_recommendation: str,
) -> None:
    if not isinstance(passed, bool):
        raise UnifiedJudgeLabelError("passed_must_be_boolean")
    if passed:
        if failure_type != "none" or failure_types != ["none"]:
            raise UnifiedJudgeLabelError("pass_has_failure_class")
        if severity != "none":
            raise UnifiedJudgeLabelError("pass_has_failure_severity")
        if failed_action:
            raise UnifiedJudgeLabelError("pass_has_failed_action")
        if failure_probability >= 0.5:
            raise UnifiedJudgeLabelError("pass_probability_crosses_failure_threshold")
    else:
        if failure_type == "none" or "none" in failure_types:
            raise UnifiedJudgeLabelError("fail_missing_failure_class")
        if failure_type not in failure_types:
            raise UnifiedJudgeLabelError("primary_failure_not_in_failure_types")
        if severity == "none":
            raise UnifiedJudgeLabelError("fail_missing_severity")
        if not failed_action:
            raise UnifiedJudgeLabelError("fail_missing_failed_action")
        if failure_probability < 0.5:
            raise UnifiedJudgeLabelError("fail_probability_below_failure_threshold")
        if release_recommendation == "allow":
            raise UnifiedJudgeLabelError("failed_label_cannot_recommend_allow")
        if severity in {"high", "critical"} and release_recommendation == "staged_rollout":
            raise UnifiedJudgeLabelError(
                "high_risk_failure_cannot_recommend_staged_rollout"
            )
        if severity == "critical" and release_recommendation not in {
            "human_review",
            "block",
        }:
            raise UnifiedJudgeLabelError(
                "critical_failure_requires_review_or_block"
            )
    if calibration_status == "uncalibrated" and release_recommendation == "allow":
        raise UnifiedJudgeLabelError(
            "uncalibrated_probability_cannot_authorize_release"
        )


def _failure_classes(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise UnifiedJudgeLabelError("failure_types_must_be_non_empty_list")
    normalized = [
        _failure_class(item, f"failure_types_{index}")
        for index, item in enumerate(value)
    ]
    if len(set(normalized)) != len(normalized):
        raise UnifiedJudgeLabelError("duplicate_failure_type")
    return normalized


def _failure_class(value: Any, field: str) -> str:
    return _enum(value, VALID_FAILURE_CLASSES, field)


def _optional_range(
    value: dict[str, Any],
    start_field: str,
    end_field: str,
    index: int,
) -> dict[str, int] | None:
    has_start = start_field in value
    has_end = end_field in value
    if has_start != has_end:
        raise UnifiedJudgeLabelError(
            f"evidence_location_{index}_{start_field}_{end_field}_pair_incomplete"
        )
    if not has_start:
        return None
    return _required_range(value, start_field, end_field, index)


def _required_range(
    value: dict[str, Any],
    start_field: str,
    end_field: str,
    index: int,
) -> dict[str, int]:
    start = _non_negative_integer(
        value.get(start_field),
        f"evidence_location_{index}_{start_field}",
    )
    end = _non_negative_integer(
        value.get(end_field),
        f"evidence_location_{index}_{end_field}",
    )
    if end <= start:
        raise UnifiedJudgeLabelError(
            f"evidence_location_{index}_{start_field}_{end_field}_range_invalid"
        )
    return {start_field: start, end_field: end}


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise UnifiedJudgeLabelError(f"{field}_must_be_sha256")
    return value


def _enum(value: Any, allowed: frozenset[str], field: str) -> str:
    if value not in allowed:
        raise UnifiedJudgeLabelError(f"{field}_not_supported")
    return str(value)


def _public_text(
    value: Any,
    field: str,
    *,
    allow_empty: bool = False,
    max_length: int = 256,
) -> str:
    if not isinstance(value, str):
        raise UnifiedJudgeLabelError(f"{field}_must_be_string")
    normalized = value.strip()
    if not allow_empty and not normalized:
        raise UnifiedJudgeLabelError(f"{field}_must_not_be_empty")
    if len(normalized) > max_length:
        raise UnifiedJudgeLabelError(f"{field}_too_long")
    _validate_public_safe(normalized)
    return normalized


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UnifiedJudgeLabelError(f"{field}_must_be_number")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise UnifiedJudgeLabelError(f"{field}_must_be_probability")
    return normalized


def _non_negative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnifiedJudgeLabelError(f"{field}_must_be_non_negative_integer")
    return value


def _non_negative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UnifiedJudgeLabelError(f"{field}_must_be_non_negative_number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise UnifiedJudgeLabelError(f"{field}_must_be_non_negative_number")
    return normalized


def _positive_number(value: Any, field: str) -> float:
    normalized = _non_negative_number(value, field)
    if normalized <= 0:
        raise UnifiedJudgeLabelError(f"{field}_must_be_positive_number")
    return normalized


def _validate_public_safe(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_public_safe(str(key))
            _validate_public_safe(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_public_safe(item)
        return
    if not isinstance(value, str):
        return
    for pattern in PUBLIC_TEXT_PATTERNS:
        if pattern.search(value):
            raise UnifiedJudgeLabelError("private_or_secret_material_rejected")
