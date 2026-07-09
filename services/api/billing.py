"""Billing provider contracts for Ashr clone SaaS control plane.

This module intentionally builds provider plans instead of making network calls.
It gives A1 a typed, public-safe contract for Stripe hosted Checkout/Billing
Portal and hosted China payment rails while keeping live secrets and card data
out of code, logs, and evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
import uuid
from typing import Any, Mapping, Sequence

JsonDict = dict[str, Any]

BILLING_SCHEMA_VERSION = "ashr.clone.billing_provider_contract.v1"
SUPPORTED_PROVIDERS = {"stripe", "wechat_pay", "alipay"}
SUPPORTED_MODES = {"test", "live"}
SUPPORTED_CURRENCIES = {"usd", "cny"}
SUPPORTED_PAYMENT_METHODS: dict[str, tuple[str, ...]] = {
    "stripe": ("card", "alipay", "wechat_pay"),
    "wechat_pay": ("wechat_pay",),
    "alipay": ("alipay",),
}

_SECRET_KEY_RE = re.compile(r"\b(?:sk|rk|whsec)_(?:test|live)_[A-Za-z0-9]{8,}\b")
_CARD_NUMBER_RE = re.compile(r"(?:\d[ -]*?){13,19}")


class BillingContractError(ValueError):
    """Raised when a billing plan would leak secrets or trigger unsafe live use."""


@dataclass(frozen=True)
class BillingPrice:
    lookup_key: str
    unit_amount_minor: int
    currency: str = "usd"
    interval: str = "month"
    metered: bool = False
    included_units: int = 0

    def to_public_dict(self) -> JsonDict:
        return {
            "lookup_key": self.lookup_key,
            "unit_amount_minor": self.unit_amount_minor,
            "currency": self.currency,
            "interval": self.interval,
            "metered": self.metered,
            "included_units": self.included_units,
        }


@dataclass(frozen=True)
class BillingProviderConfig:
    provider: str
    mode: str = "test"
    secret_ref: str | None = None
    webhook_secret_ref: str | None = None
    account_ref: str | None = None
    live_mode_ack: bool = False
    allowed_payment_methods: tuple[str, ...] = field(default_factory=tuple)

    def normalized(self) -> "BillingProviderConfig":
        provider = _normalize_provider(self.provider)
        mode = _normalize_mode(self.mode)
        methods = tuple(self.allowed_payment_methods or SUPPORTED_PAYMENT_METHODS[provider])
        normalized = BillingProviderConfig(
            provider=provider,
            mode=mode,
            secret_ref=self.secret_ref,
            webhook_secret_ref=self.webhook_secret_ref,
            account_ref=self.account_ref,
            live_mode_ack=bool(self.live_mode_ack),
            allowed_payment_methods=methods,
        )
        _validate_provider_config(normalized)
        return normalized

    def to_public_dict(self) -> JsonDict:
        normalized = self.normalized()
        return {
            "provider": normalized.provider,
            "mode": normalized.mode,
            "secret_ref": normalized.secret_ref,
            "webhook_secret_ref": normalized.webhook_secret_ref,
            "account_ref": normalized.account_ref,
            "live_mode_ack": normalized.live_mode_ack,
            "allowed_payment_methods": list(normalized.allowed_payment_methods),
            "raw_secret_present": False,
        }


def build_checkout_session_plan(
    *,
    tenant_id: str,
    project_id: str,
    customer_ref: str,
    price: BillingPrice | Mapping[str, Any],
    success_url: str,
    cancel_url: str,
    provider_config: BillingProviderConfig | Mapping[str, Any] | None = None,
    usage_rollup: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    quantity: int = 1,
    idempotency_key: str | None = None,
) -> JsonDict:
    """Build a public-safe hosted checkout plan without calling providers."""

    config = _coerce_provider_config(provider_config)
    price_obj = _coerce_price(price)
    _validate_tenant_project(tenant_id, project_id)
    _reject_sensitive_payload({"metadata": metadata, "customer_ref": customer_ref, "success_url": success_url, "cancel_url": cancel_url})
    if quantity < 1:
        raise BillingContractError("quantity must be >= 1")
    if not str(success_url).startswith("https://") or not str(cancel_url).startswith("https://"):
        raise BillingContractError("checkout redirect urls must be https")

    rollup = _public_usage_rollup(usage_rollup, tenant_id=tenant_id, project_id=project_id)
    plan_id = _plan_id("checkout", tenant_id, project_id, customer_ref, price_obj.lookup_key, config.provider, config.mode, idempotency_key)
    session = {
        "schema_version": BILLING_SCHEMA_VERSION,
        "plan_type": "checkout_session",
        "plan_id": plan_id,
        "provider": config.provider,
        "mode": config.mode,
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "customer_ref": str(customer_ref),
        "price": price_obj.to_public_dict(),
        "quantity": int(quantity),
        "currency": price_obj.currency,
        "payment_methods": list(config.allowed_payment_methods),
        "success_url": str(success_url),
        "cancel_url": str(cancel_url),
        "metadata": _public_metadata(metadata),
        "usage_rollup": rollup,
        "provider_request": _provider_checkout_request(config, price_obj, tenant_id, project_id, customer_ref, quantity),
        "side_effects": {"provider_called": False, "checkout_or_portal_called": False, "real_charge_possible": False},
        "created_at": _utc_now(),
        "idempotency_key": idempotency_key or plan_id,
    }
    return _assert_public_safe(session)


def build_billing_portal_plan(
    *,
    tenant_id: str,
    project_id: str,
    customer_ref: str,
    return_url: str,
    provider_config: BillingProviderConfig | Mapping[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> JsonDict:
    config = _coerce_provider_config(provider_config)
    _validate_tenant_project(tenant_id, project_id)
    _reject_sensitive_payload({"customer_ref": customer_ref, "return_url": return_url})
    if not str(return_url).startswith("https://"):
        raise BillingContractError("billing portal return_url must be https")
    if config.provider != "stripe":
        raise BillingContractError("billing portal is currently only available through stripe")

    plan_id = _plan_id("portal", tenant_id, project_id, customer_ref, config.provider, config.mode, idempotency_key)
    plan = {
        "schema_version": BILLING_SCHEMA_VERSION,
        "plan_type": "billing_portal",
        "plan_id": plan_id,
        "provider": config.provider,
        "mode": config.mode,
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "customer_ref": str(customer_ref),
        "return_url": str(return_url),
        "provider_request": {
            "provider": "stripe",
            "operation": "billing_portal.sessions.create",
            "customer": str(customer_ref),
            "return_url": str(return_url),
            "secret_ref": config.secret_ref,
        },
        "side_effects": {"provider_called": False, "checkout_or_portal_called": False, "real_charge_possible": False},
        "created_at": _utc_now(),
        "idempotency_key": idempotency_key or plan_id,
    }
    return _assert_public_safe(plan)


def verify_billing_webhook_envelope(
    *,
    provider: str,
    mode: str,
    event_type: str,
    event_id: str,
    tenant_id: str,
    project_id: str,
    payload_sha256: str,
    signature_header_present: bool,
    webhook_secret_ref: str | None = None,
    livemode: bool | None = None,
) -> JsonDict:
    provider_name = _normalize_provider(provider)
    normalized_mode = _normalize_mode(mode)
    _validate_tenant_project(tenant_id, project_id)
    if not re.fullmatch(r"[a-fA-F0-9]{64}", str(payload_sha256)):
        raise BillingContractError("payload_sha256 must be a sha256 hex digest")
    live_event = bool(livemode) if livemode is not None else normalized_mode == "live"
    failures: list[JsonDict] = []
    if not signature_header_present:
        failures.append({"reason": "missing_signature_header"})
    if normalized_mode == "live" and not webhook_secret_ref:
        failures.append({"reason": "missing_live_webhook_secret_ref"})
    if normalized_mode == "test" and live_event:
        failures.append({"reason": "live_event_received_in_test_mode"})

    envelope = {
        "schema_version": BILLING_SCHEMA_VERSION,
        "plan_type": "webhook_envelope_verification",
        "provider": provider_name,
        "mode": normalized_mode,
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "event_type": str(event_type),
        "event_id": str(event_id),
        "payload_sha256": str(payload_sha256).lower(),
        "signature_header_present": bool(signature_header_present),
        "webhook_secret_ref": webhook_secret_ref,
        "verified": not failures,
        "failures": failures,
        "raw_payload_included": False,
        "secret_value_present": False,
        "created_at": _utc_now(),
    }
    return _assert_public_safe(envelope)


def billing_provider_manifest() -> JsonDict:
    return {
        "schema_version": BILLING_SCHEMA_VERSION,
        "providers": sorted(SUPPORTED_PROVIDERS),
        "modes": sorted(SUPPORTED_MODES),
        "currencies": sorted(SUPPORTED_CURRENCIES),
        "payment_methods": {provider: list(methods) for provider, methods in SUPPORTED_PAYMENT_METHODS.items()},
        "live_mode_guardrails": [
            "live mode requires live_mode_ack",
            "live mode requires secret_ref indirection",
            "raw provider secrets are rejected",
            "raw card numbers are rejected",
            "plans do not call providers until an executor with explicit credentials is wired",
        ],
    }


def _provider_checkout_request(config: BillingProviderConfig, price: BillingPrice, tenant_id: str, project_id: str, customer_ref: str, quantity: int) -> JsonDict:
    if config.provider == "stripe":
        return {
            "provider": "stripe",
            "operation": "checkout.sessions.create",
            "mode": "subscription" if price.interval else "payment",
            "customer": str(customer_ref),
            "line_items": [{"price_lookup_key": price.lookup_key, "quantity": int(quantity)}],
            "payment_method_types": list(config.allowed_payment_methods),
            "client_reference_id": f"{tenant_id}:{project_id}",
            "secret_ref": config.secret_ref,
            "webhook_secret_ref": config.webhook_secret_ref,
        }
    if config.provider == "wechat_pay":
        return {
            "provider": "wechat_pay",
            "operation": "hosted_checkout.prepay",
            "trade_type": "NATIVE",
            "customer": str(customer_ref),
            "amount": {"total": price.unit_amount_minor, "currency": price.currency.upper()},
            "description": price.lookup_key,
            "tenant_project_ref": f"{tenant_id}:{project_id}",
            "merchant_account_ref": config.account_ref,
            "secret_ref": config.secret_ref,
        }
    return {
        "provider": "alipay",
        "operation": "hosted_checkout.trade_page_pay",
        "customer": str(customer_ref),
        "total_amount": _minor_to_major(price.unit_amount_minor),
        "currency": price.currency.upper(),
        "subject": price.lookup_key,
        "tenant_project_ref": f"{tenant_id}:{project_id}",
        "merchant_account_ref": config.account_ref,
        "secret_ref": config.secret_ref,
    }


def _coerce_provider_config(value: BillingProviderConfig | Mapping[str, Any] | None) -> BillingProviderConfig:
    if value is None:
        return BillingProviderConfig(provider="stripe", mode="test", secret_ref="env:STRIPE_TEST_REF").normalized()
    if isinstance(value, BillingProviderConfig):
        return value.normalized()
    return BillingProviderConfig(
        provider=str(value.get("provider", "stripe")),
        mode=str(value.get("mode", "test")),
        secret_ref=value.get("secret_ref"),
        webhook_secret_ref=value.get("webhook_secret_ref"),
        account_ref=value.get("account_ref"),
        live_mode_ack=bool(value.get("live_mode_ack", False)),
        allowed_payment_methods=tuple(value.get("allowed_payment_methods") or ()),
    ).normalized()


def _coerce_price(value: BillingPrice | Mapping[str, Any]) -> BillingPrice:
    if isinstance(value, BillingPrice):
        price = value
    else:
        price = BillingPrice(
            lookup_key=str(value.get("lookup_key") or value.get("price_lookup_key") or "ashr_enterprise_monthly"),
            unit_amount_minor=int(value.get("unit_amount_minor", 0)),
            currency=str(value.get("currency", "usd")),
            interval=str(value.get("interval", "month")),
            metered=bool(value.get("metered", False)),
            included_units=int(value.get("included_units", 0)),
        )
    if not price.lookup_key or any(ch.isspace() for ch in price.lookup_key):
        raise BillingContractError("price lookup_key must be non-empty and space-free")
    if price.unit_amount_minor < 0:
        raise BillingContractError("unit_amount_minor must be >= 0")
    currency = price.currency.lower()
    if currency not in SUPPORTED_CURRENCIES:
        raise BillingContractError(f"unsupported currency: {price.currency}")
    return BillingPrice(
        lookup_key=price.lookup_key,
        unit_amount_minor=price.unit_amount_minor,
        currency=currency,
        interval=price.interval,
        metered=price.metered,
        included_units=price.included_units,
    )


def _validate_provider_config(config: BillingProviderConfig) -> None:
    if config.provider not in SUPPORTED_PROVIDERS:
        raise BillingContractError(f"unsupported billing provider: {config.provider}")
    if config.mode not in SUPPORTED_MODES:
        raise BillingContractError(f"unsupported billing mode: {config.mode}")
    for ref_name in ("secret_ref", "webhook_secret_ref", "account_ref"):
        value = getattr(config, ref_name)
        if value and _looks_like_raw_secret(str(value)):
            raise BillingContractError(f"{ref_name} must be an indirection, not a raw secret")
    allowed = set(SUPPORTED_PAYMENT_METHODS[config.provider])
    unknown = set(config.allowed_payment_methods) - allowed
    if unknown:
        raise BillingContractError(f"unsupported payment methods for {config.provider}: {sorted(unknown)}")
    if config.mode == "live":
        if not config.live_mode_ack:
            raise BillingContractError("live mode requires live_mode_ack=True")
        if not config.secret_ref:
            raise BillingContractError("live mode requires secret_ref indirection")


def _normalize_provider(provider: str) -> str:
    normalized = str(provider).strip().lower().replace("-", "_")
    aliases = {"stripe_checkout": "stripe", "wechat": "wechat_pay", "weixin": "wechat_pay", "alipay_plus": "alipay"}
    return aliases.get(normalized, normalized)


def _normalize_mode(mode: str) -> str:
    return str(mode).strip().lower()


def _validate_tenant_project(tenant_id: str, project_id: str) -> None:
    if not str(tenant_id).strip() or not str(project_id).strip():
        raise BillingContractError("tenant_id and project_id are required")


def _public_usage_rollup(value: Mapping[str, Any] | None, *, tenant_id: str, project_id: str) -> JsonDict:
    rollup = dict(value or {})
    _reject_sensitive_payload(rollup)
    return {
        "tenant_id": str(rollup.get("tenant_id") or tenant_id),
        "project_id": str(rollup.get("project_id") or project_id),
        "billing_period": rollup.get("billing_period"),
        "operation_totals": dict(rollup.get("operation_totals") or {}),
        "billable_units": int(rollup.get("billable_units") or 0),
    }


def _public_metadata(value: Mapping[str, Any] | None) -> JsonDict:
    metadata = dict(value or {})
    _reject_sensitive_payload(metadata)
    return {str(key): _jsonable_public(item) for key, item in metadata.items()}


def _jsonable_public(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable_public(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable_public(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _reject_sensitive_payload(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {"card", "card_number", "cvc", "cvv", "pan", "secret", "client_secret", "api_key", "authorization", "token"}:
                raise BillingContractError(f"sensitive billing field is not allowed at {path}.{key}")
            _reject_sensitive_payload(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_sensitive_payload(item, path=f"{path}[{index}]")
    elif isinstance(value, str):
        if _looks_like_raw_secret(value) or _looks_like_card_number(value):
            raise BillingContractError(f"sensitive billing value is not allowed at {path}")


def _looks_like_raw_secret(value: str) -> bool:
    lowered = value.lower()
    return bool(_SECRET_KEY_RE.search(value)) or lowered.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_", "whsec_", "bearer ", "basic "))


def _looks_like_card_number(value: str) -> bool:
    compact = re.sub(r"\D", "", value)
    return len(compact) >= 13 and len(compact) <= 19 and bool(_CARD_NUMBER_RE.search(value))


def _assert_public_safe(payload: JsonDict) -> JsonDict:
    encoded = json.dumps(payload, sort_keys=True, default=str)
    if _SECRET_KEY_RE.search(encoded) or "Bearer " in encoded or _looks_like_card_number(encoded):
        raise BillingContractError("billing payload failed public-safety scan")
    return payload


def _plan_id(*parts: Any) -> str:
    seed = "|".join(str(part) for part in parts if part is not None)
    return "billplan_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _minor_to_major(value: int) -> str:
    try:
        amount = (Decimal(value) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise BillingContractError("invalid minor amount") from exc
    return format(amount, "f")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


LEDGER_EVENT_TYPES = {
    "checkout_created",
    "invoice_paid",
    "refund_created",
    "subscription_canceled",
    "usage_reconciled",
}
PROVIDER_EVENT_TYPES: dict[str, str] = {
    "checkout.session.completed": "checkout_created",
    "checkout.session.async_payment_succeeded": "checkout_created",
    "invoice.paid": "invoice_paid",
    "charge.refunded": "refund_created",
    "refund.created": "refund_created",
    "customer.subscription.deleted": "subscription_canceled",
    "wechat_pay.transaction.success": "invoice_paid",
    "wechat_pay.refund.success": "refund_created",
    "alipay.trade.success": "invoice_paid",
    "alipay.trade.refund.success": "refund_created",
    "ashr.usage.reconciled": "usage_reconciled",
}


@dataclass(frozen=True)
class BillingLedgerEvent:
    tenant_id: str
    project_id: str
    event_type: str
    amount_minor: int = 0
    currency: str = "usd"
    provider: str | None = None
    mode: str = "test"
    provider_event_id: str | None = None
    customer_ref: str | None = None
    invoice_ref: str | None = None
    usage_units: int = 0
    metadata: Mapping[str, Any] | None = None
    ledger_event_id: str | None = None


class BillingLedger:
    """Append-only billing event ledger plus provider-webhook replay store."""

    def __init__(self) -> None:
        self.ledger_events: list[JsonDict] = []
        self.provider_events: dict[str, JsonDict] = {}
        self.billing_accounts: dict[str, JsonDict] = {}

    def upsert_billing_account(
        self,
        *,
        tenant_id: str,
        project_id: str,
        customer_ref: str,
        provider: str,
        mode: str = "test",
        account_ref: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        provider_name = _normalize_provider(provider)
        normalized_mode = _normalize_mode(mode)
        _validate_tenant_project(tenant_id, project_id)
        _reject_sensitive_payload({"customer_ref": customer_ref, "account_ref": account_ref, "metadata": metadata})
        key = _account_key(tenant_id, project_id, provider_name, normalized_mode, customer_ref)
        record = {
            "schema_version": BILLING_SCHEMA_VERSION,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "provider": provider_name,
            "mode": normalized_mode,
            "customer_ref": str(customer_ref),
            "account_ref": account_ref,
            "metadata": _public_metadata(metadata),
            "created_at": self.billing_accounts.get(key, {}).get("created_at") or _utc_now(),
            "updated_at": _utc_now(),
            "raw_secret_present": False,
            "raw_payload_included": False,
        }
        self.billing_accounts[key] = _assert_public_safe(record)
        return dict(record)

    def get_billing_account(self, *, tenant_id: str, project_id: str, provider: str, customer_ref: str, mode: str = "test") -> JsonDict:
        key = _account_key(tenant_id, project_id, _normalize_provider(provider), _normalize_mode(mode), customer_ref)
        record = self.billing_accounts.get(key)
        if not record:
            raise BillingContractError("billing account not found")
        return dict(record)

    def append_ledger_event(self, event: BillingLedgerEvent | Mapping[str, Any]) -> JsonDict:
        event_obj = _coerce_ledger_event(event)
        _validate_tenant_project(event_obj.tenant_id, event_obj.project_id)
        event_type = _normalize_ledger_event_type(event_obj.event_type)
        provider = _normalize_provider(event_obj.provider or "stripe")
        mode = _normalize_mode(event_obj.mode)
        currency = str(event_obj.currency).lower()
        if currency not in SUPPORTED_CURRENCIES:
            raise BillingContractError(f"unsupported currency: {event_obj.currency}")
        if event_obj.amount_minor < 0 and event_type not in {"refund_created"}:
            raise BillingContractError("negative amounts are only allowed for refunds")
        _reject_sensitive_payload({"customer_ref": event_obj.customer_ref, "invoice_ref": event_obj.invoice_ref, "metadata": event_obj.metadata})
        ledger_event_id = event_obj.ledger_event_id or _ledger_event_id(event_obj.tenant_id, event_obj.project_id, event_type, provider, mode, event_obj.provider_event_id, len(self.ledger_events))
        record = {
            "schema_version": BILLING_SCHEMA_VERSION,
            "ledger_event_id": ledger_event_id,
            "tenant_id": str(event_obj.tenant_id),
            "project_id": str(event_obj.project_id),
            "event_type": event_type,
            "provider": provider,
            "mode": mode,
            "provider_event_id": event_obj.provider_event_id,
            "customer_ref": event_obj.customer_ref,
            "invoice_ref": event_obj.invoice_ref,
            "amount_minor": int(event_obj.amount_minor),
            "currency": currency,
            "usage_units": int(event_obj.usage_units),
            "metadata": _public_metadata(event_obj.metadata),
            "raw_payload_included": False,
            "secret_value_present": False,
            "created_at": _utc_now(),
        }
        self.ledger_events.append(_assert_public_safe(record))
        return dict(record)

    def ingest_provider_webhook(
        self,
        *,
        envelope: Mapping[str, Any],
        customer_ref: str | None = None,
        amount_minor: int = 0,
        currency: str = "usd",
        invoice_ref: str | None = None,
        usage_units: int = 0,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        _reject_sensitive_payload({"customer_ref": customer_ref, "invoice_ref": invoice_ref, "metadata": metadata})
        if not bool(envelope.get("verified")):
            raise BillingContractError("cannot ingest unverified billing webhook envelope")
        provider = _normalize_provider(str(envelope.get("provider")))
        mode = _normalize_mode(str(envelope.get("mode")))
        tenant_id = str(envelope.get("tenant_id") or "")
        project_id = str(envelope.get("project_id") or "")
        event_id = str(envelope.get("event_id") or "")
        payload_sha256 = str(envelope.get("payload_sha256") or "").lower()
        event_type = str(envelope.get("event_type") or "")
        if not event_id:
            raise BillingContractError("provider event_id is required")
        if not re.fullmatch(r"[a-f0-9]{64}", payload_sha256):
            raise BillingContractError("provider payload_sha256 must be a sha256 hex digest")
        key = _provider_event_key(provider, mode, tenant_id, project_id, event_id)
        existing = self.provider_events.get(key)
        if existing:
            if existing["payload_sha256"] != payload_sha256:
                conflict = {**existing, "ingest_status": "conflict", "conflict_payload_sha256": payload_sha256, "ledger_mutation_count": 0}
                return _assert_public_safe(conflict)
            duplicate = {**existing, "ingest_status": "duplicate", "ledger_mutation_count": 0}
            return _assert_public_safe(duplicate)

        ledger_event_type = PROVIDER_EVENT_TYPES.get(event_type, "usage_reconciled" if event_type.startswith("ashr.usage") else "checkout_created")
        ledger = self.append_ledger_event(
            BillingLedgerEvent(
                tenant_id=tenant_id,
                project_id=project_id,
                event_type=ledger_event_type,
                provider=provider,
                mode=mode,
                provider_event_id=event_id,
                customer_ref=customer_ref,
                invoice_ref=invoice_ref,
                amount_minor=amount_minor,
                currency=currency,
                usage_units=usage_units,
                metadata=metadata,
            )
        )
        provider_record = {
            "schema_version": BILLING_SCHEMA_VERSION,
            "provider_event_key": key,
            "provider": provider,
            "mode": mode,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "event_id": event_id,
            "event_type": event_type,
            "payload_sha256": payload_sha256,
            "ledger_event_id": ledger["ledger_event_id"],
            "ledger_event_type": ledger["event_type"],
            "ingest_status": "accepted",
            "ledger_mutation_count": 1,
            "raw_payload_included": False,
            "secret_value_present": False,
            "created_at": _utc_now(),
        }
        self.provider_events[key] = _assert_public_safe(provider_record)
        return dict(provider_record)

    def reconcile_usage_rollup(self, usage_rollup: Mapping[str, Any], *, provider: str = "stripe", mode: str = "test", customer_ref: str | None = None, billing_period: str | None = None) -> JsonDict:
        tenant_id = str(usage_rollup.get("tenant_id") or "")
        project_id = str(usage_rollup.get("project_id") or "")
        billable_units = int(usage_rollup.get("billable_units") or 0)
        period = str(billing_period or usage_rollup.get("billing_period") or "unperiodized")
        return self.append_ledger_event(
            BillingLedgerEvent(
                tenant_id=tenant_id,
                project_id=project_id,
                event_type="usage_reconciled",
                provider=provider,
                mode=mode,
                provider_event_id=f"usage:{tenant_id}:{project_id}:{period}",
                customer_ref=customer_ref,
                usage_units=billable_units,
                amount_minor=0,
                currency="usd",
                metadata={"billing_period": period, "operation_totals": usage_rollup.get("operation_totals") or {}},
            )
        )

    def public_ledger(self, *, tenant_id: str, project_id: str) -> JsonDict:
        events = [dict(item) for item in self.ledger_events if item["tenant_id"] == str(tenant_id) and item["project_id"] == str(project_id)]
        totals: dict[str, int] = {}
        usage_units = 0
        for event in events:
            currency = str(event.get("currency") or "usd")
            totals[currency] = totals.get(currency, 0) + int(event.get("amount_minor") or 0)
            usage_units += int(event.get("usage_units") or 0)
        accounts = [dict(item) for item in self.billing_accounts.values() if item["tenant_id"] == str(tenant_id) and item["project_id"] == str(project_id)]
        provider_events = [dict(item) for item in self.provider_events.values() if item["tenant_id"] == str(tenant_id) and item["project_id"] == str(project_id)]
        snapshot = {
            "schema_version": BILLING_SCHEMA_VERSION,
            "tenant_id": str(tenant_id),
            "project_id": str(project_id),
            "ledger_events": events,
            "provider_events": provider_events,
            "billing_accounts": accounts,
            "totals_by_currency_minor": totals,
            "usage_units": usage_units,
            "ledger_event_count": len(events),
            "provider_event_count": len(provider_events),
            "raw_payload_included": False,
            "secret_value_present": False,
        }
        return _assert_public_safe(snapshot)


def billing_evidence_snapshot(*, ledger: BillingLedger, tenant_id: str, project_id: str) -> JsonDict:
    snapshot = ledger.public_ledger(tenant_id=tenant_id, project_id=project_id)
    body = json.dumps(snapshot, sort_keys=True, default=str).encode("utf-8")
    return {
        "schema_version": "ashr.clone.billing_evidence_snapshot.v1",
        "tenant_id": str(tenant_id),
        "project_id": str(project_id),
        "billing_snapshot_sha256": hashlib.sha256(body).hexdigest(),
        "ledger_event_count": snapshot["ledger_event_count"],
        "provider_event_count": snapshot["provider_event_count"],
        "totals_by_currency_minor": dict(snapshot["totals_by_currency_minor"]),
        "usage_units": snapshot["usage_units"],
        "raw_payload_included": False,
        "secret_value_present": False,
    }


def _coerce_ledger_event(value: BillingLedgerEvent | Mapping[str, Any]) -> BillingLedgerEvent:
    if isinstance(value, BillingLedgerEvent):
        return value
    return BillingLedgerEvent(
        tenant_id=str(value.get("tenant_id") or ""),
        project_id=str(value.get("project_id") or ""),
        event_type=str(value.get("event_type") or ""),
        amount_minor=int(value.get("amount_minor") or 0),
        currency=str(value.get("currency") or "usd"),
        provider=value.get("provider"),
        mode=str(value.get("mode") or "test"),
        provider_event_id=value.get("provider_event_id"),
        customer_ref=value.get("customer_ref"),
        invoice_ref=value.get("invoice_ref"),
        usage_units=int(value.get("usage_units") or 0),
        metadata=value.get("metadata") if isinstance(value.get("metadata"), Mapping) else None,
        ledger_event_id=value.get("ledger_event_id"),
    )


def _normalize_ledger_event_type(value: str) -> str:
    normalized = str(value).strip().lower().replace(".", "_").replace("-", "_")
    if normalized not in LEDGER_EVENT_TYPES:
        raise BillingContractError(f"unsupported billing ledger event type: {value}")
    return normalized


def _provider_event_key(provider: str, mode: str, tenant_id: str, project_id: str, event_id: str) -> str:
    return ":".join([str(provider), str(mode), str(tenant_id), str(project_id), str(event_id)])


def _account_key(tenant_id: str, project_id: str, provider: str, mode: str, customer_ref: str) -> str:
    return ":".join([str(tenant_id), str(project_id), str(provider), str(mode), str(customer_ref)])


def _ledger_event_id(*parts: Any) -> str:
    return "ble_" + hashlib.sha256("|".join(str(part) for part in parts if part is not None).encode("utf-8")).hexdigest()[:24]
