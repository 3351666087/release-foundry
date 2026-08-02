from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_build_multimodal_cross_provider_comparison import stable_hash


SCHEMA = ROOT / "docs/a2/schemas/multimodal_source_repeat_comparison_v1.schema.json"
BINDING_FIELDS = (
    "provider_id",
    "model_id",
    "endpoint_region",
    "manifest_hash",
    "ordered_case_plan_hash",
    "policy_hash",
    "prompt_hash",
    "output_schema_hash",
    "provider_capability_hash",
)


def _bucket_id(perturbation: dict[str, Any]) -> str:
    if perturbation["kind"] == "rotation":
        return f"rotation_degrees:{perturbation['rotation_degrees']}"
    if perturbation["kind"] == "jpeg_compression":
        return f"jpeg_quality:{perturbation['jpeg_quality']}"
    raise ValueError("unsupported perturbation kind")


def _source_outcomes(calibration: dict[str, Any]) -> dict[str, bool]:
    grouped: dict[str, list[bool]] = {}
    for item in calibration.get("observations", []):
        if (
            item.get("expected_risk") is not True
            or not item.get("source_case_hash")
            or not item.get("perturbation")
            or item.get("observed_risk") is None
        ):
            continue
        key = f"{_bucket_id(item['perturbation'])}|{item['source_case_hash']}"
        grouped.setdefault(key, []).append(item["observed_risk"] is True)
    return {key: all(values) for key, values in sorted(grouped.items())}


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * probability)]


def _summary(outcomes: list[bool], bootstrap: list[float]) -> dict[str, Any]:
    return {
        "matched_distinct_bucket_source_count": len(outcomes),
        "detected_count": sum(outcomes),
        "sensitivity": sum(outcomes) / len(outcomes) if outcomes else None,
        "bootstrap_ci_95": {
            "lower": _percentile(bootstrap, 0.025),
            "upper": _percentile(bootstrap, 0.975),
        },
    }


def build_source_repeat_comparison(
    baseline: dict[str, Any],
    repeat: dict[str, Any],
    *,
    bootstrap_samples: int = 4000,
    seed: int = 50,
) -> dict[str, Any]:
    if bootstrap_samples < 100:
        raise ValueError("bootstrap samples must be at least 100")
    blockers = []
    mismatched_bindings = [
        field for field in BINDING_FIELDS if baseline.get(field) != repeat.get(field)
    ]
    if mismatched_bindings:
        blockers.append("source_repeat_binding_mismatch")

    baseline_outcomes = _source_outcomes(baseline)
    repeat_outcomes = _source_outcomes(repeat)
    baseline_keys = set(baseline_outcomes)
    repeat_keys = set(repeat_outcomes)
    missing_from_baseline = sorted(repeat_keys - baseline_keys)
    missing_from_repeat = sorted(baseline_keys - repeat_keys)
    if missing_from_baseline:
        blockers.append("source_repeat_units_missing_from_baseline")
    if missing_from_repeat:
        blockers.append("source_repeat_units_missing_from_repeat")
    matched_keys = sorted(baseline_keys & repeat_keys)
    if not matched_keys:
        blockers.append("source_repeat_matched_units_unavailable")

    baseline_values = [baseline_outcomes[key] for key in matched_keys]
    repeat_values = [repeat_outcomes[key] for key in matched_keys]
    randomizer = random.Random(seed)
    baseline_bootstrap = []
    repeat_bootstrap = []
    delta_bootstrap = []
    if matched_keys:
        size = len(matched_keys)
        for _ in range(bootstrap_samples):
            indices = [randomizer.randrange(size) for _ in range(size)]
            left = sum(baseline_values[index] for index in indices) / size
            right = sum(repeat_values[index] for index in indices) / size
            baseline_bootstrap.append(left)
            repeat_bootstrap.append(right)
            delta_bootstrap.append(right - left)

    baseline_sensitivity = (
        sum(baseline_values) / len(baseline_values) if baseline_values else None
    )
    repeat_sensitivity = (
        sum(repeat_values) / len(repeat_values) if repeat_values else None
    )
    result = {
        "schema_version": "a2.multimodal_source_repeat_comparison.v1",
        "baseline_calibration_hash": stable_hash(baseline),
        "repeat_calibration_hash": stable_hash(repeat),
        "binding_fields": {
            field: baseline.get(field)
            for field in BINDING_FIELDS
            if field not in mismatched_bindings
        },
        "mismatched_binding_fields": mismatched_bindings,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "baseline": _summary(baseline_values, baseline_bootstrap),
        "repeat": _summary(repeat_values, repeat_bootstrap),
        "sensitivity_delta_repeat_minus_baseline": (
            repeat_sensitivity - baseline_sensitivity
            if baseline_sensitivity is not None and repeat_sensitivity is not None
            else None
        ),
        "paired_delta_bootstrap_ci_95": {
            "lower": _percentile(delta_bootstrap, 0.025),
            "upper": _percentile(delta_bootstrap, 0.975),
        },
        "missing_unit_counts": {
            "from_baseline": len(missing_from_baseline),
            "from_repeat": len(missing_from_repeat),
        },
        "blockers": blockers,
        "promotion_eligible": not blockers,
        "release_authority": False,
        "raw_provider_text_included": False,
        "public_safe": True,
    }
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
    ).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--repeat", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=50)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_source_repeat_comparison(
        json.loads(Path(args.baseline).read_text(encoding="utf-8")),
        json.loads(Path(args.repeat).read_text(encoding="utf-8")),
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    Path(args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["promotion_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
