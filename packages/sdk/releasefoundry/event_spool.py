"""Durable, cross-language SDK event envelope and offline delivery spool.

The spool deliberately keeps delivery state separate from the trace-ingestion
service.  A network retry therefore reuses the exact same ``idempotency_key``
and payload digest, while a process restart can recover a lease without
recreating an event or re-counting quota.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JsonValue = Any
JsonDict = dict[str, JsonValue]

EVENT_ENVELOPE_SCHEMA_VERSION = "releasefoundry.event.v1"
EVENT_SPOOL_BATCH_SCHEMA_VERSION = "releasefoundry.event_spool_batch.v1"
EVENT_SPOOL_CONTRACT_VERSION = "releasefoundry.event_spool.v1"
NON_DROPPABLE_PURPOSES = frozenset({"audit", "billing", "evidence", "security"})
_SECRET_KEY_RE = re.compile(
    r"(?:^|[_-])(api[_-]?key|bearer|authorization|password|secret|token|"
    r"oauth[_-]?(?:code|state|token)|smtp|otp|private[_-]?key)(?:$|[_-])",
    re.IGNORECASE,
)


class EventSpoolError(RuntimeError):
    """Base error for local event-envelope and spool failures."""


class EventValidationError(EventSpoolError, ValueError):
    """Raised when an event or batch violates the stable contract."""


class EventBackpressureError(EventSpoolError):
    """Raised when bounded local storage refuses a new batch."""


class RetryableDeliveryError(EventSpoolError):
    """A sender may raise this to keep a leased batch pending for retry."""


class PermanentDeliveryError(EventSpoolError):
    """A sender may raise this to move a batch to the dead-letter queue."""


@dataclass(frozen=True)
class EventFlushReport:
    attempted: int
    delivered: int
    retried: int
    dead_lettered: int
    remaining: int

    def to_dict(self) -> JsonDict:
        return {
            "attempted": self.attempted,
            "delivered": self.delivered,
            "retried": self.retried,
            "dead_lettered": self.dead_lettered,
            "remaining": self.remaining,
        }


def canonical_json(value: JsonValue) -> str:
    """Return the shared compact JSON representation used for digests."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_json(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _required_text(value: JsonValue, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(f"{field} must be a non-empty string")
    return value


def _utc_now(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    text = _required_text(value, "timestamp").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EventValidationError("timestamp must be ISO-8601") from exc
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _iso(value: datetime | str | None = None) -> str:
    return _utc_now(value).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_error(error: BaseException) -> str:
    message = f"{type(error).__name__}: {error}".strip()
    message = _SECRET_KEY_RE.sub("<redacted>", message)
    message = re.sub(
        r"(?i)(api[_-]?key|authorization|bearer|token|secret|password|otp|code|state)\s*[=:]\s*\S+",
        r"\1=<redacted>",
        message,
    )
    return message[:240]


def _validate_public_metadata(metadata: Mapping[str, JsonValue]) -> None:
    for key, value in metadata.items():
        if _SECRET_KEY_RE.search(str(key)):
            raise EventValidationError(f"secret-bearing metadata key is not allowed: {key}")
        if isinstance(value, Mapping):
            _validate_public_metadata(value)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                if isinstance(item, Mapping):
                    _validate_public_metadata(item)


def _event_without_integrity(event: Mapping[str, JsonValue]) -> JsonDict:
    return {key: value for key, value in event.items() if key != "integrity_sha256"}


def build_event_envelope(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    source: str,
    event_type: str,
    payload: JsonValue,
    sequence: int = 0,
    occurred_at: datetime | str | None = None,
    purpose: str = "telemetry",
    data_class: str = "operational",
    consent: str = "product_use_not_training",
    residency: str = "customer_region",
    retention_class: str = "standard",
    learning_allowed: bool = False,
    causal_parent: str | None = None,
    event_id: str | None = None,
    metadata: Mapping[str, JsonValue] | None = None,
) -> JsonDict:
    """Build and integrity-seal one stable event envelope.

    ``metadata`` is intentionally constrained to public routing labels.  Raw
    credentials and delivery material are not accepted in the envelope's
    public metadata namespace.
    """

    if not isinstance(sequence, int) or sequence < 0:
        raise EventValidationError("sequence must be a non-negative integer")
    if not isinstance(learning_allowed, bool):
        raise EventValidationError("learning_allowed must be boolean")
    event = {
        "schema_version": EVENT_ENVELOPE_SCHEMA_VERSION,
        "event_id": _required_text(event_id or f"evt_{uuid.uuid4().hex}", "event_id"),
        "tenant_id": _required_text(tenant_id, "tenant_id"),
        "project_id": _required_text(project_id, "project_id"),
        "run_id": _required_text(run_id, "run_id"),
        "source": _required_text(source, "source"),
        "event_type": _required_text(event_type, "event_type"),
        "sequence": sequence,
        "occurred_at": _iso(occurred_at),
        "purpose": _required_text(purpose, "purpose"),
        "data_class": _required_text(data_class, "data_class"),
        "consent": _required_text(consent, "consent"),
        "residency": _required_text(residency, "residency"),
        "retention_class": _required_text(retention_class, "retention_class"),
        "learning_allowed": learning_allowed,
        "payload": payload,
        "causal_parent": causal_parent,
        "metadata": dict(metadata or {}),
    }
    _validate_public_metadata(event["metadata"])
    json.dumps(event, ensure_ascii=False, allow_nan=False)
    event["integrity_sha256"] = sha256_json(_event_without_integrity(event))
    return event


def validate_event_envelope(value: Mapping[str, JsonValue]) -> JsonDict:
    if not isinstance(value, Mapping):
        raise EventValidationError("event must be an object")
    event = dict(value)
    if event.get("schema_version") != EVENT_ENVELOPE_SCHEMA_VERSION:
        raise EventValidationError("unsupported event schema_version")
    for field in (
        "event_id",
        "tenant_id",
        "project_id",
        "run_id",
        "source",
        "event_type",
        "occurred_at",
        "purpose",
        "data_class",
        "consent",
        "residency",
        "retention_class",
    ):
        _required_text(event.get(field), field)
    if not isinstance(event.get("sequence"), int) or event["sequence"] < 0:
        raise EventValidationError("sequence must be a non-negative integer")
    if not isinstance(event.get("learning_allowed"), bool):
        raise EventValidationError("learning_allowed must be boolean")
    if "payload" not in event:
        raise EventValidationError("payload is required")
    _validate_public_metadata(event.get("metadata") if isinstance(event.get("metadata"), Mapping) else {})
    expected = sha256_json(_event_without_integrity(event))
    if event.get("integrity_sha256") != expected:
        raise EventValidationError("event integrity_sha256 mismatch")
    return event


def deterministic_sample(event_id: str, rate: float) -> bool:
    """Return the same sampling decision in Python and TypeScript."""

    if not 0.0 <= rate <= 1.0:
        raise EventValidationError("sampling_rate must be between 0 and 1")
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    bucket = int(hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:16], 16)
    return bucket / float(0xFFFFFFFFFFFFFFFF) < rate


def build_trace_ingestion_sender(
    ingest_trace: Callable[..., Mapping[str, JsonValue]],
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    api_key_id: str | None = None,
) -> Callable[[Mapping[str, JsonValue]], Mapping[str, JsonValue]]:
    """Adapt a spool sender to the existing trace-ingestion SDK contract."""

    def send(batch: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
        events = batch.get("events")
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
            raise PermanentDeliveryError("spool batch events are not a list")
        observations: list[Mapping[str, JsonValue]] = []
        for event in events:
            if not isinstance(event, Mapping) or not isinstance(event.get("payload"), Mapping):
                raise PermanentDeliveryError("trace ingestion requires mapping event payloads")
            observations.append(dict(event["payload"]))
        return ingest_trace(
            tenant_id,
            project_id,
            run_id,
            observations,
            batch_id=_required_text(batch.get("batch_id"), "batch_id"),
            api_key_id=api_key_id,
            idempotency_key=_required_text(batch.get("idempotency_key"), "idempotency_key"),
        )

    return send


class DurableEventSpool:
    """A bounded JSON-file spool with leases, resume, retry and dead letters."""

    def __init__(
        self,
        directory: str | Path,
        *,
        max_batches: int = 1_000,
        max_bytes: int = 64 * 1024 * 1024,
        sampling_rate: float = 1.0,
        drop_policy: str = "reject",
        lease_seconds: int = 60,
        max_attempts: int = 8,
        retry_base_seconds: int = 1,
        retry_max_seconds: int = 300,
    ) -> None:
        self.directory = Path(directory)
        self.pending_dir = self.directory / "pending"
        self.dead_dir = self.directory / "dead-letter"
        self.max_batches = int(max_batches)
        self.max_bytes = int(max_bytes)
        self.sampling_rate = float(sampling_rate)
        self.drop_policy = drop_policy
        self.lease_seconds = int(lease_seconds)
        self.max_attempts = int(max_attempts)
        self.retry_base_seconds = int(retry_base_seconds)
        self.retry_max_seconds = int(retry_max_seconds)
        if self.max_batches < 1 or self.max_bytes < 1 or self.lease_seconds < 1 or self.max_attempts < 1:
            raise EventValidationError("spool bounds and lease settings must be positive")
        if self.drop_policy not in {"reject", "drop_oldest"}:
            raise EventValidationError("drop_policy must be reject or drop_oldest")
        deterministic_sample("validation", self.sampling_rate)
        self._lock = threading.RLock()
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.dead_dir.mkdir(parents=True, exist_ok=True)

    def append(self, event: Mapping[str, JsonValue] | JsonDict) -> JsonDict | None:
        result = self.enqueue([event])
        return result

    def enqueue(
        self,
        events: Sequence[Mapping[str, JsonValue]],
        *,
        batch_id: str | None = None,
        idempotency_key: str | None = None,
        now: datetime | str | None = None,
    ) -> JsonDict | None:
        if not events:
            raise EventValidationError("spool enqueue requires at least one event")
        normalized = [validate_event_envelope(event) for event in events]
        sampled: list[JsonDict] = []
        for event in normalized:
            if event["purpose"] in NON_DROPPABLE_PURPOSES or deterministic_sample(str(event["event_id"]), self.sampling_rate):
                sampled.append(event)
        if not sampled:
            return None
        batch = self._new_batch(sampled, batch_id=batch_id, idempotency_key=idempotency_key, now=now)
        encoded = canonical_json(batch).encode("utf-8")
        with self._lock:
            self._recover_expired_leases(_utc_now(now))
            self._make_capacity(len(encoded), now=_utc_now(now), candidate=batch)
            self._atomic_write(self.pending_dir / f"{batch['batch_id']}.json", batch)
        return self.batch_metadata(batch)

    def list_batches(self, *, include_dead_letters: bool = False, now: datetime | str | None = None) -> list[JsonDict]:
        with self._lock:
            self._recover_expired_leases(_utc_now(now))
            paths = list(self.pending_dir.glob("*.json"))
            if include_dead_letters:
                paths.extend(self.dead_dir.glob("*.json"))
            records = [self._read(path) for path in paths]
            return sorted((self.batch_metadata(item) for item in records), key=lambda item: (item["created_at"], item["batch_id"]))

    def batch_metadata(self, batch: Mapping[str, JsonValue]) -> JsonDict:
        events = batch.get("events", [])
        event_rows = [item for item in events if isinstance(item, Mapping)]
        return {
            "schema_version": EVENT_SPOOL_BATCH_SCHEMA_VERSION,
            "batch_id": batch.get("batch_id"),
            "idempotency_key": batch.get("idempotency_key"),
            "payload_sha256": batch.get("payload_sha256"),
            "event_count": len(event_rows),
            "purposes": sorted({str(item.get("purpose")) for item in event_rows}),
            "tenant_ids": sorted({str(item.get("tenant_id")) for item in event_rows}),
            "project_ids": sorted({str(item.get("project_id")) for item in event_rows}),
            "run_ids": sorted({str(item.get("run_id")) for item in event_rows}),
            "status": batch.get("status"),
            "attempts": int(batch.get("attempts", 0)),
            "next_attempt_at": batch.get("next_attempt_at"),
            "lease_expires_at": batch.get("lease_expires_at"),
            "last_failure_code": batch.get("last_failure_code"),
            "created_at": batch.get("created_at"),
            "updated_at": batch.get("updated_at"),
        }

    def storage_metadata(self) -> JsonDict:
        with self._lock:
            pending = list(self.pending_dir.glob("*.json"))
            dead = list(self.dead_dir.glob("*.json"))
            return {
                "schema_version": EVENT_SPOOL_CONTRACT_VERSION,
                "directory": str(self.directory),
                "pending_batches": len(pending),
                "dead_letter_batches": len(dead),
                "stored_bytes": sum(path.stat().st_size for path in [*pending, *dead] if path.exists()),
                "max_batches": self.max_batches,
                "max_bytes": self.max_bytes,
                "sampling_rate": self.sampling_rate,
                "drop_policy": self.drop_policy,
            }

    def flush(
        self,
        sender: Callable[[Mapping[str, JsonValue]], JsonValue],
        *,
        max_batches: int | None = None,
        now: datetime | str | None = None,
        lease_owner: str | None = None,
    ) -> EventFlushReport:
        current = _utc_now(now)
        owner = lease_owner or f"spool_{uuid.uuid4().hex}"
        attempted = delivered = retried = dead_lettered = 0
        with self._lock:
            self._recover_expired_leases(current)
            paths = sorted(self.pending_dir.glob("*.json"))
        for path in paths:
            if max_batches is not None and attempted >= max_batches:
                break
            batch = self._read(path)
            due = batch.get("next_attempt_at")
            if isinstance(due, str) and _utc_now(due) > current:
                continue
            leased = self._lease(path, owner, current)
            if leased is None:
                continue
            attempted += 1
            try:
                result = sender(self._delivery_payload(leased))
                if isinstance(result, Mapping) and result.get("accepted") is False:
                    retryable = bool(result.get("retryable", False))
                    message = str(result.get("error_code") or "delivery_rejected")
                    raise RetryableDeliveryError(message) if retryable else PermanentDeliveryError(message)
            except BaseException as exc:  # sender failures must not lose a leased batch
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                if isinstance(exc, RetryableDeliveryError) and int(leased.get("attempts", 0)) < self.max_attempts:
                    self._retry(path, leased, exc, current)
                    retried += 1
                else:
                    self._dead_letter(path, leased, exc, current)
                    dead_lettered += 1
            else:
                with self._lock:
                    if path.exists():
                        path.unlink()
                delivered += 1
        remaining = len(list(self.pending_dir.glob("*.json")))
        return EventFlushReport(attempted, delivered, retried, dead_lettered, remaining)

    def redrive(self, batch_id: str, *, now: datetime | str | None = None) -> JsonDict:
        _required_text(batch_id, "batch_id")
        source = self.dead_dir / f"{batch_id}.json"
        if not source.exists():
            raise EventSpoolError("dead-letter batch not found")
        batch = self._read(source)
        current = _utc_now(now)
        batch.update(
            {
                "status": "pending",
                "attempts": 0,
                "next_attempt_at": _iso(current),
                "lease_owner": None,
                "lease_expires_at": None,
                "last_failure_code": None,
                "last_failure_message": None,
                "updated_at": _iso(current),
            }
        )
        encoded = canonical_json(batch).encode("utf-8")
        with self._lock:
            self._make_capacity(len(encoded), now=current, candidate=batch)
            self._atomic_write(self.pending_dir / source.name, batch)
            source.unlink()
        return self.batch_metadata(batch)

    def _new_batch(
        self,
        events: Sequence[Mapping[str, JsonValue]],
        *,
        batch_id: str | None,
        idempotency_key: str | None,
        now: datetime | str | None,
    ) -> JsonDict:
        current = _iso(now)
        batch_key = _required_text(batch_id or f"batch_{uuid.uuid4().hex}", "batch_id")
        idem = _required_text(idempotency_key or f"spool_{batch_key}", "idempotency_key")
        payload_sha256 = sha256_json(list(events))
        return {
            "schema_version": EVENT_SPOOL_BATCH_SCHEMA_VERSION,
            "batch_id": batch_key,
            "idempotency_key": idem,
            "payload_sha256": payload_sha256,
            "events": list(events),
            "attempts": 0,
            "next_attempt_at": current,
            "status": "pending",
            "lease_owner": None,
            "lease_expires_at": None,
            "last_failure_code": None,
            "last_failure_message": None,
            "created_at": current,
            "updated_at": current,
        }

    def _delivery_payload(self, batch: Mapping[str, JsonValue]) -> JsonDict:
        return {
            "schema_version": EVENT_SPOOL_BATCH_SCHEMA_VERSION,
            "batch_id": batch["batch_id"],
            "idempotency_key": batch["idempotency_key"],
            "payload_sha256": batch["payload_sha256"],
            "events": batch["events"],
        }

    def _recover_expired_leases(self, now: datetime) -> None:
        for path in self.pending_dir.glob("*.json"):
            batch = self._read(path)
            expiry = batch.get("lease_expires_at")
            if batch.get("status") == "leased" and isinstance(expiry, str) and _utc_now(expiry) <= now:
                batch.update({"status": "pending", "lease_owner": None, "lease_expires_at": None, "updated_at": _iso(now)})
                self._atomic_write(path, batch)

    def _lease(self, path: Path, owner: str, now: datetime) -> JsonDict | None:
        with self._lock:
            if not path.exists():
                return None
            batch = self._read(path)
            if batch.get("status") != "pending":
                return None
            batch.update(
                {
                    "status": "leased",
                    "lease_owner": owner,
                    "lease_expires_at": _iso(now + timedelta(seconds=self.lease_seconds)),
                    "attempts": int(batch.get("attempts", 0)) + 1,
                    "updated_at": _iso(now),
                }
            )
            self._atomic_write(path, batch)
            return batch

    def _retry(self, path: Path, batch: JsonDict, error: BaseException, now: datetime) -> None:
        attempt = int(batch.get("attempts", 1))
        delay = min(self.retry_max_seconds, self.retry_base_seconds * (2 ** max(0, attempt - 1)))
        batch.update(
            {
                "status": "pending",
                "lease_owner": None,
                "lease_expires_at": None,
                "next_attempt_at": _iso(now + timedelta(seconds=delay)),
                "last_failure_code": "retryable_delivery_failure",
                "last_failure_message": _safe_error(error),
                "updated_at": _iso(now),
            }
        )
        self._atomic_write(path, batch)

    def _dead_letter(self, path: Path, batch: JsonDict, error: BaseException, now: datetime) -> None:
        batch.update(
            {
                "status": "dead_letter",
                "lease_owner": None,
                "lease_expires_at": None,
                "last_failure_code": "delivery_failed",
                "last_failure_message": _safe_error(error),
                "dead_lettered_at": _iso(now),
                "updated_at": _iso(now),
            }
        )
        target = self.dead_dir / path.name
        with self._lock:
            self._atomic_write(target, batch)
            if path.exists():
                path.unlink()

    def _make_capacity(self, incoming_bytes: int, *, now: datetime, candidate: Mapping[str, JsonValue]) -> None:
        existing = [*self.pending_dir.glob("*.json"), *self.dead_dir.glob("*.json")]
        count = len(existing)
        total_bytes = sum(path.stat().st_size for path in existing if path.exists())
        if count < self.max_batches and total_bytes + incoming_bytes <= self.max_bytes:
            return
        if self.drop_policy != "drop_oldest" or not self._batch_is_droppable(candidate):
            raise EventBackpressureError("event spool capacity exceeded; write rejected")
        for path in sorted(self.pending_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
            if count < self.max_batches and total_bytes + incoming_bytes <= self.max_bytes:
                break
            batch = self._read(path)
            if not self._batch_is_droppable(batch) or batch.get("status") != "pending":
                continue
            total_bytes -= path.stat().st_size
            count -= 1
            path.unlink()
        if count >= self.max_batches or total_bytes + incoming_bytes > self.max_bytes:
            raise EventBackpressureError("event spool capacity exceeded; non-droppable data blocks drop_oldest")

    @staticmethod
    def _batch_is_droppable(batch: Mapping[str, JsonValue]) -> bool:
        events = batch.get("events", [])
        return bool(events) and all(
            isinstance(event, Mapping) and event.get("purpose") == "telemetry" for event in events
        )

    @staticmethod
    def _read(path: Path) -> JsonDict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EventSpoolError(f"cannot read spool batch {path.name}") from exc
        if not isinstance(value, dict) or value.get("schema_version") != EVENT_SPOOL_BATCH_SCHEMA_VERSION:
            raise EventSpoolError(f"invalid spool batch {path.name}")
        return value

    @staticmethod
    def _atomic_write(path: Path, value: Mapping[str, JsonValue]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
