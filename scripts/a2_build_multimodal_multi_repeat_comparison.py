from __future__ import annotations

import argparse
from datetime import datetime, timezone
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
    / "docs/a2/schemas/multimodal_multi_repeat_comparison_v2.schema.json"
)
TAXONOMIES = ("cross_modal_conflict", "visual_prompt_injection")
SPREAD_METRICS = (
    "specificity",
    "benign_text_false_positive_rate",
    *TAXONOMIES,
)


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


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _validate_policy(policy: dict[str, Any]) -> None:
    version = policy.get("schema_version")
    if version not in {
        "a2.multimodal_multi_repeat_policy.v1",
        "a2.multimodal_multi_repeat_policy.v2",
    }:
        raise ValueError("unsupported multi-repeat policy")
    hashes = policy.get("retained_calibration_hash_allowlist")
    if (
        not isinstance(hashes, list)
        or len(hashes) < 1
        or len(set(hashes)) != len(hashes)
        or any(
            not isinstance(value, str)
            or not value.startswith("sha256:")
            or len(value) != 71
            for value in hashes
        )
    ):
        raise ValueError("retained calibration hash allowlist is invalid")
    if version.endswith(".v2"):
        source_hashes = policy.get("source_unit_hash_allowlist")
        if (
            not isinstance(source_hashes, list)
            or len(source_hashes) < 1
            or len(set(source_hashes)) != len(source_hashes)
            or any(
                not isinstance(value, str)
                or not value.startswith("sha256:")
                or len(value) != 71
                for value in source_hashes
            )
        ):
            raise ValueError("source-unit hash allowlist is invalid")
    maximum_age = policy.get("maximum_repeat_age_hours")
    if (
        isinstance(maximum_age, bool)
        or not isinstance(maximum_age, (int, float))
        or maximum_age <= 0
    ):
        raise ValueError("maximum repeat age must be positive")
    spreads = policy.get("maximum_allowed_spread")
    if not isinstance(spreads, dict) or set(spreads) != set(SPREAD_METRICS):
        raise ValueError("maximum spread policy must cover all repeat metrics")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 <= value <= 1
        for value in spreads.values()
    ):
        raise ValueError("maximum spread thresholds must be between zero and one")
    if policy.get("provider_is_truth") is not False:
        raise ValueError("multi-repeat policy cannot designate provider truth")
    if policy.get("release_authority") is not False:
        raise ValueError("multi-repeat policy cannot be release authority")
    if policy.get("public_safe") is not True:
        raise ValueError("multi-repeat policy must be public safe")


def build_multi_repeat_comparison(
    calibrations: list[dict[str, Any]],
    *,
    bootstrap_samples: int = 4000,
    seed: int = 51,
    policy: dict[str, Any] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    if len(calibrations) < 3:
        raise ValueError("at least three retained repeats are required")
    if bootstrap_samples < 100:
        raise ValueError("bootstrap samples must be at least 100")
    calibration_hashes = [stable_hash(item) for item in calibrations]
    if policy is None:
        policy = {
            "schema_version": "a2.multimodal_multi_repeat_policy.v1",
            "policy_id": "implicit-test-policy",
            "retained_calibration_hash_allowlist": sorted(set(calibration_hashes)),
            "maximum_repeat_age_hours": 24.0,
            "maximum_allowed_spread": {
                name: 1.0 for name in SPREAD_METRICS
            },
            "provider_is_truth": False,
            "release_authority": False,
            "public_safe": True,
        }
    _validate_policy(policy)
    mismatched_bindings = [
        field
        for field in BINDING_FIELDS
        if len({json.dumps(item.get(field), sort_keys=True) for item in calibrations})
        != 1
    ]
    stability_blockers = (
        ["multi_repeat_binding_mismatch"] if mismatched_bindings else []
    )
    quality_blockers: list[str] = []
    retained_states = [
        str(item.get("qualification_state") or "unknown")
        for item in calibrations
    ]
    if any(state != "qualified" for state in retained_states):
        quality_blockers.append("multi_repeat_retained_calibration_not_qualified")
    allowlist = set(policy["retained_calibration_hash_allowlist"])
    disallowed_hashes = sorted(
        {value for value in calibration_hashes if value not in allowlist}
    )
    if disallowed_hashes:
        stability_blockers.append(
            "multi_repeat_retained_calibration_hash_not_allowlisted"
        )
    if policy["schema_version"].endswith(".v2"):
        source_allowlist = set(policy["source_unit_hash_allowlist"])
        observed_source_units = {
            _source_key(item)
            for calibration in calibrations
            for item in calibration.get("observations", [])
        }
        if observed_source_units - source_allowlist:
            stability_blockers.append(
                "multi_repeat_source_unit_hash_not_allowlisted"
            )
        if source_allowlist - observed_source_units:
            stability_blockers.append(
                "multi_repeat_source_unit_hash_missing"
            )
    source_unit_coverage = _source_unit_coverage(calibrations)
    if not source_unit_coverage["complete_across_repeats"]:
        stability_blockers.append(
            "multi_repeat_units_incomplete:all_source_units"
        )
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
            stability_blockers.append(f"multi_repeat_units_incomplete:{name}")
    metric_lookup = {**metrics, **taxonomy_metrics}
    observed_spread_upper = {
        name: metric_lookup[name]["paired_max_minus_min_bootstrap_ci_95"][
            "upper"
        ]
        for name in SPREAD_METRICS
    }
    for name, observed in observed_spread_upper.items():
        if observed is None:
            stability_blockers.append(
                f"multi_repeat_spread_unavailable:{name}"
            )
        elif observed > policy["maximum_allowed_spread"][name]:
            stability_blockers.append(
                f"multi_repeat_spread_threshold_exceeded:{name}"
            )
    observed_times = [_parse_time(item.get("generated_at")) for item in calibrations]
    if as_of is None:
        available_times = [value for value in observed_times if value is not None]
        as_of = max(available_times) if available_times else datetime(
            1970, 1, 1, tzinfo=timezone.utc
        )
    elif as_of.tzinfo is None:
        raise ValueError("as_of must be timezone aware")
    as_of = as_of.astimezone(timezone.utc)
    if any(value is not None and value > as_of for value in observed_times):
        stability_blockers.append(
            "multi_repeat_freshness_as_of_precedes_observation"
        )
    repeat_ages_hours = [
        round(max(0.0, (as_of - value).total_seconds() / 3600), 6)
        if value is not None
        else None
        for value in observed_times
    ]
    if any(value is None for value in repeat_ages_hours):
        stability_blockers.append("multi_repeat_freshness_timestamp_missing")
    if any(
        value is not None and value > policy["maximum_repeat_age_hours"]
        for value in repeat_ages_hours
    ):
        stability_blockers.append("multi_repeat_freshness_age_exceeded")
    all_required_units_complete = (
        source_unit_coverage["complete_across_repeats"]
        and not any(
            not metric["complete_across_repeats"]
            for metric in [*metrics.values(), *taxonomy_metrics.values()]
        )
    )
    quality_blockers = sorted(set(quality_blockers))
    stability_blockers = sorted(set(stability_blockers))
    stability_incomplete = any(
        blocker.startswith("multi_repeat_units_incomplete")
        or blocker.startswith("multi_repeat_spread_unavailable")
        or blocker == "multi_repeat_freshness_timestamp_missing"
        for blocker in stability_blockers
    )
    quality_state = "blocked" if quality_blockers else "qualified"
    stability_state = (
        "incomplete"
        if stability_incomplete
        else ("blocked" if stability_blockers else "qualified")
    )
    blockers = sorted(set(quality_blockers + stability_blockers))
    result = {
        "schema_version": "a2.multimodal_multi_repeat_comparison.v2",
        "calibration_hashes": calibration_hashes,
        "repeat_count": len(calibrations),
        "policy_id": policy["policy_id"],
        "policy_hash": stable_hash(policy),
        "retained_calibration_hash_allowlist": sorted(allowlist),
        "disallowed_calibration_hashes": disallowed_hashes,
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
        "maximum_allowed_spread": policy["maximum_allowed_spread"],
        "observed_spread_upper": observed_spread_upper,
        "freshness_policy": {
            "as_of": as_of.isoformat().replace("+00:00", "Z"),
            "maximum_repeat_age_hours": policy["maximum_repeat_age_hours"],
            "repeat_ages_hours": repeat_ages_hours,
            "all_repeats_fresh": not any(
                blocker.startswith("multi_repeat_freshness")
                for blocker in stability_blockers
            ),
        },
        "all_required_units_complete": all_required_units_complete,
        "quality_state": quality_state,
        "quality_blockers": quality_blockers,
        "stability_state": stability_state,
        "stability_blockers": stability_blockers,
        "blockers": blockers,
        "promotion_eligible": (
            quality_state == "qualified" and stability_state == "qualified"
        ),
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
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    policy = json.loads((ROOT / args.policy).read_text(encoding="utf-8"))
    result = build_multi_repeat_comparison(
        [
            json.loads((ROOT / path).read_text(encoding="utf-8"))
            for path in args.calibration
        ],
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
        policy=policy,
        as_of=datetime.now(timezone.utc),
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["promotion_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
