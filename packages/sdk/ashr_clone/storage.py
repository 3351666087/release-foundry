from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .api_client import redact_sensitive

JsonDict = dict[str, Any]

OBJECT_STORAGE_CONTRACT_VERSION = "ashr.clone.object_storage.v1"
OBJECT_STORAGE_VERIFICATION_VERSION = "ashr.clone.object_storage_verification.v1"
_SAFE_SCOPE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SAFE_CATEGORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SAFE_SUFFIX = re.compile(r"^\.[A-Za-z0-9][A-Za-z0-9_.-]{0,31}$")
_SECRET_REF_PREFIXES = ("env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:", "secret-ref:")
_SENSITIVE_KEY_PARTS = ("access_key", "secret_key", "api_key", "authorization", "bearer", "password", "credential", "token")
_ALLOWED_SAFETY_KEYS = {"raw_payload_included", "secret_value_present"}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ashr_live_[A-Za-z0-9_\-]+"),
)


class ObjectStorageContractError(ValueError):
    """Raised when an object storage manifest would not be public-safe."""


def sha256_bytes(content: bytes | str) -> str:
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    return hashlib.sha256(raw).hexdigest()


def scoped_object_key(*, tenant_id: str, project_id: str, run_id: str, object_id: str, category: str = "artifacts", suffix: str = ".bin") -> str:
    parts = {
        "category": category,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "run_id": run_id,
        "object_id": object_id,
    }
    for name, value in parts.items():
        if not isinstance(value, str) or not value:
            raise ObjectStorageContractError(f"{name} must be a non-empty string")
        pattern = _SAFE_CATEGORY if name == "category" else _SAFE_SCOPE_PART
        if not pattern.match(value):
            raise ObjectStorageContractError(f"{name} contains unsafe characters")
    if suffix and not _SAFE_SUFFIX.match(suffix):
        raise ObjectStorageContractError("suffix contains unsafe characters")
    return "/".join([category, tenant_id, project_id, run_id, f"{object_id}{suffix}"])


def build_object_manifest(
    *,
    backend: str,
    object_key: str,
    tenant_id: str,
    project_id: str,
    run_id: str,
    object_id: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    bucket_ref: str | None = None,
    endpoint_ref: str | None = None,
    region_ref: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> JsonDict:
    if backend not in {"local-filesystem", "s3-compatible"}:
        raise ObjectStorageContractError("backend must be local-filesystem or s3-compatible")
    _validate_object_key_scope(object_key=object_key, tenant_id=tenant_id, project_id=project_id, run_id=run_id)
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ObjectStorageContractError("sha256 must be a lowercase hex digest")
    if size_bytes < 0:
        raise ObjectStorageContractError("size_bytes must be non-negative")
    backend_refs = {
        "bucket_ref": bucket_ref,
        "endpoint_ref": endpoint_ref,
        "region_ref": region_ref,
        "access_key_ref_present": False,
        "secret_key_ref_present": False,
    }
    if backend == "local-filesystem":
        backend_refs.update({"storage_uri": f"local://object-store/{object_key}"})
    else:
        if not bucket_ref or not endpoint_ref:
            raise ObjectStorageContractError("s3-compatible manifests require bucket_ref and endpoint_ref")
        _assert_ref("bucket_ref", bucket_ref)
        _assert_ref("endpoint_ref", endpoint_ref)
        if region_ref is not None:
            _assert_ref("region_ref", region_ref)
        backend_refs.update({"storage_uri": f"s3-compatible://{bucket_ref}/{object_key}"})
    manifest = {
        "schema_version": OBJECT_STORAGE_CONTRACT_VERSION,
        "backend": backend,
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "run_id": str(run_id),
        "object_id": str(object_id),
        "object_key": object_key,
        "content_type": str(content_type),
        "size_bytes": int(size_bytes),
        "sha256": sha256,
        "raw_payload_included": False,
        "secret_value_present": False,
        "backend_refs": backend_refs,
        "metadata": _public_safe_metadata(metadata or {}),
    }
    assert_public_object_manifest_safe(manifest)
    return manifest


def assert_public_object_manifest_safe(manifest: Mapping[str, Any]) -> None:
    issues = _find_public_safety_issues(manifest)
    if issues:
        raise ObjectStorageContractError(f"object storage manifest is not public-safe: {issues[0]['reason']} at {issues[0]['path']}")


def verify_object_bytes(manifest: Mapping[str, Any], content: bytes | str) -> JsonDict:
    raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    expected = manifest.get("sha256")
    actual = hashlib.sha256(raw).hexdigest()
    expected_size = manifest.get("size_bytes")
    failures: list[JsonDict] = []
    if expected != actual:
        failures.append({"reason": "sha256_mismatch", "expected": expected, "actual": actual})
    if expected_size != len(raw):
        failures.append({"reason": "size_bytes_mismatch", "expected": expected_size, "actual": len(raw)})
    if bool(manifest.get("raw_payload_included")):
        failures.append({"reason": "raw_payload_included"})
    if bool(manifest.get("secret_value_present")):
        failures.append({"reason": "secret_value_present"})
    return {
        "schema_version": OBJECT_STORAGE_VERIFICATION_VERSION,
        "verified": not failures,
        "object_key": manifest.get("object_key"),
        "sha256": expected,
        "actual_sha256": actual,
        "size_bytes": expected_size,
        "actual_size_bytes": len(raw),
        "failures": failures,
        "raw_payload_included": False,
        "secret_value_present": False,
    }


@dataclass(slots=True)
class LocalFilesystemObjectStorage:
    root: Path | str

    def write_object(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        object_id: str,
        content: bytes | str,
        content_type: str,
        category: str = "artifacts",
        suffix: str = ".bin",
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        object_key = scoped_object_key(tenant_id=tenant_id, project_id=project_id, run_id=run_id, object_id=object_id, category=category, suffix=suffix)
        path = self._resolve_object_key(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        manifest = build_object_manifest(
            backend="local-filesystem",
            object_key=object_key,
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            object_id=object_id,
            content_type=content_type,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            metadata=metadata,
        )
        verification = self.verify_object(manifest)
        if not verification["verified"]:
            raise ObjectStorageContractError("local object write failed readback verification")
        return {**manifest, "write_readback_verification": verification}

    def read_object(self, manifest: Mapping[str, Any]) -> bytes:
        object_key = manifest.get("object_key")
        if not isinstance(object_key, str):
            raise ObjectStorageContractError("manifest object_key must be a string")
        return self._resolve_object_key(object_key).read_bytes()

    def verify_object(self, manifest: Mapping[str, Any]) -> JsonDict:
        content = self.read_object(manifest)
        return verify_object_bytes(manifest, content)

    def _resolve_object_key(self, object_key: str) -> Path:
        if object_key.startswith("/") or "\\" in object_key or any(part in {"", ".", ".."} for part in object_key.split("/")):
            raise ObjectStorageContractError("object_key contains unsafe path segments")
        root = Path(self.root).resolve()
        path = (root / object_key).resolve()
        if root != path and root not in path.parents:
            raise ObjectStorageContractError("object_key resolves outside storage root")
        return path


def _validate_object_key_scope(*, object_key: str, tenant_id: str, project_id: str, run_id: str) -> None:
    parts = object_key.split("/")
    if len(parts) < 5:
        raise ObjectStorageContractError("object_key must include category/tenant/project/run/object")
    if parts[1:4] != [str(tenant_id), str(project_id), str(run_id)]:
        raise ObjectStorageContractError("object_key tenant/project/run scope mismatch")
    if object_key.startswith("/") or "\\" in object_key or any(part in {"", ".", ".."} for part in parts):
        raise ObjectStorageContractError("object_key contains unsafe path segments")


def _assert_ref(name: str, value: str) -> None:
    if not any(value.startswith(prefix) for prefix in _SECRET_REF_PREFIXES):
        raise ObjectStorageContractError(f"{name} must use an approved reference prefix")


def _public_safe_metadata(metadata: Mapping[str, Any]) -> JsonDict:
    redacted = redact_sensitive(dict(metadata))
    safe: JsonDict = {}
    for key, value in redacted.items():
        normalized = str(key).lower().replace("-", "_")
        if normalized in _ALLOWED_SAFETY_KEYS or any(part in normalized for part in _SENSITIVE_KEY_PARTS):
            continue
        safe[str(key)] = value
    return safe


def _find_public_safety_issues(value: Any, *, path: str = "$") -> list[JsonDict]:
    issues: list[JsonDict] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            normalized = key_text.lower().replace("-", "_")
            item_path = f"{path}.{key_text}"
            if normalized not in _ALLOWED_SAFETY_KEYS and any(part in normalized for part in _SENSITIVE_KEY_PARTS) and not normalized.endswith("_ref") and not normalized.endswith("_ref_present"):
                issues.append({"reason": "sensitive_key_present", "path": item_path})
            issues.extend(_find_public_safety_issues(item, path=item_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_find_public_safety_issues(item, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        for pattern in _SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                issues.append({"reason": "secret_like_value_present", "path": path})
                break
        if value.startswith("file://") or re.match(r"^[A-Za-z]:[\\/]", value):
            issues.append({"reason": "absolute_local_path_present", "path": path})
    else:
        try:
            json.dumps(value)
        except TypeError:
            issues.append({"reason": "non_json_value_present", "path": path})
    return issues
