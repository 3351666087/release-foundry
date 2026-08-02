from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from threading import RLock
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote
from uuid import uuid4


SESSION_LIFECYCLE_SCHEMA_VERSION = "releasefoundry.session_lifecycle.v1"
SESSION_LIFECYCLE_STATUSES = ("active", "rotated", "revoked", "expired")
SESSION_ASSURANCE_LEVELS = ("aal1", "aal2", "aal3")
SESSION_REVOCATION_REASONS = (
    "user_revoked",
    "revoke_all",
    "account_recovery",
    "refresh_reuse_detected",
    "security_event",
    "administrative",
)
SESSION_LIFECYCLE_ERROR_CODES = (
    "session_invalid_request",
    "session_not_found",
    "session_expired",
    "session_revoked",
    "session_refresh_reused",
    "session_scope_mismatch",
    "session_recent_auth_required",
    "session_digest_conflict",
    "session_store_failed",
)
_ERROR_CODE_ALIASES = {
    "session_idempotency_conflict": "session_digest_conflict",
    "session_access_expired": "session_expired",
    "session_refresh_expired": "session_expired",
    "session_refresh_reuse_detected": "session_refresh_reused",
    "session_assurance_required": "session_recent_auth_required",
    "session_snapshot_invalid": "session_invalid_request",
    "session_transport_failed": "session_store_failed",
    "session_forbidden_secret": "session_invalid_request",
}

_ROUTE_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "operation": "session_issue",
        "method": "POST",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions",
    },
    {
        "operation": "session_authenticate",
        "method": "POST",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/authenticate",
    },
    {
        "operation": "session_list",
        "method": "GET",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions",
    },
    {
        "operation": "session_refresh",
        "method": "POST",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/refresh",
    },
    {
        "operation": "browser_session_refresh",
        "method": "POST",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh",
    },
    {
        "operation": "session_revoke",
        "method": "POST",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/{session_id}/revoke",
    },
    {
        "operation": "session_revoke_all",
        "method": "POST",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/revoke-all",
    },
    {
        "operation": "session_recent_auth",
        "method": "POST",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/{session_id}/recent-auth",
    },
    {
        "operation": "session_recovery_invalidate",
        "method": "POST",
        "path": "/v1/projects/{project_id}/accounts/{account_id}/sessions/recovery-invalidate",
    },
)

_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_REASON_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CREDENTIAL_VALUE_PATTERNS = (
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
    re.compile(
        r"\b(?:access_token|refresh_token|client_secret|password|authorization)\s*[:=]",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:sk-|tp_|ghp_|releasefoundry_live_)[A-Za-z0-9_-]{6,}", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b[0-9a-f]{64}\b", re.IGNORECASE),
)
_FORBIDDEN_PUBLIC_CANONICAL_KEYS = frozenset(
    {
        "accesstoken",
        "accesstokendigest",
        "apikey",
        "authorization",
        "authorizationcode",
        "clientsecret",
        "cookie",
        "credentialsecret",
        "idtoken",
        "password",
        "refreshtoken",
        "refreshtokendigest",
        "rotationfamilydigest",
        "secret",
        "sessiontoken",
        "tokendigest",
        "token",
    }
)
_ALLOWED_PUBLIC_CREDENTIAL_MARKERS = frozenset(
    {"accesstokenpresent", "refreshtokenpresent"}
)
_SNAPSHOT_TOP_LEVEL_KEYS = frozenset(
    {"schema_version", "storage_mode", "families", "idempotency", "integrity"}
)
_FAMILY_SNAPSHOT_KEYS = frozenset(
    {
        "tenant_id",
        "project_id",
        "account_id",
        "session_id",
        "rotation_family_id",
        "rotation_family_digest",
        "created_at",
        "reuse_detected_at",
        "generations",
    }
)
_GENERATION_SNAPSHOT_KEYS = frozenset(
    {
        "generation",
        "access_token_digest",
        "refresh_token_digest",
        "status",
        "assurance_level",
        "authenticated_at",
        "created_at",
        "access_expires_at",
        "refresh_expires_at",
        "rotated_at",
        "revoked_at",
        "revoke_reason_code",
    }
)
_IDEMPOTENCY_SNAPSHOT_KEYS = frozenset(
    {
        "tenant_id",
        "project_id",
        "account_id",
        "operation",
        "key_digest",
        "request_digest",
        "response_type",
        "response",
    }
)


class SessionLifecycleError(ValueError):
    """Stable, public-safe failure from the session lifecycle contract."""

    def __init__(
        self, message: str, *, code: str = "session_invalid_request"
    ) -> None:
        normalized_code = _ERROR_CODE_ALIASES.get(code, code)
        if normalized_code not in SESSION_LIFECYCLE_ERROR_CODES:
            raise ValueError("unknown session lifecycle error code")
        self.code = normalized_code
        self.message = _redact_message(message)
        super().__init__(self.message)


def session_lifecycle_contract_manifest() -> dict[str, Any]:
    """Return the stable, public-safe Python/TypeScript parity contract."""

    manifest: dict[str, Any] = {
        "schema_version": SESSION_LIFECYCLE_SCHEMA_VERSION,
        "digest_only": True,
        "rotation": True,
        "reuse_detection": True,
        "revocation": True,
        "recent_auth": True,
        "recovery": True,
        "statuses": list(SESSION_LIFECYCLE_STATUSES),
        "stable_error_codes": list(SESSION_LIFECYCLE_ERROR_CODES),
        "routes": deepcopy(list(_ROUTE_TEMPLATES)),
        "invariants": {
            "tenant_project_account_isolation": True,
            "one_active_generation_per_rotation_family": True,
            "refresh_rotation_is_atomic": True,
            "reused_refresh_revokes_active_family": True,
            "revoke_one_is_scoped": True,
            "revoke_all_is_scoped": True,
            "recent_auth_uses_original_authentication_time": True,
            "recovery_invalidates_active_sessions": True,
            "snapshots_are_digest_only": True,
            "public_dto_excludes_token_digests": True,
            "access_refresh_token_classes_are_distinct": True,
            "session_token_receipts_are_one_time": True,
            "refresh_bearer_never_authenticates_as_access": True,
            "public_serialization_redacts_bearers": True,
        },
    }
    assert_public_session_payload(manifest)
    return manifest


@dataclass(frozen=True, slots=True)
class SessionScope:
    tenant_id: str
    project_id: str
    account_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _identifier("tenant_id", self.tenant_id))
        object.__setattr__(self, "project_id", _identifier("project_id", self.project_id))
        object.__setattr__(self, "account_id", _identifier("account_id", self.account_id))

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "account_id": self.account_id,
        }


class _TypedSessionDigest:
    __slots__ = ("__value",)

    _digest_name = "session_digest"
    _display_name = "SessionDigest"
    _public_marker = "digest_present"

    def __init__(self, value: str) -> None:
        self.__value = _digest(self._digest_name, value)

    def for_storage(self) -> str:
        return self.__value

    def to_public_dict(self) -> dict[str, bool]:
        return {self._public_marker: True}

    def __repr__(self) -> str:
        return f"{self._display_name}<redacted>"

    __str__ = __repr__


class SessionAccessTokenDigest(_TypedSessionDigest):
    """Validated access digest that cannot be used as a refresh digest."""

    _digest_name = "access_token_digest"
    _display_name = "SessionAccessTokenDigest"
    _public_marker = "access_token_present"


class SessionRefreshTokenDigest(_TypedSessionDigest):
    """Validated refresh digest that cannot be used as an access digest."""

    _digest_name = "refresh_token_digest"
    _display_name = "SessionRefreshTokenDigest"
    _public_marker = "refresh_token_present"


class SessionRotationFamilyDigest(_TypedSessionDigest):
    """Validated opaque digest identifying one refresh-rotation family."""

    _digest_name = "rotation_family_digest"
    _display_name = "SessionRotationFamilyDigest"
    _public_marker = "rotation_family_present"

    @classmethod
    def from_material(cls, value: str) -> "SessionRotationFamilyDigest":
        material = _session_token_material(value)
        try:
            return cls(hashlib.sha256(material).hexdigest())
        finally:
            _wipe_bytearray(material)


class _SessionToken:
    __slots__ = ("__material", "__taken", "__lock")

    _display_name = "SessionToken"
    _token_class = "session"

    def __init__(self, value: str) -> None:
        self.__material = _session_token_material(value)
        self.__taken = False
        self.__lock = RLock()

    @property
    def token_class(self) -> str:
        return self._token_class

    @property
    def available(self) -> bool:
        with self.__lock:
            return not self.__taken and bool(self.__material)

    def _digest_value(self) -> str:
        with self.__lock:
            if self.__taken or not self.__material:
                raise SessionLifecycleError("session token is unavailable")
            return hashlib.sha256(self.__material).hexdigest()

    def take(self) -> str:
        """Transfer the bearer exactly once and clear the retained bytes."""

        with self.__lock:
            if self.__taken or not self.__material:
                raise SessionLifecycleError("session token is unavailable")
            try:
                value = bytes(self.__material).decode("ascii")
            finally:
                _wipe_bytearray(self.__material)
                self.__material.clear()
                self.__taken = True
            return value

    def discard(self) -> None:
        with self.__lock:
            _wipe_bytearray(self.__material)
            self.__material.clear()
            self.__taken = True

    def to_public_dict(self) -> dict[str, bool]:
        available = self.available
        return {
            "access_token_present": available and self._token_class == "access",
            "refresh_token_present": available and self._token_class == "refresh",
        }

    def __repr__(self) -> str:
        state = "present" if self.available else "consumed"
        return f"{self._display_name}<{state},redacted>"

    __str__ = __repr__

    def __del__(self) -> None:
        material = getattr(self, "_SessionToken__material", None)
        if isinstance(material, bytearray):
            _wipe_bytearray(material)


class SessionAccessToken(_SessionToken):
    """Opaque one-use access bearer with an access-only digest type."""

    _display_name = "SessionAccessToken"
    _token_class = "access"

    def digest(self) -> SessionAccessTokenDigest:
        return SessionAccessTokenDigest(self._digest_value())


class SessionRefreshToken(_SessionToken):
    """Opaque one-use refresh bearer with a refresh-only digest type."""

    _display_name = "SessionRefreshToken"
    _token_class = "refresh"

    def digest(self) -> SessionRefreshTokenDigest:
        return SessionRefreshTokenDigest(self._digest_value())


class SessionTokenPair:
    """Private access/refresh pair; neither bearer is publicly serializable."""

    __slots__ = ("__access", "__refresh", "__lock")

    def __init__(
        self,
        access_token: SessionAccessToken,
        refresh_token: SessionRefreshToken,
    ) -> None:
        if not isinstance(access_token, SessionAccessToken) or not isinstance(
            refresh_token, SessionRefreshToken
        ):
            raise SessionLifecycleError(
                "session token pair requires distinct access and refresh token classes"
            )
        if not access_token.available or not refresh_token.available:
            raise SessionLifecycleError("session token pair contains unavailable material")
        if (
            access_token.digest().for_storage()
            == refresh_token.digest().for_storage()
        ):
            raise SessionLifecycleError(
                "session access and refresh token material must be distinct"
            )
        self.__access = access_token
        self.__refresh = refresh_token
        self.__lock = RLock()

    @property
    def available(self) -> bool:
        with self.__lock:
            return self.__access.available and self.__refresh.available

    def access_digest(self) -> SessionAccessTokenDigest:
        with self.__lock:
            return self.__access.digest()

    def refresh_digest(self) -> SessionRefreshTokenDigest:
        with self.__lock:
            return self.__refresh.digest()

    def take_access_token(self) -> str:
        with self.__lock:
            return self.__access.take()

    def take_refresh_token(self) -> str:
        with self.__lock:
            return self.__refresh.take()

    def discard(self) -> None:
        with self.__lock:
            self.__access.discard()
            self.__refresh.discard()

    def to_public_dict(self) -> dict[str, bool]:
        with self.__lock:
            payload = {
                "access_token_present": self.__access.available,
                "refresh_token_present": self.__refresh.available,
            }
        assert_public_session_payload(payload)
        return payload

    def __repr__(self) -> str:
        payload = self.to_public_dict()
        return (
            "SessionTokenPair{access_token:<redacted:%s>,"
            "refresh_token:<redacted:%s>}"
            % (payload["access_token_present"], payload["refresh_token_present"])
        )

    __str__ = __repr__


class SessionTokenPairReceipt:
    """Ephemeral, one-use transfer receipt compatible with the Go handoff."""

    __slots__ = (
        "session_id",
        "key_version",
        "access_expires_at",
        "refresh_expires_at",
        "__pair",
        "__taken",
        "__lock",
    )

    def __init__(
        self,
        *,
        session_id: str,
        key_version: str,
        access_expires_at: datetime | str,
        refresh_expires_at: datetime | str,
        token_pair: SessionTokenPair,
        now: datetime | str | None = None,
    ) -> None:
        if not isinstance(token_pair, SessionTokenPair):
            raise SessionLifecycleError("session token receipt requires a token pair")
        if not token_pair.available:
            raise SessionLifecycleError("session token receipt requires a complete pair")
        access_expiry = _coerce_timestamp(access_expires_at)
        refresh_expiry = _coerce_timestamp(refresh_expires_at)
        if access_expiry >= refresh_expiry:
            raise SessionLifecycleError(
                "access expiration must precede refresh expiration"
            )
        if now is not None:
            current_time = _coerce_timestamp(now)
            if access_expiry <= current_time or refresh_expiry <= current_time:
                raise SessionLifecycleError("session token receipt is expired")
        self.session_id = _identifier("session_id", session_id)
        self.key_version = _identifier("key_version", key_version)
        self.access_expires_at = _format_timestamp(access_expiry)
        self.refresh_expires_at = _format_timestamp(refresh_expiry)
        self.__pair: SessionTokenPair | None = token_pair
        self.__taken = False
        self.__lock = RLock()

    def take_token_pair(self) -> SessionTokenPair:
        with self.__lock:
            if self.__taken or self.__pair is None:
                raise SessionLifecycleError("session token receipt is unavailable")
            pair = self.__pair
            self.__pair = None
            self.__taken = True
            return pair

    def discard(self) -> None:
        with self.__lock:
            if self.__pair is not None:
                self.__pair.discard()
            self.__pair = None
            self.__taken = True

    def to_public_dict(self) -> dict[str, Any]:
        with self.__lock:
            pair = self.__pair
            markers = (
                pair.to_public_dict()
                if not self.__taken and pair is not None
                else {
                    "access_token_present": False,
                    "refresh_token_present": False,
                }
            )
            payload = {
                "schema_version": SESSION_LIFECYCLE_SCHEMA_VERSION,
                "session_id": self.session_id,
                "key_version": self.key_version,
                "access_expires_at": self.access_expires_at,
                "refresh_expires_at": self.refresh_expires_at,
                **markers,
            }
        assert_public_session_payload(payload)
        return payload

    def __repr__(self) -> str:
        payload = self.to_public_dict()
        return (
            "SessionTokenPairReceipt{session_id:%r,key_version:%r,"
            "access_expires_at:%r,refresh_expires_at:%r,"
            "access_token:<redacted:%s>,refresh_token:<redacted:%s>}"
            % (
                self.session_id,
                self.key_version,
                self.access_expires_at,
                self.refresh_expires_at,
                payload["access_token_present"],
                payload["refresh_token_present"],
            )
        )

    __str__ = __repr__


@dataclass(frozen=True, slots=True)
class SessionDTO:
    schema_version: str
    tenant_id: str
    project_id: str
    account_id: str
    session_id: str
    rotation_family_id: str
    generation: int
    status: str
    assurance_level: str
    authenticated_at: str
    created_at: str
    access_expires_at: str
    refresh_expires_at: str
    last_rotated_at: str | None
    revoked_at: str | None
    revoke_reason_code: str | None
    access_token_present: bool
    refresh_token_present: bool

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "SessionDTO":
        assert_public_session_payload(payload)
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "tenant_id",
                "project_id",
                "account_id",
                "session_id",
                "rotation_family_id",
                "generation",
                "status",
                "assurance_level",
                "authenticated_at",
                "created_at",
                "access_expires_at",
                "refresh_expires_at",
                "last_rotated_at",
                "revoked_at",
                "revoke_reason_code",
                "access_token_present",
                "refresh_token_present",
            },
            "session dto",
        )
        schema_version = str(payload.get("schema_version") or "")
        if schema_version != SESSION_LIFECYCLE_SCHEMA_VERSION:
            raise SessionLifecycleError("session schema version mismatch")
        status = _enum("status", payload.get("status"), SESSION_LIFECYCLE_STATUSES)
        assurance = _enum(
            "assurance_level", payload.get("assurance_level"), SESSION_ASSURANCE_LEVELS
        )
        generation = _non_negative_int("generation", payload.get("generation"))
        authenticated_at = _timestamp_text(
            "authenticated_at", payload.get("authenticated_at")
        )
        created_at = _timestamp_text("created_at", payload.get("created_at"))
        access_expires_at = _timestamp_text(
            "access_expires_at", payload.get("access_expires_at")
        )
        refresh_expires_at = _timestamp_text(
            "refresh_expires_at", payload.get("refresh_expires_at")
        )
        if _parse_timestamp(access_expires_at) > _parse_timestamp(refresh_expires_at):
            raise SessionLifecycleError(
                "access expiration cannot exceed refresh expiration"
            )
        last_rotated_at = _optional_timestamp_text(
            "last_rotated_at", payload.get("last_rotated_at")
        )
        revoked_at = _optional_timestamp_text("revoked_at", payload.get("revoked_at"))
        reason = _optional_reason(payload.get("revoke_reason_code"))
        access_present = _boolean(
            "access_token_present", payload.get("access_token_present")
        )
        refresh_present = _boolean(
            "refresh_token_present", payload.get("refresh_token_present")
        )
        if status == "revoked" and (revoked_at is None or reason is None):
            raise SessionLifecycleError("revoked session requires revocation metadata")
        if status != "revoked" and (revoked_at is not None or reason is not None):
            raise SessionLifecycleError("non-revoked session has revocation metadata")
        if status != "active" and (access_present or refresh_present):
            raise SessionLifecycleError("inactive session cannot expose token markers")
        return cls(
            schema_version=schema_version,
            tenant_id=_identifier("tenant_id", payload.get("tenant_id")),
            project_id=_identifier("project_id", payload.get("project_id")),
            account_id=_identifier("account_id", payload.get("account_id")),
            session_id=_identifier("session_id", payload.get("session_id")),
            rotation_family_id=_identifier(
                "rotation_family_id", payload.get("rotation_family_id")
            ),
            generation=generation,
            status=status,
            assurance_level=assurance,
            authenticated_at=authenticated_at,
            created_at=created_at,
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
            last_rotated_at=last_rotated_at,
            revoked_at=revoked_at,
            revoke_reason_code=reason,
            access_token_present=access_present,
            refresh_token_present=refresh_present,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "account_id": self.account_id,
            "session_id": self.session_id,
            "rotation_family_id": self.rotation_family_id,
            "generation": self.generation,
            "status": self.status,
            "assurance_level": self.assurance_level,
            "authenticated_at": self.authenticated_at,
            "created_at": self.created_at,
            "access_expires_at": self.access_expires_at,
            "refresh_expires_at": self.refresh_expires_at,
            "last_rotated_at": self.last_rotated_at,
            "revoked_at": self.revoked_at,
            "revoke_reason_code": self.revoke_reason_code,
            "access_token_present": self.access_token_present,
            "refresh_token_present": self.refresh_token_present,
        }
        assert_public_session_payload(payload)
        return payload


SessionPublicDTO = SessionDTO


@dataclass(frozen=True, slots=True)
class SessionRevocationDTO:
    schema_version: str
    tenant_id: str
    project_id: str
    account_id: str
    reason_code: str
    revoked_at: str
    revoked_session_ids: tuple[str, ...]
    revoked_count: int

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any]
    ) -> "SessionRevocationDTO":
        assert_public_session_payload(payload)
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "tenant_id",
                "project_id",
                "account_id",
                "reason_code",
                "revoked_at",
                "revoked_session_ids",
                "revoked_count",
            },
            "session revocation dto",
        )
        if payload.get("schema_version") != SESSION_LIFECYCLE_SCHEMA_VERSION:
            raise SessionLifecycleError("session schema version mismatch")
        ids = _identifier_sequence(
            "revoked_session_ids", payload.get("revoked_session_ids")
        )
        count = _non_negative_int("revoked_count", payload.get("revoked_count"))
        if count != len(ids):
            raise SessionLifecycleError("revoked session count mismatch")
        return cls(
            schema_version=SESSION_LIFECYCLE_SCHEMA_VERSION,
            tenant_id=_identifier("tenant_id", payload.get("tenant_id")),
            project_id=_identifier("project_id", payload.get("project_id")),
            account_id=_identifier("account_id", payload.get("account_id")),
            reason_code=_reason(payload.get("reason_code")),
            revoked_at=_timestamp_text("revoked_at", payload.get("revoked_at")),
            revoked_session_ids=ids,
            revoked_count=count,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "account_id": self.account_id,
            "reason_code": self.reason_code,
            "revoked_at": self.revoked_at,
            "revoked_session_ids": list(self.revoked_session_ids),
            "revoked_count": self.revoked_count,
        }
        assert_public_session_payload(payload)
        return payload


@dataclass(frozen=True, slots=True)
class RecentAuthDTO:
    schema_version: str
    tenant_id: str
    project_id: str
    account_id: str
    session_id: str
    assurance_level: str
    authenticated_at: str
    valid_until: str
    recent: bool

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "RecentAuthDTO":
        assert_public_session_payload(payload)
        _require_exact_keys(
            payload,
            {
                "schema_version",
                "tenant_id",
                "project_id",
                "account_id",
                "session_id",
                "assurance_level",
                "authenticated_at",
                "valid_until",
                "recent",
            },
            "recent auth dto",
        )
        if payload.get("schema_version") != SESSION_LIFECYCLE_SCHEMA_VERSION:
            raise SessionLifecycleError("session schema version mismatch")
        recent = _boolean("recent", payload.get("recent"))
        if not recent:
            raise SessionLifecycleError(
                "recent authentication is required",
                code="session_recent_auth_required",
            )
        authenticated_at = _timestamp_text(
            "authenticated_at", payload.get("authenticated_at")
        )
        valid_until = _timestamp_text("valid_until", payload.get("valid_until"))
        if _parse_timestamp(valid_until) < _parse_timestamp(authenticated_at):
            raise SessionLifecycleError("recent authentication interval is invalid")
        return cls(
            schema_version=SESSION_LIFECYCLE_SCHEMA_VERSION,
            tenant_id=_identifier("tenant_id", payload.get("tenant_id")),
            project_id=_identifier("project_id", payload.get("project_id")),
            account_id=_identifier("account_id", payload.get("account_id")),
            session_id=_identifier("session_id", payload.get("session_id")),
            assurance_level=_enum(
                "assurance_level",
                payload.get("assurance_level"),
                SESSION_ASSURANCE_LEVELS,
            ),
            authenticated_at=authenticated_at,
            valid_until=valid_until,
            recent=True,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "account_id": self.account_id,
            "session_id": self.session_id,
            "assurance_level": self.assurance_level,
            "authenticated_at": self.authenticated_at,
            "valid_until": self.valid_until,
            "recent": self.recent,
        }
        assert_public_session_payload(payload)
        return payload


@dataclass(slots=True, repr=False)
class _Generation:
    generation: int
    access_token_digest: str = field(repr=False)
    refresh_token_digest: str = field(repr=False)
    status: str
    assurance_level: str
    authenticated_at: datetime
    created_at: datetime
    access_expires_at: datetime
    refresh_expires_at: datetime
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    revoke_reason_code: str | None = None


@dataclass(slots=True, repr=False)
class _SessionFamily:
    scope: SessionScope
    session_id: str
    rotation_family_id: str
    rotation_family_digest: str = field(repr=False)
    created_at: datetime
    generations: list[_Generation] = field(default_factory=list, repr=False)
    reuse_detected_at: datetime | None = None

    @property
    def current(self) -> _Generation:
        return self.generations[-1]


@dataclass(frozen=True, slots=True, repr=False)
class _IdempotencyRecord:
    request_digest: str = field(repr=False)
    response_type: str
    response: dict[str, Any] = field(repr=False)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
SessionTransport = Callable[[str, str, Mapping[str, Any]], Mapping[str, Any]]


class SessionLifecycleStore:
    """Thread-safe local lifecycle model that accepts and stores digests only."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (
            lambda prefix: f"{prefix}_{uuid4().hex}"
        )
        self._families: dict[str, _SessionFamily] = {}
        self._rotation_family_ids: set[str] = set()
        self._digest_index: dict[str, tuple[str, str, int]] = {}
        self._idempotency: dict[
            tuple[str, str, str, str, str], _IdempotencyRecord
        ] = {}
        self._lock = RLock()

    def issue_session(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        access_token_digest: str | SessionAccessTokenDigest,
        refresh_token_digest: str | SessionRefreshTokenDigest,
        rotation_family_digest: str | SessionRotationFamilyDigest,
        access_expires_at: datetime | str,
        refresh_expires_at: datetime | str,
        idempotency_key: str,
        authenticated_at: datetime | str | None = None,
        assurance_level: str = "aal1",
        session_id: str | None = None,
        rotation_family_id: str | None = None,
        now: datetime | str | None = None,
    ) -> SessionDTO:
        scope = SessionScope(tenant_id, project_id, account_id)
        current_time = self._time(now)
        authenticated = self._time(authenticated_at, default=current_time)
        access_expires = self._time(access_expires_at)
        refresh_expires = self._time(refresh_expires_at)
        access_digest = _access_digest("access_token_digest", access_token_digest)
        refresh_digest = _refresh_digest("refresh_token_digest", refresh_token_digest)
        family_digest = _rotation_family_digest(
            "rotation_family_digest", rotation_family_digest
        )
        assurance = _enum(
            "assurance_level", assurance_level, SESSION_ASSURANCE_LEVELS
        )
        requested_session_id = (
            _identifier("session_id", session_id) if session_id is not None else None
        )
        requested_family_id = (
            _identifier("rotation_family_id", rotation_family_id)
            if rotation_family_id is not None
            else None
        )
        if authenticated > current_time:
            raise SessionLifecycleError("authenticated_at cannot be in the future")
        _validate_expirations(current_time, access_expires, refresh_expires)
        request_digest = _fingerprint(
            {
                **scope.to_dict(),
                "access_token_digest": access_digest,
                "refresh_token_digest": refresh_digest,
                "rotation_family_digest": family_digest,
                "access_expires_at": _format_timestamp(access_expires),
                "refresh_expires_at": _format_timestamp(refresh_expires),
                "authenticated_at": _format_timestamp(authenticated),
                "assurance_level": assurance,
                "session_id": requested_session_id,
                "rotation_family_id": requested_family_id,
            }
        )
        with self._lock:
            replay = self._idempotency_response(
                scope,
                "session_create",
                idempotency_key,
                request_digest,
                "session",
            )
            if replay is not None:
                return SessionDTO.from_public_response(replay)
            self._assert_digests_available(
                access_digest, refresh_digest, family_digest
            )
            actual_session_id = requested_session_id or self._new_id(
                "session", set(self._families)
            )
            actual_family_id = requested_family_id or self._new_id(
                "family", self._rotation_family_ids
            )
            if actual_session_id in self._families:
                raise SessionLifecycleError(
                    "session identifier already exists",
                    code="session_digest_conflict",
                )
            if actual_family_id in self._rotation_family_ids:
                raise SessionLifecycleError(
                    "rotation family identifier already exists",
                    code="session_digest_conflict",
                )
            generation = _Generation(
                generation=0,
                access_token_digest=access_digest,
                refresh_token_digest=refresh_digest,
                status="active",
                assurance_level=assurance,
                authenticated_at=authenticated,
                created_at=current_time,
                access_expires_at=access_expires,
                refresh_expires_at=refresh_expires,
            )
            family = _SessionFamily(
                scope=scope,
                session_id=actual_session_id,
                rotation_family_id=actual_family_id,
                rotation_family_digest=family_digest,
                created_at=current_time,
                generations=[generation],
            )
            self._families[actual_session_id] = family
            self._rotation_family_ids.add(actual_family_id)
            self._digest_index[family_digest] = (
                "rotation_family",
                actual_session_id,
                0,
            )
            self._digest_index[access_digest] = (
                "access",
                actual_session_id,
                0,
            )
            self._digest_index[refresh_digest] = (
                "refresh",
                actual_session_id,
                0,
            )
            result = self._public_session(family, current_time)
            self._remember_idempotency(
                scope,
                "session_create",
                idempotency_key,
                request_digest,
                "session",
                result.to_dict(),
            )
            return result

    issue = issue_session

    def refresh_session(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        current_refresh_token_digest: str | SessionRefreshTokenDigest,
        new_access_token_digest: str | SessionAccessTokenDigest,
        new_refresh_token_digest: str | SessionRefreshTokenDigest,
        access_expires_at: datetime | str,
        idempotency_key: str,
        refresh_expires_at: datetime | str | None = None,
        now: datetime | str | None = None,
    ) -> SessionDTO:
        scope = SessionScope(tenant_id, project_id, account_id)
        current_time = self._time(now)
        presented_digest = _refresh_digest(
            "current_refresh_token_digest", current_refresh_token_digest
        )
        access_digest = _access_digest(
            "new_access_token_digest", new_access_token_digest
        )
        refresh_digest = _refresh_digest(
            "new_refresh_token_digest", new_refresh_token_digest
        )
        access_expires = self._time(access_expires_at)
        requested_refresh_expires = (
            self._time(refresh_expires_at) if refresh_expires_at is not None else None
        )
        request_digest = _fingerprint(
            {
                **scope.to_dict(),
                "current_refresh_token_digest": presented_digest,
                "new_access_token_digest": access_digest,
                "new_refresh_token_digest": refresh_digest,
                "access_expires_at": _format_timestamp(access_expires),
                "refresh_expires_at": (
                    _format_timestamp(requested_refresh_expires)
                    if requested_refresh_expires is not None
                    else None
                ),
            }
        )
        with self._lock:
            replay = self._idempotency_response(
                scope,
                "session_refresh",
                idempotency_key,
                request_digest,
                "session",
            )
            if replay is not None:
                return SessionDTO.from_public_response(replay)
            located = self._digest_index.get(presented_digest)
            if located is None or located[0] != "refresh":
                raise SessionLifecycleError(
                    "session refresh credential is unavailable",
                    code="session_not_found",
                )
            _, session_id, generation_number = located
            family = self._families[session_id]
            if family.scope != scope:
                raise SessionLifecycleError(
                    "session scope does not match",
                    code="session_scope_mismatch",
                )
            generation = family.generations[generation_number]
            if generation.status == "rotated":
                family.reuse_detected_at = family.reuse_detected_at or current_time
                self._revoke_family(
                    family, current_time, "refresh_reuse_detected"
                )
                raise SessionLifecycleError(
                    "refresh credential reuse detected; session family revoked",
                    code="session_refresh_reuse_detected",
                )
            if (
                generation.revoke_reason_code == "refresh_reuse_detected"
                or family.reuse_detected_at is not None
            ):
                raise SessionLifecycleError(
                    "refresh credential reuse detected; session family revoked",
                    code="session_refresh_reuse_detected",
                )
            if generation.status == "revoked":
                raise SessionLifecycleError(
                    "session is revoked", code="session_revoked"
                )
            if generation.status == "expired" or current_time >= generation.refresh_expires_at:
                generation.status = "expired"
                raise SessionLifecycleError(
                    "refresh credential is expired",
                    code="session_refresh_expired",
                )
            if generation is not family.current or generation.status != "active":
                raise SessionLifecycleError(
                    "session refresh credential is unavailable",
                    code="session_not_found",
                )
            next_refresh_expires = (
                requested_refresh_expires
                if requested_refresh_expires is not None
                else generation.refresh_expires_at
            )
            _validate_expirations(
                current_time, access_expires, next_refresh_expires
            )
            if next_refresh_expires > generation.refresh_expires_at:
                raise SessionLifecycleError(
                    "refresh rotation cannot extend the family lifetime"
                )
            self._assert_digests_available(access_digest, refresh_digest)
            generation.status = "rotated"
            generation.rotated_at = current_time
            next_generation = _Generation(
                generation=generation.generation + 1,
                access_token_digest=access_digest,
                refresh_token_digest=refresh_digest,
                status="active",
                assurance_level=generation.assurance_level,
                authenticated_at=generation.authenticated_at,
                created_at=current_time,
                access_expires_at=access_expires,
                refresh_expires_at=next_refresh_expires,
            )
            family.generations.append(next_generation)
            self._digest_index[access_digest] = (
                "access",
                family.session_id,
                next_generation.generation,
            )
            self._digest_index[refresh_digest] = (
                "refresh",
                family.session_id,
                next_generation.generation,
            )
            result = self._public_session(family, current_time)
            self._remember_idempotency(
                scope,
                "session_refresh",
                idempotency_key,
                request_digest,
                "session",
                result.to_dict(),
            )
            return result

    refresh = refresh_session
    rotate_refresh_token = refresh_session

    def authenticate_access(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        access_token_digest: str | SessionAccessTokenDigest,
        now: datetime | str | None = None,
    ) -> SessionDTO:
        scope = SessionScope(tenant_id, project_id, account_id)
        current_time = self._time(now)
        access_digest = _access_digest("access_token_digest", access_token_digest)
        with self._lock:
            located = self._digest_index.get(access_digest)
            if located is None or located[0] != "access":
                raise SessionLifecycleError(
                    "session access credential is unavailable",
                    code="session_not_found",
                )
            _, session_id, generation_number = located
            family = self._families[session_id]
            if family.scope != scope:
                raise SessionLifecycleError(
                    "session scope does not match",
                    code="session_scope_mismatch",
                )
            generation = family.generations[generation_number]
            if family.reuse_detected_at is not None:
                raise SessionLifecycleError(
                    "session family was revoked after refresh reuse",
                    code="session_refresh_reuse_detected",
                )
            if generation.status == "revoked":
                raise SessionLifecycleError(
                    "session is revoked", code="session_revoked"
                )
            if generation is not family.current or generation.status == "rotated":
                raise SessionLifecycleError(
                    "session access credential is unavailable",
                    code="session_revoked",
                )
            if current_time >= generation.refresh_expires_at:
                generation.status = "expired"
                raise SessionLifecycleError(
                    "session is expired", code="session_refresh_expired"
                )
            if current_time >= generation.access_expires_at:
                raise SessionLifecycleError(
                    "access credential is expired",
                    code="session_access_expired",
                )
            if generation.status != "active":
                raise SessionLifecycleError(
                    "session access credential is unavailable",
                    code="session_not_found",
                )
            return self._public_session(family, current_time)

    authenticate = authenticate_access

    def get_session(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        session_id: str,
        *,
        now: datetime | str | None = None,
    ) -> SessionDTO:
        scope = SessionScope(tenant_id, project_id, account_id)
        current_time = self._time(now)
        normalized_session_id = _identifier("session_id", session_id)
        with self._lock:
            family = self._family_for_scope(scope, normalized_session_id)
            self._expire_family(family, current_time)
            return self._public_session(family, current_time)

    def list_sessions(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        include_inactive: bool = True,
        now: datetime | str | None = None,
    ) -> tuple[SessionDTO, ...]:
        scope = SessionScope(tenant_id, project_id, account_id)
        current_time = self._time(now)
        if not isinstance(include_inactive, bool):
            raise SessionLifecycleError("include_inactive must be a boolean")
        with self._lock:
            values: list[SessionDTO] = []
            for family in self._families.values():
                if family.scope != scope:
                    continue
                self._expire_family(family, current_time)
                if include_inactive or family.current.status == "active":
                    values.append(self._public_session(family, current_time))
            values.sort(key=lambda item: (item.created_at, item.session_id))
            return tuple(values)

    def revoke_session(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        session_id: str,
        *,
        idempotency_key: str,
        reason_code: str = "user_revoked",
        now: datetime | str | None = None,
    ) -> SessionRevocationDTO:
        scope = SessionScope(tenant_id, project_id, account_id)
        normalized_session_id = _identifier("session_id", session_id)
        reason = _reason(reason_code)
        request_digest = _fingerprint(
            {**scope.to_dict(), "session_id": normalized_session_id, "reason_code": reason}
        )
        with self._lock:
            replay = self._idempotency_response(
                scope,
                "session_revoke",
                idempotency_key,
                request_digest,
                "revocation",
            )
            if replay is not None:
                return SessionRevocationDTO.from_public_response(replay)
            current_time = self._time(now)
            family = self._family_for_scope(scope, normalized_session_id)
            changed = self._revoke_family(family, current_time, reason)
            result = self._revocation_result(
                scope,
                reason,
                current_time,
                (normalized_session_id,) if changed else (),
            )
            self._remember_idempotency(
                scope,
                "session_revoke",
                idempotency_key,
                request_digest,
                "revocation",
                result.to_dict(),
            )
            return result

    revoke_one = revoke_session

    def revoke_all_sessions(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        idempotency_key: str,
        reason_code: str = "revoke_all",
        now: datetime | str | None = None,
    ) -> SessionRevocationDTO:
        scope = SessionScope(tenant_id, project_id, account_id)
        reason = _reason(reason_code)
        request_digest = _fingerprint({**scope.to_dict(), "reason_code": reason})
        with self._lock:
            replay = self._idempotency_response(
                scope,
                "session_revoke_all",
                idempotency_key,
                request_digest,
                "revocation",
            )
            if replay is not None:
                return SessionRevocationDTO.from_public_response(replay)
            current_time = self._time(now)
            revoked_ids = tuple(
                sorted(
                    family.session_id
                    for family in self._families.values()
                    if family.scope == scope
                    and self._revoke_family(family, current_time, reason)
                )
            )
            result = self._revocation_result(
                scope, reason, current_time, revoked_ids
            )
            self._remember_idempotency(
                scope,
                "session_revoke_all",
                idempotency_key,
                request_digest,
                "revocation",
                result.to_dict(),
            )
            return result

    revoke_all = revoke_all_sessions

    def invalidate_for_recovery(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        recovery_id: str,
        *,
        idempotency_key: str,
        now: datetime | str | None = None,
    ) -> SessionRevocationDTO:
        scope = SessionScope(tenant_id, project_id, account_id)
        normalized_recovery_id = _identifier("recovery_id", recovery_id)
        request_digest = _fingerprint(
            {**scope.to_dict(), "recovery_id": normalized_recovery_id}
        )
        with self._lock:
            replay = self._idempotency_response(
                scope,
                "session_recovery_invalidate",
                idempotency_key,
                request_digest,
                "revocation",
            )
            if replay is not None:
                return SessionRevocationDTO.from_public_response(replay)
            current_time = self._time(now)
            revoked_ids = tuple(
                sorted(
                    family.session_id
                    for family in self._families.values()
                    if family.scope == scope
                    and self._revoke_family(
                        family, current_time, "account_recovery"
                    )
                )
            )
            result = self._revocation_result(
                scope, "account_recovery", current_time, revoked_ids
            )
            self._remember_idempotency(
                scope,
                "session_recovery_invalidate",
                idempotency_key,
                request_digest,
                "revocation",
                result.to_dict(),
            )
            return result

    recovery_invalidate = invalidate_for_recovery

    def assert_recent_auth(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        session_id: str,
        *,
        max_age_seconds: int,
        minimum_assurance_level: str = "aal1",
        now: datetime | str | None = None,
    ) -> RecentAuthDTO:
        scope = SessionScope(tenant_id, project_id, account_id)
        normalized_session_id = _identifier("session_id", session_id)
        max_age = _bounded_int("max_age_seconds", max_age_seconds, 0, 86_400)
        minimum_assurance = _enum(
            "minimum_assurance_level",
            minimum_assurance_level,
            SESSION_ASSURANCE_LEVELS,
        )
        current_time = self._time(now)
        with self._lock:
            family = self._family_for_scope(scope, normalized_session_id)
            self._expire_family(family, current_time)
            current = family.current
            if current.status != "active" or current_time >= current.access_expires_at:
                raise SessionLifecycleError(
                    "recent authentication is required",
                    code="session_recent_auth_required",
                )
            if SESSION_ASSURANCE_LEVELS.index(current.assurance_level) < (
                SESSION_ASSURANCE_LEVELS.index(minimum_assurance)
            ):
                raise SessionLifecycleError(
                    "higher authentication assurance is required",
                    code="session_assurance_required",
                )
            valid_until = current.authenticated_at + timedelta(seconds=max_age)
            if current_time > valid_until:
                raise SessionLifecycleError(
                    "recent authentication is required",
                    code="session_recent_auth_required",
                )
            return RecentAuthDTO(
                schema_version=SESSION_LIFECYCLE_SCHEMA_VERSION,
                tenant_id=scope.tenant_id,
                project_id=scope.project_id,
                account_id=scope.account_id,
                session_id=family.session_id,
                assurance_level=current.assurance_level,
                authenticated_at=_format_timestamp(current.authenticated_at),
                valid_until=_format_timestamp(valid_until),
                recent=True,
            )

    require_recent_auth = assert_recent_auth

    def snapshot_state(self) -> dict[str, Any]:
        with self._lock:
            families = [
                self._family_snapshot(family)
                for family in sorted(
                    self._families.values(), key=lambda item: item.session_id
                )
            ]
            idempotency = []
            for key, record in sorted(self._idempotency.items()):
                tenant_id, project_id, account_id, operation, key_digest = key
                idempotency.append(
                    {
                        "tenant_id": tenant_id,
                        "project_id": project_id,
                        "account_id": account_id,
                        "operation": operation,
                        "key_digest": key_digest,
                        "request_digest": record.request_digest,
                        "response_type": record.response_type,
                        "response": deepcopy(record.response),
                    }
                )
            payload: dict[str, Any] = {
                "schema_version": SESSION_LIFECYCLE_SCHEMA_VERSION,
                "storage_mode": "digest_only",
                "families": families,
                "idempotency": idempotency,
            }
            integrity_digest = _fingerprint(payload)
            return {
                **payload,
                "integrity": {
                    "algorithm": "sha256",
                    "payload_sha256": integrity_digest,
                },
            }

    snapshot = snapshot_state

    def restore_state(self, snapshot: Mapping[str, Any]) -> None:
        try:
            restored = self._parse_snapshot(snapshot)
        except SessionLifecycleError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise SessionLifecycleError(
                "session snapshot is invalid", code="session_snapshot_invalid"
            ) from exc
        with self._lock:
            self._families = restored._families
            self._rotation_family_ids = restored._rotation_family_ids
            self._digest_index = restored._digest_index
            self._idempotency = restored._idempotency

    restore = restore_state

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> "SessionLifecycleStore":
        store = cls(clock=clock, id_factory=id_factory)
        store.restore_state(snapshot)
        return store

    def _parse_snapshot(self, snapshot: Mapping[str, Any]) -> "SessionLifecycleStore":
        if not isinstance(snapshot, Mapping):
            raise SessionLifecycleError(
                "session snapshot must be an object",
                code="session_snapshot_invalid",
            )
        _require_exact_keys(
            snapshot, _SNAPSHOT_TOP_LEVEL_KEYS, "session snapshot", snapshot=True
        )
        if snapshot.get("schema_version") != SESSION_LIFECYCLE_SCHEMA_VERSION:
            raise SessionLifecycleError(
                "session snapshot schema mismatch", code="session_snapshot_invalid"
            )
        if snapshot.get("storage_mode") != "digest_only":
            raise SessionLifecycleError(
                "session snapshot storage mode is invalid",
                code="session_snapshot_invalid",
            )
        integrity = snapshot.get("integrity")
        if not isinstance(integrity, Mapping) or set(integrity) != {
            "algorithm",
            "payload_sha256",
        }:
            raise SessionLifecycleError(
                "session snapshot integrity metadata is invalid",
                code="session_snapshot_invalid",
            )
        if integrity.get("algorithm") != "sha256":
            raise SessionLifecycleError(
                "session snapshot integrity algorithm is invalid",
                code="session_snapshot_invalid",
            )
        expected_digest = _digest(
            "payload_sha256",
            integrity.get("payload_sha256"),
            code="session_snapshot_invalid",
        )
        payload = {key: deepcopy(value) for key, value in snapshot.items() if key != "integrity"}
        if _fingerprint(payload) != expected_digest:
            raise SessionLifecycleError(
                "session snapshot integrity check failed",
                code="session_snapshot_invalid",
            )
        families_value = payload.get("families")
        idempotency_value = payload.get("idempotency")
        if not _is_sequence(families_value) or not _is_sequence(idempotency_value):
            raise SessionLifecycleError(
                "session snapshot collections are invalid",
                code="session_snapshot_invalid",
            )
        restored = SessionLifecycleStore(
            clock=self._clock, id_factory=self._id_factory
        )
        for family_payload in families_value:
            restored._restore_family(family_payload)
        for record_payload in idempotency_value:
            restored._restore_idempotency(record_payload)
        return restored

    def _restore_family(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            raise SessionLifecycleError(
                "session snapshot family is invalid", code="session_snapshot_invalid"
            )
        _require_exact_keys(
            payload, _FAMILY_SNAPSHOT_KEYS, "session snapshot family", snapshot=True
        )
        scope = SessionScope(
            payload.get("tenant_id"),
            payload.get("project_id"),
            payload.get("account_id"),
        )
        session_id = _identifier("session_id", payload.get("session_id"))
        family_id = _identifier(
            "rotation_family_id", payload.get("rotation_family_id")
        )
        family_digest = _digest(
            "rotation_family_digest",
            payload.get("rotation_family_digest"),
            code="session_snapshot_invalid",
        )
        created_at = self._time(payload.get("created_at"))
        reuse_at = self._optional_time(payload.get("reuse_detected_at"))
        generations_value = payload.get("generations")
        if not _is_sequence(generations_value) or not generations_value:
            raise SessionLifecycleError(
                "session snapshot generations are invalid",
                code="session_snapshot_invalid",
            )
        if session_id in self._families or family_id in self._rotation_family_ids:
            raise SessionLifecycleError(
                "session snapshot identifier conflict",
                code="session_snapshot_invalid",
            )
        self._assert_digests_available(family_digest, snapshot=True)
        generations: list[_Generation] = []
        previous_created_at: datetime | None = None
        for expected_generation, value in enumerate(generations_value):
            generation = self._restore_generation(value, expected_generation)
            if previous_created_at is not None and generation.created_at < previous_created_at:
                raise SessionLifecycleError(
                    "session snapshot generation order is invalid",
                    code="session_snapshot_invalid",
                )
            previous_created_at = generation.created_at
            generations.append(generation)
        if created_at != generations[0].created_at:
            raise SessionLifecycleError(
                "session snapshot creation time mismatch",
                code="session_snapshot_invalid",
            )
        if any(item.status == "active" for item in generations[:-1]):
            raise SessionLifecycleError(
                "session snapshot has multiple active generations",
                code="session_snapshot_invalid",
            )
        if reuse_at is not None and any(
            item.status != "revoked"
            or item.revoke_reason_code != "refresh_reuse_detected"
            for item in generations
        ):
            raise SessionLifecycleError(
                "session snapshot reuse state is invalid",
                code="session_snapshot_invalid",
            )
        family = _SessionFamily(
            scope=scope,
            session_id=session_id,
            rotation_family_id=family_id,
            rotation_family_digest=family_digest,
            created_at=created_at,
            generations=generations,
            reuse_detected_at=reuse_at,
        )
        self._families[session_id] = family
        self._rotation_family_ids.add(family_id)
        self._digest_index[family_digest] = ("rotation_family", session_id, 0)
        for generation in generations:
            self._assert_digests_available(
                generation.access_token_digest,
                generation.refresh_token_digest,
                snapshot=True,
            )
            self._digest_index[generation.access_token_digest] = (
                "access",
                session_id,
                generation.generation,
            )
            self._digest_index[generation.refresh_token_digest] = (
                "refresh",
                session_id,
                generation.generation,
            )

    def _restore_generation(self, payload: Any, expected: int) -> _Generation:
        if not isinstance(payload, Mapping):
            raise SessionLifecycleError(
                "session snapshot generation is invalid",
                code="session_snapshot_invalid",
            )
        _require_exact_keys(
            payload,
            _GENERATION_SNAPSHOT_KEYS,
            "session snapshot generation",
            snapshot=True,
        )
        generation_number = _non_negative_int(
            "generation", payload.get("generation"), code="session_snapshot_invalid"
        )
        if generation_number != expected:
            raise SessionLifecycleError(
                "session snapshot generation sequence is invalid",
                code="session_snapshot_invalid",
            )
        status = _enum(
            "status",
            payload.get("status"),
            SESSION_LIFECYCLE_STATUSES,
            code="session_snapshot_invalid",
        )
        assurance = _enum(
            "assurance_level",
            payload.get("assurance_level"),
            SESSION_ASSURANCE_LEVELS,
            code="session_snapshot_invalid",
        )
        authenticated = self._time(payload.get("authenticated_at"))
        created = self._time(payload.get("created_at"))
        access_expires = self._time(payload.get("access_expires_at"))
        refresh_expires = self._time(payload.get("refresh_expires_at"))
        if authenticated > created or access_expires > refresh_expires:
            raise SessionLifecycleError(
                "session snapshot time ordering is invalid",
                code="session_snapshot_invalid",
            )
        rotated_at = self._optional_time(payload.get("rotated_at"))
        revoked_at = self._optional_time(payload.get("revoked_at"))
        reason = _optional_reason(payload.get("revoke_reason_code"))
        if status == "rotated" and rotated_at is None:
            raise SessionLifecycleError(
                "session snapshot rotation state is invalid",
                code="session_snapshot_invalid",
            )
        if status == "revoked" and (revoked_at is None or reason is None):
            raise SessionLifecycleError(
                "session snapshot revocation state is invalid",
                code="session_snapshot_invalid",
            )
        if status != "revoked" and (revoked_at is not None or reason is not None):
            raise SessionLifecycleError(
                "session snapshot revocation state is invalid",
                code="session_snapshot_invalid",
            )
        return _Generation(
            generation=generation_number,
            access_token_digest=_digest(
                "access_token_digest",
                payload.get("access_token_digest"),
                code="session_snapshot_invalid",
            ),
            refresh_token_digest=_digest(
                "refresh_token_digest",
                payload.get("refresh_token_digest"),
                code="session_snapshot_invalid",
            ),
            status=status,
            assurance_level=assurance,
            authenticated_at=authenticated,
            created_at=created,
            access_expires_at=access_expires,
            refresh_expires_at=refresh_expires,
            rotated_at=rotated_at,
            revoked_at=revoked_at,
            revoke_reason_code=reason,
        )

    def _restore_idempotency(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            raise SessionLifecycleError(
                "session snapshot idempotency record is invalid",
                code="session_snapshot_invalid",
            )
        _require_exact_keys(
            payload,
            _IDEMPOTENCY_SNAPSHOT_KEYS,
            "session snapshot idempotency record",
            snapshot=True,
        )
        scope = SessionScope(
            payload.get("tenant_id"),
            payload.get("project_id"),
            payload.get("account_id"),
        )
        operation = _identifier("operation", payload.get("operation"))
        key_digest = _digest(
            "key_digest", payload.get("key_digest"), code="session_snapshot_invalid"
        )
        request_digest = _digest(
            "request_digest",
            payload.get("request_digest"),
            code="session_snapshot_invalid",
        )
        response_type = str(payload.get("response_type") or "")
        response = payload.get("response")
        if not isinstance(response, Mapping):
            raise SessionLifecycleError(
                "session snapshot idempotency response is invalid",
                code="session_snapshot_invalid",
            )
        if response_type == "session":
            SessionDTO.from_public_response(response)
        elif response_type == "revocation":
            SessionRevocationDTO.from_public_response(response)
        else:
            raise SessionLifecycleError(
                "session snapshot idempotency response type is invalid",
                code="session_snapshot_invalid",
            )
        key = (*scope.to_dict().values(), operation, key_digest)
        if key in self._idempotency:
            raise SessionLifecycleError(
                "session snapshot idempotency key is duplicated",
                code="session_snapshot_invalid",
            )
        self._idempotency[key] = _IdempotencyRecord(
            request_digest=request_digest,
            response_type=response_type,
            response=deepcopy(dict(response)),
        )

    def _family_snapshot(self, family: _SessionFamily) -> dict[str, Any]:
        return {
            **family.scope.to_dict(),
            "session_id": family.session_id,
            "rotation_family_id": family.rotation_family_id,
            "rotation_family_digest": family.rotation_family_digest,
            "created_at": _format_timestamp(family.created_at),
            "reuse_detected_at": (
                _format_timestamp(family.reuse_detected_at)
                if family.reuse_detected_at is not None
                else None
            ),
            "generations": [
                {
                    "generation": generation.generation,
                    "access_token_digest": generation.access_token_digest,
                    "refresh_token_digest": generation.refresh_token_digest,
                    "status": generation.status,
                    "assurance_level": generation.assurance_level,
                    "authenticated_at": _format_timestamp(
                        generation.authenticated_at
                    ),
                    "created_at": _format_timestamp(generation.created_at),
                    "access_expires_at": _format_timestamp(
                        generation.access_expires_at
                    ),
                    "refresh_expires_at": _format_timestamp(
                        generation.refresh_expires_at
                    ),
                    "rotated_at": (
                        _format_timestamp(generation.rotated_at)
                        if generation.rotated_at is not None
                        else None
                    ),
                    "revoked_at": (
                        _format_timestamp(generation.revoked_at)
                        if generation.revoked_at is not None
                        else None
                    ),
                    "revoke_reason_code": generation.revoke_reason_code,
                }
                for generation in family.generations
            ],
        }

    def _public_session(
        self, family: _SessionFamily, current_time: datetime
    ) -> SessionDTO:
        current = family.current
        last_rotated = next(
            (
                item.rotated_at
                for item in reversed(family.generations[:-1])
                if item.rotated_at is not None
            ),
            None,
        )
        active = current.status == "active"
        result = SessionDTO(
            schema_version=SESSION_LIFECYCLE_SCHEMA_VERSION,
            tenant_id=family.scope.tenant_id,
            project_id=family.scope.project_id,
            account_id=family.scope.account_id,
            session_id=family.session_id,
            rotation_family_id=family.rotation_family_id,
            generation=current.generation,
            status=current.status,
            assurance_level=current.assurance_level,
            authenticated_at=_format_timestamp(current.authenticated_at),
            created_at=_format_timestamp(family.created_at),
            access_expires_at=_format_timestamp(current.access_expires_at),
            refresh_expires_at=_format_timestamp(current.refresh_expires_at),
            last_rotated_at=(
                _format_timestamp(last_rotated) if last_rotated is not None else None
            ),
            revoked_at=(
                _format_timestamp(current.revoked_at)
                if current.revoked_at is not None
                else None
            ),
            revoke_reason_code=current.revoke_reason_code,
            access_token_present=active and current_time < current.access_expires_at,
            refresh_token_present=active and current_time < current.refresh_expires_at,
        )
        assert_public_session_payload(result.to_dict())
        return result

    def _revocation_result(
        self,
        scope: SessionScope,
        reason: str,
        revoked_at: datetime,
        session_ids: tuple[str, ...],
    ) -> SessionRevocationDTO:
        return SessionRevocationDTO(
            schema_version=SESSION_LIFECYCLE_SCHEMA_VERSION,
            tenant_id=scope.tenant_id,
            project_id=scope.project_id,
            account_id=scope.account_id,
            reason_code=reason,
            revoked_at=_format_timestamp(revoked_at),
            revoked_session_ids=session_ids,
            revoked_count=len(session_ids),
        )

    @staticmethod
    def _revoke_family(
        family: _SessionFamily, revoked_at: datetime, reason: str
    ) -> bool:
        changed = any(item.status != "revoked" for item in family.generations)
        if not changed:
            return False
        for generation in family.generations:
            generation.status = "revoked"
            generation.revoked_at = revoked_at
            generation.revoke_reason_code = reason
        return True

    @staticmethod
    def _expire_family(family: _SessionFamily, current_time: datetime) -> None:
        current = family.current
        if current.status == "active" and current_time >= current.refresh_expires_at:
            current.status = "expired"

    def _family_for_scope(
        self, scope: SessionScope, session_id: str
    ) -> _SessionFamily:
        family = self._families.get(session_id)
        if family is None:
            raise SessionLifecycleError(
                "session is unavailable", code="session_not_found"
            )
        if family.scope != scope:
            raise SessionLifecycleError(
                "session scope does not match", code="session_scope_mismatch"
            )
        return family

    def _assert_digests_available(
        self, *digests: str, snapshot: bool = False
    ) -> None:
        if len(set(digests)) != len(digests) or any(
            digest in self._digest_index for digest in digests
        ):
            raise SessionLifecycleError(
                "session digest conflict",
                code=("session_snapshot_invalid" if snapshot else "session_digest_conflict"),
            )

    def _idempotency_response(
        self,
        scope: SessionScope,
        operation: str,
        key: str,
        request_digest: str,
        response_type: str,
    ) -> dict[str, Any] | None:
        idempotency_digest = _idempotency_digest(key)
        record = self._idempotency.get(
            (
                scope.tenant_id,
                scope.project_id,
                scope.account_id,
                operation,
                idempotency_digest,
            )
        )
        if record is None:
            return None
        if (
            record.request_digest != request_digest
            or record.response_type != response_type
        ):
            raise SessionLifecycleError(
                "idempotency key was used with a different request",
                code="session_idempotency_conflict",
            )
        return deepcopy(record.response)

    def _remember_idempotency(
        self,
        scope: SessionScope,
        operation: str,
        key: str,
        request_digest: str,
        response_type: str,
        response: Mapping[str, Any],
    ) -> None:
        assert_public_session_payload(response)
        self._idempotency[
            (
                scope.tenant_id,
                scope.project_id,
                scope.account_id,
                operation,
                _idempotency_digest(key),
            )
        ] = _IdempotencyRecord(
            request_digest=request_digest,
            response_type=response_type,
            response=deepcopy(dict(response)),
        )

    def _new_id(self, prefix: str, existing: set[str]) -> str:
        for _ in range(16):
            candidate = _identifier(f"{prefix}_id", self._id_factory(prefix))
            if candidate not in existing:
                return candidate
        raise SessionLifecycleError("identifier allocation failed")

    def _time(
        self,
        value: datetime | str | None,
        *,
        default: datetime | None = None,
    ) -> datetime:
        if value is None:
            resolved = default if default is not None else self._clock()
        else:
            resolved = value
        return _coerce_timestamp(resolved)

    def _optional_time(self, value: Any) -> datetime | None:
        return None if value is None else self._time(value)


SessionLifecycleMemoryStore = SessionLifecycleStore


class SessionLifecycleClient:
    """Typed public client; credentials remain in transport-owned secure channels."""

    def __init__(self, base_url: str, *, transport: SessionTransport) -> None:
        normalized = str(base_url or "").strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise SessionLifecycleError("base_url must be HTTP or HTTPS")
        self.base_url = normalized
        self._transport = transport

    def issue_session(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        access_token_digest: str | SessionAccessTokenDigest,
        refresh_token_digest: str | SessionRefreshTokenDigest,
        access_expires_at: datetime | str,
        refresh_expires_at: datetime | str,
        rotation_family_digest: str | SessionRotationFamilyDigest | None = None,
        assurance_level: str = "aal1",
    ) -> SessionDTO:
        payload: dict[str, Any] = {
            "tenant_id": _identifier("tenant_id", tenant_id),
            "access_token_digest": _access_digest(
                "access_token_digest", access_token_digest
            ),
            "refresh_token_digest": _refresh_digest(
                "refresh_token_digest", refresh_token_digest
            ),
            "access_expires_at": _timestamp_text(
                "access_expires_at", access_expires_at
            ),
            "refresh_expires_at": _timestamp_text(
                "refresh_expires_at", refresh_expires_at
            ),
            "assurance_level": _enum(
                "assurance_level", assurance_level, SESSION_ASSURANCE_LEVELS
            ),
        }
        if rotation_family_digest is not None:
            payload["rotation_family_digest"] = _rotation_family_digest(
                "rotation_family_digest", rotation_family_digest
            )
        return SessionDTO.from_public_response(
            self._request(
                "POST", session_collection_route(project_id, account_id), payload
            )
        )

    def authenticate_access_token(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        access_token_digest: str | SessionAccessTokenDigest,
    ) -> SessionDTO:
        return SessionDTO.from_public_response(
            self._request(
                "POST",
                session_authenticate_route(project_id, account_id),
                {
                    "tenant_id": _identifier("tenant_id", tenant_id),
                    "access_token_digest": _access_digest(
                        "access_token_digest", access_token_digest
                    ),
                },
            )
        )

    def rotate_refresh_token(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        refresh_token_digest: str | SessionRefreshTokenDigest,
        next_access_token_digest: str | SessionAccessTokenDigest,
        next_refresh_token_digest: str | SessionRefreshTokenDigest,
        access_expires_at: datetime | str,
        refresh_expires_at: datetime | str,
    ) -> SessionDTO:
        return SessionDTO.from_public_response(
            self._request(
                "POST",
                session_refresh_route(project_id, account_id),
                {
                    "tenant_id": _identifier("tenant_id", tenant_id),
                    "refresh_token_digest": _refresh_digest(
                        "refresh_token_digest", refresh_token_digest
                    ),
                    "next_access_token_digest": _access_digest(
                        "next_access_token_digest", next_access_token_digest
                    ),
                    "next_refresh_token_digest": _refresh_digest(
                        "next_refresh_token_digest", next_refresh_token_digest
                    ),
                    "access_expires_at": _timestamp_text(
                        "access_expires_at", access_expires_at
                    ),
                    "refresh_expires_at": _timestamp_text(
                        "refresh_expires_at", refresh_expires_at
                    ),
                },
            )
        )

    def list_sessions(
        self, tenant_id: str, project_id: str, account_id: str
    ) -> tuple[SessionDTO, ...]:
        payload = self._request(
            "GET",
            session_collection_route(project_id, account_id),
            {"tenant_id": _identifier("tenant_id", tenant_id)},
        )
        values = payload.get("sessions")
        if not _is_sequence(values) or any(not isinstance(item, Mapping) for item in values):
            raise SessionLifecycleError("sessions response must be an array")
        return tuple(SessionDTO.from_public_response(item) for item in values)

    def get_session(
        self, tenant_id: str, project_id: str, account_id: str, session_id: str
    ) -> SessionDTO:
        return SessionDTO.from_public_response(
            self._request(
                "GET",
                session_route(project_id, account_id, session_id),
                {"tenant_id": _identifier("tenant_id", tenant_id)},
            )
        )

    def create_session(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        credential_id: str,
        assurance_level: str = "aal1",
        idempotency_key: str,
    ) -> SessionDTO:
        return SessionDTO.from_public_response(
            self._request(
                "POST",
                session_collection_route(project_id, account_id),
                {
                    "tenant_id": _identifier("tenant_id", tenant_id),
                    "credential_id": _identifier("credential_id", credential_id),
                    "assurance_level": _enum(
                        "assurance_level",
                        assurance_level,
                        SESSION_ASSURANCE_LEVELS,
                    ),
                    "idempotency_key": _identifier(
                        "idempotency_key", idempotency_key
                    ),
                },
            )
        )

    def refresh_session(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        session_id: str,
        *,
        idempotency_key: str,
    ) -> SessionDTO:
        return SessionDTO.from_public_response(
            self._request(
                "POST",
                session_refresh_route(project_id, account_id),
                {
                    "tenant_id": _identifier("tenant_id", tenant_id),
                    "session_id": _identifier("session_id", session_id),
                    "idempotency_key": _identifier("idempotency_key", idempotency_key),
                },
            )
        )

    def revoke_session(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        session_id: str,
        *,
        idempotency_key: str,
        reason_code: str = "user_revoked",
    ) -> SessionRevocationDTO:
        return SessionRevocationDTO.from_public_response(
            self._request(
                "POST",
                session_revoke_route(project_id, account_id, session_id),
                {
                    "tenant_id": _identifier("tenant_id", tenant_id),
                    "idempotency_key": _identifier(
                        "idempotency_key", idempotency_key
                    ),
                    "reason_code": _reason(reason_code),
                },
            )
        )

    def revoke_all_sessions(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        *,
        idempotency_key: str,
        reason_code: str = "revoke_all",
    ) -> SessionRevocationDTO:
        return SessionRevocationDTO.from_public_response(
            self._request(
                "POST",
                session_revoke_all_route(project_id, account_id),
                {
                    "tenant_id": _identifier("tenant_id", tenant_id),
                    "idempotency_key": _identifier(
                        "idempotency_key", idempotency_key
                    ),
                    "reason_code": _reason(reason_code),
                },
            )
        )

    def assert_recent_auth(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        session_id: str,
        *,
        max_age_seconds: int,
        minimum_assurance_level: str = "aal1",
    ) -> RecentAuthDTO:
        return RecentAuthDTO.from_public_response(
            self._request(
                "POST",
                session_recent_auth_route(project_id, account_id, session_id),
                {
                    "tenant_id": _identifier("tenant_id", tenant_id),
                    "max_age_seconds": _bounded_int(
                        "max_age_seconds", max_age_seconds, 0, 86_400
                    ),
                    "minimum_assurance_level": _enum(
                        "minimum_assurance_level",
                        minimum_assurance_level,
                        SESSION_ASSURANCE_LEVELS,
                    ),
                },
            )
        )

    def invalidate_for_recovery(
        self,
        tenant_id: str,
        project_id: str,
        account_id: str,
        recovery_id: str,
        *,
        idempotency_key: str,
    ) -> SessionRevocationDTO:
        return SessionRevocationDTO.from_public_response(
            self._request(
                "POST",
                session_recovery_invalidation_route(project_id, account_id),
                {
                    "tenant_id": _identifier("tenant_id", tenant_id),
                    "recovery_id": _identifier("recovery_id", recovery_id),
                    "idempotency_key": _identifier("idempotency_key", idempotency_key),
                },
            )
        )

    def invalidate_sessions_for_recovery(
        self, tenant_id: str, project_id: str, account_id: str
    ) -> SessionRevocationDTO:
        return SessionRevocationDTO.from_public_response(
            self._request(
                "POST",
                session_recovery_invalidation_route(project_id, account_id),
                {"tenant_id": _identifier("tenant_id", tenant_id)},
            )
        )

    require_recent_authentication = assert_recent_auth

    def _request(
        self, method: str, path: str, payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        try:
            response = self._transport(method, f"{self.base_url}{path}", dict(payload))
        except SessionLifecycleError:
            raise
        except Exception as exc:
            raise SessionLifecycleError(
                "session transport failed", code="session_transport_failed"
            ) from exc
        if not isinstance(response, Mapping):
            raise SessionLifecycleError(
                "session transport must return an object",
                code="session_transport_failed",
            )
        error = response.get("error")
        if isinstance(error, Mapping):
            if not set(error).issubset({"code", "message", "retryable", "status"}):
                raise SessionLifecycleError(
                    "session error payload contains unsupported fields"
                )
            code = str(error.get("code") or "")
            if code not in SESSION_LIFECYCLE_ERROR_CODES:
                raise SessionLifecycleError(
                    "session transport returned an unknown error",
                    code="session_transport_failed",
                )
            message = str(error.get("message") or code)
            raise SessionLifecycleError(message, code=code)
        assert_public_session_payload(response)
        result = response.get("result") if isinstance(response.get("result"), Mapping) else response
        assert_public_session_payload(result)
        return result


def session_collection_route(project_id: str, account_id: str) -> str:
    return (
        f"/v1/projects/{_route_segment('project_id', project_id)}"
        f"/accounts/{_route_segment('account_id', account_id)}/sessions"
    )


def session_route(project_id: str, account_id: str, session_id: str) -> str:
    return (
        f"{session_collection_route(project_id, account_id)}/"
        f"{_route_segment('session_id', session_id)}"
    )


def session_authenticate_route(project_id: str, account_id: str) -> str:
    return f"{session_collection_route(project_id, account_id)}/authenticate"


def session_refresh_route(project_id: str, account_id: str) -> str:
    return f"{session_collection_route(project_id, account_id)}/refresh"


def browser_session_refresh_route(project_id: str, account_id: str) -> str:
    return (
        f"/v1/projects/{_route_segment('project_id', project_id)}"
        f"/accounts/{_route_segment('account_id', account_id)}"
        "/browser-sessions/refresh"
    )


def session_revoke_route(
    project_id: str, account_id: str, session_id: str
) -> str:
    return f"{session_route(project_id, account_id, session_id)}/revoke"


def session_revoke_all_route(project_id: str, account_id: str) -> str:
    return f"{session_collection_route(project_id, account_id)}/revoke-all"


def session_recent_auth_route(
    project_id: str, account_id: str, session_id: str
) -> str:
    return f"{session_route(project_id, account_id, session_id)}/recent-auth"


def session_recovery_invalidation_route(project_id: str, account_id: str) -> str:
    return f"{session_collection_route(project_id, account_id)}/recovery-invalidate"


session_recovery_invalidate_route = session_recovery_invalidation_route
SessionLifecycleHttpClient = SessionLifecycleClient


def assert_public_session_payload(payload: Mapping[str, Any]) -> None:
    """Reject token material, token digests, and secret aliases recursively."""

    if not isinstance(payload, Mapping):
        raise SessionLifecycleError("public session payload must be an object")

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for raw_key, item in value.items():
                if not isinstance(raw_key, str):
                    raise SessionLifecycleError("public session keys must be strings")
                canonical = _canonical_key(raw_key)
                forbidden_suffix = canonical.endswith(
                    ("token", "tokendigest", "secret", "password")
                )
                if canonical not in _ALLOWED_PUBLIC_CREDENTIAL_MARKERS and (
                    canonical in _FORBIDDEN_PUBLIC_CANONICAL_KEYS or forbidden_suffix
                ):
                    raise SessionLifecycleError(
                        "public session payload contains forbidden credential material",
                        code="session_forbidden_secret",
                    )
                visit(item)
        elif _is_sequence(value):
            for item in value:
                visit(item)
        elif isinstance(value, (bytes, bytearray, memoryview)):
            raise SessionLifecycleError(
                "public session payload contains binary credential material",
                code="session_forbidden_secret",
            )
        elif isinstance(value, str) and any(
            pattern.search(value) for pattern in _CREDENTIAL_VALUE_PATTERNS
        ):
            raise SessionLifecycleError(
                "public session payload contains forbidden credential material",
                code="session_forbidden_secret",
            )

    visit(payload)


def _redact_message(value: Any) -> str:
    message = str(value or "session lifecycle request failed").strip()
    for pattern in _CREDENTIAL_VALUE_PATTERNS:
        message = pattern.sub("[redacted]", message)
    return message[:500] or "session lifecycle request failed"


def _canonical_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _identifier(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise SessionLifecycleError(f"{name} must be a non-empty opaque identifier")
    return normalized


def _route_segment(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 255:
        raise SessionLifecycleError(f"{name} must be a non-empty route identifier")
    return quote(normalized, safe="")


def _digest(name: str, value: Any, *, code: str = "session_invalid_request") -> str:
    normalized = str(value or "").strip()
    if not _DIGEST_PATTERN.fullmatch(normalized):
        raise SessionLifecycleError(f"{name} must be a lowercase sha256 digest", code=code)
    return normalized


def _typed_digest(
    name: str,
    value: Any,
    expected_type: type[_TypedSessionDigest],
) -> str:
    if isinstance(value, expected_type):
        return value.for_storage()
    if isinstance(value, _TypedSessionDigest):
        raise SessionLifecycleError(f"{name} token class is invalid")
    return _digest(name, value)


def _access_digest(name: str, value: Any) -> str:
    return _typed_digest(name, value, SessionAccessTokenDigest)


def _refresh_digest(name: str, value: Any) -> str:
    return _typed_digest(name, value, SessionRefreshTokenDigest)


def _rotation_family_digest(name: str, value: Any) -> str:
    return _typed_digest(name, value, SessionRotationFamilyDigest)


def _session_token_material(value: Any) -> bytearray:
    if not isinstance(value, str):
        raise SessionLifecycleError("session token material must be an opaque string")
    try:
        material = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise SessionLifecycleError(
            "session token material must be printable ASCII"
        ) from error
    if not 1 <= len(material) <= 4096 or any(
        character < 0x21 or character > 0x7E for character in material
    ):
        raise SessionLifecycleError(
            "session token material must be bounded printable ASCII"
        )
    return bytearray(material)


def _wipe_bytearray(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0


def _idempotency_digest(value: Any) -> str:
    normalized = _identifier("idempotency_key", value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _enum(
    name: str,
    value: Any,
    allowed: Sequence[str],
    *,
    code: str = "session_invalid_request",
) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise SessionLifecycleError(f"{name} is invalid", code=code)
    return normalized


def _reason(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if (
        normalized not in SESSION_REVOCATION_REASONS
        or not _REASON_PATTERN.fullmatch(normalized)
    ):
        raise SessionLifecycleError("reason_code is invalid")
    return normalized


def _optional_reason(value: Any) -> str | None:
    return None if value is None else _reason(value)


def _boolean(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise SessionLifecycleError(f"{name} must be a boolean")
    return value


def _non_negative_int(
    name: str, value: Any, *, code: str = "session_invalid_request"
) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SessionLifecycleError(f"{name} must be a non-negative integer", code=code)
    return value


def _bounded_int(name: str, value: Any, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise SessionLifecycleError(
            f"{name} must be an integer from {minimum} through {maximum}"
        )
    return value


def _coerce_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise SessionLifecycleError("timestamp must be ISO-8601") from exc
    else:
        raise SessionLifecycleError("timestamp must be ISO-8601")
    if parsed.utcoffset() is None:
        raise SessionLifecycleError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    return _coerce_timestamp(value)


def _format_timestamp(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return normalized.replace("+00:00", "Z")


def _timestamp_text(name: str, value: Any) -> str:
    try:
        return _format_timestamp(_coerce_timestamp(value))
    except SessionLifecycleError as exc:
        raise SessionLifecycleError(f"{name} must be an ISO-8601 timestamp") from exc


def _optional_timestamp_text(name: str, value: Any) -> str | None:
    return None if value is None else _timestamp_text(name, value)


def _validate_expirations(
    current_time: datetime, access_expires_at: datetime, refresh_expires_at: datetime
) -> None:
    if access_expires_at <= current_time:
        raise SessionLifecycleError("access expiration must be in the future")
    if refresh_expires_at <= access_expires_at:
        raise SessionLifecycleError("refresh expiration must follow access expiration")


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_exact_keys(
    payload: Mapping[str, Any],
    expected: Sequence[str] | set[str] | frozenset[str],
    name: str,
    *,
    snapshot: bool = False,
) -> None:
    if set(payload) != set(expected):
        raise SessionLifecycleError(
            f"{name} fields are invalid",
            code=("session_snapshot_invalid" if snapshot else "session_invalid_request"),
        )


def _identifier_sequence(name: str, value: Any) -> tuple[str, ...]:
    if not _is_sequence(value):
        raise SessionLifecycleError(f"{name} must be an array")
    result = tuple(_identifier(name, item) for item in value)
    if len(result) != len(set(result)):
        raise SessionLifecycleError(f"{name} must not contain duplicates")
    return result


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray, memoryview)
    )


__all__ = [
    "SESSION_ASSURANCE_LEVELS",
    "SESSION_LIFECYCLE_ERROR_CODES",
    "SESSION_LIFECYCLE_SCHEMA_VERSION",
    "SESSION_LIFECYCLE_STATUSES",
    "SESSION_REVOCATION_REASONS",
    "RecentAuthDTO",
    "SessionDTO",
    "SessionLifecycleClient",
    "SessionLifecycleError",
    "SessionLifecycleHttpClient",
    "SessionLifecycleMemoryStore",
    "SessionLifecycleStore",
    "SessionPublicDTO",
    "SessionRevocationDTO",
    "SessionScope",
    "assert_public_session_payload",
    "session_collection_route",
    "session_authenticate_route",
    "session_lifecycle_contract_manifest",
    "session_recent_auth_route",
    "session_recovery_invalidation_route",
    "session_recovery_invalidate_route",
    "session_refresh_route",
    "session_revoke_all_route",
    "session_revoke_route",
    "session_route",
]
