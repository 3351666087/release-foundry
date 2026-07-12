"""Authorized, version-pinned artifact retrieval for A2 evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Mapping, Protocol

from .result_persistence import stable_hash


ARTIFACT_REFERENCE_SCHEMA_VERSION = "a2.artifact_reference.v1"
ARTIFACT_REFERENCE_RESOLUTION_SCHEMA_VERSION = "a2.artifact_reference_resolution.v1"
SCOPE_FIELDS = ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
ALLOWED_STORAGE_PROVIDERS = {"a1-object-store", "s3-compatible", "azure-blob", "gcs"}
_OPAQUE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$")
_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")


class ArtifactReferenceError(ValueError):
    """Fail-closed reference error carrying only public-safe resolution metadata."""

    def __init__(self, blockers: list[str], resolution: dict[str, Any]):
        super().__init__(", ".join(blockers))
        self.blockers = blockers
        self.resolution = resolution


class VersionedObjectReader(Protocol):
    reader_id: str
    reader_version: str

    def read_version(
        self,
        *,
        storage_provider: str,
        container_ref: str,
        object_ref: str,
        object_version: str,
        max_bytes: int,
    ) -> "ObjectRead": ...


@dataclass(frozen=True)
class ObjectRead:
    content: bytes
    object_version: str
    media_type: str


class InMemoryVersionedObjectReader:
    """Deterministic test/reference reader; production adapters implement the same contract."""

    reader_id = "a2.in_memory_versioned_object_reader"
    reader_version = "1.0.0"

    def __init__(self, objects: Mapping[tuple[str, str, str, str], ObjectRead]):
        self._objects = dict(objects)

    def read_version(
        self,
        *,
        storage_provider: str,
        container_ref: str,
        object_ref: str,
        object_version: str,
        max_bytes: int,
    ) -> ObjectRead:
        key = (storage_provider, container_ref, object_ref, object_version)
        try:
            result = self._objects[key]
        except KeyError as error:
            raise FileNotFoundError("version-pinned object is unavailable") from error
        if len(result.content) > max_bytes:
            raise OverflowError("object exceeds bounded read limit")
        return result


def authorization_binding_hash(reference: Mapping[str, Any]) -> str:
    """Bind authorization to scope, immutable object identity, purpose and expiry."""
    binding = {
        "schema_version": reference.get("schema_version"),
        "reference_id": reference.get("reference_id"),
        "tenant_scope": reference.get("tenant_scope"),
        "artifact_id": reference.get("artifact_id"),
        "storage_provider": reference.get("storage_provider"),
        "container_ref": reference.get("container_ref"),
        "object_ref": reference.get("object_ref"),
        "object_version": reference.get("object_version"),
        "content_hash": reference.get("content_hash"),
        "size_bytes": reference.get("size_bytes"),
        "media_type": reference.get("media_type"),
        "purpose": reference.get("purpose"),
        "issued_at": reference.get("issued_at"),
        "expires_at": reference.get("expires_at"),
    }
    return stable_hash(binding)


def read_authorized_artifact(
    reference: Mapping[str, Any],
    *,
    reader: VersionedObjectReader,
    expected_scope: Mapping[str, str],
    expected_purpose: str,
    now: str,
    max_bytes: int,
) -> tuple[bytes, dict[str, Any]]:
    """Authorize and verify a bounded immutable object read before extraction."""
    blockers = _validate_reference(
        reference,
        expected_scope=expected_scope,
        expected_purpose=expected_purpose,
        now=now,
        max_bytes=max_bytes,
    )
    if blockers:
        resolution = _resolution(reference, reader, blockers, read_performed=False)
        raise ArtifactReferenceError(blockers, resolution)

    try:
        result = reader.read_version(
            storage_provider=str(reference["storage_provider"]),
            container_ref=str(reference["container_ref"]),
            object_ref=str(reference["object_ref"]),
            object_version=str(reference["object_version"]),
            max_bytes=max_bytes,
        )
    except FileNotFoundError:
        blockers.append("object_version_unavailable")
        resolution = _resolution(reference, reader, blockers, read_performed=True)
        raise ArtifactReferenceError(blockers, resolution) from None
    except OverflowError:
        blockers.append("bounded_read_exceeded")
        resolution = _resolution(reference, reader, blockers, read_performed=True)
        raise ArtifactReferenceError(blockers, resolution) from None
    except Exception as error:
        blockers.append(f"object_reader_error:{type(error).__name__}")
        resolution = _resolution(reference, reader, blockers, read_performed=True)
        raise ArtifactReferenceError(blockers, resolution) from None

    content = bytes(result.content)
    actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    if result.object_version != reference["object_version"]:
        blockers.append("object_version_mismatch")
    if len(content) != reference["size_bytes"]:
        blockers.append("object_size_mismatch")
    if actual_hash != reference["content_hash"]:
        blockers.append("object_content_hash_mismatch")
    if result.media_type != reference["media_type"]:
        blockers.append("object_media_type_mismatch")
    if blockers:
        resolution = _resolution(
            reference,
            reader,
            blockers,
            read_performed=True,
            actual_hash=actual_hash,
            actual_size=len(content),
            observed_version=result.object_version,
        )
        raise ArtifactReferenceError(sorted(set(blockers)), resolution)
    return content, _resolution(
        reference,
        reader,
        [],
        read_performed=True,
        actual_hash=actual_hash,
        actual_size=len(content),
        observed_version=result.object_version,
    )


def _validate_reference(
    reference: Mapping[str, Any],
    *,
    expected_scope: Mapping[str, str],
    expected_purpose: str,
    now: str,
    max_bytes: int,
) -> list[str]:
    blockers: list[str] = []
    if reference.get("schema_version") != ARTIFACT_REFERENCE_SCHEMA_VERSION:
        blockers.append("reference_schema_unsupported")
    for field in ("reference_id", "artifact_id", "container_ref", "object_ref", "object_version"):
        value = reference.get(field)
        if not isinstance(value, str) or not _OPAQUE_REF.fullmatch(value):
            blockers.append(f"{field}_invalid")
    provider = reference.get("storage_provider")
    if provider not in ALLOWED_STORAGE_PROVIDERS:
        blockers.append("storage_provider_not_allowed")
    if str(reference.get("object_version") or "").lower() in {"latest", "current", "head"}:
        blockers.append("mutable_object_version_forbidden")

    scope = reference.get("tenant_scope")
    if any(not str(expected_scope.get(field) or "") for field in SCOPE_FIELDS):
        blockers.append("expected_scope_incomplete")
    if not isinstance(scope, Mapping) or any(not str(scope.get(field) or "") for field in SCOPE_FIELDS):
        blockers.append("tenant_scope_incomplete")
    elif any(str(scope.get(field)) != str(expected_scope.get(field) or "") for field in SCOPE_FIELDS):
        blockers.append("tenant_scope_mismatch")

    content_hash = reference.get("content_hash")
    if not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash):
        blockers.append("content_hash_invalid")
    size_bytes = reference.get("size_bytes")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes <= 0:
        blockers.append("size_bytes_invalid")
    elif size_bytes > max_bytes:
        blockers.append("artifact_size_exceeded")
    if not isinstance(reference.get("media_type"), str) or not reference.get("media_type"):
        blockers.append("media_type_missing")
    if reference.get("purpose") != expected_purpose:
        blockers.append("purpose_mismatch")

    issued_at = _parse_time(reference.get("issued_at"), "issued_at", blockers)
    expires_at = _parse_time(reference.get("expires_at"), "expires_at", blockers)
    current = _parse_time(now, "evaluation_time", blockers)
    if issued_at and current and issued_at > current:
        blockers.append("reference_not_yet_valid")
    if expires_at and current and expires_at <= current:
        blockers.append("reference_expired")
    if issued_at and expires_at and expires_at <= issued_at:
        blockers.append("reference_lifetime_invalid")
    if reference.get("authorization_binding_hash") != authorization_binding_hash(reference):
        blockers.append("authorization_binding_mismatch")
    return sorted(set(blockers))


def _parse_time(value: Any, field: str, blockers: list[str]) -> datetime | None:
    if not isinstance(value, str):
        blockers.append(f"{field}_invalid")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        blockers.append(f"{field}_invalid")
        return None
    if parsed.tzinfo is None:
        blockers.append(f"{field}_timezone_required")
        return None
    return parsed.astimezone(timezone.utc)


def _resolution(
    reference: Mapping[str, Any],
    reader: VersionedObjectReader,
    blockers: list[str],
    *,
    read_performed: bool,
    actual_hash: str = "",
    actual_size: int | None = None,
    observed_version: str = "",
) -> dict[str, Any]:
    core = {
        "schema_version": ARTIFACT_REFERENCE_RESOLUTION_SCHEMA_VERSION,
        "reference_id_hash": stable_hash(str(reference.get("reference_id") or "")),
        "artifact_id": str(reference.get("artifact_id") or ""),
        "tenant_scope": {
            field: str((reference.get("tenant_scope") or {}).get(field) or "")
            if isinstance(reference.get("tenant_scope"), Mapping)
            else ""
            for field in SCOPE_FIELDS
        },
        "storage_provider": str(reference.get("storage_provider") or ""),
        "container_ref_hash": stable_hash(str(reference.get("container_ref") or "")),
        "object_ref_hash": stable_hash(str(reference.get("object_ref") or "")),
        "expected_object_version_hash": stable_hash(str(reference.get("object_version") or "")),
        "observed_object_version_hash": stable_hash(observed_version) if observed_version else "",
        "expected_content_hash": str(reference.get("content_hash") or ""),
        "actual_content_hash": actual_hash,
        "expected_size_bytes": reference.get("size_bytes")
        if isinstance(reference.get("size_bytes"), int)
        else None,
        "actual_size_bytes": actual_size,
        "purpose": str(reference.get("purpose") or ""),
        "reader_id": str(getattr(reader, "reader_id", "")),
        "reader_version": str(getattr(reader, "reader_version", "")),
        "read_performed": read_performed,
        "status": "verified" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "raw_content_included": False,
        "secret_material_included": False,
    }
    return {**core, "resolution_hash": stable_hash(core)}
