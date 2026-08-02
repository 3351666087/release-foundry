import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from services.judge.releasefoundry_dataset_identity import RECEIPT_SCHEMA_VERSION
from services.judge.releasefoundry_test_receipts import (
    PUBLIC_RECEIPT_SCHEMA_VERSION,
    TEST_SCORING_SUMMARY_SCHEMA_VERSION,
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_terminal_receipt,
)
from services.judge.casebook import (
    build_case_book_report,
    promote_incident_candidates_to_case_book,
    verify_case_book_artifact,
)
from services.judge.incident_regression import (
    build_incident_regression_candidate_report,
    seal_incident_regression_candidate_report,
)
from services.judge.result_persistence import stable_hash


ROOT = Path(__file__).resolve().parents[2]
CASE_ID = "sample-a2-unit-test"


def _public_terminal_receipt() -> dict:
    private_receipt = build_releasefoundry_test_terminal_receipt(
        {
            "id": "synthetic-run",
            "dataset": 7,
            "result": {
                "status": "completed",
                "judge_version": "releasefoundry-grader-v1",
                "tests": [
                    {
                        "test_id": "releasefoundry-a2-unit-test",
                        "status": "completed",
                        "started_at": "2026-07-28T08:00:00Z",
                        "completed_at": "2026-07-28T08:00:01Z",
                        "action_results": [
                            {
                                "actor": "agent",
                                "action_type": "message",
                                "actual_response": "Verified response evidence.",
                                "llm_judgment": {"verdict": "pass"},
                            }
                        ],
                    }
                ],
            },
        },
        case_map={"releasefoundry-a2-unit-test": CASE_ID},
        expected_dataset_id=7,
    )
    return public_releasefoundry_test_terminal_receipt(private_receipt)


def _verified_terminal_scoring_metadata(public_receipt: dict) -> dict:
    test_receipt = public_receipt["tests"][0]
    return {
        "terminal_scoring_receipt_schema_version": (
            TEST_SCORING_SUMMARY_SCHEMA_VERSION
        ),
        "terminal_status": test_receipt["terminal_status"],
        "response_evidence_count": test_receipt["response_evidence_count"],
        "response_evidence_kinds": test_receipt["response_evidence_kinds"],
        "grading_signal_count": test_receipt["grading_signal_count"],
        "grading_signal_types": test_receipt["grading_signal_types"],
        "terminal_status_verified": test_receipt["terminal_status_verified"],
        "timestamps_verified": test_receipt["timestamps_verified"],
        "response_evidence_verified": test_receipt[
            "response_evidence_verified"
        ],
        "server_grading_signal_verified": test_receipt[
            "server_grading_signal_verified"
        ],
        "terminal_scoring_verified": test_receipt[
            "terminal_scoring_verified"
        ],
        "terminal_receipt_blockers": test_receipt["blockers"],
        "run_terminal_receipt_schema_version": PUBLIC_RECEIPT_SCHEMA_VERSION,
        "run_terminal_receipt_sha256": stable_hash(public_receipt),
        "run_expected_test_count": public_receipt["expected_test_count"],
        "run_verified_test_count": public_receipt["verified_test_count"],
        "run_receipt_complete": public_receipt["receipt_complete"],
        "run_dataset_id_verified": public_receipt[
            "run_dataset_id_verified"
        ],
        "run_result_terminal_verified": public_receipt[
            "run_result_terminal_verified"
        ],
        "server_grading_lifecycle_verified": public_receipt[
            "server_grading_lifecycle_verified"
        ],
        "exact_test_set_verified": public_receipt["exact_test_set_verified"],
        "all_expected_tests_terminal_scoring_verified": public_receipt[
            "all_expected_tests_terminal_scoring_verified"
        ],
        "observed_judge_version": public_receipt["observed_judge_version"],
        "judge_version_source": public_receipt["judge_version_source"],
        "judge_version_verified": public_receipt["judge_version_verified"],
        "aggregate_marker_used_as_acceptance_authority": public_receipt[
            "aggregate_marker_used_as_acceptance_authority"
        ],
        "run_terminal_receipt_blockers": public_receipt["blockers"],
        "dataset_identity_receipt_schema_version": RECEIPT_SCHEMA_VERSION,
        "dataset_identity_verified": True,
        "dataset_identity_receipt_sha256": "sha256:" + ("b" * 64),
        "dataset_identity_manifest_sha256": "sha256:" + ("c" * 64),
        "dataset_identity_content_sha256": "sha256:" + ("d" * 64),
        "dataset_identity_content_collection": "runs",
        "dataset_identity_content_item_count": 1,
        "dataset_identity_blockers": [],
    }


class CaseBookSafetyTests(unittest.TestCase):
    def test_calibration_cases_must_be_a_list(self):
        matrix = self._matrix(review_status="unreviewed")
        matrix["cases"] = {"case": matrix["cases"][0]}

        with self.assertRaisesRegex(
            ValueError,
            "case-book calibration cases must be a list",
        ):
            build_case_book_report(matrix)

    def test_malformed_calibration_case_rows_fail_closed(self):
        invalid_rows = (
            (None, r"case-book calibration cases\[1\] must be an object"),
            ({}, r"case-book calibration cases\[1\] requires case_id"),
        )
        for invalid_row, error in invalid_rows:
            with self.subTest(invalid_row=invalid_row):
                matrix = self._matrix(review_status="unreviewed")
                matrix["cases"].append(invalid_row)

                with self.assertRaisesRegex(ValueError, error):
                    build_case_book_report(matrix)

    def test_duplicate_calibration_case_ids_fail_closed_before_filtering(self):
        matrix = self._matrix(review_status="unreviewed")
        duplicate = deepcopy(matrix["cases"][0])
        duplicate["calibration_tags"] = []
        matrix["cases"].append(duplicate)

        with self.assertRaisesRegex(
            ValueError,
            "duplicate case-book calibration case_id",
        ):
            build_case_book_report(matrix)

    def test_malformed_calibration_tags_fail_closed(self):
        invalid_values = (
            ("judge_disagreement_regression", "must be a list"),
            (["judge_disagreement_regression", ""], r"\[1\] must be a non-empty string"),
            (
                ["judge_disagreement_regression", "judge_disagreement_regression"],
                "contains duplicate tag",
            ),
        )
        for invalid_value, error in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                matrix = self._matrix(review_status="unreviewed")
                matrix["cases"][0]["calibration_tags"] = invalid_value

                with self.assertRaisesRegex(ValueError, error):
                    build_case_book_report(matrix)

    def test_malformed_calibration_diffs_fail_closed(self):
        invalid_values = (
            ({"status": "mismatch"}, "must be a list"),
            (["mismatch"], r"\[0\] must be an object"),
        )
        for invalid_value, error in invalid_values:
            with self.subTest(invalid_value=invalid_value):
                matrix = self._matrix(review_status="unreviewed")
                matrix["cases"][0]["diffs"] = invalid_value

                with self.assertRaisesRegex(ValueError, error):
                    build_case_book_report(matrix)

    def test_malformed_calibration_sources_fail_closed(self):
        matrix = self._matrix(review_status="unreviewed")
        matrix["cases"][0]["sources"] = []

        with self.assertRaisesRegex(ValueError, "sources must be an object"):
            build_case_book_report(matrix)

    def test_malformed_calibration_source_rows_fail_closed(self):
        for source_key in ("local_judge", "releasefoundry_grading", "llm_judge"):
            with self.subTest(source_key=source_key):
                matrix = self._matrix(review_status="unreviewed")
                matrix["cases"][0]["sources"][source_key] = "malformed"

                with self.assertRaisesRegex(
                    ValueError,
                    rf"sources\.{source_key} must be an object",
                ):
                    build_case_book_report(matrix)

    def test_unreviewed_releasefoundry_row_cannot_satisfy_c5_evidence_gate(self):
        report = build_case_book_report(self._matrix(review_status="unreviewed"))

        self.assertEqual(report["regression_case_count"], 1)
        self.assertEqual(report["maturity_gate"]["reviewed_external_evidence_count"], 0)
        self.assertFalse(report["maturity_gate"]["ready"])

    def test_reviewed_releasefoundry_row_is_preserved_for_c5_evidence_count(self):
        report = build_case_book_report(self._matrix(review_status="reviewed"))

        self.assertEqual(report["maturity_gate"]["reviewed_external_evidence_count"], 1)
        self.assertFalse(report["maturity_gate"]["ready"])

        regression = report["regression_cases"][0]
        self.assertEqual(regression["releasefoundry_grading"]["metadata"]["review_status"], "reviewed")

    def test_reviewed_releasefoundry_row_without_retained_receipt_cannot_count(self):
        matrix = self._matrix(review_status="reviewed")
        matrix.pop("releasefoundry_run_terminal_receipt")

        report = build_case_book_report(matrix)

        self.assertEqual(
            report["maturity_gate"]["reviewed_external_evidence_count"],
            0,
        )

    def test_reviewed_releasefoundry_row_with_replaced_receipt_cannot_count(self):
        matrix = self._matrix(review_status="reviewed")
        matrix["releasefoundry_run_terminal_receipt"]["observed_judge_version"] = (
            "different-grader"
        )

        report = build_case_book_report(matrix)

        self.assertEqual(
            report["maturity_gate"]["reviewed_external_evidence_count"],
            0,
        )

    def test_reviewed_releasefoundry_row_requires_canonical_private_evidence_ref(self):
        invalid_refs = (
            "",
            "fixtures/a2/results/releasefoundry.json",
            "https://example.invalid/releasefoundry.json",
            "docs/evidence/private_refs/../releasefoundry.json",
        )
        for evidence_ref in invalid_refs:
            with self.subTest(evidence_ref=evidence_ref):
                matrix = self._matrix(review_status="reviewed")
                matrix["cases"][0]["sources"]["releasefoundry_grading"]["evidence_ref"] = evidence_ref

                report = build_case_book_report(matrix)

                self.assertEqual(
                    report["maturity_gate"]["reviewed_external_evidence_count"],
                    0,
                )

    def test_reviewed_releasefoundry_row_requires_reviewer_attestation(self):
        invalid_metadata = (
            {"review_status": "reviewed"},
            {
                "review_status": "reviewed",
                "reviewer_receipt": "reviewer@example.com",
                "reviewed_at_unix_ms": 1784700000000,
            },
            {
                "review_status": "reviewed",
                "reviewer_receipt": "sha256:" + ("a" * 64),
                "reviewed_at_unix_ms": True,
            },
            {
                "review_status": "reviewed",
                "reviewer_receipt": "sha256:" + ("a" * 64),
                "reviewed_at_unix_ms": "1784700000000",
            },
        )
        for metadata in invalid_metadata:
            with self.subTest(metadata=metadata):
                matrix = self._matrix(review_status="reviewed")
                matrix["cases"][0]["sources"]["releasefoundry_grading"]["metadata"] = metadata

                report = build_case_book_report(matrix)

                self.assertEqual(
                    report["maturity_gate"]["reviewed_external_evidence_count"],
                    0,
                )

    def test_reviewed_releasefoundry_row_requires_official_provider_identity(self):
        for provider in ("", "releasefoundry", "fake-provider", "offline_reference"):
            with self.subTest(provider=provider):
                matrix = self._matrix(review_status="reviewed")
                matrix["cases"][0]["sources"]["releasefoundry_grading"]["provider"] = provider

                report = build_case_book_report(matrix)

                self.assertEqual(
                    report["maturity_gate"]["reviewed_external_evidence_count"],
                    0,
                )

    def test_reviewed_releasefoundry_row_requires_server_side_model(self):
        for model in ("", "fake-model", "offline-reference-v0"):
            with self.subTest(model=model):
                matrix = self._matrix(review_status="reviewed")
                matrix["cases"][0]["sources"]["releasefoundry_grading"]["model"] = model

                report = build_case_book_report(matrix)

                self.assertEqual(
                    report["maturity_gate"]["reviewed_external_evidence_count"],
                    0,
                )

    def test_reviewed_releasefoundry_row_requires_complete_per_test_receipts(self):
        invalid_receipt_values = {
            "terminal_scoring_verified": False,
            "run_terminal_receipt_sha256": "",
            "run_expected_test_count": 0,
            "run_verified_test_count": 0,
            "run_receipt_complete": False,
            "exact_test_set_verified": False,
            "dataset_identity_verified": False,
            "observed_judge_version": "",
            "aggregate_marker_used_as_acceptance_authority": True,
        }
        for field, invalid_value in invalid_receipt_values.items():
            with self.subTest(field=field):
                matrix = self._matrix(review_status="reviewed")
                metadata = matrix["cases"][0]["sources"]["releasefoundry_grading"]["metadata"]
                metadata[field] = invalid_value

                report = build_case_book_report(matrix)

                self.assertEqual(
                    report["maturity_gate"]["reviewed_external_evidence_count"],
                    0,
                )

    def test_non_boolean_external_availability_cannot_satisfy_c5_evidence_gate(self):
        for available in ("false", "yes", 1):
            with self.subTest(available=available):
                matrix = self._matrix(review_status="reviewed")
                matrix["cases"][0]["sources"]["releasefoundry_grading"]["available"] = available

                report = build_case_book_report(matrix)

                self.assertIs(report["regression_cases"][0]["releasefoundry_grading"]["available"], False)
                self.assertEqual(
                    report["maturity_gate"]["reviewed_external_evidence_count"],
                    0,
                )

    def test_duplicate_regression_source_case_ids_fail_closed(self):
        matrix = self._matrix(review_status="unreviewed")
        matrix["cases"].append(deepcopy(matrix["cases"][0]))

        with self.assertRaisesRegex(ValueError, "duplicate case-book calibration case_id"):
            build_case_book_report(matrix)

    def test_case_book_artifact_hash_binds_report_content(self):
        report = build_case_book_report(self._matrix(review_status="unreviewed"))

        self.assertEqual(verify_case_book_artifact(report), report["artifact_hash"])

        tampered = deepcopy(report)
        tampered["regression_cases"][0]["severity"] = "critical"
        with self.assertRaisesRegex(ValueError, "does not match case-book content"):
            verify_case_book_artifact(tampered)

    def test_incident_promotion_rejects_tampered_case_book(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        case_book["regression_cases"][0]["severity"] = "critical"

        with self.assertRaisesRegex(ValueError, "does not match case-book content"):
            promote_incident_candidates_to_case_book(
                case_book,
                seal_incident_regression_candidate_report({"candidates": []}),
                [],
            )

    def test_incident_promotion_rejects_tampered_candidate_report(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        candidate = {
            "case_id": "incident-case",
            "public_safe": True,
            "ready_for_case_book_review": True,
        }
        incident_report = self._incident_report(candidate)
        review = self._approved_review(incident_report, candidate)
        incident_report["candidates"][0]["severity"] = "critical"

        with self.assertRaisesRegex(ValueError, "does not match report content"):
            promote_incident_candidates_to_case_book(
                case_book,
                incident_report,
                [review],
            )

    def test_incident_promotion_rejects_malformed_candidate_cohort(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        valid_candidate = {
            "case_id": "incident-case",
            "public_safe": True,
            "ready_for_case_book_review": True,
            "fixture_sha256": "sha256:" + ("d" * 64),
        }
        for malformed_candidate in (None, "not-an-object", []):
            with self.subTest(malformed_candidate=malformed_candidate):
                incident_report = seal_incident_regression_candidate_report(
                    {
                        "schema_version": "a2.incident_regression_candidates.v1",
                        "report_id": "unit-test-incident-candidates",
                        "candidates": [valid_candidate, malformed_candidate],
                    }
                )

                with self.assertRaisesRegex(
                    ValueError,
                    r"incident candidate report candidates\[1\] must be an object",
                ):
                    promote_incident_candidates_to_case_book(
                        case_book,
                        incident_report,
                        [],
                    )

    def test_incident_promotion_requires_candidate_list_and_case_ids(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        invalid_cohorts = (
            (
                {"incident-case": {"case_id": "incident-case"}},
                "incident candidate report candidates must be a list",
            ),
            (
                [{}],
                r"incident candidate report candidates\[0\] requires case_id",
            ),
        )
        for candidates, error in invalid_cohorts:
            with self.subTest(candidates=candidates):
                incident_report = seal_incident_regression_candidate_report(
                    {
                        "schema_version": "a2.incident_regression_candidates.v1",
                        "report_id": "unit-test-incident-candidates",
                        "candidates": candidates,
                    }
                )

                with self.assertRaisesRegex(ValueError, error):
                    promote_incident_candidates_to_case_book(
                        case_book,
                        incident_report,
                        [],
                    )

    def test_incident_promotion_rejects_malformed_candidate_fields(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        invalid_fields = (
            ("expected", None, "must be an object"),
            ("local_judge", "malformed", "must be an object"),
            ("releasefoundry_grading", [], "must be an object"),
            ("semantic_or_llm_judge", "malformed", "must be an object"),
            ("calibration_focus", "judge_boundary", "must be a list"),
            ("disagreement_pairs", {"status": "mismatch"}, "must be a list"),
            ("evidence_refs", "fixtures/a2/result.json", "must be a list"),
        )
        for field, value, error in invalid_fields:
            with self.subTest(field=field):
                candidate = {"case_id": "incident-case", field: value}
                incident_report = self._incident_report(candidate)

                with self.assertRaisesRegex(
                    ValueError,
                    rf"candidates\[0\]\.{field} {error}",
                ):
                    promote_incident_candidates_to_case_book(
                        case_book,
                        incident_report,
                        [],
                    )

    def test_incident_promotion_rejects_malformed_candidate_list_rows(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        invalid_rows = (
            (
                "calibration_focus",
                ["judge_boundary", ""],
                r"calibration_focus\[1\] must be a non-empty string",
            ),
            (
                "calibration_focus",
                ["judge_boundary", 7],
                r"calibration_focus\[1\] must be a non-empty string",
            ),
            (
                "evidence_refs",
                ["fixtures/a2/result.json", ""],
                r"evidence_refs\[1\] must be a non-empty string",
            ),
            (
                "evidence_refs",
                ["fixtures/a2/result.json", 7],
                r"evidence_refs\[1\] must be a non-empty string",
            ),
            (
                "disagreement_pairs",
                [{"status": "mismatch"}, "malformed"],
                r"disagreement_pairs\[1\] must be an object",
            ),
        )
        for field, value, error in invalid_rows:
            with self.subTest(field=field):
                candidate = {"case_id": "incident-case", field: value}
                incident_report = self._incident_report(candidate)

                with self.assertRaisesRegex(
                    ValueError,
                    rf"candidates\[0\]\.{error}",
                ):
                    promote_incident_candidates_to_case_book(
                        case_book,
                        incident_report,
                        [],
                    )

    def test_incident_promotion_rejects_review_not_bound_to_current_candidate(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        candidate = {
            "case_id": "incident-case",
            "public_safe": True,
            "ready_for_case_book_review": True,
        }
        incident_report = self._incident_report(candidate)

        invalid_bindings = (
            (
                "source_incident_candidates_hash",
                "sha256:" + ("b" * 64),
                "does not bind the current incident candidate report",
            ),
            (
                "candidate_hash",
                "sha256:" + ("c" * 64),
                "does not bind the current candidate content",
            ),
        )
        for field, value, error in invalid_bindings:
            with self.subTest(field=field):
                review = self._approved_review(incident_report, candidate)
                review[field] = value

                with self.assertRaisesRegex(ValueError, error):
                    promote_incident_candidates_to_case_book(
                        case_book,
                        incident_report,
                        [review],
                    )

    def test_incident_promotion_preserves_reviewed_fixture_content_hash(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        incident_report = build_incident_regression_candidate_report(
            ROOT / "fixtures/a2/incidents/a2_prod_incident_summary.json",
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        candidate = incident_report["candidates"][0]

        promoted = promote_incident_candidates_to_case_book(
            case_book,
            incident_report,
            [self._approved_review(incident_report, candidate)],
        )

        promoted_case = next(
            regression
            for regression in promoted["regression_cases"]
            if regression["case_id"] == candidate["case_id"]
        )
        self.assertEqual(
            promoted_case["fixture_sha256"],
            candidate["fixture_sha256"],
        )

    def test_incident_promotion_rejects_candidate_without_canonical_fixture_hash(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        invalid_hashes = (None, "", "not-a-hash", "sha256:" + ("A" * 64))
        for invalid_hash in invalid_hashes:
            with self.subTest(invalid_hash=invalid_hash):
                candidate = {
                    "case_id": "incident-case",
                    "public_safe": True,
                    "ready_for_case_book_review": True,
                }
                if invalid_hash is not None:
                    candidate["fixture_sha256"] = invalid_hash
                incident_report = self._incident_report(candidate)

                promoted = promote_incident_candidates_to_case_book(
                    case_book,
                    incident_report,
                    [self._approved_review(incident_report, candidate)],
                )

                self.assertEqual(promoted["regression_case_count"], 1)
                audit = promoted["metadata"]["promotion_audit"][0]
                self.assertEqual(audit["outcome"], "blocked")
                self.assertIn(
                    "candidate_not_public_safe_or_content_bound",
                    audit["blockers"],
                )

    def test_non_boolean_incident_safety_flags_cannot_be_promoted(self):
        case_book = build_case_book_report(self._matrix(review_status="unreviewed"))
        for field in ("public_safe", "ready_for_case_book_review"):
            for value in ("false", 1, {}, []):
                with self.subTest(field=field, value=value):
                    candidate = {
                        "case_id": "incident-case",
                        "public_safe": True,
                        "ready_for_case_book_review": True,
                    }
                    candidate[field] = value
                    incident_report = self._incident_report(candidate)

                    promoted = promote_incident_candidates_to_case_book(
                        case_book,
                        incident_report,
                        [self._approved_review(incident_report, candidate)],
                    )

                    self.assertEqual(promoted["regression_case_count"], 1)
                    self.assertEqual(
                        promoted["metadata"]["promotion_audit"][0]["outcome"],
                        "blocked",
                    )
                    self.assertEqual(
                        verify_case_book_artifact(promoted),
                        promoted["artifact_hash"],
                    )

    def test_incident_report_does_not_count_non_boolean_ready_flags(self):
        candidate = {
            "case_id": "incident-case",
            "public_safe": "false",
            "ready_for_case_book_review": True,
        }
        with patch(
            "services.judge.incident_regression._candidate_from_incident",
            return_value=candidate,
        ):
            report = build_incident_regression_candidate_report(
                ROOT / "fixtures/a2/incidents/a2_prod_incident_summary.json",
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["ready_candidate_count"], 0)
        self.assertFalse(report["ready_for_case_book_review"])

    @staticmethod
    def _incident_report(candidate: dict) -> dict:
        return seal_incident_regression_candidate_report(
            {
                "schema_version": "a2.incident_regression_candidates.v1",
                "report_id": "unit-test-incident-candidates",
                "candidates": [candidate],
            }
        )

    @staticmethod
    def _approved_review(incident_report: dict, candidate: dict) -> dict:
        return {
            "case_id": str(candidate["case_id"]),
            "decision": "approved",
            "reviewer_receipt": "sha256:" + ("a" * 64),
            "reviewed_at_unix_ms": 1784700000000,
            "source_incident_candidates_hash": incident_report["artifact_hash"],
            "candidate_hash": stable_hash(candidate),
            "evidence_refs": [],
        }

    @staticmethod
    def _matrix(*, review_status: str) -> dict:
        public_receipt = _public_terminal_receipt()
        terminal_metadata = _verified_terminal_scoring_metadata(public_receipt)
        matrix = {
            "matrix_id": "unit-test-matrix",
            "dataset_id": "unit-test-dataset",
            "case_count": 1,
            "releasefoundry_run_terminal_receipt": public_receipt,
            "agreement_summary": {
                "local_vs_llm_judge": {
                    "comparable": 1,
                    "mismatch_count": 1,
                }
            },
            "source_coverage": {"releasefoundry_grading": {"missing": 0}},
            "cases": [
                {
                    "case_id": CASE_ID,
                    "scenario_id": "A2-UNIT",
                    "fixture_ref": "fixtures/a2/runs/unit-test.json",
                    "calibration_focus": ["judge_boundary"],
                    "expected": {"passed": False, "primary_failure_class": "wrong_arguments"},
                    "calibration_tags": ["judge_disagreement_regression"],
                    "sources": {
                        "local_judge": {
                            "available": True,
                            "status": "available",
                            "source": "local_judge",
                            "provider": "local",
                            "passed": False,
                            "primary_failure_class": "wrong_arguments",
                            "score": 70,
                            "confidence": 1.0,
                            "rationale": "unit test",
                            "evidence_ref": "fixtures/a2/results/local.json",
                        },
                        "releasefoundry_grading": {
                            "available": True,
                            "status": "available",
                            "source": "releasefoundry_grading",
                            "provider": "releasefoundry server-side grading",
                            "model": "releasefoundry-server-side",
                            "passed": False,
                            "primary_failure_class": "wrong_arguments",
                            "score": 68,
                            "confidence": 0.9,
                            "rationale": "unit test",
                            "evidence_ref": "docs/evidence/private_refs/releasefoundry.json",
                            "metadata": {
                                **terminal_metadata,
                                "review_status": review_status,
                                "reviewer_receipt": "sha256:" + ("a" * 64),
                                "reviewed_at_unix_ms": 1784700000000,
                            },
                        },
                        "llm_judge": {
                            "available": True,
                            "status": "available",
                            "source": "llm_judge",
                            "provider": "offline_reference",
                            "passed": True,
                            "primary_failure_class": "none",
                            "score": 90,
                            "confidence": 0.8,
                            "rationale": "unit test",
                            "evidence_ref": "fixtures/a2/runs/unit-test.json",
                        },
                    },
                    "diffs": [
                        {
                            "left": "local_judge",
                            "right": "llm_judge",
                            "status": "mismatch",
                        }
                    ],
                }
            ],
        }
        return matrix


if __name__ == "__main__":
    unittest.main()
