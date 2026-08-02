from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "releasefoundry.a1.provider_execution_receipt.v1"
RELEASE_SCHEMA_VERSION = "releasefoundry.a1.release_receipt.v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
STATUSES = frozenset({"succeeded", "failed"})
CAPABILITIES = frozenset({"text", "image", "audio", "file", "video", "stream", "tools", "usage"})


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: bytes | str | Mapping[str, Any] | list[Any]) -> str:
    if isinstance(value, str):
        value = value.encode()
    elif not isinstance(value, bytes):
        value = canonical_json(value)
    return sha256(value).hexdigest()


def _timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("timestamp must be timezone-aware ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware ISO-8601")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hex(value: str, name: str, *, optional: bool = False) -> str:
    if optional and value == "":
        return value
    if not HEX64.fullmatch(value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")
    return value


@dataclass(frozen=True, slots=True)
class ProviderExecutionReceipt:
    receipt_id: str
    provider: str
    model: str
    endpoint_sha256: str
    invoked_at: str
    completed_at: str
    request_binding_sha256: str
    response_binding_sha256: str
    evidence_sha256: str
    capabilities: tuple[str, ...]
    status: str
    git_sha: str
    release_candidate: str
    request_id_sha256: str = ""
    previous_receipt_sha256: str = ""
    safe_response_shape: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    receipt_sha256: str = ""

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("receipt_sha256")
        value["capabilities"] = list(self.capabilities)
        return value

    def to_dict(self) -> dict[str, Any]:
        return self.payload() | {"receipt_sha256": self.receipt_sha256}


def create_provider_receipt(*, provider: str, model: str, endpoint: str,
                            invoked_at: str, completed_at: str, request_binding: Any,
                            response_binding: Any, evidence: bytes | str,
                            capabilities: Iterable[str], status: str, git_sha: str,
                            release_candidate: str, request_id: str = "",
                            previous_receipt_sha256: str = "",
                            safe_response_shape: Mapping[str, Any] | None = None) -> ProviderExecutionReceipt:
    caps = tuple(sorted(set(capabilities)))
    if not provider.strip() or not model.strip() or not endpoint.startswith(("http://", "https://")):
        raise ValueError("provider, model, and HTTP(S) endpoint are required")
    if not caps or set(caps) - CAPABILITIES:
        raise ValueError("unsupported or empty capabilities")
    if status not in STATUSES:
        raise ValueError("status must be succeeded or failed")
    if status != "succeeded":
        caps = tuple()
    if not re.fullmatch(r"[0-9a-f]{7,64}", git_sha):
        raise ValueError("git_sha must be lowercase Git hex")
    invoked, completed = _timestamp(invoked_at), _timestamp(completed_at)
    if datetime.fromisoformat(completed.replace("Z", "+00:00")) < datetime.fromisoformat(invoked.replace("Z", "+00:00")):
        raise ValueError("completed_at precedes invoked_at")
    evidence_bytes = evidence.encode() if isinstance(evidence, str) else evidence
    if not evidence_bytes:
        raise ValueError("evidence is required")
    provisional = ProviderExecutionReceipt(
        receipt_id="pending", provider=provider, model=model,
        endpoint_sha256=digest(endpoint.rstrip("/")), invoked_at=invoked,
        completed_at=completed, request_binding_sha256=digest(request_binding),
        response_binding_sha256=digest(response_binding), evidence_sha256=digest(evidence_bytes),
        capabilities=caps, status=status, git_sha=git_sha,
        release_candidate=release_candidate.strip(), request_id_sha256=digest(request_id) if request_id else "",
        previous_receipt_sha256=previous_receipt_sha256,
        safe_response_shape=dict(safe_response_shape or {}),
    )
    _hex(previous_receipt_sha256, "previous_receipt_sha256", optional=True)
    receipt_id = "provider_receipt_" + digest(provisional.payload() | {"receipt_id": ""})[:20]
    next_value = provisional.payload() | {"receipt_id": receipt_id}
    next_value["capabilities"] = tuple(next_value["capabilities"])
    provisional = ProviderExecutionReceipt(**next_value)
    final_value = provisional.payload() | {"receipt_sha256": digest(provisional.payload())}
    final_value["capabilities"] = tuple(final_value["capabilities"])
    return ProviderExecutionReceipt(**final_value)


def verify_provider_receipt(value: Mapping[str, Any], *, expected_previous: str | None = None) -> ProviderExecutionReceipt:
    try:
        receipt = ProviderExecutionReceipt(**(dict(value) | {"capabilities": tuple(value["capabilities"])}))
    except (KeyError, TypeError) as exc:
        raise ValueError("malformed provider receipt") from exc
    for name in ("endpoint_sha256", "request_binding_sha256", "response_binding_sha256", "evidence_sha256", "receipt_sha256"):
        _hex(getattr(receipt, name), name)
    _hex(receipt.request_id_sha256, "request_id_sha256", optional=True)
    _hex(receipt.previous_receipt_sha256, "previous_receipt_sha256", optional=True)
    if receipt.schema_version != SCHEMA_VERSION or digest(receipt.payload()) != receipt.receipt_sha256:
        raise ValueError("provider receipt integrity verification failed")
    if expected_previous is not None and receipt.previous_receipt_sha256 != expected_previous:
        raise ValueError("provider receipt chain mismatch")
    _timestamp(receipt.invoked_at); _timestamp(receipt.completed_at)
    if receipt.status not in STATUSES or set(receipt.capabilities) - CAPABILITIES or tuple(sorted(set(receipt.capabilities))) != receipt.capabilities:
        raise ValueError("provider receipt semantics invalid")
    if receipt.status != "succeeded" and receipt.capabilities:
        raise ValueError("failed receipt cannot claim capabilities")
    return receipt


class ProviderReceiptStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[ProviderExecutionReceipt]:
        if not self.path.exists():
            return []
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ValueError("receipt store must contain an array")
        result, previous = [], ""
        for item in value:
            receipt = verify_provider_receipt(item, expected_previous=previous)
            result.append(receipt); previous = receipt.receipt_sha256
        return result

    def append(self, receipt: ProviderExecutionReceipt) -> None:
        existing = self.load()
        expected = existing[-1].receipt_sha256 if existing else ""
        verify_provider_receipt(receipt.to_dict(), expected_previous=expected)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [item.to_dict() for item in existing] + [receipt.to_dict()]
        fd, name = tempfile.mkstemp(prefix=self.path.name, dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, sort_keys=True, indent=2); handle.write("\n")
                handle.flush(); os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)


def build_release_receipt(*, git_sha: str, release_candidate: str,
                          provider_receipts: Iterable[Mapping[str, Any]],
                          evidence_files: Mapping[str, bytes | str], generated_at: str) -> dict[str, Any]:
    receipts = [verify_provider_receipt(item) for item in provider_receipts]
    refs = [{"name": name, "sha256": digest(content)} for name, content in sorted(evidence_files.items())]
    body = {"schema_version": RELEASE_SCHEMA_VERSION, "git_sha": git_sha,
            "release_candidate": release_candidate, "generated_at": _timestamp(generated_at),
            "provider_receipt_sha256s": sorted(item.receipt_sha256 for item in receipts),
            "evidence_refs": refs}
    return body | {"release_receipt_sha256": digest(body)}


def verify_release_receipt(value: Mapping[str, Any]) -> bool:
    body = dict(value); claimed = body.pop("release_receipt_sha256", "")
    _hex(claimed, "release_receipt_sha256")
    if body.get("schema_version") != RELEASE_SCHEMA_VERSION or digest(body) != claimed:
        raise ValueError("release receipt integrity verification failed")
    for ref in body.get("evidence_refs", []): _hex(ref["sha256"], "evidence_ref.sha256")
    for item in body.get("provider_receipt_sha256s", []): _hex(item, "provider_receipt_sha256")
    return True