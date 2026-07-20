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

from services.judge.result_persistence import stable_hash


SCHEMAS = {
    "a2.shared_candidate_identity.v1": (
        ROOT / "docs/a2/schemas/shared_candidate_identity_v1.schema.json"
    ),
    "a2.shared_candidate_identity.v2": (
        ROOT / "docs/a2/schemas/shared_candidate_identity_v2.schema.json"
    ),
}


def verify_shared_candidate_identity(
    value: dict[str, Any],
    *,
    actual_review_collection_hash: str | None = None,
    actual_review_conservation_hash: str | None = None,
) -> list[str]:
    schema_path = SCHEMAS.get(str(value.get("schema_version") or ""))
    if schema_path is None:
        raise ValueError("unsupported shared candidate identity schema")
    jsonschema.Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8"))
    ).validate(value)
    blockers = list(value.get("blockers", []))
    candidate_ids = {
        value["candidate_id"],
        value["a1"]["candidate_id"],
        value["a2"]["candidate_id"],
        value["a3"]["candidate_id"],
    }
    if len(candidate_ids) != 1:
        blockers.append("shared_candidate_id_mismatch")
    if value["a2"]["decision_hash"] != value["a3"]["consumed_decision_hash"]:
        blockers.append("a3_consumed_decision_hash_mismatch")
    if value["a2"]["grades_hash"] != value["a3"]["consumed_grades_hash"]:
        blockers.append("a3_consumed_grades_hash_mismatch")
    if value["schema_version"] == "a2.shared_candidate_identity.v2":
        if (
            actual_review_collection_hash is not None
            and value["a2"]["review_collection_hash"]
            != actual_review_collection_hash
        ):
            blockers.append("a2_review_collection_hash_mismatch")
        if (
            actual_review_conservation_hash is not None
            and value["a2"]["review_conservation_hash"]
            != actual_review_conservation_hash
        ):
            blockers.append("a2_review_conservation_hash_mismatch")
    if value["binding_state"] == "blocked" and not blockers:
        blockers.append("blocked_binding_missing_reason")
    return sorted(set(blockers))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--review-collection")
    parser.add_argument("--review-conservation")
    args = parser.parse_args()
    value = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    collection_hash = None
    conservation_hash = None
    if args.review_collection:
        collection_hash = stable_hash(
            json.loads((ROOT / args.review_collection).read_text(encoding="utf-8"))
        )
    if args.review_conservation:
        conservation_hash = stable_hash(
            json.loads(
                (ROOT / args.review_conservation).read_text(encoding="utf-8")
            )
        )
    blockers = verify_shared_candidate_identity(
        value,
        actual_review_collection_hash=collection_hash,
        actual_review_conservation_hash=conservation_hash,
    )
    print(json.dumps({"blockers": blockers, "verified": not blockers}, sort_keys=True))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
