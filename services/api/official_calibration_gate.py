"""Public-safe planning and quota-change gates for official API calibration.

The types in this module cannot execute network requests.  They accept only
redacted status metadata, response field names, quota-presence booleans, and
references to ignored private evidence.  Every mutation phase fails closed
unless a newer private evidence reference carries changed quota booleans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


PUBLIC_OBSERVATION_SCHEMA_VERSION = "ashr.clone.public_calibration_observation.v1"
MUTATION_PLAN_SCHEMA_VERSION = "ashr.clone.calibration_mutation_plan.v1"
PRIVATE_EVIDENCE_ROOT = PurePosixPath("docs/evidence/private_refs")
CALIBRATION_MODALITIES = ("audio", "file", "image", "text", "video")
QUOTA_BOOLEAN_FIELDS = (
    "blocked",
    "limit_present",
    "used_present",
    "requested_present",
    "remaining_present",
    "reset_present",
    "resource_present",
)
PHASE_CALL_LIMITS = {"small_batch": 3, "batch": 80}

_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_STATUS_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_RESPONSE_KEY_RE = re.compile(r"^[_A-Za-z][_A-Za-z0-9.-]{0,127}$")
_PRIVATE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,191}\.json$")

_OBSERVATION_KEYS = frozenset(
    {
        "schema_version",
        "operation",
        "status",
        "status_code",
        "response_keys",
        "quota",
        "private_evidence_ref",
    }
)
_QUOTA_KEYS = frozenset(QUOTA_BOOLEAN_FIELDS)
_SUCCESS_STATUSES = frozenset({"available", "ok", "success"})


class CalibrationGateError(ValueError):
    """Raised when public calibration evidence is unsafe or ambiguous."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class QuotaBooleanEvidence:
    """Value-free quota evidence safe for a public planning artifact."""

    blocked: bool
    limit_present: bool
    used_present: bool
    requested_present: bool
    remaining_present: bool
    reset_present: bool
    resource_present: bool

    def __post_init__(self) -> None:
        for name, value in self.as_dict().items():
            if not isinstance(value, bool):
                raise CalibrationGateError(
                    "invalid_quota_boolean", f"quota.{name} must be a boolean"
                )

    def as_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in QUOTA_BOOLEAN_FIELDS}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "QuotaBooleanEvidence":
        if not isinstance(value, Mapping) or frozenset(value) != _QUOTA_KEYS:
            raise CalibrationGateError(
                "quota_shape_mismatch", "quota evidence must contain only boolean presence fields"
            )
        return cls(**{name: value[name] for name in QUOTA_BOOLEAN_FIELDS})


@dataclass(frozen=True)
class PublicCalibrationObservation:
    """Strict public projection of one private official API observation."""

    operation: str
    status: str
    status_code: int | None
    response_keys: tuple[str, ...]
    quota: QuotaBooleanEvidence
    private_evidence_ref: str

    def __post_init__(self) -> None:
        _validate_operation(self.operation)
        if not isinstance(self.status, str) or not _STATUS_RE.fullmatch(self.status):
            raise CalibrationGateError(
                "invalid_status", "status must be a lowercase public status label"
            )
        if self.status_code is not None and (
            isinstance(self.status_code, bool)
            or not isinstance(self.status_code, int)
            or self.status_code < 100
            or self.status_code > 599
        ):
            raise CalibrationGateError(
                "invalid_status_code", "status_code must be null or an HTTP status code"
            )
        if not isinstance(self.response_keys, tuple):
            raise CalibrationGateError(
                "invalid_response_keys", "response_keys must be a tuple"
            )
        if len(self.response_keys) > 256:
            raise CalibrationGateError(
                "response_key_limit_exceeded", "response_keys exceeds the public-safe limit"
            )
        if len(self.response_keys) != len(set(self.response_keys)):
            raise CalibrationGateError(
                "duplicate_response_key", "response_keys must not contain duplicates"
            )
        for key in self.response_keys:
            if not isinstance(key, str) or not _RESPONSE_KEY_RE.fullmatch(key):
                raise CalibrationGateError(
                    "invalid_response_key", "response_keys may contain field names only"
                )
        if not isinstance(self.quota, QuotaBooleanEvidence):
            raise CalibrationGateError(
                "invalid_quota", "quota must be QuotaBooleanEvidence"
            )
        _validate_private_evidence_ref(self.private_evidence_ref)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_OBSERVATION_SCHEMA_VERSION,
            "operation": self.operation,
            "status": self.status,
            "status_code": self.status_code,
            "response_keys": sorted(self.response_keys),
            "quota": self.quota.as_dict(),
            "private_evidence_ref": self.private_evidence_ref,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PublicCalibrationObservation":
        validate_public_calibration_observation(value)
        return cls(
            operation=value["operation"],
            status=value["status"],
            status_code=value["status_code"],
            response_keys=tuple(value["response_keys"]),
            quota=QuotaBooleanEvidence.from_mapping(value["quota"]),
            private_evidence_ref=value["private_evidence_ref"],
        )


def build_public_calibration_observation(
    *,
    operation: str,
    status: str,
    status_code: int | None,
    response_keys: Sequence[str],
    quota: QuotaBooleanEvidence,
    private_evidence_ref: str,
) -> dict[str, Any]:
    """Build a value-free public projection; raw response input is impossible."""

    observation = PublicCalibrationObservation(
        operation=operation,
        status=status,
        status_code=status_code,
        response_keys=tuple(response_keys),
        quota=quota,
        private_evidence_ref=private_evidence_ref,
    )
    return observation.as_dict()


def validate_public_calibration_observation(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or frozenset(value) != _OBSERVATION_KEYS:
        raise CalibrationGateError(
            "observation_shape_mismatch",
            "public observation contains a missing or non-public field",
        )
    if value["schema_version"] != PUBLIC_OBSERVATION_SCHEMA_VERSION:
        raise CalibrationGateError(
            "observation_schema_mismatch", "unsupported public observation schema"
        )
    response_keys = value["response_keys"]
    if not isinstance(response_keys, list) or response_keys != sorted(response_keys):
        raise CalibrationGateError(
            "non_canonical_response_keys", "response_keys must be a canonical sorted array"
        )
    PublicCalibrationObservation(
        operation=value["operation"],
        status=value["status"],
        status_code=value["status_code"],
        response_keys=tuple(response_keys),
        quota=QuotaBooleanEvidence.from_mapping(value["quota"]),
        private_evidence_ref=value["private_evidence_ref"],
    )


def build_mutation_plan(
    *,
    operation: str,
    phase: str,
    modalities: Sequence[str],
    estimated_calls: int,
    dry_run_reviewed: bool,
    previous_quota_evidence: PublicCalibrationObservation,
    current_quota_evidence: PublicCalibrationObservation,
    small_batch_receipt: PublicCalibrationObservation | None = None,
) -> dict[str, Any]:
    """Return a non-executing mutation plan with an unbypassable quota gate."""

    plan = _compute_mutation_plan(
        operation=operation,
        phase=phase,
        modalities=modalities,
        estimated_calls=estimated_calls,
        dry_run_reviewed=dry_run_reviewed,
        previous_quota_evidence=previous_quota_evidence,
        current_quota_evidence=current_quota_evidence,
        small_batch_receipt=small_batch_receipt,
    )
    validate_mutation_plan(plan)
    return plan


def _compute_mutation_plan(
    *,
    operation: str,
    phase: str,
    modalities: Sequence[str],
    estimated_calls: int,
    dry_run_reviewed: bool,
    previous_quota_evidence: PublicCalibrationObservation,
    current_quota_evidence: PublicCalibrationObservation,
    small_batch_receipt: PublicCalibrationObservation | None = None,
) -> dict[str, Any]:
    _validate_operation(operation)
    if phase not in PHASE_CALL_LIMITS:
        raise CalibrationGateError(
            "invalid_phase", "phase must be small_batch or batch"
        )
    selected_modalities = _validated_modalities(modalities)
    if isinstance(estimated_calls, bool) or not isinstance(estimated_calls, int):
        raise CalibrationGateError(
            "invalid_estimated_calls", "estimated_calls must be an integer"
        )
    if estimated_calls < 1 or estimated_calls > PHASE_CALL_LIMITS[phase]:
        raise CalibrationGateError(
            "phase_call_limit_exceeded",
            f"estimated_calls must be between 1 and {PHASE_CALL_LIMITS[phase]} for {phase}",
        )
    if not isinstance(dry_run_reviewed, bool):
        raise CalibrationGateError(
            "invalid_dry_run_review", "dry_run_reviewed must be a boolean"
        )
    for name, evidence in (
        ("previous_quota_evidence", previous_quota_evidence),
        ("current_quota_evidence", current_quota_evidence),
    ):
        if not isinstance(evidence, PublicCalibrationObservation):
            raise CalibrationGateError(
                "invalid_observation", f"{name} must be PublicCalibrationObservation"
            )
    if small_batch_receipt is not None and not isinstance(
        small_batch_receipt, PublicCalibrationObservation
    ):
        raise CalibrationGateError(
            "invalid_small_batch_receipt",
            "small_batch_receipt must be PublicCalibrationObservation",
        )

    reasons: list[str] = []
    for label, evidence in (
        ("previous", previous_quota_evidence),
        ("current", current_quota_evidence),
    ):
        if evidence.operation != operation:
            reasons.append(f"{label}_operation_mismatch")
    if not dry_run_reviewed:
        reasons.append("dry_run_not_reviewed")
    if previous_quota_evidence.private_evidence_ref == current_quota_evidence.private_evidence_ref:
        reasons.append("quota_evidence_reference_unchanged")

    previous_quota = previous_quota_evidence.quota.as_dict()
    current_quota = current_quota_evidence.quota.as_dict()
    changed_fields = sorted(
        name for name in QUOTA_BOOLEAN_FIELDS if previous_quota[name] != current_quota[name]
    )
    if not changed_fields:
        reasons.append("quota_booleans_unchanged")
    if current_quota_evidence.quota.blocked:
        reasons.append("current_quota_blocked")
    if not _observation_succeeded(current_quota_evidence):
        reasons.append("current_quota_observation_not_successful")

    if phase == "batch":
        if small_batch_receipt is None:
            reasons.append("small_batch_receipt_required")
        else:
            if small_batch_receipt.operation != operation:
                reasons.append("small_batch_operation_mismatch")
            if not _observation_succeeded(small_batch_receipt):
                reasons.append("small_batch_not_successful")
            if small_batch_receipt.quota.blocked:
                reasons.append("small_batch_quota_blocked")
            if small_batch_receipt.private_evidence_ref in {
                previous_quota_evidence.private_evidence_ref,
                current_quota_evidence.private_evidence_ref,
            }:
                reasons.append("small_batch_evidence_not_independent")
    elif small_batch_receipt is not None:
        reasons.append("unexpected_small_batch_receipt")

    gate_decision = "go" if not reasons else "stop"
    plan: dict[str, Any] = {
        "schema_version": MUTATION_PLAN_SCHEMA_VERSION,
        "operation": operation,
        "phase": phase,
        "modalities": selected_modalities,
        "estimated_calls": estimated_calls,
        "dry_run": {"reviewed": dry_run_reviewed},
        "quota_evidence": {
            "previous": previous_quota_evidence.as_dict(),
            "current": current_quota_evidence.as_dict(),
            "changed": bool(changed_fields),
            "changed_boolean_fields": changed_fields,
            "private_reference_changed": (
                previous_quota_evidence.private_evidence_ref
                != current_quota_evidence.private_evidence_ref
            ),
        },
        "phase_prerequisite": {
            "small_batch_receipt_required": phase == "batch",
            "small_batch_receipt": (
                small_batch_receipt.as_dict() if small_batch_receipt is not None else None
            ),
        },
        "gate": {
            "decision": gate_decision,
            "reasons": reasons,
            "mutation_authorized": gate_decision == "go",
            "override_permitted": False,
            "network_called": False,
        },
        "public_safety": {
            "raw_request_included": False,
            "raw_response_included": False,
            "response_values_included": False,
            "headers_included": False,
            "secret_values_included": False,
            "private_evidence_contents_included": False,
            "private_evidence_references_only": True,
        },
    }
    return plan


def validate_mutation_plan(plan: Mapping[str, Any]) -> None:
    """Recompute a plan and reject edits to a gate decision or safety claim."""

    expected_keys = {
        "schema_version",
        "operation",
        "phase",
        "modalities",
        "estimated_calls",
        "dry_run",
        "quota_evidence",
        "phase_prerequisite",
        "gate",
        "public_safety",
    }
    if not isinstance(plan, Mapping) or set(plan) != expected_keys:
        raise CalibrationGateError("plan_shape_mismatch", "mutation plan shape is invalid")
    if plan["schema_version"] != MUTATION_PLAN_SCHEMA_VERSION:
        raise CalibrationGateError("plan_schema_mismatch", "unsupported mutation plan schema")
    quota_evidence = plan["quota_evidence"]
    phase_prerequisite = plan["phase_prerequisite"]
    if not isinstance(quota_evidence, Mapping) or not isinstance(phase_prerequisite, Mapping):
        raise CalibrationGateError("plan_shape_mismatch", "mutation plan evidence is invalid")
    previous = PublicCalibrationObservation.from_mapping(quota_evidence.get("previous"))
    current = PublicCalibrationObservation.from_mapping(quota_evidence.get("current"))
    receipt_value = phase_prerequisite.get("small_batch_receipt")
    receipt = (
        PublicCalibrationObservation.from_mapping(receipt_value)
        if receipt_value is not None
        else None
    )

    expected = _compute_mutation_plan(
        operation=plan["operation"],
        phase=plan["phase"],
        modalities=plan["modalities"],
        estimated_calls=plan["estimated_calls"],
        dry_run_reviewed=_mapping_bool(plan["dry_run"], "reviewed"),
        previous_quota_evidence=previous,
        current_quota_evidence=current,
        small_batch_receipt=receipt,
    )
    if dict(plan) != expected:
        raise CalibrationGateError(
            "plan_recomputation_mismatch", "mutation plan does not match recomputed gate"
        )
def _observation_succeeded(observation: PublicCalibrationObservation) -> bool:
    return (
        observation.status in _SUCCESS_STATUSES
        and observation.status_code is not None
        and 200 <= observation.status_code < 300
    )


def _validated_modalities(value: Sequence[str]) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CalibrationGateError("invalid_modalities", "modalities must be a sequence")
    result = list(value)
    if not result:
        raise CalibrationGateError("missing_modalities", "at least one modality is required")
    if len(result) != len(set(result)):
        raise CalibrationGateError("duplicate_modality", "modalities contains a duplicate")
    for modality in result:
        if modality not in CALIBRATION_MODALITIES:
            raise CalibrationGateError(
                "invalid_modality", f"unsupported calibration modality: {modality!r}"
            )
    return sorted(result)


def _validate_operation(value: Any) -> None:
    if not isinstance(value, str) or not _OPERATION_RE.fullmatch(value):
        raise CalibrationGateError("invalid_operation", "operation is invalid")


def _validate_private_evidence_ref(value: Any) -> None:
    if not isinstance(value, str) or "\\" in value or "%" in value or "://" in value:
        raise CalibrationGateError(
            "unsafe_private_evidence_ref",
            "private_evidence_ref must be a repository-relative private JSON reference",
        )
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise CalibrationGateError(
            "unsafe_private_evidence_ref", "private_evidence_ref traversal is rejected"
        )
    root_parts = PRIVATE_EVIDENCE_ROOT.parts
    if path.parts[: len(root_parts)] != root_parts or len(path.parts) != len(root_parts) + 1:
        raise CalibrationGateError(
            "unsafe_private_evidence_ref",
            "private_evidence_ref must point directly under docs/evidence/private_refs",
        )
    if not _PRIVATE_FILENAME_RE.fullmatch(path.name):
        raise CalibrationGateError(
            "unsafe_private_evidence_ref", "private evidence filename is invalid"
        )


def _mapping_bool(value: Any, key: str) -> bool:
    if not isinstance(value, Mapping) or set(value) != {key} or not isinstance(value[key], bool):
        raise CalibrationGateError("plan_shape_mismatch", f"{key} block is invalid")
    return value[key]


__all__ = [
    "CALIBRATION_MODALITIES",
    "MUTATION_PLAN_SCHEMA_VERSION",
    "PHASE_CALL_LIMITS",
    "PRIVATE_EVIDENCE_ROOT",
    "PUBLIC_OBSERVATION_SCHEMA_VERSION",
    "QUOTA_BOOLEAN_FIELDS",
    "CalibrationGateError",
    "PublicCalibrationObservation",
    "QuotaBooleanEvidence",
    "build_mutation_plan",
    "build_public_calibration_observation",
    "validate_mutation_plan",
    "validate_public_calibration_observation",
]
