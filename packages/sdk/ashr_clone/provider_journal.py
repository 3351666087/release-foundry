from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
from typing import Any, Mapping, Sequence

JsonDict = dict[str, Any]
PROVIDER_JOURNAL_SCHEMA_VERSION = "ashr.clone.provider_request_journal.python.v1"
PROVIDER_MODALITIES = ("text", "image", "audio", "file", "video")
PROVIDER_JOURNAL_STATES = frozenset(
    {"reserved", "in_flight", "retry_wait", "succeeded", "failed_terminal", "indeterminate"}
)
TERMINAL_STATES = frozenset({"succeeded", "failed_terminal"})
PERSISTENCE_CAPABILITIES = {
    "atomic_single_process_replace": True,
    "cross_process_claim_coordination": False,
    "distributed_consensus": False,
    "lease_survives_process_restart": False,
    "restart_in_flight_policy": "indeterminate",
}
_ENDPOINT_OPERATION = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_SAFE_EVIDENCE_FIELDS = frozenset(
    {"finish_reason", "provider_request_id", "response_model", "status_code", "error_code", "retryable"}
)


class ProviderJournalError(RuntimeError):
    pass


class ProviderJournalConflict(ProviderJournalError):
    pass


class ProviderJournalStateError(ProviderJournalError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderRequestIdentity:
    tenant_id: str
    project_id: str
    provider: str
    model: str
    endpoint_operation: str


@dataclass(frozen=True, slots=True)
class JournalDecision:
    entry: JsonDict
    idempotent_replay: bool


class ProviderRequestJournal:
    """Restart-persistent local JSON journal with single-process claims and fencing."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._state, restored = self._load_or_create()
        if restored:
            self._recover_after_restart()

    def begin(
        self,
        identity: ProviderRequestIdentity,
        idempotency_key: str,
        request: Mapping[str, Any],
        *,
        now: str | None = None,
    ) -> JournalDecision:
        self._validate_identity(identity)
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise ValueError("idempotency_key must be a non-empty string")
        if not isinstance(request, Mapping):
            raise TypeError("request must be a mapping")
        timestamp = _timestamp(now)
        with self._lock:
            scope = {
                "tenant_id": identity.tenant_id,
                "project_id": identity.project_id,
                "provider": identity.provider,
                "model": identity.model,
                "endpoint_operation": identity.endpoint_operation,
            }
            scope_fingerprint = self._fingerprint(scope)
            idempotency_fingerprint = self._fingerprint(
                {"scope_fingerprint": scope_fingerprint, "idempotency_key": idempotency_key}
            )
            request_fingerprint = self._fingerprint({"request": request})
            lookup_key = f"{scope_fingerprint}:{idempotency_fingerprint}"
            existing_id = self._state["lookup"].get(lookup_key)
            if existing_id:
                existing = self._state["entries"][existing_id]
                self._expire_if_stale(existing, timestamp)
                if not hmac.compare_digest(existing["request_fingerprint"], request_fingerprint):
                    raise ProviderJournalConflict(
                        "idempotency key was already used with a different request fingerprint"
                    )
                replay = _clone(existing)
                replay["replay_evidence"] = {
                    "replayed_at": timestamp,
                    "persistence_capabilities": _clone(PERSISTENCE_CAPABILITIES),
                    "source_state": existing["state"],
                }
                return JournalDecision(replay, True)

            entry_id = f"pjr_{hashlib.sha256(lookup_key.encode('ascii')).hexdigest()[:24]}"
            entry = {
                "schema_version": PROVIDER_JOURNAL_SCHEMA_VERSION,
                "entry_id": entry_id,
                "scope_fingerprint": scope_fingerprint,
                "idempotency_fingerprint": idempotency_fingerprint,
                "request_fingerprint": request_fingerprint,
                "identity_evidence": {
                    "provider_fingerprint": self._fingerprint({"provider": identity.provider}),
                    "model_fingerprint": self._fingerprint({"model": identity.model}),
                    "endpoint_operation": identity.endpoint_operation,
                    "tenant_fingerprint": self._fingerprint({"tenant_id": identity.tenant_id}),
                    "project_fingerprint": self._fingerprint({"project_id": identity.project_id}),
                },
                "request_evidence": _request_evidence(request),
                "state": "reserved",
                "attempt_count": 0,
                "fencing_token": 0,
                "lease_owner_fingerprint": None,
                "lease_expires_at": None,
                "retry_not_before": None,
                "stream_observed": False,
                "stream_snapshot": None,
                "created_at": timestamp,
                "updated_at": timestamp,
                "state_history": [{"state": "reserved", "at": timestamp}],
                "retry_evidence": [],
                "reconciliation_evidence": [],
                "usage_evidence": _normalize_usage({}),
                "response_evidence": {},
                "raw_request_persisted": False,
                "raw_response_persisted": False,
                "credentials_persisted": False,
            }
            self._state["entries"][entry_id] = entry
            self._state["lookup"][lookup_key] = entry_id
            self._persist()
            return JournalDecision(_clone(entry), False)

    def claim(
        self,
        entry_id: str,
        *,
        lease_owner: str,
        lease_seconds: float,
        now: str | None = None,
    ) -> JsonDict:
        timestamp = _timestamp(now)
        duration = _positive_number(lease_seconds, "lease_seconds")
        owner = _required_private_value(lease_owner, "lease_owner")
        with self._lock:
            entry = self._entry(entry_id)
            self._expire_if_stale(entry, timestamp)
            if entry["state"] not in {"reserved", "retry_wait"}:
                raise ProviderJournalStateError(f"cannot claim request from {entry['state']}")
            if entry["state"] == "retry_wait" and _parse_time(timestamp) < _parse_time(entry["retry_not_before"]):
                raise ProviderJournalStateError("retry_wait request is not eligible yet")
            entry["attempt_count"] += 1
            entry["fencing_token"] += 1
            entry["lease_owner_fingerprint"] = self._fingerprint({"lease_owner": owner})
            entry["lease_expires_at"] = _format_time(_parse_time(timestamp) + timedelta(seconds=duration))
            entry["retry_not_before"] = None
            return self._transition_locked(entry, "in_flight", timestamp, clear_lease=False)

    def observe_stream(
        self,
        entry_id: str,
        *,
        lease_owner: str,
        fencing_token: int,
        now: str | None = None,
    ) -> JsonDict:
        timestamp = _timestamp(now)
        with self._lock:
            entry = self._entry(entry_id)
            self._assert_claim(entry, lease_owner, fencing_token, timestamp)
            entry["stream_observed"] = True
            entry["updated_at"] = timestamp
            self._persist()
            return _clone(entry)

    def record_stream_snapshot(
        self,
        entry_id: str,
        snapshot: Mapping[str, Any],
        *,
        lease_owner: str,
        fencing_token: int,
        now: str | None = None,
    ) -> JsonDict:
        """Persist a content-free ProviderStreamLedger snapshot under the active fence."""
        from .provider_stream import ProviderStreamLedger

        timestamp = _timestamp(now)
        if not isinstance(snapshot, Mapping):
            raise TypeError("stream snapshot must be a mapping")
        with self._lock:
            entry = self._entry(entry_id)
            self._assert_claim(entry, lease_owner, fencing_token, timestamp)
            validated = ProviderStreamLedger(
                snapshot, entry_id=entry_id, fencing_token=fencing_token
            ).snapshot()
            if validated["frame_count"] <= 0:
                raise ValueError("stream snapshot must contain at least one frame")
            current = entry.get("stream_snapshot")
            if current is not None:
                if validated["frame_count"] < current["frame_count"]:
                    raise ProviderJournalStateError("stream snapshot cannot move backwards")
                if (
                    validated["frame_count"] == current["frame_count"]
                    and validated["stream_digest"] != current["stream_digest"]
                ):
                    raise ProviderJournalStateError("stream snapshot conflicts at the current fence")
            entry["stream_observed"] = True
            entry["stream_snapshot"] = validated
            entry["updated_at"] = timestamp
            self._persist()
            return _clone(entry)

    def schedule_retry(
        self,
        entry_id: str,
        *,
        lease_owner: str,
        fencing_token: int,
        error_code: str,
        retry_after_seconds: float = 0,
        now: str | None = None,
    ) -> JsonDict:
        timestamp = _timestamp(now)
        delay = _non_negative_number(retry_after_seconds)
        assert delay is not None
        with self._lock:
            entry = self._entry(entry_id)
            self._assert_claim(entry, lease_owner, fencing_token, timestamp)
            if entry["stream_observed"]:
                raise ProviderJournalStateError("stream-observed requests cannot be retried automatically")
            entry["retry_not_before"] = _format_time(_parse_time(timestamp) + timedelta(seconds=delay))
            entry["retry_evidence"].append(
                {
                    "at": timestamp,
                    "attempt": entry["attempt_count"],
                    "fencing_token": entry["fencing_token"],
                    "error_code": _safe_label(error_code, "error_code"),
                    "retry_after_seconds": delay,
                }
            )
            return self._transition_locked(entry, "retry_wait", timestamp)

    def mark_succeeded(
        self,
        entry_id: str,
        *,
        lease_owner: str,
        fencing_token: int,
        usage: Mapping[str, Any] | None = None,
        evidence: Mapping[str, Any] | None = None,
        now: str | None = None,
    ) -> JsonDict:
        return self._finish_claim(
            entry_id, "succeeded", lease_owner, fencing_token, usage, evidence, now
        )

    def mark_failed_terminal(
        self,
        entry_id: str,
        *,
        lease_owner: str,
        fencing_token: int,
        error_code: str,
        usage: Mapping[str, Any] | None = None,
        evidence: Mapping[str, Any] | None = None,
        now: str | None = None,
    ) -> JsonDict:
        safe_evidence = dict(evidence or {})
        safe_evidence.update({"error_code": error_code, "retryable": False})
        return self._finish_claim(
            entry_id, "failed_terminal", lease_owner, fencing_token, usage, safe_evidence, now
        )

    def expire_stale(self, *, now: str | None = None) -> list[JsonDict]:
        timestamp = _timestamp(now)
        expired: list[JsonDict] = []
        with self._lock:
            for entry in self._state["entries"].values():
                if self._expire_if_stale(entry, timestamp):
                    expired.append(_clone(entry))
            return expired

    def reconcile(
        self,
        entry_id: str,
        *,
        outcome: str,
        reason: str,
        usage: Mapping[str, Any] | None = None,
        evidence: Mapping[str, Any] | None = None,
        now: str | None = None,
    ) -> JsonDict:
        if outcome not in {"succeeded", "failed_terminal", "reserved"}:
            raise ValueError("reconciliation outcome must be succeeded, failed_terminal, or reserved")
        timestamp = _timestamp(now)
        with self._lock:
            entry = self._entry(entry_id)
            self._expire_if_stale(entry, timestamp)
            if entry["state"] != "indeterminate":
                raise ProviderJournalStateError("only indeterminate requests may be reconciled")
            if outcome == "reserved" and entry["stream_observed"]:
                raise ProviderJournalStateError(
                    "partial-stream requests cannot be reconciled to reserved"
                )
            entry["reconciliation_evidence"].append(
                {
                    "at": timestamp,
                    "outcome": outcome,
                    "reason": _safe_label(reason, "reason"),
                    "prior_fencing_token": entry["fencing_token"],
                }
            )
            if outcome in TERMINAL_STATES:
                entry["usage_evidence"] = _normalize_usage(usage or {})
                entry["response_evidence"] = _safe_evidence(evidence or {})
            return self._transition_locked(entry, outcome, timestamp)

    def get(self, entry_id: str, *, now: str | None = None) -> JsonDict:
        timestamp = _timestamp(now)
        with self._lock:
            entry = self._entry(entry_id)
            self._expire_if_stale(entry, timestamp)
            return _clone(entry)

    def snapshot(self, *, now: str | None = None) -> JsonDict:
        self.expire_stale(now=now)
        with self._lock:
            return _clone(
                {
                    "schema_version": PROVIDER_JOURNAL_SCHEMA_VERSION,
                    "entries": list(self._state["entries"].values()),
                    "entry_count": len(self._state["entries"]),
                    "metadata": {
                        "persistence_capabilities": _clone(PERSISTENCE_CAPABILITIES),
                        "raw_request_persisted": False,
                        "raw_response_persisted": False,
                        "credentials_persisted": False,
                    },
                }
            )

    def _finish_claim(
        self,
        entry_id: str,
        state: str,
        lease_owner: str,
        fencing_token: int,
        usage: Mapping[str, Any] | None,
        evidence: Mapping[str, Any] | None,
        now: str | None,
    ) -> JsonDict:
        timestamp = _timestamp(now)
        with self._lock:
            entry = self._entry(entry_id)
            self._assert_claim(entry, lease_owner, fencing_token, timestamp)
            if state == "succeeded" and entry["stream_observed"]:
                stream_snapshot = entry.get("stream_snapshot")
                if (
                    not isinstance(stream_snapshot, Mapping)
                    or stream_snapshot.get("entry_id") != entry_id
                    or stream_snapshot.get("fencing_token") != fencing_token
                    or stream_snapshot.get("terminal_observed") is not True
                ):
                    raise ProviderJournalStateError(
                        "streamed success requires a terminal snapshot under the active fence"
                    )
            entry["usage_evidence"] = _normalize_usage(usage or {})
            entry["response_evidence"] = _safe_evidence(evidence or {})
            return self._transition_locked(entry, state, timestamp)

    def _assert_claim(
        self, entry: JsonDict, lease_owner: str, fencing_token: int, timestamp: str
    ) -> None:
        owner = _required_private_value(lease_owner, "lease_owner")
        if not isinstance(fencing_token, int) or isinstance(fencing_token, bool) or fencing_token <= 0:
            raise ValueError("fencing_token must be a positive integer")
        self._expire_if_stale(entry, timestamp)
        if entry["state"] != "in_flight":
            raise ProviderJournalStateError(f"request is not in_flight; current state is {entry['state']}")
        if fencing_token != entry["fencing_token"]:
            raise ProviderJournalStateError("stale fencing token")
        expected = self._fingerprint({"lease_owner": owner})
        if not hmac.compare_digest(entry["lease_owner_fingerprint"], expected):
            raise ProviderJournalStateError("lease owner does not hold this claim")

    def _expire_if_stale(self, entry: JsonDict, timestamp: str) -> bool:
        if entry["state"] != "in_flight":
            return False
        expires_at = entry.get("lease_expires_at")
        if not isinstance(expires_at, str):
            raise ProviderJournalError("in_flight entry has an invalid lease")
        if _parse_time(timestamp) < _parse_time(expires_at):
            return False
        entry["indeterminate_evidence"] = {
            "at": timestamp,
            "reason": "lease_expired",
            "fencing_token": entry["fencing_token"],
            "stream_observed": entry["stream_observed"],
        }
        self._transition_locked(entry, "indeterminate", timestamp)
        return True

    def _transition_locked(
        self, entry: JsonDict, state: str, timestamp: str, *, clear_lease: bool = True
    ) -> JsonDict:
        if state not in PROVIDER_JOURNAL_STATES:
            raise ProviderJournalStateError(f"unknown journal state: {state}")
        entry["state"] = state
        entry["updated_at"] = timestamp
        entry["state_history"].append({"state": state, "at": timestamp})
        if clear_lease:
            entry["lease_owner_fingerprint"] = None
            entry["lease_expires_at"] = None
        self._persist()
        return _clone(entry)

    def _entry(self, entry_id: str) -> JsonDict:
        try:
            return self._state["entries"][entry_id]
        except KeyError as exc:
            raise KeyError(f"unknown provider journal entry: {entry_id}") from exc

    def _fingerprint(self, value: Any) -> str:
        payload = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_json_default
        )
        return hmac.new(
            bytes.fromhex(self._state["salt"]), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _load_or_create(self) -> tuple[JsonDict, bool]:
        if self.path.exists():
            try:
                state = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProviderJournalError("provider journal is not valid JSON") from exc
            self._validate_persisted_state(state)
            return state, True
        state = {
            "schema_version": PROVIDER_JOURNAL_SCHEMA_VERSION,
            "salt": secrets.token_hex(32),
            "entries": {},
            "lookup": {},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state = state
        self._persist()
        return state, False

    def _recover_after_restart(self) -> None:
        timestamp = _utc_now()
        changed = False
        for entry in self._state["entries"].values():
            if entry["state"] != "in_flight":
                continue
            entry["indeterminate_evidence"] = {
                "at": timestamp,
                "reason": "process_restart",
                "fencing_token": entry["fencing_token"],
                "stream_observed": entry["stream_observed"],
            }
            entry["state"] = "indeterminate"
            entry["updated_at"] = timestamp
            entry["state_history"].append({"state": "indeterminate", "at": timestamp})
            entry["lease_owner_fingerprint"] = None
            entry["lease_expires_at"] = None
            changed = True
        if changed:
            self._persist()

    @staticmethod
    def _validate_persisted_state(state: Any) -> None:
        if not isinstance(state, dict):
            raise ProviderJournalError("invalid provider journal state")
        if state.get("schema_version") != PROVIDER_JOURNAL_SCHEMA_VERSION:
            raise ProviderJournalError("unsupported provider journal schema")
        salt = state.get("salt")
        entries = state.get("entries")
        lookup = state.get("lookup")
        if (
            not isinstance(salt, str)
            or len(salt) != 64
            or not re.fullmatch(r"[0-9a-f]{64}", salt)
            or not isinstance(entries, dict)
            or not isinstance(lookup, dict)
        ):
            raise ProviderJournalError("invalid provider journal state")
        required = {
            "schema_version", "entry_id", "scope_fingerprint", "idempotency_fingerprint",
            "request_fingerprint", "identity_evidence", "request_evidence", "state",
            "attempt_count", "fencing_token", "lease_owner_fingerprint", "lease_expires_at",
            "retry_not_before", "stream_observed", "stream_snapshot", "created_at", "updated_at",
            "state_history", "retry_evidence", "reconciliation_evidence", "usage_evidence",
            "response_evidence", "raw_request_persisted", "raw_response_persisted",
            "credentials_persisted",
        }
        for entry_id, entry in entries.items():
            if not isinstance(entry_id, str) or not isinstance(entry, dict) or not required.issubset(entry):
                raise ProviderJournalError("provider journal entry is malformed")
            if entry["entry_id"] != entry_id or entry["schema_version"] != PROVIDER_JOURNAL_SCHEMA_VERSION:
                raise ProviderJournalError("provider journal entry identity is invalid")
            if entry["state"] not in PROVIDER_JOURNAL_STATES:
                raise ProviderJournalError("provider journal entry state is invalid")
            if (
                not isinstance(entry["attempt_count"], int)
                or isinstance(entry["attempt_count"], bool)
                or entry["attempt_count"] < 0
                or not isinstance(entry["fencing_token"], int)
                or isinstance(entry["fencing_token"], bool)
                or entry["fencing_token"] < entry["attempt_count"]
                or not isinstance(entry["stream_observed"], bool)
                or not isinstance(entry["state_history"], list)
                or not entry["state_history"]
            ):
                raise ProviderJournalError("provider journal counters are invalid")
            for fingerprint_field in (
                "scope_fingerprint", "idempotency_fingerprint", "request_fingerprint"
            ):
                if not _is_digest(entry[fingerprint_field]):
                    raise ProviderJournalError("provider journal fingerprint is invalid")
            if entry["state"] == "in_flight":
                if not _is_digest(entry["lease_owner_fingerprint"]) or not isinstance(
                    entry["lease_expires_at"], str
                ):
                    raise ProviderJournalError("in_flight entry has an invalid lease")
                _parse_time(entry["lease_expires_at"])
            elif entry["lease_owner_fingerprint"] is not None or entry["lease_expires_at"] is not None:
                raise ProviderJournalError("non-in_flight entry cannot retain a lease")
            if entry["retry_not_before"] is not None:
                _parse_time(entry["retry_not_before"])
            _parse_time(entry["created_at"])
            _parse_time(entry["updated_at"])
            if entry["stream_snapshot"] is not None:
                from .provider_stream import ProviderStreamIntegrityError, ProviderStreamLedger
                try:
                    stream = ProviderStreamLedger(
                        entry["stream_snapshot"],
                        entry_id=entry_id,
                        fencing_token=entry["fencing_token"],
                    ).snapshot()
                except ProviderStreamIntegrityError as exc:
                    raise ProviderJournalError("provider stream snapshot is invalid") from exc
                if stream["frame_count"] <= 0 or not entry["stream_observed"]:
                    raise ProviderJournalError("provider stream snapshot evidence is inconsistent")
            if any(
                entry[field] is not False
                for field in ("raw_request_persisted", "raw_response_persisted", "credentials_persisted")
            ):
                raise ProviderJournalError("provider journal privacy flags are invalid")
        for lookup_key, entry_id in lookup.items():
            if not isinstance(lookup_key, str) or entry_id not in entries:
                raise ProviderJournalError("provider journal lookup is invalid")

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temporary.write_text(
            json.dumps(self._state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, self.path)

    @staticmethod
    def _validate_identity(identity: ProviderRequestIdentity) -> None:
        for field in ("tenant_id", "project_id", "provider", "model"):
            value = getattr(identity, field)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} must be a non-empty string")
        operation = identity.endpoint_operation
        if not isinstance(operation, str) or not _ENDPOINT_OPERATION.fullmatch(operation):
            raise ValueError("endpoint_operation must be a controlled operation label")


def _request_evidence(request: Mapping[str, Any]) -> JsonDict:
    counts = {modality: 0 for modality in PROVIDER_MODALITIES}
    parts = request.get("parts", request.get("input", []))
    if isinstance(parts, str):
        counts["text"] = 1
    elif isinstance(parts, Sequence) and not isinstance(parts, (str, bytes, bytearray)):
        for part in parts:
            if isinstance(part, str):
                counts["text"] += 1
            elif isinstance(part, Mapping):
                modality = str(part.get("type", "text")).lower()
                if modality in counts:
                    counts[modality] += 1
    if isinstance(request.get("prompt"), str) or isinstance(request.get("text"), str):
        counts["text"] += 1
    return {
        "modality_counts": counts,
        "modalities_present": [name for name in PROVIDER_MODALITIES if counts[name] > 0],
        "stream": bool(request.get("stream", False)),
        "tool_count": len(request.get("tools", []))
        if isinstance(request.get("tools"), Sequence)
        else 0,
        "raw_prompt_persisted": False,
        "raw_media_persisted": False,
        "raw_url_persisted": False,
        "raw_credential_persisted": False,
    }


def _normalize_usage(usage: Mapping[str, Any]) -> JsonDict:
    input_tokens = _non_negative_int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
    output_tokens = _non_negative_int(
        usage.get("output_tokens", usage.get("completion_tokens", 0))
    )
    total = _non_negative_int(usage.get("total_tokens", input_tokens + output_tokens))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total,
        "image_units": _non_negative_int(usage.get("image_units", usage.get("images", 0))),
        "audio_seconds": _non_negative_number(usage.get("audio_seconds", 0)),
        "file_bytes": _non_negative_int(usage.get("file_bytes", 0)),
        "video_seconds": _non_negative_number(usage.get("video_seconds", 0)),
    }


def _safe_evidence(evidence: Mapping[str, Any]) -> JsonDict:
    result: JsonDict = {}
    for key in sorted(_SAFE_EVIDENCE_FIELDS):
        if key not in evidence:
            continue
        value = evidence[key]
        if key == "status_code":
            result[key] = _non_negative_int(value)
        elif key == "retryable":
            result[key] = bool(value)
        else:
            result[key] = _safe_label(value, key)
    return result


def _safe_label(value: Any, field: str) -> str:
    text = str(value)
    lowered = text.lower()
    if (
        not text
        or len(text) > 256
        or any(
            token in lowered
            for token in ("http://", "https://", "bearer ", "api_key", "secret", "token=")
        )
    ):
        raise ValueError(f"{field} is not safe journal evidence")
    return text


def _required_private_value(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _positive_number(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive finite number") from exc
    if parsed <= 0 or parsed == float("inf") or parsed != parsed:
        raise ValueError(f"{field} must be a positive finite number")
    return parsed


def _non_negative_int(value: Any) -> int:
    parsed = int(value or 0)
    if parsed < 0:
        raise ValueError("usage values must be non-negative")
    return parsed


def _non_negative_number(value: Any) -> float | int | None:
    if value is None:
        return None
    parsed = float(value)
    if parsed < 0 or parsed == float("inf") or parsed != parsed:
        raise ValueError("usage values must be non-negative and finite")
    return int(parsed) if parsed.is_integer() else parsed


def _timestamp(value: str | None) -> str:
    return _format_time(_parse_time(value or _utc_now()))


def _parse_time(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be a valid ISO-8601 value") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    return repr(value)


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
