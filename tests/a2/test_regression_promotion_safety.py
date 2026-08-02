import copy
import json
import unittest
from pathlib import Path

from services.judge.regression_promotion import (
    build_regression_promotion_queue_report,
)
from services.judge.result_persistence import stable_hash


ROOT = Path(__file__).resolve().parents[2]


class RegressionPromotionSafetyTests(unittest.TestCase):
    def test_non_boolean_candidate_safety_flags_cannot_enter_owner_review(self):
        for field in ("public_safe", "ready_for_case_book_review"):
            for value in ("false", 1, {}, [], None):
                with self.subTest(field=field, value=value):
                    case_book, incident_candidates, replay = self._reports()
                    incident_candidates["candidates"][0][field] = value
                    self._reseal(incident_candidates)

                    report = build_regression_promotion_queue_report(
                        case_book,
                        incident_candidates,
                        replay,
                    )

                    item = report["promotion_items"][0]
                    self.assertEqual(item["queue_status"], "blocked_before_review")
                    self.assertFalse(item["can_promote_to_case_book"])
                    self.assertEqual(report["ready_for_owner_review_count"], 0)

    def test_replay_counts_require_non_negative_integers(self):
        for field in (
            "current_replay_case_count",
            "target_replay_case_count",
        ):
            for value in (True, "3", 3.0, -1, None):
                with self.subTest(field=field, value=value):
                    case_book, incident_candidates, replay = self._reports()
                    replay["maturity_gate"][field] = value
                    self._reseal(replay)

                    with self.assertRaisesRegex(
                        ValueError,
                        f"{field} must be a non-negative integer",
                    ):
                        build_regression_promotion_queue_report(
                            case_book,
                            incident_candidates,
                            replay,
                        )

    def test_replay_target_cannot_be_lowered(self):
        case_book, incident_candidates, replay = self._reports()
        replay["maturity_gate"]["target_replay_case_count"] = 0
        self._reseal(replay)

        with self.assertRaisesRegex(ValueError, "must be at least 3"):
            build_regression_promotion_queue_report(
                case_book,
                incident_candidates,
                replay,
            )

    def test_release_blocker_requires_a_boolean(self):
        for value in ("false", 0, 1, None, {}):
            with self.subTest(value=value):
                case_book, incident_candidates, replay = self._reports()
                replay["release_gate_summary"]["blocks_release"] = value
                self._reseal(replay)

                with self.assertRaisesRegex(
                    ValueError,
                    "blocks_release must be a boolean",
                ):
                    build_regression_promotion_queue_report(
                        case_book,
                        incident_candidates,
                        replay,
                    )

    def test_candidate_collections_must_be_lists_of_objects(self):
        cases = (
            ("case_book_report", "regression_cases"),
            ("incident_candidates_report", "candidates"),
            ("regression_replay_report", "cases"),
        )
        for report_name, field in cases:
            for value in ("invalid", {}, [None]):
                with self.subTest(report=report_name, field=field, value=value):
                    case_book, incident_candidates, replay = self._reports()
                    report = {
                        "case_book_report": case_book,
                        "incident_candidates_report": incident_candidates,
                        "regression_replay_report": replay,
                    }[report_name]
                    report[field] = value

                    with self.assertRaisesRegex(TypeError, "must be a list|entries must be objects"):
                        build_regression_promotion_queue_report(
                            case_book,
                            incident_candidates,
                            replay,
                        )

    def test_candidate_requires_a_non_empty_case_id(self):
        case_book, incident_candidates, replay = self._reports()
        incident_candidates["candidates"][0]["case_id"] = " "
        self._reseal(incident_candidates)

        with self.assertRaisesRegex(ValueError, "candidate.case_id must be a non-empty string"):
            build_regression_promotion_queue_report(
                case_book,
                incident_candidates,
                replay,
            )

    def test_queue_rejects_tampered_source_artifacts(self):
        for source_name in ("case_book", "incident_candidates", "replay"):
            with self.subTest(source=source_name):
                case_book, incident_candidates, replay = self._reports()
                source = {
                    "case_book": case_book,
                    "incident_candidates": incident_candidates,
                    "replay": replay,
                }[source_name]
                source["metadata"]["tampered"] = True

                with self.assertRaisesRegex(
                    ValueError,
                    "artifact_hash does not match",
                ):
                    build_regression_promotion_queue_report(
                        case_book,
                        incident_candidates,
                        replay,
                    )

    def test_queue_binds_each_candidate_and_all_source_artifacts(self):
        case_book, incident_candidates, replay = self._reports()

        report = build_regression_promotion_queue_report(
            case_book,
            incident_candidates,
            replay,
        )

        self.assertEqual(
            report["source_case_book_hash"],
            case_book["artifact_hash"],
        )
        self.assertEqual(
            report["source_incident_candidates_hash"],
            incident_candidates["artifact_hash"],
        )
        self.assertEqual(
            report["source_regression_replay_hash"],
            replay["artifact_hash"],
        )
        self.assertEqual(
            report["promotion_items"][0]["candidate_hash"],
            stable_hash(incident_candidates["candidates"][0]),
        )
        core = {
            key: value
            for key, value in report.items()
            if key != "artifact_hash"
        }
        self.assertEqual(report["artifact_hash"], stable_hash(core))

    @staticmethod
    def _reports():
        case_book = json.loads(
            (ROOT / "fixtures/a2/results/a2_case_book.json").read_text(
                encoding="utf-8"
            )
        )
        incident_candidates = json.loads(
            (
                ROOT
                / "fixtures/a2/results/a2_incident_regression_candidates.json"
            ).read_text(encoding="utf-8")
        )
        replay = json.loads(
            (
                ROOT / "fixtures/a2/results/a2_regression_replay_report.json"
            ).read_text(encoding="utf-8")
        )
        return (
            copy.deepcopy(case_book),
            copy.deepcopy(incident_candidates),
            copy.deepcopy(replay),
        )

    @staticmethod
    def _reseal(report):
        core = {
            key: value
            for key, value in report.items()
            if key != "artifact_hash"
        }
        report["artifact_hash"] = stable_hash(core)


if __name__ == "__main__":
    unittest.main()
