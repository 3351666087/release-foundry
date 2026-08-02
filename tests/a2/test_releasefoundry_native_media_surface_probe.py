from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jsonschema

from scripts import a2_releasefoundry_native_media_surface_probe as probe


ROOT = Path(__file__).resolve().parents[2]


class ReleaseFoundryNativeMediaSurfaceProbeTests(unittest.TestCase):
    def test_pinned_sdk_surface_is_audited_fail_closed(self):
        audit = probe.audit_sdk_surface()

        self.assertEqual(audit["status"], "completed")
        self.assertEqual(audit["package_name"], "releasefoundry")
        self.assertEqual(audit["version"], "0.3.1")
        self.assertTrue(audit["expected_surface_matches"])
        self.assertEqual(audit["upload_method_names_observed"], [])
        self.assertEqual(audit["dataset_ingestion_method_names_observed"], [])
        self.assertEqual(audit["immutable_media_url_parameters_observed"], [])
        self.assertIn(
            "create_request.request",
            audit["generic_payload_parameters_observed"],
        )
        self.assertEqual(
            audit["accepted_inputs"]["classification"],
            "agent_capability_declaration_not_media_transport",
        )
        self.assertEqual(
            audit["add_user_file"]["classification"],
            "metadata_only",
        )
        self.assertEqual(audit["add_user_file"]["file_io_calls_observed"], [])
        self.assertEqual(
            audit["eval_runner"]["classification"],
            "text_content_only_observed",
        )
        self.assertRegex(audit["surface_fingerprint_sha256"], r"^[0-9a-f]{64}$")

    def test_static_report_separates_generated_artifacts_from_native_submission(self):
        report = probe.build_report(live=False)

        self.assertEqual(
            report["generated_artifact_capabilities"],
            {
                "image": "verified",
                "audio": "verified",
                "file": "verified",
                "video": "provider_unverified",
            },
        )
        self.assertEqual(
            report["caller_native_submission"],
            {
                "image": "provider_surface_missing",
                "audio": "provider_surface_missing",
                "file": "provider_surface_missing",
                "video": "provider_unverified",
            },
        )
        self.assertFalse(report["upload_method_observed"])
        self.assertFalse(report["immutable_media_url_parameter_observed"])
        self.assertFalse(report["undocumented_endpoint_probed"])
        self.assertEqual(report["mutation_attempt_count"], 0)
        self.assertFalse(report["native_media_uploaded"])
        self.assertFalse(report["caller_native_input_support_proven"])
        self.assertFalse(report["c3_grading_ready"])
        self.assertEqual(report["live_session"]["status"], "not_requested")

    def test_generated_capability_requires_complete_requested_modality_coverage(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            partial_path = Path(tmp_dir) / "partial.json"
            partial_path.write_text(
                json.dumps(
                    self._generated_artifact_receipt(
                        required_modalities=["text", "image", "audio", "file"],
                        verified_modalities=["image", "file"],
                        missing_modalities=["audio"],
                        receipt_status="partial",
                        coverage_complete=False,
                    )
                ),
                encoding="utf-8",
            )
            audio_path = Path(tmp_dir) / "audio.json"
            audio_path.write_text(
                json.dumps(
                    self._generated_artifact_receipt(
                        required_modalities=["text", "audio"],
                        verified_modalities=["audio"],
                    )
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                probe,
                "GENERATED_ARTIFACT_EVIDENCE",
                (partial_path, audio_path),
            ):
                capabilities, evidence = probe._generated_artifact_capabilities()

        self.assertEqual(
            capabilities,
            {
                "image": "not_verified",
                "audio": "verified",
                "file": "not_verified",
                "video": "provider_unverified",
            },
        )
        self.assertEqual(evidence[0]["verified_modalities"], [])
        self.assertEqual(evidence[1]["verified_modalities"], ["audio"])

    def test_generated_capability_accepts_complete_independent_receipts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = []
            for modality in ("image", "audio", "file"):
                path = Path(tmp_dir) / f"{modality}.json"
                path.write_text(
                    json.dumps(
                        self._generated_artifact_receipt(
                            required_modalities=["text", modality],
                            verified_modalities=[modality],
                        )
                    ),
                    encoding="utf-8",
                )
                paths.append(path)

            with mock.patch.object(
                probe,
                "GENERATED_ARTIFACT_EVIDENCE",
                tuple(paths),
            ):
                capabilities, evidence = probe._generated_artifact_capabilities()

        self.assertEqual(
            capabilities,
            {
                "image": "verified",
                "audio": "verified",
                "file": "verified",
                "video": "provider_unverified",
            },
        )
        self.assertEqual(
            [record["verified_modalities"] for record in evidence],
            [["image"], ["audio"], ["file"]],
        )

    def test_generated_capability_rejects_malformed_receipt_collections(self):
        for field in (
            "required_modalities",
            "artifact_verified_modalities",
            "artifact_missing_modalities",
            "artifact_receipts",
        ):
            for malformed in (None, {}, "image"):
                with self.subTest(field=field, malformed=malformed):
                    payload = self._generated_artifact_receipt(
                        required_modalities=["text", "image"],
                        verified_modalities=["image"],
                    )
                    payload[field] = malformed
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        path = Path(tmp_dir) / "image.json"
                        path.write_text(json.dumps(payload), encoding="utf-8")
                        with mock.patch.object(
                            probe,
                            "GENERATED_ARTIFACT_EVIDENCE",
                            (path,),
                        ):
                            capabilities, evidence = (
                                probe._generated_artifact_capabilities()
                            )

                    self.assertEqual(capabilities["image"], "not_verified")
                    self.assertEqual(evidence[0]["verified_modalities"], [])

    def test_generated_capability_rejects_duplicate_or_unbound_receipts(self):
        mutations = (
            (
                "duplicate modality receipt",
                lambda payload: payload["artifact_receipts"].append(
                    dict(payload["artifact_receipts"][0])
                ),
            ),
            (
                "missing artifact hash",
                lambda payload: payload["artifact_receipts"][0].update(
                    {"sha256": ""}
                ),
            ),
            (
                "unreliable video mixed into request",
                lambda payload: payload.update(
                    {
                        "required_modalities": ["text", "image", "video"],
                        "artifact_verified_modalities": ["image", "video"],
                        "artifact_receipts": [
                            *payload["artifact_receipts"],
                            {
                                "modality": "video",
                                "verification_status": "verified",
                                "sha256": "d" * 64,
                                "byte_size": 128,
                                "response_mime": "video/mp4",
                            },
                        ],
                    }
                ),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                payload = self._generated_artifact_receipt(
                    required_modalities=["text", "image"],
                    verified_modalities=["image"],
                )
                mutate(payload)
                with tempfile.TemporaryDirectory() as tmp_dir:
                    path = Path(tmp_dir) / "image.json"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    with mock.patch.object(
                        probe,
                        "GENERATED_ARTIFACT_EVIDENCE",
                        (path,),
                    ):
                        capabilities, evidence = (
                            probe._generated_artifact_capabilities()
                        )

                self.assertEqual(capabilities["image"], "not_verified")
                self.assertEqual(
                    capabilities["video"],
                    "provider_unverified",
                )
                self.assertEqual(evidence[0]["verified_modalities"], [])

    def test_live_probe_calls_only_init_once(self):
        class FakeClient:
            def __init__(self):
                self.calls: list[str] = []

            def init(self):
                self.calls.append("init")
                return {"tenant_id": 123, "user_email": "private@example.test"}

            def create_request(self, *args, **kwargs):
                raise AssertionError("mutation must not be called")

            def create_run(self, *args, **kwargs):
                raise AssertionError("mutation must not be called")

        client = FakeClient()
        report = probe.build_report(
            live=True,
            client_factory=lambda timeout: client,
        )

        self.assertEqual(client.calls, ["init"])
        self.assertEqual(
            report["live_session"],
            {
                "requested": True,
                "attempted": True,
                "reached": True,
                "status": "ok",
                "api_call_count": 1,
                "mutation_attempt_count": 0,
            },
        )
        self.assertEqual(
            set(report["live_session"]),
            {
                "requested",
                "attempted",
                "reached",
                "status",
                "api_call_count",
                "mutation_attempt_count",
            },
        )
        self.assertNotIn("private@example.test", json.dumps(report))

    def test_changed_sdk_surface_requires_review_instead_of_claiming_missing(self):
        audit = probe.audit_sdk_surface()
        audit["expected_surface_matches"] = False

        self.assertEqual(
            probe._caller_native_submission_status(audit),
            "sdk_surface_changed_review_required",
        )

    def test_live_mode_requires_environment_key_before_building_report(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(sys, "argv", ["probe", "--live"]),
            mock.patch.object(probe, "build_report") as build_report,
        ):
            with self.assertRaisesRegex(SystemExit, "RELEASEFOUNDRY_LABS_API_KEY is required"):
                probe.main()

        build_report.assert_not_called()

    def test_output_must_stay_under_public_evidence_directory(self):
        with self.assertRaisesRegex(SystemExit, "docs/evidence"):
            probe._resolve_output("../../outside.json")

    def test_committed_static_evidence_matches_schema_and_is_redacted(self):
        evidence_path = ROOT / "docs/evidence/a2_releasefoundry_native_media_surface.json"
        schema_path = (
            ROOT / "docs/a2/schemas/releasefoundry_native_media_surface.schema.json"
        )
        payload_text = evidence_path.read_text(encoding="utf-8")
        payload = json.loads(payload_text)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        jsonschema.Draft202012Validator(
            schema,
            format_checker=jsonschema.FormatChecker(),
        ).validate(payload)
        self.assertFalse(payload["live_session"]["requested"])
        self.assertFalse(payload["live_session"]["reached"])
        self.assertEqual(payload["live_session"]["status"], "not_requested")
        self.assertEqual(payload["live_session"]["api_call_count"], 0)
        self.assertEqual(payload["live_session"]["mutation_attempt_count"], 0)
        self.assertEqual(payload["mutation_attempt_count"], 0)
        self.assertTrue(payload["public_safe"])
        self.assertNotRegex(payload_text, re.compile(r"tp_[A-Za-z0-9_\-]+"))
        self.assertNotIn("Bearer ", payload_text)
        self.assertNotIn("@", payload_text)
        self.assertNotRegex(
            payload_text,
            re.compile(r"[A-Za-z]:\\\\"),
        )

    def test_live_failure_records_only_error_type(self):
        class FailingClient:
            def init(self):
                raise RuntimeError("sensitive credential payload")

        report = probe.build_report(
            live=True,
            client_factory=lambda timeout: FailingClient(),
        )

        self.assertEqual(report["live_session"]["status"], "error")
        self.assertEqual(report["live_session"]["error_type"], "RuntimeError")
        self.assertNotIn("sensitive credential payload", json.dumps(report))

    @staticmethod
    def _generated_artifact_receipt(
        *,
        required_modalities: list[str],
        verified_modalities: list[str],
        missing_modalities: list[str] | None = None,
        receipt_status: str = "verified",
        coverage_complete: bool = True,
    ) -> dict:
        digest_by_modality = {
            "image": "a" * 64,
            "audio": "b" * 64,
            "file": "c" * 64,
            "video": "d" * 64,
        }
        mime_by_modality = {
            "image": "image/png",
            "audio": "audio/mpeg",
            "file": "application/pdf",
            "video": "video/mp4",
        }
        return {
            "schema_version": "a2.multimodal_real_api_smoke.v1",
            "required_modalities": required_modalities,
            "artifact_origin": "releasefoundry_generated_dataset",
            "artifact_receipt_status": receipt_status,
            "artifact_verified_modalities": verified_modalities,
            "artifact_missing_modalities": missing_modalities or [],
            "artifact_modality_coverage_complete": coverage_complete,
            "artifact_receipts_public_safe": True,
            "artifact_receipts": [
                {
                    "modality": modality,
                    "verification_status": "verified",
                    "sha256": digest_by_modality[modality],
                    "byte_size": 128,
                    "response_mime": mime_by_modality[modality],
                }
                for modality in verified_modalities
            ],
            "request_status": "completed",
            "dataset_request_binding_verified": True,
            "native_media_uploaded": False,
            "media_upload_api_observed": False,
            "public_safe": True,
        }


if __name__ == "__main__":
    unittest.main()
