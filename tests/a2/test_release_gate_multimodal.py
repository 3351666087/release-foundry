import json
import unittest

from scripts.a2_build_release_gate_report import _multimodal_expected_bindings
from scripts.a2_ollama_multimodal_matrix import ROOT
from services.judge.release_gate import build_release_gate_report


class ReleaseGateMultimodalTests(unittest.TestCase):
    def _inputs(self):
        load = lambda name: json.loads(
            (ROOT / "fixtures/a2/results" / name).read_text(encoding="utf-8")
        )
        return (
            load("a2_commercial_readiness_report.json"),
            load("a2_evidence_readiness_report.json"),
            load("a2_g3_calibration_matrix.json"),
            load("a2_regression_replay_report.json"),
            load("a2_scenario_selection_report.json"),
        )

    def test_image_candidate_missing_multimodal_artifact_is_blocked(self):
        report = build_release_gate_report(
            *self._inputs(), modality_scope=["text", "image"]
        )
        blockers = [
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        ]
        self.assertEqual(report["decision"], "block")
        self.assertEqual(report["multimodal_qualification_blocker_count"], 1)
        self.assertEqual(len(blockers), 1)
        self.assertIn(
            "multimodal qualification artifact is missing", blockers[0]["gaps"]
        )

    def test_provider_failure_or_usage_gap_cannot_pass_image_gate(self):
        artifact = {
            "qualification_state": "blocked",
            "blockers": ["dashscope_provider_failure_observed"],
            "usage_cost_receipt": {
                "usage_accounting_state": "missing_or_invalid",
                "pricing_state": "unavailable",
                "within_cost_budget": False,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        )
        self.assertEqual(report["decision"], "block")
        self.assertIn(
            "multimodal usage or pricing qualification is incomplete",
            blocker["gaps"],
        )

    def test_text_only_candidate_does_not_require_visual_qualification(self):
        report = build_release_gate_report(
            *self._inputs(), modality_scope=["text"]
        )
        self.assertNotIn("multimodal_qualification", report)
        self.assertFalse(
            any(
                item["type"] == "multimodal_qualification_gate"
                for item in report["blockers"]
            )
        )

    def test_qualified_image_artifact_must_match_expected_bindings(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "model_id": "qwen-vl-plus",
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": "sha256:" + "b" * 64,
                "model_id": "qwen-vl-plus",
            },
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        )
        self.assertIn(
            "multimodal qualification binding mismatch: manifest_hash",
            blocker["gaps"],
        )

    def test_qualified_image_artifact_with_exact_bindings_adds_no_mm_blocker(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "model_id": "qwen-vl-plus",
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": artifact["manifest_hash"],
                "model_id": artifact["model_id"],
            },
        )
        self.assertFalse(
            any(
                item["type"] == "multimodal_qualification_gate"
                for item in report["blockers"]
            )
        )

    def test_stale_qualified_artifact_from_prior_candidate_is_blocked(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "b" * 64,
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": "c" * 40,
                "manifest_hash": artifact["manifest_hash"],
            },
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        )
        self.assertIn(
            "multimodal qualification binding mismatch: candidate_sha",
            blocker["gaps"],
        )

    def test_release_gate_cli_builds_mandatory_exact_bindings(self):
        bindings = _multimodal_expected_bindings(
            modality_scope=["image"],
            binding_file=None,
            candidate_sha="d" * 40,
            dataset_manifest_hash="sha256:" + "e" * 64,
        )
        self.assertEqual(
            bindings,
            {
                "candidate_sha": "d" * 40,
                "manifest_hash": "sha256:" + "e" * 64,
            },
        )

    def test_release_gate_cli_rejects_missing_candidate_sha(self):
        with self.assertRaisesRegex(SystemExit, "--candidate-sha is required"):
            _multimodal_expected_bindings(
                modality_scope=["image"],
                binding_file=None,
                candidate_sha=None,
                dataset_manifest_hash="sha256:" + "e" * 64,
            )
