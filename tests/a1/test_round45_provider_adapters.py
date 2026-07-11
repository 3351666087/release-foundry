from __future__ import annotations

import hashlib
import json

import pytest

from services.api.oauth_providers import (
    OAuthClientConfig,
    OAuthProviderContractError,
    build_authorization_envelope,
    build_token_exchange_envelope,
    build_token_ref_envelope,
    derive_pkce_s256,
    hash_oauth_state,
    oauth_provider_contract_manifest,
    verify_callback_state,
)
from services.api.payment_providers import (
    HostedWalletPaymentAdapter,
    HostedWalletProviderConfig,
    PaymentModeGate,
    PaymentProviderContractError,
    SignatureVerificationResult,
    StripePaymentAdapter,
    StripeProviderConfig,
    payment_provider_contract_manifest,
)


class RecordingVerifier:
    def __init__(self, result: SignatureVerificationResult):
        self.result = result
        self.requests = []

    def verify(self, request):
        self.requests.append(request)
        return self.result


def _stripe(mode: str = "test", *, live_ack: bool = False):
    gate = PaymentModeGate(
        mode=mode,
        live_mode_ack=live_ack,
        live_execution_gate_ref=(
            "provider-ref:stripe/live/change-ticket/approved"
            if mode == "live"
            else None
        ),
    )
    return StripePaymentAdapter(
        StripeProviderConfig(
            mode_gate=gate,
            api_secret_ref=f"vault:stripe/{mode}/api",
            webhook_secret_ref=f"vault:stripe/{mode}/webhook",
            account_ref=f"dashboard-ref:stripe/{mode}/account",
        )
    )


def test_stripe_plan_requires_idempotency_and_remains_non_executable():
    plan = _stripe().build_checkout_plan(
        tenant_id="tenant_r45",
        project_id="project_r45",
        customer_ref="provider-ref:stripe/test/customer/42",
        price_ref="provider-ref:stripe/test/price/team",
        checkout_mode="subscription",
        quantity=2,
        success_url="https://app.ashr-clone.invalid/billing/success",
        cancel_url="https://app.ashr-clone.invalid/billing/cancel",
        idempotency_key="checkout:tenant_r45:order_42",
        metadata={"order_ref": "order_42"},
    )

    assert plan["provider"] == "stripe"
    assert plan["request_shape"]["checkout_mode"] == "subscription"
    assert plan["mode_gate"]["mode"] == "test"
    assert plan["mode_gate"]["adapter_can_execute"] is False
    assert plan["idempotency"]["required"] is True
    assert len(plan["idempotency"]["request_fingerprint_sha256"]) == 64
    assert plan["execution_hook"]["secret_resolution_deferred"] is True
    assert plan["side_effects"] == {
        "provider_called": False,
        "checkout_or_portal_called": False,
        "real_charge_possible": False,
        "network_io_performed": False,
    }

    with pytest.raises(PaymentProviderContractError, match="idempotency_key"):
        _stripe().build_portal_plan(
            tenant_id="tenant_r45",
            project_id="project_r45",
            customer_ref="provider-ref:stripe/test/customer/42",
            return_url="https://app.ashr-clone.invalid/billing",
            idempotency_key="short",
        )


def test_stripe_live_mode_requires_ack_and_external_gate_ref():
    with pytest.raises(PaymentProviderContractError, match="live_mode_ack"):
        StripeProviderConfig(
            mode_gate=PaymentModeGate(mode="live"),
            api_secret_ref="vault:stripe/live/api",
            webhook_secret_ref="vault:stripe/live/webhook",
        ).validate()

    with pytest.raises(PaymentProviderContractError, match="live_execution_gate_ref"):
        StripeProviderConfig(
            mode_gate=PaymentModeGate(mode="live", live_mode_ack=True),
            api_secret_ref="vault:stripe/live/api",
            webhook_secret_ref="vault:stripe/live/webhook",
        ).validate()

    live = _stripe("live", live_ack=True).build_portal_plan(
        tenant_id="tenant_r45",
        project_id="project_r45",
        customer_ref="provider-ref:stripe/live/customer/42",
        return_url="https://app.ashr-clone.invalid/billing",
        idempotency_key="portal:tenant_r45:customer_42",
    )
    assert live["mode_gate"]["live_mode_ack"] is True
    assert live["mode_gate"]["live_execution_gate_ref"].startswith("provider-ref:")
    assert live["side_effects"]["real_charge_possible"] is False


def test_stripe_raw_body_verification_uses_hook_without_persisting_values():
    raw_body = b'{"id":"event-fixture","livemode":false}'
    signature_value = "fixture-signature-value"
    verifier = RecordingVerifier(
        SignatureVerificationResult(
            verified=True,
            event_id_ref="dashboard-ref:stripe/test/event/fixture",
            event_type="invoice.paid",
            livemode=False,
        )
    )
    envelope = _stripe().verify_webhook(
        raw_body=raw_body,
        headers={"Stripe-Signature": signature_value},
        verifier=verifier,
    )
    serialized = json.dumps(envelope, sort_keys=True)

    assert len(verifier.requests) == 1
    assert verifier.requests[0].raw_body == raw_body
    assert verifier.requests[0].verification_key_ref == "vault:stripe/test/webhook"
    assert envelope["verified"] is True
    assert envelope["payload_sha256"] == hashlib.sha256(raw_body).hexdigest()
    assert envelope["raw_body_included"] is False
    assert raw_body.decode() not in serialized
    assert signature_value not in serialized


@pytest.mark.parametrize(
    ("provider", "surface"),
    [
        ("wechat_pay", "wechat_pay_native_qr_handoff"),
        ("alipay", "alipay_trade_page_pay_handoff"),
    ],
)
def test_wallet_adapters_build_hosted_plans_and_expose_verifier_interface(provider, surface):
    adapter = HostedWalletPaymentAdapter(
        HostedWalletProviderConfig(
            provider=provider,
            mode_gate=PaymentModeGate(),
            signing_key_ref=f"vault:{provider}/test/signing",
            verification_key_ref=f"vault:{provider}/test/verification",
            merchant_account_ref=f"provider-ref:{provider}/test/merchant",
        )
    )
    plan = adapter.build_hosted_payment_plan(
        tenant_id="tenant_r45",
        project_id="project_r45",
        order_ref=f"provider-ref:{provider}/test/order/42",
        amount_minor=880,
        currency="CNY",
        description="A1 team plan",
        return_url="https://app.ashr-clone.invalid/payment/return",
        notify_url="https://api.ashr-clone.invalid/payment/notify",
        idempotency_key=f"{provider}:tenant_r45:order_42",
    )
    expected_headers = payment_provider_contract_manifest()["providers"][provider][
        "signature_headers"
    ]
    verifier = RecordingVerifier(
        SignatureVerificationResult(
            verified=True,
            event_id_ref=f"dashboard-ref:{provider}/test/event/42",
            event_type="payment.succeeded",
            livemode=False,
        )
    )
    notification = adapter.verify_notification(
        raw_body=b'{"fixture":"notification"}',
        headers={name: f"value-{index}" for index, name in enumerate(expected_headers)},
        verifier=verifier,
    )

    assert plan["hosted_surface"] == surface
    assert plan["execution_hook"]["adapter_executes"] is False
    assert notification["verified"] is True
    assert notification["integration_hook"]["interface"] == "PaymentSignatureVerifier"


def test_payment_adapters_reject_raw_refs_sensitive_metadata_and_mode_crossing():
    with pytest.raises(PaymentProviderContractError, match="reference prefix"):
        StripeProviderConfig(
            mode_gate=PaymentModeGate(),
            api_secret_ref="raw-provider-key",
            webhook_secret_ref="vault:stripe/test/webhook",
        ).validate()

    with pytest.raises(PaymentProviderContractError, match="sensitive payment field"):
        _stripe().build_checkout_plan(
            tenant_id="tenant_r45",
            project_id="project_r45",
            customer_ref="provider-ref:stripe/test/customer/42",
            price_ref="provider-ref:stripe/test/price/team",
            checkout_mode="subscription",
            quantity=1,
            success_url="https://app.ashr-clone.invalid/success",
            cancel_url="https://app.ashr-clone.invalid/cancel",
            idempotency_key="checkout:tenant_r45:sensitive",
            metadata={"payment_credential": "forbidden"},
        )
    with pytest.raises(PaymentProviderContractError, match="possible card data"):
        _stripe().build_checkout_plan(
            tenant_id="tenant_r45",
            project_id="project_r45",
            customer_ref="provider-ref:stripe/test/customer/42",
            price_ref="provider-ref:stripe/test/price/team",
            checkout_mode="subscription",
            quantity=1,
            success_url="https://app.ashr-clone.invalid/success",
            cancel_url="https://app.ashr-clone.invalid/cancel",
            idempotency_key="checkout:tenant_r45:pan-guard",
            metadata={"note": "4242 4242 4242 4242"},
        )

    verifier = RecordingVerifier(
        SignatureVerificationResult(verified=True, livemode=True)
    )
    result = _stripe().verify_webhook(
        raw_body=b'{"livemode":true}',
        headers={"stripe-signature": "fixture"},
        verifier=verifier,
    )
    assert result["verified"] is False
    assert result["reason_codes"] == ["provider_mode_mismatch"]


@pytest.mark.parametrize("provider", ["github", "google"])
def test_oauth_metadata_pkce_state_and_authorization_envelopes_are_safe(provider):
    verifier = "A" * 43
    state = "state-round45-login-attempt-000001"
    pkce = derive_pkce_s256(verifier)
    state_record = hash_oauth_state(state)
    config = OAuthClientConfig(
        provider=provider,
        client_id_ref=f"env:{provider.upper()}_CLIENT_ID_REF",
        client_secret_ref=f"vault:{provider}/oauth/client-secret-ref",
        redirect_uri=f"https://app.ashr-clone.invalid/oauth/{provider}/callback",
        scopes=("openid", "email") if provider == "google" else ("read:user",),
    )
    envelope = build_authorization_envelope(
        config=config,
        state_ref=f"provider-ref:oauth/state/{provider}/attempt-1",
        state_sha256=state_record["state_sha256"],
        pkce_code_challenge=pkce["code_challenge"],
    )
    serialized = json.dumps(envelope, sort_keys=True)

    assert envelope["provider_metadata"]["provider"] == provider
    assert envelope["parameters"]["code_challenge_method"] == "S256"
    assert envelope["raw_state_present"] is False
    assert envelope["code_verifier_present"] is False
    assert envelope["token_value_present"] is False
    assert verifier not in serialized
    assert state not in serialized


def test_oauth_callback_rejects_state_mismatch_and_drops_code_ref():
    expected = hash_oauth_state("state-round45-expected-000001")["state_sha256"]
    mismatch = verify_callback_state(
        received_state="state-round45-attacker-000002",
        expected_state_sha256=expected,
        authorization_code_ref="vault:oauth/codes/code-1",
    )
    accepted = verify_callback_state(
        received_state="state-round45-expected-000001",
        expected_state_sha256=expected,
        authorization_code_ref="vault:oauth/codes/code-1",
    )

    assert mismatch["accepted"] is False
    assert mismatch["authorization_code_ref"] is None
    assert accepted["accepted"] is True
    assert accepted["authorization_code_ref"] == "vault:oauth/codes/code-1"


def test_oauth_token_exchange_and_session_envelopes_contain_refs_only():
    config = OAuthClientConfig(
        provider="google",
        client_id_ref="env:GOOGLE_CLIENT_ID_REF",
        client_secret_ref="vault:google/oauth/client-secret-ref",
        redirect_uri="https://app.ashr-clone.invalid/oauth/google/callback",
        scopes=("openid", "email", "profile"),
    )
    exchange = build_token_exchange_envelope(
        config=config,
        authorization_code_ref="vault:google/oauth/code/attempt-1",
        code_verifier_ref="vault:google/oauth/pkce/attempt-1",
    )
    tokens = build_token_ref_envelope(
        provider="google",
        subject_ref="provider-ref:google/user/subject-1",
        access_token_ref="vault:google/oauth/tokens/access-1",
        refresh_token_ref="vault:google/oauth/tokens/refresh-1",
        id_token_ref="vault:google/oauth/tokens/id-1",
        granted_scopes=("openid", "email"),
    )

    assert exchange["executor_contract"]["network_io_performed"] is False
    assert exchange["secret_value_present"] is False
    assert tokens["token_value_present"] is False
    assert all(
        tokens[name].startswith(("vault:", "provider-ref:"))
        for name in ("subject_ref", "access_token_ref", "refresh_token_ref", "id_token_ref")
    )


def test_oauth_contract_rejects_raw_secrets_plain_pkce_and_insecure_redirects():
    with pytest.raises(OAuthProviderContractError, match="reference prefix"):
        OAuthClientConfig(
            provider="github",
            client_id_ref="env:GITHUB_CLIENT_ID_REF",
            client_secret_ref="raw-client-material",
            redirect_uri="https://app.ashr-clone.invalid/oauth/github/callback",
            scopes=("read:user",),
        ).validate()
    with pytest.raises(OAuthProviderContractError, match="raw OAuth secret"):
        OAuthClientConfig(
            provider="github",
            client_id_ref="env:GITHUB_CLIENT_ID_REF",
            client_secret_ref="vault:github/" + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456",
            redirect_uri="https://app.ashr-clone.invalid/oauth/github/callback",
            scopes=("read:user",),
        ).validate()
    with pytest.raises(OAuthProviderContractError, match="43-128"):
        derive_pkce_s256("too-short")
    with pytest.raises(OAuthProviderContractError, match="HTTPS or localhost"):
        OAuthClientConfig(
            provider="github",
            client_id_ref="env:GITHUB_CLIENT_ID_REF",
            client_secret_ref="vault:github/oauth/client-secret-ref",
            redirect_uri="http://example.invalid/callback",
            scopes=("read:user",),
        ).validate()

    manifest = oauth_provider_contract_manifest()
    assert set(manifest["providers"]) == {"github", "google", "wechat", "alipay"}
    assert manifest["required_controls"]["disabled_by_default"] is True
    assert manifest["required_controls"]["pkce_method"] == "S256"
    assert manifest["required_controls"]["token_refs_only"] is True
