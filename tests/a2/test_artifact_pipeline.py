import hashlib
import io
import json
from pathlib import Path
import struct
import unittest
import wave
import zlib

import jsonschema

from services.judge.artifact_pipeline import ArtifactLimits, SignatureScanner, process_artifact
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


def png(width=2, height=3):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\x00" + (b"\x00\x00\x00" * width)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw * height)) + chunk(b"IEND", b"")


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
        self.assertEqual(snapshot["completeness"], "complete")
        self.assertIn("image", snapshot["observed_modalities"])
        self.assertEqual(snapshot["artifacts"][-1]["reference_hash"], valid_pipeline["manifest"]["manifest_id"])
        self.assertEqual(
            snapshot["extractor_provenance"][-1]["extractor_id"],
            valid_pipeline["extraction"]["extractor_id"],
        )

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


if __name__ == "__main__":
    unittest.main()
