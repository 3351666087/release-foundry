from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any, Callable

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_build_multimodal_cross_provider_comparison import stable_hash
from scripts.a2_build_multimodal_source_repeat_comparison import BINDING_FIELDS


SCHEMA = (
    ROOT
    / "docs/a2/schemas/multimodal_multi_repeat_comparison_v1.schema.json"
)
TAXONOMIES = ("cross_modal_conflict", "visual_prompt_injection")


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * probability)]


def _eligible(calibration: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in calibration.get("observations", [])
        if item.get("observed_risk") is not None
    ]


def _source_key(item: dict[str, Any]) -> str:
    return str(item.get("source_case_hash") or item["artifact_hash"])


def _metric_maps(
    calibrations: list[dict[str, Any]],
    predicate: Callable[[dict[str, Any]], bool],
    success: Callable[[dict[str, Any]], bool],
) -> list[dict[str, bool]]:
    result = []
    for calibration in calibrations:
        grouped: dict[str, list[bool]] = {}
        for item in _eligible(calibration):
            if predicate(item):
                grouped.setdefault(_source_key(item), []).append(success(item))
        result.append(
            {
                key: all(values)
                for key, values in sorted(grouped.items())
            }
        )
    return result


def _source_unit_coverage(
    calibrations: list[dict[str, Any]],
) -> dict[str, Any]:
    required = set().union(
        *(
            {_source_key(item) for item in calibration.get("observations", [])}
            for calibration in calibrations
        )
    )
    eligible_by_repeat = [
        {_source_key(item) for item in _eligible(calibration)}
        for calibration in calibrations
    ]
    missing = [len(required - values) for values in eligible_by_repeat]
    return {
        "required_unit_count": len(required),
        "eligible_unit_counts_by_repeat": [
            len(values) for values in eligible_by_repeat
        ],
        "missing_unit_counts_by_repeat": missing,
        "complete_across_repeats": bool(required) and not any(missing),
    }


def _bootstrap_metric(
    maps: list[dict[str, bool]],
    *,
    bootstrap_samples: int,
    randomizer: random.Random,
) -> dict[str, Any]:
    union = set().union(*(set(values) for values in maps))
    intersection = set.intersection(*(set(values) for values in maps)) if maps else set()
    missing_counts = [len(union - set(values)) for values in maps]
    keys = sorted(intersection)
    bootstraps = [[] for _ in maps]
    spread_bootstrap: list[float] = []
    if keys:
        for _ in range(bootstrap_samples):
            sampled = [keys[randomizer.randrange(len(keys))] for _ in keys]
            estimates = [
                sum(values[key] for key in sampled) / len(sampled)
                for values in maps
            ]
            for target, estimate in zip(bootstraps, estimates):
                target.append(estimate)
            spread_bootstrap.append(max(estimates) - min(estimates))
    return {
        "required_unit_count": len(union),
        "matched_unit_count": len(keys),
        "missing_unit_counts_by_repeat": missing_counts,
        "complete_across_repeats": bool(union) and not any(missing_counts),
        "repeat_summaries": [
            {
                "eligible_unit_count": len(values),
                "success_count": sum(values.values()),
                "estimate": (
                    sum(values.values()) / len(values) if values else None
                ),
                "bootstrap_ci_95": {
                    "lower": _percentile(bootstrap, 0.025),
                    "upper": _percentile(bootstrap, 0.975),
                },
            }
            for values, bootstrap in zip(maps, bootstraps)
        ],
        "paired_max_minus_min_bootstrap_ci_95": {
            "lower": _percentile(spread_bootstrap, 0.025),
            "upper": _percentile(spread_bootstrap, 0.975),
        },
    }


def build_multi_repeat_comparison(
    calibrations: list[dict[str, Any]],
    *,
    bootstrap_samples: int = 4000,
    seed: int = 51,
) -> dict[str, Any]:
    if len(calibrations) < 3:
        raise ValueError("at least three retained repeats are required")
    if bootstrap_samples < 100:
        raise ValueError("bootstrap samples must be at least 100")
    mismatched_bindings = [
        field
        for field in BINDING_FIELDS
        if len({json.dumps(item.get(field), sort_keys=True) for item in calibrations})
        != 1
    ]
    blockers = ["multi_repeat_binding_mismatch"] if mismatched_bindings else []
    retained_states = [
        str(item.get("qualification_state") or "unknown")
        for item in calibrations
    ]
    if any(state != "qualified" for state in retained_states):
        blockers.append("multi_repeat_retained_calibration_not_qualified")
    source_unit_coverage = _source_unit_coverage(calibrations)
    if not source_unit_coverage["complete_across_repeats"]:
        blockers.append("multi_repeat_units_incomplete:all_source_units")
    randomizer = random.Random(seed)
    metrics = {
        "specificity": _bootstrap_metric(
            _metric_maps(
                calibrations,
                lambda item: item["expected_risk"] is False,
                lambda item: item["observed_risk"] is False,
            ),
            bootstrap_samples=bootstrap_samples,
            randomizer=randomizer,
        ),
        "benign_text_false_positive_rate": _bootstrap_metric(
            _metric_maps(
                calibrations,
                lambda item: item["expected_risk"] is False
                and (
                    item["taxonomy"] == "benign_text_safe"
                    or item.get("user_text_present") is True
                ),
                lambda item: item["observed_risk"] is True,
            ),
            bootstrap_samples=bootstrap_samples,
            randomizer=randomizer,
        ),
    }
    taxonomy_metrics = {
        taxonomy: _bootstrap_metric(
            _metric_maps(
                calibrations,
                lambda item, taxonomy=taxonomy: item["expected_risk"] is True
                and item["taxonomy"] == taxonomy,
                lambda item: item["observed_risk"] is True,
            ),
            bootstrap_samples=bootstrap_samples,
            randomizer=randomizer,
        )
        for taxonomy in TAXONOMIES
    }
    for name, metric in {**metrics, **taxonomy_metrics}.items():
        if not metric["complete_across_repeats"]:
            blockers.append(f"multi_repeat_units_incomplete:{name}")
    result = {
        "schema_version": "a2.multimodal_multi_repeat_comparison.v1",
        "calibration_hashes": [stable_hash(item) for item in calibrations],
        "repeat_count": len(calibrations),
        "binding_fields": {
            field: calibrations[0].get(field)
            for field in BINDING_FIELDS
            if field not in mismatched_bindings
        },
        "mismatched_binding_fields": mismatched_bindings,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "retained_calibration_states": retained_states,
        "source_unit_coverage": source_unit_coverage,
        "metrics": metrics,
        "taxonomy_sensitivity": taxonomy_metrics,
        "all_required_units_complete": (
            source_unit_coverage["complete_across_repeats"]
            and not any(
                not metric["complete_across_repeats"]
                for metric in [*metrics.values(), *taxonomy_metrics.values()]
            )
        ),
        "blockers": sorted(set(blockers)),
        "promotion_eligible": not blockers,
        "provider_is_truth": False,
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
    parser.add_argument("--calibration", action="append", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=51)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_multi_repeat_comparison(
        [
            json.loads((ROOT / path).read_text(encoding="utf-8"))
            for path in args.calibration
        ],
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["promotion_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
