from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
import argparse
import json
import re
import ssl
import sys
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


BROWSER_SESSION_SCHEMA_VERSION = "ashr.clone.browser_session.v1"
BROWSER_SESSION_OPENAPI_SCHEMA_VERSION = "ashr.clone.browser_session.openapi.v1"
BROWSER_SESSION_CAPABILITY_SCHEMA_VERSION = (
    "ashr.clone.browser_session.capabilities.v1"
)
BROWSER_SESSION_OPENAPI_VERSION = "3.1.0"
BROWSER_SESSION_COOKIE_NAMES = (
    "__Host-ashr_session",
    "__Host-ashr_refresh",
)
BROWSER_SESSION_MODALITIES = ("text", "image", "audio", "file", "video")
BROWSER_SESSION_ACCESS_MAX_AGE_SECONDS = 24 * 60 * 60
BROWSER_SESSION_REFRESH_MAX_AGE_SECONDS = 90 * 24 * 60 * 60

BROWSER_SESSION_ERROR_CODES = (
    "browser_session_authentication_required",
    "browser_session_cookie_expired",
    "browser_session_idempotency_conflict",
    "browser_session_invalid_request",
    "browser_session_rate_limited",
    "browser_session_response_invalid",
    "browser_session_transport_failed",
    "browser_session_unavailable",
    "credential_link_conflict",
    "identity_session_handoff_failed",
    "identity_session_refresh_idempotency_required",
    "identity_session_refresh_invalid",
    "identity_session_refresh_origin_rejected",
    "identity_session_refresh_request_invalid",
    "identity_session_refresh_reused",
    "identity_session_refresh_unavailable",
    "identity_session_secure_transport_required",
    "identity_session_transport_unavailable",
    "identity_verification_failed",
    "identity_verification_policy_unavailable",
    "identity_verification_unavailable",
    "request_cancelled",
    "verification_code_invalid",
    "verification_consumed",
    "verification_expired",
    "verification_not_found",
    "verification_resend_cooldown",
)

_ERROR_DETAILS: dict[str, tuple[int, bool, str]] = {
    "browser_session_authentication_required": (
        401,
        False,
        "browser session authentication is required",
    ),
    "browser_session_cookie_expired": (
        401,
        False,
        "browser session cookie has expired",
    ),
    "browser_session_idempotency_conflict": (
        409,
        False,
        "idempotency key conflicts with an earlier request",
    ),
    "browser_session_invalid_request": (
        400,
        False,
        "browser session request is invalid",
    ),
    "browser_session_rate_limited": (
        429,
        True,
        "browser session request was rate limited",
    ),
    "browser_session_response_invalid": (
        502,
        True,
        "browser session response is invalid",
    ),
    "browser_session_transport_failed": (
        502,
        True,
        "browser session transport failed",
    ),
    "browser_session_unavailable": (
        503,
        True,
        "browser session service is unavailable",
    ),
    "credential_link_conflict": (409, False, "credential is already linked"),
    "identity_session_handoff_failed": (
        500,
        True,
        "identity session handoff failed",
    ),
    "identity_session_refresh_idempotency_required": (
        400,
        False,
        "identity session refresh requires a valid idempotency key",
    ),
    "identity_session_refresh_invalid": (
        401,
        False,
        "identity session refresh could not be authenticated",
    ),
    "identity_session_refresh_origin_rejected": (
        403,
        False,
        "identity session refresh origin was rejected",
    ),
    "identity_session_refresh_request_invalid": (
        400,
        False,
        "identity session refresh request is invalid",
    ),
    "identity_session_refresh_reused": (
        409,
        False,
        "identity session refresh credential was reused",
    ),
    "identity_session_refresh_unavailable": (
        503,
        True,
        "identity session refresh is not configured",
    ),
    "identity_session_secure_transport_required": (
        426,
        False,
        "identity session requires HTTPS",
    ),
    "identity_session_transport_unavailable": (
        503,
        True,
        "identity session handoff is not configured",
    ),
    "identity_verification_failed": (
        500,
        True,
        "identity verification failed",
    ),
    "identity_verification_policy_unavailable": (
        503,
        True,
        "identity verification policy is unavailable",
    ),
    "identity_verification_unavailable": (
        503,
        True,
        "identity verification is unavailable",
    ),
    "request_cancelled": (408, True, "browser session request was cancelled"),
    "verification_code_invalid": (
        401,
        False,
        "identity verification proof is invalid",
    ),
    "verification_consumed": (
        401,
        False,
        "identity verification proof is invalid",
    ),
    "verification_expired": (
        401,
        False,
        "identity verification proof has expired",
    ),
    "verification_not_found": (
        401,
        False,
        "identity verification proof is invalid",
    ),
    "verification_resend_cooldown": (
        429,
        True,
        "identity verification is rate limited",
    ),
}

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{7,254}$")
_CHANNELS = ("email", "phone")
_SUCCESS_STATUSES: dict[str, frozenset[int]] = {
    "complete_login": frozenset({200, 303}),
    "bootstrap": frozenset({200, 204}),
    "refresh": frozenset({200, 204}),
    "logout": frozenset({204}),
    "revoke_all": frozenset({204}),
}
_OPERATION_STATUS = {
    "complete_login": "authenticated",
    "bootstrap": "active",
    "refresh": "rotated",
    "logout": "logged_out",
    "revoke_all": "revoked_all",
}


class BrowserSessionError(RuntimeError):
    """Stable public-safe browser-session failure."""

    def __init__(
        self,
        code: str,
        *,
        status: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        if code not in _ERROR_DETAILS:
            code = "browser_session_transport_failed"
        default_status, retryable, message = _ERROR_DETAILS[code]
        self.code = code
        self.status = default_status if status is None else int(status)
        self.retryable = retryable
        self.retry_after_seconds = _optional_retry_after(retry_after_seconds)
        super().__init__(message)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BROWSER_SESSION_SCHEMA_VERSION,
            "status": "error",
            "error": {
                "code": self.code,
                "message": str(self),
                "http_status": self.status,
                "retryable": self.retryable,
                "retry_after_seconds": self.retry_after_seconds,
            },
        }

    def __repr__(self) -> str:
        return (
            f"BrowserSessionError(code={self.code!r}, status={self.status!r}, "
            f"retryable={self.retryable!r})"
        )


@dataclass(frozen=True)
class BrowserHTTPResponse:
    status: int
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | str | Mapping[str, Any] | None = None

    @classmethod
    def create(
        cls,
        status: int,
        *,
        headers: Mapping[str, str | Sequence[str]]
        | Sequence[tuple[str, str]]
        | None = None,
        body: bytes | str | Mapping[str, Any] | None = None,
    ) -> "BrowserHTTPResponse":
        return cls(int(status), _normalize_response_headers(headers), body)

    def header_values(self, name: str) -> tuple[str, ...]:
        lowered = name.lower()
        return tuple(value for key, value in self.headers if key.lower() == lowered)


BrowserSessionTransport = Callable[
    [str, str, Mapping[str, str], bytes | None], BrowserHTTPResponse
]


@dataclass(frozen=True)
class BrowserCookieDescriptor:
    name: str
    expires_at: datetime
    max_age_seconds: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expires_at": _timestamp(self.expires_at),
            "max_age_seconds": self.max_age_seconds,
            "path": "/",
            "secure": True,
            "http_only": True,
            "same_site": "Strict",
            "host_only": True,
            "credential_present": True,
        }


@dataclass(frozen=True)
class BrowserCookieReplacement:
    issued_at: datetime
    access: BrowserCookieDescriptor
    refresh: BrowserCookieDescriptor
    replayed_at: datetime | None = None

    def replay(self, replayed_at: datetime | str) -> "BrowserCookieReplacement":
        replay_time = _datetime("replayed_at", replayed_at)
        if replay_time < self.issued_at:
            raise BrowserSessionError("browser_session_invalid_request")
        return BrowserCookieReplacement(
            issued_at=self.issued_at,
            access=_replayed_descriptor(self.access, replay_time),
            refresh=_replayed_descriptor(self.refresh, replay_time),
            replayed_at=replay_time,
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BROWSER_SESSION_SCHEMA_VERSION,
            "issued_at": _timestamp(self.issued_at),
            "replayed_at": (
                None if self.replayed_at is None else _timestamp(self.replayed_at)
            ),
            "cookies": [
                self.access.to_public_dict(),
                self.refresh.to_public_dict(),
            ],
            "replacement_is_atomic": True,
            "expires_is_stable_across_replay": True,
            "max_age_decreases_with_elapsed_seconds": True,
            "contains_credential_values": False,
        }


def build_browser_cookie_replacement(
    *,
    issued_at: datetime | str,
    access_expires_at: datetime | str,
    refresh_expires_at: datetime | str,
    access_cap_seconds: int = BROWSER_SESSION_ACCESS_MAX_AGE_SECONDS,
    refresh_cap_seconds: int = 30 * 24 * 60 * 60,
) -> BrowserCookieReplacement:
    issued = _datetime("issued_at", issued_at)
    access_expiry = _datetime("access_expires_at", access_expires_at)
    refresh_expiry = _datetime("refresh_expires_at", refresh_expires_at)
    access_cap = _bounded_int(
        "access_cap_seconds",
        access_cap_seconds,
        1,
        BROWSER_SESSION_ACCESS_MAX_AGE_SECONDS,
    )
    refresh_cap = _bounded_int(
        "refresh_cap_seconds",
        refresh_cap_seconds,
        1,
        BROWSER_SESSION_REFRESH_MAX_AGE_SECONDS,
    )
    effective_access = min(access_expiry, issued + timedelta(seconds=access_cap))
    effective_refresh = min(refresh_expiry, issued + timedelta(seconds=refresh_cap))
    access_max_age = int((effective_access - issued).total_seconds())
    refresh_max_age = int((effective_refresh - issued).total_seconds())
    if access_max_age < 1 or refresh_max_age < 1 or effective_refresh <= effective_access:
        raise BrowserSessionError("browser_session_invalid_request")
    return BrowserCookieReplacement(
        issued_at=issued,
        access=BrowserCookieDescriptor(
            BROWSER_SESSION_COOKIE_NAMES[0], effective_access, access_max_age
        ),
        refresh=BrowserCookieDescriptor(
            BROWSER_SESSION_COOKIE_NAMES[1], effective_refresh, refresh_max_age
        ),
    )


@dataclass
class _StoredCookie:
    value: str
    expires_at: datetime


class BrowserSessionCookieJar:
    """Origin-bound cookie jar whose public representation never exposes values."""

    def __init__(self, origin: str) -> None:
        self._origin = _normalize_origin(origin, allow_insecure_localhost=True)
        self._cookies: dict[str, _StoredCookie] = {}

    def ingest(
        self,
        response: BrowserHTTPResponse,
        *,
        now: datetime | str | None = None,
    ) -> tuple[BrowserCookieDescriptor, ...]:
        current = _now() if now is None else _datetime("now", now)
        mutations: list[
            tuple[str, _StoredCookie | None, BrowserCookieDescriptor]
        ] = []
        descriptors: list[BrowserCookieDescriptor] = []
        for header in response.header_values("set-cookie"):
            parsed = _parse_set_cookie(header, current)
            if parsed is None:
                continue
            mutations.append(parsed)
        next_cookies = dict(self._cookies)
        for name, stored, descriptor in mutations:
            if stored is None:
                next_cookies.pop(name, None)
                continue
            next_cookies[name] = stored
            descriptors.append(descriptor)
        self._cookies = next_cookies
        self._discard_expired(current)
        return tuple(descriptors)

    def clear(self) -> None:
        for name in BROWSER_SESSION_COOKIE_NAMES:
            self._cookies.pop(name, None)

    def to_public_dict(self, *, now: datetime | str | None = None) -> dict[str, Any]:
        current = _now() if now is None else _datetime("now", now)
        self._discard_expired(current)
        return {
            "schema_version": BROWSER_SESSION_SCHEMA_VERSION,
            "management": "sdk_cookie_jar",
            "origin": self._origin,
            "cookie_count": len(self._cookies),
            "access_credential_present": BROWSER_SESSION_COOKIE_NAMES[0]
            in self._cookies,
            "refresh_credential_present": BROWSER_SESSION_COOKIE_NAMES[1]
            in self._cookies,
            "credential_values_exposed": False,
        }

    def __repr__(self) -> str:
        public = self.to_public_dict()
        return (
            "BrowserSessionCookieJar("
            f"origin={public['origin']!r}, cookie_count={public['cookie_count']!r}, "
            "credential_values_exposed=False)"
        )

    def _request_cookie_header(
        self, url: str, *, now: datetime | None = None
    ) -> str | None:
        if _origin_from_url(url) != self._origin:
            raise BrowserSessionError("browser_session_invalid_request")
        current = _now() if now is None else now
        self._discard_expired(current)
        values = [
            f"{name}={self._cookies[name].value}"
            for name in BROWSER_SESSION_COOKIE_NAMES
            if name in self._cookies
        ]
        return "; ".join(values) or None

    def _discard_expired(self, now: datetime) -> None:
        for name, stored in tuple(self._cookies.items()):
            if stored.expires_at <= now:
                del self._cookies[name]


@dataclass(frozen=True)
class BrowserSessionReceipt:
    operation: str
    http_status: int
    status: str
    redirect_to: str | None
    cookie_state: Mapping[str, Any]
    replacement_cookies: tuple[BrowserCookieDescriptor, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BROWSER_SESSION_SCHEMA_VERSION,
            "operation": self.operation,
            "http_status": self.http_status,
            "status": self.status,
            "redirect_to": self.redirect_to,
            "cookie_state": dict(self.cookie_state),
            "replacement_cookies": [
                item.to_public_dict() for item in self.replacement_cookies
            ],
            "credential_values_exposed": False,
        }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class BrowserSessionClient:
    """Cookie-authenticated browser-session client with no credential logging."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: BrowserSessionTransport | None = None,
        cookie_jar: BrowserSessionCookieJar | None = None,
        timeout_seconds: float = 30.0,
        allow_insecure_localhost: bool = False,
    ) -> None:
        self.origin = _normalize_origin(base_url, allow_insecure_localhost)
        self.base_url = self.origin
        self.cookie_jar = cookie_jar or BrowserSessionCookieJar(self.origin)
        if self.cookie_jar._origin != self.origin:
            raise BrowserSessionError("browser_session_invalid_request")
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise BrowserSessionError("browser_session_invalid_request")
        self.timeout_seconds = float(timeout_seconds)
        self._transport = transport or self._default_transport

    def complete_login(
        self,
        *,
        tenant_id: str,
        account_id: str,
        challenge_id: str,
        verification_code: str,
        channel: str,
        identifier: str,
        display_name: str | None = None,
    ) -> BrowserSessionReceipt:
        normalized_channel = str(channel).strip().lower()
        if normalized_channel not in _CHANNELS:
            raise BrowserSessionError("browser_session_invalid_request")
        code = str(verification_code)
        if not code or len(code) > 1024 or "\x00" in code:
            raise BrowserSessionError("browser_session_invalid_request")
        identity = str(identifier).strip()
        if not identity or len(identity) > 512:
            raise BrowserSessionError("browser_session_invalid_request")
        payload: dict[str, Any] = {
            "tenant_id": _identifier("tenant_id", tenant_id),
            "account_id": _identifier("account_id", account_id),
            "challenge_id": _identifier("challenge_id", challenge_id),
            "code": code,
            "channel": normalized_channel,
            "identifier": identity,
            "purpose": "login",
        }
        if display_name is not None:
            display = str(display_name).strip()
            if not display or len(display) > 255:
                raise BrowserSessionError("browser_session_invalid_request")
            payload["display_name"] = display
        return self._request(
            "complete_login",
            "POST",
            browser_session_login_route(),
            payload=payload,
        )

    login_and_bootstrap_session = complete_login

    def bootstrap(self, project_id: str, account_id: str) -> BrowserSessionReceipt:
        return self._request(
            "bootstrap",
            "GET",
            browser_session_bootstrap_route(project_id, account_id),
        )

    def refresh(
        self,
        project_id: str,
        account_id: str,
        *,
        idempotency_key: str,
    ) -> BrowserSessionReceipt:
        return self._request(
            "refresh",
            "POST",
            browser_session_refresh_route(project_id, account_id),
            idempotency_key=idempotency_key,
        )

    def logout(
        self,
        project_id: str,
        account_id: str,
        *,
        idempotency_key: str,
    ) -> BrowserSessionReceipt:
        return self._request(
            "logout",
            "POST",
            browser_session_logout_route(project_id, account_id),
            idempotency_key=idempotency_key,
        )

    def revoke_all(
        self,
        project_id: str,
        account_id: str,
        *,
        idempotency_key: str,
    ) -> BrowserSessionReceipt:
        return self._request(
            "revoke_all",
            "POST",
            browser_session_revoke_all_route(project_id, account_id),
            idempotency_key=idempotency_key,
        )

    revoke_all_sessions = revoke_all

    def _request(
        self,
        operation: str,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> BrowserSessionReceipt:
        if operation not in _SUCCESS_STATUSES:
            raise BrowserSessionError("browser_session_invalid_request")
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Cache-Control": "no-store",
            "Origin": self.origin,
            "Pragma": "no-cache",
            "Sec-Fetch-Site": "same-origin",
        }
        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode(
                "utf-8"
            )
        if idempotency_key is not None:
            headers["Idempotency-Key"] = _idempotency_key(idempotency_key)
        cookie_header = self.cookie_jar._request_cookie_header(url)
        if cookie_header is not None:
            headers["Cookie"] = cookie_header
        try:
            response = self._transport(method, url, headers, body)
        except BrowserSessionError:
            raise
        except Exception as exc:
            raise BrowserSessionError("browser_session_transport_failed") from exc
        if not isinstance(response, BrowserHTTPResponse):
            raise BrowserSessionError("browser_session_response_invalid")
        replacement = self.cookie_jar.ingest(response)
        if response.status not in _SUCCESS_STATUSES[operation]:
            raise _error_from_response(response)
        if operation in {"logout", "revoke_all"}:
            self.cookie_jar.clear()
        redirect_to = None
        if response.status == 303:
            redirect_to = _safe_redirect(
                self.origin, _single_header(response, "location", required=True)
            )
        _validate_success_body(operation, response)
        return BrowserSessionReceipt(
            operation=operation,
            http_status=response.status,
            status=_OPERATION_STATUS[operation],
            redirect_to=redirect_to,
            cookie_state=self.cookie_jar.to_public_dict(),
            replacement_cookies=replacement,
        )

    def _default_transport(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None
    ) -> BrowserHTTPResponse:
        context = ssl.create_default_context()
        opener = build_opener(_NoRedirect(), HTTPSHandler(context=context))
        request = Request(url, data=body, headers=dict(headers), method=method)
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                return BrowserHTTPResponse(
                    status=response.status,
                    headers=tuple(response.headers.items()),
                    body=response.read(1_048_577),
                )
        except HTTPError as exc:
            return BrowserHTTPResponse(
                status=exc.code,
                headers=tuple(exc.headers.items()),
                body=exc.read(1_048_577),
            )
        except (URLError, TimeoutError, OSError) as exc:
            raise BrowserSessionError("browser_session_transport_failed") from exc


def browser_session_login_route() -> str:
    return "/v1/identity-verification/verify"


def browser_session_collection_route(project_id: str, account_id: str) -> str:
    return (
        f"/v1/projects/{_route_segment('project_id', project_id)}"
        f"/accounts/{_route_segment('account_id', account_id)}/browser-sessions"
    )


def browser_session_bootstrap_route(project_id: str, account_id: str) -> str:
    return f"{browser_session_collection_route(project_id, account_id)}/bootstrap"


def browser_session_refresh_route(project_id: str, account_id: str) -> str:
    return f"{browser_session_collection_route(project_id, account_id)}/refresh"


def browser_session_logout_route(project_id: str, account_id: str) -> str:
    return f"{browser_session_collection_route(project_id, account_id)}/logout"


def browser_session_revoke_all_route(project_id: str, account_id: str) -> str:
    return f"{browser_session_collection_route(project_id, account_id)}/revoke-all"


def browser_session_capability_manifest() -> dict[str, Any]:
    operations = [
        {
            "operation": "complete_login",
            "method": "POST",
            "path": browser_session_login_route(),
            "request_fields": [
                "account_id",
                "challenge_id",
                "channel",
                "code",
                "display_name",
                "identifier",
                "purpose",
                "tenant_id",
            ],
            "success_statuses": [200, 303],
            "go_executable": True,
        },
        {
            "operation": "bootstrap",
            "method": "GET",
            "path": "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/bootstrap",
            "request_fields": [],
            "success_statuses": [200, 204],
            "go_executable": False,
        },
        {
            "operation": "refresh",
            "method": "POST",
            "path": "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh",
            "request_fields": [],
            "success_statuses": [200, 204],
            "go_executable": True,
        },
        {
            "operation": "logout",
            "method": "POST",
            "path": "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/logout",
            "request_fields": [],
            "success_statuses": [204],
            "go_executable": False,
        },
        {
            "operation": "revoke_all",
            "method": "POST",
            "path": "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/revoke-all",
            "request_fields": [],
            "success_statuses": [204],
            "go_executable": False,
        },
    ]
    return {
        "schema_version": BROWSER_SESSION_CAPABILITY_SCHEMA_VERSION,
        "sdk_schema_version": BROWSER_SESSION_SCHEMA_VERSION,
        "operations": operations,
        "stable_error_codes": list(BROWSER_SESSION_ERROR_CODES),
        "cookie_names": list(BROWSER_SESSION_COOKIE_NAMES),
        "cookie_contract_fields": [
            "credential_present",
            "expires_at",
            "host_only",
            "http_only",
            "max_age_seconds",
            "name",
            "path",
            "same_site",
            "secure",
        ],
        "receipt_fields": [
            "cookie_state",
            "credential_values_exposed",
            "http_status",
            "operation",
            "redirect_to",
            "replacement_cookies",
            "schema_version",
            "status",
        ],
        "modalities": list(BROWSER_SESSION_MODALITIES),
        "modality_policy": "equal_security_and_transport_envelope",
        "credentials": {
            "http_only": True,
            "secure": True,
            "same_site": "Strict",
            "host_only": True,
            "values_in_public_contract": False,
            "values_in_logs": False,
        },
        "go_known_gaps": [
            "browser_session_bootstrap_route",
            "browser_session_logout_route",
            "browser_session_revoke_all_route",
        ],
    }


def browser_session_openapi_document() -> dict[str, Any]:
    error_schema = {"$ref": "#/components/schemas/BrowserSessionErrorEnvelope"}
    receipt_schema = {"$ref": "#/components/schemas/BrowserSessionReceipt"}

    def response(
        description: str,
        *,
        status: str,
        error_code: str | None = None,
        headers: Mapping[str, Any] | None = None,
        no_content: bool = False,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"description": description}
        if headers:
            result["headers"] = dict(headers)
        if not no_content:
            example = (
                {
                    "schema_version": BROWSER_SESSION_SCHEMA_VERSION,
                    "status": "error",
                    "error": {
                        "code": error_code,
                        "message": _ERROR_DETAILS[error_code][2],
                        "http_status": int(status),
                        "retryable": _ERROR_DETAILS[error_code][1],
                        "retry_after_seconds": None,
                    },
                }
                if error_code
                else {
                    "schema_version": BROWSER_SESSION_SCHEMA_VERSION,
                    "operation": "refresh",
                    "http_status": int(status),
                    "status": "rotated",
                    "redirect_to": None,
                    "cookie_state": {
                        "management": "browser",
                        "credential_values_exposed": False,
                    },
                    "replacement_cookies": [],
                    "credential_values_exposed": False,
                }
            )
            result["content"] = {
                "application/json": {
                    "schema": error_schema if error_code else receipt_schema,
                    "examples": {"public_safe": {"value": example}},
                }
            }
        return result

    set_cookie = {"$ref": "#/components/headers/SetCookie"}
    no_store = {"$ref": "#/components/headers/CacheControl"}
    retry_after = {"$ref": "#/components/headers/RetryAfter"}
    common_headers = {"Cache-Control": no_store, "Set-Cookie": set_cookie}
    common_errors = {
        "401": response(
            "Authentication failed; credential cookies are never echoed.",
            status="401",
            error_code="browser_session_authentication_required",
            headers=common_headers,
        ),
        "409": response(
            "Refresh reuse or idempotency conflict.",
            status="409",
            error_code="identity_session_refresh_reused",
            headers=common_headers,
        ),
        "429": response(
            "Rate limit reached.",
            status="429",
            error_code="browser_session_rate_limited",
            headers={"Cache-Control": no_store, "Retry-After": retry_after},
        ),
        "503": response(
            "Browser-session service is unavailable.",
            status="503",
            error_code="browser_session_unavailable",
            headers={"Cache-Control": no_store},
        ),
    }
    path_parameters = [
        {"$ref": "#/components/parameters/ProjectId"},
        {"$ref": "#/components/parameters/AccountId"},
    ]
    idempotency_headers = [
        {"$ref": "#/components/parameters/IdempotencyKey"},
        {"$ref": "#/components/parameters/Origin"},
        {"$ref": "#/components/parameters/SecFetchSite"},
    ]
    cookie_security = [{"browserAccessCookie": [], "browserRefreshCookie": []}]

    paths: dict[str, Any] = {
        browser_session_login_route(): {
            "post": {
                "operationId": "completeBrowserSessionLogin",
                "summary": "Complete verified login and establish secure browser cookies",
                "security": [],
                "parameters": [{"$ref": "#/components/parameters/Origin"}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/BrowserSessionLoginRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "200": response(
                        "Login completed and cookies were replaced atomically.",
                        status="200",
                        headers=common_headers,
                    ),
                    "303": {
                        "description": "Login completed; continue at a validated same-origin location.",
                        "headers": {
                            **common_headers,
                            "Location": {"$ref": "#/components/headers/Location"},
                        },
                    },
                    **common_errors,
                },
                "x-ashr-modalities": list(BROWSER_SESSION_MODALITIES),
            }
        },
        "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/bootstrap": {
            "get": {
                "operationId": "bootstrapBrowserSession",
                "summary": "Resolve the current cookie-authenticated browser session",
                "security": [{"browserAccessCookie": []}],
                "parameters": path_parameters,
                "responses": {
                    "200": response(
                        "Current browser session is active.",
                        status="200",
                        headers={"Cache-Control": no_store},
                    ),
                    "204": response(
                        "Browser session is valid and has no public body.",
                        status="204",
                        headers={"Cache-Control": no_store},
                        no_content=True,
                    ),
                    "401": common_errors["401"],
                    "503": common_errors["503"],
                },
                "x-ashr-modalities": list(BROWSER_SESSION_MODALITIES),
            }
        },
        "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/refresh": {
            "post": {
                "operationId": "refreshBrowserSession",
                "summary": "Rotate access and refresh cookies atomically",
                "security": cookie_security,
                "parameters": [*path_parameters, *idempotency_headers],
                "responses": {
                    "200": response(
                        "Browser session rotated.",
                        status="200",
                        headers=common_headers,
                    ),
                    "204": response(
                        "Browser session rotated with no public body.",
                        status="204",
                        headers=common_headers,
                        no_content=True,
                    ),
                    **common_errors,
                },
                "x-ashr-modalities": list(BROWSER_SESSION_MODALITIES),
            }
        },
        "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/logout": {
            "post": {
                "operationId": "logoutBrowserSession",
                "summary": "Revoke the current session and clear both cookies",
                "security": [{"browserAccessCookie": []}],
                "parameters": [*path_parameters, *idempotency_headers],
                "responses": {
                    "204": response(
                        "Current session revoked and cookies cleared.",
                        status="204",
                        headers=common_headers,
                        no_content=True,
                    ),
                    "401": common_errors["401"],
                    "409": common_errors["409"],
                    "429": common_errors["429"],
                    "503": common_errors["503"],
                },
                "x-ashr-modalities": list(BROWSER_SESSION_MODALITIES),
            }
        },
        "/v1/projects/{project_id}/accounts/{account_id}/browser-sessions/revoke-all": {
            "post": {
                "operationId": "revokeAllBrowserSessions",
                "summary": "Revoke every account session and clear both cookies",
                "security": [{"browserAccessCookie": []}],
                "parameters": [*path_parameters, *idempotency_headers],
                "responses": {
                    "204": response(
                        "All account sessions revoked and cookies cleared.",
                        status="204",
                        headers=common_headers,
                        no_content=True,
                    ),
                    "401": common_errors["401"],
                    "409": common_errors["409"],
                    "429": common_errors["429"],
                    "503": common_errors["503"],
                },
                "x-ashr-modalities": list(BROWSER_SESSION_MODALITIES),
            }
        },
    }

    return {
        "openapi": BROWSER_SESSION_OPENAPI_VERSION,
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "info": {
            "title": "Ashr Clone Browser Session API",
            "version": "1.0.0",
            "description": "Public-safe cookie session contract; credential values are never examples or response fields.",
        },
        "servers": [{"url": "https://api.example.invalid"}],
        "tags": [{"name": "BrowserSession"}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "browserAccessCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": BROWSER_SESSION_COOKIE_NAMES[0],
                    "description": "Secure HttpOnly host-only access credential.",
                },
                "browserRefreshCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": BROWSER_SESSION_COOKIE_NAMES[1],
                    "description": "Secure HttpOnly host-only refresh credential.",
                },
            },
            "parameters": {
                "ProjectId": {
                    "name": "project_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "pattern": _IDENTIFIER_PATTERN.pattern},
                },
                "AccountId": {
                    "name": "account_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "pattern": _IDENTIFIER_PATTERN.pattern},
                },
                "IdempotencyKey": {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "schema": {
                        "type": "string",
                        "minLength": 8,
                        "maxLength": 255,
                        "pattern": _IDEMPOTENCY_PATTERN.pattern,
                    },
                },
                "Origin": {
                    "name": "Origin",
                    "in": "header",
                    "required": True,
                    "schema": {"type": "string", "format": "uri"},
                },
                "SecFetchSite": {
                    "name": "Sec-Fetch-Site",
                    "in": "header",
                    "required": False,
                    "schema": {"type": "string", "const": "same-origin"},
                },
            },
            "headers": {
                "CacheControl": {
                    "description": "Session responses are never cacheable.",
                    "schema": {"type": "string", "const": "no-store"},
                },
                "Location": {
                    "description": "Validated same-origin continuation path.",
                    "schema": {"type": "string", "pattern": "^/"},
                },
                "RetryAfter": {
                    "description": "Whole seconds before retry.",
                    "schema": {"type": "integer", "minimum": 1},
                },
                "SetCookie": {
                    "description": "Atomic secure HttpOnly cookie replacement or deletion. Values are intentionally absent from examples.",
                    "schema": {"type": "string", "writeOnly": True},
                },
            },
            "schemas": {
                "BrowserSessionLoginRequest": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "tenant_id",
                        "account_id",
                        "challenge_id",
                        "code",
                        "channel",
                        "identifier",
                        "purpose",
                    ],
                    "properties": {
                        "tenant_id": {"type": "string"},
                        "account_id": {"type": "string"},
                        "challenge_id": {"type": "string"},
                        "code": {
                            "type": "string",
                            "writeOnly": True,
                            "description": "One-time proof; never logged or returned.",
                        },
                        "channel": {"type": "string", "enum": list(_CHANNELS)},
                        "identifier": {"type": "string", "writeOnly": True},
                        "purpose": {"type": "string", "const": "login"},
                        "display_name": {"type": "string", "maxLength": 255},
                    },
                },
                "BrowserSessionCookieState": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["credential_values_exposed"],
                    "properties": {
                        "credential_values_exposed": {"type": "boolean", "const": False},
                        "access_credential_present": {"type": "boolean"},
                        "refresh_credential_present": {"type": "boolean"},
                    },
                },
                "BrowserSessionReplacementCookie": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "name",
                        "expires_at",
                        "max_age_seconds",
                        "path",
                        "secure",
                        "http_only",
                        "same_site",
                        "host_only",
                        "credential_present",
                    ],
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": list(BROWSER_SESSION_COOKIE_NAMES),
                        },
                        "expires_at": {"type": "string", "format": "date-time"},
                        "max_age_seconds": {"type": "integer", "minimum": 1},
                        "path": {"type": "string", "const": "/"},
                        "secure": {"type": "boolean", "const": True},
                        "http_only": {"type": "boolean", "const": True},
                        "same_site": {"type": "string", "const": "Strict"},
                        "host_only": {"type": "boolean", "const": True},
                        "credential_present": {"type": "boolean", "const": True},
                    },
                },
                "BrowserSessionReceipt": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "schema_version",
                        "operation",
                        "http_status",
                        "status",
                        "redirect_to",
                        "cookie_state",
                        "replacement_cookies",
                        "credential_values_exposed",
                    ],
                    "properties": {
                        "schema_version": {
                            "type": "string",
                            "const": BROWSER_SESSION_SCHEMA_VERSION,
                        },
                        "operation": {
                            "type": "string",
                            "enum": list(_SUCCESS_STATUSES),
                        },
                        "http_status": {"type": "integer"},
                        "status": {"type": "string"},
                        "redirect_to": {"type": ["string", "null"]},
                        "cookie_state": {
                            "$ref": "#/components/schemas/BrowserSessionCookieState"
                        },
                        "replacement_cookies": {
                            "type": "array",
                            "items": {
                                "$ref": "#/components/schemas/BrowserSessionReplacementCookie"
                            },
                        },
                        "credential_values_exposed": {
                            "type": "boolean",
                            "const": False,
                        },
                    },
                },
                "BrowserSessionError": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "code",
                        "message",
                        "http_status",
                        "retryable",
                        "retry_after_seconds",
                    ],
                    "properties": {
                        "code": {
                            "type": "string",
                            "enum": list(BROWSER_SESSION_ERROR_CODES),
                        },
                        "message": {"type": "string"},
                        "http_status": {"type": "integer"},
                        "retryable": {"type": "boolean"},
                        "retry_after_seconds": {"type": ["integer", "null"]},
                    },
                },
                "BrowserSessionErrorEnvelope": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["schema_version", "status", "error"],
                    "properties": {
                        "schema_version": {
                            "type": "string",
                            "const": BROWSER_SESSION_SCHEMA_VERSION,
                        },
                        "status": {"type": "string", "const": "error"},
                        "error": {"$ref": "#/components/schemas/BrowserSessionError"},
                    },
                },
            },
        },
        "x-ashr-contract-schema-version": BROWSER_SESSION_OPENAPI_SCHEMA_VERSION,
        "x-ashr-modalities": list(BROWSER_SESSION_MODALITIES),
        "x-ashr-public-safe": True,
    }


def _normalize_origin(value: str, allow_insecure_localhost: bool) -> str:
    try:
        parsed = urlsplit(str(value or "").strip())
        port = parsed.port
    except ValueError as exc:
        raise BrowserSessionError("browser_session_invalid_request") from exc
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BrowserSessionError("browser_session_invalid_request")
    if parsed.path not in {"", "/"} or not parsed.hostname or port == 0:
        raise BrowserSessionError("browser_session_invalid_request")
    local = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and local and allow_insecure_localhost
    ):
        raise BrowserSessionError("identity_session_secure_transport_required")
    return f"{parsed.scheme}://{parsed.netloc.lower()}"


def _origin_from_url(value: str) -> str:
    parsed = urlsplit(value)
    return f"{parsed.scheme}://{parsed.netloc.lower()}"


def _route_segment(name: str, value: str) -> str:
    return quote(_identifier(name, value), safe="")


def _identifier(name: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise BrowserSessionError("browser_session_invalid_request")
    return normalized


def _idempotency_key(value: str) -> str:
    normalized = str(value or "")
    if normalized != normalized.strip() or not _IDEMPOTENCY_PATTERN.fullmatch(normalized):
        raise BrowserSessionError("browser_session_invalid_request")
    return normalized


def _bounded_int(name: str, value: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BrowserSessionError("browser_session_invalid_request")
    if value < minimum or value > maximum:
        raise BrowserSessionError("browser_session_invalid_request")
    return value


def _datetime(name: str, value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        resolved = value
    elif isinstance(value, str):
        try:
            resolved = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BrowserSessionError("browser_session_invalid_request") from exc
    else:
        raise BrowserSessionError("browser_session_invalid_request")
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise BrowserSessionError("browser_session_invalid_request")
    return resolved.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _replayed_descriptor(
    descriptor: BrowserCookieDescriptor, replayed_at: datetime
) -> BrowserCookieDescriptor:
    max_age = int((descriptor.expires_at - replayed_at).total_seconds())
    if max_age < 1:
        raise BrowserSessionError("browser_session_cookie_expired")
    return BrowserCookieDescriptor(descriptor.name, descriptor.expires_at, max_age)


def _normalize_response_headers(
    headers: Mapping[str, str | Sequence[str]]
    | Sequence[tuple[str, str]]
    | None,
) -> tuple[tuple[str, str], ...]:
    if headers is None:
        return ()
    pairs: list[tuple[str, str]] = []
    values = headers.items() if isinstance(headers, Mapping) else headers
    for raw_name, raw_value in values:
        name = str(raw_name).strip()
        if not name or any(character in name for character in "\r\n:"):
            raise BrowserSessionError("browser_session_response_invalid")
        expanded = (
            raw_value
            if isinstance(raw_value, Sequence)
            and not isinstance(raw_value, (str, bytes, bytearray))
            else (raw_value,)
        )
        for item in expanded:
            value = str(item)
            if "\r" in value or "\n" in value:
                raise BrowserSessionError("browser_session_response_invalid")
            pairs.append((name, value))
    return tuple(pairs)


def _parse_set_cookie(
    header: str, now: datetime
) -> tuple[str, _StoredCookie | None, BrowserCookieDescriptor] | None:
    cookie = SimpleCookie()
    try:
        cookie.load(header)
    except Exception as exc:
        raise BrowserSessionError("browser_session_response_invalid") from exc
    matching = [name for name in BROWSER_SESSION_COOKIE_NAMES if name in cookie]
    if not matching:
        return None
    if len(matching) != 1 or len(cookie) != 1:
        raise BrowserSessionError("browser_session_response_invalid")
    name = matching[0]
    morsel = cookie[name]
    if (
        morsel["path"] != "/"
        or not morsel["secure"]
        or not morsel["httponly"]
        or morsel["samesite"].lower() != "strict"
        or morsel["domain"]
    ):
        raise BrowserSessionError("browser_session_response_invalid")
    try:
        max_age = int(morsel["max-age"])
    except (TypeError, ValueError) as exc:
        raise BrowserSessionError("browser_session_response_invalid") from exc
    if max_age <= 0:
        descriptor = BrowserCookieDescriptor(name, now, 0)
        return name, None, descriptor
    if not morsel.value or len(morsel.value) > 8192:
        raise BrowserSessionError("browser_session_response_invalid")
    try:
        expires_at = parsedate_to_datetime(morsel["expires"]).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise BrowserSessionError("browser_session_response_invalid") from exc
    expected = now + timedelta(seconds=max_age)
    if abs((expires_at - expected).total_seconds()) > 1.0:
        raise BrowserSessionError("browser_session_response_invalid")
    descriptor = BrowserCookieDescriptor(name, expires_at, max_age)
    return name, _StoredCookie(morsel.value, expires_at), descriptor


def _single_header(
    response: BrowserHTTPResponse, name: str, *, required: bool = False
) -> str | None:
    values = response.header_values(name)
    if len(values) > 1 or (required and len(values) != 1):
        raise BrowserSessionError("browser_session_response_invalid")
    return values[0] if values else None


def _safe_redirect(origin: str, location: str | None) -> str:
    if location is None or not location.strip() or location != location.strip():
        raise BrowserSessionError("browser_session_response_invalid")
    resolved = urljoin(f"{origin}/", location)
    parsed = urlsplit(resolved)
    if _origin_from_url(resolved) != origin or parsed.username or parsed.password:
        raise BrowserSessionError("browser_session_response_invalid")
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def _decode_body(response: BrowserHTTPResponse) -> Mapping[str, Any] | None:
    if response.body is None or (
        isinstance(response.body, (bytes, str)) and response.body in {b"", ""}
    ):
        return None
    if isinstance(response.body, Mapping):
        return dict(response.body)
    raw = response.body.encode("utf-8") if isinstance(response.body, str) else response.body
    if len(raw) > 1_048_576:
        raise BrowserSessionError("browser_session_response_invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrowserSessionError("browser_session_response_invalid") from exc
    if not isinstance(value, Mapping):
        raise BrowserSessionError("browser_session_response_invalid")
    return value


def _validate_success_body(operation: str, response: BrowserHTTPResponse) -> None:
    payload = _decode_body(response)
    if response.status in {204, 303}:
        if payload is not None:
            raise BrowserSessionError("browser_session_response_invalid")
        return
    if payload is None:
        raise BrowserSessionError("browser_session_response_invalid")
    if operation == "refresh" and payload.get("status") != "rotated":
        raise BrowserSessionError("browser_session_response_invalid")


def _error_from_response(response: BrowserHTTPResponse) -> BrowserSessionError:
    payload = _decode_body(response)
    code = "browser_session_transport_failed"
    if payload is not None:
        error = payload.get("error")
        if isinstance(error, Mapping) and isinstance(error.get("code"), str):
            candidate = str(error["code"])
            if candidate in BROWSER_SESSION_ERROR_CODES:
                code = candidate
    if code == "browser_session_transport_failed":
        code = {
            401: "browser_session_authentication_required",
            409: "browser_session_idempotency_conflict",
            429: "browser_session_rate_limited",
            503: "browser_session_unavailable",
        }.get(response.status, code)
    retry_after = _single_header(response, "retry-after")
    parsed_retry: int | None = None
    if retry_after is not None and retry_after.isdigit():
        parsed_retry = int(retry_after)
    return BrowserSessionError(
        code, status=response.status, retry_after_seconds=parsed_retry
    )


def _optional_retry_after(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return min(value, 86_400)


def _cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ashr-clone-browser-session")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("capabilities")
    subparsers.add_parser("openapi")
    cookie = subparsers.add_parser("cookie-contract")
    cookie.add_argument("--issued-at", required=True)
    cookie.add_argument("--access-expires-at", required=True)
    cookie.add_argument("--refresh-expires-at", required=True)
    cookie.add_argument("--access-cap-seconds", type=int, default=86400)
    cookie.add_argument("--refresh-cap-seconds", type=int, default=2592000)
    cookie.add_argument("--replayed-at")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _cli_parser().parse_args(argv)
        if args.command == "capabilities":
            output = browser_session_capability_manifest()
        elif args.command == "openapi":
            output = browser_session_openapi_document()
        else:
            replacement = build_browser_cookie_replacement(
                issued_at=args.issued_at,
                access_expires_at=args.access_expires_at,
                refresh_expires_at=args.refresh_expires_at,
                access_cap_seconds=args.access_cap_seconds,
                refresh_cap_seconds=args.refresh_cap_seconds,
            )
            if args.replayed_at:
                replacement = replacement.replay(args.replayed_at)
            output = replacement.to_public_dict()
        sys.stdout.write(json.dumps(output, indent=2, sort_keys=True) + "\n")
        return 0
    except BrowserSessionError as exc:
        sys.stderr.write(json.dumps(exc.to_public_dict(), sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
