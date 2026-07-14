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
from scripts.a2_build_multimodal_three_way_comparison import (
    _index_observations,
    _validate_provider_labels,
    load_pairs,
)


SCHEMA = ROOT / "docs/a2/schemas/multimodal_four_way_comparison_v1.schema.json"


def build_four_way_comparison(
    providers: dict[str, dict[str, Any]],
    *,
    partial_journals: dict[str, dict[str, Any] | None] | None = None,
    designated_high_quality_reference: str | None = None,
) -> dict[str, Any]:
    if len(providers) != 4:
        raise ValueError("four-way comparison requires exactly four providers")
    _validate_provider_labels(list(providers))
    partial_journals = partial_journals or {}
    if set(partial_journals) - set(providers):
        raise ValueError("partial journal labels must match provider labels")
    if (
        designated_high_quality_reference is not None
        and designated_high_quality_reference not in providers
    ):
        raise ValueError("designated high-quality reference must match provider labels")

    indexes = {
        provider: _index_observations(provider, evidence)
        for provider, evidence in providers.items()
    }
    all_keys = sorted(set().union(*(set(index) for index in indexes.values())))
    summary = {
        "four_way_agreement": 0,
        "three_way_agreement_with_unavailable": 0,
        "pairwise_agreement_with_unavailable": 0,
        "semantic_disagreement": 0,
        "unavailable": 0,
    }
    comparisons = []
    pending_receipts = []
    for case_id, artifact_hash, repeat in all_keys:
        states = {}
        eligible_values = []
        for provider in sorted(providers):
            item = indexes[provider].get((case_id, artifact_hash, repeat))
            eligible = bool(
                item
                and item.get("http_state") == "completed"
                and item.get("parse_state") == "valid_json"
                and item.get("observed_risk") is not None
                and item.get("promotion_eligible", True)
            )
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

        eligible_count = len(eligible_values)
        unanimous = eligible_count >= 2 and len(set(eligible_values)) == 1
        if eligible_count < 2:
            comparison_state = "unavailable"
        elif not unanimous:
            comparison_state = "semantic_disagreement"
        elif eligible_count == 4:
            comparison_state = "four_way_agreement"
        elif eligible_count == 3:
            comparison_state = "three_way_agreement_with_unavailable"
        else:
            comparison_state = "pairwise_agreement_with_unavailable"
        reference_unavailable = bool(
            "with_unavailable" in comparison_state
            and designated_high_quality_reference
            and not states[designated_high_quality_reference]["eligible"]
        )
        human_review_required = (
            comparison_state == "semantic_disagreement" or reference_unavailable
        )
        comparison = {
            "case_id": case_id,
            "artifact_hash": artifact_hash,
            "repeat": repeat,
            "eligible_provider_count": eligible_count,
            "provider_states": states,
            "comparison_state": comparison_state,
            "human_review_required": human_review_required,
        }
        comparisons.append(comparison)
        summary[comparison_state] += 1
        if human_review_required:
            pending_receipts.append({
                "comparison": comparison,
                "eligibility_rule": (
                    "designated_high_quality_reference_unavailable"
                    if reference_unavailable
                    else "at_least_two_eligible_and_semantically_disagree"
                ),
                "reference_provider": (
                    designated_high_quality_reference if reference_unavailable else ""
                ),
            })

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
    receipts = []
    for pending in pending_receipts:
        comparison = pending["comparison"]
        comparison_hash = stable_hash({
            "case_id": comparison["case_id"],
            "artifact_hash": comparison["artifact_hash"],
            "repeat": comparison["repeat"],
            "provider_states": comparison["provider_states"],
            "comparison_state": comparison["comparison_state"],
            "eligibility_rule": pending["eligibility_rule"],
            "reference_provider": pending["reference_provider"],
        })
        receipts.append({
            "receipt_id": stable_hash({
                "comparison_hash": comparison_hash,
                "queue": "multimodal_safety_reviewer",
            }),
            "comparison_artifact_hash": comparison_artifact_hash,
            "comparison_hash": comparison_hash,
            "artifact_hash": comparison["artifact_hash"],
            "case_id": comparison["case_id"],
            "repeat": comparison["repeat"],
            "eligibility_rule": pending["eligibility_rule"],
            **(
                {"reference_provider": pending["reference_provider"]}
                if pending["reference_provider"]
                else {}
            ),
            "queue_state": "awaiting_human_review",
            "reviewer_role": "multimodal_safety_reviewer",
            "release_authority": False,
        })

    pairwise_summaries = {}
    provider_names = sorted(providers)
    for left_index, left in enumerate(provider_names):
        for right in provider_names[left_index + 1 :]:
            pair_summary = {"agreement": 0, "semantic_disagreement": 0, "unavailable": 0}
            for comparison in comparisons:
                states = comparison["provider_states"]
                if not states[left]["eligible"] or not states[right]["eligible"]:
                    state = "unavailable"
                elif states[left]["observed_risk"] == states[right]["observed_risk"]:
                    state = "agreement"
                else:
                    state = "semantic_disagreement"
                pair_summary[state] += 1
            pairwise_summaries[f"{left}::{right}"] = pair_summary

    result = {
        "schema_version": "a2.multimodal_four_way_comparison.v1",
        "comparison_artifact_hash": comparison_artifact_hash,
        "evidence_hashes": evidence_hashes,
        "partial_journal_hashes": partial_hashes,
        "comparisons": comparisons,
        "summary": summary,
        "pairwise_summaries": pairwise_summaries,
        "human_review_queue_receipts": receipts,
        **(
            {"designated_high_quality_reference": designated_high_quality_reference}
            if designated_high_quality_reference is not None
            else {}
        ),
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
    parser.add_argument("--designated-high-quality-reference")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_four_way_comparison(
        load_pairs(args.provider),
        partial_journals=load_pairs(args.partial),
        designated_high_quality_reference=args.designated_high_quality_reference,
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
