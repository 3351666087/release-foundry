"""Fail-closed A2 release-decision handoff to the A1 durable event spool."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from .result_persistence import stable_hash


A1_EVENT_SCHEMA_VERSION = "releasefoundry.event.v1"
A1_SPOOL_HANDOFF_SCHEMA_VERSION = "a2.a1_event_spool_handoff.v1"
RELEASE_DECISION_EVENT_TYPE = "a2.release_decision.committed.v1"
RELEASE_DECISION_EVENT_SOURCE = "a2.release_decision_store"
_HASH_REF = re.compile(r"sha256:[0-9a-f]{64}\Z")
_INTEGRITY_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SECRET_KEY = re.compile(
    r"(?:^|[_-])(api[_-]?key|bearer|authorization|password|secret|token|"
    r"oauth[_-]?(?:code|state|token)|smtp|otp|private[_-]?key)(?:$|[_-])",
    re.IGNORECASE,
)
_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "event_id",
        "tenant_id",
        "project_id",
        "run_id",
        "source",
        "event_type",
        "sequence",
        "occurred_at",
        "purpose",
        "data_class",
        "consent",
        "residency",
        "retention_class",
        "learning_allowed",
        "payload",
        "causal_parent",
        "metadata",
        "integrity_sha256",
    }
)
_HANDOFF_FIELDS = frozenset(
    {
        "schema_version",
        "batch_id",
        "idempotency_key",
        "payload_hash",
        "event",
        "public_safe",
    }
)


class A1EventBridgeError(ValueError):
    """Raised when persisted A2 evidence cannot safely enter the A1 spool."""


def build_release_decision_spool_handoff(
    claimed_outbox: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one deterministic A1 event and spool identity from a claimed row."""

    payload = _release_decision_payload(claimed_outbox)
    event_id = _required_text(claimed_outbox.get("event_id"), "event_id")
    event_hex = _hash_ref_hex(event_id, "event_id")
    envelope = {
        "schema_version": A1_EVENT_SCHEMA_VERSION,
        "event_id": event_id,
        "tenant_id": _required_text(claimed_outbox.get("tenant_id"), "tenant_id"),
        "project_id": _required_text(claimed_outbox.get("project_id"), "project_id"),
        "run_id": _required_text(claimed_outbox.get("run_id"), "run_id"),
        "source": RELEASE_DECISION_EVENT_SOURCE,
        "event_type": RELEASE_DECISION_EVENT_TYPE,
        "sequence": 0,
        "occurred_at": _iso_milliseconds(claimed_outbox.get("created_at")),
        "purpose": "evidence",
        "data_class": "operational",
        "consent": "product_use_not_training",
        "residency": "customer_region",
        "retention_class": "standard",
        "learning_allowed": False,
        "payload": payload,
        "causal_parent": _required_text(claimed_outbox.get("operation_id"), "operation_id"),
        "metadata": {
            "organization_id": _required_text(
                claimed_outbox.get("organization_id"), "organization_id"
            ),
            "workspace_id": _required_text(
                claimed_outbox.get("workspace_id"), "workspace_id"
            ),
            "environment_id": _required_text(
                claimed_outbox.get("environment_id"), "environment_id"
            ),
            "case_id": _required_text(claimed_outbox.get("case_id"), "case_id"),
            "scenario_id": _required_text(
                claimed_outbox.get("scenario_id"), "scenario_id"
            ),
        },
    }
    _validate_public_metadata(envelope["metadata"])
    envelope["integrity_sha256"] = _sha256_json(envelope)
    handoff = {
        "schema_version": A1_SPOOL_HANDOFF_SCHEMA_VERSION,
        "batch_id": f"a2_release_{event_hex[:32]}",
        "idempotency_key": f"a2_release_{event_hex}",
        "payload_hash": _required_hash(claimed_outbox.get("payload_hash"), "payload_hash"),
        "event": envelope,
        "public_safe": True,
    }
    return verify_release_decision_spool_handoff(
        handoff,
        expected_outbox=claimed_outbox,
    )


def verify_release_decision_spool_handoff(
    value: Mapping[str, Any],
    *,
    expected_outbox: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify the bridge and exact A1 envelope contract without trusting callers."""

    if not isinstance(value, Mapping):
        raise A1EventBridgeError("A1 spool handoff must be an object")
    handoff = dict(value)
    if frozenset(handoff) != _HANDOFF_FIELDS:
        raise A1EventBridgeError("A1 spool handoff fields are not canonical")
    if handoff.get("schema_version") != A1_SPOOL_HANDOFF_SCHEMA_VERSION:
        raise A1EventBridgeError("unsupported A1 spool handoff schema_version")
    if handoff.get("public_safe") is not True:
        raise A1EventBridgeError("A1 spool handoff must be public-safe")
    _required_hash(handoff.get("payload_hash"), "payload_hash")

    raw_event = handoff.get("event")
    if not isinstance(raw_event, Mapping):
        raise A1EventBridgeError("A1 event must be an object")
    event = dict(raw_event)
    if frozenset(event) != _ENVELOPE_FIELDS:
        raise A1EventBridgeError("A1 event fields are not canonical")
    if event.get("schema_version") != A1_EVENT_SCHEMA_VERSION:
        raise A1EventBridgeError("unsupported A1 event schema_version")
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
    if event.get("source") != RELEASE_DECISION_EVENT_SOURCE:
        raise A1EventBridgeError("A1 event source mismatch")
    if event.get("event_type") != RELEASE_DECISION_EVENT_TYPE:
        raise A1EventBridgeError("A1 event type mismatch")
    if event.get("sequence") != 0:
        raise A1EventBridgeError("release-decision event sequence must be zero")
    if event.get("purpose") != "evidence":
        raise A1EventBridgeError("release-decision event purpose must be evidence")
    if event.get("consent") != "product_use_not_training":
        raise A1EventBridgeError("release-decision event consent mismatch")
    if event.get("learning_allowed") is not False:
        raise A1EventBridgeError("release-decision evidence cannot allow learning")
    if not isinstance(event.get("metadata"), Mapping):
        raise A1EventBridgeError("A1 event metadata must be an object")
    _validate_public_metadata(event["metadata"])
    if not isinstance(event.get("payload"), Mapping):
        raise A1EventBridgeError("A1 release-decision payload must be an object")
    integrity = event.get("integrity_sha256")
    if not isinstance(integrity, str) or not _INTEGRITY_HASH.fullmatch(integrity):
        raise A1EventBridgeError("A1 event integrity_sha256 is invalid")
    expected_integrity = _sha256_json(
        {key: item for key, item in event.items() if key != "integrity_sha256"}
    )
    if integrity != expected_integrity:
        raise A1EventBridgeError("A1 event integrity_sha256 mismatch")

    event_hex = _hash_ref_hex(event["event_id"], "event_id")
    if handoff.get("batch_id") != f"a2_release_{event_hex[:32]}":
        raise A1EventBridgeError("A1 spool batch identity mismatch")
    if handoff.get("idempotency_key") != f"a2_release_{event_hex}":
        raise A1EventBridgeError("A1 spool idempotency identity mismatch")

    if expected_outbox is not None:
        expected_payload = _release_decision_payload(expected_outbox)
        if event["payload"] != expected_payload:
            raise A1EventBridgeError("A1 event payload does not match persisted decision")
        if handoff["payload_hash"] != expected_outbox.get("payload_hash"):
            raise A1EventBridgeError("A1 handoff payload hash mismatch")
        expected_fields = {
            "event_id": expected_outbox.get("event_id"),
            "tenant_id": expected_outbox.get("tenant_id"),
            "project_id": expected_outbox.get("project_id"),
            "run_id": expected_outbox.get("run_id"),
            "event_type": expected_outbox.get("event_type"),
            "causal_parent": expected_outbox.get("operation_id"),
            "occurred_at": _iso_milliseconds(expected_outbox.get("created_at")),
        }
        for field, expected in expected_fields.items():
            if event.get(field) != expected:
                raise A1EventBridgeError(f"A1 event {field} mismatch")
        expected_metadata = {
            "organization_id": expected_outbox.get("organization_id"),
            "workspace_id": expected_outbox.get("workspace_id"),
            "environment_id": expected_outbox.get("environment_id"),
            "case_id": expected_outbox.get("case_id"),
            "scenario_id": expected_outbox.get("scenario_id"),
        }
        if event["metadata"] != expected_metadata:
            raise A1EventBridgeError("A1 event metadata scope mismatch")
    return handoff


def _release_decision_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    if row.get("schema_version") != A1_EVENT_SCHEMA_VERSION:
        raise A1EventBridgeError("outbox target schema is not the A1 event contract")
    if row.get("event_type") != RELEASE_DECISION_EVENT_TYPE:
        raise A1EventBridgeError("outbox event type mismatch")
    if int(row.get("public_safe") or 0) != 1:
        raise A1EventBridgeError("outbox row is not public-safe")

    scope = {
        field: _required_text(row.get(field), field)
        for field in (
            "organization_id",
            "tenant_id",
            "workspace_id",
            "project_id",
            "environment_id",
        )
    }
    for field in scope:
        joined = _required_text(row.get(f"decision_{field}"), f"decision_{field}")
        if joined != scope[field]:
            raise A1EventBridgeError(f"outbox {field} scope mismatch")

    record_hash = _required_hash(row.get("decision_record_hash"), "decision_record_hash")
    ledger_hash = _required_hash(row.get("decision_ledger_hash"), "decision_ledger_hash")
    provider_outcome_hash = _required_hash(
        row.get("operation_provider_outcome_hash"),
        "operation_provider_outcome_hash",
    )
    if row.get("record_hash") != record_hash:
        raise A1EventBridgeError("outbox record hash mismatch")
    if row.get("ledger_hash") != ledger_hash:
        raise A1EventBridgeError("outbox ledger hash mismatch")
    if row.get("provider_outcome_hash") != provider_outcome_hash:
        raise A1EventBridgeError("outbox provider outcome hash mismatch")

    decision = _required_text(row.get("decision"), "decision")
    if decision not in {"allow", "review", "block"}:
        raise A1EventBridgeError("outbox release decision is invalid")
    review_value = row.get("review_required")
    if review_value not in {0, 1, False, True}:
        raise A1EventBridgeError("outbox review_required is invalid")
    review_required = bool(review_value)
    payload = {
        **scope,
        "operation_id": _required_text(row.get("operation_id"), "operation_id"),
        "record_id": _required_text(row.get("record_id"), "record_id"),
        "record_hash": record_hash,
        "ledger_id": _required_text(row.get("ledger_id"), "ledger_id"),
        "ledger_hash": ledger_hash,
        "provider_outcome_hash": provider_outcome_hash,
        "decision": decision,
        "review_required": review_required,
        "release_ready": decision == "allow",
    }
    persisted_payload_hash = _required_hash(row.get("payload_hash"), "payload_hash")
    if stable_hash(payload) != persisted_payload_hash:
        raise A1EventBridgeError("outbox payload hash mismatch")
    return payload


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise A1EventBridgeError(f"{field} must be a non-empty string")
    return value


def _required_hash(value: Any, field: str) -> str:
    text = _required_text(value, field)
    if not _HASH_REF.fullmatch(text):
        raise A1EventBridgeError(f"{field} must be a sha256 reference")
    return text


def _hash_ref_hex(value: Any, field: str) -> str:
    return _required_hash(value, field).split(":", 1)[1]


def _validate_public_metadata(metadata: Mapping[str, Any]) -> None:
    for key, value in metadata.items():
        if _SECRET_KEY.search(str(key)):
            raise A1EventBridgeError(
                f"secret-bearing metadata key is not allowed: {key}"
            )
        if isinstance(value, Mapping):
            _validate_public_metadata(value)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for item in value:
                if isinstance(item, Mapping):
                    _validate_public_metadata(item)


def _iso_milliseconds(value: Any) -> str:
    text = _required_text(value, "occurred_at").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise A1EventBridgeError("occurred_at must be ISO-8601") from exc
    normalized = parsed.replace(
        tzinfo=parsed.tzinfo or timezone.utc
    ).astimezone(timezone.utc)
    return normalized.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise A1EventBridgeError("A1 event is not canonical JSON") from exc


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
