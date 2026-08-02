import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from services.judge.incident_regression import (
    build_incident_regression_candidate_report,
)
from services.judge.result_persistence import stable_hash


ROOT = Path(__file__).resolve().parents[2]


class IncidentRegressionSafetyTests(unittest.TestCase):
    def test_existing_public_run_fixture_remains_replayable(self):
        report = self._build_report(self._incident())

        candidate = report["candidates"][0]
        fixture = json.loads(
            (
                ROOT
                / "fixtures/a2/runs/a2_s041_poor_retry_recovery.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            candidate["fixture_ref"],
            "fixtures/a2/runs/a2_s041_poor_retry_recovery.json",
        )
        self.assertEqual(candidate["fixture_sha256"], stable_hash(fixture))
        self.assertTrue(candidate["local_judge"]["available"])
        self.assertTrue(candidate["public_safe"])
        self.assertTrue(candidate["ready_for_case_book_review"])

    def test_untrusted_fixture_refs_are_not_read_or_exposed(self):
        invalid_refs = (
            str(
                (
                    ROOT / "fixtures/a2/runs/a2_s041_poor_retry_recovery.json"
                ).resolve()
            ),
            "fixtures/a2/runs/../../results/a2_case_book.json",
            r"fixtures\a2\runs\..\..\results\a2_case_book.json",
            "docs/evidence/private_refs/a2_private_receipt.json",
            "fixtures/a2/runs/a2_s041_poor_retry_recovery.txt",
        )
        for fixture_ref in invalid_refs:
            with self.subTest(fixture_ref=fixture_ref):
                incident = self._incident()
                incident["failed_case"]["fixture_ref"] = fixture_ref

                with patch(
                    "services.judge.incident_regression._load_fixture"
                ) as load_fixture:
                    report = self._build_report(incident)

                load_fixture.assert_not_called()
                candidate = report["candidates"][0]
                self.assertEqual(candidate["fixture_ref"], "")
                self.assertFalse(candidate["public_safe"])
                self.assertFalse(candidate["ready_for_case_book_review"])
                self.assertIn(
                    "needs_public_safety_or_replayable_fixture_fix",
                    candidate["promotion_blockers"],
                )
                self.assertNotIn(fixture_ref, json.dumps(report))

    def test_traversing_evidence_ref_is_not_exposed_or_review_ready(self):
        incident = self._incident()
        unsafe_ref = "fixtures/a2/runs/../../private/customer-payload.json"
        incident["evidence_refs"] = [unsafe_ref]

        report = self._build_report(incident)

        candidate = report["candidates"][0]
        self.assertFalse(candidate["public_safe"])
        self.assertFalse(candidate["ready_for_case_book_review"])
        self.assertNotIn(unsafe_ref, json.dumps(report))

    def test_malformed_incident_cohort_entries_are_rejected(self):
        for malformed_entry in (None, "not-an-object", []):
            with self.subTest(malformed_entry=malformed_entry):
                payload = {
                    "incidents": [
                        self._incident(),
                        malformed_entry,
                    ]
                }

                with self.assertRaisesRegex(
                    ValueError,
                    r"incidents\[1\] must be an object",
                ):
                    self._build_report(payload)

    def test_incidents_field_must_be_a_list(self):
        payload = {"incidents": self._incident()}

        with self.assertRaisesRegex(ValueError, "incidents must be a list"):
            self._build_report(payload)

    @staticmethod
    def _build_report(incident):
        return build_incident_regression_candidate_report(
            incident,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

    @staticmethod
    def _incident():
        return copy.deepcopy(
            json.loads(
                (
                    ROOT
                    / "fixtures/a2/incidents/a2_prod_incident_summary.json"
                ).read_text(encoding="utf-8")
            )
        )


if __name__ == "__main__":
    unittest.main()
