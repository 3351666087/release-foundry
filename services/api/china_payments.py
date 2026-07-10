"""Provider-neutral, China-first payment domain contracts.

This module performs no provider or network calls. It produces scope-bound,
public-safe plans for an external WeChat Pay API v3, Alipay, or domestic bank
card acquirer executor and hash-only evidence for notifications and daily bill
reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
import hashlib
import io
import json
import re
from typing import Any, Mapping, Protocol, Sequence

from .payment_providers import (
    JsonDict,
    PaymentModeGate,
    PaymentProviderContractError,
    _no_side_effects,
    _safe_text,
    _validate_common_plan_fields,
    _validate_ref as _base_validate_ref,
)

CHINA_PAYMENT_SCHEMA_VERSION = "ashr.clone.china_payment_domain.v1"
CHINA_PAYMENT_PROVIDERS = ("wechat_pay", "alipay", "domestic_bank_card")
CHINA_PAYMENT_CHANNELS = (
    "native",
    "jsapi",
    "h5",
    "app",
    "mini_program",
    "hosted",
    "token_ref",
)
NORMALIZED_PAYMENT_LIFECYCLE = (
    "created",
    "pending",
    "succeeded",
    "failed",
    "closed",
    "refunding",
    "refunded",
    "partially_refunded",
    "unknown",
)

_PROVIDER_ALIASES = {
    "wechat": "wechat_pay",
    "wechatpay": "wechat_pay",
    "weixin": "wechat_pay",
    "ali_pay": "alipay",
    "bank_card": "domestic_bank_card",
    "domestic_card": "domestic_bank_card",
    "unionpay_card": "domestic_bank_card",
}
_CHANNEL_ALIASES = {
    "mini-program": "mini_program",
    "miniprogram": "mini_program",
    "miniapp": "mini_program",
    "web": "h5",
    "wap": "h5",
    "hosted_page": "hosted",
    "token": "token_ref",
    "tokenized": "token_ref",
}
_CAMEL_CASE_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_PAYMENT_FIELD_SEPARATOR_RE = re.compile(r"[^a-z0-9]+")
_POSSIBLE_PAN_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_FORBIDDEN_PAYMENT_VALUE_RE = re.compile(
    r"(?:\b(?:pan|primary[ _-]*account[ _-]*(?:number|no)|card[ _-]*(?:number|no)|"
    r"account[ _-]*(?:number|no)|exp(?:iry|iration)?(?:[ _-]*(?:month|year|date))?|"
    r"valid[ _-]*(?:thru|through)|cvv|cvc|cvn|cid|security[ _-]*code|pin|"
    r"one[ _-]*time[ _-]*(?:password|code)|otp|sms[ _-]*code|track[ _-]*(?:1|2|data)|"
    r"cryptogram|cardholder|kyc[ _-]*(?:doc|docs|document|documents|data))\b"
    r"(?:\s*(?:=|:)\s*|\s+)\S+)",
    re.IGNORECASE,
)
_FORBIDDEN_PAYMENT_FIELD_NAMES = frozenset(
    {
        "pan",
        "primary_account_number",
        "primary_account_no",
        "card_number",
        "card_no",
        "account_number",
        "account_no",
        "expiry",
        "expiration",
        "expiry_date",
        "expiration_date",
        "exp",
        "exp_date",
        "exp_month",
        "expiry_month",
        "expiration_month",
        "exp_year",
        "expiry_year",
        "expiration_year",
        "valid_thru",
        "valid_through",
        "cvv",
        "cvc",
        "cvn",
        "cid",
        "security_code",
        "card_security_code",
        "pin",
        "pin_block",
        "otp",
        "one_time_password",
        "one_time_code",
        "sms_code",
        "sms_otp",
        "track1",
        "track_1",
        "track2",
        "track_2",
        "track_data",
        "cryptogram",
        "payment_cryptogram",
        "cardholder",
        "card_holder",
        "cardholder_name",
        "card_holder_name",
        "cardholder_data",
        "card_holder_data",
        "raw_cardholder",
        "raw_cardholder_data",
        "kyc",
        "kyc_data",
        "kyc_doc",
        "kyc_docs",
        "kyc_document",
        "kyc_documents",
        "raw_kyc",
        "raw_kyc_data",
        "raw_kyc_doc",
        "raw_kyc_docs",
        "raw_kyc_document",
        "raw_kyc_documents",
    }
)
_CAPABILITY_MATRIX: dict[str, dict[str, dict[str, Any]]] = {
    "wechat_pay": {
        "native": {
            "supported": True,
            "create_operation": "v3.pay.transactions.native",
            "required_context_refs": (),
            "client_action": "display_qr_code",
        },
        "jsapi": {
            "supported": True,
            "create_operation": "v3.pay.transactions.jsapi",
            "required_context_refs": ("payer_ref",),
            "client_action": "invoke_jsapi",
        },
        "h5": {
            "supported": True,
            "create_operation": "v3.pay.transactions.h5",
            "required_context_refs": ("client_ip_ref",),
            "client_action": "redirect_h5",
        },
        "app": {
            "supported": True,
            "create_operation": "v3.pay.transactions.app",
            "required_context_refs": (),
            "client_action": "invoke_app_sdk",
        },
        "mini_program": {
            "supported": True,
            "create_operation": "v3.pay.transactions.jsapi",
            "required_context_refs": ("payer_ref",),
            "client_action": "invoke_mini_program_payment",
        },
    },
    "alipay": {
        "native": {
            "supported": True,
            "create_operation": "alipay.trade.precreate",
            "required_context_refs": (),
            "client_action": "display_qr_code",
        },
        "jsapi": {
            "supported": False,
            "reason": "use mini_program for Alipay in-app JavaScript payment",
        },
        "h5": {
            "supported": True,
            "create_operation": "alipay.trade.wap.pay",
            "required_context_refs": (),
            "client_action": "redirect_h5",
        },
        "app": {
            "supported": True,
            "create_operation": "alipay.trade.app.pay",
            "required_context_refs": (),
            "client_action": "invoke_app_sdk",
        },
        "mini_program": {
            "supported": True,
            "create_operation": "alipay.trade.create",
            "required_context_refs": ("buyer_ref",),
            "client_action": "invoke_mini_program_payment",
        },
    },
    "domestic_bank_card": {
        "native": {"supported": False, "reason": "domestic bank cards require hosted or token_ref"},
        "jsapi": {"supported": False, "reason": "domestic bank cards require hosted or token_ref"},
        "h5": {"supported": False, "reason": "use hosted for acquirer-controlled H5"},
        "app": {"supported": False, "reason": "use hosted or token_ref for app payment"},
        "mini_program": {
            "supported": False,
            "reason": "use hosted or token_ref for mini-program payment",
        },
        "hosted": {
            "supported": True,
            "create_operation": "acquirer.card.trade.hosted.create",
            "required_context_refs": ("account_binding_ref", "hosted_flow_ref"),
            "client_action": "redirect_acquirer_hosted",
        },
        "token_ref": {
            "supported": True,
            "create_operation": "acquirer.card.trade.token.create",
            "required_context_refs": ("account_binding_ref", "payment_token_ref"),
            "client_action": "submit_acquirer_token_ref",
        },
    },
}
_LIFECYCLE_MAP = {
    "wechat_pay": {
        "NOTPAY": "pending",
        "USERPAYING": "pending",
        "SUCCESS": "succeeded",
        "PAYERROR": "failed",
        "CLOSED": "closed",
        "REVOKED": "closed",
        "REFUND": "refunded",
        "PROCESSING": "refunding",
        "ABNORMAL": "failed",
    },
    "alipay": {
        "WAIT_BUYER_PAY": "pending",
        "TRADE_SUCCESS": "succeeded",
        "TRADE_FINISHED": "succeeded",
        "TRADE_CLOSED": "closed",
        "REFUND_PROCESSING": "refunding",
        "REFUND_SUCCESS": "refunded",
        "REFUND_FAILED": "failed",
    },
    "domestic_bank_card": {
        "CREATED": "created",
        "PENDING": "pending",
        "PROCESSING": "pending",
        "AUTHORIZED": "pending",
        "CAPTURED": "succeeded",
        "SUCCEEDED": "succeeded",
        "DECLINED": "failed",
        "FAILED": "failed",
        "VOIDED": "closed",
        "CLOSED": "closed",
        "REFUNDING": "refunding",
        "PARTIALLY_REFUNDED": "partially_refunded",
        "REFUNDED": "refunded",
    },
}


class ChinaPaymentContractError(PaymentProviderContractError):
    """Raised when a China payment plan violates the domain contract."""


class PaymentIdempotencyConflict(ChinaPaymentContractError):
    """Raised when one scoped idempotency key is reused for another request."""


class PaymentScopeViolation(ChinaPaymentContractError):
    """Raised when a tenant or project attempts to use another scope's ref."""


def _validate_ref(name: str, value: str | None) -> None:
    try:
        _base_validate_ref(name, value)
    except PaymentProviderContractError as exc:
        raise ChinaPaymentContractError(str(exc)) from exc
    _reject_bank_card_material(name, str(value or ""))


@dataclass(frozen=True)
class ChinaMerchantConfig:
    """References required by an external provider executor.

    References may identify secrets or certificates, but values never contain
    raw key material, certificate bytes, merchant numbers, or app secrets.
    """

    provider: str
    mode_gate: PaymentModeGate
    merchant_ref: str
    app_ref: str
    signing_key_ref: str
    verification_key_ref: str
    certificate_refs: tuple[str, ...] = ()
    api_v3_key_ref: str | None = None
    acquirer_ref: str | None = None
    account_binding_ref: str | None = None

    def validate(self) -> "ChinaMerchantConfig":
        provider = normalize_china_provider(self.provider)
        gate = self.mode_gate.validate()
        _validate_ref("merchant_ref", self.merchant_ref)
        _validate_ref("app_ref", self.app_ref)
        _validate_ref("signing_key_ref", self.signing_key_ref)
        _validate_ref("verification_key_ref", self.verification_key_ref)
        certificates = tuple(self.certificate_refs)
        if not certificates:
            raise ChinaPaymentContractError("at least one certificate_ref is required")
        for certificate_ref in certificates:
            _validate_ref("certificate_ref", certificate_ref)
        if provider == "wechat_pay":
            _validate_ref("api_v3_key_ref", self.api_v3_key_ref)
        elif self.api_v3_key_ref is not None:
            raise ChinaPaymentContractError("api_v3_key_ref is WeChat Pay only")
        if provider == "domestic_bank_card":
            _validate_ref("acquirer_ref", self.acquirer_ref)
            _validate_ref("account_binding_ref", self.account_binding_ref)
        elif self.acquirer_ref is not None or self.account_binding_ref is not None:
            raise ChinaPaymentContractError(
                "acquirer_ref and account_binding_ref are domestic bank card only"
            )
        return ChinaMerchantConfig(
            provider=provider,
            mode_gate=gate,
            merchant_ref=self.merchant_ref,
            app_ref=self.app_ref,
            signing_key_ref=self.signing_key_ref,
            verification_key_ref=self.verification_key_ref,
            certificate_refs=certificates,
            api_v3_key_ref=self.api_v3_key_ref,
            acquirer_ref=self.acquirer_ref,
            account_binding_ref=self.account_binding_ref,
        )

    def to_public_dict(self) -> JsonDict:
        config = self.validate()
        return {
            "provider": config.provider,
            "mode_gate": config.mode_gate.to_public_dict(),
            "merchant_ref": config.merchant_ref,
            "app_ref": config.app_ref,
            "signing_key_ref": config.signing_key_ref,
            "verification_key_ref": config.verification_key_ref,
            "certificate_refs": list(config.certificate_refs),
            "api_v3_key_ref": config.api_v3_key_ref,
            "acquirer_ref": config.acquirer_ref,
            "account_binding_ref": config.account_binding_ref,
            "raw_key_material_present": False,
            "raw_certificate_present": False,
            "raw_pan_present": False,
            "raw_cvc_present": False,
            "raw_otp_present": False,
        }


@dataclass(frozen=True)
class NotificationVerificationRequest:
    provider: str
    mode: str
    tenant_id: str
    project_id: str
    raw_body: bytes = field(repr=False)
    signature_material: Mapping[str, str] = field(repr=False)
    verification_key_ref: str
    certificate_refs: tuple[str, ...]


@dataclass(frozen=True)
class NotificationVerificationResult:
    verified: bool
    provider_event_ref: str | None = None
    provider_status: str | None = None
    certificate_ref: str | None = None
    reason_codes: tuple[str, ...] = ()


class ChinaNotificationVerifier(Protocol):
    def verify(
        self, request: NotificationVerificationRequest
    ) -> NotificationVerificationResult:
        ...


class ChinaPaymentExecutor(Protocol):
    def execute(self, plan: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class ScopedIdempotencyRegistry:
    """In-memory planning registry scoped by provider, tenant, project, and operation."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, str, str, str], tuple[str, JsonDict]] = {}

    def register(
        self,
        *,
        provider: str,
        tenant_id: str,
        project_id: str,
        operation: str,
        idempotency_key: str,
        fingerprint: str,
        plan: JsonDict,
    ) -> JsonDict:
        key = (provider, tenant_id, project_id, operation, idempotency_key)
        existing = self._entries.get(key)
        if existing is not None:
            existing_fingerprint, existing_plan = existing
            if existing_fingerprint != fingerprint:
                raise PaymentIdempotencyConflict(
                    "scoped idempotency key was reused with a different request fingerprint"
                )
            replay = _deep_copy(existing_plan)
            replay["idempotency"]["replayed"] = True
            return replay
        stored = _deep_copy(plan)
        stored["idempotency"]["replayed"] = False
        self._entries[key] = (fingerprint, stored)
        return _deep_copy(stored)


class ChinaPaymentDomain:
    """Builds provider-neutral CNY plans and enforces scope and replay safety."""

    def __init__(
        self,
        config: ChinaMerchantConfig,
        *,
        idempotency_registry: ScopedIdempotencyRegistry | None = None,
    ) -> None:
        self.config = config.validate()
        self.provider = self.config.provider
        self.idempotency_registry = idempotency_registry or ScopedIdempotencyRegistry()
        self._scoped_refs: dict[str, tuple[str, str, str]] = {}

    def create_trade_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        order_ref: str,
        channel: str,
        amount_minor: int,
        currency: str,
        description: str,
        notify_url: str,
        idempotency_key: str,
        return_url: str | None = None,
        context_refs: Mapping[str, str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        normalized_channel = normalize_payment_channel(channel)
        capability = _channel_capability(self.provider, normalized_channel)
        urls = [notify_url]
        if return_url is not None:
            urls.append(return_url)
        _validate_public_mapping("metadata", metadata or {})
        _validate_common_plan_fields(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            urls=urls,
            metadata=None,
        )
        _validate_ref("order_ref", order_ref)
        _validate_cny_amount(amount_minor, currency)
        context = _validate_context_refs(
            context_refs, capability.get("required_context_refs", ())
        )
        if self.provider == "domestic_bank_card":
            if context["account_binding_ref"] != self.config.account_binding_ref:
                raise PaymentScopeViolation(
                    "account_binding_ref does not match the configured merchant binding"
                )
        request_shape: JsonDict = {
            "operation": capability["create_operation"],
            "channel": normalized_channel,
            "order_ref": order_ref,
            "amount": {
                "minor": int(amount_minor),
                "currency": "CNY",
                "unit": "fen",
            },
            "description": _safe_public_text("description", description),
            "notify_url": notify_url,
            "return_url": return_url,
            "context_refs": context,
            "metadata": dict(metadata or {}),
        }
        plan = self._build_plan(
            tenant_id=tenant_id,
            project_id=project_id,
            operation="trade.create",
            idempotency_key=idempotency_key,
            request_shape=request_shape,
            lifecycle="created",
            provider_resource_ref=None,
        )
        plan["client_handoff"] = {
            "action": capability["client_action"],
            "prepay_result_ref_only": True,
            "hosted_or_token_ref_only": self.provider == "domestic_bank_card",
            "collects_pan_cvc_otp": False,
        }
        self._remember_ref(order_ref, tenant_id, project_id, "order")
        return plan

    def query_trade_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        order_ref: str,
        idempotency_key: str,
    ) -> JsonDict:
        self._assert_ref_scope(order_ref, tenant_id, project_id)
        return self._simple_trade_plan(
            tenant_id=tenant_id,
            project_id=project_id,
            operation="trade.query",
            provider_operation=(
                "v3.pay.transactions.out_trade_no.query"
                if self.provider == "wechat_pay"
                else "alipay.trade.query"
                if self.provider == "alipay"
                else "acquirer.card.trade.query"
            ),
            order_ref=order_ref,
            idempotency_key=idempotency_key,
        )

    def close_trade_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        order_ref: str,
        idempotency_key: str,
    ) -> JsonDict:
        self._assert_ref_scope(order_ref, tenant_id, project_id)
        return self._simple_trade_plan(
            tenant_id=tenant_id,
            project_id=project_id,
            operation="trade.close",
            provider_operation=(
                "v3.pay.transactions.out_trade_no.close"
                if self.provider == "wechat_pay"
                else "alipay.trade.close"
                if self.provider == "alipay"
                else "acquirer.card.trade.close"
            ),
            order_ref=order_ref,
            idempotency_key=idempotency_key,
        )

    def create_refund_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        order_ref: str,
        refund_ref: str,
        refund_amount_minor: int,
        original_amount_minor: int,
        currency: str,
        reason: str,
        idempotency_key: str,
        notify_url: str | None = None,
    ) -> JsonDict:
        urls: list[str] = []
        if notify_url is not None:
            urls.append(notify_url)
        _validate_common_plan_fields(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            urls=urls,
            metadata=None,
        )
        self._assert_ref_scope(order_ref, tenant_id, project_id)
        _validate_ref("refund_ref", refund_ref)
        _validate_cny_amount(original_amount_minor, currency)
        _validate_cny_amount(refund_amount_minor, currency)
        if int(refund_amount_minor) > int(original_amount_minor):
            raise ChinaPaymentContractError(
                "refund_amount_minor must not exceed original_amount_minor"
            )
        plan = self._build_plan(
            tenant_id=tenant_id,
            project_id=project_id,
            operation="refund.create",
            idempotency_key=idempotency_key,
            request_shape={
                "operation": (
                    "v3.refund.domestic.refunds.create"
                    if self.provider == "wechat_pay"
                    else "alipay.trade.refund"
                    if self.provider == "alipay"
                    else "acquirer.card.refund.create"
                ),
                "order_ref": order_ref,
                "refund_ref": refund_ref,
                "refund_amount": {
                    "minor": int(refund_amount_minor),
                    "currency": "CNY",
                    "unit": "fen",
                },
                "original_amount": {
                    "minor": int(original_amount_minor),
                    "currency": "CNY",
                    "unit": "fen",
                },
                "reason": _safe_public_text("reason", reason),
                "notify_url": notify_url,
            },
            lifecycle="refunding",
            provider_resource_ref=refund_ref,
        )
        self._remember_ref(refund_ref, tenant_id, project_id, "refund")
        return plan

    def query_refund_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        refund_ref: str,
        idempotency_key: str,
    ) -> JsonDict:
        self._assert_ref_scope(refund_ref, tenant_id, project_id)
        _validate_common_plan_fields(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            urls=(),
            metadata=None,
        )
        return self._build_plan(
            tenant_id=tenant_id,
            project_id=project_id,
            operation="refund.query",
            idempotency_key=idempotency_key,
            request_shape={
                "operation": (
                    "v3.refund.domestic.refunds.query"
                    if self.provider == "wechat_pay"
                    else "alipay.trade.fastpay.refund.query"
                    if self.provider == "alipay"
                    else "acquirer.card.refund.query"
                ),
                "refund_ref": refund_ref,
            },
            lifecycle="unknown",
            provider_resource_ref=refund_ref,
        )

    def request_daily_bill_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        bill_date: str,
        bill_type: str,
        idempotency_key: str,
    ) -> JsonDict:
        _validate_common_plan_fields(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            urls=(),
            metadata=None,
        )
        normalized_date = _validate_bill_date(bill_date)
        normalized_type = str(bill_type).strip().lower()
        allowed = (
            {"trade", "fundflow"}
            if self.provider == "wechat_pay"
            else {"trade", "signcustomer"}
            if self.provider == "alipay"
            else {"trade", "settlement"}
        )
        if normalized_type not in allowed:
            raise ChinaPaymentContractError(
                f"unsupported {self.provider} daily bill type"
            )
        return self._build_plan(
            tenant_id=tenant_id,
            project_id=project_id,
            operation="bill.request",
            idempotency_key=idempotency_key,
            request_shape={
                "operation": (
                    "v3.bill.tradebill.get"
                    if self.provider == "wechat_pay" and normalized_type == "trade"
                    else "v3.bill.fundflowbill.get"
                    if self.provider == "wechat_pay"
                    else "alipay.data.dataservice.bill.downloadurl.query"
                    if self.provider == "alipay"
                    else "acquirer.card.reconciliation.download"
                ),
                "bill_date": normalized_date,
                "bill_type": normalized_type,
            },
            lifecycle="unknown",
            provider_resource_ref=None,
        )

    def parse_daily_bill(
        self,
        *,
        tenant_id: str,
        project_id: str,
        bill_date: str,
        raw_bill: bytes,
        expected_sha256: str | None = None,
    ) -> JsonDict:
        _validate_scope(tenant_id, project_id)
        normalized_date = _validate_bill_date(bill_date)
        return parse_daily_bill_reconciliation(
            provider=self.provider,
            tenant_id=tenant_id,
            project_id=project_id,
            bill_date=normalized_date,
            raw_bill=raw_bill,
            expected_sha256=expected_sha256,
        )

    def verify_notification(
        self,
        *,
        tenant_id: str,
        project_id: str,
        raw_body: bytes,
        signature_material: Mapping[str, str],
        verifier: ChinaNotificationVerifier,
    ) -> JsonDict:
        return verify_china_notification(
            config=self.config,
            tenant_id=tenant_id,
            project_id=project_id,
            raw_body=raw_body,
            signature_material=signature_material,
            verifier=verifier,
        )

    def _simple_trade_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        operation: str,
        provider_operation: str,
        order_ref: str,
        idempotency_key: str,
    ) -> JsonDict:
        _validate_common_plan_fields(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            urls=(),
            metadata=None,
        )
        return self._build_plan(
            tenant_id=tenant_id,
            project_id=project_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_shape={
                "operation": provider_operation,
                "order_ref": order_ref,
            },
            lifecycle="unknown",
            provider_resource_ref=order_ref,
        )

    def _build_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        operation: str,
        idempotency_key: str,
        request_shape: Mapping[str, Any],
        lifecycle: str,
        provider_resource_ref: str | None,
    ) -> JsonDict:
        _validate_scope(tenant_id, project_id)
        fingerprint = _fingerprint(
            {
                "provider": self.provider,
                "mode": self.config.mode_gate.mode,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "operation": operation,
                "idempotency_key": idempotency_key,
                "request_shape": request_shape,
            }
        )
        plan: JsonDict = {
            "schema_version": CHINA_PAYMENT_SCHEMA_VERSION,
            "plan_type": "china_payment_operation",
            "provider": self.provider,
            "provider_protocol": (
                "wechat_pay_api_v3"
                if self.provider == "wechat_pay"
                else "alipay_openapi"
                if self.provider == "alipay"
                else "domestic_card_acquirer"
            ),
            "tenant_id": tenant_id,
            "project_id": project_id,
            "scope": {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "cross_scope_reuse_allowed": False,
            },
            "operation": operation,
            "mode_gate": self.config.mode_gate.to_public_dict(),
            "merchant": self.config.to_public_dict(),
            "request_shape": dict(request_shape),
            "normalized_lifecycle": lifecycle,
            "provider_resource_ref": provider_resource_ref,
            "idempotency": {
                "required": True,
                "key": idempotency_key,
                "scope": "provider+tenant+project+operation",
                "request_fingerprint_sha256": fingerprint,
                "reuse_requires_identical_fingerprint": True,
            },
            "execution_hook": {
                "interface": "ChinaPaymentExecutor",
                "adapter_executes": False,
                "secret_resolution_deferred": True,
            },
            "raw_secret_present": False,
            "raw_private_data_present": False,
            "raw_pan_present": False,
            "raw_cvc_present": False,
            "raw_otp_present": False,
            "side_effects": _no_side_effects(),
        }
        return self.idempotency_registry.register(
            provider=self.provider,
            tenant_id=tenant_id,
            project_id=project_id,
            operation=operation,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            plan=plan,
        )

    def _remember_ref(
        self, ref: str, tenant_id: str, project_id: str, resource_type: str
    ) -> None:
        existing = self._scoped_refs.get(ref)
        scope = (tenant_id, project_id, resource_type)
        if existing is not None and existing != scope:
            raise PaymentScopeViolation(
                "provider reference is already bound to another tenant or project"
            )
        self._scoped_refs[ref] = scope

    def _assert_ref_scope(self, ref: str, tenant_id: str, project_id: str) -> None:
        _validate_ref("provider_resource_ref", ref)
        existing = self._scoped_refs.get(ref)
        if existing is None:
            raise PaymentScopeViolation("provider reference is not registered in this domain")
        if existing[:2] != (tenant_id, project_id):
            raise PaymentScopeViolation(
                "provider reference belongs to another tenant or project"
            )


def china_payment_capability_matrix() -> JsonDict:
    return {
        provider: {
            channel: dict(capability)
            for channel, capability in channels.items()
        }
        for provider, channels in _CAPABILITY_MATRIX.items()
    }


def normalize_china_provider(provider: str) -> str:
    normalized = str(provider).strip().lower().replace("-", "_")
    normalized = _PROVIDER_ALIASES.get(normalized, normalized)
    if normalized not in CHINA_PAYMENT_PROVIDERS:
        raise ChinaPaymentContractError(
            "China payment provider must be wechat_pay, alipay, or domestic_bank_card"
        )
    return normalized


def normalize_payment_channel(channel: str) -> str:
    normalized = str(channel).strip().lower().replace(" ", "_")
    normalized = _CHANNEL_ALIASES.get(normalized, normalized)
    if normalized not in CHINA_PAYMENT_CHANNELS:
        raise ChinaPaymentContractError("unsupported China payment channel")
    return normalized


def normalize_payment_lifecycle(provider: str, provider_status: str | None) -> str:
    normalized_provider = normalize_china_provider(provider)
    status = str(provider_status or "").strip().upper()
    return _LIFECYCLE_MAP[normalized_provider].get(status, "unknown")


def verify_china_notification(
    *,
    config: ChinaMerchantConfig,
    tenant_id: str,
    project_id: str,
    raw_body: bytes,
    signature_material: Mapping[str, str],
    verifier: ChinaNotificationVerifier,
) -> JsonDict:
    validated = config.validate()
    _validate_scope(tenant_id, project_id)
    if not isinstance(raw_body, bytes) or not raw_body:
        raise ChinaPaymentContractError(
            "notification verification requires non-empty raw bytes"
        )
    normalized_material = {
        str(name).strip().lower(): str(value)
        for name, value in signature_material.items()
        if str(name).strip()
    }
    required = (
        ("wechatpay-signature", "wechatpay-timestamp", "wechatpay-nonce", "wechatpay-serial")
        if validated.provider == "wechat_pay"
        else ("sign", "sign_type")
        if validated.provider == "alipay"
        else ("acquirer-signature", "acquirer-timestamp", "acquirer-certificate-ref")
    )
    missing = [name for name in required if not normalized_material.get(name)]
    result = NotificationVerificationResult(
        verified=False,
        reason_codes=("missing_signature_material",),
    )
    verifier_called = False
    if not missing:
        request = NotificationVerificationRequest(
            provider=validated.provider,
            mode=validated.mode_gate.mode,
            tenant_id=tenant_id,
            project_id=project_id,
            raw_body=raw_body,
            signature_material=normalized_material,
            verification_key_ref=validated.verification_key_ref,
            certificate_refs=validated.certificate_refs,
        )
        candidate = verifier.verify(request)
        verifier_called = True
        if not isinstance(candidate, NotificationVerificationResult):
            raise ChinaPaymentContractError(
                "notification verifier returned an unsupported result"
            )
        if candidate.provider_event_ref is not None:
            _validate_ref("provider_event_ref", candidate.provider_event_ref)
        if candidate.certificate_ref is not None:
            _validate_ref("certificate_ref", candidate.certificate_ref)
            if candidate.certificate_ref not in validated.certificate_refs:
                candidate = NotificationVerificationResult(
                    verified=False,
                    provider_event_ref=candidate.provider_event_ref,
                    provider_status=candidate.provider_status,
                    certificate_ref=candidate.certificate_ref,
                    reason_codes=tuple(candidate.reason_codes)
                    + ("untrusted_certificate_ref",),
                )
        result = candidate
    lifecycle = normalize_payment_lifecycle(
        validated.provider, result.provider_status
    )
    return {
        "schema_version": CHINA_PAYMENT_SCHEMA_VERSION,
        "envelope_type": "china_payment_notification_verification",
        "provider": validated.provider,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "mode": validated.mode_gate.mode,
        "verified": bool(result.verified) and not result.reason_codes,
        "provider_event_ref": result.provider_event_ref,
        "provider_status": result.provider_status,
        "normalized_lifecycle": lifecycle,
        "certificate_ref": result.certificate_ref,
        "payload_sha256": hashlib.sha256(raw_body).hexdigest(),
        "signature_shape": {
            "expected_fields": list(required),
            "provided_fields": sorted(normalized_material),
            "missing_fields": missing,
            "raw_values_included": False,
        },
        "reason_codes": list(result.reason_codes),
        "verification_hook": {
            "interface": "ChinaNotificationVerifier",
            "verifier_called": verifier_called,
        },
        "raw_body_included": False,
        "raw_private_data_present": False,
        "side_effects": _no_side_effects(),
    }


def parse_daily_bill_reconciliation(
    *,
    provider: str,
    tenant_id: str,
    project_id: str,
    bill_date: str,
    raw_bill: bytes,
    expected_sha256: str | None = None,
) -> JsonDict:
    normalized_provider = normalize_china_provider(provider)
    _validate_scope(tenant_id, project_id)
    normalized_date = _validate_bill_date(bill_date)
    if not isinstance(raw_bill, bytes) or not raw_bill:
        raise ChinaPaymentContractError("daily bill must be non-empty bytes")
    bill_sha256 = hashlib.sha256(raw_bill).hexdigest()
    if expected_sha256 is not None:
        expected = str(expected_sha256).strip().lower()
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise ChinaPaymentContractError("expected_sha256 must be a SHA-256 digest")
        if expected != bill_sha256:
            raise ChinaPaymentContractError("daily bill SHA-256 mismatch")
    try:
        text = raw_bill.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ChinaPaymentContractError("daily bill must be UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ChinaPaymentContractError("daily bill CSV requires a header row")
    row_hashes: list[str] = []
    status_counts: dict[str, int] = {}
    amount_total_minor = 0
    amount_rows = 0
    for row in reader:
        canonical = {
            str(key).strip(): str(value or "").strip()
            for key, value in row.items()
            if key is not None
        }
        if not any(canonical.values()):
            continue
        row_hashes.append(_fingerprint(canonical))
        status = _first_present(
            canonical, ("provider_status", "trade_status", "status")
        )
        lifecycle = normalize_payment_lifecycle(normalized_provider, status)
        status_counts[lifecycle] = status_counts.get(lifecycle, 0) + 1
        amount = _first_present(
            canonical, ("amount_minor", "total_amount_minor", "trade_amount_minor")
        )
        if amount:
            try:
                amount_total_minor += int(amount)
                amount_rows += 1
            except ValueError as exc:
                raise ChinaPaymentContractError(
                    "daily bill amount columns must contain integer minor units"
                ) from exc
    return {
        "schema_version": CHINA_PAYMENT_SCHEMA_VERSION,
        "envelope_type": "china_payment_daily_bill_reconciliation",
        "provider": normalized_provider,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "bill_date": normalized_date,
        "bill_sha256": bill_sha256,
        "row_count": len(row_hashes),
        "row_sha256": row_hashes,
        "normalized_lifecycle_counts": dict(sorted(status_counts.items())),
        "amount_summary": {
            "currency": "CNY",
            "unit": "fen",
            "minor_total": amount_total_minor,
            "rows_with_amount": amount_rows,
        },
        "raw_bill_included": False,
        "raw_row_values_included": False,
        "provider_identifiers_included": False,
        "side_effects": _no_side_effects(),
    }


def _channel_capability(provider: str, channel: str) -> dict[str, Any]:
    capability = _CAPABILITY_MATRIX[provider][channel]
    if not capability.get("supported"):
        raise ChinaPaymentContractError(str(capability.get("reason", "unsupported channel")))
    return capability


def _validate_context_refs(
    context_refs: Mapping[str, str] | None, required: Sequence[str]
) -> JsonDict:
    context = dict(context_refs or {})
    missing = [name for name in required if not context.get(name)]
    if missing:
        raise ChinaPaymentContractError(
            f"channel requires context refs: {', '.join(missing)}"
        )
    for name, value in context.items():
        _validate_ref(str(name), value)
    _validate_public_mapping("context_refs", context)
    return context


def _validate_cny_amount(amount_minor: int, currency: str) -> None:
    if str(currency).strip().upper() != "CNY":
        raise ChinaPaymentContractError("China payment trade plans require CNY")
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
        raise ChinaPaymentContractError(
            "amount_minor must be a positive integer number of fen"
        )


def _validate_public_mapping(name: str, values: Mapping[str, Any]) -> None:
    _validate_public_value(name, values)


def _validate_public_value(path: str, value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if _is_forbidden_payment_field(key_text):
                raise ChinaPaymentContractError(
                    f"{path} must not contain forbidden payment data "
                    f"(PAN/CVC/OTP/cardholder/KYC) field {key_text!r}"
                )
            _validate_public_value(f"{path}.{key_text}", item)
        return
    if isinstance(value, (list, tuple, set)):
        for index, item in enumerate(value):
            _validate_public_value(f"{path}[{index}]", item)
        return
    if isinstance(value, (bytes, bytearray)):
        raise ChinaPaymentContractError(f"{path} must not contain raw binary payment data")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ChinaPaymentContractError(f"{path} contains an unsupported public value")
    if isinstance(value, str):
        _reject_bank_card_material(path, value)


def _safe_public_text(name: str, value: str) -> str:
    text = _safe_text(name, value)
    _reject_bank_card_material(name, text)
    return text


def _reject_bank_card_material(name: str, value: str) -> None:
    if (
        _is_forbidden_payment_field(name)
        or _POSSIBLE_PAN_RE.search(value)
        or _FORBIDDEN_PAYMENT_VALUE_RE.search(value)
    ):
        raise ChinaPaymentContractError(
            "forbidden payment data (PAN/CVC/OTP/cardholder/KYC) must use a "
            "hosted URL, provider token, or opaque reference"
        )


def _canonical_payment_field_name(value: str) -> str:
    with_boundaries = _CAMEL_CASE_BOUNDARY_RE.sub("_", str(value).strip())
    return _PAYMENT_FIELD_SEPARATOR_RE.sub("_", with_boundaries.lower()).strip("_")


def _is_forbidden_payment_field(value: str) -> bool:
    canonical = _canonical_payment_field_name(value)
    if canonical in _FORBIDDEN_PAYMENT_FIELD_NAMES:
        return True
    return (
        canonical.startswith(("kyc_", "raw_kyc_", "cardholder_", "card_holder_"))
        or canonical.endswith(("_cryptogram", "_track_data"))
    )


def _validate_scope(tenant_id: str, project_id: str) -> None:
    if not str(tenant_id).strip() or not str(project_id).strip():
        raise ChinaPaymentContractError("tenant_id and project_id are required")


def _validate_bill_date(value: str) -> str:
    text = str(value).strip()
    parts = text.split("-")
    if (
        len(parts) != 3
        or tuple(map(len, parts)) != (4, 2, 2)
        or not all(part.isdigit() for part in parts)
    ):
        raise ChinaPaymentContractError("bill_date must use YYYY-MM-DD")
    year, month, day = (int(part) for part in parts)
    if year < 2000 or not 1 <= month <= 12 or not 1 <= day <= 31:
        raise ChinaPaymentContractError("bill_date is not valid")
    return text


def _first_present(row: Mapping[str, str], names: Sequence[str]) -> str:
    lowered = {str(key).strip().lower(): value for key, value in row.items()}
    for name in names:
        if lowered.get(name):
            return lowered[name]
    return ""


def _fingerprint(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _deep_copy(value: JsonDict) -> JsonDict:
    return json.loads(json.dumps(value, sort_keys=True))
