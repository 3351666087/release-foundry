from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Mapping

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from ashr_clone.identity_client import (
    IDENTITY_SCHEMA_VERSION,
    IdentityClient,
    IdentityClientError,
    IdentitySessionCredential,
    MFARequired,
    OAuthBindingTicket,
)


def _identity_view() -> dict[str, Any]:
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "account_id": "account-1",
        "primary_email_hint": "o***@qq.com",
        "display_name": "Owner",
        "locale": "zh-CN",
        "region": "cn",
        "status": "active",
        "preferred_registration_method": "email_magic_link",
        "credentials": [{"provider": "email_magic_link", "kind": "email"}],
        "two_factor": {"enabled": False, "recommended": True, "methods": []},
        "provider_capabilities": [
            {
                "provider": "qq",
                "kind": "oauth2",
                "enabled": True,
                "region": "cn",
                "supports_registration": True,
                "supports_login": True,
                "supports_explicit_binding": True,
                "pkce_required": True,
            },
            {
                "provider": "wechat_open",
                "kind": "oauth2",
                "enabled": True,
                "region": "cn",
                "supports_registration": True,
                "supports_login": True,
                "supports_explicit_binding": True,
                "pkce_required": True,
            },
        ],
    }


class QueueTransport:
    def __init__(self, responses: list[tuple[int, Mapping[str, Any]]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: int,
    ) -> tuple[int, bytes, Mapping[str, str]]:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": json.loads(body) if body is not None else None,
                "timeout": timeout,
            }
        )
        status, payload = self.responses.pop(0)
        return status, json.dumps(payload).encode(), {"Content-Type": "application/json"}


def test_email_registration_and_login_are_separate_and_mfa_is_typed() -> None:
    transport = QueueTransport(
        [
            (
                202,
                {
                    "schema_version": IDENTITY_SCHEMA_VERSION,
                    "challenge_id": "register-challenge",
                    "purpose": "register",
                    "delivery_method": "email",
                    "delivery_hint": "o***@qq.com",
                    "expires_at": "2026-07-14T00:10:00Z",
                },
            ),
            (
                201,
                {
                    "schema_version": IDENTITY_SCHEMA_VERSION,
                    "status": "registered",
                    "identity": _identity_view(),
                },
            ),
            (
                202,
                {
                    "schema_version": IDENTITY_SCHEMA_VERSION,
                    "challenge_id": "login-challenge",
                    "purpose": "login",
                    "delivery_method": "email",
                    "delivery_hint": "o***@qq.com",
                    "expires_at": "2026-07-14T00:10:00Z",
                },
            ),
            (
                202,
                {
                    "schema_version": IDENTITY_SCHEMA_VERSION,
                    "status": "mfa_required",
                    "mfa_challenge_id": "mfa-challenge",
                    "expires_at": "2026-07-14T00:10:00Z",
                },
            ),
        ]
    )
    client = IdentityClient(base_url="https://identity.example", transport=transport)

    challenge = client.begin_email_registration("owner@qq.com")
    identity = client.complete_email_registration(challenge.challenge_id, "register-proof", display_name="Owner")
    login_challenge = client.begin_email_login("owner@qq.com")
    login_result = client.complete_email_login(login_challenge.challenge_id, "login-proof")

    assert identity.account_id == "account-1"
    assert identity.locale == "zh-CN"
    assert identity.region == "cn"
    assert identity.two_factor.recommended is True
    assert {item.provider for item in identity.provider_capabilities} >= {"qq", "wechat_open"}
    assert isinstance(login_result, MFARequired)
    assert [item["url"].split("https://identity.example", 1)[1] for item in transport.requests] == [
        "/v1/identity/registration/email/begin",
        "/v1/identity/registration/email/complete",
        "/v1/identity/login/email/begin",
        "/v1/identity/login/email/complete",
    ]
    assert transport.requests[1]["body"]["proof"] == "register-proof"
    assert transport.requests[3]["body"]["proof"] == "login-proof"


def test_session_and_binding_proofs_are_explicit_and_never_repr_serialized() -> None:
    session = IdentitySessionCredential(
        account_id="account-1",
        session_id="session-1",
        session_token="private-session-token",
        expires_at="2026-07-15T00:00:00Z",
    )
    ticket = OAuthBindingTicket(
        binding_ticket_id="ticket-1",
        binding_ticket_proof="private-binding-proof",
        provider="wechat_open",
        expires_at="2026-07-14T00:10:00Z",
    )
    transport = QueueTransport(
        [
            (
                200,
                {
                    "schema_version": IDENTITY_SCHEMA_VERSION,
                    "status": "bound",
                    "identity": _identity_view(),
                },
            ),
            (200, _identity_view()),
            (200, {"schema_version": IDENTITY_SCHEMA_VERSION, "status": "revoked"}),
        ]
    )
    client = IdentityClient(base_url="https://identity.example", transport=transport, session=session)

    view = client.bind_credential(ticket, explicit_consent=True)
    assert view.account_id == session.account_id
    assert "private-session-token" not in repr(session)
    assert "private-session-token" not in json.dumps(session.to_safe_dict())
    assert "private-binding-proof" not in repr(ticket)
    assert "private-binding-proof" not in json.dumps(ticket.to_safe_dict())
    assert transport.requests[0]["headers"]["Authorization"] == "Bearer private-session-token"
    assert transport.requests[0]["headers"]["X-Ashr-Session-ID"] == "session-1"
    assert transport.requests[0]["body"] == {
        "binding_ticket_id": "ticket-1",
        "binding_ticket_proof": "private-binding-proof",
        "explicit_consent": True,
    }
    assert client.me().account_id == "account-1"
    client.revoke_session()

    with pytest.raises(ValueError, match="explicit_consent"):
        client.bind_credential(ticket, explicit_consent=False)


def test_oauth_intents_and_one_time_values_remain_explicit() -> None:
    session = IdentitySessionCredential("account-1", "session-1", "private-session-token", "2026-07-15T00:00:00Z")
    transport = QueueTransport(
        [
            (
                202,
                {
                    "schema_version": IDENTITY_SCHEMA_VERSION,
                    "flow_id": "flow-link",
                    "provider": "wechat_open",
                    "intent": "link",
                    "authorization_url": "https://provider.example/authorize?state=private-state",
                    "expires_at": "2026-07-14T00:10:00Z",
                },
            ),
            (
                200,
                {
                    "schema_version": IDENTITY_SCHEMA_VERSION,
                    "status": "binding_ticket_issued",
                    "provider": "wechat_open",
                    "binding_ticket_id": "ticket-link",
                    "binding_ticket_proof": "private-ticket-proof",
                    "expires_at": "2026-07-14T00:10:00Z",
                },
            ),
        ]
    )
    client = IdentityClient(base_url="https://identity.example", transport=transport)
    begin = client.begin_oauth(
        "wechat_open",
        "link",
        "https://console.example/oauth/callback",
        session=session,
    )
    completion = client.complete_oauth(begin.flow_id, "private-state", "private-code")

    assert begin.intent == "link"
    assert begin.authorization_url.startswith("https://provider.example/")
    assert "private-state" not in repr(begin)
    assert "private-state" not in json.dumps(begin.to_safe_dict())
    assert isinstance(completion, OAuthBindingTicket)
    assert completion.binding_ticket_id == "ticket-link"
    assert transport.requests[0]["body"] == {
        "provider": "wechat_open",
        "intent": "link",
        "redirect_uri": "https://console.example/oauth/callback",
    }
    assert transport.requests[1]["body"] == {
        "flow_id": "flow-link",
        "state": "private-state",
        "code": "private-code",
    }


def test_errors_are_sanitized_and_schema_mismatch_fails_closed() -> None:
    transport = QueueTransport(
        [
            (
                401,
                {
                    "schema_version": IDENTITY_SCHEMA_VERSION,
                    "status": "error",
                    "error": {
                        "code": "invalid_credentials",
                        "message": 'invalid {"session_token":"private-token"}',
                    },
                },
            ),
            (200, {"schema_version": "future.identity.v2", "status": "revoked"}),
        ]
    )
    client = IdentityClient(base_url="https://identity.example", transport=transport)

    with pytest.raises(IdentityClientError) as captured:
        client.begin_email_login("owner@qq.com")
    assert captured.value.code == "invalid_credentials"
    assert "private-token" not in str(captured.value)

    session = IdentitySessionCredential("account-1", "session-1", "token", "2026-07-15T00:00:00Z")
    with pytest.raises(IdentityClientError, match="schema"):
        client.revoke_session(session=session)
