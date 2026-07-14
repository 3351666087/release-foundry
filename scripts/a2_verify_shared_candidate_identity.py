from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs/a2/schemas/shared_candidate_identity_v1.schema.json"


def verify_shared_candidate_identity(value: dict[str, Any]) -> list[str]:
    jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
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
    if value["binding_state"] == "blocked" and not blockers:
        blockers.append("blocked_binding_missing_reason")
    return sorted(set(blockers))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    value = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    blockers = verify_shared_candidate_identity(value)
    print(json.dumps({"blockers": blockers, "verified": not blockers}, sort_keys=True))
    return 0 if not blockers else 2


if __name__ == "__main__":
    raise SystemExit(main())
