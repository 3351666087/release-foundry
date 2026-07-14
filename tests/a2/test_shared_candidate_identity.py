from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from scripts.a2_verify_shared_candidate_identity import (
    verify_shared_candidate_identity,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (
        ROOT / "docs/a2/schemas/shared_candidate_identity_v1.schema.json"
    ).read_text(encoding="utf-8")
)


def exact_identity() -> dict:
    digest = "sha256:" + "1" * 64
    return {
        "schema_version": "a2.shared_candidate_identity.v1",
        "candidate_id": "candidate-2026-07-14-001",
        "a1": {
            "candidate_id": "candidate-2026-07-14-001",
            "git_sha": "a" * 40,
            "evidence_bundle_hash": digest,
        },
        "a2": {
            "candidate_id": "candidate-2026-07-14-001",
            "git_sha": "b" * 40,
            "decision_hash": digest,
            "grades_hash": digest,
            "review_conservation_hash": digest,
        },
        "a3": {
            "candidate_id": "candidate-2026-07-14-001",
            "git_sha": "c" * 40,
            "consumed_decision_hash": digest,
            "consumed_grades_hash": digest,
        },
        "binding_state": "exact",
        "blockers": [],
        "release_authority": False,
        "public_safe": True,
    }


class SharedCandidateIdentityTests(unittest.TestCase):
    def test_exact_identity_requires_all_three_projects_and_review_binding(self):
        jsonschema.Draft202012Validator(SCHEMA).validate(exact_identity())

    def test_exact_identity_rejects_missing_review_conservation_hash(self):
        value = exact_identity()
        del value["a2"]["review_conservation_hash"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(SCHEMA).validate(value)

    def test_blocked_identity_requires_at_least_one_explicit_blocker(self):
        value = exact_identity()
        value["binding_state"] = "blocked"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(SCHEMA).validate(value)

    def test_semantic_verifier_rejects_cross_project_candidate_mismatch(self):
        value = exact_identity()
        value["a3"]["candidate_id"] = "different-candidate"
        self.assertEqual(
            verify_shared_candidate_identity(value),
            ["shared_candidate_id_mismatch"],
        )

    def test_semantic_verifier_rejects_consumed_decision_or_grades_mismatch(self):
        value = exact_identity()
        value["a3"]["consumed_decision_hash"] = "sha256:" + "2" * 64
        value["a3"]["consumed_grades_hash"] = "sha256:" + "3" * 64
        self.assertEqual(
            verify_shared_candidate_identity(value),
            [
                "a3_consumed_decision_hash_mismatch",
                "a3_consumed_grades_hash_mismatch",
            ],
        )


if __name__ == "__main__":
    unittest.main()
