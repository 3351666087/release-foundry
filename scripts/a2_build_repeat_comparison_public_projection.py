from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT
    / "docs/a2/schemas/multimodal_repeat_comparison_public_projection_v1.schema.json"
)


def _hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def build_public_projection(
    comparison: dict[str, Any],
    *,
    source_path: str,
    source_bytes: bytes,
) -> dict[str, Any]:
    if comparison.get("schema_version") != (
        "a2.multimodal_multi_repeat_comparison.v2"
    ):
        raise ValueError("repeat comparison v2 is required")
    if comparison.get("public_safe") is not True:
        raise ValueError("repeat comparison is not public safe")
    if comparison.get("release_authority") is not False:
        raise ValueError("repeat comparison cannot grant release authority")
    if comparison.get("raw_provider_text_included") is not False:
        raise ValueError("repeat comparison includes raw provider text")
    result = {
        "schema_version": (
            "a2.multimodal_repeat_comparison_public_projection.v1"
        ),
        "source_comparison_path": source_path,
        "source_comparison_hash": _hash(source_bytes),
        "policy_id": comparison["policy_id"],
        "policy_hash": comparison["policy_hash"],
        "repeat_count": comparison["repeat_count"],
        "binding_fields": comparison["binding_fields"],
        "mismatched_binding_fields": comparison["mismatched_binding_fields"],
        "quality_state": comparison["quality_state"],
        "quality_blockers": comparison["quality_blockers"],
        "stability_state": comparison["stability_state"],
        "stability_blockers": comparison["stability_blockers"],
        "maximum_allowed_spread": comparison["maximum_allowed_spread"],
        "observed_spread_upper": comparison["observed_spread_upper"],
        "freshness_policy": comparison["freshness_policy"],
        "promotion_eligible": comparison["promotion_eligible"],
        "provider_is_truth": False,
        "raw_provider_text_included": False,
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
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = ROOT / args.comparison
    source_bytes = source.read_bytes()
    result = build_public_projection(
        json.loads(source_bytes),
        source_path=args.comparison,
        source_bytes=source_bytes,
    )
    (ROOT / args.output).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output}: quality={result['quality_state']} "
        f"stability={result['stability_state']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
