from __future__ import annotations

import hashlib
import json

import pytest

from services.api.china_payments import (
    CHINA_PAYMENT_SCHEMA_VERSION,
    ChinaMerchantConfig,
    ChinaPaymentContractError,
    ChinaPaymentDomain,
    NotificationVerificationResult,
    PaymentIdempotencyConflict,
    PaymentScopeViolation,
    ScopedIdempotencyRegistry,
    china_payment_capability_matrix,
    normalize_payment_lifecycle,
)
from services.api.payment_providers import (
    PaymentModeGate,
    payment_provider_contract_manifest,
)


class RecordingNotificationVerifier:
    def __init__(self, result: NotificationVerificationResult):
        self.result = result
        self.requests = []

    def verify(self, request):
        self.requests.append(request)
        return self.result


def _config(provider: str) -> ChinaMerchantConfig:
    return ChinaMerchantConfig(
        provider=provider,
        mode_gate=PaymentModeGate(),
        merchant_ref=f"provider-ref:{provider}/test/merchant/ashr",
        app_ref=f"provider-ref:{provider}/test/app/ashr",
        signing_key_ref=f"vault:{provider}/test/signing-key-ref",
        verification_key_ref=f"vault:{provider}/test/verification-key-ref",
        certificate_refs=(
            f"provider-ref:{provider}/test/certificate/current",
            f"provider-ref:{provider}/test/certificate/previous",
        ),
        api_v3_key_ref=(
            "vault:wechat_pay/test/api-v3-key-ref"
            if provider == "wechat_pay"
            else None
        ),
        acquirer_ref=(
            "provider-ref:domestic_bank_card/test/acquirer/ashr"
            if provider == "domestic_bank_card"
            else None
        ),
        account_binding_ref=(
            "provider-ref:domestic_bank_card/test/account-binding/ashr"
            if provider == "domestic_bank_card"
            else None
        ),
    )


def _domain(
    provider: str, registry: ScopedIdempotencyRegistry | None = None
) -> ChinaPaymentDomain:
    return ChinaPaymentDomain(_config(provider), idempotency_registry=registry)


def _trade(
    domain: ChinaPaymentDomain,
    *,
    tenant_id: str = "tenant_cn",
    project_id: str = "project_cn",
    order_ref: str = "provider-ref:orders/cn/order-42",
    channel: str = "native",
    idempotency_key: str = "trade:tenant_cn:order-42",
    context_refs: dict[str, str] | None = None,
):
    return domain.create_trade_plan(
        tenant_id=tenant_id,
        project_id=project_id,
        order_ref=order_ref,
        channel=channel,
        amount_minor=880,
        currency="CNY",
        description="Ashr team plan",
        notify_url="https://api.ashr-clone.invalid/payments/notify",
        return_url="https://app.ashr-clone.invalid/payments/return",
        idempotency_key=idempotency_key,
        context_refs=context_refs,
        metadata={"sku": "team_monthly"},
    )


def test_capability_matrix_is_china_first_and_marks_unsafe_alipay_jsapi():
    matrix = china_payment_capability_matrix()
    manifest = payment_provider_contract_manifest()

    assert set(matrix) == {"wechat_pay", "alipay", "domestic_bank_card"}
    assert all(matrix["wechat_pay"][channel]["supported"] for channel in matrix["wechat_pay"])
    assert matrix["alipay"]["jsapi"]["supported"] is False
    assert matrix["alipay"]["mini_program"]["supported"] is True
    assert matrix["domestic_bank_card"]["hosted"]["supported"] is True
    assert matrix["domestic_bank_card"]["token_ref"]["supported"] is True
    assert matrix["domestic_bank_card"]["native"]["supported"] is False
    assert manifest["domain_priority"] == "china_first"
    assert manifest["providers"]["stripe"]["role"] == "compatibility_only"
    assert manifest["providers"]["wechat_pay"]["protocol"] == "wechat_pay_api_v3"
    assert manifest["providers"]["domestic_bank_card"]["raw_card_data_allowed"] is False
    assert manifest["china_domain_controls"]["daily_bill_hash_reconciliation"] is True


@pytest.mark.parametrize(
    ("provider", "channel", "expected_operation", "context_refs"),
    [
        ("wechat_pay", "native", "v3.pay.transactions.native", None),
        (
            "wechat_pay",
            "jsapi",
            "v3.pay.transactions.jsapi",
            {"payer_ref": "provider-ref:wechat_pay/test/payer/42"},
        ),
        (
            "wechat_pay",
            "h5",
            "v3.pay.transactions.h5",
            {"client_ip_ref": "provider-ref:network/request/ip-hash-42"},
        ),
        ("wechat_pay", "app", "v3.pay.transactions.app", None),
        (
            "wechat_pay",
            "mini_program",
            "v3.pay.transactions.jsapi",
            {"payer_ref": "provider-ref:wechat_pay/test/openid/42"},
        ),
        ("alipay", "native", "alipay.trade.precreate", None),
        ("alipay", "h5", "alipay.trade.wap.pay", None),
        ("alipay", "app", "alipay.trade.app.pay", None),
        (
            "alipay",
            "mini_program",
            "alipay.trade.create",
            {"buyer_ref": "provider-ref:alipay/test/buyer/42"},
        ),
    ],
)
def test_cny_trade_plans_cover_semantically_safe_channels(
    provider, channel, expected_operation, context_refs
):
    plan = _trade(
        _domain(provider),
        channel=channel,
        order_ref=f"provider-ref:{provider}/test/order/{channel}",
        idempotency_key=f"trade:{provider}:{channel}:order-42",
        context_refs=context_refs,
    )
    serialized = json.dumps(plan, sort_keys=True)

    assert plan["schema_version"] == CHINA_PAYMENT_SCHEMA_VERSION
    assert plan["provider"] == provider
    assert plan["request_shape"]["operation"] == expected_operation
    assert plan["request_shape"]["amount"] == {
        "minor": 880,
        "currency": "CNY",
        "unit": "fen",
    }
    assert plan["normalized_lifecycle"] == "created"
    assert plan["execution_hook"]["adapter_executes"] is False
    assert plan["side_effects"]["network_io_performed"] is False
    assert plan["scope"]["cross_scope_reuse_allowed"] is False
    assert plan["merchant"]["raw_key_material_present"] is False
    assert "BEGIN PRIVATE KEY" not in serialized


def test_channel_requirements_and_cny_boundary_fail_closed():
    with pytest.raises(ChinaPaymentContractError, match="payer_ref"):
        _trade(_domain("wechat_pay"), channel="jsapi")

    with pytest.raises(ChinaPaymentContractError, match="client_ip_ref"):
        _trade(_domain("wechat_pay"), channel="h5")

    with pytest.raises(ChinaPaymentContractError, match="buyer_ref"):
        _trade(_domain("alipay"), channel="mini_program")

    with pytest.raises(ChinaPaymentContractError, match="mini_program"):
        _trade(_domain("alipay"), channel="jsapi")

    with pytest.raises(ChinaPaymentContractError, match="require CNY"):
        _domain("wechat_pay").create_trade_plan(
            tenant_id="tenant_cn",
            project_id="project_cn",
            order_ref="provider-ref:wechat_pay/test/order/usd",
            channel="native",
            amount_minor=100,
            currency="USD",
            description="Wrong currency",
            notify_url="https://api.ashr-clone.invalid/payments/notify",
            idempotency_key="trade:wechat:wrong-currency",
        )

    with pytest.raises(ChinaPaymentContractError, match="integer number of fen"):
        _domain("domestic_bank_card").create_trade_plan(
            tenant_id="tenant_cn",
            project_id="project_cn",
            order_ref="provider-ref:domestic_bank_card/test/order/fractional",
            channel="hosted",
            amount_minor=8.8,
            currency="CNY",
            description="Fractional fen is invalid",
            notify_url="https://api.ashr-clone.invalid/payments/notify",
            idempotency_key="trade:domestic-card:fractional-fen",
            context_refs={
                "account_binding_ref": "provider-ref:domestic_bank_card/test/account-binding/ashr",
                "hosted_flow_ref": "provider-ref:domestic_bank_card/test/hosted-flow/fractional",
            },
        )


@pytest.mark.parametrize(
    ("channel", "context_refs", "expected_action"),
    [
        (
            "hosted",
            {
                "account_binding_ref": "provider-ref:domestic_bank_card/test/account-binding/ashr",
                "hosted_flow_ref": "provider-ref:domestic_bank_card/test/hosted-flow/42",
            },
            "redirect_acquirer_hosted",
        ),
        (
            "token_ref",
            {
                "account_binding_ref": "provider-ref:domestic_bank_card/test/account-binding/ashr",
                "payment_token_ref": "provider-ref:domestic_bank_card/test/token/42",
            },
            "submit_acquirer_token_ref",
        ),
    ],
)
def test_domestic_bank_card_is_hosted_or_token_ref_only(
    channel, context_refs, expected_action
):
    plan = _trade(
        _domain("domestic_bank_card"),
        order_ref=f"provider-ref:domestic_bank_card/test/order/{channel}",
        channel=channel,
        idempotency_key=f"trade:domestic-card:{channel}:42",
        context_refs=context_refs,
    )
    serialized = json.dumps(plan, sort_keys=True)

    assert plan["provider_protocol"] == "domestic_card_acquirer"
    assert plan["request_shape"]["amount"]["unit"] == "fen"
    assert plan["client_handoff"]["action"] == expected_action
    assert plan["client_handoff"]["hosted_or_token_ref_only"] is True
    assert plan["client_handoff"]["collects_pan_cvc_otp"] is False
    assert plan["merchant"]["account_binding_ref"] == context_refs["account_binding_ref"]
    assert plan["raw_pan_present"] is False
    assert plan["raw_cvc_present"] is False
    assert plan["raw_otp_present"] is False
    for forbidden_value in (
        "6222021234567890",
        "alice cardholder",
        "otp 123456",
        "cvc 123",
    ):
        assert forbidden_value not in serialized.lower()


@pytest.mark.parametrize("channel", ["native", "jsapi", "h5", "app", "mini_program"])
def test_domestic_bank_card_rejects_non_hosted_non_token_channels(channel):
    with pytest.raises(ChinaPaymentContractError, match="hosted|token_ref"):
        _trade(
            _domain("domestic_bank_card"),
            channel=channel,
            order_ref=f"provider-ref:domestic_bank_card/test/order/{channel}",
            idempotency_key=f"trade:domestic-card:unsafe:{channel}",
        )


def test_domestic_bank_card_requires_matching_account_binding():
    domain = _domain("domestic_bank_card")
    with pytest.raises(PaymentScopeViolation, match="configured merchant binding"):
        _trade(
            domain,
            channel="token_ref",
            order_ref="provider-ref:domestic_bank_card/test/order/wrong-binding",
            idempotency_key="trade:domestic-card:wrong-binding",
            context_refs={
                "account_binding_ref": "provider-ref:domestic_bank_card/test/account-binding/other",
                "payment_token_ref": "provider-ref:domestic_bank_card/test/token/42",
            },
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pan", "provider-ref:domestic_bank_card/test/value/42"),
        ("cvc", "provider-ref:domestic_bank_card/test/value/42"),
        ("otp", "provider-ref:domestic_bank_card/test/value/42"),
        ("cardholder_name", "Alice"),
        ("note", "card_number=6222021234567890"),
        ("note", "otp 123456"),
        ("note", "cvc 123"),
    ],
)
def test_domestic_bank_card_adversarial_raw_material_is_rejected(field, value):
    with pytest.raises(ChinaPaymentContractError, match="PAN|CVC|OTP|cardholder"):
        _domain("domestic_bank_card").create_trade_plan(
            tenant_id="tenant_cn",
            project_id="project_cn",
            order_ref="provider-ref:domestic_bank_card/test/order/adversarial",
            channel="hosted",
            amount_minor=880,
            currency="CNY",
            description="Hosted card payment",
            notify_url="https://api.ashr-clone.invalid/payments/notify",
            return_url="https://app.ashr-clone.invalid/payments/return",
            idempotency_key=f"trade:domestic-card:adversarial:{field}",
            context_refs={
                "account_binding_ref": "provider-ref:domestic_bank_card/test/account-binding/ashr",
                "hosted_flow_ref": "provider-ref:domestic_bank_card/test/hosted-flow/42",
            },
            metadata={field: value},
        )


FORBIDDEN_PAYMENT_FIELD_ALIASES = (
    "pan",
    "primaryAccountNumber",
    "primary-account-no",
    "card number",
    "cardNo",
    "account-number",
    "expiry",
    "expirationDate",
    "exp month",
    "expiry-year",
    "valid thru",
    "validThrough",
    "cvv",
    "CVC",
    "cvn",
    "cid",
    "security code",
    "cardSecurityCode",
    "pin",
    "pin-block",
    "otp",
    "oneTimePassword",
    "one-time-code",
    "sms code",
    "smsOtp",
    "track1",
    "track-2",
    "track data",
    "paymentCryptogram",
    "cardholder",
    "cardHolderName",
    "raw-cardholder-data",
    "kyc",
    "kycDocs",
    "raw kyc document",
)


@pytest.mark.parametrize("field_alias", FORBIDDEN_PAYMENT_FIELD_ALIASES)
@pytest.mark.parametrize(
    "metadata_factory",
    [
        lambda field: {field: "synthetic-sensitive-placeholder"},
        lambda field: {"level_one": {"level_two": {field: "synthetic-sensitive-placeholder"}}},
        lambda field: {"items": [{"safe": True}, {field: "synthetic-sensitive-placeholder"}]},
    ],
)
def test_forbidden_payment_data_alias_matrix_is_rejected_recursively(
    field_alias, metadata_factory
):
    with pytest.raises(ChinaPaymentContractError, match="forbidden payment data"):
        _domain("wechat_pay").create_trade_plan(
            tenant_id="tenant_cn",
            project_id="project_cn",
            order_ref="provider-ref:wechat_pay/test/order/forbidden-matrix",
            channel="native",
            amount_minor=880,
            currency="CNY",
            description="Hosted payment",
            notify_url="https://api.ashr-clone.invalid/payments/notify",
            return_url="https://app.ashr-clone.invalid/payments/return",
            idempotency_key=f"trade:forbidden:{field_alias.replace(' ', '-')}",
            metadata=metadata_factory(field_alias),
        )


def test_recursive_payment_metadata_allows_hosted_provider_token_and_opaque_refs():
    plan = _domain("domestic_bank_card").create_trade_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        order_ref="provider-ref:domestic_bank_card/test/order/safe-matrix",
        channel="hosted",
        amount_minor=880,
        currency="CNY",
        description="Hosted payment",
        notify_url="https://api.ashr-clone.invalid/payments/notify",
        return_url="https://app.ashr-clone.invalid/payments/return",
        idempotency_key="trade:domestic-card:safe-matrix",
        context_refs={
            "account_binding_ref": "provider-ref:domestic_bank_card/test/account-binding/ashr",
            "hosted_flow_ref": "provider-ref:domestic_bank_card/test/hosted-flow/safe",
        },
        metadata={
            "handoff": {
                "hostedUrl": "https://pay.example.invalid/session/synthetic",
                "provider_token": "provider-ref:acquirer/token/synthetic",
                "opaque-reference": "opaque-ref:payment/synthetic",
            },
            "attempts": [{"status": "planned", "sequence": 1}],
        },
    )

    assert plan["request_shape"]["metadata"]["handoff"]["hostedUrl"].startswith(
        "https://"
    )
    assert plan["request_shape"]["metadata"]["handoff"]["provider_token"].startswith(
        "provider-ref:"
    )
    assert plan["request_shape"]["metadata"]["handoff"]["opaque-reference"].startswith(
        "opaque-ref:"
    )


def test_merchant_configuration_requires_refs_certificates_and_wechat_api_v3_ref():
    public = _config("wechat_pay").to_public_dict()

    assert public["merchant_ref"].startswith("provider-ref:")
    assert len(public["certificate_refs"]) == 2
    assert public["api_v3_key_ref"].startswith("vault:")
    assert public["raw_certificate_present"] is False

    with pytest.raises(ChinaPaymentContractError, match="certificate_ref"):
        ChinaMerchantConfig(
            provider="alipay",
            mode_gate=PaymentModeGate(),
            merchant_ref="provider-ref:alipay/test/merchant",
            app_ref="provider-ref:alipay/test/app",
            signing_key_ref="vault:alipay/test/signing",
            verification_key_ref="vault:alipay/test/verify",
        ).validate()

    with pytest.raises(ChinaPaymentContractError, match="api_v3_key_ref"):
        ChinaMerchantConfig(
            provider="wechat_pay",
            mode_gate=PaymentModeGate(),
            merchant_ref="provider-ref:wechat/test/merchant",
            app_ref="provider-ref:wechat/test/app",
            signing_key_ref="vault:wechat/test/signing",
            verification_key_ref="vault:wechat/test/verify",
            certificate_refs=("provider-ref:wechat/test/cert",),
        ).validate()

    with pytest.raises(ChinaPaymentContractError, match="approved reference prefix"):
        ChinaMerchantConfig(
            provider="alipay",
            mode_gate=PaymentModeGate(),
            merchant_ref="merchant-number-raw",
            app_ref="provider-ref:alipay/test/app",
            signing_key_ref="vault:alipay/test/signing",
            verification_key_ref="vault:alipay/test/verify",
            certificate_refs=("provider-ref:alipay/test/cert",),
        ).validate()

    with pytest.raises(ChinaPaymentContractError, match="account_binding_ref"):
        ChinaMerchantConfig(
            provider="domestic_bank_card",
            mode_gate=PaymentModeGate(),
            merchant_ref="provider-ref:domestic_bank_card/test/merchant",
            app_ref="provider-ref:domestic_bank_card/test/app",
            signing_key_ref="vault:domestic_bank_card/test/signing",
            verification_key_ref="vault:domestic_bank_card/test/verify",
            certificate_refs=("provider-ref:domestic_bank_card/test/cert",),
            acquirer_ref="provider-ref:domestic_bank_card/test/acquirer",
        ).validate()


def test_scoped_idempotency_replays_identical_plan_and_rejects_conflict():
    domain = _domain("wechat_pay")
    first = _trade(domain)
    replay = _trade(domain)

    assert first["idempotency"]["replayed"] is False
    assert replay["idempotency"]["replayed"] is True
    assert (
        replay["idempotency"]["request_fingerprint_sha256"]
        == first["idempotency"]["request_fingerprint_sha256"]
    )

    with pytest.raises(PaymentIdempotencyConflict, match="different request fingerprint"):
        domain.create_trade_plan(
            tenant_id="tenant_cn",
            project_id="project_cn",
            order_ref="provider-ref:orders/cn/order-42",
            channel="native",
            amount_minor=990,
            currency="CNY",
            description="Changed amount",
            notify_url="https://api.ashr-clone.invalid/payments/notify",
            return_url="https://app.ashr-clone.invalid/payments/return",
            idempotency_key="trade:tenant_cn:order-42",
            metadata={"sku": "team_monthly"},
        )


def test_idempotency_scope_allows_same_key_for_different_tenants_and_projects():
    registry = ScopedIdempotencyRegistry()
    tenant_a = _domain("alipay", registry)
    tenant_b = _domain("alipay", registry)

    plan_a = _trade(
        tenant_a,
        tenant_id="tenant_a",
        project_id="project_a",
        order_ref="provider-ref:alipay/order/a",
        idempotency_key="shared:idempotency:key",
    )
    plan_b = _trade(
        tenant_b,
        tenant_id="tenant_b",
        project_id="project_b",
        order_ref="provider-ref:alipay/order/b",
        idempotency_key="shared:idempotency:key",
    )

    assert plan_a["idempotency"]["replayed"] is False
    assert plan_b["idempotency"]["replayed"] is False
    assert plan_a["idempotency"]["request_fingerprint_sha256"] != plan_b["idempotency"]["request_fingerprint_sha256"]


def test_registered_order_and_refund_refs_are_tenant_project_isolated():
    domain = _domain("wechat_pay")
    _trade(domain)

    query = domain.query_trade_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        order_ref="provider-ref:orders/cn/order-42",
        idempotency_key="query:tenant_cn:order-42",
    )
    assert query["operation"] == "trade.query"

    with pytest.raises(PaymentScopeViolation, match="another tenant or project"):
        domain.close_trade_plan(
            tenant_id="tenant_other",
            project_id="project_cn",
            order_ref="provider-ref:orders/cn/order-42",
            idempotency_key="close:tenant_other:order-42",
        )

    with pytest.raises(PaymentScopeViolation, match="not registered"):
        domain.query_trade_plan(
            tenant_id="tenant_cn",
            project_id="project_cn",
            order_ref="provider-ref:orders/cn/unknown",
            idempotency_key="query:tenant_cn:unknown-order",
        )


@pytest.mark.parametrize(
    ("provider", "create_operation", "query_operation"),
    [
        (
            "wechat_pay",
            "v3.refund.domestic.refunds.create",
            "v3.refund.domestic.refunds.query",
        ),
        (
            "alipay",
            "alipay.trade.refund",
            "alipay.trade.fastpay.refund.query",
        ),
        (
            "domestic_bank_card",
            "acquirer.card.refund.create",
            "acquirer.card.refund.query",
        ),
    ],
)
def test_refund_creation_and_status_query(provider, create_operation, query_operation):
    domain = _domain(provider)
    order_ref = f"provider-ref:{provider}/test/order/refund-42"
    _trade(
        domain,
        order_ref=order_ref,
        idempotency_key=f"trade:{provider}:refund-order-42",
        channel="token_ref" if provider == "domestic_bank_card" else "native",
        context_refs=(
            {
                "account_binding_ref": "provider-ref:domestic_bank_card/test/account-binding/ashr",
                "payment_token_ref": "provider-ref:domestic_bank_card/test/token/refund-42",
            }
            if provider == "domestic_bank_card"
            else None
        ),
    )
    refund_ref = f"provider-ref:{provider}/test/refund/42"
    created = domain.create_refund_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        order_ref=order_ref,
        refund_ref=refund_ref,
        refund_amount_minor=300,
        original_amount_minor=880,
        currency="CNY",
        reason="Partial service credit",
        notify_url="https://api.ashr-clone.invalid/payments/refunds/notify",
        idempotency_key=f"refund:{provider}:42:create",
    )
    queried = domain.query_refund_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        refund_ref=refund_ref,
        idempotency_key=f"refund:{provider}:42:query",
    )

    assert created["request_shape"]["operation"] == create_operation
    assert created["normalized_lifecycle"] == "refunding"
    assert queried["request_shape"]["operation"] == query_operation

    with pytest.raises(ChinaPaymentContractError, match="must not exceed"):
        domain.create_refund_plan(
            tenant_id="tenant_cn",
            project_id="project_cn",
            order_ref=order_ref,
            refund_ref=f"provider-ref:{provider}/test/refund/too-large",
            refund_amount_minor=881,
            original_amount_minor=880,
            currency="CNY",
            reason="Invalid over-refund",
            idempotency_key=f"refund:{provider}:too-large",
        )


@pytest.mark.parametrize(
    ("provider", "query_operation", "close_operation"),
    [
        (
            "wechat_pay",
            "v3.pay.transactions.out_trade_no.query",
            "v3.pay.transactions.out_trade_no.close",
        ),
        ("alipay", "alipay.trade.query", "alipay.trade.close"),
        (
            "domestic_bank_card",
            "acquirer.card.trade.query",
            "acquirer.card.trade.close",
        ),
    ],
)
def test_trade_query_and_close_plans(provider, query_operation, close_operation):
    domain = _domain(provider)
    order_ref = f"provider-ref:{provider}/test/order/close-42"
    _trade(
        domain,
        order_ref=order_ref,
        idempotency_key=f"trade:{provider}:close-order",
        channel="hosted" if provider == "domestic_bank_card" else "native",
        context_refs=(
            {
                "account_binding_ref": "provider-ref:domestic_bank_card/test/account-binding/ashr",
                "hosted_flow_ref": "provider-ref:domestic_bank_card/test/hosted-flow/close-42",
            }
            if provider == "domestic_bank_card"
            else None
        ),
    )

    queried = domain.query_trade_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        order_ref=order_ref,
        idempotency_key=f"query:{provider}:close-order",
    )
    closed = domain.close_trade_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        order_ref=order_ref,
        idempotency_key=f"close:{provider}:close-order",
    )

    assert queried["request_shape"]["operation"] == query_operation
    assert closed["request_shape"]["operation"] == close_operation
    assert queried["normalized_lifecycle"] == "unknown"


@pytest.mark.parametrize(
    ("provider", "signature_material"),
    [
        (
            "wechat_pay",
            {
                "Wechatpay-Signature": "fixture-signature",
                "Wechatpay-Timestamp": "1700000000",
                "Wechatpay-Nonce": "fixture-nonce",
                "Wechatpay-Serial": "fixture-serial",
            },
        ),
        ("alipay", {"sign": "fixture-signature", "sign_type": "RSA2"}),
        (
            "domestic_bank_card",
            {
                "Acquirer-Signature": "fixture-signature",
                "Acquirer-Timestamp": "1700000000",
                "Acquirer-Certificate-Ref": "fixture-certificate",
            },
        ),
    ],
)
def test_notification_verification_uses_transient_request_and_hash_only_envelope(
    provider, signature_material
):
    raw_body = b'{"out_trade_no":"private-provider-order","trade_state":"SUCCESS"}'
    verifier = RecordingNotificationVerifier(
        NotificationVerificationResult(
            verified=True,
            provider_event_ref=f"dashboard-ref:{provider}/test/event/42",
            provider_status=(
                "SUCCESS"
                if provider == "wechat_pay"
                else "TRADE_SUCCESS"
                if provider == "alipay"
                else "CAPTURED"
            ),
            certificate_ref=f"provider-ref:{provider}/test/certificate/current",
        )
    )
    envelope = _domain(provider).verify_notification(
        tenant_id="tenant_cn",
        project_id="project_cn",
        raw_body=raw_body,
        signature_material=signature_material,
        verifier=verifier,
    )
    serialized = json.dumps(envelope, sort_keys=True)

    assert len(verifier.requests) == 1
    assert verifier.requests[0].raw_body == raw_body
    assert verifier.requests[0].tenant_id == "tenant_cn"
    assert envelope["verified"] is True
    assert envelope["normalized_lifecycle"] == "succeeded"
    assert envelope["payload_sha256"] == hashlib.sha256(raw_body).hexdigest()
    assert envelope["raw_body_included"] is False
    assert "private-provider-order" not in serialized
    assert "fixture-signature" not in serialized


def test_notification_missing_signature_and_untrusted_certificate_fail_closed():
    missing_verifier = RecordingNotificationVerifier(
        NotificationVerificationResult(verified=True)
    )
    missing = _domain("wechat_pay").verify_notification(
        tenant_id="tenant_cn",
        project_id="project_cn",
        raw_body=b"fixture",
        signature_material={"wechatpay-signature": "only-one-field"},
        verifier=missing_verifier,
    )
    assert missing["verified"] is False
    assert missing["reason_codes"] == ["missing_signature_material"]
    assert missing_verifier.requests == []

    untrusted_verifier = RecordingNotificationVerifier(
        NotificationVerificationResult(
            verified=True,
            provider_event_ref="dashboard-ref:alipay/test/event/42",
            provider_status="TRADE_SUCCESS",
            certificate_ref="provider-ref:alipay/test/certificate/attacker",
        )
    )
    untrusted = _domain("alipay").verify_notification(
        tenant_id="tenant_cn",
        project_id="project_cn",
        raw_body=b"fixture",
        signature_material={"sign": "fixture", "sign_type": "RSA2"},
        verifier=untrusted_verifier,
    )
    assert untrusted["verified"] is False
    assert untrusted["reason_codes"] == ["untrusted_certificate_ref"]


@pytest.mark.parametrize(
    ("provider", "statuses", "expected"),
    [
        (
            "wechat_pay",
            ["NOTPAY", "SUCCESS", "PAYERROR", "CLOSED", "PROCESSING", "REFUND"],
            ["pending", "succeeded", "failed", "closed", "refunding", "refunded"],
        ),
        (
            "alipay",
            [
                "WAIT_BUYER_PAY",
                "TRADE_SUCCESS",
                "TRADE_CLOSED",
                "REFUND_PROCESSING",
                "REFUND_SUCCESS",
            ],
            ["pending", "succeeded", "closed", "refunding", "refunded"],
        ),
        (
            "domestic_bank_card",
            ["CREATED", "PENDING", "CAPTURED", "DECLINED", "VOIDED", "PARTIALLY_REFUNDED", "REFUNDED"],
            ["created", "pending", "succeeded", "failed", "closed", "partially_refunded", "refunded"],
        ),
    ],
)
def test_provider_statuses_normalize_to_shared_lifecycle(provider, statuses, expected):
    assert [normalize_payment_lifecycle(provider, status) for status in statuses] == expected
    assert normalize_payment_lifecycle(provider, "future-provider-state") == "unknown"


@pytest.mark.parametrize("provider", ["wechat_pay", "alipay", "domestic_bank_card"])
def test_daily_bill_request_and_parse_return_hashes_without_raw_identifiers(provider):
    domain = _domain(provider)
    request = domain.request_daily_bill_plan(
        tenant_id="tenant_cn",
        project_id="project_cn",
        bill_date="2026-07-09",
        bill_type="trade",
        idempotency_key=f"bill:{provider}:2026-07-09",
    )
    raw_bill = (
        "provider_order_id,trade_status,amount_minor,customer_name\n"
        "provider-secret-order-1,"
        + (
            "SUCCESS"
            if provider == "wechat_pay"
            else "TRADE_SUCCESS"
            if provider == "alipay"
            else "CAPTURED"
        )
        + ",880,Alice\n"
        "provider-secret-order-2,"
        + (
            "CLOSED"
            if provider == "wechat_pay"
            else "TRADE_CLOSED"
            if provider == "alipay"
            else "VOIDED"
        )
        + ",120,Bob\n"
    ).encode()
    reconciliation = domain.parse_daily_bill(
        tenant_id="tenant_cn",
        project_id="project_cn",
        bill_date="2026-07-09",
        raw_bill=raw_bill,
        expected_sha256=hashlib.sha256(raw_bill).hexdigest(),
    )
    serialized = json.dumps(reconciliation, sort_keys=True)

    assert request["operation"] == "bill.request"
    assert request["request_shape"]["bill_date"] == "2026-07-09"
    assert reconciliation["row_count"] == 2
    assert len(reconciliation["row_sha256"]) == 2
    assert reconciliation["amount_summary"]["minor_total"] == 1000
    assert reconciliation["amount_summary"]["unit"] == "fen"
    assert reconciliation["normalized_lifecycle_counts"] == {
        "closed": 1,
        "succeeded": 1,
    }
    assert reconciliation["raw_row_values_included"] is False
    assert "provider-secret-order" not in serialized
    assert "Alice" not in serialized
    assert "Bob" not in serialized


def test_daily_bill_integrity_and_input_shape_are_strict():
    domain = _domain("wechat_pay")
    raw_bill = b"trade_status,amount_minor\nSUCCESS,880\n"

    with pytest.raises(ChinaPaymentContractError, match="SHA-256 mismatch"):
        domain.parse_daily_bill(
            tenant_id="tenant_cn",
            project_id="project_cn",
            bill_date="2026-07-09",
            raw_bill=raw_bill,
            expected_sha256="0" * 64,
        )

    with pytest.raises(ChinaPaymentContractError, match="integer minor units"):
        domain.parse_daily_bill(
            tenant_id="tenant_cn",
            project_id="project_cn",
            bill_date="2026-07-09",
            raw_bill=b"trade_status,amount_minor\nSUCCESS,8.80\n",
        )

    with pytest.raises(ChinaPaymentContractError, match="YYYY-MM-DD"):
        domain.request_daily_bill_plan(
            tenant_id="tenant_cn",
            project_id="project_cn",
            bill_date="20260709",
            bill_type="trade",
            idempotency_key="bill:wechat:invalid-date",
        )
