from __future__ import annotations

import json

import pytest

from services.api.billing import (
    BILLING_SCHEMA_VERSION,
    BillingContractError,
    BillingPrice,
    BillingProviderConfig,
    billing_provider_manifest,
    build_billing_portal_plan,
    build_checkout_session_plan,
    verify_billing_webhook_envelope,
)
from services.api.platform import usage_billing_rollup


def test_stripe_checkout_plan_uses_hosted_test_mode_without_side_effects():
    rollup = usage_billing_rollup(
        [
            {"tenant_id": "tenant_bill", "project_id": "project_bill", "operation": "run.submit", "units": 12},
            {"tenant_id": "tenant_bill", "project_id": "project_bill", "operation": "trace.ingest", "units": 38},
        ],
        tenant_id="tenant_bill",
        project_id="project_bill",
        billing_period="2026-07",
    )
    plan = build_checkout_session_plan(
        tenant_id="tenant_bill",
        project_id="project_bill",
        customer_ref="cus_test_123",
        price=BillingPrice("ashr_scale_monthly", 9900, currency="usd", included_units=10000),
        success_url="https://app.ashr-clone.invalid/billing/success",
        cancel_url="https://app.ashr-clone.invalid/billing/cancel",
        provider_config=BillingProviderConfig(provider="stripe", mode="test", secret_ref="env:STRIPE_SECRET_KEY_TEST"),
        usage_rollup=rollup,
        metadata={"plan_family": "scale", "sales_motion": "self_serve"},
        idempotency_key="bill_once",
    )

    assert plan["schema_version"] == BILLING_SCHEMA_VERSION
    assert plan["provider"] == "stripe"
    assert plan["mode"] == "test"
    assert plan["provider_request"]["operation"] == "checkout.sessions.create"
    assert plan["provider_request"]["payment_method_types"] == ["card", "alipay", "wechat_pay"]
    assert plan["usage_rollup"]["billable_units"] == 50
    assert plan["side_effects"] == {"provider_called": False, "checkout_or_portal_called": False, "real_charge_possible": False}
    text = json.dumps(plan, sort_keys=True)
    assert "sk_test" not in text
    assert "4242424242424242" not in text


def test_stripe_billing_portal_plan_is_public_safe_and_plan_only():
    plan = build_billing_portal_plan(
        tenant_id="tenant_bill",
        project_id="project_bill",
        customer_ref="cus_portal_123",
        return_url="https://app.ashr-clone.invalid/billing",
        provider_config={"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_SECRET_KEY_TEST"},
    )

    assert plan["plan_type"] == "billing_portal"
    assert plan["provider_request"]["operation"] == "billing_portal.sessions.create"
    assert plan["provider_request"]["secret_ref"] == "env:STRIPE_SECRET_KEY_TEST"
    assert plan["side_effects"]["provider_called"] is False


def test_wechat_and_alipay_hosted_payment_contracts_are_first_class():
    wechat = build_checkout_session_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        customer_ref="wechat-openid-ref",
        price={"lookup_key": "ashr_cn_team_monthly", "unit_amount_minor": 68800, "currency": "cny"},
        success_url="https://app.ashr-clone.invalid/cn/success",
        cancel_url="https://app.ashr-clone.invalid/cn/cancel",
        provider_config={"provider": "wechat", "mode": "test", "secret_ref": "vault:wechat/test/mch_private_key", "account_ref": "mch:demo"},
    )
    alipay = build_checkout_session_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        customer_ref="alipay-user-ref",
        price={"lookup_key": "ashr_cn_team_monthly", "unit_amount_minor": 68800, "currency": "cny"},
        success_url="https://app.ashr-clone.invalid/cn/success",
        cancel_url="https://app.ashr-clone.invalid/cn/cancel",
        provider_config={"provider": "alipay_plus", "mode": "test", "secret_ref": "vault:alipay/test/app_private_key", "account_ref": "alipay-app:demo"},
    )

    assert wechat["provider"] == "wechat_pay"
    assert wechat["payment_methods"] == ["wechat_pay"]
    assert wechat["provider_request"]["trade_type"] == "NATIVE"
    assert alipay["provider"] == "alipay"
    assert alipay["payment_methods"] == ["alipay"]
    assert alipay["provider_request"]["total_amount"] == "688.00"


def test_live_mode_requires_explicit_ack_and_secret_indirection():
    with pytest.raises(BillingContractError, match="live_mode_ack"):
        build_checkout_session_plan(
            tenant_id="tenant_live",
            project_id="project_live",
            customer_ref="cus_live",
            price={"lookup_key": "enterprise", "unit_amount_minor": 100000, "currency": "usd"},
            success_url="https://app.ashr-clone.invalid/success",
            cancel_url="https://app.ashr-clone.invalid/cancel",
            provider_config={"provider": "stripe", "mode": "live", "secret_ref": "env:STRIPE_SECRET_KEY_LIVE"},
        )

    plan = build_checkout_session_plan(
        tenant_id="tenant_live",
        project_id="project_live",
        customer_ref="cus_live",
        price={"lookup_key": "enterprise", "unit_amount_minor": 100000, "currency": "usd"},
        success_url="https://app.ashr-clone.invalid/success",
        cancel_url="https://app.ashr-clone.invalid/cancel",
        provider_config={"provider": "stripe", "mode": "live", "secret_ref": "env:STRIPE_SECRET_KEY_LIVE", "live_mode_ack": True},
    )
    assert plan["mode"] == "live"
    assert plan["side_effects"]["provider_called"] is False
    assert plan["side_effects"]["real_charge_possible"] is False


def test_billing_contract_rejects_raw_secrets_cards_and_insecure_redirects():
    base = {
        "tenant_id": "tenant_secret",
        "project_id": "project_secret",
        "customer_ref": "cus_secret",
        "price": {"lookup_key": "team", "unit_amount_minor": 1000, "currency": "usd"},
        "success_url": "https://app.ashr-clone.invalid/success",
        "cancel_url": "https://app.ashr-clone.invalid/cancel",
    }
    with pytest.raises(BillingContractError, match="raw secret"):
        build_checkout_session_plan(**base, provider_config={"provider": "stripe", "mode": "test", "secret_ref": "sk_test_should_not_be_here123456"})
    with pytest.raises(BillingContractError, match="sensitive billing"):
        build_checkout_session_plan(**base, provider_config={"provider": "stripe", "mode": "test"}, metadata={"card_number": "4242 4242 4242 4242"})
    with pytest.raises(BillingContractError, match="https"):
        build_checkout_session_plan(**{**base, "success_url": "http://localhost/success"}, provider_config={"provider": "stripe", "mode": "test"})


def test_billing_webhook_envelope_verification_is_hash_only():
    verified = verify_billing_webhook_envelope(
        provider="stripe",
        mode="test",
        event_type="checkout.session.completed",
        event_id="evt_test_123",
        tenant_id="tenant_bill",
        project_id="project_bill",
        payload_sha256="a" * 64,
        signature_header_present=True,
        webhook_secret_ref="env:STRIPE_WEBHOOK_SECRET_TEST",
    )
    assert verified["verified"] is True
    assert verified["raw_payload_included"] is False
    assert verified["secret_value_present"] is False

    failed = verify_billing_webhook_envelope(
        provider="stripe",
        mode="live",
        event_type="invoice.paid",
        event_id="evt_live_123",
        tenant_id="tenant_bill",
        project_id="project_bill",
        payload_sha256="b" * 64,
        signature_header_present=False,
        livemode=True,
    )
    assert failed["verified"] is False
    assert {item["reason"] for item in failed["failures"]} == {"missing_signature_header", "missing_live_webhook_secret_ref"}


def test_billing_provider_manifest_names_commercial_payment_rails():
    manifest = billing_provider_manifest()
    assert set(manifest["providers"]) == {"stripe", "wechat_pay", "alipay"}
    assert manifest["payment_methods"]["stripe"] == ["card", "alipay", "wechat_pay"]
    assert "raw provider secrets are rejected" in manifest["live_mode_guardrails"]
