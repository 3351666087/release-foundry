from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, urlparse

ACCOUNT_CONNECTION_SCHEMA_VERSION = "ashr.clone.account_connection.v1"
ACCOUNT_CONNECTION_PROVIDERS = ("github", "google")
GOOGLE_ACCOUNT_CONNECTION_SCOPES = ("openid", "email", "profile")
GOOGLE_OIDC_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

ACCOUNT_CONNECTION_ERROR_CODES = (
    "invalid_oauth_binding",
    "invalid_oauth_callback",
    "invalid_oauth_state",
    "oauth_binding_mismatch",
    "oauth_connection_not_found",
    "oauth_credentials_unavailable",
    "oauth_provider_error",
    "oauth_provider_revoke_failed",
    "oauth_reconnect_revoke_failed",
    "oauth_secret_store_failed",
    "oauth_secret_resolve_failed",
    "oauth_secret_delete_failed",
    "oauth_connection_store_failed",
    "oauth_disconnect_failed",
    "oidc_issuer_mismatch",
    "oidc_audience_mismatch",
    "oidc_nonce_mismatch",
    "oauth_email_unverified",
)

_FORBIDDEN_PUBLIC_KEYS = {
    "access_token",
    "authorization_code",
    "client_secret",
    "code_verifier",
    "id_token",
    "nonce",
    "refresh_token",
    "state",
    "provider_subject_sha256",
    "subject_digest",
    "identifier_sha256",
    "token",
    "token_ref",
}


class AccountConnectionContractError(ValueError):
    pass


def normalize_account_connection_provider(provider: str) -> str:
    value = str(provider or "").strip().lower()
    if value not in ACCOUNT_CONNECTION_PROVIDERS:
        raise AccountConnectionContractError(
            f"account connection provider must be one of: {', '.join(ACCOUNT_CONNECTION_PROVIDERS)}"
        )
    return value


def account_connection_contract_manifest() -> dict[str, Any]:
    return {
        "schema_version": ACCOUNT_CONNECTION_SCHEMA_VERSION,
        "providers": list(ACCOUNT_CONNECTION_PROVIDERS),
        "google": {
            "authorization_scopes": list(GOOGLE_ACCOUNT_CONNECTION_SCOPES),
            "issuer_allowlist": list(GOOGLE_OIDC_ISSUERS),
            "issuer_validation": True,
            "audience_validation": True,
            "nonce_validation": True,
            "verified_email_required": True,
        },
        "durability": {
            "transaction_store_required": True,
            "atomic_state_consumption_required": True,
            "connection_store_required": True,
            "opaque_token_reference_store_required": True,
            "revocation_outbox_required": True,
            "reconnect_revokes_previous_credential": True,
        },
        "public_response": {
            "raw_authorization_code_present": False,
            "raw_state_present": False,
            "raw_nonce_present": False,
            "raw_token_present": False,
            "client_secret_present": False,
        },
        "stable_error_codes": list(ACCOUNT_CONNECTION_ERROR_CODES),
    }


@dataclass(frozen=True)
class AccountConnectionBinding:
    tenant_id: str
    project_id: str
    account_id: str
    provider: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _required_identifier("tenant_id", self.tenant_id))
        object.__setattr__(self, "project_id", _required_identifier("project_id", self.project_id))
        object.__setattr__(self, "account_id", _required_identifier("account_id", self.account_id))
        object.__setattr__(self, "provider", normalize_account_connection_provider(self.provider))

    def request_payload(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "account_id": self.account_id,
            "provider": self.provider,
        }


@dataclass(frozen=True)
class AccountConnectionStart:
    schema_version: str
    provider: str
    authorize_url: str
    expires_at: str

    @classmethod
    def from_public_response(
        cls,
        payload: Mapping[str, Any],
        *,
        expected_provider: str,
        expected_google_audience: str | None = None,
    ) -> "AccountConnectionStart":
        _assert_public_safe(payload)
        provider = normalize_account_connection_provider(str(payload.get("provider") or ""))
        if provider != normalize_account_connection_provider(expected_provider):
            raise AccountConnectionContractError("account connection response provider mismatch")
        schema_version = str(payload.get("schema_version") or "")
        if not schema_version:
            raise AccountConnectionContractError("account connection response schema_version is required")
        authorize_url = _https_url("authorize_url", payload.get("authorize_url"))
        expires_at = _timestamp("expires_at", payload.get("expires_at"))
        if provider == "google":
            _validate_google_authorize_url(authorize_url, expected_audience=expected_google_audience)
        return cls(schema_version, provider, authorize_url, expires_at)

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "authorize_url": self.authorize_url,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class AccountConnection:
    schema_version: str
    provider: str
    account_id: str
    credential_id: str
    provider_subject_present: bool
    email_present: bool
    email_verified: bool
    connected_at: str
    disconnected_at: str | None = None
    display_name: str | None = None
    provider_login: str | None = None

    @classmethod
    def from_public_response(
        cls,
        payload: Mapping[str, Any],
        *,
        expected_provider: str,
        require_verified_email: bool | None = None,
    ) -> "AccountConnection":
        _assert_public_safe(payload)
        provider = normalize_account_connection_provider(str(payload.get("provider") or expected_provider))
        if provider != normalize_account_connection_provider(expected_provider):
            raise AccountConnectionContractError("account connection provider mismatch")
        email_present = _required_bool(payload, "email_present")
        email_verified = _required_bool(payload, "email_verified")
        must_verify = provider == "google" if require_verified_email is None else require_verified_email
        if must_verify and (not email_present or not email_verified):
            raise AccountConnectionContractError("oauth_email_unverified")
        credential_id = _required_identifier("credential_id", payload.get("credential_id"))
        provider_subject_present = _required_bool(payload, "provider_subject_present")
        if not provider_subject_present:
            raise AccountConnectionContractError(
                "provider_subject_present must be true for an account connection"
            )
        disconnected = payload.get("disconnected_at")
        display_name = _public_display_text(payload.get("display_name"))
        provider_login = _public_display_text(
            payload.get("provider_login") or payload.get(f"{provider}_login")
        )
        return cls(
            schema_version=str(payload.get("schema_version") or ACCOUNT_CONNECTION_SCHEMA_VERSION),
            provider=provider,
            account_id=_required_identifier("account_id", payload.get("account_id")),
            credential_id=credential_id,
            provider_subject_present=provider_subject_present,
            email_present=email_present,
            email_verified=email_verified,
            connected_at=_timestamp("connected_at", payload.get("connected_at")),
            disconnected_at=_timestamp("disconnected_at", disconnected) if disconnected else None,
            display_name=display_name,
            provider_login=provider_login,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "account_id": self.account_id,
            "credential_id": self.credential_id,
            "provider_subject_present": self.provider_subject_present,
            "display_name": self.display_name,
            "provider_login": self.provider_login,
            "email_present": self.email_present,
            "email_verified": self.email_verified,
            "connected_at": self.connected_at,
            "disconnected_at": self.disconnected_at,
        }


@dataclass(frozen=True)
class AccountConnectionDisconnect:
    schema_version: str
    provider: str
    disconnected: bool
    connection: AccountConnection
    revocation_status: str

    @classmethod
    def from_public_response(
        cls, payload: Mapping[str, Any], *, expected_provider: str
    ) -> "AccountConnectionDisconnect":
        _assert_public_safe(payload)
        provider = normalize_account_connection_provider(str(payload.get("provider") or expected_provider))
        if provider != normalize_account_connection_provider(expected_provider):
            raise AccountConnectionContractError("disconnect response provider mismatch")
        connection_payload = payload.get("connection")
        if not isinstance(connection_payload, Mapping):
            raise AccountConnectionContractError("disconnect response connection is required")
        connection = AccountConnection.from_public_response(
            connection_payload, expected_provider=provider, require_verified_email=False
        )
        disconnected = _required_bool(payload, "disconnected")
        revocation_status = str(payload.get("revocation_status") or ("revoked" if disconnected else "pending"))
        if revocation_status not in {"revoked", "not_required", "pending", "failed"}:
            raise AccountConnectionContractError("invalid revocation_status")
        return cls(
            schema_version=str(payload.get("schema_version") or ACCOUNT_CONNECTION_SCHEMA_VERSION),
            provider=provider,
            disconnected=disconnected,
            connection=connection,
            revocation_status=revocation_status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "disconnected": self.disconnected,
            "revocation_status": self.revocation_status,
            "connection": self.connection.to_dict(),
        }


@dataclass(frozen=True)
class AccountConnectionError:
    code: str
    message: str
    retryable: bool
    provider: str | None = None
    revocation_pending: bool = False

    @classmethod
    def from_public_response(cls, payload: Mapping[str, Any]) -> "AccountConnectionError":
        _assert_public_safe(payload)
        error = payload.get("error") if isinstance(payload.get("error"), Mapping) else payload
        code = str(error.get("code") or "")
        if code not in ACCOUNT_CONNECTION_ERROR_CODES:
            raise AccountConnectionContractError("unknown account connection error code")
        provider_value = error.get("provider")
        provider = normalize_account_connection_provider(str(provider_value)) if provider_value else None
        return cls(
            code=code,
            message=_public_display_text(error.get("message")) or "",
            retryable=bool(error.get("retryable", False)),
            provider=provider,
            revocation_pending=bool(error.get("revocation_pending", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "provider": self.provider,
            "revocation_pending": self.revocation_pending,
        }


def validate_google_oidc_public_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    _assert_public_safe(payload)
    issuer = str(payload.get("issuer") or "")
    audience_matches = _required_bool(payload, "audience_matches")
    nonce_matches = _required_bool(payload, "nonce_matches")
    email_verified = _required_bool(payload, "email_verified")
    if issuer not in GOOGLE_OIDC_ISSUERS or payload.get("issuer_matches") is not True:
        raise AccountConnectionContractError("oidc_issuer_mismatch")
    if not audience_matches:
        raise AccountConnectionContractError("oidc_audience_mismatch")
    if payload.get("nonce_required") is not True or not nonce_matches:
        raise AccountConnectionContractError("oidc_nonce_mismatch")
    if not email_verified:
        raise AccountConnectionContractError("oauth_email_unverified")
    return {
        "issuer": issuer,
        "issuer_matches": True,
        "audience_matches": True,
        "nonce_required": True,
        "nonce_matches": True,
        "email_verified": True,
        "raw_nonce_present": False,
        "raw_token_present": False,
    }


def _validate_google_authorize_url(url: str, *, expected_audience: str | None) -> None:
    parsed = urlparse(url)
    if parsed.hostname not in {"accounts.google.com", "accounts.google.cn"}:
        raise AccountConnectionContractError("Google authorize_url must use an official Google host")
    query = parse_qs(parsed.query)
    scopes = set(" ".join(query.get("scope", [])).split())
    if scopes != set(GOOGLE_ACCOUNT_CONNECTION_SCOPES):
        raise AccountConnectionContractError("Google account connection scopes must be exactly openid email profile")
    if query.get("code_challenge_method") != ["S256"] or not query.get("code_challenge"):
        raise AccountConnectionContractError("Google account connection requires PKCE S256")
    if not query.get("state") or not query.get("nonce"):
        raise AccountConnectionContractError("Google account connection requires state and nonce")
    if expected_audience is not None and query.get("client_id") != [expected_audience]:
        raise AccountConnectionContractError("oidc_audience_mismatch")


def _assert_public_safe(payload: Mapping[str, Any]) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                normalized = str(key).lower()
                if normalized in _FORBIDDEN_PUBLIC_KEYS:
                    raise AccountConnectionContractError(
                        f"public account connection payload must not include {normalized}"
                    )
                visit(item)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for item in value:
                visit(item)

    visit(payload)


def _required_identifier(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 255:
        raise AccountConnectionContractError(f"{name} is required and must be at most 255 characters")
    if any(char.isspace() for char in normalized):
        raise AccountConnectionContractError(f"{name} must not contain whitespace")
    return normalized


def _required_bool(payload: Mapping[str, Any], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise AccountConnectionContractError(f"{name} must be a boolean")
    return value


def _https_url(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AccountConnectionContractError(f"{name} must be an HTTPS URL")
    return normalized


def _timestamp(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise AccountConnectionContractError(f"{name} is required")
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AccountConnectionContractError(f"{name} must be an ISO-8601 timestamp") from exc
    return normalized


def _public_display_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    # Keep public DTOs and CLI output safe even when an upstream error or
    # identity label accidentally embeds credentials or an email address.
    from .api_client import redact_text

    return redact_text(normalized)
