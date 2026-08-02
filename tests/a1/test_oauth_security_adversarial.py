from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
from pathlib import Path

import pytest

from services.api.control_plane import SaaSControlPlaneRouter, SaaSControlPlaneService
from services.api.oauth_providers import (
    OAuthClientConfig,
    OAuthProviderContractError,
    OAuthProviderRuntimeError,
    OAuthReplayLedger,
    GitHubOAuthRuntime,
    InMemoryOAuthSecretReferenceStore,
    hash_oauth_nonce,
    verify_callback_identity,
    verify_callback_state,
)
from services.api.runtime import NotFoundError, ValidationError


CALLBACK = "https://app.releasefoundry.invalid/oauth/github/callback"
VERIFIER = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
GOOGLE_CALLBACK = "https://app.releasefoundry.invalid/oauth/google/callback"


def _control() -> SaaSControlPlaneService:
    control = SaaSControlPlaneService()
    for tenant_id, project_id in (
        ("tenant_red", "project_red"),
        ("tenant_blue", "project_blue"),
    ):
        control.bootstrap_project(
            tenant_name=tenant_id,
            project_name=project_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        control.create_api_key(
            tenant_id,
            project_id,
            name="oauth writer",
            scopes=["commercial:write"],
            key_id=f"key_{tenant_id}",
        )
    return control


def _configure(
    control: SaaSControlPlaneService,
    *,
    tenant_id: str = "tenant_red",
    project_id: str = "project_red",
    config_id: str = "oauth_github_red",
) -> dict:
    return control.configure_oauth_provider(
        tenant_id,
        project_id,
        provider="github",
        client_id_ref=f"env:{tenant_id.upper()}_GITHUB_CLIENT_ID_REF",
        client_secret_ref=f"vault:{tenant_id}/github/client_secret_ref",
        redirect_uris=[CALLBACK],
        scopes=["read:user", "user:email"],
        config_id=config_id,
    )


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "http://localhost:8080/oauth/callback",
        "http://127.0.0.1:8080/oauth/callback",
        "https://app.releasefoundry.invalid./oauth/github/callback",
        "https://app.releasefoundry.invalid/oauth/github/callback?next=https://evil.invalid",
        "https://app.releasefoundry.invalid@evil.invalid/oauth/github/callback",
    ],
)
def test_control_plane_rejects_loopback_alias_and_open_redirects(redirect_uri):
    control = _control()

    with pytest.raises(ValidationError, match="redirect_uri"):
        control.configure_oauth_provider(
            "tenant_red",
            "project_red",
            provider="github",
            client_id_ref="env:GITHUB_CLIENT_ID_REF",
            client_secret_ref="vault:github/oauth/client_secret_ref",
            redirect_uris=[redirect_uri],
            scopes=["read:user"],
        )


def test_authorization_begin_requires_exact_redirect_allowlist_match():
    control = _control()
    _configure(control)

    with pytest.raises(ValidationError, match="match provider config"):
        control.begin_oauth_authorization(
            "tenant_red",
            "project_red",
            provider_config_id="oauth_github_red",
            redirect_uri="https://evil.invalid/oauth/github/callback",
            code_verifier=VERIFIER,
            state="state-open-redirect-attempt-0001",
        )


def test_live_provider_contract_rejects_loopback_dev_bypass_and_callback_aliases():
    base = {
        "provider": "github",
        "client_id_ref": "env:GITHUB_CLIENT_ID_REF",
        "client_secret_ref": "vault:github/oauth/client-secret-ref",
        "scopes": ("read:user",),
        "enabled": True,
    }
    with pytest.raises(OAuthProviderContractError, match="live redirect URI"):
        OAuthClientConfig(
            **base,
            environment="live",
            redirect_uri="http://localhost:8765/oauth/callback",
        ).validate()
    with pytest.raises(OAuthProviderContractError, match="HTTPS or localhost"):
        OAuthClientConfig(
            **base,
            environment="sandbox",
            redirect_uri="https://app.releasefoundry.invalid./oauth/callback",
        ).validate()


def test_invalid_callback_does_not_consume_replay_key_before_valid_callback():
    state = "state-valid-callback-attempt-0001"
    expected = hashlib.sha256(state.encode()).hexdigest()
    ledger = OAuthReplayLedger()
    replay_key = "callback-replay-key-attempt-0001"

    rejected = verify_callback_state(
        received_state="state-attacker-callback-attempt-0002",
        expected_state_sha256=expected,
        authorization_code_ref="vault:oauth/code/attempt-1",
        replay_key=replay_key,
        replay_ledger=ledger,
    )
    assert ledger.public_snapshot()["consumed_digest_count"] == 0
    accepted = verify_callback_state(
        received_state=state,
        expected_state_sha256=expected,
        authorization_code_ref="vault:oauth/code/attempt-1",
        replay_key=replay_key,
        replay_ledger=ledger,
    )
    replay = verify_callback_state(
        received_state=state,
        expected_state_sha256=expected,
        authorization_code_ref="vault:oauth/code/attempt-1",
        replay_key=replay_key,
        replay_ledger=ledger,
    )

    assert rejected["accepted"] is False
    assert accepted["accepted"] is True
    assert ledger.public_snapshot()["consumed_digest_count"] == 1
    assert replay["accepted"] is False
    assert "callback_replay" in replay["failure_reasons"]


def test_in_memory_replay_ledger_allows_exactly_one_concurrent_consumer():
    ledger = OAuthReplayLedger()

    def consume_once(_: int) -> bool:
        return ledger.consume(
            provider="github",
            environment="sandbox",
            replay_key="concurrent-callback-attempt-20260710",
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(consume_once, range(128)))

    assert results.count(True) == 1
    assert results.count(False) == 127
    assert ledger.public_snapshot() == {
        "consumed_digest_count": 1,
        "raw_replay_keys_present": False,
    }


def test_state_and_authorization_code_replay_fail_closed_across_flows():
    control = _control()
    _configure(control)
    state_one = "state-red-oauth-attempt-0001"
    state_two = "state-red-oauth-attempt-0002"

    first = control.begin_oauth_authorization(
        "tenant_red",
        "project_red",
        provider_config_id="oauth_github_red",
        redirect_uri=CALLBACK,
        code_verifier=VERIFIER,
        state=state_one,
    )
    with pytest.raises(ValidationError, match="state replay"):
        control.begin_oauth_authorization(
            "tenant_red",
            "project_red",
            provider_config_id="oauth_github_red",
            redirect_uri=CALLBACK,
            code_verifier=VERIFIER,
            state=state_one,
        )
    completed = control.complete_oauth_authorization(
        "tenant_red",
        "project_red",
        flow_id=first["flow_id"],
        state=state_one,
        code_verifier=VERIFIER,
        redirect_uri=CALLBACK,
        subject_ref="provider-ref:github/user/red-1",
        provider_code_ref="vault:github/code/shared-code-ref",
    )
    second = control.begin_oauth_authorization(
        "tenant_red",
        "project_red",
        provider_config_id="oauth_github_red",
        redirect_uri=CALLBACK,
        code_verifier=VERIFIER,
        state=state_two,
    )
    replay = control.complete_oauth_authorization(
        "tenant_red",
        "project_red",
        flow_id=second["flow_id"],
        state=state_two,
        code_verifier=VERIFIER,
        redirect_uri=CALLBACK,
        subject_ref="provider-ref:github/user/red-1",
        provider_code_ref="vault:github/code/shared-code-ref",
    )

    assert completed["accepted"] is True
    assert replay["accepted"] is False
    assert "authorization_code_replay" in replay["failure_reasons"]


@pytest.mark.parametrize(
    ("override", "failure_reason"),
    [
        ({"received_nonce": "wrong-nonce-value-20260710"}, "nonce_mismatch"),
        ({"issuer": "https://issuer.invalid"}, "issuer_mismatch"),
        ({"audience": "wrong-google-client-id"}, "audience_mismatch"),
        ({"email_verified": False}, "email_unverified"),
    ],
)
def test_google_identity_claim_failures_are_individually_fail_closed(
    override, failure_reason
):
    nonce = "google-oidc-nonce-value-20260710"
    config = OAuthClientConfig(
        provider="google",
        client_id_ref="env:GOOGLE_CLIENT_ID_REF",
        client_secret_ref="vault:google/oauth/client-secret-ref",
        redirect_uri=GOOGLE_CALLBACK,
        redirect_allowlist=(GOOGLE_CALLBACK,),
        scopes=("openid", "email"),
        environment="sandbox",
        enabled=True,
        issuer_allowlist=("https://accounts.google.com",),
        audience_allowlist=("google-client-id",),
    )
    claims = {
        "issuer": "https://accounts.google.com",
        "audience": "google-client-id",
        "subject": "google-subject-synthetic-123",
        "account_binding_ref": "provider-ref:google/account/synthetic-123",
        "expected_account_binding_ref": "provider-ref:google/account/synthetic-123",
        "received_nonce": nonce,
        "expected_nonce_sha256": hash_oauth_nonce(nonce)["nonce_sha256"],
        "email_verified": True,
    }
    claims.update(override)

    result = verify_callback_identity(config=config, **claims)
    serialized = json.dumps(result, sort_keys=True)

    assert result["accepted"] is False
    assert result["failure_reasons"] == [failure_reason]
    assert result["raw_subject_present"] is False
    assert result["raw_nonce_present"] is False
    assert "google-subject-synthetic-123" not in serialized
    assert nonce not in serialized


@pytest.mark.parametrize("failure", [TimeoutError("timeout"), OSError("outage")])
def test_github_provider_timeout_and_outage_are_redacted_and_leave_no_token_ref(
    failure,
):
    class FailingTransport:
        def __init__(self):
            self.calls = 0

        def request(self, method, url, *, headers=None, form=None, json_body=None):
            self.calls += 1
            raise failure

    transport = FailingTransport()
    store = InMemoryOAuthSecretReferenceStore(
        {
            "env:GITHUB_CLIENT_ID_REF": "synthetic-client-id",
            "vault:github/oauth/client-secret-ref": "synthetic-client-secret",
        }
    )
    runtime = GitHubOAuthRuntime(transport=transport, secret_store=store)
    config = OAuthClientConfig(
        provider="github",
        client_id_ref="env:GITHUB_CLIENT_ID_REF",
        client_secret_ref="vault:github/oauth/client-secret-ref",
        redirect_uri=CALLBACK,
        redirect_allowlist=(CALLBACK,),
        scopes=("read:user",),
        environment="sandbox",
        enabled=True,
    )
    state = "github-provider-failure-state-20260710"
    begun = runtime.begin_authorization(
        config=config,
        state=state,
        code_verifier=VERIFIER,
    )

    with pytest.raises(OAuthProviderRuntimeError) as exc_info:
        runtime.complete_authorization(
            config=config,
            authorization_code="synthetic-provider-failure-code",
            received_state=state,
            expected_state_sha256=begun["state_sha256"],
            code_verifier_ref=begun["code_verifier_ref"],
        )

    public_error = json.dumps(exc_info.value.to_public_dict(), sort_keys=True)
    assert exc_info.value.code == "github_transport_error"
    assert transport.calls == 1
    assert "synthetic-provider-failure-code" not in public_error
    assert "synthetic-client-secret" not in public_error
    assert store.public_snapshot() == {
        "reference_count": 3,
        "secret_value_present": False,
        "references_included": False,
    }


def test_client_credentials_and_refs_are_rejected_or_omitted_without_echo():
    control = _control()
    equal_ref = "vault:github/oauth/client_secret_equal_marker"
    implausible_ref = "vault:github/oauth/client_id_marker"

    for client_id_ref, client_secret_ref, message in (
        (equal_ref, equal_ref, "distinct"),
        ("env:GITHUB_CLIENT_ID_REF", implausible_ref, "secret credential material"),
    ):
        with pytest.raises(ValidationError, match=message) as exc:
            control.configure_oauth_provider(
                "tenant_red",
                "project_red",
                provider="github",
                client_id_ref=client_id_ref,
                client_secret_ref=client_secret_ref,
                redirect_uris=[CALLBACK],
                scopes=["read:user"],
            )
        assert client_id_ref not in str(exc.value)
        assert client_secret_ref not in str(exc.value)

    configured = _configure(control)
    public_text = json.dumps(configured, sort_keys=True)
    snapshot_text = json.dumps(
        control.commercial_auth_payment_snapshot("tenant_red", "project_red"),
        sort_keys=True,
    )
    audit_text = json.dumps(
        control.audit_snapshot("tenant_red", "project_red"),
        sort_keys=True,
    )
    for value in (
        "env:TENANT_RED_GITHUB_CLIENT_ID_REF",
        "vault:tenant_red/github/client_secret_ref",
        equal_ref,
        implausible_ref,
    ):
        assert value not in public_text
        assert value not in snapshot_text
        assert value not in audit_text
    assert configured["client_id_ref_present"] is True
    assert configured["client_secret_ref_present"] is True


def test_public_session_snapshot_and_audit_omit_identity_and_token_refs():
    control = _control()
    _configure(control)
    subject_ref = "provider-ref:github/user/synthetic-private-account"
    account_binding_ref = subject_ref
    email_sha256 = hashlib.sha256(
        b"synthetic-private-account@example.invalid"
    ).hexdigest()
    access_token_ref = "vault:github/session/synthetic-access-token-ref"
    refresh_token_ref = "vault:github/session/synthetic-refresh-token-ref"

    session = control.create_oauth_session(
        "tenant_red",
        "project_red",
        provider="github",
        provider_config_id="oauth_github_red",
        subject_ref=subject_ref,
        account_binding_ref=account_binding_ref,
        email_sha256=email_sha256,
        access_token_ref=access_token_ref,
        refresh_token_ref=refresh_token_ref,
    )
    snapshot_text = json.dumps(
        control.commercial_auth_payment_snapshot("tenant_red", "project_red"),
        sort_keys=True,
    )
    audit_text = json.dumps(
        control.audit_snapshot("tenant_red", "project_red"),
        sort_keys=True,
    )
    public_text = json.dumps(session, sort_keys=True)

    for value in (
        subject_ref,
        account_binding_ref,
        email_sha256,
        access_token_ref,
        refresh_token_ref,
    ):
        assert value not in public_text
        assert value not in snapshot_text
        assert value not in audit_text
    assert session["subject_ref_present"] is True
    assert session["subject_sha256"] == hashlib.sha256(
        subject_ref.encode("utf-8")
    ).hexdigest()
    assert session["account_binding_present"] is True
    assert session["email_hash_present"] is True
    assert session["access_token_ref_present"] is True
    assert session["refresh_token_ref_present"] is True


def test_cross_tenant_flow_session_and_provider_subject_binding_are_rejected():
    control = _control()
    _configure(control)
    _configure(
        control,
        tenant_id="tenant_blue",
        project_id="project_blue",
        config_id="oauth_github_blue",
    )
    flow = control.begin_oauth_authorization(
        "tenant_red",
        "project_red",
        provider_config_id="oauth_github_red",
        redirect_uri=CALLBACK,
        code_verifier=VERIFIER,
        state="state-red-cross-tenant-attempt-0001",
    )

    with pytest.raises(NotFoundError, match="flow not found"):
        control.complete_oauth_authorization(
            "tenant_blue",
            "project_blue",
            flow_id=flow["flow_id"],
            state="state-red-cross-tenant-attempt-0001",
            code_verifier=VERIFIER,
            redirect_uri=CALLBACK,
            subject_ref="provider-ref:github/user/red-1",
            provider_code_ref="vault:github/code/cross-tenant",
        )
    with pytest.raises(ValidationError, match="provider binding"):
        control.create_oauth_session(
            "tenant_red",
            "project_red",
            provider="github",
            provider_config_id="oauth_github_red",
            subject_ref="provider-ref:google/user/confused-account",
        )
    session = control.create_oauth_session(
        "tenant_red",
        "project_red",
        provider="github",
        provider_config_id="oauth_github_red",
        subject_ref="provider-ref:github/user/red-1",
        session_id="globally-bound-session-id",
    )
    with pytest.raises(ValidationError, match="session_id already exists"):
        control.create_oauth_session(
            "tenant_blue",
            "project_blue",
            provider="github",
            provider_config_id="oauth_github_blue",
            subject_ref="provider-ref:github/user/blue-1",
            session_id=session["session_id"],
        )
    with pytest.raises(ValidationError, match="already bound to another project"):
        control.create_oauth_session(
            "tenant_blue",
            "project_blue",
            provider="github",
            provider_config_id="oauth_github_blue",
            subject_ref="provider-ref:github/user/red-1",
        )


def test_router_redacts_unexpected_provider_body_and_requires_auth_key():
    control = _control()
    router = SaaSControlPlaneRouter(control)
    unauthenticated = router.handle(
        "POST",
        "/v1/projects/project_red/commercial-auth-payment/oauth-providers/configure",
        {
            "tenant_id": "tenant_red",
            "provider": "github",
            "client_id_ref": "env:GITHUB_CLIENT_ID_REF",
            "client_secret_ref": "vault:github/oauth/client_secret_ref",
            "redirect_uris": [CALLBACK],
            "scopes": ["read:user"],
        },
    )
    synthetic_body = "HTTP 502 body access_token=synthetic-token-value"

    def fail_closed(*args, **kwargs):
        raise RuntimeError(synthetic_body)

    control.configure_oauth_provider = fail_closed
    outage = router.handle(
        "POST",
        "/v1/projects/project_red/commercial-auth-payment/oauth-providers/configure",
        {
            "tenant_id": "tenant_red",
            "auth_key_id": "key_tenant_red",
            "provider": "github",
            "client_id_ref": "env:GITHUB_CLIENT_ID_REF",
            "client_secret_ref": "vault:github/oauth/client_secret_ref",
            "redirect_uris": [CALLBACK],
            "scopes": ["read:user"],
        },
    )

    assert unauthenticated["status_code"] == 400
    assert outage["status_code"] == 500
    assert synthetic_body not in json.dumps(outage)
    assert outage["body"]["error"]["message"] == "internal request processing failed"


def test_go_public_json_omits_token_ref_contract():
    root = Path(__file__).resolve().parents[2]
    source = (root / "packages/go/releasefoundry/oauth_github.go").read_text(encoding="utf-8")
    connection_block = source[
        source.index("type GitHubOAuthConnection struct"):
        source.index("type GitHubOAuthConnectionStore")
    ]

    assert re.search(r'\bTokenRef\s+string\s+`json:"-"`', connection_block)
    assert "AccessToken" not in connection_block
