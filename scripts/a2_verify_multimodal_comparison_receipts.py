from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_build_multimodal_cross_provider_comparison import stable_hash


def verify_comparison_receipts(comparison: dict[str, Any]) -> dict[str, Any]:
    expected_artifact_hash = stable_hash(
        {
            "left_evidence_hash": comparison["left_evidence_hash"],
            "right_evidence_hash": comparison["right_evidence_hash"],
            "comparisons": comparison["comparisons"],
            "aggregate_comparisons": comparison["aggregate_comparisons"],
        }
    )
    errors: list[str] = []
    if comparison.get("comparison_artifact_hash") != expected_artifact_hash:
        errors.append("comparison_artifact_hash_mismatch")

    repeat_by_hash = {
        stable_hash(item): item
        for item in comparison["comparisons"]
        if item["comparison_state"] == "semantic_disagreement"
    }
    aggregate_by_hash = {
        stable_hash(item): item
        for item in comparison["aggregate_comparisons"]
        if item["comparison_state"] == "internally_unstable"
    }
    expected_receipts = {
        ("repeat", comparison_hash): item
        for comparison_hash, item in repeat_by_hash.items()
    } | {
        ("aggregate", comparison_hash): item
        for comparison_hash, item in aggregate_by_hash.items()
    }
    seen: set[tuple[str, str]] = set()
    for receipt in comparison["human_review_queue_receipts"]:
        key = (receipt["review_scope"], receipt["comparison_hash"])
        if key in seen:
            errors.append("duplicate_review_receipt")
        seen.add(key)
        source = expected_receipts.get(key)
        if source is None:
            errors.append("orphan_review_receipt")
            continue
        if receipt["comparison_artifact_hash"] != expected_artifact_hash:
            errors.append("receipt_artifact_hash_mismatch")
        expected_receipt_id = stable_hash(
            {
                "comparison_artifact_hash": expected_artifact_hash,
                "comparison_hash": receipt["comparison_hash"],
                "review_scope": receipt["review_scope"],
                "queue": "multimodal_safety_reviewer",
            }
        )
        if receipt["receipt_id"] != expected_receipt_id:
            errors.append("receipt_id_mismatch")
        if (receipt["case_id"], receipt["artifact_hash"]) != (
            source["case_id"],
            source["artifact_hash"],
        ):
            errors.append("receipt_source_binding_mismatch")
    if seen != set(expected_receipts):
        errors.append("missing_review_receipt")
    return {
        "schema_version": "a2.multimodal_comparison_receipt_verification.v1",
        "comparison_artifact_hash": expected_artifact_hash,
        "receipt_count": len(comparison["human_review_queue_receipts"]),
        "verification_state": "verified" if not errors else "rejected",
        "errors": sorted(set(errors)),
        "release_authority": False,
        "public_safe": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    comparison = json.loads((ROOT / args.comparison).read_text(encoding="utf-8"))
    result = verify_comparison_receipts(comparison)
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["verification_state"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
