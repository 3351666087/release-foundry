from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "docs/a2/schemas/local_multimodal_availability_comparison_v1.schema.json"
)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _case_key(trial: dict[str, Any]) -> tuple[str, str]:
    return (
        str(trial.get("case_id") or ""),
        str(trial.get("artifact_hash") or ""),
    )


def _duration(trial: dict[str, Any]) -> float | None:
    receipt = trial.get("duration_receipt")
    if isinstance(receipt, dict) and receipt.get("effective_seconds") is not None:
        return float(receipt["effective_seconds"])
    attempts = trial.get("attempt_receipts") or []
    values = []
    for attempt in attempts:
        duration = attempt.get("duration_receipt") or {}
        if duration.get("effective_seconds") is not None:
            values.append(float(duration["effective_seconds"]))
    return sum(values) if values else None


def _nearest_rank(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * probability + 0.999999) - 1))
    return ordered[index]


def summarize(artifact: dict[str, Any]) -> dict[str, Any]:
    trials = artifact.get("trials") or []
    request_receipt = artifact.get("request_count_receipt") or {}
    completed = int(request_receipt.get("completed") or 0)
    eligible = sum(
        trial.get("eligible") is True
        or trial.get("observed_risk") is not None
        for trial in trials
    )
    timeout_count = sum(
        any(
            attempt.get("error_class") == "timeout"
            for attempt in trial.get("attempt_receipts") or []
        )
        for trial in trials
    )
    durations = [
        value for value in (_duration(trial) for trial in trials) if value is not None
    ]
    binding_summaries = list((artifact.get("binding_summaries") or {}).values())
    if binding_summaries:
        eligible = sum(int(item.get("eligible_count") or 0) for item in binding_summaries)
    return {
        "artifact_hash": stable_hash(artifact),
        "attempted_count": int(request_receipt.get("attempted") or len(trials)),
        "completed_count": completed,
        "eligible_count": eligible,
        "failed_count": int(request_receipt.get("failed") or 0),
        "timeout_case_count": timeout_count,
        "latency_seconds": {
            "count": len(durations),
            "median": _nearest_rank(durations, 0.5),
            "p95_nearest_rank": _nearest_rank(durations, 0.95),
            "maximum": max(durations) if durations else None,
        },
        "qualification_state": artifact.get("qualification_state", "blocked"),
    }


def build_comparison(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    left_label: str,
    right_label: str,
) -> dict[str, Any]:
    left_cases = sorted(_case_key(item) for item in left.get("trials") or [])
    right_cases = sorted(_case_key(item) for item in right.get("trials") or [])
    same_case_set = left_cases == right_cases and bool(left_cases)
    blockers = [] if same_case_set else ["local_availability_case_set_mismatch"]
    result = {
        "schema_version": "a2.local_multimodal_availability_comparison.v1",
        "same_case_set": same_case_set,
        "case_set_hash": stable_hash(left_cases) if same_case_set else None,
        "providers": {
            left_label: summarize(left),
            right_label: summarize(right),
        },
        "blockers": blockers,
        "comparison_state": "complete" if same_case_set else "blocked",
        "quality_comparison_performed": False,
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
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--left-label", required=True)
    parser.add_argument("--right-label", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_comparison(
        json.loads((ROOT / args.left).read_text(encoding="utf-8")),
        json.loads((ROOT / args.right).read_text(encoding="utf-8")),
        left_label=args.left_label,
        right_label=args.right_label,
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["comparison_state"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
