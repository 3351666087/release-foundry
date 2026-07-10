"""Account-ready, public-safe OAuth provider contracts.

The helpers in this module are deliberately pure. They do not resolve secrets,
call provider endpoints, exchange codes, or create login sessions. Provider
activation remains disabled until an operator supplies reviewed reference-only
configuration in a separately isolated environment.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import re
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

JsonDict = dict[str, Any]

OAUTH_PROVIDER_SCHEMA_VERSION = "ashr.clone.oauth_provider_adapter.v2"
OAUTH_ENVIRONMENTS = ("sandbox", "live")
REFERENCE_PREFIXES = ("env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:")
_PKCE_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_PKCE_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
_RAW_SECRET_RE = re.compile(
    r"(?:\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bya29\.[A-Za-z0-9._-]{20,}\b|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


class OAuthProviderContractError(ValueError):
    """Raised when an OAuth envelope is unsafe or ambiguously bound."""


@dataclass(frozen=True)
class OAuthProviderMetadata:
    provider: str
    protocol: str
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    discovery_document: str | None
    default_scopes: tuple[str, ...]
    subject_claim: str
    audience_claim: str | None
    nonce_supported: bool
    account_binding: str
    pkce_methods: tuple[str, ...] = ("S256",)
    supported_environments: tuple[str, ...] = OAUTH_ENVIRONMENTS

    def to_public_dict(self) -> JsonDict:
        return {
            "provider": self.provider,
            "protocol": self.protocol,
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "discovery_document": self.discovery_document,
            "default_scopes": list(self.default_scopes),
            "subject_claim": self.subject_claim,
            "audience_claim": self.audience_claim,
            "nonce_supported": self.nonce_supported,
            "account_binding": self.account_binding,
            "pkce_methods": list(self.pkce_methods),
            "supported_environments": list(self.supported_environments),
            "metadata_fetch_performed": False,
        }


PROVIDER_METADATA: dict[str, OAuthProviderMetadata] = {
    "github": OAuthProviderMetadata(
        provider="github",
        protocol="oauth2",
        issuer="https://github.com",
        authorization_endpoint="https://github.com/login/oauth/authorize",
        token_endpoint="https://github.com/login/oauth/access_token",
        userinfo_endpoint="https://api.github.com/user",
        discovery_document=None,
        default_scopes=("read:user", "user:email"),
        subject_claim="id",
        audience_claim=None,
        nonce_supported=False,
        account_binding="github_user_id",
    ),
    "google": OAuthProviderMetadata(
        provider="google",
        protocol="oidc",
        issuer="https://accounts.google.com",
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
        discovery_document="https://accounts.google.com/.well-known/openid-configuration",
        default_scopes=("openid", "email", "profile"),
        subject_claim="sub",
        audience_claim="aud",
        nonce_supported=True,
        account_binding="google_subject",
    ),
    "wechat": OAuthProviderMetadata(
        provider="wechat",
        protocol="oauth2",
        issuer="https://open.weixin.qq.com",
        authorization_endpoint="https://open.weixin.qq.com/connect/qrconnect",
        token_endpoint="https://api.weixin.qq.com/sns/oauth2/access_token",
        userinfo_endpoint="https://api.weixin.qq.com/sns/userinfo",
        discovery_document=None,
        default_scopes=("snsapi_login",),
        subject_claim="unionid_or_openid",
        audience_claim="appid",
        nonce_supported=False,
        account_binding="wechat_unionid_with_appid_openid_fallback",
    ),
    "alipay": OAuthProviderMetadata(
        provider="alipay",
        protocol="oauth2",
        issuer="https://openauth.alipay.com",
        authorization_endpoint="https://openauth.alipay.com/oauth2/publicAppAuthorize.htm",
        token_endpoint="https://openapi.alipay.com/gateway.do",
        userinfo_endpoint="https://openapi.alipay.com/gateway.do",
        discovery_document=None,
        default_scopes=("auth_user",),
        subject_claim="user_id",
        audience_claim="app_id",
        nonce_supported=False,
        account_binding="alipay_user_id",
    ),
}


@dataclass(frozen=True)
class OAuthClientConfig:
    provider: str
    client_id_ref: str
    client_secret_ref: str
    redirect_uri: str
    scopes: tuple[str, ...]
    environment: str = "sandbox"
    redirect_allowlist: tuple[str, ...] = ()
    enabled: bool = False
    issuer_allowlist: tuple[str, ...] = ()
    audience_allowlist: tuple[str, ...] = ()

    def validate(self) -> "OAuthClientConfig":
        provider = normalize_oauth_provider(self.provider)
        environment = normalize_oauth_environment(self.environment)
        _validate_ref("client_id_ref", self.client_id_ref)
        _validate_ref("client_secret_ref", self.client_secret_ref)
        redirect_uri = _normalize_redirect_uri(self.redirect_uri)
        allowlist = tuple(
            dict.fromkeys(_normalize_redirect_uri(uri) for uri in self.redirect_allowlist)
        ) or (redirect_uri,)
        if redirect_uri not in allowlist:
            raise OAuthProviderContractError(
                "OAuth redirect URI must exactly match redirect_allowlist"
            )
        scopes = tuple(dict.fromkeys(str(scope).strip() for scope in self.scopes))
        if not scopes or any(not scope for scope in scopes):
            raise OAuthProviderContractError("OAuth scopes must not be empty")
        metadata = PROVIDER_METADATA[provider]
        issuer_allowlist = tuple(
            dict.fromkeys(_normalize_https_origin("issuer", value) for value in self.issuer_allowlist)
        ) or (metadata.issuer,)
        audience_allowlist = tuple(
            dict.fromkeys(_validate_identifier("audience", value) for value in self.audience_allowlist)
        )
        return OAuthClientConfig(
            provider=provider,
            client_id_ref=self.client_id_ref,
            client_secret_ref=self.client_secret_ref,
            redirect_uri=redirect_uri,
            scopes=scopes,
            environment=environment,
            redirect_allowlist=allowlist,
            enabled=bool(self.enabled),
            issuer_allowlist=issuer_allowlist,
            audience_allowlist=audience_allowlist,
        )

    def to_public_dict(self) -> JsonDict:
        config = self.validate()
        return {
            "provider": config.provider,
            "environment": config.environment,
            "client_id_ref": config.client_id_ref,
            "client_secret_ref": config.client_secret_ref,
            "redirect_uri": config.redirect_uri,
            "redirect_allowlist": list(config.redirect_allowlist),
            "scopes": list(config.scopes),
            "issuer_allowlist": list(config.issuer_allowlist),
            "audience_allowlist": list(config.audience_allowlist),
            "enabled": config.enabled,
            "disabled_by_default": not config.enabled,
            "secret_value_present": False,
        }


@dataclass
class OAuthReplayLedger:
    """In-memory one-time digest ledger for deterministic adapters and tests."""

    _consumed: set[str] = field(default_factory=set)

    def consume(self, *, provider: str, environment: str, replay_key: str) -> bool:
        provider_name = normalize_oauth_provider(provider)
        environment_name = normalize_oauth_environment(environment)
        key = str(replay_key)
        if len(key) < 16 or len(key) > 1024:
            raise OAuthProviderContractError("OAuth replay key must be 16-1024 characters")
        digest = hashlib.sha256(
            f"{provider_name}\0{environment_name}\0{key}".encode("utf-8")
        ).hexdigest()
        if digest in self._consumed:
            return False
        self._consumed.add(digest)
        return True

    def public_snapshot(self) -> JsonDict:
        return {
            "consumed_digest_count": len(self._consumed),
            "raw_replay_keys_present": False,
        }


def oauth_provider_metadata(provider: str) -> JsonDict:
    return PROVIDER_METADATA[normalize_oauth_provider(provider)].to_public_dict()


def derive_pkce_s256(code_verifier: str) -> JsonDict:
    verifier = str(code_verifier)
    if not _PKCE_VERIFIER_RE.fullmatch(verifier):
        raise OAuthProviderContractError(
            "PKCE code_verifier must be 43-128 unreserved characters"
        )
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return {
        "method": "S256",
        "code_challenge": base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
        "code_verifier_sha256": hashlib.sha256(verifier.encode("ascii")).hexdigest(),
        "code_verifier_present": False,
    }


def hash_oauth_state(state: str) -> JsonDict:
    return _hash_transient("state", state, minimum=16, maximum=512)


def hash_oauth_nonce(nonce: str) -> JsonDict:
    return _hash_transient("nonce", nonce, minimum=16, maximum=512)


def build_authorization_envelope(
    *,
    config: OAuthClientConfig,
    state_ref: str,
    state_sha256: str,
    pkce_code_challenge: str,
    prompt: str | None = None,
    nonce_ref: str | None = None,
    nonce_sha256: str | None = None,
) -> JsonDict:
    safe_config = config.validate()
    _validate_ref("state_ref", state_ref)
    _validate_digest("state_sha256", state_sha256)
    if not _PKCE_CHALLENGE_RE.fullmatch(str(pkce_code_challenge)):
        raise OAuthProviderContractError("PKCE challenge must be an S256 base64url digest")
    if (nonce_ref is None) != (nonce_sha256 is None):
        raise OAuthProviderContractError("OAuth nonce_ref and nonce_sha256 must be paired")
    if nonce_ref is not None:
        _validate_ref("nonce_ref", nonce_ref)
        _validate_digest("nonce_sha256", str(nonce_sha256))
    metadata = PROVIDER_METADATA[safe_config.provider]
    if metadata.nonce_supported and safe_config.enabled and nonce_ref is None:
        raise OAuthProviderContractError(
            f"{safe_config.provider} authorization requires nonce binding"
        )
    parameters: JsonDict = {
        "response_type": "code",
        "client_id_ref": safe_config.client_id_ref,
        "redirect_uri": safe_config.redirect_uri,
        "scopes": list(safe_config.scopes),
        "state_ref": state_ref,
        "code_challenge": pkce_code_challenge,
        "code_challenge_method": "S256",
    }
    if nonce_ref is not None:
        parameters["nonce_ref"] = nonce_ref
    if prompt is not None:
        parameters["prompt"] = str(prompt)
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "authorization_request",
        "provider": safe_config.provider,
        "environment": safe_config.environment,
        "enabled": safe_config.enabled,
        "ready": False,
        "provider_metadata": metadata.to_public_dict(),
        "parameters": parameters,
        "state_sha256": state_sha256,
        "nonce_sha256": nonce_sha256,
        "redirect_allowlist": list(safe_config.redirect_allowlist),
        "executor_contract": {
            "resolve_client_id_ref": True,
            "resolve_state_ref": True,
            "resolve_nonce_ref": nonce_ref is not None,
            "network_io_performed": False,
        },
        "raw_state_present": False,
        "raw_nonce_present": False,
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
    provider: str = "github",
    environment: str = "sandbox",
    replay_key: str | None = None,
    replay_ledger: OAuthReplayLedger | None = None,
) -> JsonDict:
    _validate_digest("expected_state_sha256", expected_state_sha256)
    received_digest = hashlib.sha256(str(received_state).encode("utf-8")).hexdigest()
    state_matches = hmac.compare_digest(received_digest, expected_state_sha256)
    if authorization_code_ref is not None:
        _validate_ref("authorization_code_ref", authorization_code_ref)
    replay_accepted = True
    if replay_key is not None:
        if replay_ledger is None:
            raise OAuthProviderContractError("OAuth replay ledger is required")
        replay_accepted = replay_ledger.consume(
            provider=provider, environment=environment, replay_key=replay_key
        )
    accepted = (
        state_matches
        and replay_accepted
        and authorization_code_ref is not None
        and error_code is None
    )
    reasons = []
    if not state_matches:
        reasons.append("state_mismatch")
    if not replay_accepted:
        reasons.append("callback_replay")
    if authorization_code_ref is None:
        reasons.append("authorization_code_ref_missing")
    if error_code is not None:
        reasons.append("provider_error")
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "authorization_callback",
        "accepted": accepted,
        "state_matches": state_matches,
        "replay_accepted": replay_accepted,
        "failure_reasons": reasons,
        "received_state_sha256": received_digest,
        "authorization_code_ref": authorization_code_ref if accepted else None,
        "error_code": str(error_code) if error_code else None,
        "raw_state_present": False,
        "raw_authorization_code_present": False,
        "secret_value_present": False,
    }


def verify_callback_identity(
    *,
    config: OAuthClientConfig,
    issuer: str,
    audience: str | Iterable[str] | None,
    subject: str,
    account_binding_ref: str,
    expected_account_binding_ref: str | None = None,
    received_nonce: str | None = None,
    expected_nonce_sha256: str | None = None,
) -> JsonDict:
    """Validate callback identity claims without retaining raw subject or nonce."""

    safe_config = config.validate()
    normalized_issuer = _normalize_https_origin("issuer", issuer)
    audiences = _normalize_audiences(audience)
    subject_value = _validate_identifier("subject", subject)
    _validate_ref("account_binding_ref", account_binding_ref)
    if expected_account_binding_ref is not None:
        _validate_ref("expected_account_binding_ref", expected_account_binding_ref)
    issuer_matches = normalized_issuer in safe_config.issuer_allowlist
    audience_matches = (
        not safe_config.audience_allowlist
        or bool(set(audiences).intersection(safe_config.audience_allowlist))
    )
    account_matches = (
        expected_account_binding_ref is None
        or hmac.compare_digest(account_binding_ref, expected_account_binding_ref)
    )
    metadata = PROVIDER_METADATA[safe_config.provider]
    nonce_required = metadata.nonce_supported
    nonce_matches = not nonce_required
    received_nonce_sha256 = None
    if expected_nonce_sha256 is not None:
        _validate_digest("expected_nonce_sha256", expected_nonce_sha256)
        received_nonce_sha256 = hashlib.sha256(
            str(received_nonce or "").encode("utf-8")
        ).hexdigest()
        nonce_matches = received_nonce is not None and hmac.compare_digest(
            received_nonce_sha256, expected_nonce_sha256
        )
    elif nonce_required:
        nonce_matches = False
    failures = []
    if not issuer_matches:
        failures.append("issuer_mismatch")
    if not audience_matches:
        failures.append("audience_mismatch")
    if not nonce_matches:
        failures.append("nonce_mismatch")
    if not account_matches:
        failures.append("account_binding_mismatch")
    accepted = not failures and safe_config.enabled
    if not safe_config.enabled:
        failures.append("provider_disabled")
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "callback_identity_verification",
        "provider": safe_config.provider,
        "environment": safe_config.environment,
        "accepted": accepted,
        "failure_reasons": failures,
        "issuer": normalized_issuer if issuer_matches else None,
        "issuer_matches": issuer_matches,
        "audience_matches": audience_matches,
        "nonce_required": nonce_required,
        "nonce_matches": nonce_matches,
        "account_binding_matches": account_matches,
        "subject_sha256": hashlib.sha256(subject_value.encode("utf-8")).hexdigest(),
        "received_nonce_sha256": received_nonce_sha256,
        "account_binding_ref": account_binding_ref if account_matches else None,
        "raw_subject_present": False,
        "raw_nonce_present": False,
        "secret_value_present": False,
    }


def build_token_exchange_envelope(
    *,
    config: OAuthClientConfig,
    authorization_code_ref: str,
    code_verifier_ref: str,
) -> JsonDict:
    safe_config = config.validate()
    _validate_ref("authorization_code_ref", authorization_code_ref)
    _validate_ref("code_verifier_ref", code_verifier_ref)
    metadata = PROVIDER_METADATA[safe_config.provider]
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "token_exchange",
        "provider": safe_config.provider,
        "environment": safe_config.environment,
        "enabled": safe_config.enabled,
        "ready": False,
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
    environment: str = "sandbox",
    account_binding_ref: str | None = None,
) -> JsonDict:
    provider_name = normalize_oauth_provider(provider)
    environment_name = normalize_oauth_environment(environment)
    _validate_ref("subject_ref", subject_ref)
    _validate_ref("access_token_ref", access_token_ref)
    if refresh_token_ref is not None:
        _validate_ref("refresh_token_ref", refresh_token_ref)
    if id_token_ref is not None:
        _validate_ref("id_token_ref", id_token_ref)
    if account_binding_ref is not None:
        _validate_ref("account_binding_ref", account_binding_ref)
    return {
        "schema_version": OAUTH_PROVIDER_SCHEMA_VERSION,
        "envelope_type": "token_references",
        "provider": provider_name,
        "environment": environment_name,
        "subject_ref": subject_ref,
        "account_binding_ref": account_binding_ref,
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
        "environments": list(OAUTH_ENVIRONMENTS),
        "required_controls": {
            "pkce_method": "S256",
            "state_hash_only": True,
            "nonce_hash_only": True,
            "redirect_exact_allowlist": True,
            "sandbox_live_separation": True,
            "issuer_validation": True,
            "audience_validation": True,
            "subject_hash_only": True,
            "account_binding_required": True,
            "callback_replay_protection": True,
            "token_refs_only": True,
            "raw_authorization_code_allowed": False,
            "network_io_performed": False,
            "disabled_by_default": True,
        },
    }


def normalize_oauth_provider(provider: str) -> str:
    normalized = str(provider).strip().lower()
    aliases = {"wechat_login": "wechat", "weixin": "wechat", "alipay_login": "alipay"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in PROVIDER_METADATA:
        raise OAuthProviderContractError(
            "OAuth provider must be github, google, wechat, or alipay"
        )
    return normalized


def normalize_oauth_environment(environment: str) -> str:
    normalized = str(environment).strip().lower()
    if normalized not in OAUTH_ENVIRONMENTS:
        raise OAuthProviderContractError("OAuth environment must be sandbox or live")
    return normalized


def _validate_ref(name: str, value: str | None) -> None:
    text = str(value or "")
    if not any(text.startswith(prefix) for prefix in REFERENCE_PREFIXES):
        raise OAuthProviderContractError(f"{name} must use an approved reference prefix")
    if any(character.isspace() for character in text):
        raise OAuthProviderContractError(f"{name} must not contain whitespace")
    if _RAW_SECRET_RE.search(text):
        raise OAuthProviderContractError(f"{name} contains raw OAuth secret material")


def _normalize_redirect_uri(value: str) -> str:
    text = str(value).strip()
    parsed = urlparse(text)
    is_localhost = (
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1"}
        and parsed.port is not None
    )
    is_https = parsed.scheme == "https" and bool(parsed.netloc)
    if (
        not (is_https or is_localhost)
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not parsed.path
    ):
        raise OAuthProviderContractError(
            "OAuth redirect URI must be HTTPS or localhost; localhost requires an explicit port and path"
        )
    return text


def _normalize_https_origin(name: str, value: str) -> str:
    text = str(value).strip().rstrip("/")
    parsed = urlparse(text)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise OAuthProviderContractError(f"OAuth {name} must be an HTTPS issuer URL")
    return text


def _validate_identifier(name: str, value: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 512 or any(character.isspace() for character in text):
        raise OAuthProviderContractError(f"OAuth {name} must be a bounded identifier")
    return text


def _validate_digest(name: str, value: str) -> None:
    if not _DIGEST_RE.fullmatch(str(value)):
        raise OAuthProviderContractError(f"{name} must be a lowercase SHA-256 digest")


def _hash_transient(name: str, value: str, *, minimum: int, maximum: int) -> JsonDict:
    text = str(value)
    if len(text) < minimum or len(text) > maximum:
        raise OAuthProviderContractError(
            f"OAuth {name} must be {minimum}-{maximum} characters"
        )
    return {
        f"{name}_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        f"raw_{name}_present": False,
    }


def _normalize_audiences(value: str | Iterable[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    values = (value,) if isinstance(value, str) else tuple(value)
    return tuple(dict.fromkeys(_validate_identifier("audience", item) for item in values))
