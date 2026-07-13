from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.a2_build_multimodal_cross_provider_comparison import ROOT, stable_hash


def verify_review_chain(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    seen_receipts: set[str] = set()
    seen_dispositions: set[tuple[str, str]] = set()
    previous_hash = ""
    for sequence, receipt in enumerate(receipts, 1):
        receipt_hash = stable_hash(receipt)
        if receipt_hash in seen_receipts:
            errors.append("duplicate_receipt")
        seen_receipts.add(receipt_hash)
        disposition_key = (
            str(receipt.get("queue_receipt_hash") or ""),
            str(receipt.get("disposition") or ""),
        )
        if disposition_key in seen_dispositions:
            errors.append("duplicate_disposition")
        seen_dispositions.add(disposition_key)
        if receipt.get("review_sequence") != sequence:
            errors.append("noncontiguous_review_sequence")
        if receipt.get("predecessor_receipt_hash") != previous_hash:
            errors.append("predecessor_receipt_hash_mismatch")
        previous_hash = receipt_hash
    return {
        "schema_version": "a2.multimodal_review_chain_verification.v1",
        "receipt_count": len(receipts),
        "terminal_receipt_hash": previous_hash,
        "verification_state": "verified" if not errors else "rejected",
        "errors": sorted(set(errors)),
        "release_authority": False,
        "public_safe": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    value = json.loads((ROOT / args.receipts).read_text(encoding="utf-8"))
    receipts = value if isinstance(value, list) else value["receipts"]
    result = verify_review_chain(receipts)
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result["verification_state"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
