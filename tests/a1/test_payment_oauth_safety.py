from __future__ import annotations

import hashlib
import json

import pytest

from services.api.control_plane import SaaSControlPlaneRouter, SaaSControlPlaneService
from services.api.runtime import ValidationError
from packages.sdk.releasefoundry.saas import SaaSIngestionClient


def _control() -> SaaSControlPlaneService:
    control = SaaSControlPlaneService()
    control.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_authpay", project_id="project_authpay")
    control.create_api_key(
        "tenant_authpay",
        "project_authpay",
        name="commercial config writer",
        scopes=["commercial:write"],
        key_id="key_commercial_writer",
    )
    for operation in (
        "oauth.provider.configure",
        "oauth.authorization.begin",
        "oauth.authorization.complete",
        "oauth.session.create",
        "oauth.session.revoke",
        "commercial.provider.configure",
        "payment.mode_boundary.record",
    ):
        control.configure_api_key_rate_limit(
            "tenant_authpay",
            "project_authpay",
            key_id="key_commercial_writer",
            operation=operation,
            limit=2,
        )
    return control


def test_github_google_oauth_configs_and_sessions_store_secret_refs_only():
    control = _control()

    github = control.configure_oauth_provider(
        "tenant_authpay",
        "project_authpay",
        provider="github",
        client_id_ref="env:GITHUB_CLIENT_ID_REF",
        client_secret_ref="vault:github/oauth/client_secret_ref",
        redirect_uris=["https://app.releasefoundry.invalid/oauth/github/callback"],
        scopes=["read:user", "user:email"],
        config_id="oauth_github",
        auth_key_id="key_commercial_writer",
    )
    google = control.configure_oauth_provider(
        "tenant_authpay",
        "project_authpay",
        provider="google",
        client_id_ref="env:GOOGLE_CLIENT_ID_REF",
        client_secret_ref="kms:google/oauth/client_secret_ref",
        redirect_uris=["https://app.releasefoundry.invalid/oauth/google/callback"],
        scopes=["openid", "email", "profile"],
        config_id="oauth_google",
        auth_key_id="key_commercial_writer",
    )
    session = control.create_oauth_session(
        "tenant_authpay",
        "project_authpay",
        provider="github",
        provider_config_id="oauth_github",
        subject_ref="provider-ref:github/user/12345",
        access_token_ref="vault:github/session/access_ref",
        refresh_token_ref=None,
        pkce_code_challenge="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO12",
        pkce_code_challenge_method="S256",
        oauth_state="state-github-login-2026-07-a1",
        session_id="session_github",
        auth_key_id="key_commercial_writer",
    )

    snapshot = control.commercial_auth_payment_snapshot("tenant_authpay", "project_authpay")
    text = json.dumps(snapshot, sort_keys=True)

    assert {item["provider"] for item in snapshot["oauth_provider_configs"]} == {"github", "google"}
    assert github["secret_value_present"] is False
    assert google["secret_value_present"] is False
    assert session["secret_value_present"] is False
    assert session["pkce_code_challenge_method"] == "S256"
    assert session["pkce_code_challenge_sha256"] == hashlib.sha256(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO12").hexdigest()
    assert session["oauth_state_present"] is True
    assert session["oauth_state_sha256"] == hashlib.sha256(b"state-github-login-2026-07-a1").hexdigest()
    assert session["linked_rate_limit"]["operation"] == "oauth.session.create"
    assert "state-github-login-2026-07-a1" not in text
    assert "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO12" not in text
    assert "client_secret=" not in text
    assert "access_token=" not in text
    assert "Bearer " not in text

    with pytest.raises(ValidationError, match="secret reference prefix"):
        control.configure_oauth_provider(
            "tenant_authpay",
            "project_authpay",
            provider="github",
            client_id_ref="env:GITHUB_CLIENT_ID_REF",
            client_secret_ref="github_raw_client_secret",
            redirect_uris=["https://app.releasefoundry.invalid/oauth/github/callback"],
            scopes=["read:user"],
        )


def test_oauth_pkce_s256_and_state_replay_contract_rejects_unsafe_flows():
    control = _control()
    control.configure_api_key_rate_limit(
        "tenant_authpay",
        "project_authpay",
        key_id="key_commercial_writer",
        operation="oauth.session.create",
        limit=5,
    )
    control.configure_oauth_provider(
        "tenant_authpay",
        "project_authpay",
        provider="github",
        client_id_ref="env:GITHUB_CLIENT_ID_REF",
        client_secret_ref="vault:github/oauth/client_secret_ref",
        redirect_uris=["https://app.releasefoundry.invalid/oauth/github/callback"],
        scopes=["read:user"],
        config_id="oauth_github",
        auth_key_id="key_commercial_writer",
    )
    challenge = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    state = "state-unique-login-attempt-a1-0001"

    created = control.create_oauth_session(
        "tenant_authpay",
        "project_authpay",
        provider="github",
        provider_config_id="oauth_github",
        subject_ref="provider-ref:github/user/abc",
        access_token_ref="vault:github/session/access_ref_abc",
        pkce_code_challenge=challenge,
        pkce_code_challenge_method="S256",
        oauth_state=state,
        session_id="session_pkce",
        auth_key_id="key_commercial_writer",
    )
    text = json.dumps(control.commercial_auth_payment_snapshot("tenant_authpay", "project_authpay"), sort_keys=True)

    assert created["pkce_required"] is True
    assert created["pkce_code_challenge_method"] == "S256"
    assert created["pkce_code_challenge_sha256"] == hashlib.sha256(challenge.encode("utf-8")).hexdigest()
    assert created["oauth_state_sha256"] == hashlib.sha256(state.encode("utf-8")).hexdigest()
    assert challenge not in text
    assert state not in text

    with pytest.raises(ValidationError, match="state replay"):
        control.create_oauth_session(
            "tenant_authpay",
            "project_authpay",
            provider="github",
            provider_config_id="oauth_github",
            subject_ref="provider-ref:github/user/abc2",
            pkce_code_challenge=challenge,
            pkce_code_challenge_method="S256",
            oauth_state=state,
        )
    with pytest.raises(ValidationError, match="S256"):
        control.create_oauth_session(
            "tenant_authpay",
            "project_authpay",
            provider="github",
            provider_config_id="oauth_github",
            subject_ref="provider-ref:github/user/abc3",
            pkce_code_challenge=challenge,
            pkce_code_challenge_method="plain",
            oauth_state="state-unique-login-attempt-a1-0002",
        )

    router = SaaSControlPlaneRouter(control)
    response = router.handle(
        "POST",
        "/v1/projects/project_authpay/commercial-auth-payment/oauth-sessions/create",
        {
            "tenant_id": "tenant_authpay",
            "auth_key_id": "key_commercial_writer",
            "provider": "github",
            "provider_config_id": "oauth_github",
            "subject_ref": "provider-ref:github/user/router",
            "access_token_ref": "vault:github/session/access_ref_router",
            "pkce_code_challenge": challenge,
            "pkce_code_challenge_method": "S256",
            "oauth_state": "state-unique-login-attempt-a1-router",
            "session_id": "session_router_pkce",
        },
    )

    assert response["status_code"] == 201
    assert response["body"]["pkce_code_challenge_sha256"] == hashlib.sha256(challenge.encode("utf-8")).hexdigest()
    assert response["body"]["oauth_state_present"] is True


def test_oauth_authorization_flow_is_pkce_bound_replay_safe_and_public_safe():
    control = _control()
    control.configure_oauth_provider(
        "tenant_authpay",
        "project_authpay",
        provider="github",
        client_id_ref="env:GITHUB_CLIENT_ID_REF",
        client_secret_ref="vault:github/oauth/client_secret_ref",
        redirect_uris=["https://app.releasefoundry.invalid/oauth/github/callback"],
        scopes=["read:user"],
        config_id="oauth_github_flow",
        auth_key_id="key_commercial_writer",
    )
    verifier = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
    state = "oauth-state-round45-unique-attempt-0001"
    router = SaaSControlPlaneRouter(control)

    begun = router.handle(
        "POST",
        "/v1/projects/project_authpay/commercial-auth-payment/oauth-authorizations/begin",
        {
            "tenant_id": "tenant_authpay",
            "auth_key_id": "key_commercial_writer",
            "provider_config_id": "oauth_github_flow",
            "redirect_uri": "https://app.releasefoundry.invalid/oauth/github/callback",
            "code_verifier": verifier,
            "state": state,
        },
    )

    assert begun["status_code"] == 201
    assert begun["body"]["state"] == state
    assert begun["body"]["code_challenge_method"] == "S256"
    assert begun["body"]["raw_state_present"] is False
    flow_id = begun["body"]["flow_id"]

    completed = router.handle(
        "POST",
        f"/v1/projects/project_authpay/commercial-auth-payment/oauth-authorizations/{flow_id}/complete",
        {
            "tenant_id": "tenant_authpay",
            "auth_key_id": "key_commercial_writer",
            "state": state,
            "code_verifier": verifier,
            "redirect_uri": "https://app.releasefoundry.invalid/oauth/github/callback",
            "subject_ref": "provider-ref:github/user/round45",
            "provider_code_ref": "vault:github/code/round45",
            "access_token_ref": "vault:github/access/round45",
            "refresh_token_ref": "vault:github/refresh/round45",
            "session_id": "oauth_session_round45",
        },
    )

    assert completed["status_code"] == 200
    assert completed["body"]["accepted"] is True
    assert completed["body"]["status"] == "completed"
    assert completed["body"]["session"]["session_id"] == "oauth_session_round45"

    replay = router.handle(
        "POST",
        f"/v1/projects/project_authpay/commercial-auth-payment/oauth-authorizations/{flow_id}/complete",
        {
            "tenant_id": "tenant_authpay",
            "auth_key_id": "key_commercial_writer",
            "state": state,
            "code_verifier": verifier,
            "redirect_uri": "https://app.releasefoundry.invalid/oauth/github/callback",
            "subject_ref": "provider-ref:github/user/round45",
        },
    )
    snapshot_text = json.dumps(control.commercial_auth_payment_snapshot("tenant_authpay", "project_authpay"), sort_keys=True)
    audit_text = json.dumps(control.audit_snapshot("tenant_authpay", "project_authpay"), sort_keys=True)

    assert replay["status_code"] == 200
    assert replay["body"]["accepted"] is False
    assert "oauth_state_replay" in replay["body"]["failure_reasons"]
    assert completed["body"]["provider_code_ref_present"] is True
    assert completed["body"]["session"]["access_token_ref_present"] is True
    assert completed["body"]["session"]["refresh_token_ref_present"] is True
    for secret_ref in (
        "vault:github/code/round45",
        "vault:github/access/round45",
        "vault:github/refresh/round45",
    ):
        assert secret_ref not in json.dumps(completed["body"], sort_keys=True)
        assert secret_ref not in snapshot_text
        assert secret_ref not in audit_text
    for sensitive in (state, verifier, "raw-provider-authorization-code"):
        assert sensitive not in snapshot_text
        assert sensitive not in audit_text


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"state": "oauth-state-round45-wrong-attempt-0002"}, "oauth_state_mismatch"),
        ({"code_verifier": "Z" * 64}, "pkce_verifier_mismatch"),
        ({"redirect_uri": "https://app.releasefoundry.invalid/oauth/wrong/callback"}, "redirect_uri_mismatch"),
        ({"provider_error": "access_denied"}, "provider_error"),
    ],
)
def test_oauth_authorization_flow_fails_closed_on_callback_mismatch(override, expected_reason):
    control = _control()
    control.configure_oauth_provider(
        "tenant_authpay",
        "project_authpay",
        provider="google",
        client_id_ref="env:GOOGLE_CLIENT_ID_REF",
        client_secret_ref="vault:google/oauth/client_secret_ref",
        redirect_uris=["https://app.releasefoundry.invalid/oauth/google/callback"],
        scopes=["openid", "email"],
        config_id="oauth_google_flow",
        auth_key_id="key_commercial_writer",
    )
    verifier = "v" * 64
    state = "oauth-state-round45-google-attempt-0001"
    begun = control.begin_oauth_authorization(
        "tenant_authpay",
        "project_authpay",
        provider_config_id="oauth_google_flow",
        redirect_uri="https://app.releasefoundry.invalid/oauth/google/callback",
        code_verifier=verifier,
        state=state,
        auth_key_id="key_commercial_writer",
    )
    callback = {
        "state": state,
        "code_verifier": verifier,
        "redirect_uri": "https://app.releasefoundry.invalid/oauth/google/callback",
        "subject_ref": "provider-ref:google/user/round45",
        "provider_code_ref": "vault:google/code/round45",
        "auth_key_id": "key_commercial_writer",
        **override,
    }

    rejected = control.complete_oauth_authorization(
        "tenant_authpay",
        "project_authpay",
        flow_id=begun["flow_id"],
        **callback,
    )

    assert rejected["accepted"] is False
    assert expected_reason in rejected["failure_reasons"]
    assert rejected["status"] == "failed"


def test_stripe_payment_provider_test_live_boundary_is_non_live_and_public_safe():
    control = _control()

    test_config = control.configure_commercial_provider(
        "tenant_authpay",
        "project_authpay",
        provider="stripe",
        purpose="payment",
        mode="test",
        secret_ref="env:STRIPE_TEST_REF",
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
        account_ref="dashboard-ref:stripe/test/account",
        config_id="stripe_test_config",
        auth_key_id="key_commercial_writer",
    )
    live_config = control.configure_commercial_provider(
        "tenant_authpay",
        "project_authpay",
        provider="stripe",
        purpose="payment",
        mode="live",
        secret_ref="env:STRIPE_LIVE_REF",
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_LIVE",
        account_ref="dashboard-ref:stripe/live/account",
        live_mode_ack=True,
        config_id="stripe_live_config",
        auth_key_id="key_commercial_writer",
    )
    with pytest.raises(ValidationError, match="provider_specific_verification_required"):
        control.record_payment_mode_boundary(
            "tenant_authpay",
            "project_authpay",
            provider="stripe",
            mode="live",
            event_type="invoice.paid",
            event_id_ref="dashboard-ref:stripe/live/invoice_paid/manual_only",
            payload_sha256="d" * 64,
            signature_header_present=True,
            webhook_secret_ref="env:STRIPE_WEBHOOK_REF_LIVE",
            livemode=True,
            boundary_id="stripe_live_invoice_paid_boundary",
            auth_key_id="key_commercial_writer",
        )
    snapshot = control.commercial_auth_payment_snapshot("tenant_authpay", "project_authpay")
    text = json.dumps(snapshot, sort_keys=True)

    assert test_config["provider_called"] is False
    assert live_config["live_mode_ack"] is True
    assert live_config["live_mode_enabled"] is False
    assert live_config["real_charge_possible"] is False
    assert snapshot["payment_mode_boundaries"] == []
    assert "sk_live_" not in text
    assert "whsec_" not in text
    assert "card[number]" not in text

    with pytest.raises(ValidationError, match="live mode requires live_mode_ack"):
        control.configure_commercial_provider(
            "tenant_authpay",
            "project_authpay",
            provider="stripe",
            purpose="payment",
            mode="live",
            secret_ref="env:STRIPE_LIVE_REF",
            webhook_secret_ref="env:STRIPE_WEBHOOK_REF_LIVE",
        )
    with pytest.raises(ValidationError, match="test_event_received_in_live_mode"):
        control.record_payment_mode_boundary(
            "tenant_authpay",
            "project_authpay",
            provider="stripe",
            mode="live",
            event_type="invoice.paid",
            event_id_ref="evt_ref:stripe/test/invoice_paid",
            payload_sha256="e" * 64,
            signature_header_present=True,
            webhook_secret_ref="env:STRIPE_WEBHOOK_REF_LIVE",
            livemode=False,
        )


def test_sdk_and_router_expose_commercial_auth_payment_safety_routes():
    control = _control()
    client = SaaSIngestionClient(service=control)
    configured = client.configure_oauth_provider(
        "tenant_authpay",
        "project_authpay",
        provider="google",
        client_id_ref="env:GOOGLE_CLIENT_ID_REF",
        client_secret_ref="vault:google/client_secret_ref",
        redirect_uris=["https://app.releasefoundry.invalid/oauth/google/callback"],
        scopes=["openid", "email"],
        config_id="google_sdk_config",
        auth_key_id="key_commercial_writer",
    )
    assert configured["operation"] == "configure_oauth_provider"
    assert configured["result"]["secret_value_present"] is False

    calls: list[tuple[str, str, dict]] = []

    def transport(url: str, payload: dict, *, method: str, headers: dict | None = None) -> dict:
        calls.append((method, url, payload))
        return {"ok": True, "tenant_id": payload.get("tenant_id"), "project_id": payload.get("project_id")}

    http_client = SaaSIngestionClient.from_base_url("https://api.releasefoundry.invalid", http_transport=transport)
    http_client.commercial_auth_payment_snapshot("tenant auth", "project auth", auth_key_id="key_commercial_writer")
    assert calls[0][0] == "GET"
    assert calls[0][1].startswith("https://api.releasefoundry.invalid/v1/projects/project%20auth/commercial-auth-payment")

    router = SaaSControlPlaneRouter(control)
    routed = router.handle(
        "POST",
        "/v1/projects/project_authpay/commercial-auth-payment/providers/configure",
        {
            "tenant_id": "tenant_authpay",
            "auth_key_id": "key_commercial_writer",
            "provider": "stripe",
            "purpose": "payment",
            "mode": "test",
            "secret_ref": "env:STRIPE_TEST_REF",
            "webhook_secret_ref": "env:STRIPE_WEBHOOK_REF_TEST",
        },
    )
    assert routed["status_code"] == 200
    assert routed["body"]["secret_value_present"] is False
