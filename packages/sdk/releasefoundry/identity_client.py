"""Safe A3 identity client for the ReleaseFoundry control-plane API.

Registration and login are deliberately separate methods.  OAuth account
linking returns an opaque binding ticket, and binding always requires an
authenticated session plus explicit consent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Callable, Literal, Mapping, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

JsonDict = dict[str, Any]
IdentityTransportResponse = tuple[int, bytes] | tuple[int, bytes, Mapping[str, str]]
IdentityTransport = Callable[[str, str, Mapping[str, str], bytes | None, int], IdentityTransportResponse]
OAuthIntent = Literal["registration", "login", "link"]

IDENTITY_SCHEMA_VERSION = "releasefoundry.identity.v1"
IDENTITY_DEFAULT_BASE_URL = "http://127.0.0.1:8787"

_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r'"(?:session_token|binding_ticket_proof|proof|code|state)"\s*:\s*"[^"]+"', re.IGNORECASE),
)


def _redact_text(value: str) -> str:
    safe = value
    for pattern in _SECRET_PATTERNS:
        safe = pattern.sub("[redacted]", safe)
    return safe


class IdentityClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, code: str = "identity_client_error") -> None:
        super().__init__(_redact_text(message))
        self.status_code = status_code
        self.code = code

    def to_safe_dict(self) -> JsonDict:
        return {"message": str(self), "status_code": self.status_code, "code": self.code}


@dataclass(frozen=True, slots=True)
class IdentitySessionCredential:
    account_id: str
    session_id: str
    session_token: str = field(repr=False)
    expires_at: str

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.session_token}",
            "X-ReleaseFoundry-Session-ID": self.session_id,
        }

    def to_safe_dict(self) -> JsonDict:
        return {
            "account_id": self.account_id,
            "session_id": self.session_id,
            "expires_at": self.expires_at,
            "session_token_present": bool(self.session_token),
        }


@dataclass(frozen=True, slots=True)
class IdentityChallenge:
    challenge_id: str
    purpose: str
    delivery_method: str
    delivery_hint: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class MFARequired:
    mfa_challenge_id: str
    expires_at: str
    status: Literal["mfa_required"] = "mfa_required"


@dataclass(frozen=True, slots=True)
class OAuthBegin:
    flow_id: str
    provider: str
    intent: OAuthIntent
    authorization_url: str = field(repr=False)
    expires_at: str = ""

    def to_safe_dict(self) -> JsonDict:
        return {
            "flow_id": self.flow_id,
            "provider": self.provider,
            "intent": self.intent,
            "expires_at": self.expires_at,
            "authorization_url_present": bool(self.authorization_url),
        }


@dataclass(frozen=True, slots=True)
class OAuthBindingTicket:
    binding_ticket_id: str
    binding_ticket_proof: str = field(repr=False)
    provider: str = ""
    expires_at: str = ""

    def to_safe_dict(self) -> JsonDict:
        return {
            "binding_ticket_id": self.binding_ticket_id,
            "provider": self.provider,
            "expires_at": self.expires_at,
            "binding_ticket_proof_present": bool(self.binding_ticket_proof),
        }


@dataclass(frozen=True, slots=True)
class IdentityCredentialView:
    provider: str
    kind: str


@dataclass(frozen=True, slots=True)
class TwoFactorView:
    enabled: bool
    recommended: bool
    methods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    provider: str
    kind: str
    enabled: bool
    region: str
    supports_registration: bool
    supports_login: bool
    supports_explicit_binding: bool
    pkce_required: bool


@dataclass(frozen=True, slots=True)
class IdentityView:
    account_id: str
    primary_email_hint: str
    display_name: str
    locale: str
    region: str
    status: str
    preferred_registration_method: str
    credentials: tuple[IdentityCredentialView, ...]
    two_factor: TwoFactorView
    provider_capabilities: tuple[ProviderCapability, ...]


IdentityAuthResult = IdentitySessionCredential | MFARequired
OAuthCompletion = IdentityView | IdentityAuthResult | OAuthBindingTicket


class IdentityClient:
    def __init__(
        self,
        *,
        base_url: str = IDENTITY_DEFAULT_BASE_URL,
        timeout: int = 30,
        transport: IdentityTransport | None = None,
        session: IdentitySessionCredential | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = max(1, int(timeout))
        self._transport = transport or _urlopen_identity_transport
        self._session = session

    def with_session(self, session: IdentitySessionCredential | None) -> "IdentityClient":
        return IdentityClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self._transport,
            session=session,
        )

    def begin_email_registration(self, email: str, *, locale: str = "", region: str = "") -> IdentityChallenge:
        payload: JsonDict = {"email": email}
        if locale:
            payload["locale"] = locale
        if region:
            payload["region"] = region
        return _parse_challenge(self._request("POST", "/v1/identity/registration/email/begin", payload))

    def complete_email_registration(self, challenge_id: str, proof: str, *, display_name: str = "") -> IdentityView:
        payload: JsonDict = {"challenge_id": challenge_id, "proof": proof}
        if display_name:
            payload["display_name"] = display_name
        response = self._request("POST", "/v1/identity/registration/email/complete", payload)
        return _parse_identity(_object(response.get("identity"), "identity"))

    def begin_email_login(self, email: str) -> IdentityChallenge:
        return _parse_challenge(self._request("POST", "/v1/identity/login/email/begin", {"email": email}))

    def complete_email_login(self, challenge_id: str, proof: str) -> IdentityAuthResult:
        response = self._request(
            "POST",
            "/v1/identity/login/email/complete",
            {"challenge_id": challenge_id, "proof": proof},
        )
        return _parse_auth(response)

    def complete_mfa(self, challenge_id: str, proof: str) -> IdentitySessionCredential:
        result = _parse_auth(
            self._request("POST", "/v1/identity/mfa/complete", {"challenge_id": challenge_id, "proof": proof})
        )
        if isinstance(result, MFARequired):
            raise IdentityClientError("MFA completion returned another MFA challenge", code="invalid_response")
        return result

    def begin_oauth(
        self,
        provider: str,
        intent: OAuthIntent,
        redirect_uri: str,
        *,
        session: IdentitySessionCredential | None = None,
    ) -> OAuthBegin:
        if intent not in ("registration", "login", "link"):
            raise ValueError("intent must be registration, login, or link")
        response = self._request(
            "POST",
            "/v1/identity/oauth/begin",
            {"provider": provider, "intent": intent, "redirect_uri": redirect_uri},
            session=self._required_session(session) if intent == "link" else None,
        )
        return OAuthBegin(
            flow_id=_string(response, "flow_id"),
            provider=_string(response, "provider"),
            intent=cast(OAuthIntent, _string(response, "intent")),
            authorization_url=_string(response, "authorization_url"),
            expires_at=_string(response, "expires_at"),
        )

    def complete_oauth(
        self,
        flow_id: str,
        state: str,
        code: str,
        *,
        registration_display_name: str = "",
        registration_locale: str = "",
        registration_region: str = "",
    ) -> OAuthCompletion:
        payload: JsonDict = {"flow_id": flow_id, "state": state, "code": code}
        if registration_display_name:
            payload["display_name"] = registration_display_name
        if registration_locale:
            payload["locale"] = registration_locale
        if registration_region:
            payload["region"] = registration_region
        response = self._request("POST", "/v1/identity/oauth/complete", payload)
        status = _string(response, "status")
        if status in ("registered", "bound"):
            return _parse_identity(_object(response.get("identity"), "identity"))
        if status in ("authenticated", "mfa_required"):
            return _parse_auth(response)
        if status == "binding_ticket_issued":
            return OAuthBindingTicket(
                binding_ticket_id=_string(response, "binding_ticket_id"),
                binding_ticket_proof=_string(response, "binding_ticket_proof"),
                provider=_string(response, "provider"),
                expires_at=_string(response, "expires_at"),
            )
        raise IdentityClientError("unexpected OAuth completion response", code="invalid_response")

    def bind_credential(
        self,
        ticket: OAuthBindingTicket,
        *,
        explicit_consent: bool,
        session: IdentitySessionCredential | None = None,
    ) -> IdentityView:
        if not explicit_consent:
            raise ValueError("explicit_consent must be true")
        response = self._request(
            "POST",
            "/v1/identity/credentials/bind",
            {
                "binding_ticket_id": ticket.binding_ticket_id,
                "binding_ticket_proof": ticket.binding_ticket_proof,
                "explicit_consent": True,
            },
            session=self._required_session(session),
        )
        return _parse_identity(_object(response.get("identity"), "identity"))

    def me(self, *, session: IdentitySessionCredential | None = None) -> IdentityView:
        return _parse_identity(self._request("GET", "/v1/me", session=self._required_session(session)))

    def revoke_session(self, *, session: IdentitySessionCredential | None = None) -> None:
        response = self._request(
            "POST",
            "/v1/identity/sessions/revoke",
            {},
            session=self._required_session(session),
        )
        if _string(response, "status") != "revoked":
            raise IdentityClientError("unexpected session revoke response", code="invalid_response")

    def _required_session(self, session: IdentitySessionCredential | None) -> IdentitySessionCredential:
        selected = session or self._session
        if selected is None:
            raise IdentityClientError("authenticated session is required", code="session_required")
        return selected

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        session: IdentitySessionCredential | None = None,
    ) -> JsonDict:
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if session is not None:
            headers.update(session.headers())
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
        try:
            raw_response = self._transport(method, f"{self.base_url}{path}", headers, body, self.timeout)
        except IdentityClientError:
            raise
        except Exception as exc:
            raise IdentityClientError("identity transport failed", code="transport_error") from exc
        if len(raw_response) == 2:
            status_code, raw_body = raw_response
        else:
            status_code, raw_body, _ = raw_response
        try:
            decoded = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IdentityClientError("identity service returned invalid JSON", status_code=status_code, code="invalid_response") from exc
        response = _object(decoded, "response")
        if status_code < 200 or status_code >= 300:
            error = response.get("error")
            safe_error = error if isinstance(error, Mapping) else {}
            raise IdentityClientError(
                str(safe_error.get("message") or "identity request failed"),
                status_code=status_code,
                code=str(safe_error.get("code") or "identity_request_failed"),
            )
        if response.get("schema_version") != IDENTITY_SCHEMA_VERSION:
            raise IdentityClientError("unsupported identity schema version", status_code=status_code, code="invalid_response")
        return response


def _parse_challenge(response: Mapping[str, Any]) -> IdentityChallenge:
    return IdentityChallenge(
        challenge_id=_string(response, "challenge_id"),
        purpose=_string(response, "purpose"),
        delivery_method=_string(response, "delivery_method"),
        delivery_hint=_string(response, "delivery_hint"),
        expires_at=_string(response, "expires_at"),
    )


def _parse_auth(response: Mapping[str, Any]) -> IdentityAuthResult:
    status = _string(response, "status")
    if status == "mfa_required":
        return MFARequired(
            mfa_challenge_id=_string(response, "mfa_challenge_id"),
            expires_at=_string(response, "expires_at"),
        )
    if status != "authenticated":
        raise IdentityClientError("unexpected authentication response", code="invalid_response")
    return IdentitySessionCredential(
        account_id=_string(response, "account_id"),
        session_id=_string(response, "session_id"),
        session_token=_string(response, "session_token"),
        expires_at=_string(response, "expires_at"),
    )


def _parse_identity(value: Mapping[str, Any]) -> IdentityView:
    credentials = tuple(
        IdentityCredentialView(provider=_string(_object(item, "credential"), "provider"), kind=_string(_object(item, "credential"), "kind"))
        for item in _list(value, "credentials")
    )
    raw_two_factor = _object(value.get("two_factor"), "two_factor")
    capabilities = tuple(
        ProviderCapability(
            provider=_string(raw, "provider"),
            kind=_string(raw, "kind"),
            enabled=_boolean(raw, "enabled"),
            region=_string(raw, "region"),
            supports_registration=_boolean(raw, "supports_registration"),
            supports_login=_boolean(raw, "supports_login"),
            supports_explicit_binding=_boolean(raw, "supports_explicit_binding"),
            pkce_required=_boolean(raw, "pkce_required"),
        )
        for raw in (_object(item, "provider_capability") for item in _list(value, "provider_capabilities"))
    )
    return IdentityView(
        account_id=_string(value, "account_id"),
        primary_email_hint=_string(value, "primary_email_hint"),
        display_name=str(value.get("display_name") or ""),
        locale=_string(value, "locale"),
        region=_string(value, "region"),
        status=_string(value, "status"),
        preferred_registration_method=_string(value, "preferred_registration_method"),
        credentials=credentials,
        two_factor=TwoFactorView(
            enabled=_boolean(raw_two_factor, "enabled"),
            recommended=_boolean(raw_two_factor, "recommended"),
            methods=tuple(str(item) for item in _list(raw_two_factor, "methods")),
        ),
        provider_capabilities=capabilities,
    )


def _object(value: Any, name: str) -> JsonDict:
    if not isinstance(value, Mapping):
        raise IdentityClientError(f"{name} must be an object", code="invalid_response")
    return dict(value)


def _list(value: Mapping[str, Any], key: str) -> list[Any]:
    selected = value.get(key)
    if not isinstance(selected, list):
        raise IdentityClientError(f"{key} must be an array", code="invalid_response")
    return selected


def _string(value: Mapping[str, Any], key: str) -> str:
    selected = value.get(key)
    if not isinstance(selected, str) or not selected:
        raise IdentityClientError(f"{key} must be a non-empty string", code="invalid_response")
    return selected


def _boolean(value: Mapping[str, Any], key: str) -> bool:
    selected = value.get(key)
    if not isinstance(selected, bool):
        raise IdentityClientError(f"{key} must be a boolean", code="invalid_response")
    return selected


def _urlopen_identity_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: int,
) -> IdentityTransportResponse:
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())
    except URLError as exc:
        raise IdentityClientError("identity service is unreachable", code="transport_error") from exc
