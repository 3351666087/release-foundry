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
        provider_config=BillingProviderConfig(provider="stripe", mode="test", secret_ref="env:STRIPE_TEST_REF"),
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
        provider_config={"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"},
    )

    assert plan["plan_type"] == "billing_portal"
    assert plan["provider_request"]["operation"] == "billing_portal.sessions.create"
    assert plan["provider_request"]["secret_ref"] == "env:STRIPE_TEST_REF"
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
            provider_config={"provider": "stripe", "mode": "live", "secret_ref": "env:STRIPE_LIVE_REF"},
        )

    plan = build_checkout_session_plan(
        tenant_id="tenant_live",
        project_id="project_live",
        customer_ref="cus_live",
        price={"lookup_key": "enterprise", "unit_amount_minor": 100000, "currency": "usd"},
        success_url="https://app.ashr-clone.invalid/success",
        cancel_url="https://app.ashr-clone.invalid/cancel",
        provider_config={"provider": "stripe", "mode": "live", "secret_ref": "env:STRIPE_LIVE_REF", "live_mode_ack": True},
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
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
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


def test_billing_ledger_appends_provider_events_idempotently_and_detects_conflict():
    from services.api.billing import BillingLedger, billing_evidence_snapshot

    ledger = BillingLedger()
    ledger.upsert_billing_account(
        tenant_id="tenant_bill",
        project_id="project_bill",
        provider="stripe",
        mode="test",
        customer_ref="cus_test_123",
        account_ref="acct_test_ref",
    )
    envelope = verify_billing_webhook_envelope(
        provider="stripe",
        mode="test",
        event_type="invoice.paid",
        event_id="evt_invoice_paid_1",
        tenant_id="tenant_bill",
        project_id="project_bill",
        payload_sha256="c" * 64,
        signature_header_present=True,
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
    )

    accepted = ledger.ingest_provider_webhook(
        envelope=envelope,
        customer_ref="cus_test_123",
        amount_minor=9900,
        currency="usd",
        invoice_ref="in_test_123",
        metadata={"billing_period": "2026-07"},
    )
    duplicate = ledger.ingest_provider_webhook(
        envelope=envelope,
        customer_ref="cus_test_123",
        amount_minor=9900,
        currency="usd",
        invoice_ref="in_test_123",
    )
    conflict_envelope = {**envelope, "payload_sha256": "d" * 64}
    conflict = ledger.ingest_provider_webhook(envelope=conflict_envelope, customer_ref="cus_test_123")

    assert accepted["ingest_status"] == "accepted"
    assert accepted["ledger_event_type"] == "invoice_paid"
    assert accepted["ledger_mutation_count"] == 1
    assert duplicate["ingest_status"] == "duplicate"
    assert duplicate["ledger_mutation_count"] == 0
    assert conflict["ingest_status"] == "conflict"
    assert conflict["ledger_mutation_count"] == 0
    assert duplicate["ledger_event_id"] == accepted["ledger_event_id"]
    assert conflict["ledger_event_id"] == accepted["ledger_event_id"]
    assert conflict["conflict_payload_sha256"] == "d" * 64

    public = ledger.public_ledger(tenant_id="tenant_bill", project_id="project_bill")
    assert public["ledger_event_count"] == 1
    assert public["provider_event_count"] == 1
    assert public["totals_by_currency_minor"] == {"usd": 9900}
    assert public["provider_events"][0]["payload_sha256"] == "c" * 64
    assert public["provider_events"][0]["raw_payload_included"] is False
    assert "provider_config" not in json.dumps(public, sort_keys=True)
    evidence = billing_evidence_snapshot(ledger=ledger, tenant_id="tenant_bill", project_id="project_bill")
    assert len(evidence["billing_snapshot_sha256"]) == 64
    assert evidence["ledger_event_count"] == 1
    assert evidence["provider_event_count"] == 1
    assert evidence["raw_payload_included"] is False
    assert evidence["secret_value_present"] is False
    assert json.dumps(public, sort_keys=True).find("sk_test") == -1
    assert json.dumps(public, sort_keys=True).find("whsec") == -1


def test_billing_ledger_reconciles_usage_and_scopes_tenant_readback():
    from services.api.billing import BillingLedger

    ledger = BillingLedger()
    usage_a = usage_billing_rollup(
        [
            {"tenant_id": "tenant_a", "project_id": "project_a", "operation": "sdk.submit", "units": 7},
            {"tenant_id": "tenant_a", "project_id": "project_a", "operation": "trace.ingest", "units": 13},
            {"tenant_id": "tenant_b", "project_id": "project_b", "operation": "sdk.submit", "units": 99},
        ],
        tenant_id="tenant_a",
        project_id="project_a",
        billing_period="2026-07",
    )
    usage_b = usage_billing_rollup(
        [{"tenant_id": "tenant_b", "project_id": "project_b", "operation": "sdk.submit", "units": 99}],
        tenant_id="tenant_b",
        project_id="project_b",
        billing_period="2026-07",
    )
    ledger.reconcile_usage_rollup(usage_a, customer_ref="cus_a")
    ledger.reconcile_usage_rollup(usage_b, customer_ref="cus_b")

    public_a = ledger.public_ledger(tenant_id="tenant_a", project_id="project_a")
    public_b = ledger.public_ledger(tenant_id="tenant_b", project_id="project_b")
    assert public_a["ledger_event_count"] == 1
    assert public_a["usage_units"] == 20
    assert public_b["ledger_event_count"] == 1
    assert public_b["usage_units"] == 99
    assert "cus_b" not in json.dumps(public_a, sort_keys=True)
    assert "tenant_b" not in json.dumps(public_a, sort_keys=True)


def test_billing_ledger_rejects_unverified_webhooks_and_sensitive_metadata():
    from services.api.billing import BillingLedger

    ledger = BillingLedger()
    failed = verify_billing_webhook_envelope(
        provider="stripe",
        mode="live",
        event_type="invoice.paid",
        event_id="evt_live_bad",
        tenant_id="tenant_live",
        project_id="project_live",
        payload_sha256="e" * 64,
        signature_header_present=False,
        livemode=True,
    )
    with pytest.raises(BillingContractError, match="unverified"):
        ledger.ingest_provider_webhook(envelope=failed, customer_ref="cus_live")

    verified = verify_billing_webhook_envelope(
        provider="stripe",
        mode="test",
        event_type="invoice.paid",
        event_id="evt_secret_bad",
        tenant_id="tenant_secret",
        project_id="project_secret",
        payload_sha256="f" * 64,
        signature_header_present=True,
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
    )
    with pytest.raises(BillingContractError, match="sensitive billing"):
        ledger.ingest_provider_webhook(envelope=verified, customer_ref="cus_secret", metadata={"client_secret": "sk_test_badbadbadbad"})
