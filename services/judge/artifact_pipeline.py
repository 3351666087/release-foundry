"""Tenant-scoped, fail-closed multimodal artifact ingestion and extraction."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import re
import struct
import wave
from typing import Any, Protocol

from .artifact_reference import (
    ArtifactReferenceError,
    VersionedObjectReader,
    read_authorized_artifact,
)
from .signed_artifact_reference import (
    ArtifactAuthorizationLedger,
    KeyResolver,
    SIGNED_ARTIFACT_REFERENCE_SCHEMA_VERSION,
    read_signed_artifact,
)
from .result_persistence import stable_hash


MANIFEST_SCHEMA_VERSION = "a2.artifact_manifest.v1"
EXTRACTION_SCHEMA_VERSION = "a2.artifact_extraction.v1"
PIPELINE_SCHEMA_VERSION = "a2.multimodal_artifact_pipeline.v1"
SCOPE_FIELDS = ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
SUPPORTED_MEDIA_TYPES = {
    "text/plain": "text",
    "text/markdown": "text",
    "application/json": "file",
    "application/pdf": "file",
    "image/png": "image",
    "image/jpeg": "image",
    "audio/wav": "audio",
    "video/mp4": "video",
}


class ArtifactScanner(Protocol):
    scanner_id: str
    scanner_version: str

    def scan(self, content: bytes, media_type: str) -> dict[str, Any]: ...


class ExtractorRuntime(Protocol):
    def extract(
        self,
        content: bytes,
        *,
        media_type: str,
        input_hash: str,
        limits: "ArtifactLimits",
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ArtifactLimits:
    max_artifact_bytes: int = 25 * 1024 * 1024
    max_text_chars: int = 1_000_000
    max_pdf_pages: int = 2_000
    max_image_pixels: int = 100_000_000
    max_audio_seconds: float = 7_200.0
    max_video_seconds: float = 14_400.0


class SignatureScanner:
    """Deterministic development scanner with explicit, non-production provenance."""

    scanner_id = "a2.signature_scanner"
    scanner_version = "1.0.0"

    def scan(self, content: bytes, media_type: str) -> dict[str, Any]:
        suspicious = (
            b"eicar-standard-antivirus-test-file" in content.lower()
            or (media_type != "application/pdf" and content.startswith(b"MZ"))
        )
        return {
            "status": "blocked" if suspicious else "clean",
            "engine": self.scanner_id,
            "engine_version": self.scanner_version,
            "production_qualified": False,
            "signature_set": "a2-development-signatures-v1",
        }


def process_artifact(
    submission: dict[str, Any],
    content: bytes,
    *,
    scanner: ArtifactScanner | None,
    limits: ArtifactLimits | None = None,
    require_production_scanner: bool = False,
    extractor_runtime: ExtractorRuntime | None = None,
    require_isolated_extraction: bool = False,
) -> dict[str, Any]:
    """Validate, scan and extract one artifact without returning raw content."""
    limits = limits or ArtifactLimits()
    blockers: list[str] = []
    scope = _scope(submission, blockers)
    artifact_id = str(submission.get("artifact_id") or "")
    filename = str(submission.get("filename") or "")
    claimed_media_type = str(submission.get("media_type") or "").lower()
    expected_hash = str(submission.get("content_hash") or "")
    actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()

    if not artifact_id:
        blockers.append("artifact_id_missing")
    if not filename or filename != _safe_filename(filename):
        blockers.append("unsafe_filename")
    if not content:
        blockers.append("artifact_empty")
    if len(content) > limits.max_artifact_bytes:
        blockers.append("artifact_size_exceeded")
    if expected_hash != actual_hash:
        blockers.append("content_hash_mismatch")

    detected_media_type = sniff_media_type(content, filename)
    if detected_media_type == "application/octet-stream":
        blockers.append("media_type_unsupported")
    if claimed_media_type not in SUPPORTED_MEDIA_TYPES:
        blockers.append("claimed_media_type_unsupported")
    if claimed_media_type and detected_media_type != claimed_media_type:
        blockers.append("media_type_mismatch")

    scan = _scan(scanner, content, detected_media_type, require_production_scanner)
    if scan["status"] != "clean":
        blockers.append(f"scanner_{scan['status']}")
    if require_production_scanner and not scan["production_qualified"]:
        blockers.append("production_scanner_required")

    extraction = _blocked_extraction(actual_hash, detected_media_type, blockers)
    if not blockers:
        if require_isolated_extraction and extractor_runtime is None:
            extraction = _blocked_extraction(
                actual_hash,
                detected_media_type,
                ["isolated_extractor_required"],
            )
        elif extractor_runtime is not None:
            extraction = extractor_runtime.extract(
                content,
                media_type=detected_media_type,
                input_hash=actual_hash,
                limits=limits,
            )
        else:
            extraction = extract_artifact(
                content,
                media_type=detected_media_type,
                input_hash=actual_hash,
                limits=limits,
            )
        blockers.extend(extraction["blockers"])

    blockers = sorted(set(blockers))
    manifest_core = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "tenant_scope": scope,
        "artifact_id": artifact_id,
        "filename_hash": stable_hash(filename),
        "claimed_media_type": claimed_media_type,
        "detected_media_type": detected_media_type,
        "modality": SUPPORTED_MEDIA_TYPES.get(detected_media_type, "file"),
        "content_hash": actual_hash,
        "size_bytes": len(content),
        "source_ref_hash": stable_hash(str(submission.get("source_ref") or "")),
        "ingestion_status": "accepted" if not blockers else "blocked",
        "blockers": blockers,
        "security_scan": scan,
        "raw_content_included": False,
    }
    manifest = {**manifest_core, "manifest_id": stable_hash(manifest_core)}
    pipeline_core = {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "tenant_scope": scope,
        "manifest": manifest,
        "extraction": extraction,
        "evaluation_eligible": not blockers and extraction["status"] == "complete",
        "blockers": blockers,
        "raw_content_included": False,
        "release_authority": False,
    }
    return {**pipeline_core, "pipeline_record_hash": stable_hash(pipeline_core)}


def process_artifact_reference(
    reference: dict[str, Any],
    *,
    reader: VersionedObjectReader,
    expected_scope: dict[str, str],
    expected_purpose: str,
    now: str,
    scanner: ArtifactScanner | None,
    limits: ArtifactLimits | None = None,
    require_production_scanner: bool = False,
    extractor_runtime: ExtractorRuntime | None = None,
    require_isolated_extraction: bool = False,
    key_resolver: KeyResolver | None = None,
    authorization_ledger: ArtifactAuthorizationLedger | None = None,
    expected_issuer: str = "",
    expected_audience: str = "",
    expected_subject: str = "",
    expected_evaluation_job_id: str = "",
) -> dict[str, Any]:
    """Resolve an authorized immutable object and then run the artifact pipeline."""
    limits = limits or ArtifactLimits()
    try:
        if reference.get("schema_version") == SIGNED_ARTIFACT_REFERENCE_SCHEMA_VERSION:
            if key_resolver is None or authorization_ledger is None:
                raise ArtifactReferenceError(
                    ["signed_authorization_runtime_missing"],
                    {},
                )
            content, resolution = read_signed_artifact(
                reference,
                reader=reader,
                key_resolver=key_resolver,
                ledger=authorization_ledger,
                expected_scope=expected_scope,
                expected_purpose=expected_purpose,
                expected_issuer=expected_issuer,
                expected_audience=expected_audience,
                expected_subject=expected_subject,
                expected_evaluation_job_id=expected_evaluation_job_id,
                now=now,
                max_bytes=limits.max_artifact_bytes,
            )
        else:
            content, resolution = read_authorized_artifact(
                reference,
                reader=reader,
                expected_scope=expected_scope,
                expected_purpose=expected_purpose,
                now=now,
                max_bytes=limits.max_artifact_bytes,
            )
    except ArtifactReferenceError as error:
        return _blocked_reference_pipeline(reference, error.resolution, error.blockers)

    submission = {
        "tenant_scope": dict(expected_scope),
        "artifact_id": str(reference.get("artifact_id") or ""),
        "filename": _filename_for_media_type(
            str(reference.get("artifact_id") or "artifact"),
            str(reference.get("media_type") or ""),
        ),
        "media_type": str(reference.get("media_type") or ""),
        "content_hash": str(reference.get("content_hash") or ""),
        "source_ref": str(reference.get("reference_id") or ""),
    }
    pipeline = process_artifact(
        submission,
        content,
        scanner=scanner,
        limits=limits,
        require_production_scanner=require_production_scanner,
        extractor_runtime=extractor_runtime,
        require_isolated_extraction=require_isolated_extraction,
    )
    core = {
        key: value
        for key, value in pipeline.items()
        if key != "pipeline_record_hash"
    }
    core["artifact_reference_resolution"] = resolution
    return {**core, "pipeline_record_hash": stable_hash(core)}


def sniff_media_type(content: bytes, filename: str = "") -> str:
    """Use byte signatures first; extensions never override the content."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return "audio/wav"
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "video/mp4"
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return "application/octet-stream"
    if filename.lower().endswith(".json"):
        return "application/json"
    if filename.lower().endswith((".md", ".markdown")):
        return "text/markdown"
    if "\x00" not in text:
        return "text/plain"
    return "application/octet-stream"


def extract_artifact(
    content: bytes,
    *,
    media_type: str,
    input_hash: str,
    limits: ArtifactLimits,
) -> dict[str, Any]:
    extractors = {
        "image/png": _extract_png,
        "image/jpeg": _extract_jpeg,
        "audio/wav": _extract_wav,
        "application/pdf": _extract_pdf,
        "video/mp4": _extract_mp4,
        "text/plain": _extract_text,
        "text/markdown": _extract_text,
        "application/json": _extract_text,
    }
    extractor = extractors.get(media_type)
    if extractor is None:
        return _blocked_extraction(input_hash, media_type, ["extractor_unavailable"])
    error_class = ""
    try:
        metadata, quality = extractor(content, limits)
        blockers: list[str] = []
        status = "complete"
    except (ValueError, EOFError, wave.Error, struct.error) as error:
        metadata = {}
        quality = {"score": 0.0, "signals": [], "limitations": ["parser_rejected_input"]}
        blockers = ["extractor_failed"]
        status = "failed"
        error_class = type(error).__name__
    core = {
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "extractor_id": f"a2.safe_{SUPPORTED_MEDIA_TYPES.get(media_type, 'file')}_metadata",
        "extractor_version": "1.0.0",
        "media_type": media_type,
        "input_hash": input_hash,
        "status": status,
        "metadata": metadata,
        "quality": quality,
        "blockers": blockers,
        "error_class": error_class,
        "raw_content_included": False,
        "derived_content_included": False,
    }
    return {**core, "extraction_hash": stable_hash(core)}


def _extract_png(content: bytes, limits: ArtifactLimits) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(content) < 33 or content[12:16] != b"IHDR" or not content.endswith(b"IEND\xaeB`\x82"):
        raise ValueError("invalid PNG structure")
    width, height, bit_depth, color_type = struct.unpack(">IIBB", content[16:26])
    if width <= 0 or height <= 0 or width * height > limits.max_image_pixels:
        raise ValueError("image dimensions exceed policy")
    return (
        {"width": width, "height": height, "bit_depth": bit_depth, "color_type": color_type},
        {"score": 1.0, "signals": ["signature", "ihdr", "iend"], "limitations": ["metadata_only"]},
    )


def _extract_jpeg(content: bytes, limits: ArtifactLimits) -> tuple[dict[str, Any], dict[str, Any]]:
    offset = 2
    while offset + 9 < len(content):
        if content[offset] != 0xFF:
            raise ValueError("invalid JPEG marker")
        marker = content[offset + 1]
        if marker == 0xD9:
            break
        if marker in {0xD8, 0x01}:
            offset += 2
            continue
        length = struct.unpack(">H", content[offset + 2 : offset + 4])[0]
        if length < 2 or offset + 2 + length > len(content):
            raise ValueError("invalid JPEG segment")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height, width = struct.unpack(">HH", content[offset + 5 : offset + 9])
            if width <= 0 or height <= 0 or width * height > limits.max_image_pixels:
                raise ValueError("image dimensions exceed policy")
            return (
                {"width": width, "height": height, "encoding": "jpeg"},
                {"score": 0.95, "signals": ["signature", "sof"], "limitations": ["metadata_only"]},
            )
        offset += 2 + length
    raise ValueError("JPEG dimensions unavailable")


def _extract_wav(content: bytes, limits: ArtifactLimits) -> tuple[dict[str, Any], dict[str, Any]]:
    with wave.open(io.BytesIO(content), "rb") as reader:
        frames = reader.getnframes()
        rate = reader.getframerate()
        duration = frames / rate if rate else 0.0
        if duration <= 0 or duration > limits.max_audio_seconds:
            raise ValueError("audio duration exceeds policy")
        metadata = {
            "channels": reader.getnchannels(),
            "sample_width_bytes": reader.getsampwidth(),
            "sample_rate_hz": rate,
            "frame_count": frames,
            "duration_seconds": round(duration, 6),
        }
    return metadata, {
        "score": 1.0,
        "signals": ["riff", "wave_header", "duration"],
        "limitations": ["metadata_only", "transcript_not_generated"],
    }


def _extract_pdf(content: bytes, limits: ArtifactLimits) -> tuple[dict[str, Any], dict[str, Any]]:
    if not content.rstrip().endswith(b"%%EOF"):
        raise ValueError("PDF EOF missing")
    page_count = len(re.findall(rb"/Type\s*/Page(?!s)\b", content))
    if page_count <= 0 or page_count > limits.max_pdf_pages:
        raise ValueError("PDF page count outside policy")
    version = content[5:8].decode("ascii", errors="strict")
    return (
        {"pdf_version": version, "page_count": page_count},
        {
            "score": 0.8,
            "signals": ["header", "eof", "page_markers"],
            "limitations": ["metadata_only", "text_not_extracted", "active_content_not_executed"],
        },
    )


def _extract_mp4(content: bytes, limits: ArtifactLimits) -> tuple[dict[str, Any], dict[str, Any]]:
    brands: list[str] = []
    box_types: list[str] = []
    offset = 0
    while offset + 8 <= len(content):
        size = struct.unpack(">I", content[offset : offset + 4])[0]
        box_type = content[offset + 4 : offset + 8].decode("ascii", errors="strict")
        if size == 1:
            if offset + 16 > len(content):
                raise ValueError("truncated extended MP4 box")
            size = struct.unpack(">Q", content[offset + 8 : offset + 16])[0]
        if size < 8 or offset + size > len(content):
            raise ValueError("invalid MP4 box")
        box_types.append(box_type)
        if box_type == "ftyp" and size >= 16:
            brands.append(content[offset + 8 : offset + 12].decode("ascii", errors="strict"))
        offset += size
    if offset != len(content) or "ftyp" not in box_types or "moov" not in box_types:
        raise ValueError("required MP4 boxes missing")
    return (
        {"major_brands": sorted(set(brands)), "box_types": box_types, "duration_seconds": None},
        {
            "score": 0.7,
            "signals": ["ftyp", "bounded_box_walk", "moov"],
            "limitations": ["metadata_only", "duration_not_extracted", "keyframes_not_generated"],
        },
    )


def _extract_text(content: bytes, limits: ArtifactLimits) -> tuple[dict[str, Any], dict[str, Any]]:
    text = content.decode("utf-8")
    if len(text) > limits.max_text_chars:
        raise ValueError("text size exceeds policy")
    line_count = text.count("\n") + (1 if text else 0)
    return (
        {"character_count": len(text), "line_count": line_count},
        {"score": 1.0, "signals": ["utf8_valid"], "limitations": ["content_not_exported"]},
    )


def _scope(submission: dict[str, Any], blockers: list[str]) -> dict[str, str]:
    source = submission.get("tenant_scope")
    if not isinstance(source, dict):
        blockers.append("tenant_scope_missing")
        source = {}
    scope = {field: str(source.get(field) or "") for field in SCOPE_FIELDS}
    if not all(scope.values()):
        blockers.append("tenant_scope_incomplete")
    return scope


def _scan(
    scanner: ArtifactScanner | None,
    content: bytes,
    media_type: str,
    require_production_scanner: bool,
) -> dict[str, Any]:
    if scanner is None:
        return {
            "status": "unavailable",
            "engine": "",
            "engine_version": "",
            "production_qualified": False,
            "signature_set": "",
        }
    try:
        result = scanner.scan(content, media_type)
    except Exception as error:
        return {
            "status": "error",
            "engine": getattr(scanner, "scanner_id", ""),
            "engine_version": getattr(scanner, "scanner_version", ""),
            "production_qualified": False,
            "signature_set": "",
            "error_class": type(error).__name__,
        }
    status = str(result.get("status") or "error")
    if status not in {"clean", "blocked", "error"}:
        status = "error"
    return {
        "status": status,
        "engine": str(result.get("engine") or getattr(scanner, "scanner_id", "")),
        "engine_version": str(
            result.get("engine_version") or getattr(scanner, "scanner_version", "")
        ),
        "production_qualified": bool(result.get("production_qualified")),
        "signature_set": str(result.get("signature_set") or ""),
    }


def _blocked_extraction(input_hash: str, media_type: str, blockers: list[str]) -> dict[str, Any]:
    core = {
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "extractor_id": "a2.extraction_not_run",
        "extractor_version": "1.0.0",
        "media_type": media_type,
        "input_hash": input_hash,
        "status": "blocked",
        "metadata": {},
        "quality": {"score": 0.0, "signals": [], "limitations": ["ingestion_blocked"]},
        "blockers": sorted(set(blockers)),
        "error_class": "",
        "raw_content_included": False,
        "derived_content_included": False,
    }
    return {**core, "extraction_hash": stable_hash(core)}


def _safe_filename(filename: str) -> str:
    normalized = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if normalized in {"", ".", ".."} or "\x00" in normalized:
        return ""
    return normalized


def _filename_for_media_type(artifact_id: str, media_type: str) -> str:
    suffixes = {
        "text/plain": ".txt",
        "text/markdown": ".md",
        "application/json": ".json",
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "audio/wav": ".wav",
        "video/mp4": ".mp4",
    }
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", artifact_id) or "artifact"
    return safe_id + suffixes.get(media_type, ".bin")


def _blocked_reference_pipeline(
    reference: dict[str, Any],
    resolution: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    scope_source = reference.get("tenant_scope")
    scope = {
        field: str(scope_source.get(field) or "")
        if isinstance(scope_source, dict)
        else ""
        for field in SCOPE_FIELDS
    }
    content_hash = str(reference.get("content_hash") or "")
    media_type = str(reference.get("media_type") or "")
    artifact_id = str(reference.get("artifact_id") or "")
    blockers = sorted(set(blockers))
    manifest_core = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "tenant_scope": scope,
        "artifact_id": artifact_id,
        "filename_hash": stable_hash(""),
        "claimed_media_type": media_type,
        "detected_media_type": "",
        "modality": SUPPORTED_MEDIA_TYPES.get(media_type, "file"),
        "content_hash": content_hash,
        "size_bytes": 0,
        "source_ref_hash": stable_hash(str(reference.get("reference_id") or "")),
        "ingestion_status": "blocked",
        "blockers": blockers,
        "security_scan": {
            "status": "unavailable",
            "engine": "",
            "engine_version": "",
            "production_qualified": False,
            "signature_set": "",
        },
        "raw_content_included": False,
    }
    manifest = {**manifest_core, "manifest_id": stable_hash(manifest_core)}
    extraction = _blocked_extraction(content_hash, media_type, blockers)
    core = {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "tenant_scope": scope,
        "manifest": manifest,
        "extraction": extraction,
        "artifact_reference_resolution": resolution,
        "evaluation_eligible": False,
        "blockers": blockers,
        "raw_content_included": False,
        "release_authority": False,
    }
    return {**core, "pipeline_record_hash": stable_hash(core)}
