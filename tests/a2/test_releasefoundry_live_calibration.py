from __future__ import annotations

import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from scripts import a2_releasefoundry_live_calibration as calibration


class ReleaseFoundryLiveCalibrationTests(unittest.TestCase):
    def _generated_dataset(self, spec, *, dataset_id: int = 42):
        run_order = [5, 1, 0, 4, 2, 3]
        runs = []
        for contract_index in run_order:
            contract = spec.case_contracts[contract_index]
            anchors = [
                contract.title,
                contract.user_task,
                *contract.expected_behaviors[:2],
                contract.primary_failure_class,
            ]
            runs.append(
                {
                    "run_id": f"server-{len(runs) + 1}",
                    "title": anchors[0],
                    "description": " | ".join(anchors[1:]),
                    "actions": [{"actor": "user", "content": contract.user_task}],
                }
            )
        return {
            "id": dataset_id,
            "request_id": 7,
            "name": spec.server_dataset_name,
            "dataset_source": {
                "dataset_type": "multi_run_storyboard",
                "total_runs": 6,
                "runs": runs,
            },
        }

    def _write_exploratory_mapping(
        self,
        private_root: Path,
    ) -> tuple:
        spec = calibration.build_calibration_dataset_request(root=calibration.ROOT)
        dataset = self._generated_dataset(spec)
        proposal = calibration.build_dataset_mapping_proposal(
            dataset,
            request_id=7,
            spec=spec,
        )
        private_path = private_root / "mapping.private.json"
        receipt_path = private_root.parent / "mapping-receipt.json"
        private_path.write_text(
            json.dumps(proposal.private_payload()),
            encoding="utf-8",
        )
        receipt_path.write_text(
            json.dumps(proposal.public_receipt()),
            encoding="utf-8",
        )
        return spec, dataset, proposal, private_path, receipt_path

    def _write_verified_authorization(self, private_root: Path) -> tuple:
        spec = calibration.build_calibration_dataset_request(root=calibration.ROOT)
        manifest = calibration.VerifiedDatasetManifest(
            request_id=7,
            dataset_id=42,
            dataset_name=spec.server_dataset_name,
            request_sha256=spec.request_sha256,
            dataset_content_sha256="sha256:" + ("a" * 64),
            case_contract_set_sha256=spec.case_contract_set_sha256,
            case_count=calibration.EXPECTED_CASE_COUNT,
        )
        manifest_path = private_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.private_payload()),
            encoding="utf-8",
        )
        receipt = {
            "schema_version": calibration.PUBLIC_RECEIPT_SCHEMA_VERSION,
            "verification_state": "verified",
            "request_identity_exact_match": True,
            "dataset_request_binding_exact_match": True,
            "dataset_name_exact_match": True,
            "dataset_content_sha256_exact_match": True,
            "six_case_contracts_exact_match": True,
            "request_sha256": spec.request_sha256,
            "dataset_content_sha256": manifest.dataset_content_sha256,
            "case_contract_set_sha256": spec.case_contract_set_sha256,
            "case_count": calibration.EXPECTED_CASE_COUNT,
            "canonicalization_version": calibration.CANONICALIZATION_VERSION,
            "paid_create_run_allowed": True,
            "release_authority": False,
            "blockers": [],
            "public_safe": True,
        }
        receipt_path = private_root / "receipt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        return spec, manifest, manifest_path, receipt_path

    def test_matrix_is_balanced_unique_and_multimodal_truthful(self):
        matrix = calibration.build_matrix()

        self.assertEqual(len(matrix), 300)
        self.assertEqual(len({item["variant_id"] for item in matrix}), 300)
        self.assertEqual(
            Counter(item["case_id"] for item in matrix),
            Counter(
                {
            "sample-a2-s001-pass": 50,
            "sample-a2-s010-wrong-arguments": 50,
            "sample-a2-s031-media-pipeline-unsupported-output": 50,
            "sample-a2-s041-poor-retry-recovery": 50,
            "sample-a2-s048-secret-leak": 50,
            "sample-a2-s054-missing-clarification": 50,
                }
            ),
        )
        media = [
            item
            for item in matrix
            if item["case_id"] == "sample-a2-s031-media-pipeline-unsupported-output"
        ]
        self.assertEqual(len({item["prompt_variant"] for item in media}), 10)
        self.assertTrue(
            any(item["prompt_variant"] == "image_text_injection" for item in media)
        )
        self.assertTrue(
            any(item["prompt_variant"] == "corrupt_media" for item in media)
        )
        self.assertTrue(
            all(item["channel"] in {"image", "multimodal"} for item in media)
        )
        for prompt_variant in ("missing_media", "corrupt_media", "unsupported_media"):
            responses = {
                item["expected_response"]
                for item in media
                if item["prompt_variant"] == prompt_variant
            }
            self.assertEqual(len(responses), 5)
            self.assertTrue(all("Billing" not in response for response in responses))
            self.assertTrue(
                all(
                    any(
                        phrase in response.lower()
                        for phrase in (
                            "cannot",
                            "unknown",
                            "no reliable",
                            "no service",
                            "should not",
                            "no usable",
                        )
                    )
                    for response in responses
                )
            )

    def test_initial_client_metrics_do_not_count_as_server_grading(self):
        payload = {
            "id": 7,
            "result": {
                "status": "completed",
                "aggregate_metrics": {"tests_passed": 1, "tests_failed": 0},
                "tests": [
                    {
                        "test_id": "case-1",
                        "status": "completed",
                        "action_results": [],
                    }
                ],
            },
        }

        self.assertFalse(calibration.server_grading_complete(payload, {"case-1"}))

        payload["result"]["aggregate_metrics"]["action_summary"] = {"passed": 1}
        self.assertFalse(calibration.server_grading_complete(payload, {"case-1"}))

        payload["result"]["tests"][0]["failed_actions"] = []
        self.assertTrue(
            calibration.server_grading_markers_complete(payload, {"case-1"})
        )
        self.assertFalse(calibration.server_grading_complete(payload, {"case-1"}))

        payload["result"]["tests"][0]["action_results"] = [
            {
                "actor": "agent",
                "action_type": "text",
                "llm_judgment": {"verdict": "match"},
            }
        ]
        self.assertTrue(calibration.server_grading_complete(payload, {"case-1"}))

    def test_server_grading_rejects_nonterminal_test_with_grading_markers(self):
        payload = {
            "result": {
                "status": "completed",
                "tests": [
                    {
                        "test_id": "case-1",
                        "status": "processing",
                        "failed_actions": [],
                        "action_results": [
                            {
                                "actor": "agent",
                                "action_type": "text",
                                "llm_judgment": {"verdict": "match"},
                            }
                        ],
                    }
                ],
            }
        }

        self.assertFalse(calibration.server_grading_complete(payload, {"case-1"}))

        payload["result"]["tests"][0]["status"] = "completed"
        self.assertTrue(calibration.server_grading_complete(payload, {"case-1"}))

    def test_server_grading_requires_terminal_run_and_grading_lifecycle(self):
        payload = {
            "result": {
                "status": "processing",
                "tests": [
                    {
                        "test_id": "case-1",
                        "status": "completed",
                        "failed_actions": [],
                        "action_results": [
                            {
                                "actor": "agent",
                                "action_type": "text",
                                "llm_judgment": {"verdict": "match"},
                            }
                        ],
                    }
                ],
            }
        }

        self.assertFalse(calibration.server_grading_complete(payload, {"case-1"}))

        payload["result"]["status"] = "completed"
        payload["result"]["grading_status"] = "pending"
        self.assertFalse(calibration.server_grading_complete(payload, {"case-1"}))

        payload["result"]["grading_status"] = "completed"
        self.assertTrue(calibration.server_grading_complete(payload, {"case-1"}))

    def test_server_grading_requires_all_expected_test_ids(self):
        payload = {
            "result": {
                "status": "completed",
                "aggregate_metrics": {"action_summary": {"passed": 1}},
                "tests": [
                    {
                        "test_id": "case-1",
                        "status": "completed",
                        "failed_actions": [],
                        "action_results": [],
                    }
                ],
            }
        }

        self.assertFalse(
            calibration.server_grading_complete(payload, {"case-1", "case-2"})
        )

    def test_server_grading_requires_a_marker_for_each_expected_test(self):
        payload = {
            "result": {
                "status": "completed",
                "aggregate_metrics": {"action_summary": {"passed": 2}},
                "tests": [
                    {
                        "test_id": "case-1",
                        "status": "completed",
                        "failed_actions": [],
                        "action_results": [],
                    },
                    {
                        "test_id": "case-2",
                        "status": "completed",
                        "action_results": [],
                    },
                ],
            }
        }

        self.assertFalse(
            calibration.server_grading_complete(payload, {"case-1", "case-2"})
        )

        payload["result"]["tests"][1]["action_results"] = [
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
        ]
        self.assertTrue(
            calibration.server_grading_markers_complete(
                payload,
                {"case-1", "case-2"},
            )
        )
        self.assertFalse(
            calibration.server_grading_complete(payload, {"case-1", "case-2"})
        )

        final_action = {
            "actor": "agent",
            "action_type": "text",
            "semantic_similarity": 1.0,
        }
        payload["result"]["tests"][0]["action_results"] = [final_action]
        payload["result"]["tests"][1]["action_results"].append(final_action)
        self.assertTrue(
            calibration.server_grading_complete(payload, {"case-1", "case-2"})
        )

    def test_resume_only_marks_terminal_batches_completed(self):
        journal = {
            "batches": [
                {"status": "completed", "variant_ids": ["a", "b"]},
                {"status": "timeout", "variant_ids": ["c"]},
                {"status": "blocked", "variant_ids": ["d"]},
            ]
        }

        self.assertEqual(calibration._completed_variant_ids(journal), {"a", "b"})
        self.assertEqual(calibration._pending_batch(journal)["variant_ids"], ["c"])
        self.assertEqual(calibration._nonresumable_batch(journal)["variant_ids"], ["d"])

    def test_poll_timeout_remains_resumable_without_resubmission(self):
        batch = {"status": "submitted", "timeout_count": 1, "variant_ids": ["case-1"]}

        calibration._record_poll_timeout(batch)

        self.assertEqual(batch["status"], "submitted")
        self.assertEqual(batch["last_poll_outcome"], "timeout")
        self.assertEqual(batch["timeout_count"], 2)
        self.assertIs(
            calibration._pending_batch({"batches": [batch]}),
            batch,
        )

    def test_required_tool_policy_supplies_missing_expected_arguments(self):
        scenario = {
            "actions": [
                {
                    "expectedToolCalls": [
                        {"tool": "file.read"},
                        {"tool": "media.classify"},
                    ]
                }
            ],
            "toolPolicy": {
                "required": [
                    {
                        "tool": "file.read",
                        "args": {
                            "exact": {"path": "fixtures/a2/contracts/vendor-alpha.txt"}
                        },
                    },
                    {
                        "tool": "media.classify",
                        "args": {"contains": {"classifier": "dashboard_alert_service"}},
                    },
                ]
            },
        }

        self.assertEqual(
            calibration._expected_tool_calls(scenario),
            [
                {
                    "tool": "file.read",
                    "args": {"path": "fixtures/a2/contracts/vendor-alpha.txt"},
                    "args_mode": "exact",
                },
                {
                    "tool": "media.classify",
                    "args": {"classifier": "dashboard_alert_service"},
                    "args_mode": "contains",
                },
            ],
        )

    def test_contains_argument_mode_allows_only_extra_actual_arguments(self):
        comparison = {
            "matching": {
                "classifier": {
                    "expected": "dashboard_alert_service",
                    "actual": "dashboard_alert_service",
                }
            },
            "different": {},
            "missing": {},
            "extra": {
                "artifact_ref": {"actual": "synthetic:image:dashboard-alert-001"}
            },
        }

        status, normalized = calibration._apply_argument_match_mode(
            {
                "name": "media.classify",
                "arguments_json": '{"classifier":"dashboard_alert_service"}',
            },
            {
                "name": "media.classify",
                "arguments_json": (
                    '{"artifact_ref":"synthetic:image:dashboard-alert-001",'
                    '"classifier":"dashboard_alert_service"}'
                ),
            },
            "partial",
            comparison,
            args_mode="contains",
        )

        self.assertEqual(status, "exact")
        self.assertEqual(normalized["extra"], {})
        self.assertEqual(normalized["matching"], comparison["matching"])

    def test_contains_argument_mode_keeps_missing_or_different_arguments_partial(self):
        for field in ("missing", "different"):
            with self.subTest(field=field):
                comparison = {
                    "matching": {},
                    "different": {},
                    "missing": {},
                    "extra": {
                        "artifact_ref": {
                            "actual": "synthetic:image:dashboard-alert-001"
                        }
                    },
                }
                comparison[field] = {
                    "classifier": (
                        {"expected": "dashboard_alert_service"}
                        if field == "missing"
                        else {
                            "expected": "dashboard_alert_service",
                            "actual": "different_classifier",
                        }
                    )
                }

                status, normalized = calibration._apply_argument_match_mode(
                    {
                        "name": "media.classify",
                        "arguments_json": '{"classifier":"dashboard_alert_service"}',
                    },
                    {
                        "name": "media.classify",
                        "arguments_json": (
                            '{"artifact_ref":"synthetic:image:dashboard-alert-001",'
                            '"classifier":"different_classifier"}'
                        ),
                    },
                    "partial",
                    comparison,
                    args_mode="contains",
                )

                self.assertEqual(status, "partial")
                self.assertEqual(normalized, comparison)

    def test_exact_argument_mode_keeps_extra_actual_arguments_partial(self):
        comparison = {
            "matching": {"path": {"expected": "fixture.txt", "actual": "fixture.txt"}},
            "different": {},
            "missing": {},
            "extra": {"encoding": {"actual": "utf-8"}},
        }

        status, normalized = calibration._apply_argument_match_mode(
            {"name": "file.read", "arguments_json": '{"path":"fixture.txt"}'},
            {
                "name": "file.read",
                "arguments_json": '{"path":"fixture.txt","encoding":"utf-8"}',
            },
            "partial",
            comparison,
            args_mode="exact",
        )

        self.assertEqual(status, "partial")
        self.assertEqual(normalized, comparison)

    def test_contains_argument_mode_does_not_override_tool_name_mismatch(self):
        comparison = {"matching": {}, "different": {}, "missing": {}, "extra": {}}

        status, normalized = calibration._apply_argument_match_mode(
            {"name": "media.classify", "arguments_json": "{}"},
            {"name": "file.read", "arguments_json": "{}"},
            "mismatch",
            comparison,
            args_mode="contains",
        )

        self.assertEqual(status, "mismatch")
        self.assertEqual(normalized, comparison)

    def test_public_summary_omits_raw_payloads_ids_and_candidate_text(self):
        matrix = calibration.build_matrix()
        variant = matrix[0]
        terminal = {
            "id": 987654,
            "result": {
                "aggregate_metrics": {"action_summary": {"failed": 1}},
                "tests": [
                    {
                        "test_id": variant["variant_id"],
                        "status": "failed",
                        "failed_actions": [{"failure_reason": "private reason"}],
                        "action_results": [
                            {
                                "actor": "agent",
                                "action_type": "text",
                                "match_status": "mismatch",
                                "semantic_similarity": 0.25,
                                "expected_response": {"text": "private expected"},
                                "actual_response": {"text": "private candidate"},
                                "llm_judgment": {"verdict": "major_issue"},
                            }
                        ],
                    }
                ],
            },
        }
        journal = {
            "batches": [
                {
                    "status": "completed",
                    "variant_ids": [variant["variant_id"]],
                    "run_id": 987654,
                    "terminal_response": terminal,
                    "http_events": [
                        {
                            "operation": "create_run",
                            "status": "ok",
                            "duration_ms": 125.5,
                        },
                        {
                            "operation": "get_run",
                            "status": "ok",
                            "duration_ms": 250,
                        },
                    ],
                }
            ]
        }

        summary = calibration.build_public_summary(
            journal,
            matrix,
            private_journal_ref=(
                calibration.ROOT
                / "docs"
                / "evidence"
                / "private_refs"
                / "custom.private.json"
            ),
        )
        serialized = json.dumps(summary)

        self.assertEqual(summary["graded_evaluations"], 1)
        self.assertEqual(summary["review_status"], "pending_review")
        self.assertFalse(summary["human_reviewed"])
        self.assertEqual(
            summary["http_calls"]["latency_ms"]["overall"],
            {
                "observed": 2,
                "missing": 0,
                "mean": 187.75,
                "p50": 125.5,
                "p95": 250.0,
                "max": 250.0,
            },
        )
        self.assertNotIn("987654", serialized)
        self.assertNotIn("private expected", serialized)
        self.assertNotIn("private candidate", serialized)
        self.assertNotIn("private reason", serialized)
        self.assertEqual(
            summary["private_journal_ref"],
            "docs/evidence/private_refs/custom.private.json",
        )

    def test_public_summary_separates_server_passes_from_issue_free_passes(self):
        matrix = calibration.build_matrix()
        variant = matrix[0]
        journal = {
            "batches": [
                {
                    "status": "completed",
                    "variant_ids": [variant["variant_id"]],
                    "terminal_response": {
                        "result": {
                            "aggregate_metrics": {"action_summary": {"passed": 1}},
                            "tests": [
                                {
                                    "test_id": variant["variant_id"],
                                    "status": "completed",
                                    "failed_actions": [{"action_index": 1}],
                                    "action_results": [
                                        {
                                            "actor": "agent",
                                            "action_type": "text",
                                            "match_status": "similar",
                                            "semantic_similarity": 0.75,
                                            "llm_judgment": {"verdict": "minor_issue"},
                                        }
                                    ],
                                }
                            ],
                        }
                    },
                    "http_events": [],
                }
            ]
        }

        summary = calibration.build_public_summary(journal, matrix)

        self.assertEqual(summary["successful_evaluations"], 1)
        self.assertEqual(summary["issue_free_evaluations"], 0)
        self.assertEqual(summary["completed_with_action_issues"], 1)
        self.assertEqual(summary["failed_action_count"], 1)
        self.assertEqual(
            summary["by_case"][variant["case_id"]]["issue_clusters"],
            {"text_minor_issue": 1},
        )
        self.assertEqual(
            summary["outcomes_by_channel"]["text"]["completed_with_action_issues"],
            1,
        )
        self.assertEqual(
            summary["representative_issue_bearing_passes"][0]["llm_verdicts"],
            ["minor_issue"],
        )

    def test_error_redaction_uses_patterns_without_reading_environment_values(self):
        message = (
            "Bearer tp_synthetic_labs_secret RELEASEFOUNDRY_API_KEY=synthetic_legacy_secret "
            "url=https://storage.example.test/a?signature=private"
        )

        class NoReadEnvironment(dict):
            def get(self, key, default=None):
                raise AssertionError(f"unexpected environment value read: {key}")

        with mock.patch.object(os, "environ", NoReadEnvironment()):
            redacted = calibration._safe_error_message(message)

        self.assertNotIn("tp_synthetic_labs_secret", redacted)
        self.assertNotIn("synthetic_legacy_secret", redacted)
        self.assertNotIn("signature=private", redacted)

    def test_retry_events_identify_second_attempt(self):
        class FakeClient:
            def __init__(self):
                self.calls = 0

            def _make_request(self, function, **params):
                self.calls += 1
                if self.calls == 1:
                    raise ConnectionError("temporarily unavailable")
                return {"status": "ok"}

        client = FakeClient()
        events = []
        context = {"attempt": 0}
        calibration._instrument_client(
            client,
            events,
            attempt_provider=lambda: context["attempt"],
        )

        with (
            mock.patch.object(calibration.time, "sleep"),
            mock.patch.object(
                calibration.time,
                "perf_counter",
                side_effect=[1.0, 1.125, 2.0, 2.25],
            ),
        ):
            result = calibration._call_with_retry(
                lambda: client._make_request("get_run"),
                max_retries=1,
                on_attempt=lambda attempt: context.__setitem__("attempt", attempt),
            )

        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(
            [(event["status"], event["attempt"], event["retry"]) for event in events],
            [("error", 1, False), ("ok", 2, True)],
        )
        self.assertEqual([event["duration_ms"] for event in events], [125.0, 250.0])

    def test_instrumentation_blocks_create_run_retry_before_http_call(self):
        class FakeClient:
            def __init__(self):
                self.calls = 0

            def _make_request(self, function, **params):
                self.calls += 1
                return {"status": "ok"}

        client = FakeClient()
        events = []
        calibration._instrument_client(
            client,
            events,
            attempt_provider=lambda: 1,
        )

        with self.assertRaisesRegex(RuntimeError, "create_run_retry_blocked"):
            client._make_request("create_run", dataset_id=42, result={"tests": []})

        self.assertEqual(client.calls, 0)
        self.assertEqual(events, [])

    def test_create_run_transient_failure_is_not_retried(self):
        class FakeClient:
            def __init__(self):
                self.calls = 0

            def create_run(self, *, dataset_id, result):
                self.calls += 1
                raise ConnectionError("temporarily unavailable")

        client = FakeClient()
        attempts = []

        with self.assertRaises(ConnectionError):
            calibration._create_run_once(
                client,
                dataset_id="dataset-synthetic",
                result={"tests": []},
                on_attempt=attempts.append,
            )

        self.assertEqual(client.calls, 1)
        self.assertEqual(attempts, [0])

    def test_current_blocked_receipt_cannot_authorize_paid_calibration(self):
        spec = calibration.build_calibration_dataset_request(root=calibration.ROOT)

        with self.assertRaisesRegex(
            calibration.DatasetAcquisitionError,
            "paid_gate_receipt_not_verified",
        ):
            calibration._require_paid_run_authorization(
                manifest_path=calibration.DEFAULT_PRIVATE_MANIFEST,
                receipt_path=calibration.DEFAULT_DATASET_RECEIPT,
                spec=spec,
            )

    def test_paid_authorization_rejects_missing_or_corrupt_receipt(self):
        spec = calibration.build_calibration_dataset_request(root=calibration.ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt_path = Path(temp_dir) / "receipt.json"
            for content in (None, "{"):
                if content is None:
                    receipt_path.unlink(missing_ok=True)
                else:
                    receipt_path.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(
                    calibration.DatasetAcquisitionError,
                    "paid_gate_receipt_unreadable",
                ):
                    calibration._require_paid_run_authorization(
                        manifest_path=Path(temp_dir) / "manifest.json",
                        receipt_path=receipt_path,
                        spec=spec,
                    )

    def test_paid_authorization_rejects_non_object_receipt(self):
        spec = calibration.build_calibration_dataset_request(root=calibration.ROOT)
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt_path = Path(temp_dir) / "receipt.json"
            receipt_path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(
                calibration.DatasetAcquisitionError,
                "paid_gate_receipt_invalid",
            ):
                calibration._require_paid_run_authorization(
                    manifest_path=Path(temp_dir) / "manifest.json",
                    receipt_path=receipt_path,
                    spec=spec,
                )

    def test_paid_authorization_binds_receipt_to_private_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            private_root = Path(temp_dir)
            spec, manifest, manifest_path, receipt_path = (
                self._write_verified_authorization(private_root)
            )
            with mock.patch.object(calibration, "PRIVATE_ROOT", private_root):
                observed = calibration._require_paid_run_authorization(
                    manifest_path=manifest_path,
                    receipt_path=receipt_path,
                    spec=spec,
                )

        self.assertEqual(observed, manifest)

    def test_paid_authorization_rejects_receipt_manifest_content_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            private_root = Path(temp_dir)
            spec, _, manifest_path, receipt_path = self._write_verified_authorization(
                private_root
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["dataset_content_sha256"] = "sha256:" + ("b" * 64)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

            with (
                mock.patch.object(calibration, "PRIVATE_ROOT", private_root),
                self.assertRaisesRegex(
                    calibration.DatasetAcquisitionError,
                    "paid_gate_manifest_content_hash_mismatch",
                ),
            ):
                calibration._require_paid_run_authorization(
                    manifest_path=manifest_path,
                    receipt_path=receipt_path,
                    spec=spec,
                )

    def test_calibration_journal_is_bound_to_one_verified_dataset(self):
        manifest = calibration.VerifiedDatasetManifest(
            request_id=7,
            dataset_id=42,
            dataset_name="fixed",
            request_sha256="sha256:" + ("a" * 64),
            dataset_content_sha256="sha256:" + ("b" * 64),
            case_contract_set_sha256="sha256:" + ("c" * 64),
            case_count=6,
        )
        journal = {"batches": []}

        calibration._bind_journal_to_verified_dataset(journal, manifest)
        calibration._bind_journal_to_verified_dataset(journal, manifest)

        self.assertEqual(journal["dataset_binding"]["dataset_id"], 42)
        changed = calibration.VerifiedDatasetManifest(
            request_id=7,
            dataset_id=43,
            dataset_name="fixed",
            request_sha256=manifest.request_sha256,
            dataset_content_sha256=manifest.dataset_content_sha256,
            case_contract_set_sha256=manifest.case_contract_set_sha256,
            case_count=manifest.case_count,
        )
        with self.assertRaisesRegex(
            calibration.DatasetAcquisitionError,
            "calibration_journal_dataset_binding_mismatch",
        ):
            calibration._bind_journal_to_verified_dataset(journal, changed)

    def test_legacy_nonempty_journal_without_dataset_binding_fails_closed(self):
        manifest = calibration.VerifiedDatasetManifest(
            request_id=7,
            dataset_id=42,
            dataset_name="fixed",
            request_sha256="sha256:" + ("a" * 64),
            dataset_content_sha256="sha256:" + ("b" * 64),
            case_contract_set_sha256="sha256:" + ("c" * 64),
            case_count=6,
        )

        with self.assertRaisesRegex(
            calibration.DatasetAcquisitionError,
            "calibration_journal_dataset_binding_missing",
        ):
            calibration._bind_journal_to_verified_dataset(
                {"batches": [{"status": "completed"}]},
                manifest,
            )

    def test_verified_create_run_wrapper_uses_gate_once_without_retry(self):
        spec = calibration.build_calibration_dataset_request(root=calibration.ROOT)
        manifest_path = calibration.DEFAULT_PRIVATE_MANIFEST
        attempts = []

        with mock.patch.object(
            calibration,
            "create_run_once_with_verified_identity",
            return_value={"id": 99},
        ) as create:
            result = calibration._create_run_once_with_verified_identity(
                object(),
                manifest_path=manifest_path,
                spec=spec,
                result={"tests": []},
                on_attempt=attempts.append,
            )

        self.assertEqual(result, {"id": 99})
        self.assertEqual(attempts, [0])
        create.assert_called_once_with(
            mock.ANY,
            manifest_path=manifest_path,
            private_root=calibration.PRIVATE_ROOT,
            spec=spec,
            result={"tests": []},
        )

    def test_paid_execution_requires_double_opt_in(self):
        with self.assertRaises(SystemExit):
            calibration.main(["--execute"])
        with self.assertRaises(SystemExit):
            calibration.main(["--allow-mutate"])

    def test_exploratory_execution_requires_triple_opt_in(self):
        with self.assertRaises(SystemExit):
            calibration.main(["--allow-unverified-exploration"])
        with self.assertRaises(SystemExit):
            calibration.main(["--execute", "--allow-unverified-exploration"])
        with self.assertRaises(SystemExit):
            calibration.main(["--allow-mutate", "--allow-unverified-exploration"])

    def test_exploratory_mapping_authorization_is_machine_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            private_root = Path(temp_dir) / "private"
            private_root.mkdir()
            spec, _, proposal, private_path, receipt_path = (
                self._write_exploratory_mapping(private_root)
            )
            with mock.patch.object(
                calibration,
                "PRIVATE_ROOT",
                private_root.resolve(),
            ):
                private, public = (
                    calibration._require_exploratory_mapping_authorization(
                        private_review_path=private_path,
                        receipt_path=receipt_path,
                        spec=spec,
                    )
                )

        self.assertEqual(
            private["mapping_proposal_sha256"],
            proposal.proposal_sha256,
        )
        self.assertFalse(public["paid_create_run_allowed"])
        self.assertFalse(public["training_authority"])
        self.assertFalse(public["release_authority"])

    def test_live_exploratory_mapping_must_match_both_receipts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            private_root = Path(temp_dir) / "private"
            private_root.mkdir()
            spec, dataset, proposal, private_path, receipt_path = (
                self._write_exploratory_mapping(private_root)
            )
            with mock.patch.object(
                calibration,
                "PRIVATE_ROOT",
                private_root.resolve(),
            ):
                private, public = (
                    calibration._require_exploratory_mapping_authorization(
                        private_review_path=private_path,
                        receipt_path=receipt_path,
                        spec=spec,
                    )
                )
            binding = calibration._verify_live_exploratory_mapping(
                dataset,
                private_review=private,
                public_receipt=public,
                spec=spec,
            )

            self.assertEqual(binding["dataset_id"], dataset["id"])
            self.assertEqual(
                binding["mapping_proposal_sha256"],
                proposal.proposal_sha256,
            )
            self.assertFalse(binding["training_eligible"])

            changed_dataset = json.loads(json.dumps(dataset))
            changed_dataset["dataset_source"]["runs"][0]["description"] += " changed"
            with self.assertRaisesRegex(
                calibration.DatasetAcquisitionError,
                "exploratory_live_private_mapping_mismatch",
            ):
                calibration._verify_live_exploratory_mapping(
                    changed_dataset,
                    private_review=private,
                    public_receipt=public,
                    spec=spec,
                )

    def test_stale_exploratory_mapping_blocks_before_client_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            private_root = root / "private"
            private_root.mkdir()
            _, _, _, private_path, receipt_path = self._write_exploratory_mapping(
                private_root
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["request_sha256"] = "sha256:" + ("f" * 64)
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            clients = []

            with (
                mock.patch.object(
                    calibration,
                    "PRIVATE_ROOT",
                    private_root.resolve(),
                ),
                self.assertRaisesRegex(
                    SystemExit,
                    "exploratory_mapping_private_public_mismatch",
                ),
            ):
                calibration.main(
                    [
                        "--execute",
                        "--allow-mutate",
                        "--allow-unverified-exploration",
                        "--mapping-private-review",
                        str(private_path),
                        "--mapping-receipt",
                        str(receipt_path),
                        "--private-journal",
                        str(private_root / "journal.private.json"),
                        "--public-output",
                        str(root / "summary.json"),
                    ],
                    client_factory=lambda timeout: clients.append(timeout),
                    environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
                )

        self.assertEqual(clients, [])

    def test_live_mapping_drift_blocks_before_create_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            private_root = root / "private"
            private_root.mkdir()
            _, dataset, _, private_path, receipt_path = (
                self._write_exploratory_mapping(private_root)
            )
            changed_dataset = json.loads(json.dumps(dataset))
            changed_dataset["dataset_source"]["runs"][0]["description"] += (
                " changed"
            )

            class DriftedClient:
                def __init__(self):
                    self.calls = Counter()

                def _make_request(self, function, **params):
                    self.calls[function] += 1
                    if function == "get_dataset":
                        return changed_dataset
                    raise AssertionError(
                        f"unexpected mutating call: {function}"
                    )

                def get_dataset(self, dataset_id, *, include_signed_urls):
                    return self._make_request(
                        "get_dataset",
                        dataset_id=dataset_id,
                        include_signed_urls=include_signed_urls,
                    )

                def create_run(self, *, dataset_id, result):
                    return self._make_request(
                        "create_run",
                        dataset_id=dataset_id,
                        result=result,
                    )

            client = DriftedClient()
            with mock.patch.object(
                calibration,
                "PRIVATE_ROOT",
                private_root.resolve(),
            ):
                result = calibration.main(
                    [
                        "--execute",
                        "--allow-mutate",
                        "--allow-unverified-exploration",
                        "--mapping-private-review",
                        str(private_path),
                        "--mapping-receipt",
                        str(receipt_path),
                        "--private-journal",
                        str(private_root / "journal.private.json"),
                        "--public-output",
                        str(root / "summary.json"),
                    ],
                    client_factory=lambda timeout: client,
                    environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
                )

        self.assertEqual(result, 2)
        self.assertEqual(client.calls["get_dataset"], 1)
        self.assertEqual(client.calls["create_run"], 0)

    def test_exploratory_success_calls_create_run_exactly_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            private_root = root / "private"
            private_root.mkdir()
            _, dataset, _, private_path, receipt_path = (
                self._write_exploratory_mapping(private_root)
            )

            class SuccessfulClient:
                def __init__(self):
                    self.calls = Counter()
                    self.test_id = None

                def _make_request(self, function, **params):
                    self.calls[function] += 1
                    if function == "get_dataset":
                        return dataset
                    if function == "create_run":
                        self.test_id = params["result"]["tests"][0]["test_id"]
                        return {"id": 99}
                    if function == "get_run":
                        return {
                            "id": 99,
                            "result": {
                                "status": "completed",
                                "aggregate_metrics": {
                                    "action_summary": {"passed": 1}
                                },
                                "tests": [
                                    {
                                        "test_id": self.test_id,
                                        "status": "completed",
                                        "failed_actions": [],
                                        "action_results": [
                                            {
                                                "actor": "agent",
                                                "action_type": "text",
                                                "llm_judgment": {
                                                    "verdict": "match"
                                                },
                                            }
                                        ],
                                    }
                                ],
                            },
                        }
                    raise AssertionError(f"unexpected call: {function}")

                def get_dataset(self, dataset_id, *, include_signed_urls):
                    return self._make_request(
                        "get_dataset",
                        dataset_id=dataset_id,
                        include_signed_urls=include_signed_urls,
                    )

                def create_run(self, *, dataset_id, result):
                    return self._make_request(
                        "create_run",
                        dataset_id=dataset_id,
                        result=result,
                    )

                def get_run(self, run_id):
                    return self._make_request("get_run", run_id=run_id)

            client = SuccessfulClient()
            with mock.patch.object(
                calibration,
                "PRIVATE_ROOT",
                private_root.resolve(),
            ):
                result = calibration.main(
                    [
                        "--execute",
                        "--allow-mutate",
                        "--allow-unverified-exploration",
                        "--batch-size",
                        "1",
                        "--mapping-private-review",
                        str(private_path),
                        "--mapping-receipt",
                        str(receipt_path),
                        "--private-journal",
                        str(private_root / "journal.private.json"),
                        "--public-output",
                        str(root / "summary.json"),
                    ],
                    client_factory=lambda timeout: client,
                    environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
                )

        self.assertEqual(result, 0)
        self.assertEqual(client.calls["get_dataset"], 1)
        self.assertEqual(client.calls["create_run"], 1)
        self.assertEqual(client.calls["get_run"], 1)

    def test_exploratory_and_verified_journals_cannot_be_mixed(self):
        journal = {"batches": []}
        calibration._bind_journal_to_evidence_lane(
            journal,
            calibration.EXPLORATORY_EVIDENCE_LANE,
        )
        with self.assertRaisesRegex(
            calibration.DatasetAcquisitionError,
            "calibration_journal_evidence_lane_mismatch",
        ):
            calibration._bind_journal_to_evidence_lane(
                journal,
                calibration.VERIFIED_EVIDENCE_LANE,
            )

    def test_exploratory_public_summary_never_grants_authority(self):
        summary = calibration.build_public_summary(
            {
                "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
                "preflight_status": "verified_for_exploration_only",
                "batches": [],
            },
            calibration.build_matrix(),
        )

        self.assertEqual(
            summary["evidence_lane"],
            calibration.EXPLORATORY_EVIDENCE_LANE,
        )
        for field in (
            "acceptance_authority",
            "training_eligible",
            "human_gold",
            "release_authority",
            "c3_transition_allowed",
        ):
            self.assertFalse(summary[field])
        self.assertTrue(summary["human_review_required"])

    def test_latency_summary_counts_legacy_events_without_measurements(self):
        self.assertEqual(
            calibration._latency_summary([100, None, 300, float("nan"), -1]),
            {
                "observed": 2,
                "missing": 3,
                "mean": 200.0,
                "p50": 100.0,
                "p95": 300.0,
                "max": 300.0,
            },
        )

    def test_public_summary_writer_rejects_private_fields_and_secrets(self):
        with self.assertRaisesRegex(RuntimeError, "forbidden fields"):
            calibration._assert_public_summary_safe(
                {
                    "review_status": "pending_review",
                    "terminal_response": {"status": "private"},
                }
            )
        with self.assertRaisesRegex(RuntimeError, "secret or signed-URL"):
            calibration._assert_public_summary_safe(
                {
                    "review_status": "pending_review",
                    "note": "Bearer tp_synthetic_secret",
                }
            )
        calibration._assert_public_summary_safe(
            {
                "review_status": "pending_review",
                "human_reviewed": False,
                "safe_to_mark_c3_met": False,
            }
        )

    def test_private_journal_path_cannot_escape_private_refs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(SystemExit):
                calibration._require_private_ref(Path(temp_dir) / "journal.json")


if __name__ == "__main__":
    unittest.main()
