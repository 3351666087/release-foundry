from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
import re
from typing import Any, Mapping

PROVIDER_STREAM_SCHEMA_VERSION = "releasefoundry.provider_stream.v1"
_ZERO_DIGEST = "0" * 64
_ENTRY_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ProviderStreamIntegrityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderStreamFrame:
    sequence: int
    kind: str
    content_digest: str
    previous_digest: str
    frame_digest: str
    terminal: bool
    entry_id: str | None = None
    fencing_token: int | None = None


class ProviderStreamLedger:
    """Content-free stream integrity ledger shared by Python and TypeScript."""

    def __init__(
        self,
        snapshot: Mapping[str, Any] | None = None,
        *,
        entry_id: str | None = None,
        fencing_token: int | None = None,
    ) -> None:
        self._frames: list[dict[str, Any]] = []
        self._terminal = False
        self._entry_id, self._fencing_token = _validate_binding(entry_id, fencing_token)
        if snapshot is not None:
            self._load(snapshot)

    def observe(self, sequence: int, kind: str, content: Any, *, terminal: bool = False) -> ProviderStreamFrame:
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise ProviderStreamIntegrityError("stream sequence must be a non-negative integer")
        if not isinstance(kind, str) or not kind or len(kind) > 64:
            raise ProviderStreamIntegrityError("stream kind must be a controlled non-empty label")
        if self._terminal:
            raise ProviderStreamIntegrityError("stream already has a terminal frame")
        content_digest = _content_digest(content)
        if sequence < len(self._frames):
            existing = self._frames[sequence]
            if existing["kind"] == kind and existing["content_digest"] == content_digest and existing["terminal"] is terminal:
                return ProviderStreamFrame(**existing)
            raise ProviderStreamIntegrityError("stream sequence conflicts with an existing frame")
        if sequence != len(self._frames):
            raise ProviderStreamIntegrityError("stream sequence contains a gap or is out of order")
        previous_digest = self._frames[-1]["frame_digest"] if self._frames else _ZERO_DIGEST
        frame = {
            "sequence": sequence,
            "kind": kind,
            "content_digest": content_digest,
            "previous_digest": previous_digest,
            "frame_digest": _frame_digest(
                sequence,
                kind,
                content_digest,
                previous_digest,
                terminal,
                self._entry_id,
                self._fencing_token,
            ),
            "terminal": terminal,
        }
        if self._entry_id is not None:
            frame["entry_id"] = self._entry_id
            frame["fencing_token"] = self._fencing_token
        self._frames.append(frame)
        self._terminal = terminal
        return ProviderStreamFrame(**frame)

    def finalize(self) -> dict[str, Any]:
        if not self._terminal:
            raise ProviderStreamIntegrityError("stream is missing a terminal frame")
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        snapshot = {
            "schema_version": PROVIDER_STREAM_SCHEMA_VERSION,
            "frames": [dict(frame) for frame in self._frames],
            "frame_count": len(self._frames),
            "terminal_observed": self._terminal,
            "stream_digest": self._frames[-1]["frame_digest"] if self._frames else _ZERO_DIGEST,
        }
        if self._entry_id is not None:
            snapshot["entry_id"] = self._entry_id
            snapshot["fencing_token"] = self._fencing_token
        return snapshot

    def _load(self, snapshot: Mapping[str, Any]) -> None:
        if snapshot.get("schema_version") != PROVIDER_STREAM_SCHEMA_VERSION:
            raise ProviderStreamIntegrityError("unsupported provider stream schema")
        allowed_snapshot_fields = {
            "schema_version", "frames", "frame_count", "terminal_observed", "stream_digest"
        }
        snapshot_entry_id, snapshot_fencing_token = _validate_binding(
            snapshot.get("entry_id"), snapshot.get("fencing_token")
        )
        if snapshot_entry_id is not None:
            allowed_snapshot_fields.update({"entry_id", "fencing_token"})
        if set(snapshot) != allowed_snapshot_fields:
            raise ProviderStreamIntegrityError("provider stream snapshot is malformed")
        if self._entry_id is None:
            self._entry_id, self._fencing_token = snapshot_entry_id, snapshot_fencing_token
        elif (snapshot_entry_id, snapshot_fencing_token) != (self._entry_id, self._fencing_token):
            raise ProviderStreamIntegrityError("provider stream journal binding conflicts with constructor")
        frames = snapshot.get("frames")
        if not isinstance(frames, list):
            raise ProviderStreamIntegrityError("provider stream frames must be a list")
        for raw in frames:
            if not isinstance(raw, Mapping):
                raise ProviderStreamIntegrityError("provider stream frame is malformed")
            required = {"sequence", "kind", "content_digest", "previous_digest", "frame_digest", "terminal"}
            if self._entry_id is not None:
                required.update({"entry_id", "fencing_token"})
            if (
                set(raw) != required
                or not _is_sha256(raw["content_digest"])
                or not _is_sha256(raw["previous_digest"])
                or not _is_sha256(raw["frame_digest"])
            ):
                raise ProviderStreamIntegrityError("provider stream frame is malformed")
            if self._entry_id is not None and (
                raw["entry_id"] != self._entry_id or raw["fencing_token"] != self._fencing_token
            ):
                raise ProviderStreamIntegrityError("provider stream frame journal binding is invalid")
            frame = self.observe(
                raw["sequence"],
                raw["kind"],
                {"sha256": raw["content_digest"]},
                terminal=raw["terminal"],
            )
            if (
                frame.content_digest != raw["content_digest"]
                or frame.previous_digest != raw["previous_digest"]
                or frame.frame_digest != raw["frame_digest"]
            ):
                raise ProviderStreamIntegrityError("provider stream digest chain is invalid")
        expected = self.snapshot()
        for field in ("frame_count", "terminal_observed", "stream_digest"):
            if snapshot.get(field) != expected[field]:
                raise ProviderStreamIntegrityError("provider stream summary is invalid")


def canonical_provider_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _content_digest(content: Any) -> str:
    if (
        isinstance(content, Mapping)
        and set(content) == {"sha256"}
        and _is_sha256(content["sha256"])
    ):
        return content["sha256"]
    if isinstance(content, bytes):
        payload = content
    elif isinstance(content, str):
        payload = content.encode("utf-8")
    else:
        payload = canonical_provider_json(content).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _frame_digest(
    sequence: int,
    kind: str,
    content_digest: str,
    previous_digest: str,
    terminal: bool,
    entry_id: str | None,
    fencing_token: int | None,
) -> str:
    frame = {
        "content_digest": content_digest,
        "kind": kind,
        "previous_digest": previous_digest,
        "sequence": sequence,
        "terminal": terminal,
    }
    if entry_id is not None:
        frame["entry_id"] = entry_id
        frame["fencing_token"] = fencing_token
    payload = canonical_provider_json(frame)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_binding(entry_id: Any, fencing_token: Any) -> tuple[str | None, int | None]:
    if entry_id is None and fencing_token is None:
        return None, None
    if entry_id is None or fencing_token is None:
        raise ProviderStreamIntegrityError("provider stream journal binding fields must appear together")
    if not isinstance(entry_id, str) or _ENTRY_ID.fullmatch(entry_id) is None:
        raise ProviderStreamIntegrityError("provider stream entry_id is invalid")
    if not isinstance(fencing_token, int) or isinstance(fencing_token, bool) or fencing_token <= 0:
        raise ProviderStreamIntegrityError("provider stream fencing_token must be a positive integer")
    return entry_id, fencing_token
