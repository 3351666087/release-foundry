from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue


class ReleaseFoundryDisagreementReviewQueueTests(unittest.TestCase):
    def _inputs(self):
        matrix = calibration.build_matrix()
        local_fail = next(item for item in matrix if item["expected_passed"] is False)
        local_pass = next(item for item in matrix if item["expected_passed"] is True)
        tests = [
            {
                "test_id": local_fail["variant_id"],
                "status": "completed",
                "failed_actions": [],
                "action_results": [
                    {
                        "actor": "agent",
                        "action_type": "text",
                        "semantic_similarity": 0.95,
                        "llm_judgment": {"verdict": "match"},
                    }
                ],
            },
            {
                "test_id": local_pass["variant_id"],
                "status": "completed",
                "failed_actions": [],
                "action_results": [
                    {
                        "actor": "agent",
                        "action_type": "text",
                        "semantic_similarity": 0.95,
                        "llm_judgment": {"verdict": "match"},
                    }
                ],
            },
        ]
        journal = {
            "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
            "preflight_status": "verified_for_exploration_only",
            "dataset_binding": {
                "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
                "acceptance_authority": False,
                "training_eligible": False,
                "release_authority": False,
                "c3_transition_allowed": False,
            },
            "batches": [
                {
                    "status": "completed",
                    "variant_ids": [
                        local_fail["variant_id"],
                        local_pass["variant_id"],
                    ],
                    "http_events": [
                        {
                            "operation": "create_run",
                            "status": "ok",
                            "retry": False,
                            "duration_ms": 1,
                        }
                    ],
                    "terminal_response": {
                        "result": {
                            "status": "completed",
                            "aggregate_metrics": {
                                "action_summary": {"passed": 2, "failed": 0}
                            },
                            "tests": tests,
                        }
                    },
                }
            ],
        }
        receipt = calibration.build_public_summary(journal, matrix)
        return matrix, journal, receipt, local_fail

    def test_builds_only_redacted_pending_disagreements(self):
        matrix, journal, receipt, local_fail = self._inputs()

        with mock.patch.object(
            calibration,
            "_now",
            return_value="2026-07-27T15:00:00Z",
        ):
            queue = review_queue.build_review_queue(journal, receipt, matrix)

        self.assertEqual(queue["review_item_count"], 1)
        self.assertEqual(queue["review_status"], "pending_human_review")
        self.assertTrue(queue["human_review_required"])
        for field in (
            "acceptance_authority",
            "training_eligible",
            "human_gold",
            "release_authority",
            "c3_authority",
        ):
            self.assertFalse(queue[field])

        item = queue["items"][0]
        self.assertEqual(item["case_id"], local_fail["case_id"])
        self.assertEqual(item["local_expected_passed"], False)
        self.assertEqual(item["releasefoundry_passed"], True)
        self.assertEqual(item["releasefoundry_score"], 95.0)
        self.assertEqual(item["human_review_state"], "pending")
        self.assertEqual(item["minimum_repeat_count"], 3)
        self.assertTrue(item["variant_id_hash"].startswith("sha256:"))
        self.assertNotEqual(item["variant_id_hash"], local_fail["variant_id"])

        serialized = json.dumps(queue)
        self.assertNotIn(local_fail["variant_id"], serialized)
        self.assertNotIn("actual_response", serialized)
        self.assertNotIn("expected_response", serialized)
        calibration._assert_public_summary_safe(queue)

    def test_rejects_authority_escalation_and_stale_receipt(self):
        matrix, journal, receipt, _ = self._inputs()

        receipt["training_eligible"] = True
        with self.assertRaisesRegex(
            review_queue.DisagreementQueueError,
            "public_receipt_training_eligible_must_be_false",
        ):
            review_queue.build_review_queue(journal, receipt, matrix)

        _, journal, receipt, _ = self._inputs()
        receipt["graded_evaluations"] = 999
        with self.assertRaisesRegex(
            review_queue.DisagreementQueueError,
            "public_receipt_graded_evaluations_mismatch",
        ):
            review_queue.build_review_queue(journal, receipt, matrix)

    def test_rejects_batch_when_one_test_has_no_server_grading_marker(self):
        matrix, journal, receipt, _ = self._inputs()
        tests = journal["batches"][0]["terminal_response"]["result"]["tests"]
        tests[1].pop("failed_actions")
        tests[1]["action_results"] = []

        with self.assertRaisesRegex(
            review_queue.DisagreementQueueError,
            "test_server_grading_marker_missing",
        ):
            review_queue.build_review_queue(journal, receipt, matrix)

    def test_cli_writes_public_safe_queue(self):
        matrix, journal, receipt, _ = self._inputs()
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            private_root = temp_root / "private_refs"
            private_root.mkdir()
            private_path = private_root / "journal.private.json"
            receipt_path = temp_root / "receipt.json"
            output_path = temp_root / "queue.json"
            private_path.write_text(json.dumps(journal), encoding="utf-8")
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

            with (
                mock.patch.object(calibration, "PRIVATE_ROOT", private_root),
                mock.patch.object(
                    review_queue.calibration,
                    "build_matrix",
                    return_value=matrix,
                ),
            ):
                exit_code = review_queue.main(
                    [
                        "--private-journal",
                        str(private_path),
                        "--public-receipt",
                        str(receipt_path),
                        "--output",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["review_item_count"], 1)
            calibration._assert_public_summary_safe(payload)


if __name__ == "__main__":
    unittest.main()
