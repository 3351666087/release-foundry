"""Fail-closed blind comparison for incumbent and challenger judge versions.

The scorer consumes two anonymous run payloads first. Version identities are
bound only after the blind metrics have been computed, so a challenger cannot
be promoted from a self-reported score or from a mismatched case set.
"""

from __future__ import annotations

import re
from typing import Any

from .release_actions import CANONICAL_RELEASE_ACTIONS
from .result_persistence import stable_hash


SCHEMA_VERSION = "a2.blind_version_comparison.v1"
MANIFEST_SCHEMA_VERSION = "a2.blind_holdout_manifest.v1"
RUN_SCHEMA_VERSION = "a2.blind_judge_run.v1"
DEFAULT_COMPARISON_ID = "a2_blind_judge_version_comparison"
DEFAULT_CREATED_AT = "2026-07-27T00:00:00Z"

HASH_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
VALID_LABELS = frozenset({"pass", "fail"})
VALID_SEVERITIES = frozenset({"info", "low", "medium", "high", "critical"})
VALID_RELEASE_RECOMMENDATIONS = frozenset(CANONICAL_RELEASE_ACTIONS)
FORBIDDEN_BLIND_KEYS = frozenset(
    {
        "role",
        "version_id",
        "judge_version",
        "model_version",
        "artifact_hash",
        "incumbent",
        "challenger",
    }
)
ROLE_TOKENS = ("incumbent", "challenger")


def build_blind_version_comparison(
    *,
    held_out_manifest: dict[str, Any],
    blind_runs: list[dict[str, Any]],
    role_bindings: list[dict[str, Any]],
    comparison_id: str = DEFAULT_COMPARISON_ID,
    created_at: str = DEFAULT_CREATED_AT,
) -> dict[str, Any]:
    """Compare two immutable versions on one identical, source-isolated holdout."""
    manifest_cases = _validate_manifest(held_out_manifest)
    runs = _validate_blind_runs(blind_runs, held_out_manifest, manifest_cases)

    # Deliberately score anonymous slots before reading incumbent/challenger
    # bindings. This keeps role identity outside the scoring input.
    blind_metrics = {
        slot: _score_run(run, manifest_cases)
        for slot, run in sorted(runs.items())
    }
    bindings = _validate_role_bindings(role_bindings, runs)

    incumbent_binding = bindings["incumbent"]
    challenger_binding = bindings["challenger"]
    incumbent_slot = incumbent_binding["blind_slot"]
    challenger_slot = challenger_binding["blind_slot"]
    incumbent_metrics = blind_metrics[incumbent_slot]
    challenger_metrics = blind_metrics[challenger_slot]
    paired_cases = _paired_case_deltas(
        manifest_cases,
        runs[incumbent_slot],
        runs[challenger_slot],
    )
    metric_deltas = _metric_deltas(incumbent_metrics, challenger_metrics)
    blockers = _promotion_blockers(
        incumbent_metrics,
        challenger_metrics,
        paired_cases,
    )

    scoring_input = {
        "manifest_hash": held_out_manifest["manifest_hash"],
        "blind_run_hashes": {
            slot: run["run_hash"]
            for slot, run in sorted(runs.items())
        },
    }
    binding_payload = [
        {
            "blind_slot": binding["blind_slot"],
            "role": role,
            "version_id": binding["version_id"],
            "artifact_hash": binding["artifact_hash"],
            "run_hash": binding["run_hash"],
        }
        for role, binding in sorted(bindings.items())
    ]
    comparison_without_hash = {
        "schema_version": SCHEMA_VERSION,
        "comparison_id": _required_text(comparison_id, "comparison_id"),
        "created_at": _required_text(created_at, "created_at"),
        "manifest": {
            "manifest_id": held_out_manifest["manifest_id"],
            "manifest_hash": held_out_manifest["manifest_hash"],
            "dataset_id": held_out_manifest["dataset_id"],
            "dataset_content_hash": held_out_manifest["dataset_content_hash"],
            "prompt_version": held_out_manifest["prompt_version"],
            "split": held_out_manifest["split"],
            "case_count": len(manifest_cases),
            "source_isolation_verified": True,
        },
        "blind_scoring": {
            "identities_hidden_during_scoring": True,
            "role_bindings_applied_after_scoring": True,
            "scoring_input_hash": stable_hash(scoring_input),
            "role_binding_hash": stable_hash(binding_payload),
            "blind_slots": sorted(runs),
        },
        "versions": {
            "incumbent": _version_summary(incumbent_binding, runs[incumbent_slot]),
            "challenger": _version_summary(challenger_binding, runs[challenger_slot]),
        },
        "metrics": {
            "incumbent": incumbent_metrics,
            "challenger": challenger_metrics,
            "challenger_minus_incumbent": metric_deltas,
        },
        "paired_cases": paired_cases,
        "promotion_gate": {
            "status": "eligible_for_human_review" if not blockers else "blocked",
            "release_recommendation": "human_review" if not blockers else "block",
            "promotion_recommended": not blockers,
            "automatic_promotion_allowed": False,
            "requires_human_approval": True,
            "blockers": blockers,
            "newly_missed_critical_case_ids": [
                case["case_id"]
                for case in paired_cases
                if case["comparison_outcome"] == "critical_regression"
            ],
            "historical_critical_case_ids_missed_by_challenger": [
                case["case_id"]
                for case in paired_cases
                if case["expected"]["historical_critical_regression"]
                and case["challenger"]["label"] != "fail"
            ],
        },
        "metadata": {
            "public_safe": True,
            "deterministic": True,
            "requires_network": False,
            "requires_releasefoundry_api_key": False,
            "does_not_train_or_promote_models": True,
            "raw_case_content_not_recorded": True,
            "raw_private_evidence_not_recorded": True,
            "purpose": (
                "Block judge upgrades that regress on an identical blinded "
                "held-out case manifest."
            ),
        },
    }
    return {
        **comparison_without_hash,
        "comparison_hash": stable_hash(comparison_without_hash),
    }


def _validate_manifest(manifest: Any) -> dict[str, dict[str, Any]]:
    _require_object(manifest, "held_out_manifest")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported blind holdout manifest schema_version")
    _verify_self_hash(manifest, "manifest_hash", "blind holdout manifest")
    _required_text(manifest.get("manifest_id"), "manifest_id")
    _required_text(manifest.get("dataset_id"), "dataset_id")
    _required_hash(manifest.get("dataset_content_hash"), "dataset_content_hash")
    prompt_version = _required_text(manifest.get("prompt_version"), "prompt_version")
    if manifest.get("split") != "holdout":
        raise ValueError("blind comparison requires split='holdout'")
    if manifest.get("source_isolation_verified") is not True:
        raise ValueError("blind comparison requires verified source isolation")
    _required_hash(
        manifest.get("source_isolation_policy_hash"),
        "source_isolation_policy_hash",
    )

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("blind holdout manifest cases must be a non-empty list")
    by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        _require_object(case, "blind holdout case")
        case_id = _required_text(case.get("case_id"), "case_id")
        if case_id in by_id:
            raise ValueError(f"duplicate blind holdout case_id {case_id!r}")
        _required_hash(case.get("fixture_hash"), f"{case_id}.fixture_hash")
        _required_hash(case.get("source_hash"), f"{case_id}.source_hash")
        if case.get("prompt_version") != prompt_version:
            raise ValueError(f"blind holdout case {case_id!r} prompt_version mismatch")
        _validate_expected(case.get("expected"), case_id)
        by_id[case_id] = case
    return by_id


def _validate_expected(expected: Any, case_id: str) -> None:
    _require_object(expected, f"{case_id}.expected")
    label = expected.get("label")
    if label not in VALID_LABELS:
        raise ValueError(f"blind holdout case {case_id!r} has invalid expected label")
    failure_class = _required_text(
        expected.get("failure_class"),
        f"{case_id}.expected.failure_class",
    )
    if label == "pass" and failure_class != "none":
        raise ValueError(f"passing blind holdout case {case_id!r} must use failure_class='none'")
    if label == "fail" and failure_class == "none":
        raise ValueError(f"failing blind holdout case {case_id!r} requires a failure class")
    severity = expected.get("severity")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"blind holdout case {case_id!r} has invalid severity")
    historical = expected.get("historical_critical_regression")
    if not isinstance(historical, bool):
        raise ValueError(
            f"blind holdout case {case_id!r} historical_critical_regression must be boolean"
        )
    if historical and not (label == "fail" and severity == "critical"):
        raise ValueError(
            f"blind holdout case {case_id!r} historical critical marker is inconsistent"
        )


def _validate_blind_runs(
    blind_runs: Any,
    manifest: dict[str, Any],
    manifest_cases: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(blind_runs, list) or len(blind_runs) != 2:
        raise ValueError("blind comparison requires exactly two anonymous runs")
    runs: dict[str, dict[str, Any]] = {}
    for run in blind_runs:
        _require_object(run, "blind run")
        _reject_identity_disclosure(run)
        if run.get("schema_version") != RUN_SCHEMA_VERSION:
            raise ValueError("unsupported blind judge run schema_version")
        _verify_self_hash(run, "run_hash", "blind judge run")
        slot = _required_text(run.get("blind_slot"), "blind_slot")
        run_id = _required_text(run.get("run_id"), "run_id")
        _reject_role_token(slot, "blind_slot")
        _reject_role_token(run_id, "run_id")
        if slot in runs:
            raise ValueError(f"duplicate blind_slot {slot!r}")
        if run.get("manifest_id") != manifest["manifest_id"]:
            raise ValueError(f"blind run {slot!r} manifest_id mismatch")
        if run.get("manifest_hash") != manifest["manifest_hash"]:
            raise ValueError(f"blind run {slot!r} manifest_hash mismatch")
        _validate_run_cases(run, slot, manifest_cases)
        runs[slot] = run
    return runs


def _validate_run_cases(
    run: dict[str, Any],
    slot: str,
    manifest_cases: dict[str, dict[str, Any]],
) -> None:
    cases = run.get("cases")
    if not isinstance(cases, list):
        raise TypeError(f"blind run {slot!r} cases must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        _require_object(case, f"blind run {slot!r} case")
        case_id = _required_text(case.get("case_id"), "case_id")
        if case_id in by_id:
            raise ValueError(f"blind run {slot!r} duplicates case_id {case_id!r}")
        if case_id not in manifest_cases:
            raise ValueError(f"blind run {slot!r} contains extra case_id {case_id!r}")
        expected_case = manifest_cases[case_id]
        for field in ("fixture_hash", "source_hash", "prompt_version"):
            if case.get(field) != expected_case[field]:
                raise ValueError(
                    f"blind run {slot!r} case {case_id!r} {field} mismatch"
                )
        prediction = case.get("prediction")
        _validate_prediction(prediction, slot, case_id)
        if case.get("prediction_hash") != stable_hash(prediction):
            raise ValueError(
                f"blind run {slot!r} case {case_id!r} prediction_hash mismatch"
            )
        by_id[case_id] = case
    missing = sorted(set(manifest_cases) - set(by_id))
    if missing:
        raise ValueError(
            f"blind run {slot!r} is missing held-out case(s): {', '.join(missing)}"
        )


def _validate_prediction(prediction: Any, slot: str, case_id: str) -> None:
    _require_object(prediction, f"blind run {slot!r} case {case_id!r} prediction")
    if prediction.get("label") not in VALID_LABELS:
        raise ValueError(
            f"blind run {slot!r} case {case_id!r} has invalid predicted label"
        )
    _required_text(
        prediction.get("failure_class"),
        f"{slot}.{case_id}.prediction.failure_class",
    )
    _probability(
        prediction.get("failure_probability"),
        f"{slot}.{case_id}.prediction.failure_probability",
    )
    _probability(prediction.get("score"), f"{slot}.{case_id}.prediction.score")
    if prediction.get("release_recommendation") not in VALID_RELEASE_RECOMMENDATIONS:
        raise ValueError(
            f"blind run {slot!r} case {case_id!r} has invalid release recommendation"
        )


def _validate_role_bindings(
    role_bindings: Any,
    runs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(role_bindings, list) or len(role_bindings) != 2:
        raise ValueError("blind comparison requires exactly two role bindings")
    bindings: dict[str, dict[str, Any]] = {}
    used_slots: set[str] = set()
    for binding in role_bindings:
        _require_object(binding, "blind role binding")
        role = binding.get("role")
        if role not in {"incumbent", "challenger"}:
            raise ValueError("blind role binding role must be incumbent or challenger")
        if role in bindings:
            raise ValueError(f"duplicate blind role binding for {role!r}")
        slot = _required_text(binding.get("blind_slot"), "blind_slot")
        if slot not in runs:
            raise ValueError(f"blind role binding references unknown slot {slot!r}")
        if slot in used_slots:
            raise ValueError(f"blind slot {slot!r} is bound more than once")
        if binding.get("run_hash") != runs[slot]["run_hash"]:
            raise ValueError(f"blind role binding for {role!r} has run_hash mismatch")
        _required_text(binding.get("version_id"), f"{role}.version_id")
        _required_hash(binding.get("artifact_hash"), f"{role}.artifact_hash")
        used_slots.add(slot)
        bindings[role] = binding
    if set(bindings) != {"incumbent", "challenger"}:
        raise ValueError("blind role bindings must contain incumbent and challenger")
    if bindings["incumbent"]["version_id"] == bindings["challenger"]["version_id"]:
        raise ValueError("incumbent and challenger must be different immutable versions")
    if bindings["incumbent"]["artifact_hash"] == bindings["challenger"]["artifact_hash"]:
        raise ValueError("incumbent and challenger must bind different artifacts")
    return bindings


def _score_run(
    run: dict[str, Any],
    manifest_cases: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    predictions = {
        case["case_id"]: case["prediction"]
        for case in run["cases"]
    }
    correct_count = 0
    failure_class_correct_count = 0
    expected_failure_count = 0
    critical_total = 0
    critical_detected = 0
    false_release_count = 0
    historical_total = 0
    historical_detected = 0
    scores: list[float] = []
    expected_probabilities: list[float] = []
    per_class: dict[str, dict[str, int]] = {}

    for case_id, manifest_case in manifest_cases.items():
        expected = manifest_case["expected"]
        prediction = predictions[case_id]
        expected_label = expected["label"]
        predicted_label = prediction["label"]
        correct_count += int(predicted_label == expected_label)
        failure_class_correct_count += int(
            prediction["failure_class"] == expected["failure_class"]
        )
        failure_probability = float(prediction["failure_probability"])
        scores.append(float(prediction["score"]))
        expected_probabilities.append(
            failure_probability if expected_label == "fail" else 1.0 - failure_probability
        )

        if expected_label == "fail":
            expected_failure_count += 1
            class_metrics = per_class.setdefault(
                expected["failure_class"],
                {"expected_count": 0, "detected_count": 0, "classified_count": 0},
            )
            class_metrics["expected_count"] += 1
            if predicted_label == "fail":
                class_metrics["detected_count"] += 1
            if (
                predicted_label == "fail"
                and prediction["failure_class"] == expected["failure_class"]
            ):
                class_metrics["classified_count"] += 1
            if prediction["release_recommendation"] == "allow":
                false_release_count += 1

        if expected["severity"] == "critical" and expected_label == "fail":
            critical_total += 1
            critical_detected += int(predicted_label == "fail")
        if expected["historical_critical_regression"]:
            historical_total += 1
            historical_detected += int(predicted_label == "fail")

    return {
        "case_count": len(manifest_cases),
        "correct_count": correct_count,
        "accuracy": _rate(correct_count, len(manifest_cases)),
        "failure_class_correct_count": failure_class_correct_count,
        "failure_class_accuracy": _rate(
            failure_class_correct_count,
            len(manifest_cases),
        ),
        "expected_failure_count": expected_failure_count,
        "critical_error_count": critical_total,
        "critical_error_detected_count": critical_detected,
        "critical_error_recall": _rate(critical_detected, critical_total),
        "false_release_count": false_release_count,
        "false_release_rate": _rate(false_release_count, expected_failure_count),
        "historical_critical_regression_count": historical_total,
        "historical_critical_regression_detected_count": historical_detected,
        "historical_critical_regression_recall": _rate(
            historical_detected,
            historical_total,
        ),
        "mean_score": _mean(scores),
        "mean_expected_label_probability": _mean(expected_probabilities),
        "per_failure_class": {
            failure_class: {
                **counts,
                "detection_recall": _rate(
                    counts["detected_count"],
                    counts["expected_count"],
                ),
                "classification_recall": _rate(
                    counts["classified_count"],
                    counts["expected_count"],
                ),
            }
            for failure_class, counts in sorted(per_class.items())
        },
    }


def _paired_case_deltas(
    manifest_cases: dict[str, dict[str, Any]],
    incumbent_run: dict[str, Any],
    challenger_run: dict[str, Any],
) -> list[dict[str, Any]]:
    incumbent = {
        case["case_id"]: case["prediction"]
        for case in incumbent_run["cases"]
    }
    challenger = {
        case["case_id"]: case["prediction"]
        for case in challenger_run["cases"]
    }
    paired = []
    for case_id, manifest_case in sorted(manifest_cases.items()):
        expected = manifest_case["expected"]
        old = incumbent[case_id]
        new = challenger[case_id]
        old_correct = old["label"] == expected["label"]
        new_correct = new["label"] == expected["label"]
        if (
            expected["label"] == "fail"
            and expected["severity"] == "critical"
            and old["label"] == "fail"
            and new["label"] != "fail"
        ):
            outcome = "critical_regression"
        elif old_correct and not new_correct:
            outcome = "regressed"
        elif not old_correct and new_correct:
            outcome = "improved"
        elif old_correct:
            outcome = "unchanged_correct"
        else:
            outcome = "unchanged_incorrect"
        paired.append(
            {
                "case_id": case_id,
                "fixture_hash": manifest_case["fixture_hash"],
                "source_hash": manifest_case["source_hash"],
                "prompt_version": manifest_case["prompt_version"],
                "expected": dict(expected),
                "incumbent": dict(old),
                "challenger": dict(new),
                "comparison_outcome": outcome,
                "score_delta": _delta(old["score"], new["score"]),
                "failure_probability_delta": _delta(
                    old["failure_probability"],
                    new["failure_probability"],
                ),
            }
        )
    return paired


def _metric_deltas(
    incumbent: dict[str, Any],
    challenger: dict[str, Any],
) -> dict[str, Any]:
    fields = (
        "accuracy",
        "failure_class_accuracy",
        "critical_error_recall",
        "false_release_rate",
        "historical_critical_regression_recall",
        "mean_score",
        "mean_expected_label_probability",
    )
    deltas = {
        field: _delta(incumbent[field], challenger[field])
        for field in fields
    }
    deltas["false_release_count"] = (
        challenger["false_release_count"] - incumbent["false_release_count"]
    )
    deltas["critical_error_detected_count"] = (
        challenger["critical_error_detected_count"]
        - incumbent["critical_error_detected_count"]
    )
    deltas["historical_critical_regression_detected_count"] = (
        challenger["historical_critical_regression_detected_count"]
        - incumbent["historical_critical_regression_detected_count"]
    )
    return deltas


def _promotion_blockers(
    incumbent: dict[str, Any],
    challenger: dict[str, Any],
    paired_cases: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    if challenger["expected_failure_count"] == 0:
        blockers.append("heldout_failure_coverage_missing")
    if challenger["critical_error_count"] == 0:
        blockers.append("heldout_critical_error_coverage_missing")
    if challenger["historical_critical_regression_count"] == 0:
        blockers.append("historical_critical_regression_coverage_missing")
    if _regressed(incumbent["accuracy"], challenger["accuracy"]):
        blockers.append("challenger_accuracy_regressed")
    if _regressed(
        incumbent["failure_class_accuracy"],
        challenger["failure_class_accuracy"],
    ):
        blockers.append("challenger_failure_class_accuracy_regressed")
    if _regressed(
        incumbent["critical_error_recall"],
        challenger["critical_error_recall"],
    ):
        blockers.append("challenger_critical_error_recall_regressed")
    if challenger["false_release_count"] > incumbent["false_release_count"]:
        blockers.append("challenger_false_release_count_increased")
    if _regressed(
        incumbent["historical_critical_regression_recall"],
        challenger["historical_critical_regression_recall"],
    ):
        blockers.append("challenger_historical_critical_detection_regressed")
    if (
        challenger["historical_critical_regression_detected_count"]
        != challenger["historical_critical_regression_count"]
    ):
        blockers.append("challenger_missed_historical_critical_regression")

    for failure_class, incumbent_metrics in incumbent["per_failure_class"].items():
        challenger_metrics = challenger["per_failure_class"][failure_class]
        if _regressed(
            incumbent_metrics["detection_recall"],
            challenger_metrics["detection_recall"],
        ):
            blockers.append(
                f"challenger_failure_detection_regressed:{failure_class}"
            )
        if _regressed(
            incumbent_metrics["classification_recall"],
            challenger_metrics["classification_recall"],
        ):
            blockers.append(
                f"challenger_failure_classification_regressed:{failure_class}"
            )
    if any(case["comparison_outcome"] == "critical_regression" for case in paired_cases):
        blockers.append("challenger_newly_missed_critical_case")
    return sorted(set(blockers))


def _version_summary(
    binding: dict[str, Any],
    run: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version_id": binding["version_id"],
        "artifact_hash": binding["artifact_hash"],
        "blind_slot": binding["blind_slot"],
        "run_id": run["run_id"],
        "run_hash": run["run_hash"],
    }


def _verify_self_hash(value: dict[str, Any], field: str, label: str) -> None:
    declared = _required_hash(value.get(field), field)
    unsigned = {key: item for key, item in value.items() if key != field}
    if stable_hash(unsigned) != declared:
        raise ValueError(f"{label} {field} mismatch")


def _reject_identity_disclosure(value: Any, path: str = "blind_run") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_BLIND_KEYS:
                raise ValueError(
                    f"blind scoring input exposes version identity at {path}.{key}"
                )
            _reject_identity_disclosure(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_identity_disclosure(item, f"{path}[{index}]")


def _reject_role_token(value: str, field: str) -> None:
    lowered = value.lower()
    if any(token in lowered for token in ROLE_TOKENS):
        raise ValueError(f"{field} exposes incumbent/challenger identity")


def _required_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ValueError(f"{field} must be a sha256 hash")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _require_object(value: Any, field: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{field} must be an object")


def _probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number between 0 and 1")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field} must be a number between 0 and 1")
    return number


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 12)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 12)


def _delta(old: Any, new: Any) -> float | None:
    if old is None or new is None:
        return None
    return round(float(new) - float(old), 12)


def _regressed(old: float | None, new: float | None) -> bool:
    return old is not None and new is not None and new < old
