from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from services.api.payment_providers import (
    PaymentModeGate,
    PaymentProviderContractError,
    SignatureVerificationRequest,
    StripePaymentAdapter,
    StripeProviderConfig,
)
from services.api.stripe_executor import (
    EnvSecretResolver,
    StripeExecutorError,
    StripeIdempotencyConflict,
    StripeTestModeExecutor,
    StripeWebhookVerifierAdapter,
)


class RecordingStripeFacade:
    def __init__(self):
        self.calls = []

    def create_checkout_session(self, **kwargs):
        self.calls.append(("checkout", kwargs))
        return {
            "id": "cs_test_round46_checkout",
            "url": "https://checkout.stripe.com/c/pay/cs_test_round46_checkout",
            "object": "checkout.session",
            "livemode": False,
            "raw_provider_payload": {"card": "must-not-escape"},
        }

    def create_billing_portal_session(self, **kwargs):
        self.calls.append(("portal", kwargs))
        return {
            "id": "bps_round46_portal",
            "url": "https://billing.stripe.com/p/session/bps_round46_portal",
            "object": "billing_portal.session",
            "livemode": False,
            "customer": "cus_round46",
        }


class RecordingWebhookFacade:
    def __init__(self, event):
        self.event = event
        self.calls = []

    def construct_webhook_event(self, **kwargs):
        self.calls.append(kwargs)
        return self.event


def _adapter(*, mode="test", credential_ref="env:STRIPE_SECRET_KEY"):
    return StripePaymentAdapter(
        StripeProviderConfig(
            mode_gate=PaymentModeGate(
                mode=mode,
                live_mode_ack=mode == "live",
                live_execution_gate_ref=(
                    "provider-ref:stripe/live/change/approved" if mode == "live" else None
                ),
            ),
            api_secret_ref=credential_ref,
            webhook_secret_ref="env:STRIPE_WEBHOOK_SECRET",
            account_ref=None,
        )
    )


def _checkout_plan(
    *,
    idempotency_key="checkout:round46:order-1",
    quantity=1,
    checkout_mode="subscription",
):
    return _adapter().build_checkout_plan(
        tenant_id="tenant_round46",
        project_id="project_round46",
        customer_ref="provider-ref:stripe/test/customer/cus_round46",
        price_ref="provider-ref:stripe/test/price/price_round46_team",
        checkout_mode=checkout_mode,
        quantity=quantity,
        success_url="https://app.releasefoundry.invalid/billing/success",
        cancel_url="https://app.releasefoundry.invalid/billing/cancel",
        idempotency_key=idempotency_key,
        metadata={"order_ref": "order_round46"},
    )


def _executor(facade=None, store=None):
    return StripeTestModeExecutor(
        facade=facade or RecordingStripeFacade(),
        secret_resolver=EnvSecretResolver(
            {
                "STRIPE_SECRET_KEY": "sk_test_fixture_round46",
                "STRIPE_WEBHOOK_SECRET": "whsec_fixture_round46",
            }
        ),
        idempotency_store=store,
    )


def test_checkout_execution_is_public_safe_and_resolves_env_secret_only_at_boundary():
    facade = RecordingStripeFacade()
    result = _executor(facade).execute(_checkout_plan())

    assert result == {
        "mode": "test",
        "object_ref": (
            "provider-ref:stripe/test/checkout.session/cs_test_round46_checkout"
        ),
        "session_id": "cs_test_round46_checkout",
        "url": "https://checkout.stripe.com/c/pay/cs_test_round46_checkout",
    }
    assert len(facade.calls) == 1
    _, call = facade.calls[0]
    assert call["api_key"] == "sk_test_fixture_round46"
    assert call["idempotency_key"] == "checkout:round46:order-1"
    assert call["params"]["customer"] == "cus_round46"
    assert call["params"]["line_items"] == [
        {"price": "price_round46_team", "quantity": 1}
    ]
    assert call["params"]["mode"] == "subscription"
    serialized = json.dumps(result, sort_keys=True)
    assert "sk_test_fixture" not in serialized
    assert "raw_provider_payload" not in serialized
    assert "card" not in serialized
    assert set(result) == {
        "mode",
        "object_ref",
        "session_id",
        "url",
    }


def test_checkout_execution_preserves_explicit_one_time_payment_mode():
    facade = RecordingStripeFacade()

    _executor(facade).execute(_checkout_plan(checkout_mode="payment"))

    assert facade.calls[0][1]["params"]["mode"] == "payment"


def test_checkout_plan_rejects_ambiguous_or_unsupported_mode():
    with pytest.raises(
        PaymentProviderContractError,
        match="checkout_mode must be payment or subscription",
    ):
        _checkout_plan(checkout_mode="")
    with pytest.raises(
        PaymentProviderContractError,
        match="checkout_mode must be payment or subscription",
    ):
        _checkout_plan(checkout_mode="setup")


def test_portal_execution_maps_only_hosted_session_fields():
    facade = RecordingStripeFacade()
    plan = _adapter().build_portal_plan(
        tenant_id="tenant_round46",
        project_id="project_round46",
        customer_ref="provider-ref:stripe/test/customer/cus_round46",
        return_url="https://app.releasefoundry.invalid/billing",
        idempotency_key="portal:round46:customer-1",
    )

    result = _executor(facade).execute(plan)

    assert result["object_ref"].startswith(
        "provider-ref:stripe/test/billing_portal.session/"
    )
    assert result["session_id"] == "bps_round46_portal"
    assert "customer" not in result
    assert facade.calls[0][1]["params"] == {
        "customer": "cus_round46",
        "return_url": "https://app.releasefoundry.invalid/billing",
    }


def test_idempotency_replay_returns_prior_result_and_conflict_blocks_provider_call():
    facade = RecordingStripeFacade()
    store = {}
    executor = _executor(facade, store)
    original = _checkout_plan()

    first = executor.execute(original)
    second = executor.execute(original)
    conflict = _checkout_plan(quantity=2)
    conflict["idempotency"]["key"] = original["idempotency"]["key"]

    assert first == second
    assert len(facade.calls) == 1
    with pytest.raises(StripeIdempotencyConflict, match="different request fingerprint"):
        executor.execute(conflict)
    assert len(facade.calls) == 1


def test_executor_rejects_live_plans_non_env_refs_and_live_secrets():
    live_plan = _adapter(
        mode="live", credential_ref="env:STRIPE_SECRET_KEY"
    ).build_portal_plan(
        tenant_id="tenant_round46",
        project_id="project_round46",
        customer_ref="provider-ref:stripe/live/customer/cus_live_round46",
        return_url="https://app.releasefoundry.invalid/billing",
        idempotency_key="portal:round46:live-customer",
    )
    with pytest.raises(StripeExecutorError, match="rejects live mode"):
        _executor().execute(live_plan)

    non_env = _checkout_plan()
    non_env["credential_ref"] = "vault:stripe/test/api"
    with pytest.raises(StripeExecutorError, match="must use env:NAME"):
        _executor().execute(non_env)

    live_secret_executor = StripeTestModeExecutor(
        facade=RecordingStripeFacade(),
        secret_resolver=EnvSecretResolver(
            {
                "STRIPE_SECRET_KEY": "sk_live_fixture_round46",
                "STRIPE_WEBHOOK_SECRET": "whsec_fixture_round46",
            }
        ),
    )
    with pytest.raises(StripeExecutorError, match="test-mode secret"):
        live_secret_executor.execute(_checkout_plan())


def test_fingerprint_tampering_is_rejected_before_transport():
    facade = RecordingStripeFacade()
    plan = _checkout_plan()
    plan["request_shape"]["quantity"] = 99

    with pytest.raises(StripeExecutorError, match="fingerprint mismatch"):
        _executor(facade).execute(plan)
    assert facade.calls == []


def test_webhook_sdk_facade_maps_test_event_without_exposing_secret_or_payload():
    webhook = RecordingWebhookFacade(
        {
            "id": "evt_round46_invoice_paid",
            "type": "invoice.paid",
            "livemode": False,
            "data": {"object": {"card": "must-not-escape"}},
        }
    )
    verifier = StripeWebhookVerifierAdapter(
        secret_resolver=EnvSecretResolver(
            {"STRIPE_WEBHOOK_SECRET": "whsec_fixture_round46"}
        ),
        facade=webhook,
    )
    request = SignatureVerificationRequest(
        provider="stripe",
        mode="test",
        raw_body=b'{"id":"evt_round46_invoice_paid"}',
        headers={"Stripe-Signature": "t=100,v1=fixture-signature"},
        verification_key_ref="env:STRIPE_WEBHOOK_SECRET",
        expected_livemode=False,
    )

    result = verifier.verify(request)

    assert result.verified is True
    assert result.event_id_ref == (
        "provider-ref:stripe/test/event/evt_round46_invoice_paid"
    )
    assert result.event_type == "invoice.paid"
    assert result.livemode is False
    assert result.reason_codes == ()
    assert webhook.calls[0]["secret"] == "whsec_fixture_round46"
    assert not hasattr(result, "raw_body")
    assert "whsec_fixture_round46" not in repr(result)


def test_standard_library_webhook_verification_and_live_event_rejection():
    timestamp = 1_700_000_000
    secret = "whsec_fixture_round46"
    payload = json.dumps(
        {
            "id": "evt_round46_checkout",
            "type": "checkout.session.completed",
            "livemode": False,
        },
        separators=(",", ":"),
    ).encode()
    digest = hmac.new(
        secret.encode(),
        str(timestamp).encode() + b"." + payload,
        hashlib.sha256,
    ).hexdigest()
    verifier = StripeWebhookVerifierAdapter(
        secret_resolver=EnvSecretResolver({"STRIPE_WEBHOOK_SECRET": secret}),
        tolerance_seconds=300,
        clock=lambda: timestamp + 20,
    )
    request = SignatureVerificationRequest(
        provider="stripe",
        mode="test",
        raw_body=payload,
        headers={"stripe-signature": f"t={timestamp},v1={digest}"},
        verification_key_ref="env:STRIPE_WEBHOOK_SECRET",
        expected_livemode=False,
    )

    result = verifier.verify(request)

    assert result.verified is True
    assert result.event_type == "checkout.session.completed"

    live_webhook = RecordingWebhookFacade(
        {"id": "evt_round46_live", "type": "invoice.paid", "livemode": True}
    )
    live_result = StripeWebhookVerifierAdapter(
        secret_resolver=EnvSecretResolver({"STRIPE_WEBHOOK_SECRET": secret}),
        facade=live_webhook,
    ).verify(request)
    assert live_result.verified is False
    assert live_result.reason_codes == ("provider_mode_mismatch",)


def test_webhook_signature_failure_is_public_and_stable():
    verifier = StripeWebhookVerifierAdapter(
        secret_resolver=EnvSecretResolver(
            {"STRIPE_WEBHOOK_SECRET": "whsec_fixture_round46"}
        ),
        tolerance_seconds=0,
        clock=lambda: 100,
    )
    request = SignatureVerificationRequest(
        provider="stripe",
        mode="test",
        raw_body=b'{"id":"evt_round46_invalid"}',
        headers={"stripe-signature": "t=100,v1=invalid"},
        verification_key_ref="env:STRIPE_WEBHOOK_SECRET",
        expected_livemode=False,
    )

    result = verifier.verify(request)

    assert result.verified is False
    assert result.event_id_ref is None
    assert result.reason_codes == ("signature_verification_failed",)
