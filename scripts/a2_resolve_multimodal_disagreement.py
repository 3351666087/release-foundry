from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from scripts.a2_build_multimodal_cross_provider_comparison import ROOT, stable_hash

SCHEMA = ROOT / "docs/a2/schemas/multimodal_human_review_disposition.schema.json"
REAL_REVIEW_SCHEMA = ROOT / "docs/a2/schemas/multimodal_real_review_receipt.schema.json"


def build_disposition(
    receipt: dict[str, Any], *, comparison_artifact_hash: str,
    reviewer_identity_hash: str, disposition: str, rationale_code: str,
    reviewer_identity_class: str = "human_reviewer"
) -> dict[str, Any]:
    if receipt.get("comparison_artifact_hash") != comparison_artifact_hash:
        raise ValueError("receipt comparison artifact hash mismatch")
    result = {
        "schema_version": "a2.multimodal_human_review_disposition.v1",
        "queue_receipt_hash": stable_hash(receipt),
        "receipt_id": receipt["receipt_id"],
        "comparison_hash": receipt["comparison_hash"],
        "comparison_artifact_hash": comparison_artifact_hash,
        "artifact_hash": receipt["artifact_hash"],
        "case_id": receipt["case_id"],
        "reviewer_identity_hash": reviewer_identity_hash,
        "reviewer_identity_class": reviewer_identity_class,
        "reviewer_role": "multimodal_safety_reviewer",
        "disposition": disposition,
        **(
            {"disposition_text": "reference unavailable; collect more evidence"}
            if disposition == "reference_unavailable_collect_more_evidence"
            else {}
        ),
        "rationale_code": rationale_code,
        "release_authority": False,
        "raw_payload_included": False,
        "public_safe": True,
    }
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(result)
    return result


def build_real_review_receipt(
    receipt: dict[str, Any],
    *,
    comparison_artifact_hash: str,
    reviewer_identity_hash: str,
    disposition: str,
    rationale_code: str,
    predecessor_receipt_hash: str = "",
    prior_receipts: list[dict[str, Any]] | None = None,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    if receipt.get("comparison_artifact_hash") != comparison_artifact_hash:
        raise ValueError("receipt comparison artifact hash mismatch")
    prior_receipts = prior_receipts or []
    if any(
        item.get("queue_receipt_hash") == stable_hash(receipt)
        and item.get("disposition") == disposition
        for item in prior_receipts
    ):
        raise ValueError("duplicate review disposition")
    if predecessor_receipt_hash:
        if not prior_receipts or stable_hash(prior_receipts[-1]) != predecessor_receipt_hash:
            raise ValueError("review predecessor receipt mismatch")
    elif prior_receipts:
        raise ValueError("review predecessor receipt is required")
    completed_at = reviewed_at or datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    core = {
        "queue_receipt_hash": stable_hash(receipt),
        "comparison_artifact_hash": comparison_artifact_hash,
        "comparison_hash": receipt["comparison_hash"],
        "artifact_hash": receipt["artifact_hash"],
        "case_id": receipt["case_id"],
        "reviewer_identity_hash": reviewer_identity_hash,
        "reviewer_identity_class": "human_reviewer",
        "predecessor_receipt_hash": predecessor_receipt_hash,
        "review_sequence": len(prior_receipts) + 1,
        "review_completed_at": completed_at,
        "disposition": disposition,
        **(
            {"disposition_text": "reference unavailable; collect more evidence"}
            if disposition == "reference_unavailable_collect_more_evidence"
            else {}
        ),
        "rationale_code": rationale_code,
    }
    result = {
        "schema_version": "a2.multimodal_real_review_receipt.v1",
        "receipt_id": stable_hash(core),
        **core,
        "release_authority": False,
        "public_safe": True,
    }
    jsonschema.Draft202012Validator(
        json.loads(REAL_REVIEW_SCHEMA.read_text(encoding="utf-8"))
    ).validate(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison", required=True)
    parser.add_argument("--receipt-id", required=True)
    parser.add_argument("--reviewer-identity-hash", required=True)
    parser.add_argument(
        "--disposition",
        required=True,
        choices=(
            "uphold_left",
            "uphold_right",
            "inconclusive",
            "request_more_evidence",
            "reference_unavailable_collect_more_evidence",
        ),
    )
    parser.add_argument("--rationale-code", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    comparison = json.loads((ROOT / args.comparison).read_text(encoding="utf-8"))
    receipt = next((item for item in comparison["human_review_queue_receipts"] if item["receipt_id"] == args.receipt_id), None)
    if receipt is None:
        raise SystemExit("receipt id is not bound to the supplied comparison")
    result = build_disposition(
        receipt,
        comparison_artifact_hash=comparison["comparison_artifact_hash"],
        reviewer_identity_hash=args.reviewer_identity_hash,
        disposition=args.disposition,
        rationale_code=args.rationale_code,
    )
    (ROOT / args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output}: disposition={args.disposition}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
