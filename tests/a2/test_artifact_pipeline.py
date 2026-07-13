import hashlib
import io
import json
from pathlib import Path
import struct
import unittest
import wave
import zlib

import jsonschema

from services.judge.artifact_pipeline import (
    ArtifactLimits,
    SignatureScanner,
    process_artifact,
    process_artifact_reference,
)
from services.judge.extractor_runtime import SubprocessExtractorRuntime
from services.judge.derived_evidence import build_ocr_derived_evidence
from tests.a2.test_derived_evidence import qualification
from services.judge.artifact_reference import (
    ARTIFACT_REFERENCE_SCHEMA_VERSION,
    InMemoryVersionedObjectReader,
    ObjectRead,
    authorization_binding_hash,
)
from services.judge.trusted_spine import build_decision_record, build_evidence_snapshot


ROOT = Path(__file__).parents[2]


def digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def scope():
    return {
        "organization_id": "org-a",
        "tenant_id": "tenant-a",
        "workspace_id": "workspace-a",
        "project_id": "project-a",
        "environment_id": "test",
    }


def submission(content, media_type, filename):
    return {
        "tenant_scope": scope(),
        "artifact_id": "artifact-1",
        "filename": filename,
        "media_type": media_type,
        "content_hash": digest(content),
        "source_ref": "object://private/artifact-1",
    }


def artifact_reference(content, media_type="image/png"):
    result = {
        "schema_version": ARTIFACT_REFERENCE_SCHEMA_VERSION,
        "reference_id": "ref-1",
        "tenant_scope": scope(),
        "artifact_id": "artifact-1",
        "storage_provider": "a1-object-store",
        "container_ref": "tenant-container-1",
        "object_ref": "opaque-object-1",
        "object_version": "version-0001",
        "content_hash": digest(content),
        "size_bytes": len(content),
        "media_type": media_type,
        "purpose": "release-evaluation",
        "issued_at": "2026-07-12T00:00:00Z",
        "expires_at": "2026-07-13T00:00:00Z",
    }
    result["authorization_binding_hash"] = authorization_binding_hash(result)
    return result


def versioned_reader(reference, content, *, media_type=None, version=None):
    key = (
        reference["storage_provider"],
        reference["container_ref"],
        reference["object_ref"],
        reference["object_version"],
    )
    return InMemoryVersionedObjectReader(
        {
            key: ObjectRead(
                content=content,
                object_version=version or reference["object_version"],
                media_type=media_type or reference["media_type"],
            )
        }
    )


def png(width=2, height=3):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\x00" + (b"\x00\x00\x00" * width)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw * height)) + chunk(b"IEND", b"")


def jpeg(width=5, height=7):
    sof = b"\x08" + struct.pack(">HH", height, width) + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    return b"\xff\xd8" + b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xd9"


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8_000)
        writer.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


def pdf_bytes():
    return b"%PDF-1.7\n1 0 obj\n<< /Type /Page >>\nendobj\n%%EOF"


def mp4_bytes():
    ftyp_payload = b"isom" + b"\x00\x00\x00\x00"
    return (
        struct.pack(">I", 8 + len(ftyp_payload))
        + b"ftyp"
        + ftyp_payload
        + struct.pack(">I", 8)
        + b"moov"
    )


class ProductionScanner:
    scanner_id = "clamav"
    scanner_version = "1.2.3"

    def scan(self, content, media_type):
        return {
            "status": "clean",
            "engine": self.scanner_id,
            "engine_version": self.scanner_version,
            "production_qualified": True,
            "signature_set": "20260712",
        }


class ArtifactExtractorRuntimeTest(unittest.TestCase):
    def test_real_subprocess_extraction_is_schema_valid_and_bound_to_input(self):
        content = png()
        result = process_artifact(
            submission(content, "image/png", "sample.png"),
            content,
            scanner=ProductionScanner(),
            require_production_scanner=True,
            extractor_runtime=SubprocessExtractorRuntime(timeout_seconds=5),
            require_isolated_extraction=True,
        )
        self.assertTrue(result["evaluation_eligible"])
        self.assertEqual(result["extraction"]["metadata"]["width"], 2)
        self.assertEqual(result["extraction"]["execution"]["isolation"], "subprocess")
        self.assertEqual(result["extraction"]["execution"]["exit_code"], 0)
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_artifact_pipeline.schema.json").read_text(
                encoding="utf-8"
            )
        )
        resolver = jsonschema.RefResolver(
            base_uri=(ROOT / "docs/a2/schemas/").as_uri() + "/",
            referrer=schema,
        )
        jsonschema.Draft202012Validator(schema, resolver=resolver).validate(result)

    def test_production_policy_fails_closed_without_isolated_runtime(self):
        content = png()
        result = process_artifact(
            submission(content, "image/png", "sample.png"),
            content,
            scanner=ProductionScanner(),
            require_production_scanner=True,
            require_isolated_extraction=True,
        )
        self.assertFalse(result["evaluation_eligible"])
        self.assertEqual(result["blockers"], ["isolated_extractor_required"])

    def test_worker_timeout_is_a_blocker_not_a_pass(self):
        content = png()
        result = process_artifact(
            submission(content, "image/png", "sample.png"),
            content,
            scanner=ProductionScanner(),
            extractor_runtime=SubprocessExtractorRuntime(timeout_seconds=0.0001),
            require_isolated_extraction=True,
        )
        self.assertFalse(result["evaluation_eligible"])
        self.assertEqual(result["extraction"]["status"], "failed")
        self.assertEqual(result["blockers"], ["extractor_timeout"])
        self.assertIsNone(result["extraction"]["execution"]["exit_code"])

    def test_authorized_reference_cannot_bypass_isolated_extraction_policy(self):
        content = png()
        reference = artifact_reference(content)
        result = process_artifact_reference(
            reference,
            reader=versioned_reader(reference, content),
            expected_scope=scope(),
            expected_purpose="release-evaluation",
            now="2026-07-12T12:00:00Z",
            scanner=ProductionScanner(),
            require_production_scanner=True,
            extractor_runtime=SubprocessExtractorRuntime(timeout_seconds=5),
            require_isolated_extraction=True,
        )
        self.assertTrue(result["evaluation_eligible"])
        self.assertEqual(
            result["extraction"]["execution"]["runtime_id"],
            "a2.python_subprocess",
        )
        self.assertEqual(
            result["artifact_reference_resolution"]["status"],
            "verified",
        )


class ArtifactPipelineTests(unittest.TestCase):
    @staticmethod
    def validate(result):
        schema = json.loads(
            (ROOT / "docs/a2/schemas/multimodal_artifact_pipeline.schema.json").read_text(
                encoding="utf-8"
            )
        )
        resolver = jsonschema.RefResolver(
            base_uri=(ROOT / "docs/a2/schemas/").as_uri() + "/",
            referrer=schema,
        )
        jsonschema.Draft202012Validator(schema, resolver=resolver).validate(result)

    def test_real_image_audio_file_video_structures_are_extracted_without_raw_content(self):
        cases = [
            (png(), "image/png", "sample.png", {"width": 2, "height": 3}),
            (wav_bytes(), "audio/wav", "sample.wav", {"sample_rate_hz": 8_000}),
            (pdf_bytes(), "application/pdf", "sample.pdf", {"page_count": 1}),
            (mp4_bytes(), "video/mp4", "sample.mp4", {"box_types": ["ftyp", "moov"]}),
            (b"hello\nworld", "text/plain", "sample.txt", {"line_count": 2}),
        ]
        for content, media_type, filename, expected in cases:
            with self.subTest(media_type=media_type):
                result = process_artifact(
                    submission(content, media_type, filename),
                    content,
                    scanner=ProductionScanner(),
                    require_production_scanner=True,
                )
                self.validate(result)
                self.assertTrue(result["evaluation_eligible"])
                self.assertEqual(result["blockers"], [])
                for key, value in expected.items():
                    self.assertEqual(result["extraction"]["metadata"][key], value)
                serialized = json.dumps(result)
                self.assertNotIn("hello", serialized)
                self.assertNotIn("object://private", serialized)
                self.assertFalse(result["raw_content_included"])
                self.assertFalse(result["release_authority"])

    def test_round32_png_and_jpeg_dimensions_are_decoder_independent(self):
        for content, media_type, filename, expected in (
            (png(width=11, height=13), "image/png", "dimensions.png", (11, 13)),
            (jpeg(width=17, height=19), "image/jpeg", "dimensions.jpg", (17, 19)),
        ):
            with self.subTest(media_type=media_type):
                result = process_artifact(
                    submission(content, media_type, filename),
                    content,
                    scanner=ProductionScanner(),
                    require_production_scanner=True,
                )
                metadata = result["extraction"]["metadata"]
                self.assertEqual((metadata["width"], metadata["height"]), expected)
                self.assertIn("metadata_only", result["extraction"]["quality"]["limitations"])

    def test_hash_mime_scope_filename_scanner_and_size_fail_closed(self):
        content = png()
        bad = submission(content, "image/jpeg", "../sample.png")
        bad["content_hash"] = digest(b"other")
        bad["tenant_scope"]["workspace_id"] = ""
        result = process_artifact(
            bad,
            content,
            scanner=None,
            limits=ArtifactLimits(max_artifact_bytes=10),
            require_production_scanner=True,
        )
        self.validate(result)
        self.assertFalse(result["evaluation_eligible"])
        self.assertEqual(result["manifest"]["ingestion_status"], "blocked")
        self.assertEqual(
            result["blockers"],
            [
                "artifact_size_exceeded",
                "content_hash_mismatch",
                "media_type_mismatch",
                "production_scanner_required",
                "scanner_unavailable",
                "tenant_scope_incomplete",
                "unsafe_filename",
            ],
        )
        self.assertEqual(result["extraction"]["status"], "blocked")

    def test_parser_rejection_and_malware_signature_block_evaluation(self):
        truncated_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 30
        rejected = process_artifact(
            submission(truncated_png, "image/png", "bad.png"),
            truncated_png,
            scanner=ProductionScanner(),
        )
        self.validate(rejected)
        self.assertEqual(rejected["blockers"], ["extractor_failed"])
        self.assertEqual(rejected["extraction"]["status"], "failed")

        malware = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
        blocked = process_artifact(
            submission(malware, "text/plain", "sample.txt"),
            malware,
            scanner=SignatureScanner(),
        )
        self.validate(blocked)
        self.assertEqual(blocked["blockers"], ["scanner_blocked"])
        self.assertFalse(blocked["evaluation_eligible"])

    def test_development_scanner_is_allowed_only_when_policy_does_not_require_production(self):
        content = pdf_bytes()
        development = process_artifact(
            submission(content, "application/pdf", "sample.pdf"),
            content,
            scanner=SignatureScanner(),
        )
        self.assertTrue(development["evaluation_eligible"])
        self.assertFalse(development["manifest"]["security_scan"]["production_qualified"])

        production_gate = process_artifact(
            submission(content, "application/pdf", "sample.pdf"),
            content,
            scanner=SignatureScanner(),
            require_production_scanner=True,
        )
        self.assertFalse(production_gate["evaluation_eligible"])
        self.assertEqual(production_gate["blockers"], ["production_scanner_required"])

    def test_pipeline_is_bound_into_evidence_snapshot_and_blocks_allow_when_invalid(self):
        content = png()
        valid_pipeline = process_artifact(
            submission(content, "image/png", "sample.png"),
            content,
            scanner=ProductionScanner(),
            require_production_scanner=True,
        )
        snapshot = build_evidence_snapshot(
            {"run_id": "run-1", "final_response": "done"},
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-1",
            case_id="case-1",
            scenario_id="scenario-1",
            created_at="2026-07-12T00:00:00Z",
            required_modalities=["text", "image"],
            artifact_pipeline_records=[valid_pipeline],
        )
        self.assertEqual(snapshot["completeness"], "evidence_missing")
        self.assertIn("image", snapshot["artifact_modalities"])
        self.assertNotIn("image", snapshot["observed_modalities"])
        self.assertEqual(snapshot["missing_modalities"], ["image"])
        self.assertEqual(snapshot["artifacts"][-1]["reference_hash"], valid_pipeline["manifest"]["manifest_id"])
        self.assertEqual(snapshot["artifacts"][-1]["reference_resolution_hash"], "")
        self.assertEqual(
            snapshot["extractor_provenance"][-1]["extractor_id"],
            valid_pipeline["extraction"]["extractor_id"],
        )
        derived = build_ocr_derived_evidence(
            tenant_scope=scope(),
            artifact_id=valid_pipeline["manifest"]["artifact_id"],
            content_hash=valid_pipeline["manifest"]["content_hash"],
            media_type="image/png",
            width=2,
            height=3,
            blocks=[
                {
                    "text": "RELEASE BLOCKED",
                    "confidence": 0.99,
                    "polygon": [[0, 0], [2, 0], [2, 1], [0, 1]],
                }
            ],
        extractor={
                "extractor_id": "rapidocr",
                "extractor_version": "3.9.1",
                "runtime_id": "onnxruntime-cpu",
                "runtime_version": "1.23.2",
            "runtime_platform": "windows-x86_64",
                "model_id": "pp-ocrv6-small",
                "model_hash": digest(b"model"),
                "config_hash": digest(b"config"),
                "dictionary_hash": digest(b"dictionary"),
            "production_qualified": True,
        },
        extractor_qualification=qualification(),
            prompt_injection_status="passed",
            redaction_status="passed",
        )
        semantic_snapshot = build_evidence_snapshot(
            {"run_id": "run-1", "final_response": "done"},
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-1",
            case_id="case-1",
            scenario_id="scenario-1",
            created_at="2026-07-12T00:00:00Z",
            required_modalities=["text", "image"],
            artifact_pipeline_records=[valid_pipeline],
            derived_evidence_records=[derived],
        )
        self.assertEqual(semantic_snapshot["completeness"], "complete")
        self.assertIn("image", semantic_snapshot["observed_modalities"])
        self.assertNotIn("RELEASE BLOCKED", json.dumps(semantic_snapshot))

        invalid_pipeline = process_artifact(
            submission(content, "image/png", "sample.png"),
            content,
            scanner=None,
            require_production_scanner=True,
        )
        invalid_snapshot = build_evidence_snapshot(
            {"run_id": "run-2", "final_response": "done"},
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-2",
            case_id="case-2",
            scenario_id="scenario-1",
            created_at="2026-07-12T00:00:00Z",
            required_modalities=["text", "image"],
            artifact_pipeline_records=[invalid_pipeline],
        )
        self.assertEqual(invalid_snapshot["completeness"], "invalid")
        with self.assertRaisesRegex(ValueError, "incomplete evidence"):
            build_decision_record(
                invalid_snapshot,
                decision="allow",
                release_gate_report={"decision": "allow", "hard_blockers": []},
                judge_results=[],
                policy_version="v1",
                policy_hash=digest(b"policy"),
                model_versions=["local:test"],
                created_at="2026-07-12T00:00:01Z",
            )

    def test_authorized_versioned_reference_reaches_pipeline_without_exposing_object_identity(self):
        content = png()
        reference = artifact_reference(content)
        result = process_artifact_reference(
            reference,
            reader=versioned_reader(reference, content),
            expected_scope=scope(),
            expected_purpose="release-evaluation",
            now="2026-07-12T12:00:00Z",
            scanner=ProductionScanner(),
            require_production_scanner=True,
        )
        self.validate(result)
        resolution_schema = json.loads(
            (ROOT / "docs/a2/schemas/artifact_reference_resolution.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.Draft202012Validator(resolution_schema).validate(
            result["artifact_reference_resolution"]
        )
        self.assertTrue(result["evaluation_eligible"])
        self.assertEqual(result["artifact_reference_resolution"]["status"], "verified")
        serialized = json.dumps(result, sort_keys=True)
        self.assertNotIn(reference["container_ref"], serialized)
        self.assertNotIn(reference["object_ref"], serialized)
        self.assertNotIn(reference["object_version"], serialized)

        snapshot = build_evidence_snapshot(
            {"run_id": "run-ref-1", "final_response": "done"},
            organization_id="org-a",
            tenant_id="tenant-a",
            workspace_id="workspace-a",
            project_id="project-a",
            environment_id="test",
            run_id="run-ref-1",
            case_id="case-ref-1",
            scenario_id="scenario-ref-1",
            created_at="2026-07-12T12:00:01Z",
            required_modalities=["text", "image"],
            artifact_pipeline_records=[result],
        )
        self.assertEqual(
            snapshot["artifacts"][-1]["reference_resolution_hash"],
            result["artifact_reference_resolution"]["resolution_hash"],
        )

    def test_scope_purpose_expiry_and_mutable_version_block_before_object_read(self):
        content = png()
        cases = []

        cross_tenant = artifact_reference(content)
        cross_tenant["tenant_scope"]["tenant_id"] = "tenant-b"
        cross_tenant["authorization_binding_hash"] = authorization_binding_hash(cross_tenant)
        cases.append((cross_tenant, "tenant_scope_mismatch", "2026-07-12T12:00:00Z"))

        wrong_purpose = artifact_reference(content)
        wrong_purpose["purpose"] = "model-training"
        wrong_purpose["authorization_binding_hash"] = authorization_binding_hash(wrong_purpose)
        cases.append((wrong_purpose, "purpose_mismatch", "2026-07-12T12:00:00Z"))

        expired = artifact_reference(content)
        cases.append((expired, "reference_expired", "2026-07-13T00:00:00Z"))

        mutable = artifact_reference(content)
        mutable["object_version"] = "latest"
        mutable["authorization_binding_hash"] = authorization_binding_hash(mutable)
        cases.append((mutable, "mutable_object_version_forbidden", "2026-07-12T12:00:00Z"))

        for reference, blocker, now in cases:
            with self.subTest(blocker=blocker):
                result = process_artifact_reference(
                    reference,
                    reader=versioned_reader(reference, content),
                    expected_scope=scope(),
                    expected_purpose="release-evaluation",
                    now=now,
                    scanner=ProductionScanner(),
                )
                self.validate(result)
                self.assertFalse(result["evaluation_eligible"])
                self.assertIn(blocker, result["blockers"])
                self.assertFalse(result["artifact_reference_resolution"]["read_performed"])
                self.assertEqual(result["extraction"]["status"], "blocked")

    def test_incomplete_expected_scope_blocks_before_read(self):
        content = png()
        reference = artifact_reference(content)
        incomplete_scope = scope()
        incomplete_scope["environment_id"] = ""
        result = process_artifact_reference(
            reference,
            reader=versioned_reader(reference, content),
            expected_scope=incomplete_scope,
            expected_purpose="release-evaluation",
            now="2026-07-12T12:00:00Z",
            scanner=ProductionScanner(),
        )
        self.assertIn("expected_scope_incomplete", result["blockers"])
        self.assertFalse(result["artifact_reference_resolution"]["read_performed"])

    def test_object_replacement_short_read_media_and_version_mismatch_fail_closed(self):
        content = png()
        reference = artifact_reference(content)
        cases = [
            (
                versioned_reader(reference, png(width=4, height=4)),
                "object_content_hash_mismatch",
            ),
            (
                versioned_reader(reference, content[:-1]),
                "object_size_mismatch",
            ),
            (
                versioned_reader(reference, content, media_type="image/jpeg"),
                "object_media_type_mismatch",
            ),
            (
                versioned_reader(reference, content, version="version-0002"),
                "object_version_mismatch",
            ),
        ]
        for reader, blocker in cases:
            with self.subTest(blocker=blocker):
                result = process_artifact_reference(
                    reference,
                    reader=reader,
                    expected_scope=scope(),
                    expected_purpose="release-evaluation",
                    now="2026-07-12T12:00:00Z",
                    scanner=ProductionScanner(),
                )
                self.validate(result)
                self.assertFalse(result["evaluation_eligible"])
                self.assertIn(blocker, result["blockers"])
                self.assertTrue(result["artifact_reference_resolution"]["read_performed"])
                self.assertEqual(result["extraction"]["status"], "blocked")

    def test_reference_binding_tamper_and_bounded_read_fail_closed(self):
        content = png()
        tampered = artifact_reference(content)
        tampered["media_type"] = "image/jpeg"
        result = process_artifact_reference(
            tampered,
            reader=versioned_reader(tampered, content),
            expected_scope=scope(),
            expected_purpose="release-evaluation",
            now="2026-07-12T12:00:00Z",
            scanner=ProductionScanner(),
        )
        self.assertIn("authorization_binding_mismatch", result["blockers"])
        self.assertFalse(result["artifact_reference_resolution"]["read_performed"])

        oversized = artifact_reference(content)
        result = process_artifact_reference(
            oversized,
            reader=versioned_reader(oversized, content),
            expected_scope=scope(),
            expected_purpose="release-evaluation",
            now="2026-07-12T12:00:00Z",
            scanner=ProductionScanner(),
            limits=ArtifactLimits(max_artifact_bytes=len(content) - 1),
        )
        self.assertEqual(result["blockers"], ["artifact_size_exceeded"])
        self.assertFalse(result["artifact_reference_resolution"]["read_performed"])


if __name__ == "__main__":
    unittest.main()
