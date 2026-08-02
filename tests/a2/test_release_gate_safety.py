import json
import unittest
from copy import deepcopy
from pathlib import Path

from services.judge.release_gate import (
    apply_a1_output_policy_gate,
    build_release_gate_report,
    verify_release_gate_artifact,
)
from services.judge.result_persistence import stable_hash
from services.judge.unblock_checklist import build_release_unblock_checklist


ROOT = Path(__file__).resolve().parents[2]


class ReleaseGateSafetyTests(unittest.TestCase):
    def test_release_gate_artifact_binds_all_sources_and_judge_registry(self):
        commercial, evidence, calibration, replay, scenario_selection = (
            self._release_inputs()
        )
        evidence_index = self._load(
            "docs/a1/api_calibration/real_api_evidence_index.json"
        )
        judge_registry = self._load(
            "fixtures/a2/results/a2_judge_versions.json"
        )
        case_book = self._load("fixtures/a2/results/a2_case_book.json")

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
            evidence_index,
            judge_version_registry=judge_registry,
            case_book_report=case_book,
        )

        self.assertEqual(
            report["source_commercial_readiness_hash"],
            stable_hash(commercial),
        )
        self.assertEqual(
            report["source_evidence_readiness_hash"],
            stable_hash(evidence),
        )
        self.assertEqual(
            report["source_calibration_matrix_hash"],
            stable_hash(calibration),
        )
        self.assertEqual(
            report["source_case_book_hash"],
            stable_hash(case_book),
        )
        self.assertEqual(
            report["source_regression_replay_hash"],
            stable_hash(replay),
        )
        self.assertEqual(
            report["source_scenario_selection_hash"],
            stable_hash(scenario_selection),
        )
        self.assertEqual(
            report["source_a1_evidence_index_hash"],
            stable_hash(evidence_index),
        )
        self.assertEqual(
            report["source_judge_registry_hash"],
            stable_hash(judge_registry),
        )
        self.assertEqual(
            report["judge_registry_hash"],
            judge_registry["registry_hash"],
        )
        self.assertEqual(
            report["artifact_hash"],
            stable_hash(
                {
                    key: value
                    for key, value in report.items()
                    if key != "artifact_hash"
                }
            ),
        )
        self.assertEqual(
            verify_release_gate_artifact(
                report,
                commercial_readiness_report=commercial,
                evidence_readiness_report=evidence,
                calibration_matrix=calibration,
                case_book_report=case_book,
                regression_replay_report=replay,
                scenario_selection_report=scenario_selection,
                a1_evidence_index=evidence_index,
                judge_version_registry=judge_registry,
            ),
            report["artifact_hash"],
        )

    def test_release_gate_verifier_rejects_content_and_source_tampering(self):
        commercial, evidence, calibration, replay, scenario_selection = (
            self._release_inputs()
        )
        evidence_index = self._load(
            "docs/a1/api_calibration/real_api_evidence_index.json"
        )
        judge_registry = self._load(
            "fixtures/a2/results/a2_judge_versions.json"
        )
        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
            evidence_index,
            judge_version_registry=judge_registry,
        )

        tampered_decision = deepcopy(report)
        tampered_decision["decision"] = "pass"
        with self.assertRaisesRegex(ValueError, "artifact_hash"):
            verify_release_gate_artifact(tampered_decision)

        tampered_blockers = deepcopy(report)
        tampered_blockers["blockers"].clear()
        with self.assertRaisesRegex(ValueError, "artifact_hash"):
            verify_release_gate_artifact(tampered_blockers)

        stale_source = deepcopy(commercial)
        stale_source["current_gate"] = "C6"
        with self.assertRaisesRegex(
            ValueError,
            "source_commercial_readiness_hash",
        ):
            verify_release_gate_artifact(
                report,
                commercial_readiness_report=stale_source,
            )

    def test_release_gate_verifier_rebuilds_complete_authoritative_sources(self):
        commercial, evidence, calibration, replay, scenario_selection = (
            self._release_inputs()
        )
        case_book = self._load("fixtures/a2/results/a2_case_book.json")
        evidence_index = self._load(
            "docs/a1/api_calibration/real_api_evidence_index.json"
        )
        judge_registry = self._load(
            "fixtures/a2/results/a2_judge_versions.json"
        )
        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
            evidence_index,
            judge_version_registry=judge_registry,
            case_book_report=case_book,
        )
        forged = deepcopy(report)
        forged.update(
            {
                "decision": "pass",
                "exit_code": 0,
                "risk_score": 0,
                "blockers": [],
                "warnings": [],
            }
        )
        forged["artifact_hash"] = stable_hash(
            {
                key: value
                for key, value in forged.items()
                if key != "artifact_hash"
            }
        )

        with self.assertRaisesRegex(ValueError, "rebuilt from supplied sources"):
            verify_release_gate_artifact(
                forged,
                commercial_readiness_report=commercial,
                evidence_readiness_report=evidence,
                calibration_matrix=calibration,
                case_book_report=case_book,
                regression_replay_report=replay,
                scenario_selection_report=scenario_selection,
                a1_evidence_index=evidence_index,
                judge_version_registry=judge_registry,
            )

    def test_a1_output_policy_patch_reseals_release_gate(self):
        commercial, evidence, calibration, replay, scenario_selection = (
            self._release_inputs()
        )
        evidence_index = self._load(
            "docs/a1/api_calibration/real_api_evidence_index.json"
        )
        judge_registry = self._load(
            "fixtures/a2/results/a2_judge_versions.json"
        )
        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
            evidence_index,
            judge_version_registry=judge_registry,
        )
        patched_index = deepcopy(evidence_index)
        patched_index["output_policy_counts"][
            "unsafe_real_nonprivate_override"
        ] = 1

        patched = apply_a1_output_policy_gate(report, patched_index)

        self.assertNotEqual(patched["artifact_hash"], report["artifact_hash"])
        self.assertEqual(
            patched["source_a1_evidence_index_hash"],
            stable_hash(patched_index),
        )
        self.assertEqual(
            verify_release_gate_artifact(
                patched,
                a1_evidence_index=patched_index,
            ),
            patched["artifact_hash"],
        )

    def test_release_gate_requires_explicit_boolean_evidence_flags(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        evidence["releasefoundry_public_merge_gate"]["safe_to_mark_c3_met"] = "false"
        evidence["semantic_live_merge_gate"]["safe_to_mark_c4_met"] = 1

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
        )

        evidence_blocker_gates = {
            blocker["gate"]
            for blocker in report["blockers"]
            if blocker["type"] == "evidence_gate"
        }
        self.assertLessEqual({"C3", "C4"}, evidence_blocker_gates)

    def test_release_gate_fails_closed_for_malformed_evidence_gate_objects(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        evidence["releasefoundry_public_merge_gate"] = "false"
        evidence["semantic_live_merge_gate"] = None

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
        )

        evidence_blocker_gates = {
            blocker["gate"]
            for blocker in report["blockers"]
            if blocker["type"] == "evidence_gate"
        }
        self.assertLessEqual({"C3", "C4"}, evidence_blocker_gates)

    def test_release_gate_does_not_report_non_boolean_commercial_readiness(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        commercial["ready_for_commercial_gate"] = "false"

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
        )

        self.assertFalse(report["ready_for_commercial_gate"])

    def test_release_gate_rejects_malformed_commercial_gate_details(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        malformed_values = (None, 1, "missing")

        for field in ("gaps", "evidence_refs"):
            for value in malformed_values:
                with self.subTest(field=field, value=value):
                    candidate_commercial = deepcopy(commercial)
                    c0_gate = next(
                        gate
                        for gate in candidate_commercial["gate_status"]
                        if gate["gate"] == "C0"
                    )
                    c0_gate[field] = value

                    report = build_release_gate_report(
                        candidate_commercial,
                        evidence,
                        calibration,
                        replay,
                        scenario_selection,
                    )
                    blocker = next(
                        blocker
                        for blocker in report["blockers"]
                        if blocker["type"] == "commercial_gate"
                        and blocker["gate"] == "C0"
                    )

                    self.assertEqual(report["decision"], "block")
                    self.assertIn(field, blocker["invalid_fields"])
                    self.assertTrue(
                        all(
                            isinstance(item, str)
                            for item in blocker["gaps"]
                            + blocker["evidence_refs"]
                        )
                    )

    def test_release_gate_rejects_duplicate_hard_gate_entries(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        candidate_commercial = deepcopy(commercial)
        duplicate = deepcopy(
            next(
                gate
                for gate in candidate_commercial["gate_status"]
                if gate["gate"] == "C0"
            )
        )
        candidate_commercial["gate_status"].append(duplicate)

        report = build_release_gate_report(
            candidate_commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
        )
        blocker = next(
            blocker
            for blocker in report["blockers"]
            if blocker["type"] == "commercial_gate"
            and blocker["gate"] == "C0"
        )

        self.assertEqual(report["decision"], "block")
        self.assertIn("gate_status", blocker["invalid_fields"])
        self.assertIn(
            "duplicate commercial gate entries found: C0",
            blocker["gaps"],
        )

    def test_release_gate_rejects_non_boolean_scenario_readiness(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        scenario_selection["coverage_summary"]["coverage_ready"] = "false"
        scenario_selection["minimums_summary"]["minimums_ready"] = "false"

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
        )

        self.assertEqual(report["scenario_selection_gate"]["status"], "needs_attention")
        self.assertEqual(report["scenario_selection_blocker_count"], 1)

    def test_release_gate_blocks_when_scenario_selection_evidence_is_missing(self):
        commercial, evidence, calibration, replay, _ = self._release_inputs()

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            None,
        )

        gate = report["scenario_selection_gate"]
        self.assertEqual(report["decision"], "block")
        self.assertEqual(gate["status"], "needs_attention")
        self.assertFalse(gate["ready"])
        self.assertFalse(gate["coverage_ready"])
        self.assertFalse(gate["minimums_ready"])
        self.assertEqual(report["scenario_selection_blocker_count"], 1)
        self.assertIn("missing or malformed", gate["gaps"][0])

    def test_release_gate_blocks_on_malformed_a1_dangerous_counts(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        evidence_index = self._load("docs/a1/api_calibration/real_api_evidence_index.json")
        malformed_values = (True, False, 1.5, -1, "1", "invalid", {}, [], None)

        for field in (
            "unsafe_real_nonprivate_override",
            "private_required_but_not_private",
        ):
            for value in malformed_values:
                with self.subTest(field=field, value=value):
                    candidate_index = deepcopy(evidence_index)
                    candidate_index["output_policy_counts"][field] = value
                    report = build_release_gate_report(
                        commercial,
                        evidence,
                        calibration,
                        replay,
                        scenario_selection,
                        candidate_index,
                    )
                    gate = report["a1_output_policy_gate"]
                    blockers = [
                        blocker
                        for blocker in report["blockers"]
                        if blocker["type"] == "a1_output_policy_gate"
                    ]

                    self.assertEqual(gate["status"], "blocked")
                    self.assertFalse(gate["ready"])
                    self.assertIn(field, gate["invalid_dangerous_count_fields"])
                    self.assertEqual(report["a1_output_policy_blocker_count"], 1)
                    self.assertEqual(len(blockers), 1)
                    self.assertIn(
                        field,
                        blockers[0]["invalid_dangerous_count_fields"],
                    )

    def test_release_gate_blocks_when_a1_output_policy_evidence_is_missing(self):
        commercial, evidence, calibration, replay, scenario_selection = (
            self._release_inputs()
        )

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
            None,
        )

        self.assertEqual(report["decision"], "block")
        self.assertEqual(report["a1_output_policy_gate"]["status"], "blocked")
        self.assertFalse(report["a1_output_policy_gate"]["ready"])
        self.assertEqual(report["a1_output_policy_blocker_count"], 1)
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "a1_output_policy_gate"
        )
        self.assertIn("missing or malformed", blocker["gaps"][0])

    def test_a1_output_policy_gate_fails_closed_for_malformed_release_report(self):
        evidence_index = self._load(
            "docs/a1/api_calibration/real_api_evidence_index.json"
        )

        for malformed_report in (None, "invalid", [], True):
            with self.subTest(report=malformed_report):
                report = apply_a1_output_policy_gate(
                    malformed_report,
                    evidence_index,
                )
                integrity_blockers = [
                    blocker
                    for blocker in report["blockers"]
                    if blocker["type"] == "release_gate_report_integrity"
                ]

                self.assertEqual(report["decision"], "block")
                self.assertEqual(report["exit_code"], 2)
                self.assertEqual(len(integrity_blockers), 1)
                self.assertIn(
                    "release gate report must be an object",
                    integrity_blockers[0]["gaps"],
                )

    def test_a1_output_policy_gate_rejects_malformed_blockers_and_warnings(self):
        release_gate, _, _, _ = self._checklist_inputs()
        evidence_index = self._load(
            "docs/a1/api_calibration/real_api_evidence_index.json"
        )
        malformed_values = (None, {}, "invalid", [None], [release_gate["blockers"][0], None])

        for field in ("blockers", "warnings"):
            for value in malformed_values:
                with self.subTest(field=field, value=value):
                    candidate = deepcopy(release_gate)
                    candidate[field] = value
                    report = apply_a1_output_policy_gate(
                        candidate,
                        evidence_index,
                    )
                    integrity_blockers = [
                        blocker
                        for blocker in report["blockers"]
                        if blocker["type"] == "release_gate_report_integrity"
                    ]

                    self.assertEqual(report["decision"], "block")
                    self.assertEqual(report["exit_code"], 2)
                    self.assertEqual(len(integrity_blockers), 1)
                    self.assertTrue(
                        any(
                            gap.startswith(field)
                            for gap in integrity_blockers[0]["gaps"]
                        )
                    )
                    self.assertTrue(
                        all(
                            isinstance(item, dict)
                            for item in report["blockers"]
                        )
                    )
                    self.assertTrue(
                        all(
                            isinstance(item, dict)
                            for item in report["warnings"]
                        )
                    )

    def test_release_gate_rejects_malformed_external_evidence_counts(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        malformed_values = (True, False, 1.5, -1, "1", "invalid", {}, [], None)
        gate_fields = (
            (
                "C3",
                "releasefoundry_public_merge_gate",
                "safe_to_mark_c3_met",
                "missing_reviewed_observation_count",
            ),
            (
                "C4",
                "semantic_live_merge_gate",
                "safe_to_mark_c4_met",
                "missing_audited_observation_count",
            ),
        )

        for gate_name, source, safe_field, count_field in gate_fields:
            for value in malformed_values:
                with self.subTest(gate=gate_name, value=value):
                    candidate_evidence = deepcopy(evidence)
                    candidate_evidence[source][safe_field] = True
                    candidate_evidence[source][count_field] = value

                    report = build_release_gate_report(
                        commercial,
                        candidate_evidence,
                        calibration,
                        replay,
                        scenario_selection,
                    )
                    blocker = next(
                        blocker
                        for blocker in report["blockers"]
                        if blocker["type"] == "evidence_gate"
                        and blocker["gate"] == gate_name
                    )

                    self.assertEqual(report["decision"], "block")
                    self.assertGreaterEqual(blocker["missing_count"], 1)
                    self.assertIn(
                        count_field,
                        blocker["invalid_count_fields"],
                    )

    def test_release_gate_rejects_malformed_calibration_source_counts(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        malformed_values = (True, False, 1.5, -1, "1", "invalid", {}, [], None)

        for value in malformed_values:
            with self.subTest(value=value):
                candidate_calibration = deepcopy(calibration)
                candidate_calibration["source_coverage"]["releasefoundry_grading"][
                    "missing"
                ] = value

                report = build_release_gate_report(
                    commercial,
                    evidence,
                    candidate_calibration,
                    replay,
                    scenario_selection,
                )
                blocker = next(
                    blocker
                    for blocker in report["blockers"]
                    if blocker["type"] == "calibration_gap"
                )

                self.assertEqual(report["decision"], "block")
                self.assertGreaterEqual(blocker["missing_count"], 1)
                self.assertIn(
                    "source_coverage.releasefoundry_grading.missing",
                    blocker["invalid_count_fields"],
                )

        for field, value in (
            ("source_coverage", "invalid"),
            ("source_coverage", None),
            ("releasefoundry_grading", []),
            ("releasefoundry_grading", "invalid"),
        ):
            with self.subTest(field=field, value=value):
                candidate_calibration = deepcopy(calibration)
                if field == "source_coverage":
                    candidate_calibration[field] = value
                else:
                    candidate_calibration["source_coverage"][field] = value

                report = build_release_gate_report(
                    commercial,
                    evidence,
                    candidate_calibration,
                    replay,
                    scenario_selection,
                )
                blockers = [
                    blocker
                    for blocker in report["blockers"]
                    if blocker["type"] == "calibration_gap"
                ]

                self.assertEqual(report["decision"], "block")
                self.assertEqual(len(blockers), 1)
                self.assertIn(
                    "source_coverage.releasefoundry_grading.missing",
                    blockers[0]["invalid_count_fields"],
                )

    def test_release_gate_rejects_malformed_regression_blocking_counts(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        malformed_values = (True, False, 1.5, -1, "1", "invalid", {}, [], None)

        for value in malformed_values:
            with self.subTest(value=value):
                candidate_replay = deepcopy(replay)
                candidate_replay["release_gate_summary"]["blocking_count"] = value

                report = build_release_gate_report(
                    commercial,
                    evidence,
                    calibration,
                    candidate_replay,
                    scenario_selection,
                )
                blocker = next(
                    blocker
                    for blocker in report["blockers"]
                    if blocker["type"] == "regression_maturity"
                )

                self.assertEqual(report["decision"], "block")
                self.assertGreaterEqual(blocker["missing_count"], 1)
                self.assertIn(
                    "release_gate_summary.blocking_count",
                    blocker["invalid_count_fields"],
                )

    def test_release_gate_rejects_resealed_forged_mature_replay(self):
        commercial, evidence, calibration, replay, scenario_selection = (
            self._release_inputs()
        )
        case_book = self._load("fixtures/a2/results/a2_case_book.json")
        c5_gate = next(
            gate for gate in commercial["gate_status"] if gate.get("gate") == "C5"
        )
        c5_gate["status"] = "met"
        c5_gate["gaps"] = []
        replay["maturity_status"] = "mature"
        replay["maturity_gate"].update(
            {
                "status": "mature",
                "ready": True,
                "missing_replay_case_count": 0,
                "missing_reviewed_evidence_count": 0,
                "missing_reviewed_replay_cases": 0,
                "gaps": [],
            }
        )
        replay["release_gate_summary"].update(
            {
                "status": "mature",
                "release_gate_status": "ready",
                "blocks_release": False,
                "blocking_count": 0,
                "missing_replay_case_count": 0,
                "missing_reviewed_evidence_count": 0,
                "gaps": [],
            }
        )
        replay_core = {
            key: value for key, value in replay.items() if key != "artifact_hash"
        }
        replay["artifact_hash"] = stable_hash(replay_core)

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
            case_book_report=case_book,
        )
        integrity_blocker = next(
            blocker
            for blocker in report["blockers"]
            if blocker["type"] == "regression_replay_integrity"
        )

        self.assertEqual(report["decision"], "block")
        self.assertEqual(integrity_blocker["gate"], "C5")
        self.assertEqual(integrity_blocker["severity"], "critical")
        self.assertIn("rebuilt", integrity_blocker["gaps"][0])

    def test_release_gate_safely_normalizes_warning_and_preflight_objects(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        commercial["evidence_snapshot"] = "invalid"
        evidence["a1_real_api_evidence"] = ["invalid"]
        evidence["releasefoundry_grading_preflight"] = None
        evidence["semantic_judge_preflight"] = "invalid"

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
        )

        self.assertEqual(report["decision"], "block")
        for item in report["required_evidence"]:
            self.assertEqual(item["required_count"], 0)
            self.assertEqual(item["current_available"], 0)
            self.assertEqual(item["commands"], [])
            self.assertTrue(item["invalid_count_fields"])

    def test_release_gate_marks_malformed_warning_counts(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        commercial["evidence_snapshot"]["semantic_score_delta_reviews"] = "4"
        quota_gate = evidence["a1_real_api_evidence"]["real_quota_gate"]
        quota_gate["blocked_count"] = True
        gate_validation = evidence["a1_real_api_evidence"][
            "api_probe_gate_validation"
        ]
        gate_validation["error_validate_gate_count"] = -1
        gate_validation["blocked_plan_batch_count"] = "3"

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
        )
        invalid_fields = {
            field
            for warning in report["warnings"]
            for field in warning.get("invalid_count_fields", [])
        }

        self.assertIn(
            "evidence_snapshot.semantic_score_delta_reviews",
            invalid_fields,
        )
        self.assertIn(
            "a1_real_api_evidence.real_quota_gate.blocked_count",
            invalid_fields,
        )
        self.assertIn(
            "a1_real_api_evidence.api_probe_gate_validation."
            "error_validate_gate_count",
            invalid_fields,
        )
        self.assertIn(
            "a1_real_api_evidence.api_probe_gate_validation."
            "blocked_plan_batch_count",
            invalid_fields,
        )

    def test_release_gate_rejects_malformed_scenario_count(self):
        commercial, evidence, calibration, replay, scenario_selection = self._release_inputs()
        scenario_selection["selected_scenario_count"] = "12"

        report = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
        )

        self.assertEqual(
            report["scenario_selection_gate"]["status"],
            "needs_attention",
        )
        self.assertEqual(report["scenario_selection_blocker_count"], 1)
        self.assertIn(
            "selected_scenario_count",
            report["scenario_selection_gate"]["invalid_count_fields"],
        )

    def test_release_gate_fails_closed_for_malformed_top_level_inputs(self):
        report = build_release_gate_report(
            None,
            "invalid",
            [],
            regression_replay_report="invalid",
            scenario_selection_report=["invalid"],
        )

        self.assertEqual(report["decision"], "block")
        self.assertEqual(report["blocking_gate_count"], 6)
        self.assertGreaterEqual(report["evidence_blocker_count"], 3)
        self.assertFalse(report["ready_for_commercial_gate"])

    def test_unblock_checklist_requires_explicit_boolean_safe_flags(self):
        release_gate, evidence, replay, promotion_queue = self._checklist_inputs()
        for gate_name, field in (
            ("C3", "safe_to_mark_c3_met"),
            ("C4", "safe_to_mark_c4_met"),
        ):
            source = "releasefoundry_public_merge_gate" if gate_name == "C3" else "semantic_live_merge_gate"
            for value in ("false", 1, {}, []):
                with self.subTest(gate=gate_name, value=value):
                    candidate_evidence = deepcopy(evidence)
                    candidate_evidence[source][field] = value
                    report = build_release_unblock_checklist(
                        release_gate,
                        candidate_evidence,
                        replay,
                        promotion_queue,
                    )
                    gates = {item["gate"]: item for item in report["gate_items"]}
                    self.assertTrue(gates[gate_name]["blocks_release"])

    def test_unblock_checklist_rejects_tampered_release_gate_artifact(self):
        commercial, evidence, calibration, replay, scenario_selection = (
            self._release_inputs()
        )
        promotion_queue = self._load(
            "fixtures/a2/results/a2_regression_promotion_queue.json"
        )
        release_gate = build_release_gate_report(
            commercial,
            evidence,
            calibration,
            replay,
            scenario_selection,
            self._load(
                "docs/a1/api_calibration/real_api_evidence_index.json"
            ),
            judge_version_registry=self._load(
                "fixtures/a2/results/a2_judge_versions.json"
            ),
        )
        tampered = deepcopy(release_gate)
        tampered["decision"] = "pass"

        report = build_release_unblock_checklist(
            tampered,
            evidence,
            replay,
            promotion_queue,
        )

        self.assertFalse(report["release_gate_artifact_verified"])
        self.assertEqual(report["overall_status"], "blocked")
        self.assertEqual(
            report["source_release_gate_artifact_hash"],
            release_gate["artifact_hash"],
        )
        self.assertEqual(
            report["source_release_gate_snapshot_hash"],
            stable_hash(tampered),
        )
        self.assertIn(
            "sealed source release gate",
            report["a3_consumption_summary"]["primary_action"],
        )

    def test_unblock_checklist_rejects_resealed_forged_ready_gate(self):
        commercial, evidence, calibration, replay, scenario_selection = (
            self._release_inputs()
        )
        case_book = self._load("fixtures/a2/results/a2_case_book.json")
        evidence_index = self._load(
            "docs/a1/api_calibration/real_api_evidence_index.json"
        )
        judge_registry = self._load(
            "fixtures/a2/results/a2_judge_versions.json"
        )
        release_gate = self._load(
            "fixtures/a2/results/a2_release_gate_report.json"
        )
        promotion_queue = self._load(
            "fixtures/a2/results/a2_regression_promotion_queue.json"
        )
        forged_evidence = deepcopy(evidence)
        forged_evidence["releasefoundry_public_merge_gate"].update(
            {
                "safe_to_mark_c3_met": True,
                "missing_reviewed_observation_count": 0,
            }
        )
        forged_evidence["semantic_live_merge_gate"].update(
            {
                "safe_to_mark_c4_met": True,
                "missing_audited_observation_count": 0,
            }
        )
        forged_replay = deepcopy(replay)
        forged_replay["release_gate_summary"].update(
            {
                "blocks_release": False,
                "missing_replay_case_count": 0,
                "missing_reviewed_evidence_count": 0,
                "release_gate_status": "ready",
            }
        )
        forged_gate = deepcopy(release_gate)
        forged_gate.update(
            {
                "decision": "pass",
                "blockers": [],
                "warnings": [],
                "exit_code": 0,
                "risk_score": 0,
            }
        )
        forged_gate["artifact_hash"] = stable_hash(
            {
                key: value
                for key, value in forged_gate.items()
                if key != "artifact_hash"
            }
        )

        report = build_release_unblock_checklist(
            forged_gate,
            forged_evidence,
            forged_replay,
            promotion_queue,
            release_gate_sources={
                "commercial_readiness_report": commercial,
                "evidence_readiness_report": evidence,
                "calibration_matrix": calibration,
                "batch_plan_report": self._load(
                    "fixtures/a2/results/a2_batch_plan_report.json"
                ),
                "semantic_harness_report": self._load(
                    "fixtures/a2/results/a2_semantic_harness_report.json"
                ),
                "releasefoundry_case_map": self._load(
                    "fixtures/a2/calibration/"
                    "releasefoundry_grading_batch_case_map.json"
                ),
                "semantic_collection_packet": self._load(
                    "fixtures/a2/calibration/"
                    "a2_semantic_judge_collection_packet.json"
                ),
                "regression_replay_report": replay,
                "case_book_report": case_book,
                "scenario_selection_report": scenario_selection,
                "a1_evidence_index": evidence_index,
                "judge_version_registry": judge_registry,
            },
        )

        self.assertFalse(report["release_gate_artifact_verified"])
        self.assertEqual(report["overall_status"], "blocked")
        self.assertIn(
            "authoritative source",
            report["a3_consumption_summary"]["primary_action"],
        )

    def test_unblock_checklist_fails_closed_for_non_boolean_c5_block_flag(self):
        release_gate, evidence, replay, promotion_queue = self._checklist_inputs()
        for value in ("false", 0, "", {}, []):
            with self.subTest(value=value):
                candidate_replay = deepcopy(replay)
                candidate_replay["release_gate_summary"]["blocks_release"] = value
                report = build_release_unblock_checklist(
                    release_gate,
                    evidence,
                    candidate_replay,
                    promotion_queue,
                )
                gates = {item["gate"]: item for item in report["gate_items"]}
                self.assertTrue(gates["C5"]["blocks_release"])

    def test_unblock_checklist_rejects_malformed_external_evidence_counts(self):
        release_gate, evidence, replay, promotion_queue = self._checklist_inputs()
        malformed_values = (True, False, 1.5, -1, "1", "invalid", {}, [], None)
        gate_fields = (
            ("C3", "releasefoundry_public_merge_gate", "missing_reviewed_observation_count"),
            ("C4", "semantic_live_merge_gate", "missing_audited_observation_count"),
        )

        for gate_name, source, field in gate_fields:
            for value in malformed_values:
                with self.subTest(gate=gate_name, value=value):
                    candidate_evidence = deepcopy(evidence)
                    candidate_evidence[source][
                        "safe_to_mark_c3_met"
                        if gate_name == "C3"
                        else "safe_to_mark_c4_met"
                    ] = True
                    candidate_evidence[source][field] = value
                    report = build_release_unblock_checklist(
                        release_gate,
                        candidate_evidence,
                        replay,
                        promotion_queue,
                    )
                    gate = {
                        item["gate"]: item
                        for item in report["gate_items"]
                    }[gate_name]

                    self.assertTrue(gate["blocks_release"])
                    self.assertGreaterEqual(gate["missing_count"], 1)
                    self.assertIn(field, gate["invalid_count_fields"])

    def test_unblock_checklist_rejects_malformed_c5_missing_counts(self):
        release_gate, evidence, replay, promotion_queue = self._checklist_inputs()
        malformed_values = (True, False, 1.5, -1, "1", "invalid", {}, [], None)

        for field in (
            "missing_replay_case_count",
            "missing_reviewed_evidence_count",
        ):
            for value in malformed_values:
                with self.subTest(field=field, value=value):
                    candidate_replay = deepcopy(replay)
                    summary = candidate_replay["release_gate_summary"]
                    summary["blocks_release"] = False
                    summary["missing_replay_case_count"] = 0
                    summary["missing_reviewed_evidence_count"] = 0
                    summary[field] = value
                    report = build_release_unblock_checklist(
                        release_gate,
                        evidence,
                        candidate_replay,
                        promotion_queue,
                    )
                    gate = {
                        item["gate"]: item
                        for item in report["gate_items"]
                    }["C5"]

                    self.assertTrue(gate["blocks_release"])
                    self.assertGreaterEqual(gate["missing_count"], 1)
                    self.assertIn(field, gate["invalid_count_fields"])

    def test_unblock_checklist_fails_closed_for_malformed_top_level_inputs(self):
        report = build_release_unblock_checklist(
            None,
            "invalid",
            [],
            regression_promotion_queue="invalid",
        )

        self.assertEqual(report["release_gate_decision"], "block")
        self.assertEqual(report["release_gate_exit_code"], 0)
        self.assertEqual(report["release_gate_risk_score"], 0)
        self.assertEqual(report["overall_status"], "blocked")
        self.assertEqual(report["blocked_gate_count"], 3)
        self.assertNotEqual(
            report["a3_consumption_summary"]["primary_action"],
            "Release gates are ready.",
        )

    def test_unblock_checklist_keeps_source_release_blocker_authoritative(self):
        release_gate, evidence, replay, promotion_queue = self._checklist_inputs()
        evidence["releasefoundry_public_merge_gate"]["safe_to_mark_c3_met"] = True
        evidence["releasefoundry_public_merge_gate"][
            "missing_reviewed_observation_count"
        ] = 0
        evidence["semantic_live_merge_gate"]["safe_to_mark_c4_met"] = True
        evidence["semantic_live_merge_gate"][
            "missing_audited_observation_count"
        ] = 0
        replay["release_gate_summary"]["blocks_release"] = False
        replay["release_gate_summary"]["missing_replay_case_count"] = 0
        replay["release_gate_summary"]["missing_reviewed_evidence_count"] = 0
        release_gate["decision"] = "block"

        report = build_release_unblock_checklist(
            release_gate,
            evidence,
            replay,
            promotion_queue,
        )

        self.assertEqual(report["blocked_gate_count"], 0)
        self.assertEqual(report["overall_status"], "blocked")
        self.assertEqual(
            report["a3_consumption_summary"]["primary_action"],
            "Resolve source release gate blockers before release.",
        )

    def test_unblock_checklist_normalizes_malformed_release_metadata(self):
        release_gate, evidence, replay, promotion_queue = self._checklist_inputs()
        release_gate["decision"] = ["pass"]
        release_gate["exit_code"] = "2"
        release_gate["risk_score"] = True

        report = build_release_unblock_checklist(
            release_gate,
            evidence,
            replay,
            promotion_queue,
        )

        self.assertEqual(report["release_gate_decision"], "block")
        self.assertEqual(report["release_gate_exit_code"], 0)
        self.assertEqual(report["release_gate_risk_score"], 0)
        self.assertEqual(report["overall_status"], "blocked")

    def test_unblock_checklist_filters_malformed_commands_and_private_ref(self):
        release_gate, evidence, replay, promotion_queue = self._checklist_inputs()
        evidence["releasefoundry_public_merge_gate"]["required_commands"] = [
            "run-valid-command",
            1,
            None,
            "",
        ]
        evidence["releasefoundry_grading_preflight"]["private_input_ref"] = None

        report = build_release_unblock_checklist(
            release_gate,
            evidence,
            replay,
            promotion_queue,
        )
        c3_item = {
            item["gate"]: item
            for item in report["gate_items"]
        }["C3"]
        action = c3_item["required_actions"][0]

        self.assertEqual(action["commands"], ["run-valid-command"])
        self.assertEqual(action["private_input_ref"], "")
        self.assertFalse(action["private_evidence_required"])

    @staticmethod
    def _release_inputs() -> tuple[dict, dict, dict, dict, dict]:
        return (
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_commercial_readiness_report.json"),
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_evidence_readiness_report.json"),
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_g3_calibration_matrix.json"),
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_regression_replay_report.json"),
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_scenario_selection_report.json"),
        )

    @staticmethod
    def _checklist_inputs() -> tuple[dict, dict, dict, dict]:
        return (
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_release_gate_report.json"),
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_evidence_readiness_report.json"),
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_regression_replay_report.json"),
            ReleaseGateSafetyTests._load("fixtures/a2/results/a2_regression_promotion_queue.json"),
        )

    @staticmethod
    def _load(path: str) -> dict:
        return json.loads((ROOT / path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
