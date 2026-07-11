from __future__ import annotations

import json
from typing import Mapping
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

from ashr_clone.account_connection import (
    ACCOUNT_CONNECTION_CREDENTIAL_PROVIDERS,
    ACCOUNT_CONNECTION_ERROR_CODES,
    AccountConnection,
    AccountConnectionContractError,
    AccountConnectionDisconnect,
    AccountConnectionError,
    AccountConnectionStart,
    account_connection_contract_manifest,
    validate_google_oidc_public_contract,
)
from ashr_clone.saas import SaaSClientError, SaaSIngestionClient


AUDIENCE = "google-client-id.apps.googleusercontent.com"
CREDENTIAL_ID = "credential_google_local_01"


def _google_authorize_url(**overrides: str) -> str:
    query = {
        "client_id": AUDIENCE,
        "redirect_uri": "http://localhost:8787/oauth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "state": "public-browser-state",
        "nonce": "public-browser-nonce",
        "code_challenge": "pkce-challenge",
        "code_challenge_method": "S256",
    }
    query.update(overrides)
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(query)


def _connection(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "ashr.clone.account_connection.v1",
        "provider": "google",
        "account_id": "account_local",
        "credential_id": CREDENTIAL_ID,
        "provider_subject_present": True,
        "display_name": "Verified User",
        "email_present": True,
        "email_verified": True,
        "connected_at": "2026-07-10T08:00:00Z",
        "disconnected_at": "2026-07-10T08:30:00Z",
    }
    payload.update(overrides)
    return payload


def test_google_manifest_requires_oidc_and_durable_reconnect_guards() -> None:
    manifest = account_connection_contract_manifest()

    assert manifest["providers"] == ["github", "google"]
    assert list(ACCOUNT_CONNECTION_CREDENTIAL_PROVIDERS) == [
        "github", "google", "wechat", "qq", "alipay", "phone", "email"
    ]
    assert manifest["credential_providers"] == list(ACCOUNT_CONNECTION_CREDENTIAL_PROVIDERS)
    assert manifest["google"]["authorization_scopes"] == ["openid", "email", "profile"]
    assert manifest["google"]["issuer_validation"] is True
    assert manifest["google"]["audience_validation"] is True
    assert manifest["google"]["nonce_validation"] is True
    assert manifest["google"]["verified_email_required"] is True
    assert manifest["durability"] == {
        "transaction_store_required": True,
        "atomic_state_consumption_required": True,
        "connection_store_required": True,
        "opaque_token_reference_store_required": True,
        "revocation_outbox_required": True,
        "reconnect_revokes_previous_credential": True,
    }
    assert {
        "invalid_oauth_state",
        "oauth_provider_revoke_failed",
        "oauth_reconnect_revoke_failed",
        "oidc_nonce_mismatch",
        "oauth_email_unverified",
    }.issubset(ACCOUNT_CONNECTION_ERROR_CODES)


def test_google_start_contract_requires_exact_scopes_pkce_state_nonce_and_audience() -> None:
    start = AccountConnectionStart.from_public_response(
        {
            "schema_version": "ashr.google_oauth.v1",
            "provider": "google",
            "authorize_url": _google_authorize_url(),
            "expires_at": "2026-07-10T08:10:00Z",
        },
        expected_provider="google",
        expected_google_audience=AUDIENCE,
    )

    assert start.provider == "google"
    parsed = parse_qs(urlparse(start.authorize_url).query)
    assert set(parsed["scope"][0].split()) == {"openid", "email", "profile"}
    assert parsed["code_challenge_method"] == ["S256"]
    assert parsed["state"] and parsed["nonce"]

    for override, expected in [
        ({"scope": "openid email profile drive.readonly"}, "exactly"),
        ({"code_challenge_method": "plain"}, "PKCE S256"),
        ({"nonce": ""}, "state and nonce"),
        ({"client_id": "wrong.apps.googleusercontent.com"}, "oidc_audience_mismatch"),
    ]:
        with pytest.raises(AccountConnectionContractError, match=expected):
            AccountConnectionStart.from_public_response(
                {
                    "schema_version": "ashr.google_oauth.v1",
                    "provider": "google",
                    "authorize_url": _google_authorize_url(**override),
                    "expires_at": "2026-07-10T08:10:00Z",
                },
                expected_provider="google",
                expected_google_audience=AUDIENCE,
            )


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"issuer": "https://accounts.example.invalid", "issuer_matches": False}, "oidc_issuer_mismatch"),
        ({"audience_matches": False}, "oidc_audience_mismatch"),
        ({"nonce_matches": False}, "oidc_nonce_mismatch"),
        ({"email_verified": False}, "oauth_email_unverified"),
    ],
)
def test_google_oidc_public_contract_fails_closed(
    override: Mapping[str, object], expected: str
) -> None:
    payload: dict[str, object] = {
        "issuer": "https://accounts.google.com",
        "issuer_matches": True,
        "audience_matches": True,
        "nonce_required": True,
        "nonce_matches": True,
        "email_verified": True,
        "raw_nonce_present": False,
        "raw_token_present": False,
    }
    payload.update(override)

    with pytest.raises(AccountConnectionContractError, match=expected):
        validate_google_oidc_public_contract(payload)


def test_google_connection_requires_verified_email_and_opaque_credential() -> None:
    connection = AccountConnection.from_public_response(
        _connection(), expected_provider="google"
    )
    assert connection.email_verified is True
    assert connection.credential_id == CREDENTIAL_ID
    assert connection.provider_subject_present is True
    assert connection.display_name == "Verified User"
    assert "email" not in connection.to_dict()
    assert "provider_subject_sha256" not in connection.to_dict()

    with pytest.raises(AccountConnectionContractError, match="oauth_email_unverified"):
        AccountConnection.from_public_response(
            _connection(email_verified=False), expected_provider="google"
        )
    with pytest.raises(AccountConnectionContractError, match="provider_subject_present"):
        AccountConnection.from_public_response(
            _connection(provider_subject_present=False),
            expected_provider="google",
        )
    with pytest.raises(AccountConnectionContractError, match="credential_id"):
        AccountConnection.from_public_response(
            _connection(credential_id=""),
            expected_provider="google",
        )


def test_github_connection_accepts_provider_neutral_public_contract() -> None:
    connection = AccountConnection.from_public_response(
        _connection(
            provider="github",
            display_name="octocat",
            github_login="octocat",
            email_present=False,
            email_verified=False,
        ),
        expected_provider="github",
    )

    assert connection.provider == "github"
    assert connection.display_name == "octocat"
    assert connection.provider_login == "octocat"
    assert connection.email_present is False
    assert connection.email_verified is False


@pytest.mark.parametrize(
    "forbidden",
    [
        "authorization_code",
        "code_verifier",
        "access_token",
        "refresh_token",
        "id_token",
        "token_ref",
        "provider_subject_sha256",
        "subject_digest",
        "identifier_sha256",
    ],
)
def test_public_contract_rejects_callback_and_token_material(forbidden: str) -> None:
    payload = _connection()
    payload[forbidden] = "must-not-cross-sdk-boundary"
    with pytest.raises(AccountConnectionContractError, match=forbidden):
        AccountConnection.from_public_response(payload, expected_provider="google")


@pytest.mark.parametrize(
    "forbidden",
    ["refresh_token", "provider_subject_sha256", "subject_digest", "identifier_sha256"],
)
def test_public_contract_rejects_nested_secret_or_identity_digest(forbidden: str) -> None:
    payload = _connection(metadata=[{"nested": {forbidden: "must-not-cross"}}])
    with pytest.raises(AccountConnectionContractError, match=forbidden):
        AccountConnection.from_public_response(payload, expected_provider="google")


def test_connection_dto_does_not_retain_recursive_metadata_or_alias_mutations() -> None:
    payload = _connection(metadata={"safe": [{"label": "original"}]})
    connection = AccountConnection.from_public_response(
        payload, expected_provider="google"
    )

    payload["metadata"]["safe"][0]["label"] = "mutated"
    exported = connection.to_dict()
    exported["display_name"] = "mutated"

    assert connection.display_name == "Verified User"
    assert connection.to_dict()["display_name"] == "Verified User"
    assert "metadata" not in connection.to_dict()


@pytest.mark.parametrize(
    "forbidden",
    ["tokenRef", "tokenrefid", "token-ref-id", "revocationOutboxId"],
)
def test_public_contract_rejects_normalized_private_reference_aliases(
    forbidden: str,
) -> None:
    payload = _connection(metadata={"nested": {forbidden: "private-reference"}})
    with pytest.raises(AccountConnectionContractError, match="must not include"):
        AccountConnection.from_public_response(payload, expected_provider="google")


def test_error_shapes_cover_replay_revoke_and_reconnect_without_secret_details() -> None:
    replay = AccountConnectionError.from_public_response(
        {
            "error": {
                "code": "invalid_oauth_state",
                "message": "OAuth state is invalid, expired, or already used",
                "retryable": False,
                "provider": "google",
            }
        }
    )
    assert replay.to_dict()["code"] == "invalid_oauth_state"

    reconnect = AccountConnectionError.from_public_response(
        {
            "error": {
                "code": "oauth_reconnect_revoke_failed",
                "message": "previous provider credential revocation is pending",
                "retryable": True,
                "provider": "google",
                "revocation_pending": True,
            }
        }
    )
    assert reconnect.retryable is True
    assert reconnect.revocation_pending is True

    with pytest.raises(AccountConnectionContractError, match="access_token"):
        AccountConnectionError.from_public_response(
            {
                "error": {
                    "code": "oauth_provider_revoke_failed",
                    "message": "failed",
                    "access_token": "secret",
                }
            }
        )


def test_error_and_identity_display_text_redacts_embedded_secrets_and_email() -> None:
    error = AccountConnectionError.from_public_response(
        {
            "error": {
                "code": "oauth_provider_error",
                "message": (
                    "Bearer header.payload.signature sk-1234567890 "
                    "tp_private_token user@example.invalid"
                ),
                "retryable": False,
            }
        }
    )
    connection = AccountConnection.from_public_response(
        _connection(
            display_name="user@example.invalid",
            provider_login="Bearer header.payload.signature",
        ),
        expected_provider="google",
    )

    serialized = json.dumps(
        {"error": error.to_dict(), "connection": connection.to_dict()}
    )
    assert "header.payload.signature" not in serialized
    assert "sk-1234567890" not in serialized
    assert "tp_private_token" not in serialized
    assert "user@example.invalid" not in serialized
    assert serialized.count("[redacted]") >= 4


def test_disconnect_rejects_outer_or_nested_provider_mismatch() -> None:
    payload = {
        "provider": "github",
        "disconnected": True,
        "revocation_status": "revoked",
        "connection": _connection(provider="github", email_verified=False),
    }
    with pytest.raises(AccountConnectionContractError, match="disconnect response provider mismatch"):
        AccountConnectionDisconnect.from_public_response(
            payload, expected_provider="google"
        )

    payload["provider"] = "google"
    with pytest.raises(AccountConnectionContractError, match="provider mismatch"):
        AccountConnectionDisconnect.from_public_response(
            payload, expected_provider="google"
        )


def test_hosted_client_google_start_connection_and_disconnect_are_provider_neutral_and_public_safe() -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    def transport(
        url: str,
        payload: Mapping[str, object],
        *,
        method: str,
        headers: Mapping[str, str],
    ) -> Mapping[str, object]:
        parsed_url = urlparse(url)
        calls.append((method, parsed_url.path, dict(payload)))
        assert headers == {}
        if method == "GET":
            assert payload == {}
            assert parse_qs(parsed_url.query) == {
                "tenant_id": ["tenant_local"],
                "project_id": ["project_local"],
                "account_id": ["account_local"],
                "provider": ["google"],
            }
        else:
            assert set(payload) == {"tenant_id", "project_id", "account_id", "provider"}
        if parsed_url.path.endswith("/oauth/google/start"):
            return {
                "schema_version": "ashr.google_oauth.v1",
                "provider": "google",
                "authorize_url": _google_authorize_url(),
                "expires_at": "2026-07-10T08:10:00Z",
            }
        if parsed_url.path.endswith("/oauth/google/disconnect"):
            return {
                "schema_version": "ashr.google_oauth.v1",
                "provider": "google",
                "disconnected": True,
                "revocation_status": "revoked",
                "connection": _connection(),
            }
        if parsed_url.path.endswith("/oauth/google/connection"):
            return _connection(disconnected_at=None)
        raise AssertionError(url)

    client = SaaSIngestionClient.from_base_url(
        "http://localhost:8787", http_transport=transport
    )
    started = client.start_account_connection(
        "tenant_local",
        "project_local",
        provider="google",
        account_id="account_local",
        expected_google_audience=AUDIENCE,
    )
    connected = client.get_account_connection(
        "tenant_local",
        "project_local",
        provider="google",
        account_id="account_local",
    )
    disconnected = client.disconnect_account_connection(
        "tenant_local",
        "project_local",
        provider="google",
        account_id="account_local",
    )

    assert started["operation"] == "start_account_connection"
    assert connected["operation"] == "get_account_connection"
    assert connected["result"]["display_name"] == "Verified User"
    assert disconnected["result"]["revocation_status"] == "revoked"
    assert disconnected["result"]["connection"]["email_verified"] is True
    assert calls == [
        (
            "POST",
            "/v1/projects/project_local/oauth/google/start",
            {
                "tenant_id": "tenant_local",
                "project_id": "project_local",
                "account_id": "account_local",
                "provider": "google",
            },
        ),
        (
            "GET",
            "/v1/projects/project_local/oauth/google/connection",
            {},
        ),
        (
            "POST",
            "/v1/projects/project_local/oauth/google/disconnect",
            {
                "tenant_id": "tenant_local",
                "project_id": "project_local",
                "account_id": "account_local",
                "provider": "google",
            },
        ),
    ]
    serialized = json.dumps(
        {"started": started, "connected": connected, "disconnected": disconnected}
    )
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized
    assert "client_secret" not in serialized


def test_account_connection_requires_hosted_transport() -> None:
    client = SaaSIngestionClient()
    with pytest.raises(SaaSClientError, match="base_url HTTP transport"):
        client.start_account_connection(
            "tenant", "project", provider="google", account_id="account"
        )
    with pytest.raises(SaaSClientError, match="base_url HTTP transport"):
        client.get_account_connection(
            "tenant", "project", provider="google", account_id="account"
        )


def test_cli_exposes_provider_neutral_google_start_connection_and_disconnect(monkeypatch) -> None:
    from ashr_clone import saas_cli

    calls: list[tuple[str, str, str, str]] = []

    class FakeHostedClient:
        uses_http = True

        def start_account_connection(
            self,
            tenant_id: str,
            project_id: str,
            *,
            provider: str,
            account_id: str,
            expected_google_audience: str | None = None,
        ) -> dict[str, object]:
            calls.append(("start", tenant_id, project_id, provider))
            assert account_id == "account_cli"
            assert expected_google_audience == AUDIENCE
            return {
                "schema_version": "ashr.clone.saas_ingestion_client.v1",
                "operation": "start_account_connection",
                "result": {"provider": provider},
            }

        def disconnect_account_connection(
            self,
            tenant_id: str,
            project_id: str,
            *,
            provider: str,
            account_id: str,
        ) -> dict[str, object]:
            calls.append(("disconnect", tenant_id, project_id, provider))
            assert account_id == "account_cli"
            return {
                "schema_version": "ashr.clone.saas_ingestion_client.v1",
                "operation": "disconnect_account_connection",
                "result": {"provider": provider, "disconnected": True},
            }

        def get_account_connection(
            self,
            tenant_id: str,
            project_id: str,
            *,
            provider: str,
            account_id: str,
        ) -> dict[str, object]:
            calls.append(("connection", tenant_id, project_id, provider))
            assert account_id == "account_cli"
            return {
                "schema_version": "ashr.clone.saas_ingestion_client.v1",
                "operation": "get_account_connection",
                "result": {"provider": provider, "account_id": account_id},
            }

    monkeypatch.setattr(
        saas_cli.SaaSIngestionClient,
        "from_base_url",
        staticmethod(lambda _base_url: FakeHostedClient()),
    )
    parser = saas_cli.build_parser()
    start = saas_cli.run_command(
        parser.parse_args(
            [
                "--base-url",
                "http://localhost:8787",
                "oauth-connect-start",
                "--tenant-id",
                "tenant_cli",
                "--project-id",
                "project_cli",
                "--provider",
                "google",
                "--account-id",
                "account_cli",
                "--expected-google-audience",
                AUDIENCE,
            ]
        )
    )
    disconnected = saas_cli.run_command(
        parser.parse_args(
            [
                "--base-url",
                "http://localhost:8787",
                "oauth-disconnect",
                "--tenant-id",
                "tenant_cli",
                "--project-id",
                "project_cli",
                "--provider",
                "google",
                "--account-id",
                "account_cli",
            ]
        )
    )
    connected = saas_cli.run_command(
        parser.parse_args(
            [
                "--base-url",
                "http://localhost:8787",
                "oauth-connection",
                "--tenant-id",
                "tenant_cli",
                "--project-id",
                "project_cli",
                "--provider",
                "google",
                "--account-id",
                "account_cli",
            ]
        )
    )

    assert start["operation"] == "start_account_connection"
    assert disconnected["result"]["disconnected"] is True
    assert connected["operation"] == "get_account_connection"
    assert calls == [
        ("start", "tenant_cli", "project_cli", "google"),
        ("disconnect", "tenant_cli", "project_cli", "google"),
        ("connection", "tenant_cli", "project_cli", "google"),
    ]


def test_python_sdk_keeps_callback_credentials_server_owned() -> None:
    from ashr_clone import saas_cli

    parser = saas_cli.build_parser()
    help_text = parser.format_help()
    assert "oauth-callback" not in help_text
    assert not hasattr(SaaSIngestionClient, "complete_account_connection_callback")
    for command in ("oauth-connect-start", "oauth-connection", "oauth-disconnect"):
        subparser = next(
            action.choices[command]
            for action in parser._actions
            if getattr(action, "choices", None) and command in action.choices
        )
        command_help = subparser.format_help()
        assert "--authorization-code" not in command_help
        assert "--code-verifier" not in command_help
