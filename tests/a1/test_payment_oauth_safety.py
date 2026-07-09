from __future__ import annotations

import json

import pytest

from services.api.control_plane import SaaSControlPlaneRouter, SaaSControlPlaneService
from services.api.runtime import ValidationError
from packages.sdk.ashr_clone.saas import SaaSIngestionClient


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
        redirect_uris=["https://app.ashr-clone.invalid/oauth/github/callback"],
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
        redirect_uris=["https://app.ashr-clone.invalid/oauth/google/callback"],
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
        session_id="session_github",
        auth_key_id="key_commercial_writer",
    )

    snapshot = control.commercial_auth_payment_snapshot("tenant_authpay", "project_authpay")
    text = json.dumps(snapshot, sort_keys=True)

    assert {item["provider"] for item in snapshot["oauth_provider_configs"]} == {"github", "google"}
    assert github["secret_value_present"] is False
    assert google["secret_value_present"] is False
    assert session["secret_value_present"] is False
    assert session["linked_rate_limit"]["operation"] == "oauth.session.create"
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
            redirect_uris=["https://app.ashr-clone.invalid/oauth/github/callback"],
            scopes=["read:user"],
        )


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
    boundary = control.record_payment_mode_boundary(
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
    assert boundary["envelope"]["provider_mode_boundary"] == {"livemode": True, "test_event_in_live_mode_allowed": False, "live_event_in_test_mode_allowed": False}
    assert boundary["secret_value_present"] is False
    assert boundary["linked_rate_limit"]["operation"] == "payment.mode_boundary.record"
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
        redirect_uris=["https://app.ashr-clone.invalid/oauth/google/callback"],
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

    http_client = SaaSIngestionClient.from_base_url("https://api.ashr-clone.invalid", http_transport=transport)
    http_client.commercial_auth_payment_snapshot("tenant auth", "project auth", auth_key_id="key_commercial_writer")
    assert calls[0][0] == "GET"
    assert calls[0][1].startswith("https://api.ashr-clone.invalid/v1/projects/project%20auth/commercial-auth-payment")

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
