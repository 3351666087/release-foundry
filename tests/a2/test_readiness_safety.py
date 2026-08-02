import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from services.judge.releasefoundry_test_receipts import (
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_scoring_summary,
    public_releasefoundry_test_terminal_receipt,
)
from services.judge.evidence_readiness import build_evidence_readiness_report
from services.judge.readiness import build_commercial_readiness_report
from services.judge.result_persistence import stable_hash


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "fixtures/a2/results"


class CommercialReadinessSafetyTests(unittest.TestCase):
    def test_authoritative_boolean_strings_cannot_mark_gates_met(self):
        c0_inputs = self._inputs()
        c0_inputs["coverage"]["meets_assignment_minimums"] = "false"

        c1_inputs = self._inputs()
        c1_inputs["sdk"]["parity_passed"] = "false"

        c2_inputs = self._inputs()
        c2_inputs["batch"]["plan_ready"] = "false"

        c3_inputs = self._inputs()
        self._make_c3_eligible(c3_inputs)
        c3_inputs["evidence"]["releasefoundry_public_merge_gate"]["safe_to_mark_c3_met"] = "false"

        c4_inputs = self._inputs()
        self._make_c4_eligible(c4_inputs)
        c4_inputs["semantic"]["live_model_evidence_available"] = "false"
        c4_inputs["evidence"]["semantic_live_merge_gate"]["safe_to_mark_c4_met"] = "false"

        c5_inputs = self._inputs()
        c5_inputs["replay"]["maturity_status"] = "mature"
        c5_inputs["replay"]["replay_ready"] = "false"

        for gate_name, candidate in (
            ("C0", c0_inputs),
            ("C1", c1_inputs),
            ("C2", c2_inputs),
            ("C3", c3_inputs),
            ("C4", c4_inputs),
            ("C5", c5_inputs),
        ):
            with self.subTest(gate=gate_name):
                gate = self._gates(self._build(candidate))[gate_name]
                self.assertNotEqual(gate["status"], "met")

        c4_snapshot = self._build(c4_inputs)["evidence_snapshot"]
        self.assertFalse(c4_snapshot["semantic_harness_live_evidence"])
        self.assertFalse(c4_snapshot["semantic_safe_to_mark_c4_met"])

    def test_c3_rejects_string_coverage_ratio(self):
        inputs = self._inputs()
        self._make_c3_eligible(inputs)
        inputs["calibration"]["source_coverage"]["releasefoundry_grading"]["coverage_ratio"] = "1.0"

        report = self._build(inputs)

        self.assertNotEqual(self._gates(report)["C3"]["status"], "met")
        self.assertEqual(report["evidence_snapshot"]["releasefoundry_grading_available"], 6)

    def test_c4_rejects_boolean_confidence(self):
        inputs = self._inputs()
        self._make_c4_eligible(inputs)
        inputs["calibration"]["cases"][0]["sources"]["llm_judge"]["confidence"] = True

        report = self._build(inputs)

        self.assertNotEqual(self._gates(report)["C4"]["status"], "met")

    def test_c4_rejects_string_sample_count(self):
        inputs = self._inputs()
        self._make_c4_eligible(inputs)
        llm_cost = next(
            row
            for row in inputs["calibration"]["cost_ledger"]
            if row["source"] == "llm_judge"
        )
        llm_cost["sample_count"] = "6"

        report = self._build(inputs)

        self.assertNotEqual(self._gates(report)["C4"]["status"], "met")

    def test_c2_rejects_truthy_non_list_cost_ledger(self):
        inputs = self._inputs()
        inputs["calibration"]["cost_ledger"] = "present"

        report = self._build(inputs)

        self.assertNotEqual(self._gates(report)["C2"]["status"], "met")

    def test_malformed_counts_fail_closed_without_crashing(self):
        malformed_values = (True, False, 1.5, -1, "6", "invalid", {}, [], None)

        for value in malformed_values:
            with self.subTest(value=value):
                inputs = self._inputs()
                inputs["case_book"]["regression_case_count"] = value
                inputs["sdk"]["sdk_language_count"] = value
                inputs["batch"]["batch_count"] = value
                inputs["replay"]["replay_case_count"] = value
                inputs["evidence"]["releasefoundry_public_merge_gate"][
                    "missing_public_observation_count"
                ] = value
                inputs["evidence"]["semantic_live_merge_gate"][
                    "missing_audited_observation_count"
                ] = value
                inputs["evidence"]["a1_real_api_evidence"]["real_record_count"] = value

                snapshot = self._build(inputs)["evidence_snapshot"]

                self.assertEqual(snapshot["case_book_regression_count"], 0)
                self.assertEqual(snapshot["sdk_language_count"], 0)
                self.assertEqual(snapshot["planned_batch_count"], 0)
                self.assertEqual(snapshot["regression_replay_count"], 0)
                self.assertEqual(snapshot["releasefoundry_public_missing_observations"], 6)
                self.assertEqual(snapshot["semantic_missing_audited_observations"], 0)
                self.assertEqual(snapshot["real_api_record_count"], 0)

    def test_tampered_or_wrong_source_evidence_cannot_mark_c3_or_c4_met(self):
        inputs = self._inputs()
        self._make_c3_eligible(inputs)
        self._make_c4_eligible(inputs)

        report = self._build(inputs)

        self.assertFalse(
            report["evidence_snapshot"]["evidence_readiness_integrity_verified"]
        )
        self.assertFalse(report["evidence_snapshot"]["releasefoundry_safe_to_mark_c3_met"])
        self.assertFalse(report["evidence_snapshot"]["semantic_safe_to_mark_c4_met"])
        self.assertNotEqual(self._gates(report)["C3"]["status"], "met")
        self.assertNotEqual(self._gates(report)["C4"]["status"], "met")

    def test_resealed_replay_claims_cannot_mark_c5_met(self):
        inputs = self._inputs()
        inputs["replay"]["replay_ready"] = True
        inputs["replay"]["maturity_status"] = "mature"
        inputs["replay"]["maturity_gate"]["ready"] = True
        replay_core = {
            key: value
            for key, value in inputs["replay"].items()
            if key != "artifact_hash"
        }
        inputs["replay"]["artifact_hash"] = stable_hash(replay_core)

        report = self._build(inputs)
        c5 = self._gates(report)["C5"]

        self.assertEqual(c5["status"], "partial")
        self.assertFalse(
            report["evidence_snapshot"]["regression_replay_integrity_verified"]
        )
        self.assertFalse(report["evidence_snapshot"]["regression_replay_ready"])
        self.assertEqual(
            report["evidence_snapshot"]["regression_replay_maturity"],
            "invalid",
        )
        self.assertIn(
            "Rebuild regression replay from the current calibration matrix and case book before using it for C5.",
            c5["gaps"],
        )

    def test_freshly_built_evidence_can_authorize_eligible_c3_and_c4(self):
        inputs = self._inputs()
        self._make_c3_eligible(inputs)
        self._make_c4_eligible(inputs)
        case_map = {
            f"releasefoundry-{case['case_id']}": case["case_id"]
            for case in inputs["calibration"]["cases"]
        }
        tests = [
            {
                "test_id": raw_case_id,
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
            for raw_case_id in case_map
        ]
        private_run_receipt = build_releasefoundry_test_terminal_receipt(
            {
                "id": "synthetic-run",
                "dataset": 7,
                "result": {
                    "status": "completed",
                    "judge_version": "releasefoundry-grader-v1",
                    "tests": tests,
                },
            },
            case_map=case_map,
            expected_dataset_id=7,
        )
        public_run_receipt = public_releasefoundry_test_terminal_receipt(
            private_run_receipt
        )
        run_metadata = {
            "dataset_identity_receipt_schema_version": (
                "a2.releasefoundry_dataset_identity_receipt.v1"
            ),
            "dataset_identity_verified": True,
            "dataset_identity_receipt_sha256": "sha256:" + ("b" * 64),
            "dataset_identity_manifest_sha256": "sha256:" + ("c" * 64),
            "dataset_identity_content_sha256": "sha256:" + ("d" * 64),
            "dataset_identity_content_collection": "runs",
            "dataset_identity_content_item_count": len(case_map),
            "dataset_identity_blockers": [],
            "run_terminal_receipt_schema_version": public_run_receipt[
                "schema_version"
            ],
            "run_terminal_receipt_sha256": stable_hash(public_run_receipt),
            "run_expected_test_count": public_run_receipt[
                "expected_test_count"
            ],
            "run_verified_test_count": public_run_receipt[
                "verified_test_count"
            ],
            "run_receipt_complete": public_run_receipt["receipt_complete"],
            "run_dataset_id_verified": public_run_receipt[
                "run_dataset_id_verified"
            ],
            "run_result_terminal_verified": public_run_receipt[
                "run_result_terminal_verified"
            ],
            "server_grading_lifecycle_verified": public_run_receipt[
                "server_grading_lifecycle_verified"
            ],
            "exact_test_set_verified": public_run_receipt[
                "exact_test_set_verified"
            ],
            "all_expected_tests_terminal_scoring_verified": (
                public_run_receipt[
                    "all_expected_tests_terminal_scoring_verified"
                ]
            ),
            "observed_judge_version": public_run_receipt[
                "observed_judge_version"
            ],
            "judge_version_source": public_run_receipt[
                "judge_version_source"
            ],
            "judge_version_verified": public_run_receipt[
                "judge_version_verified"
            ],
            "aggregate_marker_used_as_acceptance_authority": (
                public_run_receipt[
                    "aggregate_marker_used_as_acceptance_authority"
                ]
            ),
            "run_terminal_receipt_blockers": public_run_receipt["blockers"],
        }
        test_receipts = {
            receipt["case_id"]: receipt
            for receipt in private_run_receipt["tests"]
        }
        for case in inputs["calibration"]["cases"]:
            case_id = case["case_id"]
            terminal_summary = public_releasefoundry_test_scoring_summary(
                test_receipts[case_id]
            )
            terminal_summary.update(
                {
                    "response_evidence_count": test_receipts[case_id][
                        "response_evidence_count"
                    ],
                    "response_evidence_kinds": test_receipts[case_id][
                        "response_evidence_kinds"
                    ],
                    "grading_signal_count": test_receipts[case_id][
                        "grading_signal_count"
                    ],
                }
            )
            source = case["sources"]["releasefoundry_grading"]
            source.update(
                {
                    "available": True,
                    "evidence_ref": (
                        "docs/evidence/private_refs/"
                        "a2_releasefoundry_grading_import.review.json"
                    ),
                    "metadata": {
                        "review_status": "reviewed",
                        "reviewer_receipt": "sha256:" + "a" * 64,
                        "reviewed_at_unix_ms": 1,
                        **terminal_summary,
                        **run_metadata,
                    },
                }
            )
        inputs["calibration"][
            "releasefoundry_run_terminal_receipt"
        ] = public_run_receipt
        inputs["semantic"]["reviewed_live_observation_count"] = len(
            inputs["calibration"]["cases"]
        )
        inputs["semantic"]["missing_reviewed_live_observation_count"] = 0
        inputs["evidence"] = build_evidence_readiness_report(
            inputs["calibration"],
            inputs["batch"],
            inputs["semantic"],
        )

        report = self._build(inputs)

        self.assertTrue(
            report["evidence_snapshot"]["evidence_readiness_integrity_verified"]
        )
        self.assertEqual(self._gates(report)["C3"]["status"], "met")
        self.assertEqual(self._gates(report)["C4"]["status"], "met")

    def test_valid_committed_inputs_keep_current_gate_statuses(self):
        report = self._build(self._inputs())
        statuses = {
            gate["gate"]: gate["status"]
            for gate in report["gate_status"]
        }

        self.assertEqual(
            statuses,
            {
                "C0": "met",
                "C1": "met",
                "C2": "met",
                "C3": "partial",
                "C4": "partial",
                "C5": "partial",
                "C6": "partial",
            },
        )
        self.assertFalse(report["ready_for_commercial_gate"])
        self.assertTrue(
            report["evidence_snapshot"]["regression_replay_integrity_verified"]
        )

    @staticmethod
    def _make_c3_eligible(inputs: dict) -> None:
        source = inputs["calibration"]["source_coverage"]["releasefoundry_grading"]
        source.update({"available": 6, "missing": 0, "coverage_ratio": 1.0})
        gate = inputs["evidence"]["releasefoundry_public_merge_gate"]
        gate.update(
            {
                "status": "merged",
                "public_matrix_merged": True,
                "safe_to_mark_c3_met": True,
                "missing_public_observation_count": 0,
            }
        )

    @staticmethod
    def _make_c4_eligible(inputs: dict) -> None:
        cases = inputs["calibration"]["cases"]
        packet = json.loads(
            (
                ROOT
                / "fixtures/a2/calibration/"
                "a2_semantic_judge_collection_packet.json"
            ).read_text(encoding="utf-8")
        )
        packet_cases = {
            str(case["case_id"]): case for case in packet.get("cases", [])
        }
        inputs["calibration"]["source_coverage"]["llm_judge"].update(
            {
                "available": len(cases),
                "missing": 0,
                "coverage_ratio": 1.0,
            }
        )
        for index, case in enumerate(cases):
            case_id = case["case_id"]
            packet_case = packet_cases[case_id]
            case["sources"]["llm_judge"].update(
                {
                    "available": True,
                    "status": "available",
                    "provider": "audited_live_model",
                    "model": "semantic-judge-reviewed-v1",
                    "evidence_ref": (
                        "docs/evidence/private_refs/"
                        "a2_semantic_judge_import.review.json"
                        f"#{case_id}"
                    ),
                    "metadata": {
                        "prompt_template_id": (
                            "a2_semantic_judge_prompt_v1"
                        ),
                        "prompt_hash": (
                            "sha256:"
                            + hashlib.sha256(
                                f"prompt:{case_id}:{index}".encode()
                            ).hexdigest()
                        ),
                        "response_hash": (
                            "sha256:"
                            + hashlib.sha256(
                                f"response:{case_id}:{index}".encode()
                            ).hexdigest()
                        ),
                        "review_status": "reviewed",
                        "reviewer_receipt": "sha256:" + ("a" * 64),
                        "reviewed_at_unix_ms": 1,
                        "sdk_language": packet_case["sdk_language"],
                        "semantic_collection_packet_schema_version": packet[
                            "schema_version"
                        ],
                        "semantic_collection_packet_id": packet["packet_id"],
                        "semantic_collection_packet_sha256": packet[
                            "artifact_hash"
                        ],
                        "semantic_collection_dataset_id": packet["dataset_id"],
                        "semantic_collection_case_count": packet["case_count"],
                        "semantic_collection_target_observation_count": packet[
                            "target_observation_count"
                        ],
                        "semantic_collection_case_id": case_id,
                        "semantic_collection_case_sdk_language": packet_case[
                            "sdk_language"
                        ],
                        "semantic_collection_case_prompt_template_id": (
                            packet_case["prompt_template_id"]
                        ),
                        "semantic_collection_case_prompt_material_sha256": (
                            packet_case["prompt_material_sha256"]
                        ),
                    },
                }
            )
        review_receipt = {
            "schema_version": "a2.semantic_human_review_receipt.v1",
            "verification_state": "verified",
            "review_scope": "a2_c4_semantic_judge_acceptance",
            "expected_case_count": len(cases),
            "reviewed_case_count": len(cases),
            "receipt_complete": True,
            "public_safe": True,
            "raw_review_notes_included": False,
            "raw_reviewer_identity_included": False,
            "cases": [],
        }
        for case in cases:
            source = case["sources"]["llm_judge"]
            metadata = source["metadata"]
            review_receipt["cases"].append(
                {
                    "case_id": case["case_id"],
                    "scenario_id": case["scenario_id"],
                    "review_status": metadata["review_status"],
                    "reviewer_receipt": metadata["reviewer_receipt"],
                    "reviewed_at_unix_ms": metadata[
                        "reviewed_at_unix_ms"
                    ],
                    "provider": source["provider"],
                    "model": source["model"],
                    "passed": source["passed"],
                    "primary_failure_class": source[
                        "primary_failure_class"
                    ],
                    "score": source["score"],
                    "confidence": source["confidence"],
                    "prompt_hash": metadata["prompt_hash"],
                    "response_hash": metadata["response_hash"],
                    "sdk_language": metadata["sdk_language"],
                    "evidence_ref": source["evidence_ref"],
                    "rationale_sha256": stable_hash(source["rationale"]),
                }
            )
        review_receipt_hash = stable_hash(review_receipt)
        for case in cases:
            case["sources"]["llm_judge"]["metadata"].update(
                {
                    "semantic_review_receipt_sha256": review_receipt_hash,
                    "semantic_review_receipt_schema_version": (
                        review_receipt["schema_version"]
                    ),
                    "semantic_review_verification_state": (
                        review_receipt["verification_state"]
                    ),
                    "semantic_review_scope": review_receipt["review_scope"],
                    "semantic_review_expected_case_count": (
                        review_receipt["expected_case_count"]
                    ),
                    "semantic_review_reviewed_case_count": (
                        review_receipt["reviewed_case_count"]
                    ),
                    "semantic_review_receipt_complete": (
                        review_receipt["receipt_complete"]
                    ),
                    "semantic_review_receipt_public_safe": (
                        review_receipt["public_safe"]
                    ),
                    "semantic_review_raw_review_notes_included": (
                        review_receipt["raw_review_notes_included"]
                    ),
                    "semantic_review_raw_reviewer_identity_included": (
                        review_receipt[
                            "raw_reviewer_identity_included"
                        ]
                    ),
                }
            )
        inputs["calibration"][
            "semantic_human_review_receipt"
        ] = review_receipt
        llm_cost = next(
            row
            for row in inputs["calibration"]["cost_ledger"]
            if row["source"] == "llm_judge"
        )
        llm_cost["provider_counts"] = {"audited_live_model": llm_cost["sample_count"]}
        inputs["semantic"]["harness_ready"] = True
        inputs["semantic"]["live_model_evidence_available"] = True
        inputs["semantic"]["reviewed_live_observation_count"] = len(cases)
        inputs["semantic"]["missing_reviewed_live_observation_count"] = 0
        inputs["semantic"]["risk_assessment"]["tracking_ready"] = True
        gate = inputs["evidence"]["semantic_live_merge_gate"]
        gate.update(
            {
                "status": "merged",
                "audited_live_evidence_merged": True,
                "safe_to_mark_c4_met": True,
                "missing_audited_observation_count": 0,
            }
        )

    @staticmethod
    def _gates(report: dict) -> dict[str, dict]:
        return {gate["gate"]: gate for gate in report["gate_status"]}

    @staticmethod
    def _build(inputs: dict) -> dict:
        return build_commercial_readiness_report(
            inputs["coverage"],
            inputs["calibration"],
            case_book_report=inputs["case_book"],
            sdk_parity_report=inputs["sdk"],
            batch_plan_report=inputs["batch"],
            semantic_harness_report=inputs["semantic"],
            regression_replay_report=inputs["replay"],
            evidence_readiness_report=inputs["evidence"],
            releasefoundry_case_map=inputs["releasefoundry_case_map"],
            semantic_collection_packet=inputs[
                "semantic_collection_packet"
            ],
        )

    @staticmethod
    def _inputs() -> dict:
        filenames = {
            "coverage": "a2_g3_coverage_report.json",
            "calibration": "a2_g3_calibration_matrix.json",
            "case_book": "a2_case_book.json",
            "sdk": "a2_sdk_parity_report.json",
            "batch": "a2_batch_plan_report.json",
            "semantic": "a2_semantic_harness_report.json",
            "replay": "a2_regression_replay_report.json",
            "evidence": "a2_evidence_readiness_report.json",
        }
        return {
            key: deepcopy(
                json.loads((RESULTS / filename).read_text(encoding="utf-8"))
            )
            for key, filename in filenames.items()
        } | {
            "releasefoundry_case_map": json.loads(
                (
                    ROOT
                    / "fixtures/a2/calibration/"
                    "releasefoundry_grading_batch_case_map.json"
                ).read_text(encoding="utf-8")
            ),
            "semantic_collection_packet": json.loads(
                (
                    ROOT
                    / "fixtures/a2/calibration/"
                    "a2_semantic_judge_collection_packet.json"
                ).read_text(encoding="utf-8")
            ),
        }


if __name__ == "__main__":
    unittest.main()
