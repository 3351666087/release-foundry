"""Held-out probability-calibration metrics and qualification gate for A2."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Any

from .result_persistence import stable_hash
from .unified_label import VALID_MODALITIES, VALID_SEVERITIES


SCHEMA_VERSION = "a2.probability_calibration_report.v1"
ARTIFACT_SCHEMA_VERSION = "a2.probability_calibration_artifact.v1"
MANIFEST_SCHEMA_VERSION = "a2.probability_calibration_holdout.v1"
OBSERVATION_SCHEMA_VERSION = "a2.probability_calibration_observation.v1"
DEFAULT_ECE_THRESHOLD = 0.03
DEFAULT_MINIMUM_CASES = 1000
DEFAULT_MINIMUM_CLASS_CASES = 100
DEFAULT_BIN_COUNT = 10

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
VALID_METHODS = frozenset(
    {"isotonic", "platt", "temperature_scaling", "histogram_binning"}
)

_ARTIFACT_FIELDS = frozenset(
    {
        "schema_version",
        "calibrator_id",
        "calibrator_version",
        "method",
        "model_version",
        "fit_dataset_id",
        "fit_dataset_hash",
        "fit_source_group_hashes",
        "fitted_parameter_hash",
        "fit_receipt_hash",
        "fit_receipt_verified",
        "created_at",
        "artifact_hash",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_id",
        "dataset_id",
        "dataset_hash",
        "split",
        "gold_authority",
        "gold_receipt_hash",
        "gold_receipt_verified",
        "source_isolation_policy_hash",
        "source_isolation_receipt_hash",
        "source_isolation_verified",
        "cases",
        "manifest_hash",
    }
)
_CASE_FIELDS = frozenset(
    {
        "case_id",
        "source_hash",
        "source_group_hash",
        "modality",
        "severity",
        "failed",
    }
)
_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "case_id",
        "source_hash",
        "model_version",
        "calibrator_version",
        "failure_probability",
        "prediction_hash",
    }
)


class ProbabilityCalibrationError(ValueError):
    """Raised when calibration evidence is incomplete, mismatched, or unsafe."""


def build_probability_calibration_report(
    *,
    calibration_artifact: dict[str, Any],
    holdout_manifest: dict[str, Any],
    observations: list[dict[str, Any]],
    report_id: str = "a2_probability_calibration",
    bin_count: int = DEFAULT_BIN_COUNT,
    ece_threshold: float = DEFAULT_ECE_THRESHOLD,
    minimum_cases: int = DEFAULT_MINIMUM_CASES,
    minimum_class_cases: int = DEFAULT_MINIMUM_CLASS_CASES,
) -> dict[str, Any]:
    """Evaluate one immutable calibrated model on human-gold held-out cases."""
    artifact = _validate_artifact(calibration_artifact)
    manifest_cases = _validate_manifest(holdout_manifest)
    normalized_observations = _validate_observations(
        observations,
        artifact=artifact,
        manifest_cases=manifest_cases,
    )
    _validate_source_isolation(artifact, manifest_cases)
    normalized_bin_count = _positive_integer(bin_count, "bin_count")
    normalized_ece_threshold = _threshold(ece_threshold, "ece_threshold")
    normalized_minimum_cases = _positive_integer(minimum_cases, "minimum_cases")
    normalized_minimum_class_cases = _positive_integer(
        minimum_class_cases,
        "minimum_class_cases",
    )

    joined = [
        {
            **manifest_cases[observation["case_id"]],
            "failure_probability": observation["failure_probability"],
            "prediction_hash": observation["prediction_hash"],
        }
        for observation in normalized_observations
    ]
    overall = _metrics(
        [
            (item["failure_probability"], int(item["failed"]))
            for item in joined
        ],
        bin_count=normalized_bin_count,
    )
    failed_cases = [item for item in joined if item["failed"]]
    passed_cases = [item for item in joined if not item["failed"]]
    class_conditional = {
        "fail": _metrics(
            [(item["failure_probability"], 1) for item in failed_cases],
            bin_count=normalized_bin_count,
        ),
        "pass": _metrics(
            [(1.0 - item["failure_probability"], 1) for item in passed_cases],
            bin_count=normalized_bin_count,
        ),
    }
    per_modality = {
        modality: _metrics(
            [
                (item["failure_probability"], int(item["failed"]))
                for item in joined
                if item["modality"] == modality
            ],
            bin_count=normalized_bin_count,
        )
        for modality in sorted({item["modality"] for item in joined})
    }
    per_severity = {
        severity: _metrics(
            [
                (item["failure_probability"], int(item["failed"]))
                for item in joined
                if item["severity"] == severity
            ],
            bin_count=normalized_bin_count,
        )
        for severity in sorted({item["severity"] for item in joined})
    }
    blockers = _qualification_blockers(
        overall=overall,
        class_conditional=class_conditional,
        case_count=len(joined),
        failed_count=len(failed_cases),
        passed_count=len(passed_cases),
        ece_threshold=normalized_ece_threshold,
        minimum_cases=normalized_minimum_cases,
        minimum_class_cases=normalized_minimum_class_cases,
        artifact=artifact,
        holdout_manifest=holdout_manifest,
    )
    report_without_hash = {
        "schema_version": SCHEMA_VERSION,
        "report_id": _required_text(report_id, "report_id"),
        "calibrator": {
            "calibrator_id": artifact["calibrator_id"],
            "calibrator_version": artifact["calibrator_version"],
            "method": artifact["method"],
            "model_version": artifact["model_version"],
            "artifact_hash": artifact["artifact_hash"],
            "fitted_parameter_hash": artifact["fitted_parameter_hash"],
            "fit_dataset_id": artifact["fit_dataset_id"],
            "fit_dataset_hash": artifact["fit_dataset_hash"],
            "fit_receipt_hash": artifact["fit_receipt_hash"],
            "fit_receipt_verified": artifact["fit_receipt_verified"],
        },
        "holdout": {
            "manifest_id": holdout_manifest["manifest_id"],
            "manifest_hash": holdout_manifest["manifest_hash"],
            "dataset_id": holdout_manifest["dataset_id"],
            "dataset_hash": holdout_manifest["dataset_hash"],
            "case_count": len(joined),
            "failed_count": len(failed_cases),
            "passed_count": len(passed_cases),
            "gold_authority": holdout_manifest["gold_authority"],
            "gold_receipt_hash": holdout_manifest["gold_receipt_hash"],
            "gold_receipt_verified": holdout_manifest["gold_receipt_verified"],
            "source_isolation_receipt_hash": holdout_manifest[
                "source_isolation_receipt_hash"
            ],
            "source_isolation_verified": holdout_manifest[
                "source_isolation_verified"
            ],
        },
        "thresholds": {
            "ece": normalized_ece_threshold,
            "minimum_cases": normalized_minimum_cases,
            "minimum_class_cases": normalized_minimum_class_cases,
            "bin_count": normalized_bin_count,
        },
        "metrics": {
            "overall": overall,
            "class_conditional": class_conditional,
            "per_modality": per_modality,
            "per_severity": per_severity,
        },
        "calibration_gate": {
            "status": "calibrated" if not blockers else "uncalibrated",
            "eligible_for_unified_label_calibrated_status": not blockers,
            "blockers": blockers,
            "automatic_model_promotion_allowed": False,
            "requires_blind_version_comparison": True,
        },
        "observation_bindings": [
            {
                "case_id": item["case_id"],
                "source_hash": item["source_hash"],
                "source_group_hash": item["source_group_hash"],
                "prediction_hash": item["prediction_hash"],
            }
            for item in sorted(joined, key=lambda candidate: candidate["case_id"])
        ],
        "metadata": {
            "public_safe": True,
            "deterministic": True,
            "raw_inputs_recorded": False,
            "raw_outputs_recorded": False,
            "does_not_fit_or_promote_models": True,
            "calibration_requires_human_gold": True,
            "train_holdout_source_overlap_allowed": False,
        },
    }
    return {
        **report_without_hash,
        "report_hash": stable_hash(report_without_hash),
    }


def _validate_artifact(value: Any) -> dict[str, Any]:
    _exact_fields(value, _ARTIFACT_FIELDS, "calibration_artifact")
    if value["schema_version"] != ARTIFACT_SCHEMA_VERSION:
        raise ProbabilityCalibrationError("unsupported_artifact_schema_version")
    _verify_self_hash(value, "artifact_hash", "calibration_artifact")
    method = _enum(value["method"], VALID_METHODS, "calibration_method")
    fit_sources = _hash_list(
        value["fit_source_group_hashes"],
        "fit_source_group_hashes",
    )
    return {
        **value,
        "calibrator_id": _required_text(value["calibrator_id"], "calibrator_id"),
        "calibrator_version": _required_text(
            value["calibrator_version"],
            "calibrator_version",
        ),
        "method": method,
        "model_version": _required_text(value["model_version"], "model_version"),
        "fit_dataset_id": _required_text(
            value["fit_dataset_id"],
            "fit_dataset_id",
        ),
        "fit_dataset_hash": _hash(value["fit_dataset_hash"], "fit_dataset_hash"),
        "fit_source_group_hashes": fit_sources,
        "fitted_parameter_hash": _hash(
            value["fitted_parameter_hash"],
            "fitted_parameter_hash",
        ),
        "fit_receipt_hash": _hash(
            value["fit_receipt_hash"],
            "fit_receipt_hash",
        ),
        "fit_receipt_verified": _boolean(
            value["fit_receipt_verified"],
            "fit_receipt_verified",
        ),
        "created_at": _required_text(value["created_at"], "created_at"),
    }


def _validate_manifest(value: Any) -> dict[str, dict[str, Any]]:
    _exact_fields(value, _MANIFEST_FIELDS, "holdout_manifest")
    if value["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ProbabilityCalibrationError("unsupported_manifest_schema_version")
    _verify_self_hash(value, "manifest_hash", "holdout_manifest")
    _required_text(value["manifest_id"], "manifest_id")
    _required_text(value["dataset_id"], "dataset_id")
    _hash(value["dataset_hash"], "dataset_hash")
    if value["split"] != "holdout":
        raise ProbabilityCalibrationError("calibration_manifest_must_be_holdout")
    if value["gold_authority"] != "human_adjudicated":
        raise ProbabilityCalibrationError("holdout_gold_must_be_human_adjudicated")
    _hash(value["gold_receipt_hash"], "gold_receipt_hash")
    _boolean(value["gold_receipt_verified"], "gold_receipt_verified")
    _hash(
        value["source_isolation_policy_hash"],
        "source_isolation_policy_hash",
    )
    _hash(
        value["source_isolation_receipt_hash"],
        "source_isolation_receipt_hash",
    )
    _boolean(value["source_isolation_verified"], "source_isolation_verified")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases:
        raise ProbabilityCalibrationError("holdout_cases_must_be_non_empty_list")
    normalized: dict[str, dict[str, Any]] = {}
    source_hashes: set[str] = set()
    for index, case in enumerate(cases):
        _exact_fields(case, _CASE_FIELDS, f"holdout_case_{index}")
        case_id = _required_text(case["case_id"], f"holdout_case_{index}_case_id")
        if case_id in normalized:
            raise ProbabilityCalibrationError("duplicate_holdout_case_id")
        source_hash = _hash(
            case["source_hash"],
            f"holdout_case_{index}_source_hash",
        )
        if source_hash in source_hashes:
            raise ProbabilityCalibrationError("duplicate_holdout_source_hash")
        source_hashes.add(source_hash)
        failed = _boolean(case["failed"], f"holdout_case_{index}_failed")
        severity = _enum(
            case["severity"],
            VALID_SEVERITIES,
            f"holdout_case_{index}_severity",
        )
        if failed and severity == "none":
            raise ProbabilityCalibrationError("failed_holdout_case_missing_severity")
        if not failed and severity != "none":
            raise ProbabilityCalibrationError("passed_holdout_case_has_severity")
        normalized[case_id] = {
            "case_id": case_id,
            "source_hash": source_hash,
            "source_group_hash": _hash(
                case["source_group_hash"],
                f"holdout_case_{index}_source_group_hash",
            ),
            "modality": _enum(
                case["modality"],
                VALID_MODALITIES,
                f"holdout_case_{index}_modality",
            ),
            "severity": severity,
            "failed": failed,
        }
    return normalized


def _validate_observations(
    value: Any,
    *,
    artifact: dict[str, Any],
    manifest_cases: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProbabilityCalibrationError("observations_must_be_list")
    normalized = []
    seen: set[str] = set()
    for index, observation in enumerate(value):
        _exact_fields(
            observation,
            _OBSERVATION_FIELDS,
            f"observation_{index}",
        )
        if observation["schema_version"] != OBSERVATION_SCHEMA_VERSION:
            raise ProbabilityCalibrationError(
                "unsupported_observation_schema_version"
            )
        _verify_self_hash(
            observation,
            "prediction_hash",
            f"observation_{index}",
        )
        case_id = _required_text(
            observation["case_id"],
            f"observation_{index}_case_id",
        )
        if case_id in seen:
            raise ProbabilityCalibrationError("duplicate_observation_case_id")
        if case_id not in manifest_cases:
            raise ProbabilityCalibrationError("observation_case_not_in_manifest")
        seen.add(case_id)
        source_hash = _hash(
            observation["source_hash"],
            f"observation_{index}_source_hash",
        )
        if source_hash != manifest_cases[case_id]["source_hash"]:
            raise ProbabilityCalibrationError("observation_source_hash_mismatch")
        if observation["model_version"] != artifact["model_version"]:
            raise ProbabilityCalibrationError("observation_model_version_mismatch")
        if observation["calibrator_version"] != artifact["calibrator_version"]:
            raise ProbabilityCalibrationError(
                "observation_calibrator_version_mismatch"
            )
        normalized.append(
            {
                **observation,
                "failure_probability": _probability(
                    observation["failure_probability"],
                    f"observation_{index}_failure_probability",
                ),
            }
        )
    if seen != set(manifest_cases):
        raise ProbabilityCalibrationError("observation_case_coverage_mismatch")
    return sorted(normalized, key=lambda item: item["case_id"])


def _validate_source_isolation(
    artifact: dict[str, Any],
    manifest_cases: dict[str, dict[str, Any]],
) -> None:
    holdout_groups = {
        case["source_group_hash"]
        for case in manifest_cases.values()
    }
    overlap = sorted(
        set(artifact["fit_source_group_hashes"]) & holdout_groups
    )
    if overlap:
        raise ProbabilityCalibrationError(
            "fit_holdout_source_group_overlap"
        )


def _metrics(
    pairs: list[tuple[float, int]],
    *,
    bin_count: int,
) -> dict[str, Any]:
    if not pairs:
        return {
            "case_count": 0,
            "expected_calibration_error": None,
            "maximum_calibration_error": None,
            "brier_score": None,
            "negative_log_likelihood": None,
            "mean_probability": None,
            "empirical_rate": None,
            "reliability_bins": [],
        }
    bins: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for probability, outcome in pairs:
        bin_index = min(int(probability * bin_count), bin_count - 1)
        bins[bin_index].append((probability, outcome))
    reliability_bins = []
    total = len(pairs)
    for bin_index in range(bin_count):
        bucket = bins.get(bin_index, [])
        if not bucket:
            continue
        mean_probability = sum(item[0] for item in bucket) / len(bucket)
        empirical_rate = sum(item[1] for item in bucket) / len(bucket)
        gap = abs(mean_probability - empirical_rate)
        reliability_bins.append(
            {
                "bin_index": bin_index,
                "lower_bound": round(bin_index / bin_count, 12),
                "upper_bound": round((bin_index + 1) / bin_count, 12),
                "case_count": len(bucket),
                "mean_probability": round(mean_probability, 12),
                "empirical_rate": round(empirical_rate, 12),
                "absolute_gap": round(gap, 12),
                "weight": round(len(bucket) / total, 12),
            }
        )
    ece = sum(
        item["absolute_gap"] * item["case_count"] / total
        for item in reliability_bins
    )
    brier = sum((probability - outcome) ** 2 for probability, outcome in pairs) / total
    epsilon = 1e-12
    nll = -sum(
        outcome * math.log(min(max(probability, epsilon), 1 - epsilon))
        + (1 - outcome)
        * math.log(min(max(1 - probability, epsilon), 1 - epsilon))
        for probability, outcome in pairs
    ) / total
    return {
        "case_count": total,
        "expected_calibration_error": round(ece, 12),
        "maximum_calibration_error": round(
            max(item["absolute_gap"] for item in reliability_bins),
            12,
        ),
        "brier_score": round(brier, 12),
        "negative_log_likelihood": round(nll, 12),
        "mean_probability": round(
            sum(probability for probability, _ in pairs) / total,
            12,
        ),
        "empirical_rate": round(
            sum(outcome for _, outcome in pairs) / total,
            12,
        ),
        "reliability_bins": reliability_bins,
    }


def _qualification_blockers(
    *,
    overall: dict[str, Any],
    class_conditional: dict[str, dict[str, Any]],
    case_count: int,
    failed_count: int,
    passed_count: int,
    ece_threshold: float,
    minimum_cases: int,
    minimum_class_cases: int,
    artifact: dict[str, Any],
    holdout_manifest: dict[str, Any],
) -> list[str]:
    blockers = []
    if artifact["fit_receipt_verified"] is not True:
        blockers.append("fit_receipt_not_verified")
    if holdout_manifest["gold_receipt_verified"] is not True:
        blockers.append("human_gold_receipt_not_verified")
    if holdout_manifest["source_isolation_verified"] is not True:
        blockers.append("source_isolation_not_verified")
    if case_count < minimum_cases:
        blockers.append("heldout_case_count_below_minimum")
    if failed_count < minimum_class_cases:
        blockers.append("heldout_failure_count_below_minimum")
    if passed_count < minimum_class_cases:
        blockers.append("heldout_pass_count_below_minimum")
    if overall["expected_calibration_error"] > ece_threshold:
        blockers.append("overall_ece_above_threshold")
    if (
        class_conditional["fail"]["expected_calibration_error"] is not None
        and class_conditional["fail"]["expected_calibration_error"] > ece_threshold
    ):
        blockers.append("failure_class_ece_above_threshold")
    if (
        class_conditional["pass"]["expected_calibration_error"] is not None
        and class_conditional["pass"]["expected_calibration_error"] > ece_threshold
    ):
        blockers.append("pass_class_ece_above_threshold")
    return sorted(blockers)


def _verify_self_hash(value: dict[str, Any], field: str, label: str) -> None:
    declared = _hash(value[field], field)
    unsigned = {key: item for key, item in value.items() if key != field}
    if stable_hash(unsigned) != declared:
        raise ProbabilityCalibrationError(f"{label}_{field}_mismatch")


def _exact_fields(value: Any, fields: frozenset[str], label: str) -> None:
    if not isinstance(value, dict):
        raise ProbabilityCalibrationError(f"{label}_must_be_object")
    if set(value) != fields:
        raise ProbabilityCalibrationError(f"{label}_fields_mismatch")


def _hash_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ProbabilityCalibrationError(f"{field}_must_be_non_empty_list")
    normalized = [_hash(item, field) for item in value]
    if len(set(normalized)) != len(normalized):
        raise ProbabilityCalibrationError(f"{field}_contains_duplicates")
    return sorted(normalized)


def _hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ProbabilityCalibrationError(f"{field}_must_be_sha256")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProbabilityCalibrationError(f"{field}_must_be_non_empty_string")
    normalized = value.strip()
    if any(pattern.search(normalized) for pattern in PUBLIC_TEXT_PATTERNS):
        raise ProbabilityCalibrationError("private_or_secret_material_rejected")
    return normalized


def _enum(value: Any, allowed: frozenset[str], field: str) -> str:
    if value not in allowed:
        raise ProbabilityCalibrationError(f"{field}_not_supported")
    return str(value)


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ProbabilityCalibrationError(f"{field}_must_be_boolean")
    return value


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProbabilityCalibrationError(f"{field}_must_be_probability")
    normalized = float(value)
    if not math.isfinite(normalized) or not 0.0 <= normalized <= 1.0:
        raise ProbabilityCalibrationError(f"{field}_must_be_probability")
    return normalized


def _threshold(value: Any, field: str) -> float:
    normalized = _probability(value, field)
    if normalized <= 0:
        raise ProbabilityCalibrationError(f"{field}_must_be_positive")
    return normalized


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProbabilityCalibrationError(f"{field}_must_be_positive_integer")
    return value
