from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_build_multimodal_cross_provider_comparison import stable_hash


SCHEMA = (
    ROOT
    / "docs/a2/schemas/multimodal_review_conservation_v1.schema.json"
)
COLLECTION_SCHEMA = (
    ROOT
    / "docs/a2/schemas/multimodal_real_review_collection_v1.schema.json"
)
RECEIPT_SCHEMA = (
    ROOT / "docs/a2/schemas/multimodal_real_review_receipt.schema.json"
)


def validate_review_collection(collection: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator(
        json.loads(COLLECTION_SCHEMA.read_text(encoding="utf-8"))
    ).validate(collection)
    receipt_validator = jsonschema.Draft202012Validator(
        json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
    )
    for receipt in collection["receipts"]:
        receipt_validator.validate(receipt)


def verify_review_conservation(
    queue_receipts: list[dict[str, Any]],
    review_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    queue_by_hash: dict[str, dict[str, Any]] = {}
    queue_ids: set[str] = set()
    for receipt in queue_receipts:
        receipt_id = str(receipt.get("receipt_id") or "")
        receipt_hash = stable_hash(receipt)
        if receipt_id in queue_ids or receipt_hash in queue_by_hash:
            errors.append("duplicate_queue_receipt")
        queue_ids.add(receipt_id)
        queue_by_hash[receipt_hash] = receipt

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for receipt in review_receipts:
        queue_hash = str(receipt.get("queue_receipt_hash") or "")
        if queue_hash not in queue_by_hash:
            errors.append("orphan_review_receipt")
        grouped[queue_hash].append(receipt)

    latest_receipt_hashes: dict[str, str] = {}
    for queue_hash, receipts in grouped.items():
        ordered = sorted(receipts, key=lambda item: item.get("review_sequence", 0))
        sequences = [item.get("review_sequence") for item in ordered]
        if sequences != list(range(1, len(ordered) + 1)):
            errors.append("noncontiguous_queue_review_sequence")
        previous_hash = ""
        for receipt in ordered:
            if receipt.get("predecessor_receipt_hash") != previous_hash:
                errors.append("queue_review_predecessor_mismatch")
            previous_hash = stable_hash(receipt)
        if queue_hash in queue_by_hash and ordered:
            latest_receipt_hashes[queue_hash] = previous_hash

    reviewed_count = sum(
        queue_hash in latest_receipt_hashes for queue_hash in queue_by_hash
    )
    pending_count = len(queue_by_hash) - reviewed_count
    result = {
        "schema_version": "a2.multimodal_review_conservation.v1",
        "queue_receipt_count": len(queue_by_hash),
        "reviewed_queue_receipt_count": reviewed_count,
        "pending_queue_receipt_count": pending_count,
        "latest_receipt_hashes": latest_receipt_hashes,
        "conservation_holds": (
            reviewed_count + pending_count == len(queue_by_hash)
        ),
        "verification_state": "verified" if not errors else "rejected",
        "errors": sorted(set(errors)),
        "release_authority": False,
        "public_safe": True,
    }
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
    ).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    comparison = json.loads((ROOT / args.comparison).read_text(encoding="utf-8"))
    reviews = json.loads((ROOT / args.reviews).read_text(encoding="utf-8"))
    if not isinstance(reviews, list):
        validate_review_collection(reviews)
    result = verify_review_conservation(
        comparison["human_review_queue_receipts"],
        reviews if isinstance(reviews, list) else reviews["receipts"],
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["verification_state"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
