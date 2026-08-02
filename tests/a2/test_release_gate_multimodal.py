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

    def test_malformed_modality_scope_is_blocked(self):
        malformed_scopes = (
            [],
            "image",
            {"image": True},
            [None],
            ["text", None],
        )
        for modality_scope in malformed_scopes:
            with self.subTest(modality_scope=modality_scope):
                report = build_release_gate_report(
                    *self._inputs(), modality_scope=modality_scope
                )
                blocker = next(
                    item
                    for item in report["blockers"]
                    if item["type"] == "multimodal_scope_gate"
                )
                self.assertEqual(report["decision"], "block")
                self.assertEqual(blocker["gate"], "MM0")
                self.assertEqual(blocker["severity"], "critical")

    def test_modalities_without_qualification_gates_are_blocked(self):
        for modality_scope in (
            ["audio"],
            ["video"],
            ["file"],
            ["text", "audio"],
        ):
            with self.subTest(modality_scope=modality_scope):
                report = build_release_gate_report(
                    *self._inputs(), modality_scope=modality_scope
                )
                blocker = next(
                    item
                    for item in report["blockers"]
                    if item["type"] == "multimodal_scope_gate"
                )
                self.assertEqual(report["decision"], "block")
                self.assertIn(
                    "modality scope has no implemented qualification gate",
                    blocker["gaps"][0],
                )

    def test_duplicate_or_non_canonical_modality_scope_is_blocked(self):
        expected_gap = {
            ("text", "text"): "modality scope contains duplicate entries: text",
            ("Image",): (
                "modality scope contains unknown or non-canonical entries: Image"
            ),
            (" image ",): (
                "modality scope contains unknown or non-canonical entries:  image "
            ),
        }
        for modality_scope, gap in expected_gap.items():
            with self.subTest(modality_scope=modality_scope):
                report = build_release_gate_report(
                    *self._inputs(), modality_scope=list(modality_scope)
                )
                blocker = next(
                    item
                    for item in report["blockers"]
                    if item["type"] == "multimodal_scope_gate"
                )
                self.assertEqual(report["decision"], "block")
                self.assertIn(gap, blocker["gaps"])

    def test_audio_and_file_generated_artifacts_do_not_unlock_release(self):
        report = build_release_gate_report(
            *self._inputs(), modality_scope=["audio", "file"]
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_scope_gate"
        )
        boundaries = {
            item["modality"]: item
            for item in blocker["modality_boundaries"]
        }
        self.assertEqual(report["decision"], "block")
        self.assertIn(
            "ReleaseFoundry generated-artifact verification does not prove caller-native "
            "input or release qualification: audio, file",
            blocker["gaps"],
        )
        for modality in ("audio", "file"):
            with self.subTest(modality=modality):
                self.assertEqual(
                    boundaries[modality]["releasefoundry_generated_artifact_state"],
                    "verified_non_qualifying",
                )
                self.assertEqual(
                    boundaries[modality][
                        "releasefoundry_caller_native_submission_state"
                    ],
                    "provider_surface_missing",
                )
                self.assertEqual(
                    boundaries[modality]["a2_release_qualification_state"],
                    "not_implemented",
                )
                self.assertEqual(
                    boundaries[modality]["required_disposition"], "retest"
                )

    def test_video_provider_unverified_boundary_requires_retest_or_review(self):
        report = build_release_gate_report(
            *self._inputs(), modality_scope=["video"]
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_scope_gate"
        )
        boundary = blocker["modality_boundaries"][0]
        self.assertEqual(report["decision"], "block")
        self.assertIn(
            "ReleaseFoundry video remains provider_unverified/unreliable and requires "
            "retest or human review",
            blocker["gaps"],
        )
        self.assertEqual(boundary["modality"], "video")
        self.assertEqual(
            boundary["releasefoundry_generated_artifact_state"], "provider_unverified"
        )
        self.assertEqual(
            boundary["releasefoundry_caller_native_submission_state"],
            "provider_unverified",
        )
        self.assertEqual(
            boundary["required_disposition"], "retest_or_human_review"
        )
        self.assertEqual(
            blocker["evidence_refs"],
            ["docs/evidence/a2_releasefoundry_native_media_surface.json"],
        )

    def test_qualified_image_artifact_must_match_expected_bindings(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "review_conservation_hash": "sha256:" + "c" * 64,
            "model_id": "qwen-vl-plus",
            "usage_cost_receipt": {
                "usage_accounting_state": "complete",
                "pricing_state": "configured",
                "within_cost_budget": True,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": "sha256:" + "b" * 64,
                "review_conservation_hash": artifact[
                    "review_conservation_hash"
                ],
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
            "review_conservation_hash": "sha256:" + "c" * 64,
            "model_id": "qwen-vl-plus",
            "usage_cost_receipt": {
                "usage_accounting_state": "complete",
                "pricing_state": "configured",
                "within_cost_budget": True,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": artifact["manifest_hash"],
                "review_conservation_hash": artifact[
                    "review_conservation_hash"
                ],
                "model_id": artifact["model_id"],
            },
        )
        self.assertFalse(
            any(
                item["type"] == "multimodal_qualification_gate"
                for item in report["blockers"]
            )
        )

    def test_qualified_image_artifact_with_stale_review_conservation_is_blocked(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "review_conservation_hash": "sha256:" + "b" * 64,
            "usage_cost_receipt": {
                "usage_accounting_state": "complete",
                "pricing_state": "configured",
                "within_cost_budget": True,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": artifact["manifest_hash"],
                "review_conservation_hash": "sha256:" + "c" * 64,
            },
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        )
        self.assertIn(
            "multimodal qualification binding mismatch: "
            "review_conservation_hash",
            blocker["gaps"],
        )

    def test_stale_qualified_artifact_from_prior_candidate_is_blocked(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "b" * 64,
            "review_conservation_hash": "sha256:" + "d" * 64,
            "usage_cost_receipt": {
                "usage_accounting_state": "complete",
                "pricing_state": "configured",
                "within_cost_budget": True,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": "c" * 40,
                "manifest_hash": artifact["manifest_hash"],
                "review_conservation_hash": artifact[
                    "review_conservation_hash"
                ],
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
            review_conservation_hash="sha256:" + "f" * 64,
        )
        self.assertEqual(
            bindings,
            {
                "candidate_sha": "d" * 40,
                "manifest_hash": "sha256:" + "e" * 64,
                "review_conservation_hash": "sha256:" + "f" * 64,
            },
        )

    def test_release_gate_cli_rejects_missing_candidate_sha(self):
        with self.assertRaisesRegex(SystemExit, "--candidate-sha is required"):
            _multimodal_expected_bindings(
                modality_scope=["image"],
                binding_file=None,
                candidate_sha=None,
                dataset_manifest_hash="sha256:" + "e" * 64,
                review_conservation_hash="sha256:" + "f" * 64,
            )

    def test_release_gate_cli_rejects_missing_review_conservation_hash(self):
        with self.assertRaisesRegex(
            SystemExit, "--multimodal-review-conservation-hash is required"
        ):
            _multimodal_expected_bindings(
                modality_scope=["image"],
                binding_file=None,
                candidate_sha="d" * 40,
                dataset_manifest_hash="sha256:" + "e" * 64,
                review_conservation_hash=None,
            )

    def test_pending_designated_reference_review_requires_latest_receipt(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "review_conservation_hash": "sha256:" + "b" * 64,
            "designated_reference_review_pending": True,
            "usage_cost_receipt": {
                "usage_accounting_state": "complete",
                "pricing_state": "configured",
                "within_cost_budget": True,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": artifact["manifest_hash"],
                "review_conservation_hash": artifact[
                    "review_conservation_hash"
                ],
            },
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        )
        self.assertIn(
            "latest human-review receipt is missing for pending "
            "designated-reference review",
            blocker["gaps"],
        )

    def test_pending_designated_reference_review_binds_latest_receipt(self):
        latest = "sha256:" + "f" * 64
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "review_conservation_hash": "sha256:" + "b" * 64,
            "designated_reference_review_pending": True,
            "latest_human_review_receipt_hash": latest,
            "usage_cost_receipt": {
                "usage_accounting_state": "complete",
                "pricing_state": "configured",
                "within_cost_budget": True,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": artifact["manifest_hash"],
                "review_conservation_hash": artifact[
                    "review_conservation_hash"
                ],
                "latest_human_review_receipt_hash": latest,
            },
        )
        self.assertFalse(
            any(
                "latest human-review receipt" in gap
                for blocker in report["blockers"]
                if blocker["type"] == "multimodal_qualification_gate"
                for gap in blocker["gaps"]
            )
        )

    def test_qualified_image_artifact_missing_usage_receipt_is_blocked(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "review_conservation_hash": "sha256:" + "b" * 64,
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": artifact["manifest_hash"],
                "review_conservation_hash": artifact[
                    "review_conservation_hash"
                ],
            },
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        )
        self.assertIn(
            "multimodal usage or pricing qualification is incomplete",
            blocker["gaps"],
        )

    def test_malformed_designated_reference_review_state_is_blocked(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "review_conservation_hash": "sha256:" + "b" * 64,
            "designated_reference_review_pending": "false",
            "usage_cost_receipt": {
                "usage_accounting_state": "complete",
                "pricing_state": "configured",
                "within_cost_budget": True,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": artifact["manifest_hash"],
                "review_conservation_hash": artifact[
                    "review_conservation_hash"
                ],
            },
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        )
        self.assertIn(
            "multimodal designated-reference review state is malformed",
            blocker["gaps"],
        )

    def test_mixed_type_expected_binding_keys_are_blocked_without_crashing(self):
        artifact = {
            "qualification_state": "qualified_for_review",
            "blockers": [],
            "candidate_sha": "a" * 40,
            "manifest_hash": "sha256:" + "a" * 64,
            "review_conservation_hash": "sha256:" + "b" * 64,
            "usage_cost_receipt": {
                "usage_accounting_state": "complete",
                "pricing_state": "configured",
                "within_cost_budget": True,
            },
            "release_authority": False,
        }
        report = build_release_gate_report(
            *self._inputs(),
            modality_scope=["image"],
            multimodal_qualification=artifact,
            multimodal_expected_bindings={
                "candidate_sha": artifact["candidate_sha"],
                "manifest_hash": artifact["manifest_hash"],
                "review_conservation_hash": artifact[
                    "review_conservation_hash"
                ],
                1: "invalid",
            },
        )
        blocker = next(
            item
            for item in report["blockers"]
            if item["type"] == "multimodal_qualification_gate"
        )
        self.assertEqual(report["decision"], "block")
        self.assertIn(
            "multimodal expected bindings are malformed",
            blocker["gaps"],
        )
