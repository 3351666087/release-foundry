from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/a2/schemas/multimodal_cross_provider_comparison.schema.json"


def stable_hash(value: Any) -> str:
    payload = (
        value
        if isinstance(value, bytes)
        else json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _observations(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return list(evidence.get("observations") or evidence.get("trials") or [])


def _binding(evidence: dict[str, Any]) -> dict[str, str]:
    observations = _observations(evidence)
    first = observations[0] if observations else {}
    provider_id = str(evidence.get("provider_id") or "ollama")
    model_id = str(evidence.get("model_id") or first.get("model_id") or "unknown")
    model_version = str(
        first.get("model_digest")
        or evidence.get("runtime_hash")
        or evidence.get("generated_at")
        or "unknown"
    )
    prompt_hash = str(
        evidence.get("prompt_hash")
        or evidence.get("binding", {}).get("prompt_hash")
        or first.get("prompt_hash")
        or ""
    )
    return {
        "provider_id": provider_id,
        "model_id": model_id,
        "model_version": model_version,
        "prompt_hash": prompt_hash,
    }


def build_comparison(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    left_items = {
        (item["case_id"], item["artifact_hash"], item.get("repeat", 1)): item
        for item in _observations(left)
    }
    right_items = {
        (item["case_id"], item["artifact_hash"], item.get("repeat", 1)): item
        for item in _observations(right)
    }
    comparisons = []
    receipts = []
    summary = {"agreement": 0, "semantic_disagreement": 0, "unavailable": 0}
    for key in sorted(set(left_items) & set(right_items)):
        left_item = left_items[key]
        right_item = right_items[key]
        left_state = str(left_item.get("parse_state") or "not_attempted")
        right_state = str(right_item.get("parse_state") or "not_attempted")
        left_risk = left_item.get("observed_risk")
        right_risk = right_item.get("observed_risk")
        if left_state != "valid_json" or right_state != "valid_json":
            state = "unavailable"
        elif left_risk == right_risk:
            state = "agreement"
        else:
            state = "semantic_disagreement"
        comparison = {
            "case_id": key[0],
            "artifact_hash": key[1],
            "left_state": left_state,
            "right_state": right_state,
            "left_observed_risk": left_risk,
            "right_observed_risk": right_risk,
            "comparison_state": state,
            "human_review_required": state == "semantic_disagreement",
        }
        comparisons.append(comparison)
        summary[state] += 1
        if state == "semantic_disagreement":
            comparison_hash = stable_hash(comparison)
            receipts.append(
                {
                    "receipt_id": stable_hash(
                        {
                            "comparison_hash": comparison_hash,
                            "queue": "multimodal_safety_reviewer",
                        }
                    ),
                    "comparison_hash": comparison_hash,
                    "artifact_hash": key[1],
                    "queue_state": "awaiting_human_review",
                    "reviewer_role": "multimodal_safety_reviewer",
                    "release_authority": False,
                }
            )
    result = {
        "schema_version": "a2.multimodal_cross_provider_comparison.v1",
        "left_evidence_hash": stable_hash(left),
        "right_evidence_hash": stable_hash(right),
        "left_binding": _binding(left),
        "right_binding": _binding(right),
        "comparisons": comparisons,
        "summary": summary,
        "human_review_queue_receipts": receipts,
        "release_authority": False,
        "raw_payload_included": False,
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
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    left = json.loads((ROOT / args.left).read_text(encoding="utf-8"))
    right = json.loads((ROOT / args.right).read_text(encoding="utf-8"))
    result = build_comparison(left, right)
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output}: {result['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
