import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys

import jsonschema

from scripts.a2_postgresql_proof_launcher import (
    build_command,
    build_dry_run_receipt,
    build_environment,
)
from scripts.a2_verify_multimodal_review_chain import verify_review_chain
from scripts.a2_resolve_multimodal_disagreement import build_real_review_receipt
from scripts.a2_build_multimodal_cross_provider_comparison import stable_hash

ROOT = Path(__file__).resolve().parents[2]


class Round42MultimodalHardeningTests(unittest.TestCase):
    def queue_receipt(self):
        return {
            "receipt_id": "sha256:" + "1" * 64,
            "comparison_artifact_hash": "sha256:" + "2" * 64,
            "comparison_hash": "sha256:" + "3" * 64,
            "artifact_hash": "sha256:" + "4" * 64,
            "case_id": "case",
        }

    def test_review_chain_verifier_accepts_chain_and_rejects_break(self):
        first = build_real_review_receipt(
            self.queue_receipt(),
            comparison_artifact_hash="sha256:" + "2" * 64,
            reviewer_identity_hash="sha256:" + "5" * 64,
            disposition="request_more_evidence",
            rationale_code="insufficient",
            reviewed_at="2026-07-14T00:00:00Z",
        )
        second = build_real_review_receipt(
            self.queue_receipt(),
            comparison_artifact_hash="sha256:" + "2" * 64,
            reviewer_identity_hash="sha256:" + "6" * 64,
            disposition="confirm_risk",
            rationale_code="visible",
            predecessor_receipt_hash=stable_hash(first),
            prior_receipts=[first],
            reviewed_at="2026-07-14T00:01:00Z",
        )
        self.assertEqual(
            verify_review_chain([first, second])["verification_state"], "verified"
        )
        broken = dict(second, predecessor_receipt_hash="sha256:" + "9" * 64)
        self.assertEqual(
            verify_review_chain([first, broken])["verification_state"], "rejected"
        )

    def test_review_chain_cli_exit_codes_and_schema(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            relative = Path(temporary).relative_to(ROOT)
            receipts_path = relative / "receipts.json"
            output_path = relative / "verification.json"
            (ROOT / receipts_path).write_text("[]\n", encoding="utf-8")
            verified = subprocess.run(
                [
                    sys.executable,
                    "scripts/a2_verify_multimodal_review_chain.py",
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(verified.returncode, 0)
            rejected_receipt = {
                "review_sequence": 2,
                "predecessor_receipt_hash": "",
                "queue_receipt_hash": "sha256:" + "1" * 64,
                "disposition": "confirm_risk",
            }
            (ROOT / receipts_path).write_text(
                json.dumps([rejected_receipt]), encoding="utf-8"
            )
            rejected = subprocess.run(
                [
                    sys.executable,
                    "scripts/a2_verify_multimodal_review_chain.py",
                    "--receipts",
                    str(receipts_path),
                    "--output",
                    str(output_path),
                ],
                cwd=ROOT,
                check=False,
            )
            self.assertEqual(rejected.returncode, 2)
            schema = json.loads(
                (
                    ROOT
                    / "docs/a2/schemas/multimodal_review_chain_verification.schema.json"
                ).read_text(encoding="utf-8")
            )
            jsonschema.Draft202012Validator(schema).validate(
                json.loads((ROOT / output_path).read_text(encoding="utf-8"))
            )

    def test_temporary_postgres_dsn_is_only_added_to_child_environment(self):
        with patch.dict("os.environ", {}, clear=True):
            child = build_environment("postgresql://temporary.invalid/releasefoundry")
            self.assertEqual(
                child["POSTGRES_DSN"], "postgresql://temporary.invalid/releasefoundry"
            )
            self.assertNotIn("POSTGRES_DSN", __import__("os").environ)
        self.assertEqual(
            build_command([])[-1], "tests/a2/test_result_persistence.py"
        )
        self.assertTrue((ROOT / build_command([])[-1]).is_file())
        dry_run = build_dry_run_receipt(["tests/a2/test_result_persistence.py"])
        self.assertFalse(dry_run["dsn_present"])
        self.assertFalse(dry_run["executes_tests"])
        self.assertNotIn("postgresql://", json.dumps(dry_run))

    def test_round42_public_evidence_is_schema_valid_and_non_authoritative(self):
        pairs = (
            (
                "multimodal_runtime_matrix_v2.schema.json",
                "a2_multimodal_runtime_matrix_round42_qwen3vl.json",
            ),
            (
                "multimodal_runtime_matrix_v2.schema.json",
                "a2_multimodal_runtime_matrix_round42_llava.json",
            ),
            (
                "multimodal_runtime_partial.schema.json",
                "a2_multimodal_runtime_matrix_round42_qwen3vl.partial.json",
            ),
            (
                "multimodal_runtime_partial.schema.json",
                "a2_multimodal_runtime_matrix_round42_llava.partial.json",
            ),
            (
                "multimodal_cross_provider_comparison_v3.schema.json",
                "a2_multimodal_local_comparison_round42.json",
            ),
            (
                "multimodal_comparison_receipt_verification.schema.json",
                "a2_multimodal_local_comparison_verification_round42.json",
            ),
            (
                "postgresql_persistence_qualification.schema.json",
                "a2_postgresql_persistence_qualification_round42.json",
            ),
            (
                "trusted_spine_binding_recheck.schema.json",
                "a2_trusted_spine_binding_recheck_round42.json",
            ),
        )
        for schema_name, evidence_name in pairs:
            with self.subTest(evidence=evidence_name):
                schema = json.loads(
                    (ROOT / "docs/a2/schemas" / schema_name).read_text(
                        encoding="utf-8"
                    )
                )
                evidence = json.loads(
                    (ROOT / "docs/evidence" / evidence_name).read_text(
                        encoding="utf-8"
                    )
                )
                jsonschema.Draft202012Validator(schema).validate(evidence)
                self.assertTrue(evidence["public_safe"])
                self.assertFalse(evidence["release_authority"])


if __name__ == "__main__":
    unittest.main()
