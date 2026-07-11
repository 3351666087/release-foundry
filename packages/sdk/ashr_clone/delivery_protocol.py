from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Callable, Mapping
from urllib.parse import quote


IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION = "ashr.clone.identity_delivery_protocol.v1"
IDENTITY_DELIVERY_STATUSES = (
    "pending",
    "leased",
    "retry",
    "provider_accepted",
    "delivered",
    "ambiguous",
    "dead",
)
IDENTITY_DELIVERY_ACCEPTANCE_STATUSES = ("provider_accepted", "ambiguous")
IDENTITY_DELIVERY_DTO_KINDS = (
    "task",
    "acceptance",
    "redrive_request",
    "redrive_receipt",
)
IDENTITY_DELIVERY_ERROR_CODES = (
    "identity_delivery_invalid_request",
    "identity_delivery_secret_forbidden",
    "identity_delivery_unknown_field",
    "identity_delivery_status_conflict",
    "identity_delivery_scope_mismatch",
    "identity_delivery_not_found",
    "identity_delivery_lease_conflict",
    "identity_delivery_idempotency_conflict",
    "identity_delivery_not_redrivable",
    "identity_delivery_ambiguous",
    "identity_delivery_store_failed",
)
IDENTITY_DELIVERY_FAILURE_CODES = (
    "malformed_task",
    "malformed_payload",
    "challenge_expired",
    "attempts_exhausted",
    "vault_unavailable",
    "vault_timeout",
    "smtp_delivery_failed",
    "sms_delivery_failed",
    "provider_timeout",
    "provider_rejected",
    "provider_result_ambiguous",
    "lease_expired",
    "lease_lost",
)
IDENTITY_DELIVERY_ADMIN_ROUTES: tuple[dict[str, str], ...] = (
    {
        "operation": "identity_delivery_admin_list",
        "method": "GET",
        "path": "/v1/projects/{project_id}/admin/identity-deliveries",
    },
    {
        "operation": "identity_delivery_admin_get",
        "method": "GET",
        "path": "/v1/projects/{project_id}/admin/identity-deliveries/{task_id}",
    },
    {
        "operation": "identity_delivery_admin_acceptances",
        "method": "GET",
        "path": "/v1/projects/{project_id}/admin/identity-deliveries/{task_id}/acceptances",
    },
    {
        "operation": "identity_delivery_admin_redrive",
        "method": "POST",
        "path": "/v1/projects/{project_id}/admin/identity-deliveries/{task_id}/redrive",
    },
    {
        "operation": "identity_delivery_admin_redrive_audit",
        "method": "GET",
        "path": "/v1/projects/{project_id}/admin/identity-deliveries/{task_id}/redrives",
    },
)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,255}$")
_REASON_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{3}Z$"
)
_PRIVATE_REFERENCE_PATTERN = re.compile(
    r"(?:^|\s)(?:vault|env|kms|secret|provider-ref|opaque-ref):",
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+\b",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(r"(?<![A-Za-z0-9])\+[1-9][0-9]{7,14}(?![0-9])")
_TOKEN_PATTERNS = (
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
    re.compile(
        r"\b(?:access_token|refresh_token|client_secret|password|authorization)\s*[:=]",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk-|tp_|ghp_|ashr_live_)[A-Za-z0-9_-]{6,}", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b"),
)
_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "authorization",
        "code",
        "destination",
        "destinationdigest",
        "email",
        "otp",
        "opaqueref",
        "password",
        "phone",
        "privateevidencepath",
        "privateref",
        "provideracceptanceid",
        "provideracceptanceref",
        "secret",
        "secretref",
        "token",
        "vaultref",
        "verificationcode",
    }
)
_FORBIDDEN_PUBLIC_SUFFIXES = (
    "accesstoken",
    "destination",
    "opaqueref",
    "privateref",
    "provideracceptanceref",
    "refreshtoken",
    "secret",
    "sessiontoken",
    "vaultref",
)
_MAX_CANONICAL_JSON_BYTES = 64 * 1024


class IdentityDeliveryProtocolError(ValueError):
    """Stable public-safe delivery protocol validation failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "identity_delivery_invalid_request",
    ) -> None:
        if code not in IDENTITY_DELIVERY_ERROR_CODES:
            raise ValueError("unknown identity delivery protocol error code")
        self.code = code
        self.message = _public_error_message(message)
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class IdentityDeliveryTaskDTO:
    schema_version: str
    task_id: str
    tenant_id: str
    project_id: str
    challenge_id: str
    channel: str
    purpose: str
    status: str
    attempt: int
    max_attempts: int
    lease_generation: int
    redrive_count: int
    provider_idempotency_key: str
    challenge_expires_at: str
    lease_expires_at: str | None
    next_attempt_at: str | None
    provider_acceptance_present: bool
    accepted_at: str | None
    completed_at: str | None
    dead_at: str | None
    last_failure_code: str | None

    def __post_init__(self) -> None:
        _literal("schema_version", self.schema_version, IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION)
        for name in ("task_id", "tenant_id", "project_id", "challenge_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        object.__setattr__(self, "channel", _enum("channel", self.channel, ("email", "phone")))
        object.__setattr__(
            self,
            "purpose",
            _enum("purpose", self.purpose, ("binding", "login", "recovery")),
        )
        object.__setattr__(
            self,
            "status",
            _enum("status", self.status, IDENTITY_DELIVERY_STATUSES),
        )
        object.__setattr__(self, "attempt", _integer("attempt", self.attempt, 0, 1000))
        object.__setattr__(
            self,
            "max_attempts",
            _integer("max_attempts", self.max_attempts, 1, 1000),
        )
        if self.attempt > self.max_attempts:
            _raise_status("attempt cannot exceed max_attempts")
        object.__setattr__(
            self,
            "lease_generation",
            _integer("lease_generation", self.lease_generation, 0, 9_007_199_254_740_991),
        )
        object.__setattr__(
            self,
            "redrive_count",
            _integer("redrive_count", self.redrive_count, 0, 1000),
        )
        object.__setattr__(
            self,
            "provider_idempotency_key",
            _idempotency_key(self.provider_idempotency_key),
        )
        object.__setattr__(
            self,
            "challenge_expires_at",
            _timestamp("challenge_expires_at", self.challenge_expires_at),
        )
        for name in (
            "lease_expires_at",
            "next_attempt_at",
            "accepted_at",
            "completed_at",
            "dead_at",
        ):
            object.__setattr__(self, name, _optional_timestamp(name, getattr(self, name)))
        object.__setattr__(
            self,
            "provider_acceptance_present",
            _boolean("provider_acceptance_present", self.provider_acceptance_present),
        )
        object.__setattr__(
            self,
            "last_failure_code",
            _optional_failure_code(self.last_failure_code),
        )
        _validate_task_state(self)
        assert_public_identity_delivery_payload(self.to_dict())

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "IdentityDeliveryTaskDTO":
        record = _strict_record("delivery task", payload, _TASK_KEYS)
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _TASK_KEYS}


@dataclass(frozen=True, slots=True)
class IdentityDeliveryAcceptanceDTO:
    schema_version: str
    task_id: str
    tenant_id: str
    project_id: str
    challenge_id: str
    status: str
    attempt: int
    lease_generation: int
    provider_idempotency_key: str
    provider_acceptance_present: bool
    accepted_at: str | None
    recorded_at: str
    failure_code: str | None

    def __post_init__(self) -> None:
        _literal("schema_version", self.schema_version, IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION)
        for name in ("task_id", "tenant_id", "project_id", "challenge_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        object.__setattr__(
            self,
            "status",
            _enum("status", self.status, IDENTITY_DELIVERY_ACCEPTANCE_STATUSES),
        )
        object.__setattr__(self, "attempt", _integer("attempt", self.attempt, 1, 1000))
        object.__setattr__(
            self,
            "lease_generation",
            _integer("lease_generation", self.lease_generation, 1, 9_007_199_254_740_991),
        )
        object.__setattr__(
            self,
            "provider_idempotency_key",
            _idempotency_key(self.provider_idempotency_key),
        )
        object.__setattr__(
            self,
            "provider_acceptance_present",
            _boolean("provider_acceptance_present", self.provider_acceptance_present),
        )
        object.__setattr__(self, "accepted_at", _optional_timestamp("accepted_at", self.accepted_at))
        object.__setattr__(self, "recorded_at", _timestamp("recorded_at", self.recorded_at))
        object.__setattr__(self, "failure_code", _optional_failure_code(self.failure_code))
        if self.status == "provider_accepted":
            if not self.provider_acceptance_present or self.accepted_at is None or self.failure_code is not None:
                _raise_status("accepted delivery requires confirmed provider acceptance")
            if self.accepted_at > self.recorded_at:
                _raise_status("provider acceptance cannot be recorded before it occurs")
        elif (
            self.provider_acceptance_present
            or self.accepted_at is not None
            or self.failure_code != "provider_result_ambiguous"
        ):
            _raise_status("ambiguous delivery cannot claim provider acceptance")
        assert_public_identity_delivery_payload(self.to_dict())

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityDeliveryAcceptanceDTO":
        record = _strict_record("delivery acceptance", payload, _ACCEPTANCE_KEYS)
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _ACCEPTANCE_KEYS}


@dataclass(frozen=True, slots=True)
class IdentityDeliveryRedriveRequestDTO:
    schema_version: str
    task_id: str
    tenant_id: str
    project_id: str
    expected_lease_generation: int
    actor_id: str
    reason_code: str
    request_id: str

    def __post_init__(self) -> None:
        _literal("schema_version", self.schema_version, IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION)
        for name in ("task_id", "tenant_id", "project_id", "actor_id", "request_id"):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        object.__setattr__(
            self,
            "expected_lease_generation",
            _integer(
                "expected_lease_generation",
                self.expected_lease_generation,
                1,
                9_007_199_254_740_990,
            ),
        )
        object.__setattr__(self, "reason_code", _reason_code(self.reason_code))
        assert_public_identity_delivery_payload(self.to_dict())

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityDeliveryRedriveRequestDTO":
        record = _strict_record("delivery redrive request", payload, _REDRIVE_REQUEST_KEYS)
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _REDRIVE_REQUEST_KEYS}


@dataclass(frozen=True, slots=True)
class IdentityDeliveryRedriveReceiptDTO:
    schema_version: str
    task_id: str
    tenant_id: str
    project_id: str
    request_id: str
    audit_id: str
    actor_id: str
    reason_code: str
    status: str
    previous_lease_generation: int
    lease_generation: int
    previous_provider_idempotency_key: str
    provider_idempotency_key: str
    redriven_at: str

    def __post_init__(self) -> None:
        _literal("schema_version", self.schema_version, IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION)
        for name in (
            "task_id",
            "tenant_id",
            "project_id",
            "request_id",
            "audit_id",
            "actor_id",
        ):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        object.__setattr__(self, "reason_code", _reason_code(self.reason_code))
        _literal("status", self.status, "pending")
        object.__setattr__(
            self,
            "previous_lease_generation",
            _integer(
                "previous_lease_generation",
                self.previous_lease_generation,
                1,
                9_007_199_254_740_990,
            ),
        )
        object.__setattr__(
            self,
            "lease_generation",
            _integer("lease_generation", self.lease_generation, 2, 9_007_199_254_740_991),
        )
        if self.lease_generation != self.previous_lease_generation + 1:
            _raise_status("redrive must advance the lease generation exactly once")
        object.__setattr__(
            self,
            "previous_provider_idempotency_key",
            _idempotency_key(self.previous_provider_idempotency_key),
        )
        object.__setattr__(
            self,
            "provider_idempotency_key",
            _idempotency_key(self.provider_idempotency_key),
        )
        if self.provider_idempotency_key == self.previous_provider_idempotency_key:
            raise IdentityDeliveryProtocolError(
                "audited redrive must rotate the provider idempotency key",
                code="identity_delivery_idempotency_conflict",
            )
        object.__setattr__(self, "redriven_at", _timestamp("redriven_at", self.redriven_at))
        assert_public_identity_delivery_payload(self.to_dict())

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "IdentityDeliveryRedriveReceiptDTO":
        record = _strict_record("delivery redrive receipt", payload, _REDRIVE_RECEIPT_KEYS)
        return cls(**record)

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _REDRIVE_RECEIPT_KEYS}


_TASK_KEYS = tuple(IdentityDeliveryTaskDTO.__dataclass_fields__)
_ACCEPTANCE_KEYS = tuple(IdentityDeliveryAcceptanceDTO.__dataclass_fields__)
_REDRIVE_REQUEST_KEYS = tuple(IdentityDeliveryRedriveRequestDTO.__dataclass_fields__)
_REDRIVE_RECEIPT_KEYS = tuple(IdentityDeliveryRedriveReceiptDTO.__dataclass_fields__)


def identity_delivery_protocol_contract_manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": IDENTITY_DELIVERY_PROTOCOL_SCHEMA_VERSION,
        "dto_kinds": list(IDENTITY_DELIVERY_DTO_KINDS),
        "statuses": list(IDENTITY_DELIVERY_STATUSES),
        "acceptance_statuses": list(IDENTITY_DELIVERY_ACCEPTANCE_STATUSES),
        "stable_error_codes": list(IDENTITY_DELIVERY_ERROR_CODES),
        "failure_codes": list(IDENTITY_DELIVERY_FAILURE_CODES),
        "routes": [dict(route) for route in IDENTITY_DELIVERY_ADMIN_ROUTES],
        "invariants": {
            "tenant_project_scope_required": True,
            "raw_delivery_material_absent": True,
            "private_reference_absent": True,
            "provider_idempotency_stable_on_retry": True,
            "provider_idempotency_rotates_only_on_audited_redrive": True,
            "provider_acceptance_presence_marker_only": True,
            "ambiguous_provider_outcome_fails_closed": True,
            "redrive_requires_generation_actor_reason_request": True,
            "admin_authorization_required": True,
            "routes_are_contract_only": True,
            "canonical_json_cross_language": True,
        },
    }
    assert_public_identity_delivery_payload(manifest)
    return manifest


def identity_delivery_admin_collection_route(project_id: str) -> str:
    return f"/v1/projects/{_route_segment('project_id', project_id)}/admin/identity-deliveries"


def identity_delivery_admin_task_route(project_id: str, task_id: str) -> str:
    return f"{identity_delivery_admin_collection_route(project_id)}/{_route_segment('task_id', task_id)}"


def identity_delivery_admin_acceptances_route(project_id: str, task_id: str) -> str:
    return f"{identity_delivery_admin_task_route(project_id, task_id)}/acceptances"


def identity_delivery_admin_redrive_route(project_id: str, task_id: str) -> str:
    return f"{identity_delivery_admin_task_route(project_id, task_id)}/redrive"


def identity_delivery_admin_redrives_route(project_id: str, task_id: str) -> str:
    return f"{identity_delivery_admin_task_route(project_id, task_id)}/redrives"


def assert_public_identity_delivery_payload(value: Any) -> None:
    """Reject raw delivery destinations, codes, credentials, and private references."""

    seen: set[int] = set()

    def visit(item: Any) -> None:
        if isinstance(item, str):
            if _contains_private_material(item):
                raise IdentityDeliveryProtocolError(
                    "public identity delivery payload contains forbidden material",
                    code="identity_delivery_secret_forbidden",
                )
            return
        if isinstance(item, (bytes, bytearray, memoryview)):
            raise IdentityDeliveryProtocolError(
                "public identity delivery payload contains forbidden binary material",
                code="identity_delivery_secret_forbidden",
            )
        if item is None or isinstance(item, (bool, int, float)):
            return
        if isinstance(item, Mapping):
            marker = id(item)
            if marker in seen:
                raise IdentityDeliveryProtocolError(
                    "public identity delivery payload contains a cycle"
                )
            seen.add(marker)
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise IdentityDeliveryProtocolError(
                        "public identity delivery payload keys must be strings"
                    )
                canonical = _canonical_key(key)
                if canonical in _FORBIDDEN_PUBLIC_KEYS or canonical.endswith(
                    _FORBIDDEN_PUBLIC_SUFFIXES
                ):
                    raise IdentityDeliveryProtocolError(
                        "public identity delivery payload contains forbidden material",
                        code="identity_delivery_secret_forbidden",
                    )
                visit(nested)
            seen.remove(marker)
            return
        if isinstance(item, (list, tuple)):
            marker = id(item)
            if marker in seen:
                raise IdentityDeliveryProtocolError(
                    "public identity delivery payload contains a cycle"
                )
            seen.add(marker)
            for nested in item:
                visit(nested)
            seen.remove(marker)
            return
        raise IdentityDeliveryProtocolError(
            "public identity delivery payload contains an unsupported value"
        )

    visit(value)


def validate_identity_delivery_task(value: Any) -> IdentityDeliveryTaskDTO:
    if isinstance(value, IdentityDeliveryTaskDTO):
        return value
    return IdentityDeliveryTaskDTO.from_public_response(value)


def validate_identity_delivery_acceptance(value: Any) -> IdentityDeliveryAcceptanceDTO:
    if isinstance(value, IdentityDeliveryAcceptanceDTO):
        return value
    return IdentityDeliveryAcceptanceDTO.from_public_response(value)


def validate_identity_delivery_redrive_request(
    value: Any,
) -> IdentityDeliveryRedriveRequestDTO:
    if isinstance(value, IdentityDeliveryRedriveRequestDTO):
        return value
    return IdentityDeliveryRedriveRequestDTO.from_public_response(value)


def validate_identity_delivery_redrive_receipt(
    value: Any,
) -> IdentityDeliveryRedriveReceiptDTO:
    if isinstance(value, IdentityDeliveryRedriveReceiptDTO):
        return value
    return IdentityDeliveryRedriveReceiptDTO.from_public_response(value)


_DTO_VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "task": validate_identity_delivery_task,
    "acceptance": validate_identity_delivery_acceptance,
    "redrive_request": validate_identity_delivery_redrive_request,
    "redrive_receipt": validate_identity_delivery_redrive_receipt,
}


def canonical_identity_delivery_json(kind: str, value: Any) -> str:
    normalized_kind = _enum("dto kind", kind, IDENTITY_DELIVERY_DTO_KINDS)
    dto = _DTO_VALIDATORS[normalized_kind](value)
    payload = dto.to_dict()
    assert_public_identity_delivery_payload(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if len(encoded.encode("utf-8")) > _MAX_CANONICAL_JSON_BYTES:
        raise IdentityDeliveryProtocolError("identity delivery payload is too large")
    return encoded


def parse_identity_delivery_canonical_json(kind: str, value: str | bytes) -> Any:
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise IdentityDeliveryProtocolError(
                "identity delivery JSON must be UTF-8"
            ) from exc
    elif isinstance(value, str):
        text = value
    else:
        raise IdentityDeliveryProtocolError("identity delivery JSON must be text")
    if not text or len(text.encode("utf-8")) > _MAX_CANONICAL_JSON_BYTES:
        raise IdentityDeliveryProtocolError("identity delivery JSON size is invalid")
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, IdentityDeliveryProtocolError) as exc:
        if isinstance(exc, IdentityDeliveryProtocolError):
            raise
        raise IdentityDeliveryProtocolError("identity delivery JSON is invalid") from exc
    dto = _DTO_VALIDATORS[_enum("dto kind", kind, IDENTITY_DELIVERY_DTO_KINDS)](payload)
    if canonical_identity_delivery_json(kind, dto) != text:
        raise IdentityDeliveryProtocolError("identity delivery JSON is not canonical")
    return dto


def _validate_task_state(task: IdentityDeliveryTaskDTO) -> None:
    leased = task.status == "leased"
    if leased != (task.lease_expires_at is not None):
        _raise_status("only leased delivery tasks carry lease expiration")
    if leased and task.lease_generation < 1:
        _raise_status("leased delivery tasks require a positive generation")
    retry = task.status == "retry"
    if retry != (task.next_attempt_at is not None):
        _raise_status("only retry delivery tasks carry a next attempt time")
    if retry and task.last_failure_code is None:
        _raise_status("retry delivery tasks require a failure code")

    if task.status == "provider_accepted":
        valid = (
            task.provider_acceptance_present
            and task.accepted_at is not None
            and task.completed_at is None
            and task.dead_at is None
            and task.last_failure_code is None
        )
    elif task.status == "delivered":
        valid = (
            task.provider_acceptance_present
            and task.accepted_at is not None
            and task.completed_at is not None
            and task.dead_at is None
            and task.last_failure_code is None
        )
        if valid and task.accepted_at > task.completed_at:
            valid = False
    elif task.status == "ambiguous":
        valid = (
            not task.provider_acceptance_present
            and task.accepted_at is None
            and task.completed_at is None
            and task.dead_at is None
            and task.last_failure_code == "provider_result_ambiguous"
        )
    elif task.status == "dead":
        valid = (
            not task.provider_acceptance_present
            and task.accepted_at is None
            and task.completed_at is None
            and task.dead_at is not None
            and task.last_failure_code is not None
        )
    else:
        valid = (
            not task.provider_acceptance_present
            and task.accepted_at is None
            and task.completed_at is None
            and task.dead_at is None
        )
    if not valid:
        _raise_status("delivery task terminal metadata conflicts with status")


def _strict_record(name: str, value: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    assert_public_identity_delivery_payload(value)
    if not isinstance(value, Mapping):
        raise IdentityDeliveryProtocolError(f"{name} must be an object")
    actual = set(value)
    expected = set(keys)
    if actual - expected:
        raise IdentityDeliveryProtocolError(
            f"{name} contains an unknown field",
            code="identity_delivery_unknown_field",
        )
    if expected - actual:
        raise IdentityDeliveryProtocolError(f"{name} is missing a required field")
    return {key: value[key] for key in keys}


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise IdentityDeliveryProtocolError(f"{name} must be a valid identifier")
    return value


def _idempotency_key(value: Any) -> str:
    if not isinstance(value, str) or not _IDEMPOTENCY_PATTERN.fullmatch(value):
        raise IdentityDeliveryProtocolError("provider idempotency key is invalid")
    return value


def _reason_code(value: Any) -> str:
    if not isinstance(value, str) or not _REASON_PATTERN.fullmatch(value):
        raise IdentityDeliveryProtocolError("reason code is invalid")
    return value


def _optional_failure_code(value: Any) -> str | None:
    if value is None:
        return None
    return _enum("failure code", value, IDENTITY_DELIVERY_FAILURE_CODES)


def _integer(name: str, value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise IdentityDeliveryProtocolError(f"{name} is outside the supported range")
    return value


def _boolean(name: str, value: Any) -> bool:
    if type(value) is not bool:
        raise IdentityDeliveryProtocolError(f"{name} must be a boolean")
    return value


def _literal(name: str, value: Any, expected: str) -> str:
    if value != expected:
        raise IdentityDeliveryProtocolError(f"{name} is not supported")
    return expected


def _enum(name: str, value: Any, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise IdentityDeliveryProtocolError(f"{name} is not supported")
    return value


def _timestamp(name: str, value: Any) -> str:
    if not isinstance(value, str) or not _TIMESTAMP_PATTERN.fullmatch(value):
        raise IdentityDeliveryProtocolError(f"{name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise IdentityDeliveryProtocolError(
            f"{name} must be a canonical UTC timestamp"
        ) from exc
    canonical = parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    if canonical != value:
        raise IdentityDeliveryProtocolError(f"{name} must be a canonical UTC timestamp")
    return value


def _optional_timestamp(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _timestamp(name, value)


def _route_segment(name: str, value: Any) -> str:
    return quote(_identifier(name, value), safe="")


def _canonical_key(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def _contains_private_material(value: str) -> bool:
    return bool(
        _PRIVATE_REFERENCE_PATTERN.search(value)
        or _EMAIL_PATTERN.search(value)
        or _PHONE_PATTERN.search(value)
        or any(pattern.search(value) for pattern in _TOKEN_PATTERNS)
    )


def _public_error_message(message: str) -> str:
    candidate = str(message or "identity delivery payload rejected")
    if _contains_private_material(candidate):
        return "identity delivery payload rejected"
    return candidate


def _raise_status(message: str) -> None:
    raise IdentityDeliveryProtocolError(
        message,
        code="identity_delivery_status_conflict",
    )


def _reject_duplicate_keys(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise IdentityDeliveryProtocolError("identity delivery JSON contains duplicate fields")
        result[key] = value
    return result
