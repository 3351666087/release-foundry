from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest

from services.api.control_plane import SaaSControlPlaneService
from services.api.oauth_providers import (
    GitHubOAuthRuntime,
    InMemoryOAuthSecretReferenceStore,
    OAuthClientConfig,
    OAuthProviderContractError,
    OAuthProviderRuntimeError,
)
from services.api.runtime import ValidationError


CLIENT_ID_REF = "env:GITHUB_CLIENT_ID"
CLIENT_SECRET_REF = "vault:github/client-secret"
REDIRECT_URI = "https://app.ashr-clone.invalid/oauth/github/callback"
VERIFIER = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"


class FakeTransport:
    def __init__(self, responses: list[dict[str, object]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, object]] = []

    def request(self, method, url, *, headers=None, form=None, json_body=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "form": dict(form or {}),
                "json_body": dict(json_body or {}),
            }
        )
        if not self.responses:
            raise AssertionError("unexpected provider request")
        return self.responses.pop(0)


def _config() -> OAuthClientConfig:
    return OAuthClientConfig(
        provider="github",
        client_id_ref=CLIENT_ID_REF,
        client_secret_ref=CLIENT_SECRET_REF,
        redirect_uri=REDIRECT_URI,
        redirect_allowlist=(REDIRECT_URI,),
        scopes=("read:user", "user:email"),
        enabled=True,
    )


def _runtime(
    responses: list[dict[str, object]] | None = None,
    *,
    client_id: str = "fake-client-id",
    client_secret: str = "fake-client-secret",
) -> tuple[GitHubOAuthRuntime, FakeTransport, InMemoryOAuthSecretReferenceStore]:
    transport = FakeTransport(responses)
    store = InMemoryOAuthSecretReferenceStore(
        {
            CLIENT_ID_REF: client_id,
            CLIENT_SECRET_REF: client_secret,
        }
    )
    return GitHubOAuthRuntime(transport=transport, secret_store=store), transport, store


def _control(runtime: GitHubOAuthRuntime) -> SaaSControlPlaneService:
    control = SaaSControlPlaneService(github_oauth_runtime=runtime)
    control.bootstrap_project(
        tenant_name="Tenant",
        project_name="Project",
        tenant_id="tenant_github_runtime",
        project_id="project_github_runtime",
    )
    control.configure_oauth_provider(
        "tenant_github_runtime",
        "project_github_runtime",
        provider="github",
        client_id_ref=CLIENT_ID_REF,
        client_secret_ref=CLIENT_SECRET_REF,
        redirect_uris=[REDIRECT_URI],
        scopes=["read:user", "user:email"],
        config_id="github_runtime",
    )
    return control


def _provider_success_responses() -> list[dict[str, object]]:
    return [
        {
            "status_code": 200,
            "json": {
                "access_token": "fake-access-token",
                "token_type": "bearer",
                "scope": "read:user,user:email",
            },
        },
        {"status_code": 200, "json": {"id": 12345, "email": None}},
        {
            "status_code": 200,
            "json": [
                {
                    "email": "verified@example.invalid",
                    "primary": True,
                    "verified": True,
                }
            ],
        },
    ]


def test_readiness_rejects_equal_credential_references_without_values() -> None:
    marker = "must-never-be-rendered"
    config = OAuthClientConfig(
        provider="github",
        client_id_ref=f"env:{marker}",
        client_secret_ref=f"env:{marker}",
        redirect_uri=REDIRECT_URI,
        redirect_allowlist=(REDIRECT_URI,),
        scopes=("read:user",),
        enabled=True,
    )

    with pytest.raises(OAuthProviderContractError) as exc_info:
        config.validate()

    assert str(exc_info.value) == "OAuth client credential references must be distinct"
    assert marker not in str(exc_info.value)


def test_runtime_readiness_rejects_equal_resolved_values_before_transport() -> None:
    marker = "same-resolved-credential-value"
    runtime, transport, store = _runtime(client_id=marker, client_secret=marker)

    with pytest.raises(OAuthProviderRuntimeError) as exc_info:
        runtime.begin_authorization(
            config=_config(),
            state="state-runtime-equal-credentials-0001",
            code_verifier=VERIFIER,
        )

    assert exc_info.value.code == "oauth_client_credentials_not_distinct"
    assert marker not in str(exc_info.value)
    assert marker not in json.dumps(exc_info.value.to_public_dict(), sort_keys=True)
    assert transport.calls == []
    assert store.public_snapshot()["reference_count"] == 2


def test_runtime_rejects_equal_resolved_values_during_complete_without_transport() -> None:
    marker = "same-complete-credential-value"
    runtime, transport, store = _runtime()
    state = "state-runtime-complete-equal-credentials-0001"
    begun = runtime.begin_authorization(
        config=_config(),
        state=state,
        code_verifier=VERIFIER,
    )
    store._values[CLIENT_ID_REF] = marker
    store._values[CLIENT_SECRET_REF] = marker

    with pytest.raises(OAuthProviderRuntimeError) as exc_info:
        runtime.complete_authorization(
            config=_config(),
            authorization_code="equal-credentials-complete-code",
            received_state=state,
            expected_state_sha256=begun["state_sha256"],
            code_verifier_ref=begun["code_verifier_ref"],
        )

    assert exc_info.value.code == "oauth_client_credentials_not_distinct"
    assert marker not in str(exc_info.value)
    assert marker not in json.dumps(exc_info.value.to_public_dict(), sort_keys=True)
    assert transport.calls == []


def test_runtime_rejects_equal_resolved_values_during_revoke_without_transport() -> None:
    marker = "same-revoke-credential-value"
    runtime, transport, store = _runtime()
    access_token_ref = store.put(
        "synthetic-revoke-access-token",
        purpose="github-access-sandbox",
    )
    store._values[CLIENT_ID_REF] = marker
    store._values[CLIENT_SECRET_REF] = marker

    with pytest.raises(OAuthProviderRuntimeError) as exc_info:
        runtime.revoke_connection(
            config=_config(),
            access_token_ref=access_token_ref,
        )

    assert exc_info.value.code == "oauth_client_credentials_not_distinct"
    assert marker not in str(exc_info.value)
    assert marker not in json.dumps(exc_info.value.to_public_dict(), sort_keys=True)
    assert transport.calls == []
    assert store.resolve(access_token_ref) == "synthetic-revoke-access-token"


def test_github_runtime_success_is_pkce_bound_reference_only_and_disconnects() -> None:
    runtime, transport, store = _runtime(
        _provider_success_responses()
        + [{"status_code": 204, "json": None}]
    )
    state = "state-runtime-success-attempt-0001"
    begun = runtime.begin_authorization(
        config=_config(), state=state, code_verifier=VERIFIER
    )
    query = parse_qs(urlparse(begun["authorization_url"]).query)

    assert query["client_id"] == ["fake-client-id"]
    assert query["state"] == [state]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_verifier" not in query
    completed = runtime.complete_authorization(
        config=_config(),
        authorization_code="fake-authorization-code",
        received_state=state,
        expected_state_sha256=begun["state_sha256"],
        code_verifier_ref=begun["code_verifier_ref"],
    )

    public_text = json.dumps(completed, sort_keys=True)
    assert completed["subject_ref"] == "provider-ref:github/user/12345"
    assert completed["account_binding_ref"] == completed["subject_ref"]
    assert completed["email_sha256"] == hashlib.sha256(
        b"verified@example.invalid"
    ).hexdigest()
    for secret in (
        "fake-client-secret",
        "fake-access-token",
        "fake-authorization-code",
        "verified@example.invalid",
        VERIFIER,
    ):
        assert secret not in public_text
    assert [call["url"] for call in transport.calls] == [
        "https://github.com/login/oauth/access_token",
        "https://api.github.com/user",
        "https://api.github.com/user/emails",
    ]

    revoked = runtime.revoke_connection(
        config=_config(), access_token_ref=completed["access_token_ref"]
    )
    assert revoked["revoked"] is True
    assert transport.calls[-1]["method"] == "DELETE"
    with pytest.raises(OAuthProviderRuntimeError):
        store.resolve(completed["access_token_ref"])


def test_control_plane_fails_closed_for_callback_and_code_replay_without_leaks() -> None:
    runtime, transport, _ = _runtime(_provider_success_responses())
    control = _control(runtime)
    first_state = "state-control-success-attempt-0001"
    first = control.begin_oauth_authorization(
        "tenant_github_runtime",
        "project_github_runtime",
        provider_config_id="github_runtime",
        redirect_uri=REDIRECT_URI,
        code_verifier=VERIFIER,
        state=first_state,
    )
    completed = control.complete_oauth_authorization(
        "tenant_github_runtime",
        "project_github_runtime",
        flow_id=first["flow_id"],
        state=first_state,
        redirect_uri=REDIRECT_URI,
        authorization_code="replayed-authorization-code",
        session_id="github_session",
    )
    call_count = len(transport.calls)

    replay = control.complete_oauth_authorization(
        "tenant_github_runtime",
        "project_github_runtime",
        flow_id=first["flow_id"],
        state=first_state,
        redirect_uri=REDIRECT_URI,
        authorization_code="replayed-authorization-code",
    )
    assert completed["accepted"] is True
    assert replay["accepted"] is False
    assert "oauth_state_replay" in replay["failure_reasons"]
    assert len(transport.calls) == call_count

    second_state = "state-control-second-attempt-0002"
    second = control.begin_oauth_authorization(
        "tenant_github_runtime",
        "project_github_runtime",
        provider_config_id="github_runtime",
        redirect_uri=REDIRECT_URI,
        code_verifier=VERIFIER,
        state=second_state,
    )
    code_replay = control.complete_oauth_authorization(
        "tenant_github_runtime",
        "project_github_runtime",
        flow_id=second["flow_id"],
        state=second_state,
        redirect_uri=REDIRECT_URI,
        authorization_code="replayed-authorization-code",
    )

    assert code_replay["accepted"] is False
    assert code_replay["failure_reasons"] == ["authorization_code_replay"]
    assert len(transport.calls) == call_count
    persisted = json.dumps(
        {
            "snapshot": control.commercial_auth_payment_snapshot(
                "tenant_github_runtime", "project_github_runtime"
            ),
            "audit": control.audit_snapshot(
                "tenant_github_runtime", "project_github_runtime"
            ),
        },
        sort_keys=True,
    )
    for sensitive in (
        first_state,
        second_state,
        "replayed-authorization-code",
        VERIFIER,
        "fake-access-token",
        "verified@example.invalid",
    ):
        assert sensitive not in persisted


def test_provider_error_is_redacted_and_control_plane_disconnect_deletes_token() -> None:
    marker = "provider-secret-message"
    runtime_error, transport_error, _ = _runtime(
        [
            {
                "status_code": 401,
                "json": {
                    "error": "unknown_error",
                    "message": marker,
                    "access_token": "provider-returned-token",
                },
            }
        ]
    )
    begun = runtime_error.begin_authorization(
        config=_config(),
        state="state-provider-error-attempt-0001",
        code_verifier=VERIFIER,
    )
    with pytest.raises(OAuthProviderRuntimeError) as exc_info:
        runtime_error.complete_authorization(
            config=_config(),
            authorization_code="provider-error-code",
            received_state="state-provider-error-attempt-0001",
            expected_state_sha256=begun["state_sha256"],
            code_verifier_ref=begun["code_verifier_ref"],
        )
    serialized_error = json.dumps(exc_info.value.to_public_dict(), sort_keys=True)
    assert exc_info.value.code == "github_provider_error"
    assert marker not in serialized_error
    assert "provider-returned-token" not in serialized_error
    assert len(transport_error.calls) == 1

    runtime, transport, store = _runtime(
        _provider_success_responses()
        + [{"status_code": 204, "json": None}]
    )
    control = _control(runtime)
    state = "state-control-disconnect-attempt-0001"
    flow = control.begin_oauth_authorization(
        "tenant_github_runtime",
        "project_github_runtime",
        provider_config_id="github_runtime",
        redirect_uri=REDIRECT_URI,
        code_verifier=VERIFIER,
        state=state,
    )
    completed = control.complete_oauth_authorization(
        "tenant_github_runtime",
        "project_github_runtime",
        flow_id=flow["flow_id"],
        state=state,
        redirect_uri=REDIRECT_URI,
        authorization_code="disconnect-code",
        session_id="disconnect_session",
    )
    token_ref = control.store.oauth_sessions["disconnect_session"]["access_token_ref"]
    disconnected = control.disconnect_oauth_session(
        "tenant_github_runtime",
        "project_github_runtime",
        "disconnect_session",
    )

    assert completed["session"]["subject_ref_present"] is True
    assert completed["session"]["account_binding_present"] is True
    assert disconnected["status"] == "disconnected"
    assert disconnected["access_token_ref_present"] is False
    assert transport.calls[-1]["method"] == "DELETE"
    with pytest.raises(OAuthProviderRuntimeError):
        store.resolve(token_ref)


def test_runtime_rejects_provider_scope_escalation_without_leaking_response() -> None:
    marker_token = "synthetic-scope-escalation-token"
    runtime, transport, store = _runtime(
        [
            {
                "status_code": 200,
                "json": {
                    "access_token": marker_token,
                    "token_type": "bearer",
                    "scope": "read:user repo admin:org",
                },
            }
        ]
    )
    state = "state-provider-scope-escalation-attempt-0001"
    begun = runtime.begin_authorization(
        config=_config(),
        state=state,
        code_verifier=VERIFIER,
    )

    with pytest.raises(OAuthProviderRuntimeError) as exc_info:
        runtime.complete_authorization(
            config=_config(),
            authorization_code="synthetic-scope-escalation-code",
            received_state=state,
            expected_state_sha256=begun["state_sha256"],
            code_verifier_ref=begun["code_verifier_ref"],
        )

    public_error = json.dumps(exc_info.value.to_public_dict(), sort_keys=True)
    assert exc_info.value.code == "oauth_scope_escalation"
    assert marker_token not in public_error
    assert "repo" not in public_error
    assert "admin:org" not in public_error
    assert len(transport.calls) == 1
    assert store.public_snapshot()["reference_count"] == 3


def test_control_plane_rejects_same_reference_without_echoing_it() -> None:
    runtime, _, _ = _runtime()
    control = SaaSControlPlaneService(github_oauth_runtime=runtime)
    control.bootstrap_project(
        tenant_name="Tenant",
        project_name="Project",
        tenant_id="tenant_equal_ref",
        project_id="project_equal_ref",
    )
    marker_ref = "env:DO_NOT_ECHO_EQUAL_REFERENCE"

    with pytest.raises(ValidationError) as exc_info:
        control.configure_oauth_provider(
            "tenant_equal_ref",
            "project_equal_ref",
            provider="github",
            client_id_ref=marker_ref,
            client_secret_ref=marker_ref,
            redirect_uris=[REDIRECT_URI],
            scopes=["read:user"],
        )

    assert str(exc_info.value) == "oauth client credential references must be distinct"
    assert marker_ref not in str(exc_info.value)
