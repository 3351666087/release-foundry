from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from scripts import a2_multimodal_real_api_smoke as multimodal_smoke
from scripts import a2_real_api_smoke as real_smoke
from services.judge import evidence_readiness


class FakeArtifactResponse:
    def __init__(
        self,
        body: bytes,
        content_type: str,
        *,
        final_url: str = "https://storage.example.test/artifact.bin",
        content_length: int | None = None,
    ):
        self._body = io.BytesIO(body)
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(
                len(body) if content_length is None else content_length
            ),
        }
        self._final_url = final_url

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return self._final_url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ReleaseFoundryLiveSmokeSafetyTests(unittest.TestCase):
    def test_single_modality_probe_requires_only_selected_modalities(self):
        request_config = multimodal_smoke._request_config(["audio"])

        self.assertTrue(
            multimodal_smoke._all_required_modalities_requested(
                required_modalities=["text", "audio"],
                requested_modalities=["text", "audio"],
                generation_options=request_config["generation_options"],
            )
        )
        self.assertFalse(
            multimodal_smoke._all_required_modalities_requested(
                required_modalities=list(
                    multimodal_smoke.DEFAULT_REQUIRED_MODALITIES
                ),
                requested_modalities=["text", "audio"],
                generation_options=request_config["generation_options"],
            )
        )

    def test_default_multimodal_config_excludes_unverified_video(self):
        modalities = multimodal_smoke._parse_modalities("image,audio,file")
        config = multimodal_smoke._request_config(modalities)

        self.assertEqual(modalities, ["image", "audio", "file"])
        self.assertTrue(config["generation_options"]["generate_images"])
        self.assertTrue(config["generation_options"]["generate_audio"])
        self.assertTrue(config["generation_options"]["generate_files"])
        self.assertFalse(config["generation_options"]["generate_videos"])
        self.assertFalse(config["agent"]["accepted_inputs"]["video"]["enabled"])
        self.assertEqual(config["generation_options"]["scenario_count"], 1)
        self.assertEqual(config["test_config"]["num_variations"], 1)
        self.assertEqual(
            config["metadata"]["dataset_name"],
            "A2 Multimodal Artifact Receipt v1",
        )
        self.assertNotIn(
            "synthetic:video:checkout-flow",
            json.dumps(config, sort_keys=True),
        )

    def test_modality_parser_is_canonical(self):
        self.assertEqual(
            multimodal_smoke._parse_modalities("file,image,file,audio"),
            ["image", "audio", "file"],
        )
        self.assertEqual(
            multimodal_smoke._parse_modalities("video"),
            ["video"],
        )
        with self.assertRaises(SystemExit):
            multimodal_smoke._parse_modalities("")
        with self.assertRaises(SystemExit):
            multimodal_smoke._parse_modalities("image,unknown")

    def test_provider_unverified_video_requires_second_explicit_opt_in(self):
        with self.assertRaisesRegex(
            SystemExit,
            "video is provider-unverified",
        ):
            multimodal_smoke._require_provider_capability_opt_in(
                ["video"],
                allow_provider_unverified_video=False,
            )

        multimodal_smoke._require_provider_capability_opt_in(
            ["image", "video"],
            allow_provider_unverified_video=True,
        )
        multimodal_smoke._require_provider_capability_opt_in(
            ["image", "audio", "file"],
            allow_provider_unverified_video=False,
        )

    def test_explicit_video_probe_keeps_provider_limitation_in_public_summary(self):
        class FakeClient:
            @classmethod
            def from_env(cls, *, timeout):
                return cls()

            def init(self):
                return {
                    "status": "ok",
                    "user": {},
                    "tenant": {},
                    "notes": [],
                }

            def list_requests(self, **kwargs):
                return {"requests": [], "next_cursor": None}

            def create_request(self, **kwargs):
                return {
                    "id": 589,
                    "request_name": kwargs["request_name"],
                    "request_status": "pending",
                }

        fake_sdk = types.ModuleType("releasefoundry")
        fake_sdk.ReleaseFoundryLabsClient = FakeClient

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            argv = [
                "a2_multimodal_real_api_smoke.py",
                "--output",
                "public.json",
                "--private-output",
                "private.json",
                "--modalities",
                "video",
                "--allow-provider-unverified-video",
                "--no-wait",
                "--no-artifact-download",
            ]
            with (
                mock.patch.object(multimodal_smoke, "ROOT", root),
                mock.patch.object(
                    multimodal_smoke,
                    "_ensure_releasefoundry_sdk_importable",
                    return_value=None,
                ),
                mock.patch.object(
                    multimodal_smoke,
                    "_sdk_source",
                    return_value="synthetic-sdk",
                ),
                mock.patch.object(sys, "argv", argv),
                mock.patch.dict(
                    sys.modules,
                    {"releasefoundry": fake_sdk},
                ),
                mock.patch.dict(
                    os.environ,
                    {"RELEASEFOUNDRY_LABS_API_KEY": "synthetic-test-key"},
                    clear=False,
                ),
            ):
                self.assertEqual(multimodal_smoke.main(), 0)

            summary = json.loads(
                (root / "public.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary["requested_modalities"], ["text", "video"])
        self.assertNotIn("video", summary["excluded_modalities"])
        self.assertEqual(
            summary["provider_limitations"],
            {"video": "provider_unverified"},
        )
        self.assertFalse(summary["c3_grading_ready"])

    def test_request_content_identity_is_stable_for_canonical_modalities(self):
        first_config = multimodal_smoke._request_config(
            multimodal_smoke._parse_modalities("file,image,audio")
        )
        second_config = multimodal_smoke._request_config(
            multimodal_smoke._parse_modalities("audio,file,image")
        )

        first_hash = multimodal_smoke._request_content_sha256(
            request_config=first_config,
            request_input_schema=multimodal_smoke._request_input_schema(first_config),
        )
        second_hash = multimodal_smoke._request_content_sha256(
            request_config=second_config,
            request_input_schema=multimodal_smoke._request_input_schema(second_config),
        )

        self.assertEqual(first_hash, second_hash)
        self.assertRegex(first_hash, r"^[0-9a-f]{64}$")

    def test_create_request_transient_failure_is_attempted_once(self):
        class FakeClient:
            def __init__(self):
                self.calls = 0

            def create_request(self, **kwargs):
                self.calls += 1
                raise ConnectionError("temporarily unavailable")

        client = FakeClient()
        with self.assertRaises(ConnectionError):
            multimodal_smoke._create_request_once(
                client,
                request_name="content-bound-name",
                request={"request": "synthetic"},
                request_input_schema={"type": "object"},
            )

        self.assertEqual(client.calls, 1)

    def test_request_reuse_requires_one_exact_content_bound_name(self):
        payload = {
            "requests": [
                {"id": 1, "request_name": "other"},
                {"id": 2, "request_name": "target"},
            ]
        }

        self.assertEqual(
            multimodal_smoke._request_for_name(payload, "target")["id"],
            2,
        )
        self.assertIsNone(multimodal_smoke._request_for_name(payload, "missing"))
        with self.assertRaises(RuntimeError):
            multimodal_smoke._request_for_name(
                {
                    "requests": [
                        {"id": 2, "request_name": "target"},
                        {"id": 3, "request_name": "target"},
                    ]
                },
                "target",
            )

    def test_request_inventory_finds_exact_match_on_second_page(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def list_requests(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs["cursor"] is None:
                    return {
                        "requests": [{"id": 100, "request_name": "other"}],
                        "next_cursor": 17,
                    }
                return {
                    "requests": [{"id": 200, "request_name": "target"}],
                    "next_cursor": None,
                }

        client = FakeClient()
        calls = []
        raw = {}
        result = multimodal_smoke._find_single_request_by_exact_name(
            client,
            request_name="target",
            calls=calls,
            raw=raw,
        )

        self.assertEqual(result["request"]["id"], 200)
        self.assertEqual(result["page_count"], 2)
        self.assertTrue(result["inventory_complete"])
        self.assertEqual(result["exact_match_count"], 1)
        self.assertEqual(
            client.calls,
            [{"limit": 50, "cursor": None}, {"limit": 50, "cursor": 17}],
        )

    def test_request_inventory_complete_no_match_allows_one_later_create(self):
        class FakeClient:
            def __init__(self):
                self.list_calls = []
                self.create_calls = 0

            def list_requests(self, **kwargs):
                self.list_calls.append(kwargs)
                if kwargs["cursor"] is None:
                    return {"requests": [], "next_cursor": 3}
                return {"requests": [], "next_cursor": None}

            def create_request(self, **kwargs):
                self.create_calls += 1
                return {"id": 300, **kwargs}

        client = FakeClient()
        result = multimodal_smoke._find_single_request_by_exact_name(
            client,
            request_name="target",
            calls=[],
            raw={},
        )
        self.assertIsNone(result["request"])
        self.assertEqual(result["page_count"], 2)
        self.assertTrue(result["inventory_complete"])
        self.assertEqual(result["exact_match_count"], 0)

        multimodal_smoke._create_request_once(
            client,
            request_name="target",
            request={"request": "synthetic"},
            request_input_schema={"type": "object"},
        )
        self.assertEqual(client.create_calls, 1)

    def test_request_inventory_rejects_cursor_loop(self):
        class FakeClient:
            def list_requests(self, **kwargs):
                return {"requests": [], "next_cursor": 7}

        with self.assertRaisesRegex(RuntimeError, "cursor loop"):
            multimodal_smoke._find_single_request_by_exact_name(
                FakeClient(),
                request_name="target",
                calls=[],
                raw={},
            )

    def test_request_inventory_rejects_malformed_responses(self):
        malformed_responses = [
            [],
            {},
            {"requests": {}},
            {"requests": ["not-an-object"]},
            {"requests": [], "next_cursor": 0},
            {"requests": [], "next_cursor": True},
            {"requests": [], "next_cursor": "2"},
        ]
        for response in malformed_responses:
            with self.subTest(response=response):
                class FakeClient:
                    def list_requests(self, **kwargs):
                        return response

                with self.assertRaises(RuntimeError):
                    multimodal_smoke._find_single_request_by_exact_name(
                        FakeClient(),
                        request_name="target",
                        calls=[],
                        raw={},
                    )

    def test_request_inventory_second_page_failure_fails_closed(self):
        class FakeClient:
            def __init__(self):
                self.calls = 0
                self.create_calls = 0

            def list_requests(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return {"requests": [], "next_cursor": 9}
                raise ConnectionError("cursor=9 private request id=123456")

            def create_request(self, **kwargs):
                self.create_calls += 1

        client = FakeClient()
        calls = []
        raw = {}
        with self.assertRaisesRegex(RuntimeError, "refusing to create"):
            multimodal_smoke._find_single_request_by_exact_name(
                client,
                request_name="target",
                calls=calls,
                raw=raw,
            )

        self.assertEqual(client.create_calls, 0)
        self.assertEqual(calls[-1]["status"], "error")
        self.assertNotIn("123456", json.dumps(calls))
        self.assertNotIn("cursor=9", json.dumps(calls))
        self.assertIn("123456", json.dumps(raw))

    def test_request_inventory_rejects_page_limit_exhaustion(self):
        class FakeClient:
            def __init__(self):
                self.cursor = 0

            def list_requests(self, **kwargs):
                self.cursor += 1
                return {"requests": [], "next_cursor": self.cursor}

        with self.assertRaisesRegex(RuntimeError, "maximum page count"):
            multimodal_smoke._find_single_request_by_exact_name(
                FakeClient(),
                request_name="target",
                calls=[],
                raw={},
                max_pages=2,
            )

    def test_request_inventory_rejects_duplicate_matches_across_pages(self):
        class FakeClient:
            def list_requests(self, **kwargs):
                if kwargs["cursor"] is None:
                    return {
                        "requests": [{"id": 1, "request_name": "target"}],
                        "next_cursor": 5,
                    }
                return {
                    "requests": [{"id": 2, "request_name": "target"}],
                    "next_cursor": None,
                }

        with self.assertRaisesRegex(RuntimeError, "multiple requests"):
            multimodal_smoke._find_single_request_by_exact_name(
                FakeClient(),
                request_name="target",
                calls=[],
                raw={},
            )

    def test_request_inventory_call_summary_does_not_leak_ids_or_cursors(self):
        class FakeClient:
            def list_requests(self, **kwargs):
                if kwargs["cursor"] is None:
                    return {
                        "requests": [{"id": 987654, "request_name": "other"}],
                        "next_cursor": 24680,
                    }
                return {
                    "requests": [{"id": 13579, "request_name": "target"}],
                    "next_cursor": None,
                }

        calls = []
        raw = {}
        multimodal_smoke._find_single_request_by_exact_name(
            FakeClient(),
            request_name="target",
            calls=calls,
            raw=raw,
        )

        public_calls = json.dumps(calls, sort_keys=True)
        self.assertNotIn("987654", public_calls)
        self.assertNotIn("24680", public_calls)
        self.assertNotIn("13579", public_calls)
        self.assertIn("987654", json.dumps(raw))
        self.assertEqual([call["name"] for call in calls], ["list_requests"] * 2)

    def test_dataset_binding_rejects_ambiguous_request_matches(self):
        self.assertEqual(
            multimodal_smoke._dataset_id_for_request(
                {
                    "datasets": [
                        {"id": 7, "request_id": 99},
                        {"id": 8, "request_id": 100},
                    ]
                },
                99,
            ),
            7,
        )
        self.assertIsNone(
            multimodal_smoke._dataset_id_for_request({"datasets": []}, 99)
        )
        with self.assertRaises(RuntimeError):
            multimodal_smoke._dataset_id_for_request(
                {
                    "datasets": [
                        {"id": 7, "request_id": 99},
                        {"id": 8, "request_id": 99},
                    ]
                },
                99,
            )

    def test_artifact_link_fetch_fails_closed_on_dataset_identity_mismatch(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def get_dataset(self, dataset_id, **kwargs):
                self.calls.append((dataset_id, kwargs))
                return {
                    "id": dataset_id + 1,
                    "request_id": 99,
                    "artifacts": [
                        {
                            "modality": "image",
                            "signed_url": "https://storage.example.test/image.png?token=private",
                        }
                    ],
                }

        client = FakeClient()
        opener_calls = []
        calls = []
        result = multimodal_smoke._collect_artifact_receipts(
            client=client,
            dataset_id=7,
            request_id=99,
            calls=calls,
            allowed_modalities=["image", "audio", "file"],
            timeout=5,
            max_artifact_bytes=1024,
            max_artifacts=4,
            opener=lambda *args, **kwargs: opener_calls.append((args, kwargs)),
        )

        self.assertEqual(result["artifact_receipt_status"], "signed_dataset_binding_failed")
        self.assertEqual(result["artifact_download_attempt_count"], 0)
        self.assertEqual(opener_calls, [])
        self.assertEqual(client.calls[0][0], 7)
        self.assertTrue(client.calls[0][1]["include_signed_urls"])
        self.assertEqual(calls[0]["name"], "get_dataset_artifact_links")
        self.assertNotIn("signed_url", json.dumps(calls).lower())

    def test_artifact_reference_extraction_filters_and_deduplicates_urls(self):
        duplicate = "https://storage.example.test/image.png?token=private"
        payload = {
            "id": 7,
            "artifacts": [
                {"modality": "image", "signed_url": duplicate},
                {"modality": "image", "download_url": duplicate},
                {
                    "content_type": "audio/wav",
                    "download_url": "https://storage.example.test/audio.wav?token=private",
                },
                {
                    "media_type": "document",
                    "file_url": "https://storage.example.test/report.pdf?token=private",
                },
                {
                    "webpage_url": "https://example.test/product",
                    "url": "https://example.test/landing",
                },
                {
                    "modality": "video",
                    "video_url": "http://storage.example.test/video.mp4",
                },
            ],
        }

        references = multimodal_smoke._signed_artifact_refs(payload)

        self.assertEqual(
            [(item["modality"], item["url"]) for item in references],
            [
                ("image", duplicate),
                (
                    "audio",
                    "https://storage.example.test/audio.wav?token=private",
                ),
                (
                    "file",
                    "https://storage.example.test/report.pdf?token=private",
                ),
            ],
        )

    def test_artifact_download_receipt_hashes_bytes_without_retaining_source(self):
        body = b"\x89PNG\r\n\x1a\nsynthetic-image"
        source_url = "https://storage.example.test/private/image.png?token=private"
        receipt = multimodal_smoke._download_artifact_receipt(
            {"modality": "image", "url": source_url},
            timeout=5,
            max_artifact_bytes=1024,
            opener=lambda request, timeout: FakeArtifactResponse(
                body,
                "image/png; charset=binary",
                final_url=request.full_url,
            ),
        )

        self.assertEqual(
            receipt,
            {
                "modality": "image",
                "verification_status": "verified",
                "sha256": hashlib.sha256(body).hexdigest(),
                "byte_size": len(body),
                "response_mime": "image/png",
            },
        )
        receipt_text = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(source_url, receipt_text)
        self.assertNotIn("token=private", receipt_text)
        self.assertNotIn("url", receipt)
        self.assertNotIn("path", receipt)
        self.assertNotIn("bytes", receipt)

    def test_artifact_download_rejects_oversize_http_and_insecure_redirects(self):
        oversized = multimodal_smoke._download_artifact_receipt(
            {
                "modality": "file",
                "url": "https://storage.example.test/report.pdf",
            },
            timeout=5,
            max_artifact_bytes=4,
            opener=lambda request, timeout: FakeArtifactResponse(
                b"0123456789",
                "application/pdf",
                final_url=request.full_url,
            ),
        )
        invalid_url = multimodal_smoke._download_artifact_receipt(
            {
                "modality": "audio",
                "url": "http://storage.example.test/audio.wav",
            },
            timeout=5,
            max_artifact_bytes=1024,
            opener=lambda *args, **kwargs: self.fail(
                "HTTP artifact URL must not be opened."
            ),
        )
        invalid_redirect = multimodal_smoke._download_artifact_receipt(
            {
                "modality": "image",
                "url": "https://storage.example.test/image.png",
            },
            timeout=5,
            max_artifact_bytes=1024,
            opener=lambda request, timeout: FakeArtifactResponse(
                b"image",
                "image/png",
                final_url="http://storage.example.test/image.png",
            ),
        )

        self.assertEqual(oversized["verification_status"], "size_limit_exceeded")
        self.assertEqual(invalid_url["verification_status"], "invalid_url")
        self.assertEqual(invalid_redirect["verification_status"], "invalid_redirect")

    def test_verified_generated_artifacts_never_claim_native_media_input(self):
        class FakeClient:
            def get_dataset(self, dataset_id, **kwargs):
                return {
                    "id": dataset_id,
                    "request_id": 99,
                    "artifacts": [
                        {
                            "modality": "image",
                            "signed_url": "https://storage.example.test/image.png?token=private",
                        },
                        {
                            "modality": "audio",
                            "signed_url": "https://storage.example.test/audio.wav?token=private",
                        },
                        {
                            "modality": "file",
                            "signed_url": "https://storage.example.test/report.pdf?token=private",
                        },
                    ],
                }

        media = {
            "image.png": (b"image", "image/png"),
            "audio.wav": (b"audio", "audio/wav"),
            "report.pdf": (b"file", "application/pdf"),
        }

        def opener(request, timeout):
            filename = request.full_url.split("?", 1)[0].rsplit("/", 1)[-1]
            body, mime = media[filename]
            return FakeArtifactResponse(
                body,
                mime,
                final_url=request.full_url,
            )

        calls = []
        result = multimodal_smoke._collect_artifact_receipts(
            client=FakeClient(),
            dataset_id=7,
            request_id=99,
            calls=calls,
            allowed_modalities=["image", "audio", "file"],
            timeout=5,
            max_artifact_bytes=1024,
            max_artifacts=4,
            opener=opener,
        )
        evidence = multimodal_smoke._modality_evidence(
            request_created=True,
            dataset={"content": "Synthetic prompt text."},
            requested_modalities=["text", "image", "audio", "file"],
            verified_artifact_modalities=[
                receipt["modality"]
                for receipt in result["artifact_receipts"]
                if receipt["verification_status"] == "verified"
            ],
        )

        self.assertEqual(result["artifact_receipt_status"], "verified")
        self.assertEqual(result["artifact_reference_count"], 3)
        self.assertEqual(result["artifact_download_attempt_count"], 3)
        self.assertEqual(result["artifact_download_verified_count"], 3)
        self.assertEqual(
            result["artifact_reference_modalities"],
            ["image", "audio", "file"],
        )
        self.assertEqual(
            result["artifact_verified_modalities"],
            ["image", "audio", "file"],
        )
        self.assertEqual(result["artifact_missing_modalities"], [])
        self.assertTrue(result["artifact_modality_coverage_complete"])
        self.assertEqual(
            evidence["observed_artifact_modalities"],
            ["text", "image", "audio", "file"],
        )
        self.assertEqual(evidence["accepted_modalities"], ["text"])
        for modality in ("image", "audio", "file"):
            self.assertEqual(
                evidence["modalities"][modality]["input_support_status"],
                "not_proven",
            )
        self.assertFalse(evidence["modalities"]["video"]["requested"])
        self.assertNotIn("signed_url", json.dumps(calls).lower())

    def test_missing_requested_artifact_modality_is_partial_not_verified(self):
        class FakeClient:
            def get_dataset(self, dataset_id, **kwargs):
                return {
                    "id": dataset_id,
                    "request_id": 99,
                    "artifacts": [
                        {
                            "modality": "image",
                            "signed_url": "https://storage.example.test/image.png?token=private",
                        },
                        {
                            "modality": "file",
                            "signed_url": "https://storage.example.test/report.pdf?token=private",
                        },
                    ],
                }

        media = {
            "image.png": (b"image", "image/png"),
            "report.pdf": (b"file", "application/pdf"),
        }

        def opener(request, timeout):
            filename = request.full_url.split("?", 1)[0].rsplit("/", 1)[-1]
            body, mime = media[filename]
            return FakeArtifactResponse(
                body,
                mime,
                final_url=request.full_url,
            )

        result = multimodal_smoke._collect_artifact_receipts(
            client=FakeClient(),
            dataset_id=7,
            request_id=99,
            calls=[],
            allowed_modalities=["image", "audio", "file"],
            timeout=5,
            max_artifact_bytes=1024,
            max_artifacts=4,
            opener=opener,
        )

        self.assertEqual(result["artifact_receipt_status"], "partial")
        self.assertEqual(
            result["artifact_reference_modalities"],
            ["image", "file"],
        )
        self.assertEqual(
            result["artifact_verified_modalities"],
            ["image", "file"],
        )
        self.assertEqual(result["artifact_missing_modalities"], ["audio"])
        self.assertFalse(result["artifact_modality_coverage_complete"])

    def test_request_status_prefers_terminal_request_detail(self):
        request_detail = {
            "id": 589,
            "request_status": "failed",
        }
        waited = None
        created = {
            "id": 589,
            "request_status": "pending",
        }

        status = multimodal_smoke._request_status(request_detail, waited, created)

        self.assertEqual(status, "failed")

    def test_processing_request_does_not_query_dataset_or_artifacts(self):
        class FakeClient:
            def list_datasets(self, **kwargs):
                raise AssertionError("processing requests must not query datasets")

            def get_dataset(self, *args, **kwargs):
                raise AssertionError("processing requests must not query artifacts")

        calls = []
        raw = {}
        dataset, dataset_id, binding_verified, result = (
            multimodal_smoke._collect_completed_request_evidence(
                client=FakeClient(),
                request_id=589,
                request_status="processing",
                calls=calls,
                raw=raw,
                allowed_modalities=["image", "audio", "file"],
                download_artifacts=True,
                artifact_timeout=5,
                max_artifact_bytes=1024,
                max_artifacts=4,
            )
        )

        self.assertIsNone(dataset)
        self.assertIsNone(dataset_id)
        self.assertFalse(binding_verified)
        self.assertEqual(result["artifact_receipt_status"], "request_not_completed")
        self.assertEqual(calls, [])
        self.assertEqual(raw, {})

    def test_failed_request_does_not_query_dataset_or_artifacts(self):
        class FakeClient:
            def list_datasets(self, **kwargs):
                raise AssertionError("failed requests must not query datasets")

            def get_dataset(self, *args, **kwargs):
                raise AssertionError("failed requests must not query artifacts")

        calls = []
        raw = {}
        dataset, dataset_id, binding_verified, result = (
            multimodal_smoke._collect_completed_request_evidence(
                client=FakeClient(),
                request_id=589,
                request_status="failed",
                calls=calls,
                raw=raw,
                allowed_modalities=["image", "audio", "file"],
                download_artifacts=True,
                artifact_timeout=5,
                max_artifact_bytes=1024,
                max_artifacts=4,
            )
        )

        self.assertIsNone(dataset)
        self.assertIsNone(dataset_id)
        self.assertFalse(binding_verified)
        self.assertEqual(result["artifact_receipt_status"], "request_failed")
        self.assertEqual(calls, [])
        self.assertEqual(raw, {})

    def test_completed_request_after_wait_timeout_still_collects_dataset_evidence(self):
        class FakeClient:
            def list_datasets(self, **kwargs):
                return {"datasets": [{"id": 7, "request_id": 589}]}

            def get_dataset(self, dataset_id, **kwargs):
                self.dataset_id = dataset_id
                self.dataset_kwargs = kwargs
                return {"id": dataset_id, "request_id": 589}

        request_status = multimodal_smoke._request_status(
            {"id": 589, "request_status": "completed"},
            None,
            {"id": 589, "request_status": "pending"},
        )
        client = FakeClient()
        calls = []
        raw = {}
        dataset, dataset_id, binding_verified, result = (
            multimodal_smoke._collect_completed_request_evidence(
                client=client,
                request_id=589,
                request_status=request_status,
                calls=calls,
                raw=raw,
                allowed_modalities=["image", "audio", "file"],
                download_artifacts=False,
                artifact_timeout=5,
                max_artifact_bytes=1024,
                max_artifacts=4,
            )
        )

        self.assertTrue(multimodal_smoke._request_completed(request_status))
        self.assertEqual(dataset["id"], 7)
        self.assertEqual(dataset_id, 7)
        self.assertTrue(binding_verified)
        self.assertEqual(result["artifact_receipt_status"], "download_disabled")
        self.assertEqual([call["name"] for call in calls], ["list_datasets", "get_dataset"])
        self.assertFalse(client.dataset_kwargs["include_signed_urls"])

    def test_public_session_summary_does_not_keep_email_fingerprint(self):
        session = {
            "status": "ok",
            "user": {"id": 7, "email": "account.owner@example.test"},
            "tenant": {"id": 9, "tenant_name": "Example"},
            "notes": [],
        }

        for module in (real_smoke, multimodal_smoke):
            with self.subTest(module=module.__name__):
                summary = module._redacted_session(session)
                self.assertTrue(summary["user_email_present"])
                self.assertNotIn("user_email_sha256_12", summary)
                self.assertNotIn("account.owner@example.test", str(summary))

    def test_error_summaries_redact_auth_pii_and_signed_url_material(self):
        message = (
            "Authorization: Bearer synthetic-labs-secret "
            "api_key=synthetic-legacy-secret "
            "email=account.owner@example.test "
            "Cookie: session=private-session; refresh_token=private-refresh "
            "asset=https://storage.example.test/object.png?"
            "X-Amz-Credential=private&X-Amz-Signature=signature"
        )
        env = {
            "RELEASEFOUNDRY_LABS_API_KEY": "synthetic-labs-secret",
            "RELEASEFOUNDRY_API_KEY": "synthetic-legacy-secret",
        }

        for module in (real_smoke, multimodal_smoke):
            with self.subTest(module=module.__name__), mock.patch.dict(os.environ, env, clear=False):
                redacted = module._safe_error_message(message)
                for forbidden in (
                    "synthetic-labs-secret",
                    "synthetic-legacy-secret",
                    "account.owner@example.test",
                    "private-session",
                    "private-refresh",
                    "X-Amz-Credential",
                    "X-Amz-Signature",
                    "Bearer ",
                ):
                    self.assertNotIn(forbidden, redacted)

    def test_modality_evidence_does_not_treat_text_mentions_as_artifacts(self):
        dataset = {
            "dataset_source": {
                "runs": {
                    "scenario-text-only": {
                        "actions": [
                            {
                                "actor": "user",
                                "content": "Discuss image, audio, file, and video behavior.",
                            }
                        ]
                    }
                }
            }
        }

        evidence = multimodal_smoke._modality_evidence(
            request_created=True,
            dataset=dataset,
        )

        self.assertEqual(evidence["requested_modalities"], multimodal_smoke.MODALITIES)
        self.assertEqual(evidence["observed_artifact_modalities"], ["text"])
        self.assertEqual(evidence["accepted_modalities"], ["text"])
        for modality in ("image", "audio", "file", "video"):
            self.assertFalse(evidence["modalities"][modality]["artifact_observed"])
            self.assertEqual(
                evidence["modalities"][modality]["input_support_status"],
                "not_proven",
            )

    def test_modality_evidence_reports_structured_artifacts_without_claiming_native_input(self):
        dataset = {
            "dataset_source": {
                "runs": {
                    "scenario-media": {
                        "actions": [
                            {
                                "actor": "user",
                                "content": "Inspect the supplied evidence.",
                                "attachments": [
                                    {"mime_type": "image/png", "object_key": "private/image.png"},
                                    {"media_type": "audio", "object_key": "private/audio.wav"},
                                ],
                            }
                        ]
                    }
                }
            }
        }

        evidence = multimodal_smoke._modality_evidence(
            request_created=True,
            dataset=dataset,
        )

        self.assertEqual(
            evidence["observed_artifact_modalities"],
            ["text", "image", "audio"],
        )
        self.assertEqual(evidence["accepted_modalities"], ["text"])
        for modality in ("image", "audio"):
            record = evidence["modalities"][modality]
            self.assertTrue(record["artifact_observed"])
            self.assertEqual(record["grading_path"], "generated_artifact")
            self.assertEqual(record["input_support_status"], "not_proven")

    def test_modality_evidence_keeps_excluded_video_out_of_request_acceptance(self):
        evidence = multimodal_smoke._modality_evidence(
            request_created=True,
            dataset={
                "dataset_source": {
                    "runs": {
                        "scenario": {
                            "content": "Inspect the generated image.",
                            "image_url": "https://example.test/image.png",
                        }
                    }
                }
            },
            requested_modalities=["text", "image", "audio", "file"],
        )

        self.assertEqual(
            evidence["requested_modalities"],
            ["text", "image", "audio", "file"],
        )
        self.assertFalse(evidence["modalities"]["video"]["requested"])
        self.assertFalse(evidence["modalities"]["video"]["request_accepted"])
        self.assertEqual(
            evidence["modalities"]["video"]["evidence_status"],
            "not_observed",
        )

    def test_readiness_keeps_requested_and_observed_modalities_distinct(self):
        payload = {
            "schema_version": "a2.multimodal_real_api_smoke.v1",
            "generated_at": "2026-07-26T00:00:00Z",
            "requested_modalities": list(multimodal_smoke.MODALITIES),
            "request_config_accepted_modalities": [],
            "observed_artifact_modalities": [],
            "accepted_modalities": [],
            "modality_evidence": {},
            "generation_options": {
                "generate_audio": True,
                "generate_files": True,
                "generate_images": True,
                "generate_videos": True,
            },
            "calls": [
                {"name": "init", "status": "ok"},
                {
                    "name": "create_request",
                    "status": "error",
                    "error_type": "ReleaseFoundryLabsError",
                    "error_message": "[400] Usage limit exceeded for videos",
                },
            ],
            "api_call_count": 2,
            "all_required_modalities_requested": True,
            "create_request_reached": False,
            "wait_completed": False,
            "dataset_id_present": False,
            "public_safe": True,
            "c3_grading_ready": False,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "multimodal.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            summary = evidence_readiness._multimodal_real_api_smoke_summary(path)

        self.assertEqual(set(summary["requested_modalities"]), set(multimodal_smoke.MODALITIES))
        self.assertEqual(summary["accepted_modalities"], [])
        self.assertTrue(summary["all_required_modalities_requested"])
        self.assertTrue(summary["real_api_boundary_reached"])
        self.assertFalse(summary["ready_for_a2_multimodal_context"])

    def test_readiness_accepts_supported_request_set_without_requiring_video_generation(self):
        payload = {
            "schema_version": "a2.multimodal_real_api_smoke.v1",
            "generated_at": "2026-07-29T00:00:00Z",
            "required_modalities": ["text", "image", "audio", "file"],
            "excluded_modalities": ["video"],
            "requested_modalities": ["text", "image", "audio", "file"],
            "request_config_accepted_modalities": ["text", "image", "audio", "file"],
            "observed_artifact_modalities": ["text", "image", "audio", "file"],
            "accepted_modalities": ["text"],
            "modality_evidence": {},
            "generation_options": {
                "generate_audio": True,
                "generate_files": True,
                "generate_images": True,
                "generate_videos": False,
            },
            "calls": [
                {"name": "init", "status": "ok"},
                {"name": "list_requests", "status": "ok"},
            ],
            "api_call_count": 2,
            "all_required_modalities_requested": True,
            "create_request_reached": False,
            "request_reused": True,
            "wait_completed": True,
            "dataset_id_present": True,
            "public_safe": True,
            "c3_grading_ready": False,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "multimodal.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            summary = evidence_readiness._multimodal_real_api_smoke_summary(path)

        self.assertEqual(
            set(summary["required_modalities"]),
            {"text", "image", "audio", "file"},
        )
        self.assertEqual(summary["excluded_modalities"], ["video"])
        self.assertTrue(summary["all_required_modalities_requested"])
        self.assertTrue(summary["real_api_boundary_reached"])
        self.assertFalse(summary["ready_for_a2_multimodal_context"])

    def test_readiness_projects_only_public_safe_artifact_receipt_fields(self):
        payload = {
            "schema_version": "a2.multimodal_real_api_smoke.v1",
            "generated_at": "2026-07-29T00:00:00Z",
            "required_modalities": ["text", "image", "audio", "file"],
            "excluded_modalities": ["video"],
            "requested_modalities": ["text", "image", "audio", "file"],
            "request_config_accepted_modalities": [
                "text",
                "image",
                "audio",
                "file",
            ],
            "observed_artifact_modalities": [
                "text",
                "image",
                "audio",
                "file",
            ],
            "accepted_modalities": ["text"],
            "modality_evidence": {},
            "generation_options": {
                "generate_audio": True,
                "generate_files": True,
                "generate_images": True,
                "generate_videos": False,
            },
            "artifact_origin": "releasefoundry_generated_dataset",
            "artifact_receipt_status": "verified",
            "artifact_reference_count": 1,
            "artifact_download_attempt_count": 1,
            "artifact_download_verified_count": 1,
            "artifact_receipts": [
                {
                    "modality": "image",
                    "verification_status": "verified",
                    "sha256": "a" * 64,
                    "byte_size": 5,
                    "response_mime": "image/png",
                    "url": "https://storage.example.test/private.png?token=private",
                    "object_key": "private/image.png",
                }
            ],
            "artifact_receipts_public_safe": True,
            "calls": [{"name": "init", "status": "ok"}],
            "api_call_count": 1,
            "all_required_modalities_requested": True,
            "create_request_reached": True,
            "request_reused": False,
            "wait_completed": True,
            "dataset_id_present": True,
            "public_safe": True,
            "c3_grading_ready": False,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "multimodal.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            summary = evidence_readiness._multimodal_real_api_smoke_summary(path)

        self.assertFalse(summary["artifact_receipts_public_safe"])
        self.assertFalse(summary["public_safe"])
        self.assertFalse(summary["ready_for_a2_multimodal_context"])
        self.assertFalse(summary["c3_grading_ready"])
        self.assertNotIn("url", summary["artifact_receipts"][0])
        self.assertNotIn("object_key", summary["artifact_receipts"][0])
        self.assertIn(
            "artifact_receipts[0].url",
            summary["invalid_artifact_receipt_fields"],
        )
        self.assertIn(
            "artifact_receipts[0].object_key",
            summary["invalid_artifact_receipt_fields"],
        )


if __name__ == "__main__":
    unittest.main()
