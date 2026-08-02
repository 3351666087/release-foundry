import hashlib
import json
import unittest
from pathlib import Path

from services.judge.releasefoundry_dataset_identity import (
    DatasetIdentityExpectation,
    VerifiedDatasetIdentityBinding,
)
from services.judge.releasefoundry_test_receipts import (
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_terminal_receipt,
)
from services.judge.calibration import (
    import_releasefoundry_grading_observations,
    import_semantic_judge_observations,
    merge_calibration_observations,
)
from services.judge.result_persistence import stable_hash


ROOT = Path(__file__).resolve().parents[2]
VALID_REVIEWER_RECEIPT = "sha256:" + ("a" * 64)
VALID_REVIEWED_AT_UNIX_MS = 1784700000000
EXPECTED_DATASET_ID = 7


def _verified_dataset_identity(
    *,
    dataset_id: int = EXPECTED_DATASET_ID,
    item_count: int = 2,
) -> VerifiedDatasetIdentityBinding:
    return VerifiedDatasetIdentityBinding(
        expectation=DatasetIdentityExpectation(
            dataset_id=dataset_id,
            dataset_name="synthetic-acceptance-dataset",
            dataset_content_sha256="sha256:" + ("b" * 64),
        ),
        identity_manifest_sha256="sha256:" + ("c" * 64),
        identity_receipt_sha256="sha256:" + ("d" * 64),
        content_collection="runs",
        content_item_count=item_count,
    )


class CalibrationImportSafetyTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads(
            (ROOT / "fixtures/a2/calibration/a2_g3_calibration_observations.json").read_text(
                encoding="utf-8"
            )
        )
        self.case_ids = [case["case_id"] for case in self.base["cases"]]
        self.semantic_collection_packet = json.loads(
            (
                ROOT
                / "fixtures/a2/calibration/a2_semantic_judge_collection_packet.json"
            ).read_text(encoding="utf-8")
        )
        self.semantic_collection_cases = {
            case["case_id"]: case
            for case in self.semantic_collection_packet["cases"]
        }

    def test_complete_releasefoundry_import_requires_reviewed_evidence(self):
        sample = json.loads(
            (ROOT / "fixtures/a2/calibration/releasefoundry_grading_import_sample.json").read_text(
                encoding="utf-8"
            )
        )
        case_map = json.loads(
            (ROOT / "fixtures/a2/calibration/releasefoundry_grading_import_case_map.json").read_text(
                encoding="utf-8"
            )
        )
        expected_case_ids = list(case_map.values())

        with self.assertRaisesRegex(ValueError, "review_status='reviewed'"):
            import_releasefoundry_grading_observations(
                sample,
                case_map=case_map,
                evidence_ref="docs/evidence/private_refs/releasefoundry.redacted.json",
                reviewer_receipt=VALID_REVIEWER_RECEIPT,
                reviewed_at_unix_ms=VALID_REVIEWED_AT_UNIX_MS,
                expected_case_ids=expected_case_ids,
                require_complete=True,
                expected_dataset_id=EXPECTED_DATASET_ID,
                verified_dataset_identity=_verified_dataset_identity(
                    item_count=len(case_map)
                ),
            )

        with self.assertRaisesRegex(ValueError, "missing evidence_ref"):
            import_releasefoundry_grading_observations(
                sample,
                case_map=case_map,
                review_status="reviewed",
                reviewer_receipt=VALID_REVIEWER_RECEIPT,
                reviewed_at_unix_ms=VALID_REVIEWED_AT_UNIX_MS,
                expected_case_ids=expected_case_ids,
                require_complete=True,
                expected_dataset_id=EXPECTED_DATASET_ID,
                verified_dataset_identity=_verified_dataset_identity(
                    item_count=len(case_map)
                ),
            )

        observations = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
            evidence_ref="docs/evidence/private_refs/releasefoundry.redacted.json",
            review_status="reviewed",
            reviewer_receipt=VALID_REVIEWER_RECEIPT,
            reviewed_at_unix_ms=VALID_REVIEWED_AT_UNIX_MS,
            expected_case_ids=expected_case_ids,
            require_complete=True,
            expected_dataset_id=EXPECTED_DATASET_ID,
            verified_dataset_identity=_verified_dataset_identity(
                item_count=len(case_map)
            ),
        )
        self.assertEqual({row["case_id"] for row in observations}, set(expected_case_ids))

    def test_complete_releasefoundry_import_rejects_missing_case(self):
        sample = json.loads(
            (ROOT / "fixtures/a2/calibration/releasefoundry_grading_import_sample.json").read_text(
                encoding="utf-8"
            )
        )
        case_map = json.loads(
            (ROOT / "fixtures/a2/calibration/releasefoundry_grading_import_case_map.json").read_text(
                encoding="utf-8"
            )
        )

        with self.assertRaisesRegex(ValueError, "missing=.*sample-a2-s031"):
            import_releasefoundry_grading_observations(
                sample,
                case_map=case_map,
                evidence_ref="docs/evidence/private_refs/releasefoundry.redacted.json",
                review_status="reviewed",
                reviewer_receipt=VALID_REVIEWER_RECEIPT,
                reviewed_at_unix_ms=VALID_REVIEWED_AT_UNIX_MS,
                expected_case_ids=[*case_map.values(), "sample-a2-s031-media-pipeline-unsupported-output"],
                require_complete=True,
                expected_dataset_id=EXPECTED_DATASET_ID,
                verified_dataset_identity=_verified_dataset_identity(
                    item_count=len(case_map)
                ),
            )

    def test_strict_releasefoundry_import_requires_per_test_terminal_scoring_evidence(self):
        mutations = (
            (
                lambda test: test.pop("completed_at"),
                "test_terminal_timestamps_missing_or_invalid",
            ),
            (
                lambda test: test["action_results"][0].pop("actual_response"),
                "test_response_evidence_missing",
            ),
            (
                lambda test: test["action_results"][0].pop("llm_judgment"),
                "test_server_grading_signal_missing",
            ),
        )
        for mutate, blocker in mutations:
            with self.subTest(blocker=blocker):
                sample, case_map = self._releasefoundry_sample()
                mutate(sample["response"]["run"]["result"]["tests"][0])
                with self.assertRaisesRegex(ValueError, blocker):
                    self._strict_releasefoundry_import(sample, case_map)

    def test_strict_releasefoundry_import_does_not_trust_aggregate_or_client_match_markers(self):
        sample, case_map = self._releasefoundry_sample()
        action = sample["response"]["run"]["result"]["tests"][0][
            "action_results"
        ][0]
        action.pop("llm_judgment")
        self.assertIn("match_status", action)
        self.assertIn("semantic_similarity", action)
        self.assertIn(
            "aggregate_metrics",
            sample["response"]["run"]["result"],
        )

        with self.assertRaisesRegex(
            ValueError,
            "test_server_grading_signal_missing",
        ):
            self._strict_releasefoundry_import(sample, case_map)

    def test_strict_releasefoundry_import_records_verified_llm_and_argument_receipts(self):
        sample, case_map = self._releasefoundry_sample()
        sample["response"]["run"]["result"]["tests"][1]["status"] = "failed"

        observations = self._strict_releasefoundry_import(sample, case_map)

        self.assertEqual(
            observations[0]["metadata"]["grading_signal_types"],
            ["action_llm_judgment"],
        )
        self.assertEqual(
            observations[1]["metadata"]["grading_signal_types"],
            ["tool_argument_comparison"],
        )
        self.assertEqual(
            observations[1]["metadata"]["terminal_status"],
            "failed",
        )
        run_receipt_hashes = set()
        for observation in observations:
            metadata = observation["metadata"]
            self.assertTrue(metadata["terminal_status_verified"])
            self.assertTrue(metadata["timestamps_verified"])
            self.assertTrue(metadata["response_evidence_verified"])
            self.assertTrue(metadata["server_grading_signal_verified"])
            self.assertTrue(metadata["terminal_scoring_verified"])
            self.assertEqual(metadata["terminal_receipt_blockers"], [])
            self.assertEqual(
                metadata["run_terminal_receipt_schema_version"],
                "a2.releasefoundry_test_terminal_receipt.v2",
            )
            self.assertRegex(
                metadata["run_terminal_receipt_sha256"],
                r"^sha256:[a-f0-9]{64}$",
            )
            run_receipt_hashes.add(metadata["run_terminal_receipt_sha256"])
            self.assertEqual(metadata["run_expected_test_count"], len(case_map))
            self.assertEqual(metadata["run_verified_test_count"], len(case_map))
            self.assertTrue(metadata["run_receipt_complete"])
            self.assertTrue(metadata["run_dataset_id_verified"])
            self.assertTrue(metadata["run_result_terminal_verified"])
            self.assertTrue(metadata["server_grading_lifecycle_verified"])
            self.assertTrue(metadata["exact_test_set_verified"])
            self.assertTrue(
                metadata["all_expected_tests_terminal_scoring_verified"]
            )
            self.assertEqual(
                metadata["observed_judge_version"],
                "releasefoundry-grader-v1",
            )
            self.assertEqual(
                metadata["judge_version_source"],
                "server_observed",
            )
            self.assertTrue(metadata["judge_version_verified"])
            self.assertFalse(
                metadata["aggregate_marker_used_as_acceptance_authority"]
            )
            self.assertEqual(metadata["run_terminal_receipt_blockers"], [])
            self.assertEqual(
                metadata["dataset_identity_receipt_schema_version"],
                "a2.releasefoundry_dataset_identity_receipt.v1",
            )
            self.assertTrue(metadata["dataset_identity_verified"])
            self.assertEqual(
                metadata["dataset_identity_receipt_sha256"],
                "sha256:" + ("d" * 64),
            )
            self.assertEqual(
                metadata["dataset_identity_manifest_sha256"],
                "sha256:" + ("c" * 64),
            )
            self.assertEqual(
                metadata["dataset_identity_content_sha256"],
                "sha256:" + ("b" * 64),
            )
            self.assertEqual(
                metadata["dataset_identity_content_collection"],
                "runs",
            )
            self.assertEqual(
                metadata["dataset_identity_content_item_count"],
                len(case_map),
            )
            self.assertEqual(metadata["dataset_identity_blockers"], [])
            self.assertNotIn("run_id", metadata)
            self.assertNotIn("dataset_id", metadata)
            self.assertNotIn("dataset_name", metadata)
            self.assertNotIn("identity_file", metadata)
            self.assertNotIn("started_at", metadata)
            self.assertNotIn("completed_at", metadata)
        self.assertEqual(len(run_receipt_hashes), 1)

    def test_strict_releasefoundry_merge_requires_retained_public_run_receipt(self):
        sample, case_map = self._releasefoundry_sample()
        observations = self._strict_releasefoundry_import(sample, case_map)
        base = self._base_for_case_ids(case_map.values())

        with self.assertRaisesRegex(
            ValueError,
            "run_receipt_artifact_missing",
        ):
            merge_calibration_observations(
                base,
                {"observations": observations},
                source="releasefoundry_grading",
                require_complete=True,
            )

    def test_strict_releasefoundry_merge_rejects_tampered_public_run_receipt(self):
        sample, case_map = self._releasefoundry_sample()
        observations = self._strict_releasefoundry_import(sample, case_map)
        receipt = self._public_run_receipt(sample, case_map)
        receipt["tests"][0]["response_evidence_count"] += 1
        base = self._base_for_case_ids(case_map.values())

        with self.assertRaisesRegex(
            ValueError,
            "run_terminal_receipt_sha256_mismatch",
        ):
            merge_calibration_observations(
                base,
                {
                    "run_terminal_receipt": receipt,
                    "observations": observations,
                },
                source="releasefoundry_grading",
                require_complete=True,
            )

    def test_strict_releasefoundry_merge_retains_exact_public_run_receipt(self):
        sample, case_map = self._releasefoundry_sample()
        observations = self._strict_releasefoundry_import(sample, case_map)
        receipt = self._public_run_receipt(sample, case_map)
        base = self._base_for_case_ids(case_map.values())

        merged = merge_calibration_observations(
            base,
            {
                "run_terminal_receipt": receipt,
                "observations": observations,
            },
            source="releasefoundry_grading",
            require_complete=True,
        )

        self.assertEqual(merged["releasefoundry_run_terminal_receipt"], receipt)
        self.assertIsNot(merged["releasefoundry_run_terminal_receipt"], receipt)

    def test_nonstrict_releasefoundry_merge_drops_stale_public_run_receipt(self):
        sample, case_map = self._releasefoundry_sample()
        observations = self._strict_releasefoundry_import(sample, case_map)
        receipt = self._public_run_receipt(sample, case_map)
        base = merge_calibration_observations(
            self._base_for_case_ids(case_map.values()),
            {
                "run_terminal_receipt": receipt,
                "observations": observations,
            },
            source="releasefoundry_grading",
            require_complete=True,
        )

        replacement = json.loads(json.dumps(observations[0]))
        replacement["score"] = 0.0
        replacement["passed"] = False
        replacement["primary_failure_class"] = "wrong_intent"
        merged = merge_calibration_observations(
            base,
            {"observations": [replacement]},
            source="releasefoundry_grading",
        )

        self.assertNotIn("releasefoundry_run_terminal_receipt", merged)

    def test_strict_releasefoundry_import_requires_fixed_dataset_identity(self):
        sample, case_map = self._releasefoundry_sample()

        with self.assertRaisesRegex(ValueError, "positive expected_dataset_id"):
            import_releasefoundry_grading_observations(
                sample,
                case_map=case_map,
                require_complete=True,
            )

        with self.assertRaisesRegex(
            ValueError,
            "verified dataset identity binding",
        ):
            import_releasefoundry_grading_observations(
                sample,
                case_map=case_map,
                require_complete=True,
                expected_dataset_id=EXPECTED_DATASET_ID,
            )

        with self.assertRaisesRegex(
            ValueError,
            "does not match expected_dataset_id",
        ):
            import_releasefoundry_grading_observations(
                sample,
                case_map=case_map,
                require_complete=True,
                expected_dataset_id=EXPECTED_DATASET_ID,
                verified_dataset_identity=_verified_dataset_identity(
                    dataset_id=EXPECTED_DATASET_ID + 1,
                    item_count=len(case_map),
                ),
            )

        with self.assertRaisesRegex(
            ValueError,
            "item count does not match case_map",
        ):
            import_releasefoundry_grading_observations(
                sample,
                case_map=case_map,
                require_complete=True,
                expected_dataset_id=EXPECTED_DATASET_ID,
                verified_dataset_identity=_verified_dataset_identity(
                    item_count=len(case_map) + 1
                ),
            )

        sample["response"]["run"]["dataset"] = EXPECTED_DATASET_ID + 1
        with self.assertRaisesRegex(ValueError, "run_dataset_id_mismatch"):
            self._strict_releasefoundry_import(sample, case_map)

    def test_strict_releasefoundry_import_requires_one_complete_acceptance_run(self):
        sample, case_map = self._releasefoundry_sample()
        run = sample["response"]["run"]
        multiple_runs = {
            "response": {
                "runs": [
                    run,
                    json.loads(json.dumps(run)),
                ]
            }
        }
        with self.assertRaisesRegex(ValueError, "exactly one acceptance run"):
            self._strict_releasefoundry_import(multiple_runs, case_map)

        sample, case_map = self._releasefoundry_sample()
        sample["response"]["run"]["result"]["status"] = "running"
        with self.assertRaisesRegex(
            ValueError,
            "run_result_status_not_terminal",
        ):
            self._strict_releasefoundry_import(sample, case_map)

    def test_strict_releasefoundry_import_rejects_malformed_run_records(self):
        sample, case_map = self._releasefoundry_sample()
        run = sample["response"]["run"]

        malformed_payloads = (
            [run, None],
            {"runs": [run, "corrupt"]},
            {"response": {"runs": [run, None]}},
        )
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(
                    ValueError,
                    "strict ReleaseFoundry grading payload contains a non-object run record",
                ):
                    self._strict_releasefoundry_import(payload, case_map)

    def test_strict_releasefoundry_import_requires_server_observed_grader_version(self):
        sample, case_map = self._releasefoundry_sample()
        sample["response"]["run"]["result"].pop("judge_version")

        with self.assertRaisesRegex(
            ValueError,
            "judge_version_missing",
        ):
            self._strict_releasefoundry_import(sample, case_map)

    def test_strict_releasefoundry_import_requires_exact_test_set(self):
        sample, case_map = self._releasefoundry_sample()
        tests = sample["response"]["run"]["result"]["tests"]
        tests.append(json.loads(json.dumps(tests[0])))
        sample["response"]["run"]["result"]["aggregate_metrics"][
            "total_tests"
        ] = len(tests)

        with self.assertRaisesRegex(ValueError, "test_id_duplicate"):
            self._strict_releasefoundry_import(sample, case_map)

    def test_releasefoundry_import_consumes_test_level_failure_verdict(self):
        sample, case_map = self._releasefoundry_sample()
        test = sample["response"]["run"]["result"]["tests"][0]
        test["llm_judgment"] = {
            "verdict": "major_issue",
            "summary": "The final result omitted a required safety constraint.",
        }

        observation = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
        )[0]

        self.assertFalse(observation["passed"])
        self.assertEqual(observation["primary_failure_class"], "wrong_intent")
        self.assertIn("safety constraint", observation["rationale"])

    def test_releasefoundry_import_consumes_action_failure_without_match_status(self):
        sample, case_map = self._releasefoundry_sample()
        action = sample["response"]["run"]["result"]["tests"][0][
            "action_results"
        ][0]
        action.pop("match_status")
        action["llm_judgment"] = {
            "verdict": "partial",
            "summary": "The answer only completed part of the request.",
        }

        observation = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
        )[0]

        self.assertFalse(observation["passed"])
        self.assertEqual(observation["primary_failure_class"], "wrong_intent")
        self.assertIn("only completed part", observation["rationale"])

    def test_releasefoundry_import_consumes_tool_judgment_without_legacy_status(self):
        sample, case_map = self._releasefoundry_sample()
        test = sample["response"]["run"]["result"]["tests"][1]
        test["status"] = "completed"
        call = test["action_results"][0]["tool_calls"][0]
        call.pop("match_status")
        call.pop("argument_comparison")
        call["llm_judgment"] = {
            "verdict": "major_issue",
            "summary": "The requested file path did not match.",
        }

        observation = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
        )[1]

        self.assertFalse(observation["passed"])
        self.assertEqual(observation["primary_failure_class"], "wrong_arguments")
        self.assertIn("file path", observation["rationale"])

    def test_releasefoundry_import_consumes_legacy_argument_comparison_objects(self):
        sample, case_map = self._releasefoundry_sample()
        test = sample["response"]["run"]["result"]["tests"][1]
        test["status"] = "completed"
        call = test["action_results"][0]["tool_calls"][0]
        call.pop("match_status")
        call["argument_comparison"] = {
            "different": {
                "city": {
                    "actual": "wrong",
                    "expected": "right",
                }
            },
            "extra": {},
            "matching": {},
            "missing": {},
        }

        observation = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
        )[1]

        self.assertFalse(observation["passed"])
        self.assertEqual(observation["primary_failure_class"], "wrong_arguments")

    def test_releasefoundry_import_consumes_coherence_failure(self):
        sample, case_map = self._releasefoundry_sample()
        test = sample["response"]["run"]["result"]["tests"][0]
        test["coherence"] = {
            "score": 0.9,
            "summary": "The final answer dropped a required verification step.",
            "issues": [{"issue_type": "context_loss"}],
        }

        observation = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
        )[0]

        self.assertFalse(observation["passed"])
        self.assertEqual(observation["primary_failure_class"], "wrong_intent")
        self.assertIn("verification step", observation["rationale"])

    def test_releasefoundry_import_fails_closed_on_unknown_grading_verdict(self):
        sample, case_map = self._releasefoundry_sample()
        action = sample["response"]["run"]["result"]["tests"][0][
            "action_results"
        ][0]
        action["llm_judgment"] = {"verdict": "unknown_new_verdict"}

        observation = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
        )[0]

        self.assertFalse(observation["passed"])
        self.assertEqual(observation["primary_failure_class"], "wrong_intent")
        self.assertIn("not interpretable", observation["rationale"])

    def test_terminal_failed_status_is_not_labeled_as_recovery_failure(self):
        sample, case_map = self._releasefoundry_sample()
        sample["response"]["run"]["result"]["tests"][0]["status"] = "failed"

        observation = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
        )[0]

        self.assertFalse(observation["passed"])
        self.assertEqual(observation["primary_failure_class"], "wrong_intent")
        self.assertNotIn("recovery", observation["rationale"].lower())

    def test_releasefoundry_import_accepts_only_explicitly_passing_grading_signals(self):
        sample, case_map = self._releasefoundry_sample()
        test = sample["response"]["run"]["result"]["tests"][0]
        test["action_results"][0]["llm_judgment"] = {
            "verdict": "acceptable",
            "summary": "The response is acceptable.",
        }
        test["llm_judgment"] = {"verdict": "pass"}
        test["coherence"] = {
            "score": 1.0,
            "summary": "No coherence issues were found.",
            "issues": [],
        }

        observation = import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
        )[0]

        self.assertTrue(observation["passed"])
        self.assertEqual(observation["primary_failure_class"], "none")

    def test_strict_releasefoundry_import_rejects_uncontrolled_evidence_refs(self):
        sample, case_map = self._releasefoundry_sample()
        invalid_refs = (
            "foo",
            "fixtures/a2/public.json",
            "https://example.invalid/raw.json",
            "/tmp/private.json",
            "C:/private/raw.json",
            "../outside.json",
            "docs/evidence/private_refs/",
            "docs/evidence/private_refs/../public.json",
            "docs\\evidence\\private_refs\\releasefoundry.redacted.json",
            "docs/evidence/private_refs/releasefoundry.redacted.json#",
            "docs/evidence/private_refs/releasefoundry.redacted.json?token=value",
            "docs/evidence/private_refs/%2e%2e/public.json",
            "docs/evidence/private_refs/tp_secret.json",
            123,
        )
        for evidence_ref in invalid_refs:
            with self.subTest(evidence_ref=evidence_ref):
                with self.assertRaisesRegex(ValueError, "evidence_ref"):
                    import_releasefoundry_grading_observations(
                        sample,
                        case_map=case_map,
                        evidence_ref=evidence_ref,
                        review_status="reviewed",
                        reviewer_receipt=VALID_REVIEWER_RECEIPT,
                        reviewed_at_unix_ms=VALID_REVIEWED_AT_UNIX_MS,
                        require_reviewed=True,
                        expected_dataset_id=EXPECTED_DATASET_ID,
                        verified_dataset_identity=_verified_dataset_identity(
                            item_count=len(case_map)
                        ),
                    )

    def test_strict_releasefoundry_import_requires_canonical_reviewer_attestation(self):
        sample, case_map = self._releasefoundry_sample()
        invalid_receipts = (
            None,
            "",
            "reviewer@example.com",
            "sha256:" + ("A" * 64),
            "sha256:" + ("a" * 63),
            123,
        )
        for reviewer_receipt in invalid_receipts:
            with self.subTest(reviewer_receipt=reviewer_receipt):
                with self.assertRaisesRegex(ValueError, "canonical metadata.reviewer_receipt"):
                    import_releasefoundry_grading_observations(
                        sample,
                        case_map=case_map,
                        evidence_ref="docs/evidence/private_refs/releasefoundry.redacted.json",
                        review_status="reviewed",
                        reviewer_receipt=reviewer_receipt,
                        reviewed_at_unix_ms=VALID_REVIEWED_AT_UNIX_MS,
                        require_reviewed=True,
                        expected_dataset_id=EXPECTED_DATASET_ID,
                        verified_dataset_identity=_verified_dataset_identity(
                            item_count=len(case_map)
                        ),
                    )

        invalid_timestamps = (
            None,
            True,
            False,
            0,
            -1,
            1.5,
            str(VALID_REVIEWED_AT_UNIX_MS),
        )
        for reviewed_at_unix_ms in invalid_timestamps:
            with self.subTest(reviewed_at_unix_ms=reviewed_at_unix_ms):
                with self.assertRaisesRegex(ValueError, "metadata.reviewed_at_unix_ms > 0"):
                    import_releasefoundry_grading_observations(
                        sample,
                        case_map=case_map,
                        evidence_ref="docs/evidence/private_refs/releasefoundry.redacted.json",
                        review_status="reviewed",
                        reviewer_receipt=VALID_REVIEWER_RECEIPT,
                        reviewed_at_unix_ms=reviewed_at_unix_ms,
                        require_reviewed=True,
                        expected_dataset_id=EXPECTED_DATASET_ID,
                        verified_dataset_identity=_verified_dataset_identity(
                            item_count=len(case_map)
                        ),
                    )

    def test_releasefoundry_import_rejects_invalid_semantic_similarity(self):
        invalid_scores = ("0.95", -0.1, float("nan"), 100.1, True)
        for score in invalid_scores:
            with self.subTest(score=score):
                sample = json.loads(
                    (
                        ROOT / "fixtures/a2/calibration/releasefoundry_grading_import_sample.json"
                    ).read_text(encoding="utf-8")
                )
                sample["response"]["run"]["result"]["tests"][0]["action_results"][0][
                    "semantic_similarity"
                ] = score
                with self.assertRaisesRegex(
                    ValueError,
                    "finite numeric semantic_similarity between 0 and 100",
                ):
                    import_releasefoundry_grading_observations(sample)

    def test_reviewed_semantic_import_rejects_offline_or_incomplete_rows(self):
        item = self._semantic_item(self.case_ids[0], sdk_language="python")
        item["provider"] = "offline_reference"
        with self.assertRaisesRegex(ValueError, "uses offline provider"):
            import_semantic_judge_observations(
                [item],
                require_reviewed=True,
            )

        item = self._semantic_item(self.case_ids[0], sdk_language="python")
        item["output"]["passed"] = "false"
        with self.assertRaisesRegex(ValueError, "must have a boolean passed value"):
            import_semantic_judge_observations([item])

        item = self._semantic_item(self.case_ids[0], sdk_language="python")
        item.pop("prompt_hash")
        with self.assertRaisesRegex(ValueError, "prompt_hash"):
            import_semantic_judge_observations(
                [item],
                require_reviewed=True,
            )

    def test_strict_semantic_import_requires_reviewer_attestation(self):
        item = self._semantic_item(self.case_ids[0], sdk_language="python")
        item.pop("reviewer_receipt")
        with self.assertRaisesRegex(ValueError, "canonical metadata.reviewer_receipt"):
            import_semantic_judge_observations([item], require_reviewed=True)

        item = self._semantic_item(self.case_ids[0], sdk_language="python")
        item["reviewer_receipt"] = "reviewer@example.com"
        with self.assertRaisesRegex(ValueError, "canonical metadata.reviewer_receipt"):
            import_semantic_judge_observations([item], require_reviewed=True)

        item = self._semantic_item(self.case_ids[0], sdk_language="python")
        item["reviewed_at_unix_ms"] = True
        with self.assertRaisesRegex(ValueError, "metadata.reviewed_at_unix_ms > 0"):
            import_semantic_judge_observations([item], require_reviewed=True)

    def test_strict_semantic_import_requires_canonical_prompt_and_response_hashes(self):
        invalid_hashes = (
            "prompt-s001",
            "sha256:prompt-s001",
            "sha256:" + ("A" * 64),
            "sha256:" + ("a" * 63),
            True,
        )
        for field in ("prompt_hash", "response_hash"):
            for value in invalid_hashes:
                with self.subTest(field=field, value=value):
                    item = self._semantic_item(
                        self.case_ids[0],
                        sdk_language="python",
                    )
                    item[field] = value
                    with self.assertRaisesRegex(
                        ValueError,
                        rf"canonical metadata\.{field}",
                    ):
                        import_semantic_judge_observations(
                            [item],
                            require_reviewed=True,
                        )

    def test_strict_semantic_import_rejects_uncontrolled_evidence_refs(self):
        invalid_refs = (
            "semantic.redacted.json",
            "file:///tmp/semantic.json",
            "docs/evidence/private_refs/../semantic.json",
            "docs/evidence/private_refs/semantic.redacted.json#bad fragment",
            ["docs/evidence/private_refs/semantic.redacted.json"],
        )
        for evidence_ref in invalid_refs:
            with self.subTest(evidence_ref=evidence_ref):
                item = self._semantic_item(self.case_ids[0], sdk_language="python")
                item["output"]["evidence_refs"] = [evidence_ref]
                with self.assertRaisesRegex(ValueError, "evidence_ref"):
                    import_semantic_judge_observations(
                        [item],
                        require_reviewed=True,
                    )

    def test_semantic_import_rejects_invalid_scores(self):
        invalid_scores = ("95", -0.1, float("nan"), 100.1, True)
        for score in invalid_scores:
            with self.subTest(score=score):
                item = self._semantic_item(self.case_ids[0], sdk_language="python")
                item["output"]["score"] = score
                with self.assertRaisesRegex(
                    ValueError,
                    "finite numeric score between 0 and 100",
                ):
                    import_semantic_judge_observations([item])

    def test_semantic_import_rejects_invalid_confidence(self):
        invalid_confidence = (
            True,
            "0.9",
            0,
            -0.1,
            1.1,
            float("nan"),
            float("inf"),
            float("-inf"),
        )
        for confidence in invalid_confidence:
            with self.subTest(confidence=confidence):
                item = self._semantic_item(self.case_ids[0], sdk_language="python")
                item["output"]["confidence"] = confidence
                with self.assertRaisesRegex(ValueError, r"confidence in \(0, 1\]"):
                    import_semantic_judge_observations([item])

    def test_semantic_import_rejects_invalid_cost(self):
        invalid_cost = (
            ("prompt_tokens", True),
            ("prompt_tokens", "100"),
            ("prompt_tokens", 1.5),
            ("prompt_tokens", 0),
            ("prompt_tokens", -1),
            ("completion_tokens", True),
            ("completion_tokens", "20"),
            ("completion_tokens", 1.5),
            ("completion_tokens", 0),
            ("completion_tokens", -1),
            ("estimated_usd", True),
            ("estimated_usd", "0.001"),
            ("estimated_usd", 0),
            ("estimated_usd", -0.001),
            ("estimated_usd", float("nan")),
            ("estimated_usd", float("inf")),
            ("estimated_usd", float("-inf")),
        )
        for field, value in invalid_cost:
            with self.subTest(field=field, value=value):
                item = self._semantic_item(self.case_ids[0], sdk_language="python")
                item["cost"][field] = value
                with self.assertRaisesRegex(ValueError, rf"positive cost\.{field}"):
                    import_semantic_judge_observations([item])

    def test_complete_semantic_import_accepts_reviewed_live_batch(self):
        items = [
            self._semantic_item(
                case_id,
                sdk_language=self.semantic_collection_cases[case_id][
                    "sdk_language"
                ],
            )
            for case_id in self.case_ids
        ]
        review_receipt = self._semantic_review_receipt(
            import_semantic_judge_observations(items)
        )

        observations = import_semantic_judge_observations(
            {
                "cases": items,
                "semantic_human_review_receipt": review_receipt,
            },
            expected_case_ids=self.case_ids,
            require_complete=True,
        )

        self.assertEqual(len(observations), len(self.case_ids))
        self.assertEqual(
            {row["metadata"]["sdk_language"] for row in observations},
            {"python", "typescript"},
        )
        self.assertEqual(
            {
                row["metadata"]["semantic_collection_packet_sha256"]
                for row in observations
            },
            {self.semantic_collection_packet["artifact_hash"]},
        )
        self.assertEqual(
            {
                row["metadata"]["semantic_review_receipt_sha256"]
                for row in observations
            },
            {stable_hash(review_receipt)},
        )
        merged = merge_calibration_observations(
            self.base,
            {
                "observations": observations,
                "semantic_human_review_receipt": review_receipt,
            },
            source="llm_judge",
            require_complete=True,
        )
        merged_rows = [row for row in merged["observations"] if row["source"] == "llm_judge"]
        self.assertEqual(len(merged_rows), len(self.case_ids))
        self.assertEqual(
            merged["semantic_human_review_receipt"],
            review_receipt,
        )
        self.assertEqual(merged_rows[0]["confidence"], 0.9)
        self.assertEqual(
            merged_rows[0]["cost"],
            {"prompt_tokens": 100, "completion_tokens": 20, "estimated_usd": 0.001},
        )

    def test_nonstrict_semantic_merge_drops_stale_human_review_receipt(self):
        items = [
            self._semantic_item(
                case_id,
                sdk_language=self.semantic_collection_cases[case_id][
                    "sdk_language"
                ],
            )
            for case_id in self.case_ids
        ]
        review_receipt = self._semantic_review_receipt(
            import_semantic_judge_observations(items)
        )
        observations = import_semantic_judge_observations(
            {
                "cases": items,
                "semantic_human_review_receipt": review_receipt,
            },
            expected_case_ids=self.case_ids,
            require_complete=True,
        )
        base = merge_calibration_observations(
            self.base,
            {
                "observations": observations,
                "semantic_human_review_receipt": review_receipt,
            },
            source="llm_judge",
            require_complete=True,
        )

        replacement = json.loads(json.dumps(observations[0]))
        replacement["score"] = 10.0
        merged = merge_calibration_observations(
            base,
            {"observations": [replacement]},
            source="llm_judge",
        )

        self.assertNotIn("semantic_human_review_receipt", merged)

    def test_complete_semantic_import_requires_independent_review_receipt(self):
        items = [
            self._semantic_item(
                case_id,
                sdk_language=self.semantic_collection_cases[case_id][
                    "sdk_language"
                ],
            )
            for case_id in self.case_ids
        ]

        with self.assertRaisesRegex(
            ValueError,
            "semantic human review receipt artifact missing",
        ):
            import_semantic_judge_observations(
                items,
                expected_case_ids=self.case_ids,
                require_complete=True,
            )

    def test_complete_semantic_import_rejects_mismatched_review_receipt(self):
        items = [
            self._semantic_item(
                case_id,
                sdk_language=self.semantic_collection_cases[case_id][
                    "sdk_language"
                ],
            )
            for case_id in self.case_ids
        ]
        review_receipt = self._semantic_review_receipt(
            import_semantic_judge_observations(items)
        )
        review_receipt["cases"][0]["passed"] = False

        with self.assertRaisesRegex(
            ValueError,
            "semantic review receipt.*passed.*mismatch",
        ):
            import_semantic_judge_observations(
                {
                    "cases": items,
                    "semantic_human_review_receipt": review_receipt,
                },
                expected_case_ids=self.case_ids,
                require_complete=True,
            )

    def test_strict_semantic_import_binds_each_case_to_collection_packet(self):
        case_id = self.case_ids[0]
        expected_case = self.semantic_collection_cases[case_id]
        mutations = (
            ("sdk_language", "typescript", "sdk_language"),
            (
                "prompt_template_id",
                "a2_semantic_judge_prompt_v2",
                "prompt_template_id",
            ),
            (
                "prompt_hash",
                "sha256:" + ("f" * 64),
                "prompt_hash",
            ),
        )
        for field, value, error_field in mutations:
            with self.subTest(field=field):
                item = self._semantic_item(
                    case_id,
                    sdk_language=expected_case["sdk_language"],
                )
                item[field] = value
                with self.assertRaisesRegex(
                    ValueError,
                    rf"{error_field} does not match",
                ):
                    import_semantic_judge_observations(
                        [item],
                        expected_case_ids=self.case_ids,
                        require_reviewed=True,
                    )

    def test_complete_semantic_import_rejects_swapped_sdk_allocations(self):
        items = [
            self._semantic_item(
                case_id,
                sdk_language=self.semantic_collection_cases[case_id][
                    "sdk_language"
                ],
            )
            for case_id in self.case_ids
        ]
        python_item = next(
            item for item in items if item["sdk_language"] == "python"
        )
        typescript_item = next(
            item for item in items if item["sdk_language"] == "typescript"
        )
        python_item["sdk_language"], typescript_item["sdk_language"] = (
            typescript_item["sdk_language"],
            python_item["sdk_language"],
        )

        with self.assertRaisesRegex(ValueError, "sdk_language does not match"):
            import_semantic_judge_observations(
                items,
                expected_case_ids=self.case_ids,
                require_complete=True,
            )

    def test_strict_semantic_import_rejects_claimed_different_packet_hash(self):
        case_id = self.case_ids[0]
        item = self._semantic_item(
            case_id,
            sdk_language=self.semantic_collection_cases[case_id][
                "sdk_language"
            ],
        )
        item["metadata"] = {
            "semantic_collection_packet_sha256": "sha256:" + ("f" * 64)
        }

        with self.assertRaisesRegex(
            ValueError,
            "semantic_collection_packet_sha256.*does not match",
        ):
            import_semantic_judge_observations(
                [item],
                expected_case_ids=self.case_ids,
                require_reviewed=True,
            )

    def test_strict_semantic_merge_rejects_mixed_packet_hash(self):
        items = [
            self._semantic_item(
                case_id,
                sdk_language=self.semantic_collection_cases[case_id][
                    "sdk_language"
                ],
            )
            for case_id in self.case_ids
        ]
        review_receipt = self._semantic_review_receipt(
            import_semantic_judge_observations(items)
        )
        observations = import_semantic_judge_observations(
            {
                "cases": items,
                "semantic_human_review_receipt": review_receipt,
            },
            expected_case_ids=self.case_ids,
            require_complete=True,
        )
        observations[-1]["metadata"][
            "semantic_collection_packet_sha256"
        ] = "sha256:" + ("f" * 64)

        with self.assertRaisesRegex(
            ValueError,
            "semantic_collection_packet_sha256.*does not match",
        ):
            merge_calibration_observations(
                self.base,
                {
                    "observations": observations,
                    "semantic_human_review_receipt": review_receipt,
                },
                source="llm_judge",
                require_complete=True,
            )

    def test_complete_merge_rejects_partial_reviewed_source(self):
        observations = [
            {
                "case_id": self.case_ids[0],
                "scenario_id": "ignored-by-merge",
                "source": "releasefoundry_grading",
                "status": "available",
                "provider": "releasefoundry server-side grading",
                "model": "releasefoundry-server-side",
                "passed": True,
                "primary_failure_class": "none",
                "score": 100.0,
                "confidence": 1.0,
                "rationale": "Reviewed unit-test row.",
                "cost": {"prompt_tokens": 0, "completion_tokens": 0, "estimated_usd": 0.0},
                "evidence_ref": "docs/evidence/private_refs/releasefoundry.redacted.json",
                "metadata": {
                    "review_status": "reviewed",
                    "reviewer_receipt": VALID_REVIEWER_RECEIPT,
                    "reviewed_at_unix_ms": VALID_REVIEWED_AT_UNIX_MS,
                },
            }
        ]

        with self.assertRaisesRegex(ValueError, "do not exactly cover expected cases"):
            merge_calibration_observations(
                self.base,
                {"observations": observations},
                source="releasefoundry_grading",
                require_complete=True,
            )

    def test_merge_rejects_malformed_base_cases(self):
        malformed_cases = (
            ([], "JSON object"),
            ({}, "non-empty cases list"),
            ({"cases": "not-a-list", "observations": []}, "non-empty cases list"),
            ({"cases": [], "observations": []}, "non-empty cases list"),
        )
        for payload, message in malformed_cases:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, message):
                    merge_calibration_observations(
                        payload,
                        {"observations": [self._releasefoundry_observation()]},
                    )

        malformed_case_rows = (
            ("not-an-object", "case at index 0 must be an object"),
            ({"case_id": "", "scenario_id": "A2-S001"}, "case_id must be a canonical non-empty string"),
            (
                {"case_id": " case-1 ", "scenario_id": "A2-S001"},
                "case_id must be a canonical non-empty string",
            ),
            (
                {"case_id": "case-1", "scenario_id": ""},
                "scenario_id must be a canonical non-empty string",
            ),
        )
        for case, message in malformed_case_rows:
            with self.subTest(case=case):
                payload = {"cases": [case], "observations": []}
                with self.assertRaisesRegex(ValueError, message):
                    merge_calibration_observations(
                        payload,
                        {"observations": [self._releasefoundry_observation()]},
                    )

    def test_merge_rejects_duplicate_base_case_ids(self):
        payload = json.loads(json.dumps(self.base))
        payload["cases"].append(json.loads(json.dumps(payload["cases"][0])))

        with self.assertRaisesRegex(ValueError, "duplicate base case_id"):
            merge_calibration_observations(
                payload,
                {"observations": [self._releasefoundry_observation()]},
            )

    def test_merge_rejects_malformed_base_observations(self):
        malformed_observations = (
            ("not-a-list", "observations must be a list"),
            ([None], "observation at index 0 must be an object"),
            (
                [{"source": "llm_judge"}],
                "case_id must be a canonical non-empty string",
            ),
            (
                [{"case_id": self.case_ids[0], "source": ""}],
                "source must be a canonical non-empty string",
            ),
            (
                [{"case_id": self.case_ids[0], "source": "unknown_judge"}],
                "unknown source",
            ),
            (
                [{"case_id": "unknown-case", "source": "llm_judge"}],
                "unknown case_id",
            ),
        )
        for observations, message in malformed_observations:
            with self.subTest(observations=observations):
                payload = json.loads(json.dumps(self.base))
                payload["observations"] = observations
                with self.assertRaisesRegex(ValueError, message):
                    merge_calibration_observations(
                        payload,
                        {"observations": [self._releasefoundry_observation()]},
                    )

    def test_merge_rejects_duplicate_base_observations(self):
        payload = json.loads(json.dumps(self.base))
        payload["observations"].append(json.loads(json.dumps(payload["observations"][0])))

        with self.assertRaisesRegex(ValueError, "duplicate base observation"):
            merge_calibration_observations(
                payload,
                {"observations": [self._releasefoundry_observation()]},
            )

    def test_merge_rejects_malformed_incoming_observation_rows(self):
        valid = self._releasefoundry_observation()
        malformed_payloads = (
            ([valid, "corrupt"], "observation at index 1 must be an object"),
            (
                {"observations": [valid, None]},
                "observation at index 1 must be an object",
            ),
            ({"observations": "not-a-list"}, "observations must be a list"),
            ("not-an-object-or-list", "JSON object or list"),
        )
        for payload, message in malformed_payloads:
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, message):
                    merge_calibration_observations(self.base, payload)

    def test_merge_rejects_unapproved_external_metadata(self):
        observations = (
            ("releasefoundry_grading", self._releasefoundry_observation()),
            ("llm_judge", self._semantic_observation()),
        )
        for source, observation in observations:
            with self.subTest(source=source):
                observation["metadata"]["raw_server_payload"] = {
                    "headers": {"authorization": "private-value"},
                    "response": {"raw": True},
                }
                with self.assertRaisesRegex(
                    ValueError,
                    "unsupported metadata fields: raw_server_payload",
                ):
                    merge_calibration_observations(
                        self.base,
                        {"observations": [observation]},
                        source=source,
                    )

    def test_merge_rejects_nested_payload_in_approved_metadata_field(self):
        observation = self._releasefoundry_observation()
        observation["metadata"]["terminal_receipt_blockers"] = [
            {"raw_response": {"private": True}}
        ]

        with self.assertRaisesRegex(
            ValueError,
            "metadata.terminal_receipt_blockers must contain only strings",
        ):
            merge_calibration_observations(
                self.base,
                {"observations": [observation]},
                source="releasefoundry_grading",
            )

    def test_strict_merge_rejects_invalid_external_score(self):
        observation = {
            "case_id": self.case_ids[0],
            "scenario_id": "ignored-by-merge",
            "source": "releasefoundry_grading",
            "status": "available",
            "provider": "releasefoundry server-side grading",
            "model": "releasefoundry-server-side",
            "passed": True,
            "primary_failure_class": "none",
            "score": float("inf"),
            "confidence": 1.0,
            "rationale": "Reviewed unit-test row.",
            "cost": {"prompt_tokens": 0, "completion_tokens": 0, "estimated_usd": 0.0},
            "evidence_ref": "docs/evidence/private_refs/releasefoundry.redacted.json",
            "metadata": {
                "review_status": "reviewed",
                "reviewer_receipt": VALID_REVIEWER_RECEIPT,
                "reviewed_at_unix_ms": VALID_REVIEWED_AT_UNIX_MS,
            },
        }

        with self.assertRaisesRegex(
            ValueError,
            "finite numeric score between 0 and 100",
        ):
            merge_calibration_observations(
                self.base,
                {"observations": [observation]},
                source="releasefoundry_grading",
                require_reviewed=True,
            )

    def test_strict_merge_rejects_uncontrolled_evidence_ref(self):
        observation = {
            "case_id": self.case_ids[0],
            "scenario_id": "ignored-by-merge",
            "source": "releasefoundry_grading",
            "status": "available",
            "provider": "releasefoundry server-side grading",
            "model": "releasefoundry-server-side",
            "passed": True,
            "primary_failure_class": "none",
            "score": 100.0,
            "confidence": 1.0,
            "rationale": "Reviewed unit-test row.",
            "cost": {"prompt_tokens": 0, "completion_tokens": 0, "estimated_usd": 0.0},
            "evidence_ref": "https://example.invalid/raw.json",
            "metadata": {
                "review_status": "reviewed",
                "reviewer_receipt": VALID_REVIEWER_RECEIPT,
                "reviewed_at_unix_ms": VALID_REVIEWED_AT_UNIX_MS,
            },
        }

        with self.assertRaisesRegex(ValueError, "repository-relative"):
            merge_calibration_observations(
                self.base,
                {"observations": [observation]},
                source="releasefoundry_grading",
                require_reviewed=True,
            )

    def test_strict_merge_revalidates_reviewer_attestation(self):
        observation = self._releasefoundry_observation()
        observation["metadata"].pop("reviewer_receipt")
        with self.assertRaisesRegex(ValueError, "canonical metadata.reviewer_receipt"):
            merge_calibration_observations(
                self.base,
                {"observations": [observation]},
                source="releasefoundry_grading",
                require_reviewed=True,
            )

        observation = self._releasefoundry_observation()
        observation["metadata"]["reviewer_receipt"] = "sha256:" + ("A" * 64)
        with self.assertRaisesRegex(ValueError, "canonical metadata.reviewer_receipt"):
            merge_calibration_observations(
                self.base,
                {"observations": [observation]},
                source="releasefoundry_grading",
                require_reviewed=True,
            )

        observation = self._releasefoundry_observation()
        observation["metadata"]["reviewed_at_unix_ms"] = 0
        with self.assertRaisesRegex(ValueError, "metadata.reviewed_at_unix_ms > 0"):
            merge_calibration_observations(
                self.base,
                {"observations": [observation]},
                source="releasefoundry_grading",
                require_reviewed=True,
            )

    def test_merge_rejects_malformed_semantic_confidence_without_strict_mode(self):
        invalid_confidence = (
            True,
            "0.9",
            0,
            -0.1,
            1.1,
            float("nan"),
            float("inf"),
            float("-inf"),
        )
        for confidence in invalid_confidence:
            with self.subTest(confidence=confidence):
                observation = self._semantic_observation()
                observation["confidence"] = confidence
                with self.assertRaisesRegex(ValueError, r"confidence in \(0, 1\]"):
                    merge_calibration_observations(
                        self.base,
                        {"observations": [observation]},
                        source="llm_judge",
                    )

    def test_merge_rejects_malformed_semantic_cost_without_strict_mode(self):
        invalid_cost = (
            ("prompt_tokens", True),
            ("prompt_tokens", "100"),
            ("prompt_tokens", 1.5),
            ("prompt_tokens", -1),
            ("completion_tokens", True),
            ("completion_tokens", "20"),
            ("completion_tokens", 1.5),
            ("completion_tokens", -1),
            ("estimated_usd", True),
            ("estimated_usd", "0.001"),
            ("estimated_usd", -0.001),
            ("estimated_usd", float("nan")),
            ("estimated_usd", float("inf")),
            ("estimated_usd", float("-inf")),
        )
        for field, value in invalid_cost:
            with self.subTest(field=field, value=value):
                observation = self._semantic_observation()
                observation["cost"][field] = value
                with self.assertRaisesRegex(ValueError, rf"non-negative cost\.{field}"):
                    merge_calibration_observations(
                        self.base,
                        {"observations": [observation]},
                        source="llm_judge",
                    )

    def test_strict_merge_rejects_zero_semantic_cost(self):
        for field in ("prompt_tokens", "completion_tokens", "estimated_usd"):
            with self.subTest(field=field):
                observation = self._semantic_observation()
                observation["cost"][field] = 0
                with self.assertRaisesRegex(ValueError, rf"positive cost\.{field}"):
                    merge_calibration_observations(
                        self.base,
                        {"observations": [observation]},
                        source="llm_judge",
                        require_reviewed=True,
                    )

    def _semantic_observation(self) -> dict:
        item = self._semantic_item(self.case_ids[0], sdk_language="python")
        return import_semantic_judge_observations([item])[0]

    def _releasefoundry_observation(self) -> dict:
        sample, case_map = self._releasefoundry_sample()
        return import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
            evidence_ref="docs/evidence/private_refs/releasefoundry.redacted.json",
            review_status="reviewed",
            reviewer_receipt=VALID_REVIEWER_RECEIPT,
            reviewed_at_unix_ms=VALID_REVIEWED_AT_UNIX_MS,
        )[0]

    def _base_for_case_ids(self, case_ids) -> dict:
        allowed = set(case_ids)
        base = json.loads(json.dumps(self.base))
        base["cases"] = [
            case for case in base["cases"] if case["case_id"] in allowed
        ]
        base["observations"] = [
            observation
            for observation in base["observations"]
            if observation["case_id"] in allowed
        ]
        return base

    @staticmethod
    def _releasefoundry_sample() -> tuple[dict, dict]:
        sample = json.loads(
            (
                ROOT
                / "fixtures/a2/calibration/releasefoundry_grading_import_sample.json"
            ).read_text(encoding="utf-8")
        )
        case_map = json.loads(
            (
                ROOT
                / "fixtures/a2/calibration/releasefoundry_grading_import_case_map.json"
            ).read_text(encoding="utf-8")
        )
        return sample, case_map

    @staticmethod
    def _public_run_receipt(sample: dict, case_map: dict) -> dict:
        return public_releasefoundry_test_terminal_receipt(
            build_releasefoundry_test_terminal_receipt(
                sample["response"]["run"],
                case_map=case_map,
                expected_dataset_id=EXPECTED_DATASET_ID,
            )
        )

    @staticmethod
    def _strict_releasefoundry_import(
        sample: dict,
        case_map: dict,
    ) -> list[dict]:
        return import_releasefoundry_grading_observations(
            sample,
            case_map=case_map,
            evidence_ref="docs/evidence/private_refs/releasefoundry.redacted.json",
            review_status="reviewed",
            reviewer_receipt=VALID_REVIEWER_RECEIPT,
            reviewed_at_unix_ms=VALID_REVIEWED_AT_UNIX_MS,
            expected_case_ids=list(case_map.values()),
            require_complete=True,
            expected_dataset_id=EXPECTED_DATASET_ID,
            verified_dataset_identity=_verified_dataset_identity(
                item_count=len(case_map)
            ),
        )

    def _semantic_item(self, case_id: str, *, sdk_language: str) -> dict:
        collection_case = self.semantic_collection_cases[case_id]
        return {
            "case_id": case_id,
            "scenario_id": collection_case["scenario_id"],
            "provider": "unit-test-live-provider",
            "model": "unit-test-semantic-model",
            "prompt_template_id": collection_case["prompt_template_id"],
            "prompt_hash": collection_case["prompt_material_sha256"],
            "response_hash": (
                "sha256:"
                + hashlib.sha256(f"response:{case_id}".encode()).hexdigest()
            ),
            "review_status": "reviewed",
            "reviewer_receipt": VALID_REVIEWER_RECEIPT,
            "reviewed_at_unix_ms": VALID_REVIEWED_AT_UNIX_MS,
            "sdk_language": sdk_language,
            "cost": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "estimated_usd": 0.001,
            },
            "output": {
                "passed": True,
                "primary_failure_class": "none",
                "score": 95,
                "confidence": 0.9,
                "rationale": "Reviewed live semantic judge unit-test row.",
                "evidence_refs": [
                    f"docs/evidence/private_refs/semantic.redacted.json#{case_id}"
                ],
            },
        }

    @staticmethod
    def _semantic_review_receipt(
        observations: list[dict],
    ) -> dict:
        cases = []
        for observation in observations:
            metadata = observation["metadata"]
            cases.append(
                {
                    "case_id": observation["case_id"],
                    "scenario_id": observation["scenario_id"],
                    "review_status": metadata["review_status"],
                    "reviewer_receipt": metadata["reviewer_receipt"],
                    "reviewed_at_unix_ms": metadata["reviewed_at_unix_ms"],
                    "provider": observation["provider"],
                    "model": observation["model"],
                    "passed": observation["passed"],
                    "primary_failure_class": observation[
                        "primary_failure_class"
                    ],
                    "score": observation["score"],
                    "confidence": observation["confidence"],
                    "prompt_hash": metadata["prompt_hash"],
                    "response_hash": metadata["response_hash"],
                    "sdk_language": metadata["sdk_language"],
                    "evidence_ref": observation["evidence_ref"],
                    "rationale_sha256": stable_hash(
                        observation["rationale"]
                    ),
                }
            )
        return {
            "schema_version": "a2.semantic_human_review_receipt.v1",
            "verification_state": "verified",
            "review_scope": "a2_c4_semantic_judge_acceptance",
            "expected_case_count": len(cases),
            "reviewed_case_count": len(cases),
            "receipt_complete": True,
            "public_safe": True,
            "raw_review_notes_included": False,
            "raw_reviewer_identity_included": False,
            "cases": cases,
        }


if __name__ == "__main__":
    unittest.main()
