"""Public-safe Google and GitHub OAuth provider envelopes.

This module contains provider metadata and pure helpers for PKCE, state, and
token-reference records. It performs no discovery fetches, redirects, token
exchanges, secret resolution, or user-info calls.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import re
from typing import Any, Mapping
from urllib.parse import urlparse

JsonDict = dict[str, Any]

OAUTH_PROVIDER_SCHEMA_VERSION = "ashr.clone.oauth_provider_adapter.v1"
REFERENCE_PREFIXES = ("env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:")
_PKCE_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_PKCE_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
_RAW_SECRET_RE = re.compile(
    r"(?:\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bya29\.[A-Za-z0-9._-]{20,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


class OAuthProviderContractError(ValueError):
    """Raised when an OAuth envelope would retain unsafe material."""


@dataclass(frozen=True)
class OAuthProviderMetadata:
    provider: str
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    discovery_document: str | None
    pkce_methods: tuple[str, ...] = ("S256",)

    def to_public_dict(self) -> JsonDict:
        return {
            "provider": self.provider,
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "discovery_document": self.discovery_document,
            "pkce_methods": list(self.pkce_methods),
            "metadata_fetch_performed": False,
        }


PROVIDER_METADATA: dict[str, OAuthProviderMetadata] = {
    "github": OAuthProviderMetadata(
        provider="github",
        issuer="https://github.com",
        authorization_endpoint="https://github.com/login/oauth/authorize",
        token_endpoint="https://github.com/login/oauth/access_token",
        userinfo_endpoint="https://api.github.com/user",
        discovery_document=None,
    ),
    "google": OAuthProviderMetadata(
        provider="google",
        issuer="https://accounts.google.com",
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
        discovery_document="https://accounts.google.com/.well-known/openid-configuration",
    ),
}


@dataclass(frozen=True)
class OAuthClientConfig:
    provider: str
    client_id_ref: str
    client_secret_ref: str
    redirect_uri: str
    scopes: tuple[str, ...]

    def validate(self) -> "OAuthClientConfig":
        provider = normalize_oauth_provider(self.provider)
        _validate_ref("client_id_ref", self.client_id_ref)
        _validate_ref("client_secret_ref", self.client_secret_ref)
        _validate_redirect_uri(self.redirect_uri)
        scopes = tuple(dict.fromkeys(str(scope).strip() for scope in self.scopes))
        if not scopes or any(not scope for scope in scopes):
            raise OAuthProviderContractError("OAuth scopes must not be empty")
        return OAuthClientConfig(
            provider=provider,
            client_id_ref=self.client_id_ref,
            client_secret_ref=self.client_secret_ref,
            redirect_uri=self.redirect_uri,
            scopes=scopes,
        )

    def to_public_dict(self) -> JsonDict:
        config = self.validate()
        return {
            "provider": config.provider,
            "client_id_ref": config.client_id_ref,
            "client_secret_ref": config.client_secret_ref,
            "redirect_uri": config.redirect_uri,
            "scopes": list(config.scopes),
            "secret_value_present": False,
        }


def oauth_provider_metadata(provider: str) -> JsonDict:
    return PROVIDER_METADATA[normalize_oauth_provider(provider)].to_public_dict()


def derive_pkce_s256(code_verifier: str) -> JsonDict:
    """Consume a verifier transiently and return no reversible verifier value."""

    verifier = str(code_verifier)
    if not _PKCE_VERIFIER_RE.fullmatch(verifier):
        raise OAuthProviderContractError(
            "PKCE code_verifier must be 43-128 unreserved characters"
        )
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return {
        "method": "S256",
        "code_challenge": challenge,
        "code_verifier_sha256": hashlib.sha256(verifier.encode("ascii")).hexdigest(),
        "code_verifier_present": False,
    }


def hash_oauth_state(state: str) -> JsonDict:
    """Consume an unguessable state transiently and return a comparison digest."""

    state_value = str(state)
    if len(state_value) < 16 or len(state_value) > 512:
        raise OAuthProviderContractError("OAuth state must be 16-512 characters")
    return {
        "state_sha256": hashlib.sha256(state_value.encode("utf-8")).hexdigest(),
        "raw_state_present": False,
    }


def build_authorization_envelope(
    *,
    config: OAuthClientConfig,
    state_ref: str,
    state_sha256: str,
    pkce_code_challenge: str,
    prompt: str | None = None,
) -> JsonDict:
    """Build executor input without resolving client ID or retaining state."""

    safe_config = config.validate()
    _validate_ref("state_ref", state_ref)
    _validate_digest("state_sha256", state_sha256)
    if not _PKCE_CHALLENGE_RE.fullmatch(str(pkce_code_challenge)):
        raise OAuthProviderContractError("PKCE challenge must be an S256 base64url digest")
    metadata = PROVIDER_METADATA[safe_config.provider]
    parameters: JsonDict = {
        "response_type": "code",
        "client_id_ref": safe_config.client_id_ref,
        "redirect_uri": safe_config.redirect_uri,
        "scopes": list(safe_config.scopes),
        "state_ref": state_ref,
        "code_challenge": pkce_code_challenge,
        "code_challenge_method": "S256",
    }
    if prompt is not None:
        parameters["prompt"] = str(prompt)
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "authorization_request",
        "provider_metadata": metadata.to_public_dict(),
        "parameters": parameters,
        "state_sha256": state_sha256,
        "executor_contract": {
            "resolve_client_id_ref": True,
            "resolve_state_ref": True,
            "network_io_performed": False,
        },
        "raw_state_present": False,
        "code_verifier_present": False,
        "secret_value_present": False,
        "token_value_present": False,
    }


def verify_callback_state(
    *,
    received_state: str,
    expected_state_sha256: str,
    authorization_code_ref: str | None,
    error_code: str | None = None,
) -> JsonDict:
    """Compare callback state transiently and retain only refs and hashes."""

    _validate_digest("expected_state_sha256", expected_state_sha256)
    received_digest = hashlib.sha256(str(received_state).encode("utf-8")).hexdigest()
    state_matches = hmac.compare_digest(received_digest, expected_state_sha256)
    if authorization_code_ref is not None:
        _validate_ref("authorization_code_ref", authorization_code_ref)
    accepted = state_matches and authorization_code_ref is not None and error_code is None
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "authorization_callback",
        "accepted": accepted,
        "state_matches": state_matches,
        "received_state_sha256": received_digest,
        "authorization_code_ref": authorization_code_ref if state_matches else None,
        "error_code": str(error_code) if error_code else None,
        "raw_state_present": False,
        "raw_authorization_code_present": False,
        "secret_value_present": False,
    }


def build_token_exchange_envelope(
    *,
    config: OAuthClientConfig,
    authorization_code_ref: str,
    code_verifier_ref: str,
) -> JsonDict:
    """Describe a token exchange for an external executor using refs only."""

    safe_config = config.validate()
    _validate_ref("authorization_code_ref", authorization_code_ref)
    _validate_ref("code_verifier_ref", code_verifier_ref)
    metadata = PROVIDER_METADATA[safe_config.provider]
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "token_exchange",
        "provider": safe_config.provider,
        "token_endpoint": metadata.token_endpoint,
        "client_id_ref": safe_config.client_id_ref,
        "client_secret_ref": safe_config.client_secret_ref,
        "authorization_code_ref": authorization_code_ref,
        "code_verifier_ref": code_verifier_ref,
        "redirect_uri": safe_config.redirect_uri,
        "grant_type": "authorization_code",
        "executor_contract": {
            "interface": "OAuthTokenExchangeExecutor",
            "network_io_performed": False,
            "secret_resolution_deferred": True,
        },
        "raw_authorization_code_present": False,
        "code_verifier_present": False,
        "secret_value_present": False,
        "token_value_present": False,
    }


def build_token_ref_envelope(
    *,
    provider: str,
    subject_ref: str,
    access_token_ref: str,
    refresh_token_ref: str | None = None,
    id_token_ref: str | None = None,
    granted_scopes: tuple[str, ...] = (),
) -> JsonDict:
    provider_name = normalize_oauth_provider(provider)
    _validate_ref("subject_ref", subject_ref)
    _validate_ref("access_token_ref", access_token_ref)
    if refresh_token_ref is not None:
        _validate_ref("refresh_token_ref", refresh_token_ref)
    if id_token_ref is not None:
        _validate_ref("id_token_ref", id_token_ref)
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "token_references",
        "provider": provider_name,
        "subject_ref": subject_ref,
        "access_token_ref": access_token_ref,
        "refresh_token_ref": refresh_token_ref,
        "id_token_ref": id_token_ref,
        "granted_scopes": list(dict.fromkeys(str(scope) for scope in granted_scopes)),
        "token_value_present": False,
        "secret_value_present": False,
    }


def oauth_provider_contract_manifest() -> JsonDict:
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "providers": {
            name: metadata.to_public_dict()
            for name, metadata in sorted(PROVIDER_METADATA.items())
        },
        "required_controls": {
            "pkce_method": "S256",
            "state_hash_only": True,
            "token_refs_only": True,
            "raw_authorization_code_allowed": False,
            "network_io_performed": False,
        },
    }


def normalize_oauth_provider(provider: str) -> str:
    normalized = str(provider).strip().lower()
    if normalized not in PROVIDER_METADATA:
        raise OAuthProviderContractError("OAuth provider must be github or google")
    return normalized


def _validate_ref(name: str, value: str | None) -> None:
    text = str(value or "")
    if not any(text.startswith(prefix) for prefix in REFERENCE_PREFIXES):
        raise OAuthProviderContractError(f"{name} must use an approved reference prefix")
    if any(character.isspace() for character in text):
        raise OAuthProviderContractError(f"{name} must not contain whitespace")
    if _RAW_SECRET_RE.search(text):
        raise OAuthProviderContractError(f"{name} contains raw OAuth secret material")


def _validate_redirect_uri(value: str) -> None:
    parsed = urlparse(str(value))
    is_localhost = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    is_https = parsed.scheme == "https" and bool(parsed.netloc)
    if not (is_https or is_localhost) or parsed.username or parsed.password:
        raise OAuthProviderContractError("OAuth redirect URI must be HTTPS or localhost")


def _validate_digest(name: str, value: str) -> None:
    if not _DIGEST_RE.fullmatch(str(value)):
        raise OAuthProviderContractError(f"{name} must be a lowercase SHA-256 digest")
