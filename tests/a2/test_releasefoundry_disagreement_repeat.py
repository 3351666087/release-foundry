from __future__ import annotations

import json
import unittest
from unittest import mock

from scripts import a2_releasefoundry_disagreement_repeat as repeat
from scripts import a2_releasefoundry_live_calibration as calibration


class ReleaseFoundryDisagreementRepeatTests(unittest.TestCase):
    def _queue_and_matrix(self):
        matrix = calibration.build_matrix()
        local_fail = next(item for item in matrix if item["expected_passed"] is False)
        local_pass = next(item for item in matrix if item["expected_passed"] is True)
        items = []
        for index, (variant, original_releasefoundry_passed) in enumerate(
            ((local_fail, True), (local_pass, False)),
            start=1,
        ):
            variant_hash = repeat._variant_id_hash(variant["variant_id"])
            items.append(
                {
                    "review_item_id": f"sha256:{index:064x}",
                    "variant_id_hash": variant_hash,
                    "case_id": variant["case_id"],
                    "channel": variant["channel"],
                    "prompt_variant": variant["prompt_variant"],
                    "expected_variant": variant["expected_variant"],
                    "local_expected_passed": variant["expected_passed"],
                    "releasefoundry_passed": original_releasefoundry_passed,
                    "releasefoundry_score": 95,
                    "human_review_state": "pending",
                    "training_eligible": False,
                    "repeat_requested": True,
                    "minimum_repeat_count": 3,
                }
            )
        queue = {
            "schema_version": "a2.releasefoundry_disagreement_review_queue.v1",
            "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
            "review_status": "pending_human_review",
            "acceptance_authority": False,
            "training_eligible": False,
            "human_gold": False,
            "release_authority": False,
            "c3_authority": False,
            "repeat_experiment_eligible": True,
            "review_item_count": len(items),
            "items": items,
        }
        return queue, matrix

    def test_build_repeat_matrix_preserves_dataset_bound_ids(self):
        queue, matrix = self._queue_and_matrix()

        repeated = repeat.build_repeat_matrix(
            queue,
            matrix,
            repeat_count=3,
        )

        self.assertEqual(len(repeated), 6)
        self.assertEqual(
            [item["repeat_index"] for item in repeated],
            [1, 1, 2, 2, 3, 3],
        )
        first_ids = [item["variant_id"] for item in repeated[:2]]
        self.assertEqual(
            [item["variant_id"] for item in repeated[2:4]],
            first_ids,
        )
        self.assertEqual(
            [item["variant_id"] for item in repeated[4:]],
            first_ids,
        )
        self.assertEqual(
            {item["source_variant_hash"] for item in repeated},
            {item["variant_id_hash"] for item in queue["items"]},
        )

    def test_build_repeat_matrix_rejects_unknown_review_hash(self):
        queue, matrix = self._queue_and_matrix()
        queue["items"][0]["variant_id_hash"] = "sha256:" + ("f" * 64)

        with self.assertRaisesRegex(
            repeat.DisagreementRepeatError,
            "review_variant_not_found_in_matrix",
        ):
            repeat.build_repeat_matrix(queue, matrix, repeat_count=3)

    def test_build_repeat_report_classifies_persistent_and_stochastic(self):
        queue, matrix = self._queue_and_matrix()
        repeated = repeat.build_repeat_matrix(queue, matrix, repeat_count=3)
        journals = {}
        for repeat_index in range(1, 4):
            variants = repeat._matrix_for_repeat(repeated, repeat_index)
            tests = []
            for item_index, variant in enumerate(variants):
                passed = item_index == 0 or repeat_index != 2
                tests.append(
                    {
                        "test_id": variant["variant_id"],
                        "status": "completed" if passed else "failed",
                        "failed_actions": [] if passed else [{}],
                        "action_results": [
                            {
                                "actor": "agent",
                                "action_type": "text",
                                "semantic_similarity": (
                                    0.9 if passed else 0.4
                                ),
                                "llm_judgment": {
                                    "verdict": "match" if passed else "mismatch"
                                },
                            }
                        ],
                    }
                )
            journals[repeat_index] = {
                "batches": [
                    {
                        "status": "completed",
                        "variant_ids": [
                            item["variant_id"] for item in variants
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
                                "aggregate_metrics": {
                                    "action_summary": {"passed": 2}
                                },
                                "tests": tests,
                            }
                        },
                    }
                ]
            }

        with mock.patch.object(
            calibration,
            "_now",
            return_value="2026-07-27T18:00:00Z",
        ):
            report = repeat.build_repeat_report(
                queue,
                repeated,
                journals,
                repeat_count=3,
            )

        self.assertEqual(report["repeat_status"], "completed")
        self.assertEqual(report["repeat_plan"]["observed_evaluations"], 6)
        self.assertTrue(
            report["repeat_plan"][
                "dataset_bound_test_ids_preserved_across_runs"
            ]
        )
        self.assertEqual(report["create_run_safety"]["attempts"], 3)
        self.assertEqual(report["create_run_safety"]["retries"], 0)
        self.assertEqual(
            report["server_grading"]["tests_with_final_answer_grading"],
            6,
        )
        self.assertEqual(
            report["outcome_summary"]["classifications"],
            {
                "persistent_disagreement": 1,
                "stochastic_boundary": 1,
            },
        )
        serialized = json.dumps(report)
        for variant in matrix:
            self.assertNotIn(variant["variant_id"], serialized)
        calibration._assert_public_summary_safe(report)

    def test_structural_only_repeat_is_not_reported_as_disagreement(self):
        queue, matrix = self._queue_and_matrix()
        repeated = repeat.build_repeat_matrix(queue, matrix, repeat_count=3)
        journals = {}
        for repeat_index in range(1, 4):
            variants = repeat._matrix_for_repeat(repeated, repeat_index)
            journals[repeat_index] = {
                "batches": [
                    {
                        "status": "completed",
                        "variant_ids": [
                            item["variant_id"] for item in variants
                        ],
                        "terminal_response": {
                            "result": {
                                "aggregate_metrics": {
                                    "action_summary": {"passed": 2}
                                },
                                "tests": [
                                    {
                                        "test_id": item["variant_id"],
                                        "status": "completed",
                                        "action_results": [
                                            {
                                                "tool_calls": [
                                                    {
                                                        "argument_comparison": {
                                                            "matching": {},
                                                            "missing": {},
                                                            "extra": {},
                                                            "different": {},
                                                        }
                                                    }
                                                ]
                                            }
                                        ],
                                    }
                                    for item in variants
                                ],
                            }
                        },
                    }
                ]
            }

        report = repeat.build_repeat_report(
            queue,
            repeated,
            journals,
            repeat_count=3,
        )

        self.assertEqual(report["repeat_status"], "partial")
        self.assertEqual(
            report["outcome_summary"]["classifications"],
            {"incomplete_grading_signal": 2},
        )
        self.assertEqual(
            report["server_grading"]["tests_with_final_answer_grading"],
            0,
        )

    def test_incomplete_completed_run_is_reopened_for_read_only_resume(self):
        queue, matrix = self._queue_and_matrix()
        repeated = repeat.build_repeat_matrix(queue, matrix, repeat_count=3)
        variants = repeat._matrix_for_repeat(repeated, 1)
        journal = {
            "batches": [
                {
                    "status": "completed",
                    "run_id": 123,
                    "completed_at": "2026-07-27T18:00:00Z",
                    "variant_ids": [
                        item["variant_id"] for item in variants
                    ],
                    "terminal_response": {
                        "result": {
                            "tests": [
                                {
                                    "test_id": item["variant_id"],
                                    "status": "completed",
                                    "action_results": [
                                        {
                                            "tool_calls": [
                                                {
                                                    "argument_comparison": {
                                                        "matching": {},
                                                        "missing": {},
                                                        "extra": {},
                                                        "different": {},
                                                    }
                                                }
                                            ]
                                        }
                                    ],
                                }
                                for item in variants
                            ]
                        }
                    },
                }
            ]
        }
        with mock.patch.object(
            calibration,
            "_write_private_journal",
        ) as write_private:
            reopened = repeat._prepare_incomplete_repeat_for_resume(
                calibration.PRIVATE_ROOT / "repeat.private.json",
                journal,
                variants,
            )

        self.assertTrue(reopened)
        write_private.assert_called_once()
        self.assertEqual(journal["batches"][0]["status"], "submitted")
        self.assertEqual(journal["batches"][0]["run_id"], 123)
        self.assertNotIn("completed_at", journal["batches"][0])
        self.assertEqual(
            journal["batches"][0]["last_poll_outcome"],
            "incomplete_final_answer_grading",
        )

    def test_repeat_report_rejects_completed_batch_without_each_marker(self):
        queue, matrix = self._queue_and_matrix()
        repeated = repeat.build_repeat_matrix(queue, matrix, repeat_count=3)
        variants = repeat._matrix_for_repeat(repeated, 1)
        journals = {
            1: {
                "batches": [
                    {
                        "status": "completed",
                        "variant_ids": [
                            item["variant_id"] for item in variants
                        ],
                        "terminal_response": {
                            "result": {
                                "aggregate_metrics": {
                                    "action_summary": {"passed": 2}
                                },
                                "tests": [
                                    {
                                        "test_id": variants[0]["variant_id"],
                                        "status": "completed",
                                        "failed_actions": [],
                                        "action_results": [],
                                    },
                                    {
                                        "test_id": variants[1]["variant_id"],
                                        "status": "completed",
                                        "action_results": [],
                                    },
                                ],
                            }
                        },
                    }
                ]
            }
        }

        with self.assertRaisesRegex(
            repeat.DisagreementRepeatError,
            "completed_batch_grading_incomplete",
        ):
            repeat.build_repeat_report(
                queue,
                repeated,
                journals,
                repeat_count=3,
            )


if __name__ == "__main__":
    unittest.main()
