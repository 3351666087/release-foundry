"""Account-ready, public-safe OAuth provider contracts and injected runtimes.

Contract helpers remain deterministic and reference-only. Provider I/O and
secret resolution are available only through explicitly injected runtime
boundaries, so tests and callers can operate without real credentials or
network access.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import re
import secrets
from typing import Any, Iterable, Mapping, Protocol
from urllib.parse import quote, urlencode, urlparse
from uuid import uuid4

JsonDict = dict[str, Any]

OAUTH_PROVIDER_SCHEMA_VERSION = "releasefoundry.oauth_provider_adapter.v2"
OAUTH_ENVIRONMENTS = ("sandbox", "live")
REFERENCE_PREFIXES = ("env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:")
_PKCE_VERIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_PKCE_CHALLENGE_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
_RAW_SECRET_RE = re.compile(
    r"(?:\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bya29\.[A-Za-z0-9._-]{20,}\b|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_SECRET_REF_HINT_RE = re.compile(
    r"(?:^|[/_:.-])(?:client[-_]?secret|secret|credential|private[-_]?key)(?:$|[/_:.-])",
    re.IGNORECASE,
)


class OAuthProviderContractError(ValueError):
    """Raised when an OAuth envelope is unsafe or ambiguously bound."""


class OAuthProviderRuntimeError(OAuthProviderContractError):
    """Public-safe provider runtime failure."""

    def __init__(self, code: str, *, status_code: int | None = None) -> None:
        safe_code = _redact_runtime_error_code(code)
        super().__init__(safe_code)
        self.code = safe_code
        self.status_code = status_code

    def to_public_dict(self) -> JsonDict:
        return {
            "code": self.code,
            "status_code": self.status_code,
            "provider_error_redacted": True,
            "secret_value_present": False,
            "raw_provider_response_present": False,
        }


class OAuthTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Execute a provider request and return status_code plus a JSON mapping."""


class OAuthSecretReferenceStore(Protocol):
    def resolve(self, reference: str) -> str:
        """Resolve a secret reference inside the runtime boundary."""

    def put(self, value: str, *, purpose: str) -> str:
        """Store a secret value and return an approved opaque reference."""

    def delete(self, reference: str) -> None:
        """Delete a referenced secret when a flow or connection is revoked."""


@dataclass
class InMemoryOAuthSecretReferenceStore:
    """Test/local reference store that never exposes values in public snapshots."""

    initial_values: Mapping[str, str] | None = None
    _values: dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for reference, value in dict(self.initial_values or {}).items():
            _validate_ref("secret_reference", reference)
            self._values[str(reference)] = _validate_secret_value(value)

    def resolve(self, reference: str) -> str:
        _validate_ref("secret_reference", reference)
        try:
            return self._values[str(reference)]
        except KeyError:
            raise OAuthProviderRuntimeError("secret_reference_unavailable") from None

    def put(self, value: str, *, purpose: str) -> str:
        safe_purpose = re.sub(r"[^a-z0-9._-]+", "-", str(purpose).strip().lower()).strip("-")
        if not safe_purpose:
            raise OAuthProviderContractError("OAuth secret purpose must be a bounded identifier")
        reference = f"provider-ref:oauth/{safe_purpose}/{uuid4().hex}"
        self._values[reference] = _validate_secret_value(value)
        return reference

    def delete(self, reference: str) -> None:
        _validate_ref("secret_reference", reference)
        self._values.pop(str(reference), None)

    def public_snapshot(self) -> JsonDict:
        return {
            "reference_count": len(self._values),
            "secret_value_present": False,
            "references_included": False,
        }


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
        if hmac.compare_digest(self.client_id_ref, self.client_secret_ref):
            raise OAuthProviderContractError(
                "OAuth client credential references must be distinct"
            )
        _validate_client_secret_ref_shape(self.client_secret_ref)
        redirect_uri = _normalize_redirect_uri(self.redirect_uri)
        if environment == "live" and urlparse(redirect_uri).scheme != "https":
            raise OAuthProviderContractError(
                "OAuth live redirect URI must use HTTPS"
            )
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
            "client_id_ref_present": bool(config.client_id_ref),
            "client_secret_ref_present": bool(config.client_secret_ref),
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


@dataclass
class GitHubOAuthRuntime:
    """GitHub OAuth runtime with injected I/O and reference-only secret storage."""

    transport: OAuthTransport
    secret_store: OAuthSecretReferenceStore
    replay_ledger: OAuthReplayLedger = field(default_factory=OAuthReplayLedger)

    def begin_authorization(
        self,
        *,
        config: OAuthClientConfig,
        state: str | None = None,
        code_verifier: str | None = None,
    ) -> JsonDict:
        safe_config = config.validate()
        if safe_config.provider != "github":
            raise OAuthProviderContractError("GitHub runtime requires provider=github")
        if not safe_config.enabled:
            raise OAuthProviderContractError("GitHub OAuth provider is disabled")
        state_value = state or secrets.token_urlsafe(32)
        verifier_value = code_verifier or secrets.token_urlsafe(64)
        state_binding = hash_oauth_state(state_value)
        pkce = derive_pkce_s256(verifier_value)
        client_id, _ = self._resolve_distinct_client_credentials(safe_config)
        code_verifier_ref = self.secret_store.put(
            verifier_value,
            purpose=f"github-pkce-{safe_config.environment}",
        )
        parameters = {
            "client_id": client_id,
            "redirect_uri": safe_config.redirect_uri,
            "scope": " ".join(safe_config.scopes),
            "state": state_value,
            "code_challenge": pkce["code_challenge"],
            "code_challenge_method": "S256",
        }
        return {
            "provider": "github",
            "environment": safe_config.environment,
            "authorization_url": f"{PROVIDER_METADATA['github'].authorization_endpoint}?{urlencode(parameters)}",
            "state_sha256": state_binding["state_sha256"],
            "code_challenge": pkce["code_challenge"],
            "code_challenge_method": "S256",
            "code_verifier_ref": code_verifier_ref,
            "raw_state_present": False,
            "code_verifier_present": False,
            "secret_value_present": False,
        }

    def complete_authorization(
        self,
        *,
        config: OAuthClientConfig,
        authorization_code: str,
        received_state: str,
        expected_state_sha256: str,
        code_verifier_ref: str,
        include_emails: bool = True,
    ) -> JsonDict:
        safe_config = config.validate()
        if safe_config.provider != "github":
            raise OAuthProviderContractError("GitHub runtime requires provider=github")
        _validate_digest("expected_state_sha256", expected_state_sha256)
        _validate_ref("code_verifier_ref", code_verifier_ref)
        code = _validate_authorization_code(authorization_code)
        received_digest = hashlib.sha256(str(received_state).encode("utf-8")).hexdigest()
        if not hmac.compare_digest(received_digest, expected_state_sha256):
            raise OAuthProviderRuntimeError("oauth_state_mismatch")
        if not self.replay_ledger.consume(
            provider="github",
            environment=safe_config.environment,
            replay_key=f"state:{expected_state_sha256}",
        ):
            raise OAuthProviderRuntimeError("callback_replay")
        code_sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if not self.replay_ledger.consume(
            provider="github",
            environment=safe_config.environment,
            replay_key=f"code:{code_sha256}",
        ):
            raise OAuthProviderRuntimeError("authorization_code_replay")

        client_id, client_secret = self._resolve_distinct_client_credentials(safe_config)
        code_verifier = self.secret_store.resolve(code_verifier_ref)
        token_payload = self._request_json(
            "POST",
            PROVIDER_METADATA["github"].token_endpoint,
            headers={"Accept": "application/json"},
            form={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": safe_config.redirect_uri,
                "code_verifier": code_verifier,
            },
        )
        access_token = _required_provider_string(token_payload, "access_token")
        token_type = str(token_payload.get("token_type") or "bearer").strip().lower()
        if token_type != "bearer":
            raise OAuthProviderRuntimeError("unsupported_token_type")
        granted_scopes = _normalize_scope_response(token_payload.get("scope"))
        if set(granted_scopes) - set(safe_config.scopes):
            raise OAuthProviderRuntimeError("oauth_scope_escalation")
        access_token_ref = self.secret_store.put(
            access_token,
            purpose=f"github-access-{safe_config.environment}",
        )
        self.secret_store.delete(code_verifier_ref)

        try:
            user = self._request_json(
                "GET",
                PROVIDER_METADATA["github"].userinfo_endpoint,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            github_user_id = _normalize_github_user_id(user.get("id"))
            email = _optional_provider_email(user.get("email"))
            email_source = "user"
            if email is None and include_emails and "user:email" in safe_config.scopes:
                emails_payload = self._request_json(
                    "GET",
                    "https://api.github.com/user/emails",
                    headers={
                        "Accept": "application/vnd.github+json",
                        "Authorization": f"Bearer {access_token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                )
                email = _select_github_email(emails_payload)
                email_source = "user_emails" if email else "unavailable"
        except Exception:
            self.secret_store.delete(access_token_ref)
            raise

        subject_ref = f"provider-ref:github/user/{github_user_id}"
        return {
            "provider": "github",
            "environment": safe_config.environment,
            "subject_ref": subject_ref,
            "account_binding_ref": subject_ref,
            "subject_sha256": hashlib.sha256(github_user_id.encode("ascii")).hexdigest(),
            "access_token_ref": access_token_ref,
            "refresh_token_ref": None,
            "granted_scopes": list(granted_scopes),
            "email_sha256": hashlib.sha256(email.encode("utf-8")).hexdigest() if email else None,
            "email_present": email is not None,
            "email_source": email_source,
            "raw_email_present": False,
            "token_value_present": False,
            "secret_value_present": False,
            "raw_provider_response_present": False,
        }

    def revoke_connection(
        self,
        *,
        config: OAuthClientConfig,
        access_token_ref: str,
    ) -> JsonDict:
        safe_config = config.validate()
        if safe_config.provider != "github":
            raise OAuthProviderContractError("GitHub runtime requires provider=github")
        _validate_ref("access_token_ref", access_token_ref)
        client_id, client_secret = self._resolve_distinct_client_credentials(safe_config)
        access_token = self.secret_store.resolve(access_token_ref)
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        self._request_json(
            "DELETE",
            f"https://api.github.com/applications/{quote(client_id, safe='')}/token",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Basic {basic}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json_body={"access_token": access_token},
            allow_empty=True,
        )
        self.secret_store.delete(access_token_ref)
        return {
            "provider": "github",
            "revoked": True,
            "access_token_ref_deleted": True,
            "token_value_present": False,
            "secret_value_present": False,
            "raw_provider_response_present": False,
        }

    def discard_reference(self, reference: str) -> None:
        """Delete a transient reference without resolving or exposing its value."""

        self.secret_store.delete(reference)

    def _resolve_distinct_client_credentials(
        self, config: OAuthClientConfig
    ) -> tuple[str, str]:
        client_id = self.secret_store.resolve(config.client_id_ref)
        client_secret = self.secret_store.resolve(config.client_secret_ref)
        if hmac.compare_digest(client_id, client_secret):
            raise OAuthProviderRuntimeError("oauth_client_credentials_not_distinct")
        return client_id, client_secret

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        allow_empty: bool = False,
    ) -> Mapping[str, Any] | list[Any]:
        try:
            response = self.transport.request(
                method,
                url,
                headers=headers,
                form=form,
                json_body=json_body,
            )
        except OAuthProviderRuntimeError:
            raise
        except Exception:
            raise OAuthProviderRuntimeError("github_transport_error") from None
        if not isinstance(response, Mapping):
            raise OAuthProviderRuntimeError("github_invalid_response")
        try:
            status_code = int(response.get("status_code", 200))
        except (TypeError, ValueError):
            raise OAuthProviderRuntimeError("github_invalid_response") from None
        payload = response.get("json", response.get("body"))
        if status_code < 200 or status_code >= 300:
            provider_code = _provider_error_code(payload)
            raise OAuthProviderRuntimeError(provider_code, status_code=status_code)
        if payload is None and allow_empty:
            return {}
        if isinstance(payload, (Mapping, list)):
            return payload
        raise OAuthProviderRuntimeError("github_invalid_response", status_code=status_code)


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
    callback_is_eligible = (
        state_matches
        and authorization_code_ref is not None
        and error_code is None
    )
    if replay_key is not None and callback_is_eligible:
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
    email_verified: bool | None = None,
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
    email_verification_required = "email" in safe_config.scopes
    email_verified_matches = not email_verification_required or email_verified is True
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
    if not email_verified_matches:
        failures.append("email_unverified")
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
        "email_verification_required": email_verification_required,
        "email_verified": email_verified is True,
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


def _validate_client_secret_ref_shape(value: str) -> None:
    if not _SECRET_REF_HINT_RE.search(str(value)):
        raise OAuthProviderContractError(
            "OAuth client_secret_ref must identify secret credential material"
        )


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
        or parsed.query
        or parsed.fragment
        or not parsed.path
        or parsed.hostname is None
        or parsed.hostname.endswith(".")
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


def _validate_secret_value(value: str) -> str:
    text = str(value)
    if not text or len(text) > 8192 or "\x00" in text:
        raise OAuthProviderContractError("OAuth secret value must be non-empty and bounded")
    return text


def _validate_authorization_code(value: str) -> str:
    text = str(value)
    if not text or len(text) > 2048 or any(character.isspace() for character in text):
        raise OAuthProviderRuntimeError("invalid_authorization_code")
    return text


def _required_provider_string(payload: Mapping[str, Any] | list[Any], key: str) -> str:
    if not isinstance(payload, Mapping):
        raise OAuthProviderRuntimeError("github_invalid_response")
    provider_error = _provider_error_code(payload)
    if provider_error != "github_provider_error":
        raise OAuthProviderRuntimeError(provider_error)
    value = payload.get(key)
    text = str(value or "")
    if not text or len(text) > 8192 or any(character.isspace() for character in text):
        raise OAuthProviderRuntimeError(f"github_{key}_missing")
    return text


def _normalize_scope_response(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        scopes = re.split(r"[\s,]+", value.strip())
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        scopes = [str(item).strip() for item in value]
    else:
        raise OAuthProviderRuntimeError("github_invalid_scope_response")
    return tuple(dict.fromkeys(scope for scope in scopes if scope))


def _normalize_github_user_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text.isdigit() or len(text) > 32:
        raise OAuthProviderRuntimeError("github_user_id_missing")
    return text


def _optional_provider_email(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    text = str(value).strip().lower()
    if len(text) > 320 or text.count("@") != 1 or any(character.isspace() for character in text):
        raise OAuthProviderRuntimeError("github_invalid_email_response")
    return text


def _select_github_email(payload: Mapping[str, Any] | list[Any]) -> str | None:
    if not isinstance(payload, list):
        raise OAuthProviderRuntimeError("github_invalid_email_response")
    candidates: list[tuple[bool, bool, str]] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        email = _optional_provider_email(item.get("email"))
        if email is None or item.get("verified") is not True:
            continue
        candidates.append((item.get("primary") is True, True, email))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][2]


def _provider_error_code(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return "github_provider_error"
    for key in ("error", "code"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _redact_provider_error_code(value)
    return "github_provider_error"


def _redact_provider_error_code(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_")
    if not normalized:
        return "github_provider_error"
    safe_codes = {
        "access_denied",
        "bad_verification_code",
        "incorrect_client_credentials",
        "redirect_uri_mismatch",
        "unverified_user_email",
    }
    return normalized if normalized in safe_codes else "github_provider_error"


def _redact_runtime_error_code(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_")
    safe_runtime_codes = {
        "authorization_code_replay",
        "callback_replay",
        "github_access_token_missing",
        "github_invalid_email_response",
        "github_invalid_response",
        "github_invalid_scope_response",
        "github_provider_error",
        "github_transport_error",
        "github_user_id_missing",
        "invalid_authorization_code",
        "oauth_client_credentials_not_distinct",
        "oauth_scope_escalation",
        "oauth_state_mismatch",
        "secret_reference_unavailable",
        "unsupported_token_type",
    }
    if normalized in safe_runtime_codes:
        return normalized
    return _redact_provider_error_code(normalized)
