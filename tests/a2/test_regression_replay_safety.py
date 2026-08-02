import copy
import json
import unittest
from pathlib import Path

from services.judge.casebook import build_case_book_receipt_bindings
from services.judge.regression_replay import (
    build_regression_replay_report,
    verify_regression_replay_artifact,
)
from services.judge.result_persistence import stable_hash


ROOT = Path(__file__).resolve().parents[2]


class RegressionReplaySafetyTests(unittest.TestCase):
    def test_replay_calibration_cases_must_be_a_list(self):
        calibration_matrix, case_book = self._fixture_reports()
        calibration_matrix["cases"] = {"case": calibration_matrix["cases"][0]}

        with self.assertRaisesRegex(
            ValueError,
            "regression replay calibration cases must be a list",
        ):
            build_regression_replay_report(
                calibration_matrix,
                case_book,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_replay_rejects_malformed_calibration_case_rows(self):
        invalid_rows = (
            (
                None,
                r"regression replay calibration cases\[1\] must be an object",
            ),
            (
                {},
                r"regression replay calibration cases\[1\] requires case_id",
            ),
        )
        for invalid_row, error in invalid_rows:
            with self.subTest(invalid_row=invalid_row):
                calibration_matrix, case_book = self._fixture_reports()
                calibration_matrix["cases"].insert(1, invalid_row)

                with self.assertRaisesRegex(ValueError, error):
                    build_regression_replay_report(
                        calibration_matrix,
                        case_book,
                        pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    )

    def test_replay_rejects_duplicate_calibration_case_ids(self):
        calibration_matrix, case_book = self._fixture_reports()
        calibration_matrix["cases"].append(
            copy.deepcopy(calibration_matrix["cases"][0])
        )

        with self.assertRaisesRegex(
            ValueError,
            "duplicate regression replay calibration case_id",
        ):
            build_regression_replay_report(
                calibration_matrix,
                case_book,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_case_book_maturity_ready_requires_a_boolean(self):
        for value in ("false", 1, None, {}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "ready must be a boolean"):
                    self._build_report({"ready": value})

    def test_case_book_maturity_counts_require_non_negative_integers(self):
        for field in (
            "reviewed_external_evidence_count",
            "reviewed_evidence_target_count",
        ):
            for value in (True, "3", 3.0, -1, None):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, f"{field} must be a non-negative integer"):
                        self._build_report({field: value})

    def test_case_book_maturity_cannot_overstate_reviewed_evidence(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed the replay case count"):
            self._build_report({"reviewed_external_evidence_count": 1})

    def test_case_book_maturity_cannot_lower_the_reviewed_evidence_target(self):
        with self.assertRaisesRegex(ValueError, "must be at least 3"):
            self._build_report({"reviewed_evidence_target_count": 0})

    def test_case_book_ready_must_match_case_and_evidence_counts(self):
        with self.assertRaisesRegex(ValueError, "ready is inconsistent"):
            self._build_report({"ready": True})

    def test_public_case_book_summary_cannot_fabricate_reviewed_evidence(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        seed = candidate["regression_cases"][0]
        candidate["regression_cases"] = []
        for index in range(3):
            regression = copy.deepcopy(seed)
            regression["case_id"] = f"fabricated-reviewed-case-{index}"
            regression["regression_id"] = f"regression-fabricated-reviewed-case-{index}"
            regression["promotion"] = {
                "source": "incident_candidate",
                "decision": "approved",
                "replay_input_approved": True,
            }
            candidate["regression_cases"].append(regression)
        candidate["regression_case_count"] = 3
        candidate["maturity_gate"] = {
            "ready": True,
            "reviewed_external_evidence_count": 3,
            "reviewed_evidence_target_count": 3,
        }
        self._reseal_case_book(candidate)

        with self.assertRaisesRegex(
            ValueError,
            "does not match reviewed evidence recomputed from regression_cases",
        ):
            build_regression_replay_report(
                calibration_matrix,
                candidate,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_case_book_declared_case_count_must_match_regression_cases(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        candidate["regression_case_count"] += 1

        with self.assertRaisesRegex(
            ValueError,
            "regression_case_count does not match the number of regression_cases",
        ):
            build_regression_replay_report(
                calibration_matrix,
                candidate,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_case_book_declared_case_count_requires_non_negative_integer(self):
        calibration_matrix, case_book = self._fixture_reports()
        for value in (True, "1", 1.0, -1, None):
            with self.subTest(value=value):
                candidate = copy.deepcopy(case_book)
                candidate["regression_case_count"] = value

                with self.assertRaisesRegex(
                    ValueError,
                    "regression_case_count must be a non-negative integer",
                ):
                    build_regression_replay_report(
                        calibration_matrix,
                        candidate,
                        pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    )

    def test_replay_rejects_tampered_case_book_content(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        candidate["regression_cases"][0]["severity"] = "critical"

        with self.assertRaisesRegex(
            ValueError,
            "artifact_hash does not match case-book content",
        ):
            build_regression_replay_report(
                calibration_matrix,
                candidate,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_replay_rejects_resealed_matrix_derived_judge_changes(self):
        calibration_matrix, case_book = self._fixture_reports()
        mutations = (
            ("local_judge", "primary_failure_class", "forged_failure_class"),
            (
                "semantic_or_llm_judge",
                "primary_failure_class",
                "forged_semantic_failure_class",
            ),
        )

        for source, field, value in mutations:
            with self.subTest(source=source, field=field):
                candidate = copy.deepcopy(case_book)
                candidate["regression_cases"][0][source][field] = value
                self._reseal_case_book(candidate)

                with self.assertRaisesRegex(
                    ValueError,
                    "matrix-derived judge evidence does not match",
                ):
                    build_regression_replay_report(
                        calibration_matrix,
                        candidate,
                        pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    )

    def test_replay_rejects_changed_matrix_with_same_ids(self):
        calibration_matrix, case_book = self._fixture_reports()
        changed_matrix = copy.deepcopy(calibration_matrix)
        changed_matrix["cases"][0]["expected"]["passed"] = not changed_matrix["cases"][0]["expected"]["passed"]

        with self.assertRaisesRegex(
            ValueError,
            "source_matrix_hash does not match calibration matrix",
        ):
            build_regression_replay_report(
                changed_matrix,
                case_book,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_replay_rejects_case_book_source_matrix_mismatch(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        candidate["source_matrix"] = "different-matrix"
        self._reseal_case_book(candidate)

        with self.assertRaisesRegex(
            ValueError,
            "source_matrix does not match calibration matrix",
        ):
            build_regression_replay_report(
                calibration_matrix,
                candidate,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_replay_rejects_case_book_dataset_id_mismatch(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        candidate["dataset_id"] = "different-dataset"
        self._reseal_case_book(candidate)

        with self.assertRaisesRegex(
            ValueError,
            "dataset_id does not match calibration matrix",
        ):
            build_regression_replay_report(
                calibration_matrix,
                candidate,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_replay_rejects_resealed_receipt_binding_mismatch(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        candidate["external_evidence_receipt_bindings"]["releasefoundry_grading"][
            "valid"
        ] = True
        self._reseal_case_book(candidate)

        with self.assertRaisesRegex(
            ValueError,
            "external evidence receipt bindings do not match",
        ):
            build_regression_replay_report(
                calibration_matrix,
                candidate,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_replay_artifact_hash_binds_report_content(self):
        calibration_matrix, case_book = self._fixture_reports()

        report = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        core = {
            key: value
            for key, value in report.items()
            if key != "artifact_hash"
        }
        self.assertEqual(report["artifact_hash"], stable_hash(core))

    def test_replay_source_verification_accepts_freshly_rebuilt_report(self):
        calibration_matrix, case_book = self._fixture_reports()
        report = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        verified_hash = verify_regression_replay_artifact(
            report,
            calibration_matrix=calibration_matrix,
            case_book_report=case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        self.assertEqual(verified_hash, report["artifact_hash"])

    def test_replay_source_verification_rejects_resealed_authority_fields(self):
        calibration_matrix, case_book = self._fixture_reports()
        report = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        mutations = (
            ("replay_ready", not report["replay_ready"]),
            ("maturity_status", "mature"),
            ("passed_count", report["passed_count"] + 1),
            ("failed_count", report["failed_count"] + 1),
            ("replay_case_count", report["replay_case_count"] + 1),
        )

        for field, value in mutations:
            with self.subTest(field=field):
                candidate = copy.deepcopy(report)
                candidate[field] = value
                self._reseal_replay(candidate)

                with self.assertRaisesRegex(
                    ValueError,
                    "does not match replay rebuilt from calibration matrix and case book",
                ):
                    verify_regression_replay_artifact(
                        candidate,
                        calibration_matrix=calibration_matrix,
                        case_book_report=case_book,
                        pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    )

    def test_replay_source_verification_rejects_resealed_case_set_changes(self):
        calibration_matrix, case_book = self._fixture_reports()
        report = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        candidates = []

        missing = copy.deepcopy(report)
        missing["cases"] = []
        candidates.append(missing)

        duplicate = copy.deepcopy(report)
        duplicate["cases"].append(copy.deepcopy(duplicate["cases"][0]))
        candidates.append(duplicate)

        changed_id = copy.deepcopy(report)
        changed_id["cases"][0]["case_id"] = "different-case"
        candidates.append(changed_id)

        for candidate in candidates:
            self._reseal_replay(candidate)
            with self.subTest(case_count=len(candidate["cases"])):
                with self.assertRaisesRegex(
                    ValueError,
                    "does not match replay rebuilt from calibration matrix and case book",
                ):
                    verify_regression_replay_artifact(
                        candidate,
                        calibration_matrix=calibration_matrix,
                        case_book_report=case_book,
                        pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                    )

    def test_replay_source_verification_rejects_different_current_case_book(self):
        calibration_matrix, case_book = self._fixture_reports()
        report = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        changed_case_book = copy.deepcopy(case_book)
        changed_case_book["case_book_id"] = "different-case-book"
        self._reseal_case_book(changed_case_book)

        with self.assertRaisesRegex(
            ValueError,
            "does not match replay rebuilt from calibration matrix and case book",
        ):
            verify_regression_replay_artifact(
                report,
                calibration_matrix=calibration_matrix,
                case_book_report=changed_case_book,
                pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
            )

    def test_replay_source_verification_requires_both_current_sources(self):
        calibration_matrix, case_book = self._fixture_reports()
        report = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        for kwargs in (
            {"calibration_matrix": calibration_matrix},
            {"case_book_report": case_book},
        ):
            with self.subTest(kwargs=tuple(kwargs)):
                with self.assertRaisesRegex(
                    ValueError,
                    "requires both calibration_matrix and case_book_report",
                ):
                    verify_regression_replay_artifact(report, **kwargs)

    def test_replay_rejects_forged_or_incomplete_promotion_provenance(self):
        calibration_matrix, case_book = self._fixture_reports()
        valid_promotion = {
            "source": "incident_candidate",
            "decision": "approved",
            "replay_input_approved": True,
            "reviewer_receipt": "sha256:" + ("a" * 64),
            "reviewed_at_unix_ms": 1784700000000,
            "source_incident_candidates_hash": "sha256:" + ("b" * 64),
            "candidate_hash": "sha256:" + ("c" * 64),
        }
        invalid_updates = (
            {"reviewer_receipt": "not-a-canonical-receipt"},
            {"reviewer_receipt": None},
            {"reviewed_at_unix_ms": None},
            {"reviewed_at_unix_ms": True},
            {"reviewed_at_unix_ms": 0},
            {"source_incident_candidates_hash": None},
            {"source_incident_candidates_hash": "not-a-hash"},
            {"candidate_hash": None},
            {"candidate_hash": "not-a-hash"},
        )

        for update in invalid_updates:
            with self.subTest(update=update):
                candidate = copy.deepcopy(case_book)
                candidate["regression_cases"][0]["fixture_sha256"] = (
                    self._fixture_sha256(
                        candidate["regression_cases"][0]["fixture_ref"]
                    )
                )
                promotion = dict(valid_promotion)
                promotion.update(update)
                candidate["regression_cases"][0]["promotion"] = promotion
                self._reseal_case_book(candidate)

                report = build_regression_replay_report(
                    calibration_matrix,
                    candidate,
                    pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                )

                replay = report["cases"][0]
                self.assertFalse(replay["checks"]["approved_promotion_visible"])
                self.assertEqual(replay["replay_status"], "failed")
                self.assertFalse(report["replay_ready"])

    def test_replay_accepts_canonical_promotion_provenance(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        candidate["regression_cases"][0]["fixture_sha256"] = self._fixture_sha256(
            candidate["regression_cases"][0]["fixture_ref"]
        )
        candidate["regression_cases"][0]["promotion"] = {
            "source": "incident_candidate",
            "decision": "approved",
            "replay_input_approved": True,
            "reviewer_receipt": "sha256:" + ("a" * 64),
            "reviewed_at_unix_ms": 1784700000000,
            "source_incident_candidates_hash": "sha256:" + ("b" * 64),
            "candidate_hash": "sha256:" + ("c" * 64),
        }
        self._reseal_case_book(candidate)

        report = build_regression_replay_report(
            calibration_matrix,
            candidate,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        replay = report["cases"][0]
        self.assertTrue(replay["checks"]["approved_promotion_visible"])
        self.assertTrue(replay["checks"]["fixture_content_hash_preserved"])
        self.assertEqual(replay["replay_status"], "passed")

    def test_replay_rejects_promoted_case_when_fixture_content_changed(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        regression = candidate["regression_cases"][0]
        regression["fixture_sha256"] = stable_hash({"stale": "reviewed fixture"})
        regression["promotion"] = {
            "source": "incident_candidate",
            "decision": "approved",
            "replay_input_approved": True,
            "reviewer_receipt": "sha256:" + ("a" * 64),
            "reviewed_at_unix_ms": 1784700000000,
            "source_incident_candidates_hash": "sha256:" + ("b" * 64),
            "candidate_hash": "sha256:" + ("c" * 64),
        }
        self._reseal_case_book(candidate)

        report = build_regression_replay_report(
            calibration_matrix,
            candidate,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        replay = report["cases"][0]
        self.assertTrue(replay["checks"]["fixture_replayed"])
        self.assertTrue(replay["checks"]["fixture_content_hash_present"])
        self.assertFalse(replay["checks"]["fixture_content_hash_preserved"])
        self.assertEqual(replay["replay_status"], "failed")
        self.assertFalse(report["replay_ready"])

    def test_replay_rejects_promoted_case_without_canonical_fixture_hash(self):
        calibration_matrix, case_book = self._fixture_reports()
        invalid_hashes = (None, "", "not-a-hash", "sha256:" + ("A" * 64))
        for invalid_hash in invalid_hashes:
            with self.subTest(invalid_hash=invalid_hash):
                candidate = copy.deepcopy(case_book)
                regression = candidate["regression_cases"][0]
                if invalid_hash is not None:
                    regression["fixture_sha256"] = invalid_hash
                regression["promotion"] = {
                    "source": "incident_candidate",
                    "decision": "approved",
                    "replay_input_approved": True,
                    "reviewer_receipt": "sha256:" + ("a" * 64),
                    "reviewed_at_unix_ms": 1784700000000,
                    "source_incident_candidates_hash": "sha256:" + ("b" * 64),
                    "candidate_hash": "sha256:" + ("c" * 64),
                }
                self._reseal_case_book(candidate)

                report = build_regression_replay_report(
                    calibration_matrix,
                    candidate,
                    pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                )

                replay = report["cases"][0]
                self.assertFalse(replay["checks"]["fixture_content_hash_present"])
                self.assertFalse(replay["checks"]["fixture_content_hash_preserved"])
                self.assertEqual(replay["replay_status"], "failed")

    def test_regression_assertion_requires_non_empty_text(self):
        calibration_matrix, case_book = self._fixture_reports()
        for value in (True, 1, {}, [], "   "):
            with self.subTest(value=value):
                candidate = copy.deepcopy(case_book)
                candidate["regression_cases"][0]["regression_assertion"] = value
                self._reseal_case_book(candidate)

                report = build_regression_replay_report(
                    calibration_matrix,
                    candidate,
                    pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
                )

                replay = report["cases"][0]
                self.assertFalse(replay["checks"]["regression_assertion_present"])
                self.assertEqual(replay["replay_status"], "failed")

    def test_failed_replay_does_not_accept_truthy_non_text_assertion(self):
        calibration_matrix, case_book = self._fixture_reports()
        candidate = copy.deepcopy(case_book)
        regression = candidate["regression_cases"][0]
        regression["fixture_ref"] = "missing-regression-fixture.json"
        regression["regression_assertion"] = True
        self._reseal_case_book(candidate)

        report = build_regression_replay_report(
            calibration_matrix,
            candidate,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        replay = report["cases"][0]
        self.assertFalse(replay["checks"]["regression_assertion_present"])
        self.assertEqual(replay["replay_status"], "failed")

    def test_replay_accepts_existing_public_run_fixture(self):
        calibration_matrix, case_book = self._fixture_reports()

        report = build_regression_replay_report(
            calibration_matrix,
            case_book,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )

        replay = report["cases"][0]
        self.assertEqual(
            replay["fixture_ref"],
            "fixtures/a2/runs/a2_s010_wrong_arguments.json",
        )
        self.assertTrue(replay["checks"]["fixture_replayed"])
        self.assertEqual(replay["replay_status"], "passed")

    def test_replay_rejects_absolute_fixture_ref_without_leaking_it(self):
        absolute_ref = str(
            (ROOT / "fixtures/a2/runs/a2_s010_wrong_arguments.json").resolve()
        )

        replay = self._replay_with_fixture_ref(absolute_ref)

        self.assertEqual(replay["replay_status"], "failed")
        self.assertEqual(replay["fixture_ref"], "")
        serialized = json.dumps(replay)
        self.assertNotIn(absolute_ref, serialized)
        self.assertNotIn(str(ROOT.resolve()), serialized)

    def test_replay_rejects_parent_traversal_fixture_ref(self):
        fixture_ref = "fixtures/a2/runs/../results/a2_case_book.json"

        replay = self._replay_with_fixture_ref(fixture_ref)

        self.assertEqual(replay["replay_status"], "failed")
        self.assertEqual(replay["fixture_ref"], "")
        self.assertNotIn(fixture_ref, json.dumps(replay))
        self.assertIn("parent traversal", replay["error"]["message"])

    def test_replay_rejects_private_evidence_as_a_fixture(self):
        fixture_ref = "docs/evidence/private_refs/a2_private_receipt.json"

        replay = self._replay_with_fixture_ref(fixture_ref)

        self.assertEqual(replay["replay_status"], "failed")
        self.assertEqual(replay["fixture_ref"], "")
        self.assertNotIn(fixture_ref, json.dumps(replay))
        self.assertIn("fixtures/a2/runs", replay["error"]["message"])

    def test_replay_rejects_non_json_fixture_ref(self):
        fixture_ref = "fixtures/a2/runs/a2_s010_wrong_arguments.txt"

        replay = self._replay_with_fixture_ref(fixture_ref)

        self.assertEqual(replay["replay_status"], "failed")
        self.assertEqual(replay["fixture_ref"], "")
        self.assertNotIn(fixture_ref, json.dumps(replay))
        self.assertIn("JSON file", replay["error"]["message"])

    @classmethod
    def _replay_with_fixture_ref(cls, fixture_ref):
        calibration_matrix, case_book = cls._fixture_reports()
        candidate = copy.deepcopy(case_book)
        candidate["regression_cases"][0]["fixture_ref"] = fixture_ref
        cls._reseal_case_book(candidate)

        report = build_regression_replay_report(
            calibration_matrix,
            candidate,
            pack_path=ROOT / "packages/scenarios/a2_g3_full_pack.json",
        )
        return report["cases"][0]

    @staticmethod
    def _build_report(maturity_gate):
        calibration_matrix = {
            "matrix_id": "test-matrix",
            "dataset_id": "test-dataset",
            "cases": [],
        }
        case_book = {
            "case_book_id": "test-case-book",
            "source_matrix": "test-matrix",
            "source_matrix_hash": stable_hash(calibration_matrix),
            "dataset_id": "test-dataset",
            "regression_case_count": 0,
            "external_evidence_receipt_bindings": (
                build_case_book_receipt_bindings(calibration_matrix)
            ),
            "maturity_gate": maturity_gate,
            "regression_cases": [],
        }
        RegressionReplaySafetyTests._reseal_case_book(case_book)
        return build_regression_replay_report(
            calibration_matrix,
            case_book,
        )

    @staticmethod
    def _reseal_case_book(case_book):
        core = {
            key: value
            for key, value in case_book.items()
            if key != "artifact_hash"
        }
        case_book["artifact_hash"] = stable_hash(core)

    @staticmethod
    def _reseal_replay(report):
        core = {
            key: value
            for key, value in report.items()
            if key != "artifact_hash"
        }
        report["artifact_hash"] = stable_hash(core)

    @staticmethod
    def _fixture_sha256(fixture_ref):
        fixture = json.loads((ROOT / fixture_ref).read_text(encoding="utf-8"))
        return stable_hash(fixture)

    @staticmethod
    def _fixture_reports():
        calibration_matrix = json.loads(
            (ROOT / "fixtures/a2/results/a2_g3_calibration_matrix.json").read_text(encoding="utf-8")
        )
        case_book = json.loads(
            (ROOT / "fixtures/a2/results/a2_case_book.json").read_text(encoding="utf-8")
        )
        case_book["source_matrix_hash"] = stable_hash(calibration_matrix)
        case_book["external_evidence_receipt_bindings"] = (
            build_case_book_receipt_bindings(calibration_matrix)
        )
        RegressionReplaySafetyTests._reseal_case_book(case_book)
        return calibration_matrix, case_book


if __name__ == "__main__":
    unittest.main()
