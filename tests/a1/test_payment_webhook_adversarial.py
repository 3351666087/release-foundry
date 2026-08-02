from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from services.api.billing import (
    BillingContractError,
    BillingLedger,
    build_billing_portal_plan,
    build_checkout_session_plan,
    verify_billing_webhook_envelope,
)
from services.api.control_plane import SaaSControlPlaneRouter, SaaSControlPlaneService
from services.api.runtime import CloudApiService


def _attesting_verifier(**overrides):
    def verify(challenge):
        return {
            "schema_version": "releasefoundry.payment_verification_attestation.v1",
            "verifier": f"{challenge['provider']}_cryptographic_verifier",
            "verified": True,
            **challenge,
            **overrides,
        }

    return verify


@pytest.mark.parametrize(
    ("provider", "headers", "secret_ref"),
    [
        ("wechat_pay", ["wechatpay-signature", "wechatpay-timestamp", "wechatpay-nonce", "wechatpay-serial"], "vault:wechat/test/verify"),
        ("alipay", ["sign", "sign_type", "app_id", "trade_no"], "vault:alipay/test/verify"),
    ],
)
def test_header_hash_and_reference_cannot_verify_domestic_callbacks(provider, headers, secret_ref):
    envelope = verify_billing_webhook_envelope(
        provider=provider,
        mode="test",
        event_type="trade.success",
        event_id="evt_forged",
        tenant_id="tenant_attack",
        project_id="project_attack",
        payload_sha256="a" * 64,
        signature_header_present=True,
        signature_header_names=headers,
        webhook_secret_ref=secret_ref,
        livemode=False,
    )

    assert envelope["verified"] is False
    assert "provider_specific_verification_required" in {item["reason"] for item in envelope["failures"]}
    with pytest.raises(BillingContractError, match="unverified"):
        BillingLedger().ingest_provider_webhook(envelope=envelope, customer_ref="attacker")


def test_structured_attestation_is_bound_to_scope_payload_and_provider():
    verified = verify_billing_webhook_envelope(
        provider="wechat_pay",
        mode="test",
        event_type="transaction.success",
        event_id="evt_bound",
        tenant_id="tenant_bound",
        project_id="project_bound",
        payload_sha256="b" * 64,
        signature_header_present=True,
        signature_header_names=["wechatpay-signature", "wechatpay-timestamp", "wechatpay-nonce", "wechatpay-serial"],
        webhook_secret_ref="vault:wechat/test/verify",
        provider_verifier=_attesting_verifier(),
        livemode=False,
    )
    wrong_merchant = verify_billing_webhook_envelope(
        provider="wechat_pay",
        mode="test",
        event_type="transaction.success",
        event_id="evt_bound",
        tenant_id="tenant_bound",
        project_id="project_bound",
        payload_sha256="b" * 64,
        signature_header_present=True,
        signature_header_names=["wechatpay-signature", "wechatpay-timestamp", "wechatpay-nonce", "wechatpay-serial"],
        webhook_secret_ref="vault:wechat/test/verify",
        provider_verifier=_attesting_verifier(project_id="project_attacker"),
        livemode=False,
    )

    assert verified["verified"] is True
    assert wrong_merchant["verified"] is False
    assert "provider_attestation_project_id_mismatch" in {item["reason"] for item in wrong_merchant["failures"]}


def test_stripe_requires_real_raw_body_signature_and_rejects_stale_replay():
    body = b'{"id":"evt_signed","livemode":false}'
    timestamp = 1_800_000_000
    signing_material = "fixture_signing_material"
    signature = hmac.new(signing_material.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    common = dict(
        provider="stripe",
        mode="test",
        event_type="invoice.paid",
        event_id="evt_signed",
        tenant_id="tenant_stripe",
        project_id="project_stripe",
        payload_sha256="0" * 64,
        raw_body=body,
        signature_header_present=True,
        signature_header_names=["stripe-signature"],
        stripe_signature_header=f"t={timestamp},v1={signature}",
        webhook_secret_ref="env:STRIPE_WEBHOOK_REF_TEST",
        webhook_secret_resolver=lambda _: signing_material,
        livemode=False,
    )

    assert verify_billing_webhook_envelope(**common, received_at_unix=timestamp)["verified"] is True
    stale = verify_billing_webhook_envelope(**common, received_at_unix=timestamp + 301)
    assert stale["verified"] is False
    assert "stripe_signature_timestamp_outside_tolerance" in {item["reason"] for item in stale["failures"]}


def test_provider_neutral_checkout_and_portal_have_no_implicit_stripe():
    checkout = dict(
        tenant_id="tenant_explicit",
        project_id="project_explicit",
        customer_ref="customer",
        price={"lookup_key": "team", "unit_amount_minor": 1000, "currency": "usd"},
        success_url="https://example.invalid/success",
        cancel_url="https://example.invalid/cancel",
    )
    with pytest.raises(BillingContractError, match="explicit provider"):
        build_checkout_session_plan(**checkout)
    with pytest.raises(BillingContractError, match="explicit provider"):
        build_billing_portal_plan(
            tenant_id="tenant_explicit",
            project_id="project_explicit",
            customer_ref="customer",
            return_url="https://example.invalid/billing",
        )
    explicit = build_checkout_session_plan(
        **checkout,
        provider_config={"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF"},
    )
    assert explicit["provider"] == "stripe"


def test_public_reconciliation_mutation_routes_are_not_exposed():
    cloud = CloudApiService()
    cloud.create_tenant("Tenant", tenant_id="tenant_routes")
    cloud.create_project("tenant_routes", "Project", project_id="project_routes")
    app = SaaSControlPlaneRouter(SaaSControlPlaneService(cloud))

    for transition in ("verify", "apply", "fail"):
        response = app.handle(
            "POST",
            f"/v1/projects/project_routes/billing/reconciliation/receipt/{transition}",
            {"tenant_id": "tenant_routes"},
        )
        assert response["status_code"] == 404, json.dumps(response, sort_keys=True)
