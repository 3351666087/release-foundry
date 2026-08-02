"""Provider-neutral payment plans and verification integration hooks.

The adapters in this module are deliberately incapable of network I/O. They
validate control-plane inputs, build public-safe hosted-payment plans, and
define the narrow interfaces an external executor or signature verifier must
implement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse

JsonDict = dict[str, Any]

PAYMENT_PROVIDER_SCHEMA_VERSION = "releasefoundry.payment_provider_adapter.v2"
REFERENCE_PREFIXES = ("env:", "vault:", "kms:", "provider-ref:", "dashboard-ref:")
PAYMENT_MODES = {"test", "live"}
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,255}$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
_SENSITIVE_FIELD_RE = re.compile(
    r"(?:card|pan|cvc|cvv|expiry|credential|account_number|private_key|client_secret|access_token|refresh_token)",
    re.IGNORECASE,
)
_RAW_SECRET_RE = re.compile(
    r"(?:\b(?:sk|rk|whsec)_(?:test|live)_[A-Za-z0-9]{8,}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_CARD_NUMBER_RE = re.compile(r"(?:\d[ -]*?){13,19}")


class PaymentProviderContractError(ValueError):
    """Raised when a provider plan crosses a production-safety boundary."""


@dataclass(frozen=True)
class PaymentModeGate:
    """Explicitly separates test planning from live execution authorization."""

    mode: str = "test"
    live_mode_ack: bool = False
    live_execution_gate_ref: str | None = None

    def validate(self) -> "PaymentModeGate":
        mode = str(self.mode).strip().lower()
        if mode not in PAYMENT_MODES:
            raise PaymentProviderContractError("payment mode must be test or live")
        if mode == "live":
            if not self.live_mode_ack:
                raise PaymentProviderContractError("live mode requires explicit live_mode_ack")
            _validate_ref("live_execution_gate_ref", self.live_execution_gate_ref)
        elif self.live_execution_gate_ref is not None:
            raise PaymentProviderContractError("test mode must not carry a live execution gate")
        return PaymentModeGate(
            mode=mode,
            live_mode_ack=bool(self.live_mode_ack),
            live_execution_gate_ref=self.live_execution_gate_ref,
        )

    def to_public_dict(self) -> JsonDict:
        gate = self.validate()
        return {
            "mode": gate.mode,
            "live_mode_ack": gate.live_mode_ack,
            "live_execution_gate_ref": gate.live_execution_gate_ref,
            "test_live_boundary_enforced": True,
            "adapter_can_execute": False,
        }


@dataclass(frozen=True)
class SignatureVerificationRequest:
    """Transient request passed to an injected provider verifier.

    Raw bytes and header values are intentionally excluded from repr and have
    no public serializer. The caller owns their lifecycle and must discard them
    after verification.
    """

    provider: str
    mode: str
    raw_body: bytes = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    verification_key_ref: str
    expected_livemode: bool


@dataclass(frozen=True)
class SignatureVerificationResult:
    verified: bool
    event_id_ref: str | None = None
    event_type: str | None = None
    livemode: bool | None = None
    reason_codes: tuple[str, ...] = ()


class PaymentSignatureVerifier(Protocol):
    """Provider SDK or cryptographic boundary implemented outside this module."""

    def verify(self, request: SignatureVerificationRequest) -> SignatureVerificationResult:
        ...


class HostedPaymentExecutor(Protocol):
    """Optional external executor; adapters themselves never implement this."""

    def execute(self, plan: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class StripeProviderConfig:
    mode_gate: PaymentModeGate
    api_secret_ref: str
    webhook_secret_ref: str
    account_ref: str | None = None

    def validate(self) -> "StripeProviderConfig":
        gate = self.mode_gate.validate()
        _validate_ref("api_secret_ref", self.api_secret_ref)
        _validate_ref("webhook_secret_ref", self.webhook_secret_ref)
        if self.account_ref is not None:
            _validate_ref("account_ref", self.account_ref)
        return StripeProviderConfig(
            mode_gate=gate,
            api_secret_ref=self.api_secret_ref,
            webhook_secret_ref=self.webhook_secret_ref,
            account_ref=self.account_ref,
        )


@dataclass(frozen=True)
class HostedWalletProviderConfig:
    provider: str
    mode_gate: PaymentModeGate
    signing_key_ref: str
    verification_key_ref: str
    merchant_account_ref: str

    def validate(self) -> "HostedWalletProviderConfig":
        provider = _normalize_wallet_provider(self.provider)
        gate = self.mode_gate.validate()
        _validate_ref("signing_key_ref", self.signing_key_ref)
        _validate_ref("verification_key_ref", self.verification_key_ref)
        _validate_ref("merchant_account_ref", self.merchant_account_ref)
        return HostedWalletProviderConfig(
            provider=provider,
            mode_gate=gate,
            signing_key_ref=self.signing_key_ref,
            verification_key_ref=self.verification_key_ref,
            merchant_account_ref=self.merchant_account_ref,
        )


class StripePaymentAdapter:
    """Build Stripe-hosted Checkout plans without importing or calling Stripe."""

    provider = "stripe"
    expected_signature_headers = ("stripe-signature",)

    def __init__(self, config: StripeProviderConfig):
        self.config = config.validate()

    def build_checkout_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        customer_ref: str,
        price_ref: str,
        checkout_mode: str,
        quantity: int,
        success_url: str,
        cancel_url: str,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        _validate_common_plan_fields(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            urls=(success_url, cancel_url),
            metadata=metadata,
        )
        _validate_ref("customer_ref", customer_ref)
        _validate_ref("price_ref", price_ref)
        normalized_checkout_mode = str(checkout_mode).strip().lower()
        if normalized_checkout_mode not in {"payment", "subscription"}:
            raise PaymentProviderContractError(
                "checkout_mode must be payment or subscription"
            )
        if int(quantity) < 1:
            raise PaymentProviderContractError("quantity must be at least one")
        request_shape = {
            "operation": "checkout.sessions.create",
            "checkout_mode": normalized_checkout_mode,
            "customer_ref": customer_ref,
            "price_ref": price_ref,
            "quantity": int(quantity),
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": _public_metadata(metadata),
        }
        return _hosted_plan(
            provider=self.provider,
            surface="stripe_checkout",
            gate=self.config.mode_gate,
            credential_ref=self.config.api_secret_ref,
            verification_key_ref=self.config.webhook_secret_ref,
            account_ref=self.config.account_ref,
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            request_shape=request_shape,
        )

    def build_portal_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        customer_ref: str,
        return_url: str,
        idempotency_key: str,
    ) -> JsonDict:
        _validate_common_plan_fields(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            urls=(return_url,),
            metadata=None,
        )
        _validate_ref("customer_ref", customer_ref)
        return _hosted_plan(
            provider=self.provider,
            surface="stripe_billing_portal",
            gate=self.config.mode_gate,
            credential_ref=self.config.api_secret_ref,
            verification_key_ref=self.config.webhook_secret_ref,
            account_ref=self.config.account_ref,
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            request_shape={
                "operation": "billing_portal.sessions.create",
                "customer_ref": customer_ref,
                "return_url": return_url,
            },
        )

    def verify_webhook(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        verifier: PaymentSignatureVerifier,
    ) -> JsonDict:
        return verify_provider_webhook(
            provider=self.provider,
            mode_gate=self.config.mode_gate,
            raw_body=raw_body,
            headers=headers,
            verification_key_ref=self.config.webhook_secret_ref,
            expected_headers=self.expected_signature_headers,
            verifier=verifier,
        )


class HostedWalletPaymentAdapter:
    """Build WeChat Pay or Alipay hosted handoff plans."""

    _SURFACES = {
        "wechat_pay": "wechat_pay_native_qr_handoff",
        "alipay": "alipay_trade_page_pay_handoff",
    }
    _OPERATIONS = {
        "wechat_pay": "hosted_checkout.prepay",
        "alipay": "hosted_checkout.trade_page_pay",
    }
    _SIGNATURE_HEADERS = {
        "wechat_pay": (
            "wechatpay-signature",
            "wechatpay-timestamp",
            "wechatpay-nonce",
            "wechatpay-serial",
        ),
        "alipay": ("sign", "sign_type"),
    }

    def __init__(self, config: HostedWalletProviderConfig):
        self.config = config.validate()
        self.provider = self.config.provider

    def build_hosted_payment_plan(
        self,
        *,
        tenant_id: str,
        project_id: str,
        order_ref: str,
        amount_minor: int,
        currency: str,
        description: str,
        return_url: str,
        notify_url: str,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        _validate_common_plan_fields(
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            urls=(return_url, notify_url),
            metadata=metadata,
        )
        _validate_ref("order_ref", order_ref)
        if int(amount_minor) <= 0:
            raise PaymentProviderContractError("amount_minor must be positive")
        if str(currency).upper() != "CNY":
            raise PaymentProviderContractError("hosted WeChat Pay and Alipay plans require CNY")
        request_shape = {
            "operation": self._OPERATIONS[self.provider],
            "order_ref": order_ref,
            "amount": {"minor": int(amount_minor), "currency": "CNY"},
            "description": _safe_text("description", description),
            "return_url": return_url,
            "notify_url": notify_url,
            "metadata": _public_metadata(metadata),
        }
        return _hosted_plan(
            provider=self.provider,
            surface=self._SURFACES[self.provider],
            gate=self.config.mode_gate,
            credential_ref=self.config.signing_key_ref,
            verification_key_ref=self.config.verification_key_ref,
            account_ref=self.config.merchant_account_ref,
            tenant_id=tenant_id,
            project_id=project_id,
            idempotency_key=idempotency_key,
            request_shape=request_shape,
        )

    def verify_notification(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        verifier: PaymentSignatureVerifier,
    ) -> JsonDict:
        return verify_provider_webhook(
            provider=self.provider,
            mode_gate=self.config.mode_gate,
            raw_body=raw_body,
            headers=headers,
            verification_key_ref=self.config.verification_key_ref,
            expected_headers=self._SIGNATURE_HEADERS[self.provider],
            verifier=verifier,
        )


def verify_provider_webhook(
    *,
    provider: str,
    mode_gate: PaymentModeGate,
    raw_body: bytes,
    headers: Mapping[str, str],
    verification_key_ref: str,
    expected_headers: Sequence[str],
    verifier: PaymentSignatureVerifier,
) -> JsonDict:
    """Run an injected verifier and return only a hash-safe result envelope."""

    gate = mode_gate.validate()
    _validate_ref("verification_key_ref", verification_key_ref)
    if not isinstance(raw_body, bytes) or not raw_body:
        raise PaymentProviderContractError("webhook verification requires non-empty raw bytes")
    normalized_headers = {str(name).strip().lower(): str(value) for name, value in headers.items()}
    required = tuple(str(name).lower() for name in expected_headers)
    missing = [name for name in required if not normalized_headers.get(name)]
    if missing:
        return _verification_envelope(
            provider=provider,
            gate=gate,
            raw_body=raw_body,
            expected_headers=required,
            provided_headers=tuple(normalized_headers),
            result=SignatureVerificationResult(
                verified=False,
                reason_codes=("missing_signature_headers",),
            ),
            missing_headers=missing,
            verifier_called=False,
        )
    request = SignatureVerificationRequest(
        provider=provider,
        mode=gate.mode,
        raw_body=raw_body,
        headers=normalized_headers,
        verification_key_ref=verification_key_ref,
        expected_livemode=gate.mode == "live",
    )
    result = verifier.verify(request)
    if not isinstance(result, SignatureVerificationResult):
        raise PaymentProviderContractError("signature verifier returned an unsupported result")
    reasons = list(result.reason_codes)
    if result.livemode is not None and result.livemode != request.expected_livemode:
        reasons.append("provider_mode_mismatch")
    safe_result = SignatureVerificationResult(
        verified=bool(result.verified) and not reasons,
        event_id_ref=result.event_id_ref,
        event_type=result.event_type,
        livemode=result.livemode,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )
    if safe_result.event_id_ref is not None:
        _validate_ref("event_id_ref", safe_result.event_id_ref)
    return _verification_envelope(
        provider=provider,
        gate=gate,
        raw_body=raw_body,
        expected_headers=required,
        provided_headers=tuple(normalized_headers),
        result=safe_result,
        missing_headers=[],
        verifier_called=True,
    )


def payment_provider_contract_manifest() -> JsonDict:
    from .china_payments import china_payment_capability_matrix

    china_capabilities = china_payment_capability_matrix()
    return {
        "schema_version": PAYMENT_PROVIDER_SCHEMA_VERSION,
        "domain_priority": "china_first",
        "providers": {
            "stripe": {
                "role": "compatibility_only",
                "hosted_surfaces": ["stripe_checkout", "stripe_billing_portal"],
                "modes": ["test", "live"],
                "live_gate_fields": ["live_mode_ack", "live_execution_gate_ref"],
                "signature_headers": ["stripe-signature"],
            },
            "wechat_pay": {
                "role": "primary",
                "protocol": "wechat_pay_api_v3",
                "channels": china_capabilities["wechat_pay"],
                "hosted_surfaces": [
                    "native",
                    "jsapi",
                    "h5",
                    "app",
                    "mini_program",
                ],
                "modes": ["test", "live"],
                "live_gate_fields": ["live_mode_ack", "live_execution_gate_ref"],
                "signature_headers": list(HostedWalletPaymentAdapter._SIGNATURE_HEADERS["wechat_pay"]),
            },
            "alipay": {
                "role": "primary",
                "protocol": "alipay_openapi",
                "channels": china_capabilities["alipay"],
                "hosted_surfaces": ["native", "h5", "app", "mini_program"],
                "modes": ["test", "live"],
                "live_gate_fields": ["live_mode_ack", "live_execution_gate_ref"],
                "signature_headers": list(HostedWalletPaymentAdapter._SIGNATURE_HEADERS["alipay"]),
            },
            "domestic_bank_card": {
                "role": "primary",
                "protocol": "domestic_card_acquirer",
                "channels": china_capabilities["domestic_bank_card"],
                "hosted_surfaces": ["hosted", "token_ref"],
                "modes": ["test", "live"],
                "live_gate_fields": ["live_mode_ack", "live_execution_gate_ref"],
                "signature_headers": [
                    "acquirer-signature",
                    "acquirer-timestamp",
                    "acquirer-certificate-ref",
                ],
                "raw_card_data_allowed": False,
            },
        },
        "integration_hooks": {
            "executor": "HostedPaymentExecutor",
            "china_executor": "ChinaPaymentExecutor",
            "signature_verifier": "PaymentSignatureVerifier",
            "china_notification_verifier": "ChinaNotificationVerifier",
            "secret_resolution_owned_by_adapter": False,
        },
        "china_domain_controls": {
            "currency": "CNY",
            "merchant_app_certificate_refs_only": True,
            "domestic_bank_card_hosted_or_token_ref_only": True,
            "pan_cvc_otp_forbidden": True,
            "amount_unit": "fen",
            "normalized_lifecycle": True,
            "refund_create_and_query": True,
            "trade_close_and_query": True,
            "daily_bill_hash_reconciliation": True,
            "tenant_project_isolation": True,
            "scoped_idempotency_conflict": True,
        },
        "side_effects": _no_side_effects(),
    }


def _hosted_plan(
    *,
    provider: str,
    surface: str,
    gate: PaymentModeGate,
    credential_ref: str,
    verification_key_ref: str,
    account_ref: str | None,
    tenant_id: str,
    project_id: str,
    idempotency_key: str,
    request_shape: Mapping[str, Any],
) -> JsonDict:
    _validate_ref("credential_ref", credential_ref)
    _validate_ref("verification_key_ref", verification_key_ref)
    if account_ref is not None:
        _validate_ref("account_ref", account_ref)
    fingerprint_source = {
        "provider": provider,
        "mode": gate.mode,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "idempotency_key": idempotency_key,
        "request_shape": request_shape,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": PAYMENT_PROVIDER_SCHEMA_VERSION,
        "plan_type": "hosted_payment",
        "provider": provider,
        "hosted_surface": surface,
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "mode_gate": gate.to_public_dict(),
        "credential_ref": credential_ref,
        "verification_key_ref": verification_key_ref,
        "account_ref": account_ref,
        "idempotency": {
            "required": True,
            "key": idempotency_key,
            "request_fingerprint_sha256": fingerprint,
            "reuse_requires_identical_fingerprint": True,
        },
        "request_shape": dict(request_shape),
        "execution_hook": {
            "interface": "HostedPaymentExecutor",
            "adapter_executes": False,
            "secret_resolution_deferred": True,
        },
        "side_effects": _no_side_effects(),
        "raw_secret_present": False,
        "raw_card_data_present": False,
    }


def _verification_envelope(
    *,
    provider: str,
    gate: PaymentModeGate,
    raw_body: bytes,
    expected_headers: Sequence[str],
    provided_headers: Sequence[str],
    result: SignatureVerificationResult,
    missing_headers: Sequence[str],
    verifier_called: bool,
) -> JsonDict:
    digest = hashlib.sha256(raw_body).hexdigest()
    if not _DIGEST_RE.fullmatch(digest):
        raise AssertionError("sha256 digest generation failed")
    return {
        "schema_version": PAYMENT_PROVIDER_SCHEMA_VERSION,
        "plan_type": "signature_verification",
        "provider": provider,
        "mode": gate.mode,
        "verified": result.verified,
        "event_id_ref": result.event_id_ref,
        "event_type": result.event_type,
        "livemode": result.livemode,
        "payload_sha256": digest,
        "signature_header_shape": {
            "expected_headers": list(expected_headers),
            "provided_headers": sorted(set(provided_headers)),
            "missing_headers": list(missing_headers),
            "raw_header_values_included": False,
        },
        "reason_codes": list(result.reason_codes),
        "integration_hook": {
            "interface": "PaymentSignatureVerifier",
            "verifier_called": verifier_called,
        },
        "raw_body_included": False,
        "secret_value_present": False,
        "side_effects": _no_side_effects(),
    }


def _validate_common_plan_fields(
    *,
    tenant_id: str,
    project_id: str,
    idempotency_key: str,
    urls: Sequence[str],
    metadata: Mapping[str, Any] | None,
) -> None:
    if not str(tenant_id).strip() or not str(project_id).strip():
        raise PaymentProviderContractError("tenant_id and project_id are required")
    if not _IDEMPOTENCY_RE.fullmatch(str(idempotency_key)):
        raise PaymentProviderContractError(
            "idempotency_key must be 8-255 safe characters"
        )
    for url in urls:
        _validate_https_url(url)
    _public_metadata(metadata)


def _validate_https_url(value: str) -> None:
    parsed = urlparse(str(value))
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise PaymentProviderContractError("provider redirect and callback URLs must be HTTPS")


def _validate_ref(name: str, value: str | None) -> None:
    text = str(value or "")
    if not any(text.startswith(prefix) for prefix in REFERENCE_PREFIXES):
        raise PaymentProviderContractError(
            f"{name} must use an approved reference prefix"
        )
    if any(character.isspace() for character in text):
        raise PaymentProviderContractError(f"{name} must not contain whitespace")
    _reject_sensitive_value(name, text)


def _normalize_wallet_provider(provider: str) -> str:
    normalized = str(provider).strip().lower().replace("-", "_")
    aliases = {"wechat": "wechat_pay", "alipay_plus": "alipay"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"wechat_pay", "alipay"}:
        raise PaymentProviderContractError("hosted wallet provider must be wechat_pay or alipay")
    return normalized


def _safe_text(name: str, value: str) -> str:
    text = str(value).strip()
    if not text:
        raise PaymentProviderContractError(f"{name} must not be empty")
    if _SENSITIVE_FIELD_RE.search(text):
        raise PaymentProviderContractError(f"{name} contains a sensitive payment marker")
    _reject_sensitive_value(name, text)
    return text


def _public_metadata(metadata: Mapping[str, Any] | None) -> JsonDict:
    public: JsonDict = {}
    for key, value in (metadata or {}).items():
        key_text = str(key)
        if _SENSITIVE_FIELD_RE.search(key_text):
            raise PaymentProviderContractError("metadata contains a sensitive payment field")
        if isinstance(value, (dict, list, tuple, set, bytes, bytearray)):
            raise PaymentProviderContractError("metadata values must be scalar and public-safe")
        value_text = str(value)
        if _SENSITIVE_FIELD_RE.search(value_text):
            raise PaymentProviderContractError("metadata contains sensitive payment material")
        _reject_sensitive_value("metadata", value_text)
        public[key_text] = value
    return public


def _reject_sensitive_value(name: str, value: str) -> None:
    if _RAW_SECRET_RE.search(value):
        raise PaymentProviderContractError(f"{name} contains raw provider secret material")
    if _CARD_NUMBER_RE.search(value):
        raise PaymentProviderContractError(f"{name} contains possible card data")


def _no_side_effects() -> JsonDict:
    return {
        "provider_called": False,
        "checkout_or_portal_called": False,
        "real_charge_possible": False,
        "network_io_performed": False,
    }
