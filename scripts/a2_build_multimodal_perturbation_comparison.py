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


SCHEMA = (
    ROOT
    / "docs/a2/schemas/multimodal_perturbation_comparison_v1.schema.json"
)


def _source_outcomes(calibration: dict[str, Any]) -> list[bool]:
    grouped: dict[str, list[bool]] = {}
    for item in calibration.get("observations", []):
        if (
            item.get("expected_risk") is True
            and item.get("source_case_hash")
            and item.get("perturbation")
        ):
            if item.get("observed_risk") is None:
                continue
            grouped.setdefault(str(item["source_case_hash"]), []).append(
                item["observed_risk"] is True
            )
    return [
        all(grouped[source_hash])
        for source_hash in sorted(grouped)
    ]


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * probability)
    return ordered[index]


def _bootstrap_sensitivities(
    outcomes: list[bool], *, samples: int, randomizer: random.Random
) -> list[float]:
    if not outcomes:
        return []
    count = len(outcomes)
    return [
        sum(randomizer.choice(outcomes) for _ in range(count)) / count
        for _ in range(samples)
    ]


def build_perturbation_comparison(
    round47: dict[str, Any],
    round48: dict[str, Any],
    *,
    bootstrap_samples: int = 2000,
    seed: int = 49,
) -> dict[str, Any]:
    if bootstrap_samples < 100:
        raise ValueError("bootstrap samples must be at least 100")
    round47_outcomes = _source_outcomes(round47)
    round48_outcomes = _source_outcomes(round48)
    blockers = []
    if not round47_outcomes:
        blockers.append("round47_transformed_attack_observations_unavailable")
    if not round48_outcomes:
        blockers.append("round48_transformed_attack_observations_unavailable")

    randomizer = random.Random(seed)
    round47_bootstrap = _bootstrap_sensitivities(
        round47_outcomes, samples=bootstrap_samples, randomizer=randomizer
    )
    round48_bootstrap = _bootstrap_sensitivities(
        round48_outcomes, samples=bootstrap_samples, randomizer=randomizer
    )
    delta_bootstrap = [
        right - left
        for left, right in zip(round47_bootstrap, round48_bootstrap)
    ]

    def summary(outcomes: list[bool], bootstrap: list[float]) -> dict[str, Any]:
        sensitivity = sum(outcomes) / len(outcomes) if outcomes else None
        return {
            "distinct_source_count": len(outcomes),
            "detected_source_count": sum(outcomes),
            "sensitivity": sensitivity,
            "bootstrap_ci_95": {
                "lower": _percentile(bootstrap, 0.025) if bootstrap else None,
                "upper": _percentile(bootstrap, 0.975) if bootstrap else None,
            },
        }

    result = {
        "schema_version": "a2.multimodal_perturbation_comparison.v1",
        "round47_calibration_hash": stable_hash(round47),
        "round48_calibration_hash": stable_hash(round48),
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "round47": summary(round47_outcomes, round47_bootstrap),
        "round48": summary(round48_outcomes, round48_bootstrap),
        "sensitivity_delta_round48_minus_round47": (
            (
                sum(round48_outcomes) / len(round48_outcomes)
                - sum(round47_outcomes) / len(round47_outcomes)
            )
            if round47_outcomes and round48_outcomes
            else None
        ),
        "delta_bootstrap_ci_95": {
            "lower": (
                _percentile(delta_bootstrap, 0.025) if delta_bootstrap else None
            ),
            "upper": (
                _percentile(delta_bootstrap, 0.975) if delta_bootstrap else None
            ),
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
    parser.add_argument("--round47", required=True)
    parser.add_argument("--round48", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=49)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_perturbation_comparison(
        json.loads((ROOT / args.round47).read_text(encoding="utf-8")),
        json.loads((ROOT / args.round48).read_text(encoding="utf-8")),
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["promotion_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
