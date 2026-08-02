from __future__ import annotations

import hashlib
import hmac
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
        price=BillingPrice("releasefoundry_scale_monthly", 9900, currency="usd", included_units=10000),
        success_url="https://app.releasefoundry.invalid/billing/success",
        cancel_url="https://app.releasefoundry.invalid/billing/cancel",
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
        return_url="https://app.releasefoundry.invalid/billing",
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
        price={"lookup_key": "releasefoundry_cn_team_monthly", "unit_amount_minor": 68800, "currency": "cny"},
        success_url="https://app.releasefoundry.invalid/cn/success",
        cancel_url="https://app.releasefoundry.invalid/cn/cancel",
        provider_config={"provider": "wechat", "mode": "test", "secret_ref": "vault:wechat/test/mch_private_key", "account_ref": "provider-ref:wechat/test/mch_demo"},
    )
    alipay = build_checkout_session_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        customer_ref="alipay-user-ref",
        price={"lookup_key": "releasefoundry_cn_team_monthly", "unit_amount_minor": 68800, "currency": "cny"},
        success_url="https://app.releasefoundry.invalid/cn/success",
        cancel_url="https://app.releasefoundry.invalid/cn/cancel",
        provider_config={"provider": "alipay_plus", "mode": "test", "secret_ref": "vault:alipay/test/app_private_key", "account_ref": "provider-ref:alipay/test/app_demo"},
    )

    assert wechat["provider"] == "wechat_pay"
    assert wechat["payment_methods"] == ["wechat_pay"]
    assert wechat["provider_request"]["trade_type"] == "NATIVE"
    assert wechat["provider_mode_boundary"]["hosted_surface"] == "wechat_pay_native_qr_handoff"
    assert alipay["provider"] == "alipay"
    assert alipay["payment_methods"] == ["alipay"]
    assert alipay["provider_request"]["total_amount"] == "688.00"
    assert alipay["provider_mode_boundary"]["hosted_surface"] == "alipay_trade_page_pay_handoff"


def test_live_mode_requires_explicit_ack_and_secret_indirection():
    with pytest.raises(BillingContractError, match="live_mode_ack"):
        build_checkout_session_plan(
            tenant_id="tenant_live",
            project_id="project_live",
            customer_ref="cus_live",
            price={"lookup_key": "enterprise", "unit_amount_minor": 100000, "currency": "usd"},
            success_url="https://app.releasefoundry.invalid/success",
            cancel_url="https://app.releasefoundry.invalid/cancel",
            provider_config={"provider": "stripe", "mode": "live", "secret_ref": "env:STRIPE_LIVE_REF"},
        )

    plan = build_checkout_session_plan(
        tenant_id="tenant_live",
        project_id="project_live",
        customer_ref="cus_live",
        price={"lookup_key": "enterprise", "unit_amount_minor": 100000, "currency": "usd"},
        success_url="https://app.releasefoundry.invalid/success",
        cancel_url="https://app.releasefoundry.invalid/cancel",
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
        "success_url": "https://app.releasefoundry.invalid/success",
        "cancel_url": "https://app.releasefoundry.invalid/cancel",
    }
    with pytest.raises(BillingContractError, match="raw secret"):
        build_checkout_session_plan(**base, provider_config={"provider": "stripe", "mode": "test", "secret_ref": "sk_test_should_not_be_here123456"})
    with pytest.raises(BillingContractError, match="sensitive billing"):
        build_checkout_session_plan(**base, provider_config={"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"}, metadata={"card_number": "4242 4242 4242 4242"})
    with pytest.raises(BillingContractError, match="https"):
        build_checkout_session_plan(**{**base, "success_url": "http://localhost/success"}, provider_config={"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"})


@pytest.mark.parametrize(
    ("provider_config", "expected_methods"),
    [
        ({"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF", "allowed_payment_methods": ["card"]}, ["card"]),
        ({"provider": "wechat_pay", "mode": "test", "secret_ref": "vault:wechat/test/mch_private_key", "allowed_payment_methods": ["wechat_pay"]}, ["wechat_pay"]),
        ({"provider": "alipay", "mode": "test", "secret_ref": "vault:alipay/test/app_private_key", "allowed_payment_methods": ["alipay"]}, ["alipay"]),
    ],
)
def test_provider_rails_allow_only_declared_payment_methods(provider_config, expected_methods):
    plan = build_checkout_session_plan(
        tenant_id="tenant_methods",
        project_id="project_methods",
        customer_ref="customer-ref",
        price={"lookup_key": "team", "unit_amount_minor": 1200, "currency": "cny" if provider_config["provider"] != "stripe" else "usd"},
        success_url="https://app.releasefoundry.invalid/success",
        cancel_url="https://app.releasefoundry.invalid/cancel",
        provider_config=provider_config,
    )

    assert plan["payment_methods"] == expected_methods
    assert plan["provider_mode_boundary"]["allowed_payment_methods"] == expected_methods
    assert plan["provider_mode_boundary"]["provider_called"] is False
    assert plan["provider_mode_boundary"]["real_charge_possible"] is False


@pytest.mark.parametrize(
    "provider_config",
    [
        {"provider": "stripe", "mode": "test", "secret_ref": "vault:stripe/test/key", "allowed_payment_methods": ["paypal"]},
        {"provider": "wechat_pay", "mode": "test", "secret_ref": "vault:wechat/test/mch_private_key", "allowed_payment_methods": ["card"]},
        {"provider": "alipay", "mode": "test", "secret_ref": "vault:alipay/test/app_private_key", "allowed_payment_methods": ["wechat_pay"]},
    ],
)
def test_provider_rails_reject_cross_provider_payment_methods(provider_config):
    with pytest.raises(BillingContractError, match="unsupported payment methods"):
        build_checkout_session_plan(
            tenant_id="tenant_methods",
            project_id="project_methods",
            customer_ref="customer-ref",
            price={"lookup_key": "team", "unit_amount_minor": 1200, "currency": "usd"},
            success_url="https://app.releasefoundry.invalid/success",
            cancel_url="https://app.releasefoundry.invalid/cancel",
            provider_config=provider_config,
        )


def test_provider_rails_require_reference_prefixes_for_secret_and_account_refs():
    with pytest.raises(BillingContractError, match="secret_ref is required"):
        BillingProviderConfig(provider="stripe", mode="test").normalized()
    with pytest.raises(BillingContractError, match="secret_ref must use an approved reference prefix"):
        BillingProviderConfig(provider="stripe", mode="test", secret_ref="STRIPE_TEST_REF").normalized()
    with pytest.raises(BillingContractError, match="account_ref must use an approved reference prefix"):
        BillingProviderConfig(provider="wechat_pay", mode="test", secret_ref="vault:wechat/test/mch_private_key", account_ref="mch:demo").normalized()


def test_billing_webhook_envelope_rejects_hash_and_header_only_verification():
    unverified = verify_billing_webhook_envelope(
        provider="stripe",
        mode="test",
        event_type="checkout.session.completed",
        event_id="evt_test_123",
        tenant_id="tenant_bill",
        project_id="project_bill",
        payload_sha256="a" * 64,
        signature_header_present=True,
        signature_header_names=["Stripe-Signature"],
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
    )
    assert unverified["verified"] is False
    assert {item["reason"] for item in unverified["failures"]} == {"provider_specific_verification_required"}
    assert unverified["signature_header_shape"]["expected_headers"] == ["stripe-signature"]
    assert unverified["raw_payload_included"] is False
    assert unverified["secret_value_present"] is False

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
    assert {item["reason"] for item in failed["failures"]} == {
        "missing_signature_header",
        "missing_live_webhook_secret_ref",
        "provider_specific_verification_required",
    }


def test_stripe_webhook_contract_verifies_raw_body_signature_without_persisting_secret_or_body():
    raw_body = b'{"id":"evt_raw_123","type":"invoice.paid","livemode":false}'
    signing_material = "local_fixture_signing_material"
    timestamp = 1780000000
    signature = hmac.new(signing_material.encode("utf-8"), f"{timestamp}.".encode("utf-8") + raw_body, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={signature}"

    verified = verify_billing_webhook_envelope(
        provider="stripe",
        mode="test",
        event_type="invoice.paid",
        event_id="evt_raw_123",
        tenant_id="tenant_bill",
        project_id="project_bill",
        payload_sha256="0" * 64,
        raw_body=raw_body,
        signature_header_present=True,
        signature_header_names=["Stripe-Signature"],
        stripe_signature_header=header,
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
        webhook_secret_resolver=lambda ref: signing_material,
        received_at_unix=timestamp,
        livemode=False,
    )
    text = json.dumps(verified, sort_keys=True)

    assert verified["verified"] is True
    assert verified["payload_sha256"] == hashlib.sha256(raw_body).hexdigest()
    assert verified["raw_body_signature_verification"] == {
        "required": True,
        "verified": True,
        "verifier": "stripe_raw_body_hmac_sha256",
        "attestation_schema_version": "releasefoundry.payment_verification_attestation.v1",
        "timestamp": timestamp,
        "v1_signature_count": 1,
        "failure_reasons": [],
        "raw_body_included": False,
        "raw_header_value_included": False,
        "secret_value_present": False,
    }
    assert raw_body.decode("utf-8") not in text
    assert signing_material not in text
    assert signature not in text

    replay_or_tamper = verify_billing_webhook_envelope(
        provider="stripe",
        mode="test",
        event_type="invoice.paid",
        event_id="evt_raw_123",
        tenant_id="tenant_bill",
        project_id="project_bill",
        payload_sha256="0" * 64,
        raw_body=raw_body + b" ",
        signature_header_present=True,
        signature_header_names=["Stripe-Signature"],
        stripe_signature_header=header,
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
        webhook_secret_resolver=lambda ref: signing_material,
        received_at_unix=timestamp + 301,
        livemode=False,
    )

    assert replay_or_tamper["verified"] is False
    assert {item["reason"] for item in replay_or_tamper["failures"]} == {"invalid_stripe_signature", "stripe_signature_timestamp_outside_tolerance"}


@pytest.mark.parametrize(
    ("provider", "event_type", "webhook_secret_ref", "headers"),
    [
        ("stripe", "invoice.paid", "env:STRIPE_WEBHOOK_REF_TEST", ["stripe-signature"]),
        ("wechat_pay", "wechat_pay.transaction.success", "vault:wechat/test/notify_verify", ["wechatpay-signature", "wechatpay-timestamp", "wechatpay-nonce", "wechatpay-serial"]),
        ("alipay", "alipay.trade.success", "vault:alipay/test/public_key", ["sign", "sign_type", "app_id", "trade_no"]),
    ],
)
def test_all_provider_webhook_envelopes_require_cryptographic_verification_beyond_header_shape(provider, event_type, webhook_secret_ref, headers):
    unverified = verify_billing_webhook_envelope(
        provider=provider,
        mode="test",
        event_type=event_type,
        event_id=f"evt_{provider}_1",
        tenant_id="tenant_hooks",
        project_id="project_hooks",
        payload_sha256="1" * 64,
        signature_header_present=True,
        signature_header_names=headers,
        webhook_secret_ref=webhook_secret_ref,
        livemode=False,
    )

    assert unverified["verified"] is False
    assert {item["reason"] for item in unverified["failures"]} == {"provider_specific_verification_required"}
    assert unverified["signature_header_shape"]["valid"] is True
    assert unverified["signature_header_shape"]["raw_header_values_included"] is False
    assert unverified["raw_payload_included"] is False
    assert unverified["secret_value_present"] is False


def test_provider_webhook_envelopes_reject_missing_refs_bad_headers_and_mode_crossing():
    bad_headers = verify_billing_webhook_envelope(
        provider="wechat_pay",
        mode="test",
        event_type="wechat_pay.transaction.success",
        event_id="evt_wechat_bad_header",
        tenant_id="tenant_hooks",
        project_id="project_hooks",
        payload_sha256="2" * 64,
        signature_header_present=True,
        signature_header_names=["wechatpay-signature"],
        webhook_secret_ref="vault:wechat/test/notify_verify",
        livemode=False,
    )
    assert bad_headers["verified"] is False
    assert bad_headers["failures"][0]["reason"] == "invalid_signature_header_shape"

    missing_ref = verify_billing_webhook_envelope(
        provider="alipay",
        mode="test",
        event_type="alipay.trade.success",
        event_id="evt_alipay_missing_ref",
        tenant_id="tenant_hooks",
        project_id="project_hooks",
        payload_sha256="3" * 64,
        signature_header_present=True,
        signature_header_names=["sign", "sign_type", "app_id", "trade_no"],
        livemode=False,
    )
    assert missing_ref["verified"] is False
    assert {failure["reason"] for failure in missing_ref["failures"]} == {
        "missing_webhook_secret_ref",
        "provider_specific_verification_required",
    }

    mode_crossing = verify_billing_webhook_envelope(
        provider="stripe",
        mode="live",
        event_type="invoice.paid",
        event_id="evt_stripe_test_in_live",
        tenant_id="tenant_hooks",
        project_id="project_hooks",
        payload_sha256="4" * 64,
        signature_header_present=True,
        signature_header_names=["stripe-signature"],
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_LIVE",
        livemode=False,
    )
    assert mode_crossing["verified"] is False
    assert {failure["reason"] for failure in mode_crossing["failures"]} == {
        "test_event_received_in_live_mode",
        "provider_specific_verification_required",
    }


def test_billing_provider_manifest_names_commercial_payment_rails():
    manifest = billing_provider_manifest()
    assert set(manifest["providers"]) == {"stripe", "wechat_pay", "alipay"}
    assert manifest["payment_methods"]["stripe"] == ["card", "alipay", "wechat_pay"]
    assert set(manifest["provider_mode_matrix"]) == {"stripe", "wechat_pay", "alipay"}
    assert manifest["provider_mode_matrix"]["wechat_pay"]["webhook_signature_headers"] == ["wechatpay-signature", "wechatpay-timestamp", "wechatpay-nonce", "wechatpay-serial"]
    assert manifest["provider_mode_matrix"]["alipay"]["allowed_payment_methods"] == ["alipay"]
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
    raw_body = b'{"id":"evt_invoice_paid_1","type":"invoice.paid","livemode":false}'
    signing_material = "local_fixture_billing_ledger_material"
    timestamp = 1780000000
    signature = hmac.new(signing_material.encode("utf-8"), f"{timestamp}.".encode("utf-8") + raw_body, hashlib.sha256).hexdigest()
    envelope = verify_billing_webhook_envelope(
        provider="stripe",
        mode="test",
        event_type="invoice.paid",
        event_id="evt_invoice_paid_1",
        tenant_id="tenant_bill",
        project_id="project_bill",
        payload_sha256="c" * 64,
        raw_body=raw_body,
        signature_header_present=True,
        signature_header_names=["stripe-signature"],
        stripe_signature_header=f"t={timestamp},v1={signature}",
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
        webhook_secret_resolver=lambda ref: signing_material,
        received_at_unix=timestamp,
        livemode=False,
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
    assert public["provider_events"][0]["payload_sha256"] == hashlib.sha256(raw_body).hexdigest()
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

    raw_body = b'{"id":"evt_secret_bad","type":"invoice.paid","livemode":false}'
    signing_material = "local_fixture_sensitive_metadata_material"
    timestamp = 1780000000
    signature = hmac.new(signing_material.encode("utf-8"), f"{timestamp}.".encode("utf-8") + raw_body, hashlib.sha256).hexdigest()
    verified = verify_billing_webhook_envelope(
        provider="stripe",
        mode="test",
        event_type="invoice.paid",
        event_id="evt_secret_bad",
        tenant_id="tenant_secret",
        project_id="project_secret",
        payload_sha256="f" * 64,
        raw_body=raw_body,
        signature_header_present=True,
        signature_header_names=["stripe-signature"],
        stripe_signature_header=f"t={timestamp},v1={signature}",
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
        webhook_secret_resolver=lambda ref: signing_material,
        received_at_unix=timestamp,
        livemode=False,
    )
    with pytest.raises(BillingContractError, match="sensitive billing"):
        ledger.ingest_provider_webhook(envelope=verified, customer_ref="cus_secret", metadata={"client_secret": "sk_test_badbadbadbad"})
