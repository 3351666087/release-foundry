import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from services.judge.releasefoundry_test_receipts import (
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_terminal_receipt,
)
from services.judge.evidence_readiness import (
    _releasefoundry_native_media_surface_summary,
    _multimodal_generated_artifact_capabilities_summary,
    _multimodal_real_api_smoke_summary,
    build_evidence_readiness_report,
    verify_evidence_readiness_artifact,
)
from services.judge.calibration import semantic_collection_packet_binding
from services.judge.result_persistence import stable_hash

VALID_REVIEWER_RECEIPT = "sha256:" + ("a" * 64)
VALID_REVIEWED_AT_UNIX_MS = 1784700000000


def _public_terminal_receipt(case_ids: tuple[str, ...]) -> dict:
    case_map = {
        f"releasefoundry-{cohort_case_id}": cohort_case_id
        for cohort_case_id in case_ids
    }
    private_receipt = build_releasefoundry_test_terminal_receipt(
        {
            "id": "synthetic-run",
            "dataset": 7,
            "result": {
                "status": "completed",
                "judge_version": "releasefoundry-grader-v1",
                "tests": [
                    {
                        "test_id": cohort_raw_case_id,
                        "status": "completed",
                        "started_at": "2026-07-28T08:00:00Z",
                        "completed_at": "2026-07-28T08:00:01Z",
                        "action_results": [
                            {
                                "actor": "agent",
                                "action_type": "message",
                                "actual_response": (
                                    "Verified response evidence."
                                ),
                                "llm_judgment": {"verdict": "pass"},
                            }
                        ],
                    }
                    for cohort_raw_case_id in case_map
                ],
            },
        },
        case_map=case_map,
        expected_dataset_id=7,
    )
    return public_releasefoundry_test_terminal_receipt(private_receipt)


def _verified_terminal_scoring_metadata(
    case_id: str,
    *,
    public_receipt: dict,
) -> dict:
    test_receipt = next(
        receipt for receipt in public_receipt["tests"] if receipt["case_id"] == case_id
    )
    return {
        "terminal_scoring_receipt_schema_version": (
            "a2.releasefoundry_test_terminal_scoring_summary.v1"
        ),
        "terminal_status": test_receipt["terminal_status"],
        "response_evidence_count": test_receipt["response_evidence_count"],
        "response_evidence_kinds": test_receipt["response_evidence_kinds"],
        "grading_signal_count": test_receipt["grading_signal_count"],
        "grading_signal_types": test_receipt["grading_signal_types"],
        "terminal_status_verified": test_receipt["terminal_status_verified"],
        "timestamps_verified": test_receipt["timestamps_verified"],
        "response_evidence_verified": test_receipt["response_evidence_verified"],
        "server_grading_signal_verified": test_receipt[
            "server_grading_signal_verified"
        ],
        "terminal_scoring_verified": test_receipt["terminal_scoring_verified"],
        "terminal_receipt_blockers": test_receipt["blockers"],
        "run_terminal_receipt_schema_version": public_receipt[
            "schema_version"
        ],
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
        "exact_test_set_verified": public_receipt[
            "exact_test_set_verified"
        ],
        "all_expected_tests_terminal_scoring_verified": public_receipt[
            "all_expected_tests_terminal_scoring_verified"
        ],
        "observed_judge_version": public_receipt[
            "observed_judge_version"
        ],
        "judge_version_source": public_receipt["judge_version_source"],
        "judge_version_verified": public_receipt["judge_version_verified"],
        "aggregate_marker_used_as_acceptance_authority": public_receipt[
            "aggregate_marker_used_as_acceptance_authority"
        ],
        "run_terminal_receipt_blockers": public_receipt["blockers"],
        "dataset_identity_receipt_schema_version": (
            "a2.releasefoundry_dataset_identity_receipt.v1"
        ),
        "dataset_identity_verified": True,
        "dataset_identity_receipt_sha256": "sha256:" + ("b" * 64),
        "dataset_identity_manifest_sha256": "sha256:" + ("c" * 64),
        "dataset_identity_content_sha256": "sha256:" + ("d" * 64),
        "dataset_identity_content_collection": "runs",
        "dataset_identity_content_item_count": public_receipt[
            "expected_test_count"
        ],
        "dataset_identity_blockers": [],
    }


class EvidenceReadinessSafetyTests(unittest.TestCase):
    def test_artifact_binds_report_to_current_sources(self):
        calibration, semantic_harness = self._ready_inputs()
        batch_plan = {"plan_ready": True, "batches": [{"batch_id": "batch-1"}]}
        case_map = {"releasefoundry-a2-g3-s001": "sample-a2-s001-pass"}
        collection_packet = self._semantic_collection_packet(calibration)
        report = self._build(
            calibration,
            semantic_harness,
            batch_plan=batch_plan,
            case_map=case_map,
            semantic_collection_packet=collection_packet,
        )

        verified_hash = verify_evidence_readiness_artifact(
            report,
            calibration_matrix=calibration,
            batch_plan_report=batch_plan,
            semantic_harness_report=semantic_harness,
            releasefoundry_case_map=case_map,
            semantic_collection_packet=collection_packet,
        )

        self.assertEqual(verified_hash, report["artifact_hash"])

    def test_artifact_rejects_tampering_and_source_mismatch(self):
        calibration, semantic_harness = self._ready_inputs()
        report = self._build(calibration, semantic_harness)

        tampered = deepcopy(report)
        tampered["releasefoundry_public_merge_gate"]["safe_to_mark_c3_met"] = not report[
            "releasefoundry_public_merge_gate"
        ]["safe_to_mark_c3_met"]
        with self.assertRaisesRegex(ValueError, "does not match report content"):
            verify_evidence_readiness_artifact(tampered)

        mismatched_matrix = deepcopy(calibration)
        mismatched_matrix["dataset_id"] = "different-dataset"
        with self.assertRaisesRegex(ValueError, "source_matrix_hash"):
            verify_evidence_readiness_artifact(
                report,
                calibration_matrix=mismatched_matrix,
            )

    def test_artifact_rejects_missing_or_malformed_hashes(self):
        calibration, semantic_harness = self._ready_inputs()
        report = self._build(calibration, semantic_harness)

        for value in (None, "", "sha256:not-a-hash", 1, {}, []):
            with self.subTest(value=value):
                candidate = deepcopy(report)
                candidate["artifact_hash"] = value
                with self.assertRaisesRegex(ValueError, "artifact_hash"):
                    verify_evidence_readiness_artifact(candidate)

    def test_artifact_rejects_resealed_forged_acceptance_gates(self):
        batch_plan = {
            "plan_ready": True,
            "batches": [{"batch_id": "batch-1"}],
        }
        case_map = {
            "releasefoundry-a2-g3-s001": "sample-a2-s001-pass",
        }

        for gate_name, safe_field in (
            ("releasefoundry_public_merge_gate", "safe_to_mark_c3_met"),
            ("semantic_live_merge_gate", "safe_to_mark_c4_met"),
        ):
            with self.subTest(gate=gate_name):
                calibration, semantic_harness = self._ready_inputs()
                if gate_name == "releasefoundry_public_merge_gate":
                    calibration["source_coverage"]["releasefoundry_grading"] = {
                        "available": 0,
                        "missing": 1,
                    }
                else:
                    calibration["source_coverage"]["llm_judge"] = {
                        "available": 0,
                        "missing": 1,
                    }
                    semantic_harness["reviewed_live_observation_count"] = 0
                    semantic_harness[
                        "missing_reviewed_live_observation_count"
                    ] = 1
                    semantic_harness["live_model_evidence_available"] = False

                collection_packet = self._semantic_collection_packet(
                    calibration
                )
                report = self._build(
                    calibration,
                    semantic_harness,
                    batch_plan=batch_plan,
                    case_map=case_map,
                    semantic_collection_packet=collection_packet,
                )
                self.assertFalse(report[gate_name][safe_field])

                forged = deepcopy(report)
                forged[gate_name][safe_field] = True
                forged["artifact_hash"] = stable_hash(
                    {
                        key: value
                        for key, value in forged.items()
                        if key != "artifact_hash"
                    }
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "deterministic source rebuild",
                ):
                    verify_evidence_readiness_artifact(
                        forged,
                        calibration_matrix=calibration,
                        batch_plan_report=batch_plan,
                        semantic_harness_report=semantic_harness,
                        releasefoundry_case_map=case_map,
                        semantic_collection_packet=collection_packet,
                    )

    def test_c3_merge_gate_rejects_malformed_source_counts(self):
        calibration, semantic_harness = self._ready_inputs()
        malformed_values = (True, False, 1.0, -1, "1", "invalid", {}, [], None)

        for field, fallback in (("available", 0), ("missing", 1)):
            for value in malformed_values:
                with self.subTest(field=field, value=value):
                    candidate = deepcopy(calibration)
                    candidate["source_coverage"]["releasefoundry_grading"][field] = value
                    gate = self._build(candidate, semantic_harness)["releasefoundry_public_merge_gate"]

                    self.assertFalse(gate["public_matrix_merged"])
                    self.assertFalse(gate["safe_to_mark_c3_met"])
                    self.assertIn(
                        f"source_coverage.releasefoundry_grading.{field}",
                        gate["invalid_count_fields"],
                    )
                    self.assertEqual(
                        gate[
                            "current_public_observation_count"
                            if field == "available"
                            else "missing_public_observation_count"
                        ],
                        fallback,
                    )

    def test_c3_merge_gate_requires_complete_terminal_scoring_receipt(self):
        calibration, semantic_harness = self._ready_inputs()
        valid_gate = self._build(
            calibration,
            semantic_harness,
        )["releasefoundry_public_merge_gate"]

        self.assertEqual(valid_gate["status"], "merged")
        self.assertTrue(valid_gate["safe_to_mark_c3_met"])
        self.assertEqual(
            valid_gate["terminal_scoring_verified_observation_count"],
            1,
        )
        self.assertEqual(
            valid_gate["missing_terminal_scoring_receipt_count"],
            0,
        )

        source = calibration["cases"][0]["sources"]["releasefoundry_grading"]
        review_metadata = {
            key: source["metadata"][key]
            for key in (
                "review_status",
                "reviewer_receipt",
                "reviewed_at_unix_ms",
            )
        }
        self_declared = deepcopy(calibration)
        self_declared["cases"][0]["sources"]["releasefoundry_grading"]["metadata"] = {
            **review_metadata,
            "terminal_scoring_verified": True,
        }
        self_declared_gate = self._build(
            self_declared,
            semantic_harness,
        )["releasefoundry_public_merge_gate"]
        self.assertEqual(
            self_declared_gate["status"],
            "merged_unverified_scoring",
        )
        self.assertFalse(self_declared_gate["safe_to_mark_c3_met"])

        invalid_fields = (
            ("terminal_scoring_receipt_schema_version", "self-declared"),
            ("terminal_status", "completed_with_failures"),
            ("terminal_status_verified", False),
            ("timestamps_verified", False),
            ("response_evidence_verified", False),
            ("server_grading_signal_verified", False),
            ("terminal_scoring_verified", False),
            ("grading_signal_types", []),
            ("grading_signal_types", ["aggregate_metrics"]),
            (
                "grading_signal_types",
                ["test_llm_judgment", "test_llm_judgment"],
            ),
            ("terminal_receipt_blockers", ["test_response_evidence_missing"]),
            ("run_terminal_receipt_schema_version", "self-declared"),
            ("run_terminal_receipt_sha256", "sha256:not-a-hash"),
            ("run_expected_test_count", 0),
            ("run_expected_test_count", True),
            ("run_verified_test_count", 0),
            ("run_verified_test_count", True),
            ("run_verified_test_count", 2),
            ("run_receipt_complete", False),
            ("run_dataset_id_verified", False),
            ("run_result_terminal_verified", False),
            ("server_grading_lifecycle_verified", False),
            ("exact_test_set_verified", False),
            ("all_expected_tests_terminal_scoring_verified", False),
            ("observed_judge_version", ""),
            (
                "judge_version_source",
                "operator_attested_not_server_observed",
            ),
            ("judge_version_verified", False),
            ("aggregate_marker_used_as_acceptance_authority", True),
            (
                "run_terminal_receipt_blockers",
                ["run_dataset_id_mismatch"],
            ),
            (
                "dataset_identity_receipt_schema_version",
                "self-declared",
            ),
            ("dataset_identity_verified", False),
            ("dataset_identity_receipt_sha256", "sha256:not-a-hash"),
            ("dataset_identity_manifest_sha256", "sha256:not-a-hash"),
            ("dataset_identity_content_sha256", "sha256:not-a-hash"),
            ("dataset_identity_content_collection", ""),
            ("dataset_identity_content_item_count", 0),
            ("dataset_identity_content_item_count", True),
            ("dataset_identity_blockers", ["identity_not_verified"]),
        )
        for field, value in invalid_fields:
            with self.subTest(field=field, value=value):
                candidate = deepcopy(calibration)
                metadata = candidate["cases"][0]["sources"][
                    "releasefoundry_grading"
                ]["metadata"]
                metadata[field] = value

                gate = self._build(
                    candidate,
                    semantic_harness,
                )["releasefoundry_public_merge_gate"]

                self.assertEqual(gate["reviewed_public_observation_count"], 1)
                self.assertEqual(
                    gate["terminal_scoring_verified_observation_count"],
                    0,
                )
                self.assertEqual(
                    gate["missing_terminal_scoring_receipt_count"],
                    1,
                )
                self.assertEqual(gate["status"], "merged_unverified_scoring")
                self.assertFalse(gate["public_matrix_merged"])
                self.assertFalse(gate["safe_to_mark_c3_met"])

    def test_c3_merge_gate_rejects_mixed_run_receipt_cohort(self):
        calibration, semantic_harness, case_map = self._two_case_ready_inputs()
        valid_gate = self._build(
            calibration,
            semantic_harness,
            case_map=case_map,
        )["releasefoundry_public_merge_gate"]

        self.assertTrue(valid_gate["receipt_cohort_consistent"])
        self.assertEqual(valid_gate["receipt_cohort_blockers"], [])
        self.assertTrue(valid_gate["safe_to_mark_c3_met"])

        candidate = deepcopy(calibration)
        candidate["cases"][1]["sources"]["releasefoundry_grading"]["metadata"][
            "run_terminal_receipt_sha256"
        ] = "sha256:" + ("f" * 64)
        gate = self._build(
            candidate,
            semantic_harness,
            case_map=case_map,
        )["releasefoundry_public_merge_gate"]

        self.assertEqual(gate["terminal_scoring_verified_observation_count"], 2)
        self.assertFalse(gate["receipt_cohort_consistent"])
        self.assertIn(
            "run_terminal_receipt_sha256_mismatch",
            gate["receipt_cohort_blockers"],
        )
        self.assertEqual(gate["status"], "merged_unverified_scoring")
        self.assertFalse(gate["safe_to_mark_c3_met"])

    def test_c3_merge_gate_requires_retained_public_run_receipt_artifact(self):
        calibration, semantic_harness, case_map = self._two_case_ready_inputs()
        calibration.pop("releasefoundry_run_terminal_receipt")
        for case in calibration["cases"]:
            case["sources"]["releasefoundry_grading"]["metadata"][
                "run_terminal_receipt_sha256"
            ] = "sha256:" + ("e" * 64)

        gate = self._build(
            calibration,
            semantic_harness,
            case_map=case_map,
        )["releasefoundry_public_merge_gate"]

        self.assertFalse(gate["run_receipt_artifact_present"])
        self.assertFalse(gate["run_receipt_artifact_binding_valid"])
        self.assertIn(
            "run_receipt_artifact_missing",
            gate["run_receipt_artifact_blockers"],
        )
        self.assertFalse(gate["safe_to_mark_c3_met"])

    def test_c3_merge_gate_rejects_run_receipt_artifact_hash_mismatch(self):
        calibration, semantic_harness = self._ready_inputs()
        case_id = calibration["cases"][0]["case_id"]
        calibration["cases"][0]["sources"]["releasefoundry_grading"]["metadata"][
            "run_terminal_receipt_sha256"
        ] = "sha256:" + ("e" * 64)

        gate = self._build(
            calibration,
            semantic_harness,
        )["releasefoundry_public_merge_gate"]

        self.assertFalse(gate["run_receipt_artifact_binding_valid"])
        self.assertIn(
            f"releasefoundry_observation_{case_id}_run_terminal_receipt_sha256_mismatch",
            gate["run_receipt_artifact_blockers"],
        )
        self.assertFalse(gate["safe_to_mark_c3_met"])

    def test_c3_merge_gate_rejects_missing_duplicate_or_extra_receipt_cases(self):
        mutations = (
            (
                "missing",
                lambda receipt: receipt["tests"].pop(),
                "run_receipt_expected_case_missing",
            ),
            (
                "duplicate",
                lambda receipt: receipt["tests"][1].update(
                    {"case_id": receipt["tests"][0]["case_id"]}
                ),
                "run_receipt_case_id_duplicate",
            ),
            (
                "extra",
                lambda receipt: receipt["tests"].append(
                    {
                        **deepcopy(receipt["tests"][0]),
                        "case_id": "sample-a2-unexpected",
                    }
                ),
                "run_receipt_unexpected_case_present",
            ),
        )
        for label, mutate, blocker in mutations:
            with self.subTest(label=label):
                calibration, semantic_harness, case_map = (
                    self._two_case_ready_inputs()
                )
                mutate(calibration["releasefoundry_run_terminal_receipt"])

                gate = self._build(
                    calibration,
                    semantic_harness,
                    case_map=case_map,
                )["releasefoundry_public_merge_gate"]

                self.assertFalse(gate["run_receipt_artifact_binding_valid"])
                self.assertIn(blocker, gate["run_receipt_artifact_blockers"])
                self.assertFalse(gate["safe_to_mark_c3_met"])

    def test_c3_merge_gate_rejects_per_test_receipt_metadata_mismatch(self):
        calibration, semantic_harness = self._ready_inputs()
        case_id = calibration["cases"][0]["case_id"]
        calibration["cases"][0]["sources"]["releasefoundry_grading"]["metadata"][
            "response_evidence_count"
        ] += 1

        gate = self._build(
            calibration,
            semantic_harness,
        )["releasefoundry_public_merge_gate"]

        self.assertFalse(gate["run_receipt_artifact_binding_valid"])
        self.assertIn(
            f"releasefoundry_observation_{case_id}_response_evidence_count_mismatch",
            gate["run_receipt_artifact_blockers"],
        )
        self.assertFalse(gate["safe_to_mark_c3_met"])

    def test_c3_merge_gate_accepts_exact_public_run_receipt_binding(self):
        calibration, semantic_harness = self._ready_inputs()

        gate = self._build(
            calibration,
            semantic_harness,
        )["releasefoundry_public_merge_gate"]

        self.assertTrue(gate["run_receipt_artifact_present"])
        self.assertRegex(
            gate["run_receipt_artifact_sha256"],
            r"^sha256:[a-f0-9]{64}$",
        )
        self.assertTrue(gate["run_receipt_artifact_binding_valid"])
        self.assertEqual(gate["run_receipt_artifact_blockers"], [])
        self.assertTrue(gate["safe_to_mark_c3_met"])

    def test_c3_merge_gate_rejects_mixed_dataset_identity_cohort(self):
        calibration, semantic_harness, case_map = self._two_case_ready_inputs()

        mutations = (
            (
                "dataset_identity_content_sha256",
                "sha256:" + ("e" * 64),
                "dataset_identity_content_sha256_mismatch",
            ),
            (
                "dataset_identity_content_item_count",
                1,
                "dataset_identity_content_item_count_mismatch",
            ),
        )
        for field, value, blocker in mutations:
            with self.subTest(field=field):
                candidate = deepcopy(calibration)
                candidate["cases"][1]["sources"]["releasefoundry_grading"]["metadata"][
                    field
                ] = value
                gate = self._build(
                    candidate,
                    semantic_harness,
                    case_map=case_map,
                )["releasefoundry_public_merge_gate"]

                self.assertEqual(
                    gate["terminal_scoring_verified_observation_count"],
                    2,
                )
                self.assertFalse(gate["receipt_cohort_consistent"])
                self.assertIn(blocker, gate["receipt_cohort_blockers"])
                self.assertEqual(gate["status"], "merged_unverified_scoring")
                self.assertFalse(gate["safe_to_mark_c3_met"])

    def test_c4_merge_gate_requires_reviewed_count_not_only_live_flag(self):
        calibration, semantic_harness = self._ready_inputs()
        semantic_harness["reviewed_live_observation_count"] = 0

        gate = self._build(calibration, semantic_harness)["semantic_live_merge_gate"]

        self.assertFalse(gate["audited_live_evidence_merged"])
        self.assertFalse(gate["safe_to_mark_c4_met"])
        self.assertEqual(gate["audited_public_observation_count"], 0)
        self.assertEqual(gate["missing_audited_observation_count"], 0)
        self.assertFalse(
            gate["aggregate_reviewed_count_matches_case_evidence"]
        )

    def test_c4_merge_gate_requires_exact_collection_packet_binding(self):
        calibration, semantic_harness = self._ready_inputs()
        packet = self._semantic_collection_packet(calibration)
        valid_gate = self._build(
            calibration,
            semantic_harness,
            semantic_collection_packet=packet,
        )["semantic_live_merge_gate"]

        self.assertTrue(valid_gate["collection_packet_binding_consistent"])
        self.assertEqual(valid_gate["collection_packet_binding_blockers"], [])
        self.assertTrue(valid_gate["safe_to_mark_c4_met"])

        case_id = calibration["cases"][0]["case_id"]
        mutations = (
            (
                "semantic_collection_packet_sha256",
                "sha256:" + ("f" * 64),
            ),
            (
                "semantic_collection_case_sdk_language",
                "typescript",
            ),
            (
                "semantic_collection_case_prompt_template_id",
                "a2_semantic_judge_prompt_v2",
            ),
            (
                "semantic_collection_case_prompt_material_sha256",
                "sha256:" + ("f" * 64),
            ),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                candidate = deepcopy(calibration)
                candidate["cases"][0]["sources"]["llm_judge"]["metadata"][
                    field
                ] = value
                gate = self._build(
                    candidate,
                    semantic_harness,
                    semantic_collection_packet=packet,
                )["semantic_live_merge_gate"]

                self.assertFalse(
                    gate["collection_packet_binding_consistent"]
                )
                self.assertIn(
                    f"{case_id}:{field}_mismatch",
                    gate["collection_packet_binding_blockers"],
                )
                self.assertEqual(
                    gate["status"],
                    "audited_unbound_collection_packet",
                )
                self.assertFalse(gate["safe_to_mark_c4_met"])

    def test_c4_merge_gate_requires_independent_human_review_receipt(self):
        calibration, semantic_harness = self._ready_inputs()
        calibration.pop("semantic_human_review_receipt")

        gate = self._build(
            calibration,
            semantic_harness,
        )["semantic_live_merge_gate"]

        self.assertFalse(gate["review_receipt_artifact_present"])
        self.assertFalse(gate["review_receipt_binding_consistent"])
        self.assertIn(
            "semantic_review_receipt_artifact_missing",
            gate["review_receipt_binding_blockers"],
        )
        self.assertEqual(
            gate["status"],
            "audited_unbound_human_review_receipt",
        )
        self.assertFalse(gate["safe_to_mark_c4_met"])

    def test_c4_merge_gate_rejects_tampered_human_review_receipt(self):
        mutations = (
            (
                "duplicated case",
                lambda receipt: receipt["cases"].append(
                    deepcopy(receipt["cases"][0])
                ),
                "semantic_review_receipt_case_id_duplicate",
            ),
            (
                "extra case",
                self._append_extra_review_receipt_case,
                "semantic_review_receipt_unexpected_case_present",
            ),
            (
                "changed verdict",
                lambda receipt: receipt["cases"][0].__setitem__(
                    "passed",
                    False,
                ),
                "semantic_review_receipt_sample-a2-s001-pass_passed_mismatch",
            ),
        )
        for label, mutate, expected_blocker in mutations:
            with self.subTest(mutation=label):
                calibration, semantic_harness = self._ready_inputs()
                mutate(calibration["semantic_human_review_receipt"])

                gate = self._build(
                    calibration,
                    semantic_harness,
                )["semantic_live_merge_gate"]

                self.assertFalse(gate["review_receipt_binding_consistent"])
                self.assertIn(
                    expected_blocker,
                    gate["review_receipt_binding_blockers"],
                )
                self.assertEqual(
                    gate["status"],
                    "audited_unbound_human_review_receipt",
                )
                self.assertFalse(gate["safe_to_mark_c4_met"])

    def test_c4_merge_gate_rejects_review_receipt_metadata_hash_mismatch(self):
        calibration, semantic_harness = self._ready_inputs()
        calibration["cases"][0]["sources"]["llm_judge"]["metadata"][
            "semantic_review_receipt_sha256"
        ] = "sha256:" + ("f" * 64)

        gate = self._build(
            calibration,
            semantic_harness,
        )["semantic_live_merge_gate"]

        self.assertFalse(gate["review_receipt_binding_consistent"])
        self.assertIn(
            (
                "semantic_observation_sample-a2-s001-pass_"
                "semantic_review_receipt_sha256_mismatch"
            ),
            gate["review_receipt_binding_blockers"],
        )
        self.assertFalse(gate["safe_to_mark_c4_met"])

    def test_c4_merge_gate_rejects_missing_review_receipt_metadata_binding(self):
        calibration, semantic_harness = self._ready_inputs()
        calibration["cases"][0]["sources"]["llm_judge"]["metadata"].pop(
            "semantic_review_receipt_sha256"
        )

        gate = self._build(
            calibration,
            semantic_harness,
        )["semantic_live_merge_gate"]

        self.assertFalse(gate["review_receipt_binding_consistent"])
        self.assertIn(
            (
                "semantic_observation_sample-a2-s001-pass_"
                "semantic_review_receipt_sha256_missing"
            ),
            gate["review_receipt_binding_blockers"],
        )
        self.assertFalse(gate["safe_to_mark_c4_met"])

    def test_c4_merge_gate_rejects_mixed_collection_packet_cohort(self):
        calibration, semantic_harness, case_map = self._two_case_ready_inputs()
        packet = self._semantic_collection_packet(calibration)
        candidate = deepcopy(calibration)
        candidate["cases"][1]["sources"]["llm_judge"]["metadata"][
            "semantic_collection_packet_sha256"
        ] = "sha256:" + ("f" * 64)

        gate = self._build(
            candidate,
            semantic_harness,
            case_map=case_map,
            semantic_collection_packet=packet,
        )["semantic_live_merge_gate"]

        self.assertFalse(gate["collection_packet_binding_consistent"])
        self.assertIn(
            "semantic_collection_packet_sha256_mixed",
            gate["collection_packet_binding_blockers"],
        )
        self.assertEqual(
            gate["status"],
            "audited_unbound_collection_packet",
        )
        self.assertFalse(gate["safe_to_mark_c4_met"])

    def test_c4_merge_gate_rejects_collection_packet_case_set_mismatch(self):
        calibration, semantic_harness = self._ready_inputs()
        packet = self._semantic_collection_packet(calibration)
        packet_core = {
            key: value
            for key, value in packet.items()
            if key != "artifact_hash"
        }
        packet_core["cases"][0]["case_id"] = "different-case"
        mismatched_packet = {
            **packet_core,
            "artifact_hash": stable_hash(packet_core),
        }

        gate = self._build(
            calibration,
            semantic_harness,
            semantic_collection_packet=mismatched_packet,
        )["semantic_live_merge_gate"]

        self.assertFalse(gate["collection_packet_binding_consistent"])
        self.assertIn(
            "calibration_case_set_mismatch",
            gate["collection_packet_binding_blockers"],
        )
        self.assertFalse(gate["safe_to_mark_c4_met"])

    def test_c4_merge_gate_requires_case_level_reviewed_live_evidence(self):
        calibration, semantic_harness = self._ready_inputs()
        calibration["cases"][0]["sources"].pop("llm_judge")

        gate = self._build(calibration, semantic_harness)["semantic_live_merge_gate"]

        self.assertFalse(gate["audited_live_evidence_merged"])
        self.assertFalse(gate["safe_to_mark_c4_met"])
        self.assertEqual(gate["case_level_reviewed_observation_count"], 0)
        self.assertEqual(gate["audited_public_observation_count"], 0)
        self.assertEqual(gate["missing_audited_observation_count"], 1)

    def test_c4_merge_gate_revalidates_each_reviewed_live_source(self):
        invalid_sources = (
            ("not available", ("available",), False),
            ("wrong status", ("status",), "missing"),
            ("offline provider", ("provider",), "offline_reference"),
            ("missing model", ("model",), ""),
            (
                "public evidence URL",
                ("evidence_ref",),
                "https://example.invalid/semantic.json",
            ),
            (
                "noncanonical prompt hash",
                ("metadata", "prompt_hash"),
                "sha256:prompt-s001",
            ),
            (
                "noncanonical response hash",
                ("metadata", "response_hash"),
                "sha256:response-s001",
            ),
            (
                "unreviewed",
                ("metadata", "review_status"),
                "unreviewed",
            ),
            (
                "noncanonical reviewer receipt",
                ("metadata", "reviewer_receipt"),
                "reviewer@example.com",
            ),
            (
                "boolean review timestamp",
                ("metadata", "reviewed_at_unix_ms"),
                True,
            ),
            (
                "unsupported SDK language",
                ("metadata", "sdk_language"),
                "java",
            ),
            ("zero prompt tokens", ("cost", "prompt_tokens"), 0),
            ("zero completion tokens", ("cost", "completion_tokens"), 0),
            ("zero cost", ("cost", "estimated_usd"), 0),
        )

        for label, path, value in invalid_sources:
            with self.subTest(source=label):
                calibration, semantic_harness = self._ready_inputs()
                target = calibration["cases"][0]["sources"]["llm_judge"]
                for field in path[:-1]:
                    target = target[field]
                target[path[-1]] = value

                gate = self._build(
                    calibration,
                    semantic_harness,
                )["semantic_live_merge_gate"]

                self.assertFalse(gate["safe_to_mark_c4_met"])
                self.assertEqual(
                    gate["case_level_reviewed_observation_count"],
                    0,
                )
                self.assertEqual(gate["missing_audited_observation_count"], 1)

    def test_c4_merge_gate_rejects_malformed_counts_and_live_flag(self):
        calibration, semantic_harness = self._ready_inputs()
        malformed_values = (True, False, 1.0, -1, "1", "invalid", {}, [], None)

        for field in ("available", "reviewed_live_observation_count"):
            for value in malformed_values:
                with self.subTest(field=field, value=value):
                    candidate_calibration = deepcopy(calibration)
                    candidate_harness = deepcopy(semantic_harness)
                    if field == "available":
                        candidate_calibration["source_coverage"]["llm_judge"][field] = value
                        expected_field = "source_coverage.llm_judge.available"
                    else:
                        candidate_harness[field] = value
                        expected_field = field

                    gate = self._build(
                        candidate_calibration,
                        candidate_harness,
                    )["semantic_live_merge_gate"]

                    self.assertFalse(gate["audited_live_evidence_merged"])
                    self.assertFalse(gate["safe_to_mark_c4_met"])
                    self.assertIn(expected_field, gate["invalid_count_fields"])

        for value in ("true", "false", 1, 0, {}, [], None):
            with self.subTest(live_model_evidence_available=value):
                candidate_harness = deepcopy(semantic_harness)
                candidate_harness["live_model_evidence_available"] = value

                gate = self._build(
                    calibration,
                    candidate_harness,
                )["semantic_live_merge_gate"]

                self.assertFalse(gate["audited_live_evidence_merged"])
                self.assertFalse(gate["safe_to_mark_c4_met"])
                self.assertIn(
                    "live_model_evidence_available",
                    gate["invalid_boolean_fields"],
                )

    def test_external_collection_rejects_malformed_semantic_flags(self):
        calibration, semantic_harness = self._ready_inputs()
        malformed_values = ("true", "false", 1, 0, {}, [], None)
        fields = (
            ("harness_ready", "semantic_harness_report.harness_ready"),
            (
                "risk_assessment.tracking_ready",
                "semantic_harness_report.risk_assessment.tracking_ready",
            ),
        )

        for field, expected_invalid_field in fields:
            for value in malformed_values:
                with self.subTest(field=field, value=value):
                    candidate_harness = deepcopy(semantic_harness)
                    if field == "harness_ready":
                        candidate_harness[field] = value
                        readiness_field = "semantic_harness_ready"
                    else:
                        candidate_harness["risk_assessment"]["tracking_ready"] = value
                        readiness_field = "semantic_false_positive_tracking_ready"

                    report = self._build(calibration, candidate_harness)

                    self.assertFalse(report["ready_for_external_collection"])
                    self.assertFalse(report["readiness_checks"][readiness_field])
                    self.assertIn(
                        expected_invalid_field,
                        report["invalid_boolean_fields"],
                    )
                    if field != "harness_ready":
                        self.assertFalse(
                            report["semantic_judge_preflight"][
                                "false_positive_tracking_ready"
                            ]
                        )

    def test_official_sdk_smoke_rejects_malformed_flags_and_counts(self):
        calibration, semantic_harness = self._ready_inputs()

        for value in ("true", "false", 1, 0, {}, [], None):
            with self.subTest(all_required_calls_reached=value):
                smoke = self._official_smoke()
                smoke["all_required_calls_reached"] = value

                report = self._build(
                    calibration,
                    semantic_harness,
                    official_sdk_smoke=smoke,
                )
                summary = report["official_sdk_smoke"]

                self.assertFalse(summary["all_required_calls_reached"])
                self.assertFalse(summary["read_only_reachable"])
                self.assertFalse(
                    report["readiness_checks"]["official_sdk_smoke_readonly_ok"]
                )
                self.assertFalse(report["ready_for_external_collection"])
                self.assertIn(
                    "all_required_calls_reached",
                    summary["invalid_boolean_fields"],
                )

        for value in (True, 1.0, -1, "6", "invalid", 5, {}, [], None):
            with self.subTest(api_call_count=value):
                smoke = self._official_smoke()
                smoke["api_call_count"] = value

                summary = self._build(
                    calibration,
                    semantic_harness,
                    official_sdk_smoke=smoke,
                )["official_sdk_smoke"]

                self.assertFalse(summary["read_only_reachable"])
                self.assertIn("api_call_count", summary["invalid_count_fields"])

    def test_multimodal_smoke_rejects_malformed_flags_and_counts(self):
        calibration, semantic_harness = self._ready_inputs()
        malformed_values = ("true", "false", 1, 0, {}, [], None)

        for field in (
            "all_required_modalities_requested",
            "create_request_reached",
            "wait_completed",
            "dataset_id_present",
            "artifact_receipts_public_safe",
            "public_safe",
        ):
            for value in malformed_values:
                with self.subTest(field=field, value=value):
                    smoke = self._multimodal_smoke()
                    smoke[field] = value

                    summary = self._build(
                        calibration,
                        semantic_harness,
                        multimodal_real_api_smoke=smoke,
                    )["multimodal_real_api_smoke"]

                    self.assertFalse(summary["ready_for_a2_multimodal_context"])
                    self.assertIn(field, summary["invalid_boolean_fields"])
                    if field == "create_request_reached":
                        self.assertFalse(summary["create_request_reached"])
                        self.assertFalse(summary["real_api_boundary_reached"])
                    elif field == "all_required_modalities_requested":
                        self.assertFalse(summary["all_required_modalities_requested"])
                    elif field == "public_safe":
                        self.assertFalse(summary["public_safe"])

        for field in (
            "api_call_count",
            "artifact_reference_count",
            "artifact_download_attempt_count",
            "artifact_download_verified_count",
        ):
            for value in (True, 1.0, -1, "2", "invalid", {}, [], None):
                with self.subTest(field=field, value=value):
                    smoke = self._multimodal_smoke()
                    smoke[field] = value

                    summary = self._build(
                        calibration,
                        semantic_harness,
                        multimodal_real_api_smoke=smoke,
                    )["multimodal_real_api_smoke"]

                    self.assertFalse(summary["ready_for_a2_multimodal_context"])
                    self.assertIn(field, summary["invalid_count_fields"])

    def test_multimodal_smoke_rejects_inconsistent_artifact_receipt_counts(self):
        calibration, semantic_harness = self._ready_inputs()
        inconsistent_counts = (
            ("artifact_reference_count", 0),
            ("artifact_download_attempt_count", 0),
            ("artifact_download_verified_count", 0),
        )

        for field, value in inconsistent_counts:
            with self.subTest(field=field):
                smoke = self._multimodal_smoke()
                smoke[field] = value

                summary = self._build(
                    calibration,
                    semantic_harness,
                    multimodal_real_api_smoke=smoke,
                )["multimodal_real_api_smoke"]

                self.assertFalse(summary["ready_for_a2_multimodal_context"])
                self.assertIn(field, summary["invalid_count_fields"])

    def test_verified_generated_artifact_receipt_does_not_mark_c3_ready(self):
        calibration, semantic_harness = self._ready_inputs()

        summary = self._build(
            calibration,
            semantic_harness,
            multimodal_real_api_smoke=self._multimodal_smoke(),
        )["multimodal_real_api_smoke"]

        self.assertEqual(summary["artifact_download_verified_count"], 1)
        self.assertEqual(summary["accepted_modalities"], ["text"])
        self.assertFalse(summary["ready_for_a2_multimodal_context"])
        self.assertFalse(summary["c3_grading_ready"])

    def test_generated_artifact_capabilities_use_three_independent_real_probes(self):
        calibration, semantic_harness = self._ready_inputs()

        report = self._build(calibration, semantic_harness)
        capabilities = report[
            "multimodal_generated_artifact_capabilities"
        ]

        self.assertTrue(
            report["readiness_checks"][
                "multimodal_generated_artifacts_verified"
            ]
        )
        self.assertEqual(capabilities["aggregation_status"], "verified")
        self.assertEqual(capabilities["probe_count"], 3)
        self.assertEqual(capabilities["verified_probe_count"], 3)
        self.assertEqual(capabilities["independent_request_count"], 3)
        self.assertEqual(
            capabilities["verified_generated_artifact_modalities"],
            ["image", "audio", "file"],
        )
        self.assertEqual(
            capabilities["provider_unverified_modalities"],
            ["video"],
        )
        self.assertEqual(
            len(
                {
                    probe["request_content_sha256"]
                    for probe in capabilities["probes"]
                }
            ),
            3,
        )
        self.assertTrue(capabilities["public_safe"])
        self.assertFalse(capabilities["native_media_uploaded"])
        self.assertFalse(capabilities["media_upload_api_observed"])
        self.assertFalse(
            capabilities["caller_native_input_support_proven"]
        )
        self.assertFalse(capabilities["c3_grading_ready"])

    def test_generated_artifact_capabilities_fail_closed_on_malformed_json(self):
        calibration, semantic_harness = self._ready_inputs()

        report = self._build(
            calibration,
            semantic_harness,
            multimodal_image_real_api_smoke="{",
            multimodal_audio_real_api_smoke=self._multimodal_smoke(
                modality="audio",
                request_content_sha256="b" * 64,
            ),
            multimodal_file_real_api_smoke=self._multimodal_smoke(
                modality="file",
                request_content_sha256="c" * 64,
            ),
        )
        capabilities = report[
            "multimodal_generated_artifact_capabilities"
        ]

        self.assertEqual(capabilities["aggregation_status"], "invalid")
        self.assertEqual(
            capabilities["verified_generated_artifact_modalities"],
            [],
        )
        self.assertFalse(capabilities["public_safe"])
        self.assertFalse(
            report["readiness_checks"][
                "multimodal_generated_artifacts_verified"
            ]
        )
        self.assertIn(
            "probes[0].available",
            capabilities["invalid_probe_fields"],
        )

    def test_generated_artifact_capabilities_reject_private_receipt_fields(self):
        calibration, semantic_harness = self._ready_inputs()
        image_smoke = self._multimodal_smoke(
            modality="image",
            request_content_sha256="a" * 64,
        )
        image_smoke["artifact_receipts"][0].update(
            {
                "signed_url": "https://example.invalid/?token=secret",
                "object_key": "private/object",
                "path": "C:/private/artifact.png",
            }
        )

        report = self._build(
            calibration,
            semantic_harness,
            multimodal_image_real_api_smoke=image_smoke,
            multimodal_audio_real_api_smoke=self._multimodal_smoke(
                modality="audio",
                request_content_sha256="b" * 64,
            ),
            multimodal_file_real_api_smoke=self._multimodal_smoke(
                modality="file",
                request_content_sha256="c" * 64,
            ),
        )
        capabilities = report[
            "multimodal_generated_artifact_capabilities"
        ]

        self.assertEqual(capabilities["aggregation_status"], "invalid")
        self.assertEqual(
            capabilities["verified_generated_artifact_modalities"],
            [],
        )
        self.assertFalse(capabilities["public_safe"])
        for field in ("signed_url", "object_key", "path"):
            self.assertIn(
                f"probes[0].artifact_receipts[0].{field}",
                capabilities["invalid_probe_fields"],
            )
        serialized = json.dumps(capabilities)
        self.assertNotIn("example.invalid", serialized)
        self.assertNotIn("private/object", serialized)
        self.assertNotIn("C:/private", serialized)

    def test_generated_artifact_capabilities_require_distinct_request_hashes(self):
        calibration, semantic_harness = self._ready_inputs()
        request_content_sha256 = "a" * 64

        report = self._build(
            calibration,
            semantic_harness,
            multimodal_image_real_api_smoke=self._multimodal_smoke(
                modality="image",
                request_content_sha256=request_content_sha256,
            ),
            multimodal_audio_real_api_smoke=self._multimodal_smoke(
                modality="audio",
                request_content_sha256=request_content_sha256,
            ),
            multimodal_file_real_api_smoke=self._multimodal_smoke(
                modality="file",
                request_content_sha256="c" * 64,
            ),
        )
        capabilities = report[
            "multimodal_generated_artifact_capabilities"
        ]

        self.assertEqual(capabilities["aggregation_status"], "invalid")
        self.assertEqual(capabilities["independent_request_count"], 0)
        self.assertIn(
            "probes.request_content_sha256.not_unique",
            capabilities["invalid_probe_fields"],
        )

    def test_generated_artifact_capabilities_bind_each_probe_to_its_modality(self):
        probes, native_surface = self._generated_artifact_probe_inputs()
        probes[0], probes[1] = (
            (probes[0][0], probes[1][1]),
            (probes[1][0], probes[0][1]),
        )

        capabilities = _multimodal_generated_artifact_capabilities_summary(
            probes,
            releasefoundry_native_media_surface=native_surface,
        )

        self.assertEqual(capabilities["aggregation_status"], "invalid")
        self.assertEqual(
            capabilities["verified_generated_artifact_modalities"],
            [],
        )
        self.assertIn(
            "probes[0].required_modality_binding",
            capabilities["invalid_probe_fields"],
        )
        self.assertIn(
            "probes[1].verified_modality_binding",
            capabilities["invalid_probe_fields"],
        )

    def test_generated_artifact_capabilities_reject_reused_artifact_hashes(self):
        probes, native_surface = self._generated_artifact_probe_inputs()
        probes[1][1]["artifact_receipts"][0]["sha256"] = (
            probes[0][1]["artifact_receipts"][0]["sha256"]
        )

        capabilities = _multimodal_generated_artifact_capabilities_summary(
            probes,
            releasefoundry_native_media_surface=native_surface,
        )

        self.assertEqual(capabilities["aggregation_status"], "invalid")
        self.assertEqual(capabilities["verified_probe_count"], 0)
        self.assertIn(
            "probes.artifact_receipts.sha256.not_unique",
            capabilities["invalid_probe_fields"],
        )

    def test_native_media_surface_default_receipt_preserves_capability_boundary(self):
        calibration, semantic_harness = self._ready_inputs()

        report = self._build(calibration, semantic_harness)
        surface = report["releasefoundry_native_media_surface"]
        capabilities = report["multimodal_generated_artifact_capabilities"]

        self.assertTrue(surface["surface_audit_verified"])
        self.assertFalse(surface["live_session_reached"])
        self.assertEqual(surface["live_session_status"], "not_requested")
        self.assertEqual(surface["sdk_package_name"], "releasefoundry")
        self.assertEqual(surface["sdk_version"], "0.3.1")
        self.assertEqual(
            surface["generated_artifact_capabilities"],
            {
                "image": "verified",
                "audio": "verified",
                "file": "verified",
                "video": "provider_unverified",
            },
        )
        self.assertEqual(
            surface["caller_native_submission"],
            {
                "image": "provider_surface_missing",
                "audio": "provider_surface_missing",
                "file": "provider_surface_missing",
                "video": "provider_unverified",
            },
        )
        self.assertFalse(surface["caller_native_input_support_proven"])
        self.assertFalse(surface["c3_grading_ready"])
        self.assertTrue(
            report["readiness_checks"]["releasefoundry_native_media_surface_audited"]
        )
        self.assertTrue(capabilities["native_media_surface_binding_verified"])
        self.assertFalse(capabilities["caller_native_input_support_proven"])
        self.assertFalse(capabilities["c3_grading_ready"])

    def test_native_media_surface_rejects_unbound_live_session_claim(self):
        calibration, semantic_harness = self._ready_inputs()
        receipt = self._native_media_surface_receipt()
        receipt["live_session"]["reached"] = True

        report = self._build(
            calibration,
            semantic_harness,
            releasefoundry_native_media_surface=receipt,
        )
        surface = report["releasefoundry_native_media_surface"]

        self.assertFalse(surface["surface_audit_verified"])
        self.assertFalse(report["readiness_checks"]["releasefoundry_native_media_surface_audited"])
        self.assertIn("live_session.reached", surface["invalid_fields"])
        self.assertFalse(
            report["multimodal_generated_artifact_capabilities"][
                "native_media_surface_binding_verified"
            ]
        )

    def test_native_media_surface_sdk_drift_fails_closed(self):
        calibration, semantic_harness = self._ready_inputs()
        receipt = self._native_media_surface_receipt()
        receipt["sdk"]["version"] = "0.3.2"
        receipt["sdk"]["artifact_sha256"] = "b" * 64
        receipt["static_audit"]["surface_fingerprint_sha256"] = "c" * 64

        report = self._build(
            calibration,
            semantic_harness,
            releasefoundry_native_media_surface=receipt,
        )
        surface = report["releasefoundry_native_media_surface"]

        self.assertFalse(surface["surface_audit_verified"])
        self.assertEqual(
            surface["caller_native_submission"],
            {
                "image": "sdk_surface_changed_review_required",
                "audio": "sdk_surface_changed_review_required",
                "file": "sdk_surface_changed_review_required",
                "video": "provider_unverified",
            },
        )
        self.assertIn("sdk.version", surface["invalid_fields"])
        self.assertIn("sdk.artifact_sha256", surface["invalid_fields"])
        self.assertIn(
            "static_audit.surface_fingerprint_sha256",
            surface["invalid_fields"],
        )

    def test_native_media_surface_upload_signals_require_manual_review(self):
        calibration, semantic_harness = self._ready_inputs()
        for field in (
            "upload_method_observed",
            "immutable_media_url_parameter_observed",
        ):
            with self.subTest(field=field):
                receipt = self._native_media_surface_receipt()
                receipt[field] = True

                report = self._build(
                    calibration,
                    semantic_harness,
                    releasefoundry_native_media_surface=receipt,
                )
                surface = report["releasefoundry_native_media_surface"]

                self.assertFalse(surface["surface_audit_verified"])
                self.assertEqual(
                    surface["caller_native_submission"]["image"],
                    "sdk_surface_changed_review_required",
                )
                self.assertEqual(
                    surface["caller_native_submission"]["video"],
                    "provider_unverified",
                )
                self.assertFalse(surface["caller_native_input_support_proven"])
                self.assertFalse(surface["c3_grading_ready"])

    def test_native_media_surface_private_material_is_not_projected(self):
        calibration, semantic_harness = self._ready_inputs()
        receipt = self._native_media_surface_receipt()
        receipt["api_key"] = "must-not-appear-in-readiness"

        report = self._build(
            calibration,
            semantic_harness,
            releasefoundry_native_media_surface=receipt,
        )
        surface = report["releasefoundry_native_media_surface"]
        serialized = json.dumps(surface)

        self.assertFalse(surface["surface_audit_verified"])
        self.assertFalse(surface["public_safe"])
        self.assertIn("payload.api_key", surface["invalid_fields"])
        self.assertNotIn("must-not-appear-in-readiness", serialized)

    def test_native_media_surface_never_promotes_video(self):
        calibration, semantic_harness = self._ready_inputs()
        receipt = self._native_media_surface_receipt()
        receipt["generated_artifact_capabilities"]["video"] = "verified"
        receipt["caller_native_submission"]["video"] = "provider_surface_missing"

        report = self._build(
            calibration,
            semantic_harness,
            releasefoundry_native_media_surface=receipt,
        )
        surface = report["releasefoundry_native_media_surface"]

        self.assertFalse(surface["surface_audit_verified"])
        self.assertEqual(
            surface["generated_artifact_capabilities"]["video"],
            "provider_unverified",
        )
        self.assertEqual(
            surface["caller_native_submission"]["video"],
            "provider_unverified",
        )

    def _build(
        self,
        calibration: dict,
        semantic_harness: dict,
        *,
        batch_plan: dict | None = None,
        case_map: dict | None = None,
        official_sdk_smoke: dict | None = None,
        multimodal_real_api_smoke: dict | str | None = None,
        multimodal_audio_real_api_smoke: dict | str | None = None,
        multimodal_image_real_api_smoke: dict | str | None = None,
        multimodal_file_real_api_smoke: dict | str | None = None,
        releasefoundry_native_media_surface: dict | str | None = None,
        semantic_collection_packet: dict | None = None,
    ) -> dict:
        case_map = case_map or {
            "releasefoundry-a2-g3-s001": "sample-a2-s001-pass"
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            case_map_path = Path(tmp_dir) / "case_map.json"
            case_map_path.write_text(json.dumps(case_map), encoding="utf-8")
            kwargs = {"releasefoundry_case_map_path": case_map_path}
            if official_sdk_smoke is not None:
                official_smoke_path = Path(tmp_dir) / "official_smoke.json"
                official_smoke_path.write_text(
                    json.dumps(official_sdk_smoke),
                    encoding="utf-8",
                )
                kwargs["official_sdk_smoke_path"] = official_smoke_path
            if multimodal_real_api_smoke is not None:
                multimodal_smoke_path = Path(tmp_dir) / "multimodal_smoke.json"
                multimodal_smoke_path.write_text(
                    (
                        multimodal_real_api_smoke
                        if isinstance(multimodal_real_api_smoke, str)
                        else json.dumps(multimodal_real_api_smoke)
                    ),
                    encoding="utf-8",
                )
                kwargs["multimodal_real_api_smoke_path"] = multimodal_smoke_path
            if multimodal_audio_real_api_smoke is not None:
                multimodal_audio_smoke_path = (
                    Path(tmp_dir) / "multimodal_audio_smoke.json"
                )
                multimodal_audio_smoke_path.write_text(
                    (
                        multimodal_audio_real_api_smoke
                        if isinstance(
                            multimodal_audio_real_api_smoke,
                            str,
                        )
                        else json.dumps(multimodal_audio_real_api_smoke)
                    ),
                    encoding="utf-8",
                )
                kwargs["multimodal_audio_real_api_smoke_path"] = (
                    multimodal_audio_smoke_path
                )
            if multimodal_image_real_api_smoke is not None:
                multimodal_image_smoke_path = (
                    Path(tmp_dir) / "multimodal_image_smoke.json"
                )
                multimodal_image_smoke_path.write_text(
                    (
                        multimodal_image_real_api_smoke
                        if isinstance(
                            multimodal_image_real_api_smoke,
                            str,
                        )
                        else json.dumps(multimodal_image_real_api_smoke)
                    ),
                    encoding="utf-8",
                )
                kwargs["multimodal_image_real_api_smoke_path"] = (
                    multimodal_image_smoke_path
                )
            if multimodal_file_real_api_smoke is not None:
                multimodal_file_smoke_path = (
                    Path(tmp_dir) / "multimodal_file_smoke.json"
                )
                multimodal_file_smoke_path.write_text(
                    (
                        multimodal_file_real_api_smoke
                        if isinstance(
                            multimodal_file_real_api_smoke,
                            str,
                        )
                        else json.dumps(multimodal_file_real_api_smoke)
                    ),
                    encoding="utf-8",
                )
                kwargs["multimodal_file_real_api_smoke_path"] = (
                    multimodal_file_smoke_path
                )
            if releasefoundry_native_media_surface is not None:
                native_media_surface_path = (
                    Path(tmp_dir) / "releasefoundry_native_media_surface.json"
                )
                native_media_surface_path.write_text(
                    (
                        releasefoundry_native_media_surface
                        if isinstance(releasefoundry_native_media_surface, str)
                        else json.dumps(releasefoundry_native_media_surface)
                    ),
                    encoding="utf-8",
                )
                kwargs["releasefoundry_native_media_surface_path"] = (
                    native_media_surface_path
                )
            return build_evidence_readiness_report(
                calibration,
                batch_plan or {},
                semantic_harness,
                semantic_collection_packet=(
                    semantic_collection_packet
                    if semantic_collection_packet is not None
                    else self._semantic_collection_packet(calibration)
                ),
                **kwargs,
            )

    def _two_case_ready_inputs(self) -> tuple[dict, dict, dict]:
        calibration, semantic_harness = self._ready_inputs()
        first_case_id = calibration["cases"][0]["case_id"]
        second_case_id = "sample-a2-s002-wrong-intent"
        cohort_case_ids = (first_case_id, second_case_id)
        public_receipt = _public_terminal_receipt(cohort_case_ids)
        calibration["releasefoundry_run_terminal_receipt"] = public_receipt

        review_metadata = {
            "review_status": "reviewed",
            "reviewer_receipt": VALID_REVIEWER_RECEIPT,
            "reviewed_at_unix_ms": VALID_REVIEWED_AT_UNIX_MS,
        }
        calibration["cases"][0]["sources"]["releasefoundry_grading"]["metadata"] = {
            **review_metadata,
            **_verified_terminal_scoring_metadata(
                first_case_id,
                public_receipt=public_receipt,
            ),
        }

        second_case = deepcopy(calibration["cases"][0])
        second_case["case_id"] = second_case_id
        second_case["scenario_id"] = "s002"
        second_case["fixture_ref"] = "fixtures/a2/runs/s002.json"
        second_case["sources"]["releasefoundry_grading"]["metadata"] = {
            **review_metadata,
            **_verified_terminal_scoring_metadata(
                second_case_id,
                public_receipt=public_receipt,
            ),
        }
        calibration["cases"].append(second_case)
        calibration["source_coverage"]["releasefoundry_grading"] = {
            "available": 2,
            "missing": 0,
        }
        calibration["source_coverage"]["llm_judge"] = {
            "available": 2,
            "missing": 0,
        }
        semantic_harness["reviewed_live_observation_count"] = 2
        semantic_harness["missing_reviewed_live_observation_count"] = 0
        self._bind_semantic_sources_to_packet(
            calibration,
            self._semantic_collection_packet(calibration),
        )
        self._bind_semantic_sources_to_review_receipt(calibration)
        case_map = {
            f"releasefoundry-{case_id}": case_id
            for case_id in cohort_case_ids
        }
        return calibration, semantic_harness, case_map

    @staticmethod
    def _ready_inputs() -> tuple[dict, dict]:
        case_id = "sample-a2-s001-pass"
        public_receipt = _public_terminal_receipt((case_id,))
        calibration = {
            "dataset_id": "a2-evidence-readiness-safety",
            "releasefoundry_run_terminal_receipt": public_receipt,
            "cases": [
                {
                    "case_id": case_id,
                    "scenario_id": "s001",
                    "fixture_ref": "fixtures/a2/runs/s001.json",
                    "sources": {
                        "releasefoundry_grading": {
                            "available": True,
                            "evidence_ref": (
                                "docs/evidence/private_refs/"
                                "a2_releasefoundry_grading_import.review.json"
                            ),
                            "metadata": {
                                "review_status": "reviewed",
                                "reviewer_receipt": VALID_REVIEWER_RECEIPT,
                                "reviewed_at_unix_ms": (
                                    VALID_REVIEWED_AT_UNIX_MS
                                ),
                                **_verified_terminal_scoring_metadata(
                                    case_id,
                                    public_receipt=public_receipt,
                                ),
                            },
                        },
                        "llm_judge": {
                            "available": True,
                            "status": "available",
                            "source": "llm_judge",
                            "provider": "reviewed-live-provider",
                            "model": "reviewed-live-model",
                            "passed": True,
                            "primary_failure_class": "none",
                            "score": 100.0,
                            "confidence": 0.9,
                            "rationale": "Synthetic reviewed semantic result.",
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
                                        f"prompt:{case_id}".encode()
                                    ).hexdigest()
                                ),
                                "response_hash": (
                                    "sha256:"
                                    + hashlib.sha256(
                                        f"response:{case_id}".encode()
                                    ).hexdigest()
                                ),
                                "review_status": "reviewed",
                                "reviewer_receipt": VALID_REVIEWER_RECEIPT,
                                "reviewed_at_unix_ms": (
                                    VALID_REVIEWED_AT_UNIX_MS
                                ),
                                "sdk_language": "python",
                            },
                            "cost": {
                                "prompt_tokens": 700,
                                "completion_tokens": 90,
                                "estimated_usd": 0.0015,
                            },
                        },
                    },
                }
            ],
            "source_coverage": {
                "releasefoundry_grading": {"available": 1, "missing": 0},
                "llm_judge": {"available": 1, "missing": 0},
            },
            "cost_ledger": [
                {
                    "source": "llm_judge",
                    "provider_counts": {"reviewed-live-provider": 1},
                }
            ],
        }
        semantic_harness = {
            "harness_ready": True,
            "live_model_evidence_available": True,
            "reviewed_live_observation_count": 1,
            "missing_reviewed_live_observation_count": 0,
            "reviewed_live_sdk_languages": ["python", "typescript"],
            "reviewed_live_required_metadata_fields": ["prompt_hash"],
            "source_matrix": {
                "official_sdk_chains": [
                    {"language": "python"},
                    {"language": "typescript"},
                ],
                "required_languages": ["python", "typescript"],
                "covered_languages": ["python", "typescript"],
            },
            "risk_assessment": {
                "status": "reviewed",
                "tracking_ready": True,
                "false_positive_candidate_count": 0,
                "false_negative_candidate_count": 0,
                "failure_class_drift_candidate_count": 0,
                "score_delta_review_count": 0,
                "risk_case_count": 0,
            },
        }
        EvidenceReadinessSafetyTests._bind_semantic_sources_to_packet(
            calibration,
            EvidenceReadinessSafetyTests._semantic_collection_packet(
                calibration
            ),
        )
        EvidenceReadinessSafetyTests._bind_semantic_sources_to_review_receipt(
            calibration
        )
        return calibration, semantic_harness

    @staticmethod
    def _semantic_collection_packet(calibration: dict) -> dict:
        packet_cases = []
        allocation_counts: dict[str, int] = {}
        for case in calibration.get("cases", []):
            case_id = str(case.get("case_id", ""))
            source = case.get("sources", {}).get("llm_judge", {})
            metadata = (
                source.get("metadata")
                if isinstance(source.get("metadata"), dict)
                else {}
            )
            sdk_language = str(
                metadata.get("semantic_collection_case_sdk_language")
                or metadata.get("sdk_language")
                or "python"
            ).lower()
            prompt_template_id = str(
                metadata.get(
                    "semantic_collection_case_prompt_template_id"
                )
                or metadata.get("prompt_template_id")
                or "a2_semantic_judge_prompt_v1"
            )
            prompt_material_sha256 = str(
                metadata.get(
                    "semantic_collection_case_prompt_material_sha256"
                )
                or metadata.get("prompt_hash")
                or stable_hash({"case_id": case_id})
            )
            allocation_counts[sdk_language] = (
                allocation_counts.get(sdk_language, 0) + 1
            )
            packet_cases.append(
                {
                    "case_id": case_id,
                    "scenario_id": str(case.get("scenario_id", "")),
                    "sdk_language": sdk_language,
                    "prompt_template_id": prompt_template_id,
                    "prompt_material_sha256": prompt_material_sha256,
                    "prompt_material_sha256_12": (
                        prompt_material_sha256.removeprefix("sha256:")[:12]
                    ),
                }
            )
        packet_core = {
            "schema_version": "a2.semantic_judge_collection_packet.v1",
            "packet_id": "synthetic_c4_collection_packet",
            "dataset_id": calibration.get("dataset_id", ""),
            "case_count": len(packet_cases),
            "target_observation_count": len(packet_cases),
            "sdk_language_plan": {
                "allocation_counts": dict(sorted(allocation_counts.items()))
            },
            "semantic_judge_contract": {
                "prompt_template_id": (
                    packet_cases[0]["prompt_template_id"]
                    if packet_cases
                    else "a2_semantic_judge_prompt_v1"
                )
            },
            "cases": packet_cases,
        }
        return {
            **packet_core,
            "artifact_hash": stable_hash(packet_core),
        }

    @staticmethod
    def _bind_semantic_sources_to_packet(
        calibration: dict,
        packet: dict,
    ) -> None:
        binding = semantic_collection_packet_binding(packet)
        for case in calibration.get("cases", []):
            case_id = case["case_id"]
            source = case.get("sources", {}).get("llm_judge")
            if not isinstance(source, dict):
                continue
            expected_case = binding["cases"][case_id]
            source["metadata"].update(
                {
                    "semantic_collection_packet_schema_version": binding[
                        "schema_version"
                    ],
                    "semantic_collection_packet_id": binding["packet_id"],
                    "semantic_collection_packet_sha256": binding[
                        "packet_sha256"
                    ],
                    "semantic_collection_dataset_id": binding["dataset_id"],
                    "semantic_collection_case_count": binding["case_count"],
                    "semantic_collection_target_observation_count": binding[
                        "target_observation_count"
                    ],
                    "semantic_collection_case_id": case_id,
                    "semantic_collection_case_sdk_language": expected_case[
                        "sdk_language"
                    ],
                    "semantic_collection_case_prompt_template_id": (
                        expected_case["prompt_template_id"]
                    ),
                    "semantic_collection_case_prompt_material_sha256": (
                        expected_case["prompt_material_sha256"]
                    ),
                }
            )

    @staticmethod
    def _bind_semantic_sources_to_review_receipt(
        calibration: dict,
    ) -> None:
        receipt_cases = []
        sources = []
        for case in calibration.get("cases", []):
            source = case.get("sources", {}).get("llm_judge")
            if not isinstance(source, dict):
                continue
            metadata = source["metadata"]
            receipt_cases.append(
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
            sources.append(source)
        receipt = {
            "schema_version": "a2.semantic_human_review_receipt.v1",
            "verification_state": "verified",
            "review_scope": "a2_c4_semantic_judge_acceptance",
            "expected_case_count": len(receipt_cases),
            "reviewed_case_count": len(receipt_cases),
            "receipt_complete": True,
            "public_safe": True,
            "raw_review_notes_included": False,
            "raw_reviewer_identity_included": False,
            "cases": receipt_cases,
        }
        receipt_hash = stable_hash(receipt)
        for source in sources:
            source["metadata"].update(
                {
                    "semantic_review_receipt_sha256": receipt_hash,
                    "semantic_review_receipt_schema_version": receipt[
                        "schema_version"
                    ],
                    "semantic_review_verification_state": receipt[
                        "verification_state"
                    ],
                    "semantic_review_scope": receipt["review_scope"],
                    "semantic_review_expected_case_count": receipt[
                        "expected_case_count"
                    ],
                    "semantic_review_reviewed_case_count": receipt[
                        "reviewed_case_count"
                    ],
                    "semantic_review_receipt_complete": receipt[
                        "receipt_complete"
                    ],
                    "semantic_review_receipt_public_safe": receipt[
                        "public_safe"
                    ],
                    "semantic_review_raw_review_notes_included": receipt[
                        "raw_review_notes_included"
                    ],
                    "semantic_review_raw_reviewer_identity_included": receipt[
                        "raw_reviewer_identity_included"
                    ],
                }
            )
        calibration["semantic_human_review_receipt"] = receipt

    @staticmethod
    def _append_extra_review_receipt_case(receipt: dict) -> None:
        extra_case = deepcopy(receipt["cases"][0])
        extra_case["case_id"] = "synthetic-extra-case"
        receipt["cases"].append(extra_case)
        receipt["expected_case_count"] = len(receipt["cases"])
        receipt["reviewed_case_count"] = len(receipt["cases"])

    @staticmethod
    def _official_smoke() -> dict:
        call_names = (
            "init",
            "health_check",
            "list_datasets",
            "list_runs",
            "list_requests",
            "list_agents",
        )
        return {
            "schema_version": "a2.real_api_smoke.v1",
            "api_call_count": len(call_names),
            "calls": [{"name": name, "status": "ok"} for name in call_names],
            "all_required_calls_reached": True,
        }

    @staticmethod
    def _native_media_surface_receipt() -> dict:
        root = Path(__file__).resolve().parents[2]
        return json.loads(
            (
                root / "docs/evidence/a2_releasefoundry_native_media_surface.json"
            ).read_text(encoding="utf-8")
        )

    @staticmethod
    def _generated_artifact_probe_inputs() -> tuple[list[tuple[str, dict]], dict]:
        paths = [
            "docs/evidence/a2_multimodal_image_real_api_smoke.json",
            "docs/evidence/a2_multimodal_audio_real_api_smoke.json",
            "docs/evidence/a2_multimodal_file_real_api_smoke.json",
        ]
        probes = [
            (path, deepcopy(_multimodal_real_api_smoke_summary(path)))
            for path in paths
        ]
        native_surface = _releasefoundry_native_media_surface_summary(
            "docs/evidence/a2_releasefoundry_native_media_surface.json"
        )
        return probes, native_surface

    @staticmethod
    def _multimodal_smoke(
        *,
        modality: str = "image",
        request_content_sha256: str = "a" * 64,
    ) -> dict:
        calls = [
            {"name": "init", "status": "ok"},
            {"name": "create_request", "status": "ok"},
        ]
        generation_option_by_modality = {
            "image": "generate_images",
            "audio": "generate_audio",
            "file": "generate_files",
        }
        response_mime_by_modality = {
            "image": "image/png",
            "audio": "audio/mpeg",
            "file": "application/pdf",
        }
        generation_options = {
            "generate_audio": False,
            "generate_files": False,
            "generate_images": False,
            "generate_videos": False,
        }
        generation_options[generation_option_by_modality[modality]] = True
        return {
            "schema_version": "a2.multimodal_real_api_smoke.v1",
            "request_content_sha256": request_content_sha256,
            "requested_modalities": ["text", modality],
            "required_modalities": ["text", modality],
            "excluded_modalities": [
                value
                for value in ("image", "audio", "file", "video")
                if value != modality
            ],
            "request_config_accepted_modalities": ["text", modality],
            "observed_artifact_modalities": ["text", modality],
            "accepted_modalities": ["text"],
            "generation_options": generation_options,
            "artifact_origin": "releasefoundry_generated_dataset",
            "artifact_receipt_status": "verified",
            "artifact_reference_count": 1,
            "artifact_download_attempt_count": 1,
            "artifact_download_verified_count": 1,
            "artifact_reference_modalities": [modality],
            "artifact_verified_modalities": [modality],
            "artifact_missing_modalities": [],
            "artifact_modality_coverage_complete": True,
            "artifact_receipts": [
                {
                    "modality": modality,
                    "verification_status": "verified",
                    "sha256": "a" * 64,
                    "byte_size": 5,
                    "response_mime": response_mime_by_modality[modality],
                }
            ],
            "artifact_receipts_public_safe": True,
            "api_call_count": len(calls),
            "calls": calls,
            "all_required_modalities_requested": True,
            "create_request_reached": True,
            "wait_completed": True,
            "dataset_id_present": True,
            "dataset_request_binding_verified": True,
            "native_media_uploaded": False,
            "media_upload_api_observed": False,
            "public_safe": True,
            "c3_grading_ready": False,
        }
