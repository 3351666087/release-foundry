from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.a2_build_multimodal_cross_provider_comparison import stable_hash


SCHEMA = ROOT / "docs/a2/schemas/multimodal_three_way_comparison.schema.json"


def _observations(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    return list(evidence.get("observations") or evidence.get("trials") or [])


def _eligible(item: dict[str, Any] | None) -> bool:
    return bool(
        item
        and item.get("http_state") == "completed"
        and item.get("parse_state") == "valid_json"
        and item.get("observed_risk") is not None
        and item.get("promotion_eligible", True)
    )


def build_three_way_comparison(
    providers: dict[str, dict[str, Any]],
    *,
    partial_journals: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    if len(providers) != 3:
        raise ValueError("three-way comparison requires exactly three providers")
    partial_journals = partial_journals or {}
    indexes = {
        provider: {
            (item["case_id"], item["artifact_hash"], item.get("repeat", 1)): item
            for item in _observations(evidence)
        }
        for provider, evidence in providers.items()
    }
    all_keys = sorted(set().union(*(set(index) for index in indexes.values())))
    comparisons = []
    summary = {"agreement": 0, "semantic_disagreement": 0, "unavailable": 0}
    pending_receipts = []
    for case_id, artifact_hash, repeat in all_keys:
        states = {}
        eligible_values = []
        for provider in sorted(providers):
            item = indexes[provider].get((case_id, artifact_hash, repeat))
            eligible = _eligible(item)
            observed = item.get("observed_risk") if eligible and item else None
            states[provider] = {
                "eligible": eligible,
                "parse_state": (
                    str(item.get("parse_state") or "not_attempted")
                    if item
                    else "missing_repeat"
                ),
                "observed_risk": observed,
            }
            if eligible:
                eligible_values.append(observed)
        if len(eligible_values) < 2:
            comparison_state = "unavailable"
        elif len(set(eligible_values)) == 1:
            comparison_state = "agreement"
        else:
            comparison_state = "semantic_disagreement"
        comparison = {
            "case_id": case_id,
            "artifact_hash": artifact_hash,
            "repeat": repeat,
            "eligible_provider_count": len(eligible_values),
            "provider_states": states,
            "comparison_state": comparison_state,
            "human_review_required": comparison_state == "semantic_disagreement",
        }
        comparisons.append(comparison)
        summary[comparison_state] += 1
        if comparison_state == "semantic_disagreement":
            pending_receipts.append(comparison)
    evidence_hashes = {
        provider: stable_hash(evidence)
        for provider, evidence in sorted(providers.items())
    }
    partial_hashes = {
        provider: (
            stable_hash(partial_journals[provider])
            if partial_journals.get(provider) is not None
            else ""
        )
        for provider in sorted(providers)
    }
    comparison_artifact_hash = stable_hash({
        "evidence_hashes": evidence_hashes,
        "partial_journal_hashes": partial_hashes,
        "comparisons": comparisons,
    })
    receipts_by_id = {}
    for comparison in pending_receipts:
        comparison_hash = stable_hash({
            "case_id": comparison["case_id"],
            "artifact_hash": comparison["artifact_hash"],
            "repeat": comparison["repeat"],
            "provider_states": comparison["provider_states"],
            "comparison_state": comparison["comparison_state"],
            "eligibility_rule": "at_least_two_eligible_and_semantically_disagree",
        })
        receipt_id = stable_hash({
            "comparison_hash": comparison_hash,
            "queue": "multimodal_safety_reviewer",
        })
        receipts_by_id[receipt_id] = {
            "receipt_id": receipt_id,
            "comparison_artifact_hash": comparison_artifact_hash,
            "comparison_hash": comparison_hash,
            "artifact_hash": comparison["artifact_hash"],
            "case_id": comparison["case_id"],
            "repeat": comparison["repeat"],
            "eligibility_rule": "at_least_two_eligible_and_semantically_disagree",
            "queue_state": "awaiting_human_review",
            "reviewer_role": "multimodal_safety_reviewer",
            "release_authority": False,
        }
    receipts = [receipts_by_id[key] for key in sorted(receipts_by_id)]
    if sum(summary.values()) != len(comparisons):
        raise ValueError("three-way comparison summary conservation failed")
    if len(receipts) != summary["semantic_disagreement"]:
        raise ValueError("three-way disagreement receipt conservation failed")
    result = {
        "schema_version": "a2.multimodal_three_way_comparison.v1",
        "comparison_artifact_hash": comparison_artifact_hash,
        "evidence_hashes": evidence_hashes,
        "partial_journal_hashes": partial_hashes,
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
    parser.add_argument("--provider", action="append", required=True, help="label=path")
    parser.add_argument("--partial", action="append", default=[], help="label=path")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    def load_pairs(values: list[str]) -> dict[str, dict[str, Any]]:
        loaded = {}
        for value in values:
            label, separator, path = value.partition("=")
            if not separator:
                raise SystemExit("provider/partial arguments must use label=path")
            loaded[label] = json.loads((ROOT / path).read_text(encoding="utf-8"))
        return loaded

    result = build_three_way_comparison(
        load_pairs(args.provider), partial_journals=load_pairs(args.partial)
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.output}: {result['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
