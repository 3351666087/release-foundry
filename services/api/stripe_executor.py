"""Stripe test-mode execution boundary for hosted Checkout and Billing Portal.

The module deliberately depends on an injected Stripe facade. Importing it
never imports the Stripe SDK and never performs network I/O. Secrets may only
be resolved from ``env:NAME`` references and are never included in public
results or exception messages.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import re
import threading
import time
from typing import Any, Callable, Mapping, MutableMapping, Protocol
from urllib.parse import urlparse

from services.api.payment_providers import (
    PAYMENT_PROVIDER_SCHEMA_VERSION,
    SignatureVerificationRequest,
    SignatureVerificationResult,
)

JsonDict = dict[str, Any]

_ENV_REF_RE = re.compile(r"^env:([A-Z][A-Z0-9_]{2,127})$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,255}$")
_CHECKOUT_ID_RE = re.compile(r"^cs_test_[A-Za-z0-9_]+$")
_PORTAL_ID_RE = re.compile(r"^bps_[A-Za-z0-9_]+$")
_EVENT_ID_RE = re.compile(r"^evt_[A-Za-z0-9_]+$")
_SENSITIVE_KEY_RE = re.compile(
    r"(?:secret|credential|api_key|signature|raw|payload|card|pan|cvc|cvv|"
    r"expiry|payment_method)",
    re.IGNORECASE,
)


class StripeExecutorError(ValueError):
    """Raised when a plan cannot safely cross the Stripe execution boundary."""


class StripeIdempotencyConflict(StripeExecutorError):
    """Raised when an idempotency key is reused for a different request."""


class StripeSDKFacade(Protocol):
    """Narrow SDK facade implemented by the production integration layer."""

    def create_checkout_session(
        self,
        *,
        api_key: str,
        params: Mapping[str, Any],
        idempotency_key: str,
        stripe_account: str | None = None,
    ) -> Any:
        ...

    def create_billing_portal_session(
        self,
        *,
        api_key: str,
        params: Mapping[str, Any],
        idempotency_key: str,
        stripe_account: str | None = None,
    ) -> Any:
        ...


class StripeWebhookSDKFacade(Protocol):
    """Optional Stripe SDK facade used to verify and decode webhook events."""

    def construct_webhook_event(
        self,
        *,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> Any:
        ...


@dataclass(frozen=True)
class EnvSecretResolver:
    """Resolve only explicit environment references without exposing values."""

    environ: Mapping[str, str] | None = None

    def resolve(self, secret_ref: str) -> str:
        match = _ENV_REF_RE.fullmatch(str(secret_ref))
        if match is None:
            raise StripeExecutorError("Stripe secrets must use an env:NAME reference")
        name = match.group(1)
        source = os.environ if self.environ is None else self.environ
        value = source.get(name)
        if not value:
            raise StripeExecutorError(f"required Stripe environment variable is absent: {name}")
        return value


class StripeTestModeExecutor:
    """Execute validated Stripe hosted-session plans through an injected facade."""

    def __init__(
        self,
        *,
        facade: StripeSDKFacade,
        secret_resolver: EnvSecretResolver | None = None,
        idempotency_store: MutableMapping[str, tuple[str, JsonDict]] | None = None,
    ):
        self._facade = facade
        self._secrets = secret_resolver or EnvSecretResolver()
        self._idempotency = idempotency_store if idempotency_store is not None else {}
        self._lock = threading.RLock()

    def execute(self, plan: Mapping[str, Any]) -> JsonDict:
        normalized = _validate_execution_plan(plan)
        idempotency_key = normalized["idempotency_key"]
        fingerprint = normalized["fingerprint"]

        with self._lock:
            prior = self._idempotency.get(idempotency_key)
            if prior is not None:
                prior_fingerprint, prior_result = prior
                if not hmac.compare_digest(prior_fingerprint, fingerprint):
                    raise StripeIdempotencyConflict(
                        "Stripe idempotency key was reused with a different request fingerprint"
                    )
                return dict(prior_result)

            api_key = self._secrets.resolve(normalized["credential_ref"])
            if not api_key.startswith("sk_test_"):
                raise StripeExecutorError("Stripe executor requires a test-mode secret")

            if normalized["operation"] == "checkout.sessions.create":
                provider_result = self._facade.create_checkout_session(
                    api_key=api_key,
                    params=normalized["params"],
                    idempotency_key=idempotency_key,
                    stripe_account=normalized["stripe_account"],
                )
                public_result = _public_session_result(
                    provider_result,
                    object_type="checkout.session",
                    id_pattern=_CHECKOUT_ID_RE,
                )
            else:
                provider_result = self._facade.create_billing_portal_session(
                    api_key=api_key,
                    params=normalized["params"],
                    idempotency_key=idempotency_key,
                    stripe_account=normalized["stripe_account"],
                )
                public_result = _public_session_result(
                    provider_result,
                    object_type="billing_portal.session",
                    id_pattern=_PORTAL_ID_RE,
                )

            self._idempotency[idempotency_key] = (fingerprint, dict(public_result))
            return dict(public_result)


class StripeWebhookVerifierAdapter:
    """Verify Stripe test webhooks through an SDK facade or standard-library HMAC."""

    def __init__(
        self,
        *,
        secret_resolver: EnvSecretResolver | None = None,
        facade: StripeWebhookSDKFacade | None = None,
        tolerance_seconds: int = 300,
        clock: Callable[[], float] = time.time,
    ):
        if int(tolerance_seconds) < 0:
            raise StripeExecutorError("webhook tolerance_seconds must be non-negative")
        self._secrets = secret_resolver or EnvSecretResolver()
        self._facade = facade
        self._tolerance_seconds = int(tolerance_seconds)
        self._clock = clock

    def verify(self, request: SignatureVerificationRequest) -> SignatureVerificationResult:
        if request.provider != "stripe":
            raise StripeExecutorError("Stripe webhook verifier received another provider")
        if request.mode != "test" or request.expected_livemode:
            raise StripeExecutorError("Stripe webhook verifier rejects live mode")
        secret = self._secrets.resolve(request.verification_key_ref)
        if not secret.startswith("whsec_"):
            raise StripeExecutorError("Stripe webhook verifier requires a webhook secret")
        signature = _header(request.headers, "stripe-signature")
        if not signature:
            return SignatureVerificationResult(
                verified=False,
                reason_codes=("missing_signature_header",),
            )

        try:
            if self._facade is not None:
                event = self._facade.construct_webhook_event(
                    payload=request.raw_body,
                    signature=signature,
                    secret=secret,
                )
            else:
                _verify_standard_signature(
                    payload=request.raw_body,
                    signature=signature,
                    secret=secret,
                    tolerance_seconds=self._tolerance_seconds,
                    now=int(self._clock()),
                )
                event = json.loads(request.raw_body.decode("utf-8"))
            return _map_verified_event(event)
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError):
            return SignatureVerificationResult(
                verified=False,
                reason_codes=("signature_verification_failed",),
            )
        except Exception:
            # Provider SDK exceptions are intentionally collapsed: exception
            # messages can contain signatures, payload fragments, or secrets.
            return SignatureVerificationResult(
                verified=False,
                reason_codes=("signature_verification_failed",),
            )


def _validate_execution_plan(plan: Mapping[str, Any]) -> JsonDict:
    if not isinstance(plan, Mapping):
        raise StripeExecutorError("Stripe execution plan must be a mapping")
    required = {
        "schema_version",
        "plan_type",
        "provider",
        "hosted_surface",
        "tenant_id",
        "project_id",
        "mode_gate",
        "credential_ref",
        "verification_key_ref",
        "account_ref",
        "idempotency",
        "request_shape",
        "execution_hook",
        "side_effects",
        "raw_secret_present",
        "raw_card_data_present",
    }
    if set(plan) != required:
        raise StripeExecutorError("Stripe execution plan does not match the strict v1 schema")
    if plan["schema_version"] != PAYMENT_PROVIDER_SCHEMA_VERSION:
        raise StripeExecutorError("unsupported Stripe payment plan schema")
    if plan["plan_type"] != "hosted_payment" or plan["provider"] != "stripe":
        raise StripeExecutorError("executor accepts only Stripe hosted-payment plans")
    mode_gate = plan["mode_gate"]
    if not isinstance(mode_gate, Mapping) or mode_gate.get("mode") != "test":
        raise StripeExecutorError("Stripe executor rejects live mode")
    if mode_gate.get("live_mode_ack") or mode_gate.get("live_execution_gate_ref") is not None:
        raise StripeExecutorError("test execution plan contains a live-mode gate")
    if plan["raw_secret_present"] is not False or plan["raw_card_data_present"] is not False:
        raise StripeExecutorError("Stripe execution plan advertises sensitive payment material")

    tenant_id = _required_text("tenant_id", plan["tenant_id"])
    project_id = _required_text("project_id", plan["project_id"])
    credential_ref = str(plan["credential_ref"])
    if _ENV_REF_RE.fullmatch(credential_ref) is None:
        raise StripeExecutorError("Stripe credential_ref must use env:NAME")

    idempotency = plan["idempotency"]
    if not isinstance(idempotency, Mapping) or set(idempotency) != {
        "required",
        "key",
        "request_fingerprint_sha256",
        "reuse_requires_identical_fingerprint",
    }:
        raise StripeExecutorError("Stripe idempotency block does not match the strict schema")
    idempotency_key = str(idempotency.get("key") or "")
    fingerprint = str(idempotency.get("request_fingerprint_sha256") or "")
    if (
        idempotency.get("required") is not True
        or idempotency.get("reuse_requires_identical_fingerprint") is not True
        or _IDEMPOTENCY_RE.fullmatch(idempotency_key) is None
        or _DIGEST_RE.fullmatch(fingerprint) is None
    ):
        raise StripeExecutorError("invalid Stripe idempotency contract")

    request_shape = plan["request_shape"]
    if not isinstance(request_shape, Mapping):
        raise StripeExecutorError("Stripe request_shape must be a mapping")
    expected_fingerprint = _plan_fingerprint(
        tenant_id=tenant_id,
        project_id=project_id,
        idempotency_key=idempotency_key,
        request_shape=request_shape,
    )
    if not hmac.compare_digest(fingerprint, expected_fingerprint):
        raise StripeExecutorError("Stripe plan fingerprint mismatch")

    operation = str(request_shape.get("operation") or "")
    surface = str(plan["hosted_surface"])
    if operation == "checkout.sessions.create" and surface == "stripe_checkout":
        params = _checkout_params(request_shape)
    elif (
        operation == "billing_portal.sessions.create"
        and surface == "stripe_billing_portal"
    ):
        params = _portal_params(request_shape)
    else:
        raise StripeExecutorError("unsupported Stripe hosted operation")

    return {
        "credential_ref": credential_ref,
        "idempotency_key": idempotency_key,
        "fingerprint": fingerprint,
        "operation": operation,
        "params": params,
        "stripe_account": _optional_provider_id(
            plan["account_ref"], prefix="acct_", kind="account"
        ),
    }


def _checkout_params(request: Mapping[str, Any]) -> JsonDict:
    expected = {
        "operation",
        "checkout_mode",
        "customer_ref",
        "price_ref",
        "quantity",
        "success_url",
        "cancel_url",
        "metadata",
    }
    if set(request) != expected:
        raise StripeExecutorError("Stripe Checkout request does not match the strict schema")
    quantity = request["quantity"]
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise StripeExecutorError("Stripe Checkout quantity must be a positive integer")
    checkout_mode = str(request["checkout_mode"]).strip().lower()
    if checkout_mode not in {"payment", "subscription"}:
        raise StripeExecutorError(
            "Stripe Checkout mode must be payment or subscription"
        )
    metadata = _public_metadata(request["metadata"])
    return {
        "customer": _provider_id(request["customer_ref"], prefix="cus_", kind="customer"),
        "line_items": [
            {
                "price": _provider_id(request["price_ref"], prefix="price_", kind="price"),
                "quantity": quantity,
            }
        ],
        "mode": checkout_mode,
        "success_url": _https_url("success_url", request["success_url"]),
        "cancel_url": _https_url("cancel_url", request["cancel_url"]),
        "metadata": metadata,
    }


def _portal_params(request: Mapping[str, Any]) -> JsonDict:
    if set(request) != {"operation", "customer_ref", "return_url"}:
        raise StripeExecutorError("Stripe Portal request does not match the strict schema")
    return {
        "customer": _provider_id(request["customer_ref"], prefix="cus_", kind="customer"),
        "return_url": _https_url("return_url", request["return_url"]),
    }


def _plan_fingerprint(
    *,
    tenant_id: str,
    project_id: str,
    idempotency_key: str,
    request_shape: Mapping[str, Any],
) -> str:
    source = {
        "provider": "stripe",
        "mode": "test",
        "tenant_id": tenant_id,
        "project_id": project_id,
        "idempotency_key": idempotency_key,
        "request_shape": request_shape,
    }
    return hashlib.sha256(
        json.dumps(source, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _public_session_result(
    provider_result: Any,
    *,
    object_type: str,
    id_pattern: re.Pattern[str],
) -> JsonDict:
    session_id = str(_provider_value(provider_result, "id") or "")
    url = str(_provider_value(provider_result, "url") or "")
    livemode = _provider_value(provider_result, "livemode")
    provider_object = _provider_value(provider_result, "object")
    if id_pattern.fullmatch(session_id) is None:
        raise StripeExecutorError("Stripe returned an invalid test session identifier")
    if livemode is not False:
        raise StripeExecutorError("Stripe returned a live-mode object to the test executor")
    if provider_object not in (None, object_type):
        raise StripeExecutorError("Stripe returned an unexpected hosted object type")
    _stripe_hosted_url(url)
    result = {
        "mode": "test",
        "object_ref": f"provider-ref:stripe/test/{object_type}/{session_id}",
        "session_id": session_id,
        "url": url,
    }
    if set(result) != {
        "mode",
        "object_ref",
        "session_id",
        "url",
    }:
        raise AssertionError("public Stripe result schema changed unexpectedly")
    return result


def _map_verified_event(event: Any) -> SignatureVerificationResult:
    event_id = str(_provider_value(event, "id") or "")
    event_type = str(_provider_value(event, "type") or "")
    livemode = _provider_value(event, "livemode")
    if _EVENT_ID_RE.fullmatch(event_id) is None or not event_type:
        return SignatureVerificationResult(
            verified=False,
            reason_codes=("invalid_event_shape",),
        )
    if livemode is not False:
        return SignatureVerificationResult(
            verified=False,
            event_id_ref=f"provider-ref:stripe/test/event/{event_id}",
            event_type=event_type,
            livemode=bool(livemode),
            reason_codes=("provider_mode_mismatch",),
        )
    return SignatureVerificationResult(
        verified=True,
        event_id_ref=f"provider-ref:stripe/test/event/{event_id}",
        event_type=event_type,
        livemode=False,
    )


def _verify_standard_signature(
    *,
    payload: bytes,
    signature: str,
    secret: str,
    tolerance_seconds: int,
    now: int,
) -> None:
    values: dict[str, list[str]] = {}
    for item in signature.split(","):
        name, separator, value = item.strip().partition("=")
        if separator:
            values.setdefault(name, []).append(value)
    timestamps = values.get("t", [])
    signatures = values.get("v1", [])
    if len(timestamps) != 1 or not signatures:
        raise ValueError("invalid Stripe signature shape")
    timestamp = int(timestamps[0])
    if tolerance_seconds and abs(now - timestamp) > tolerance_seconds:
        raise ValueError("Stripe signature timestamp is outside tolerance")
    signed_payload = str(timestamp).encode("ascii") + b"." + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise ValueError("Stripe signature mismatch")


def _provider_value(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _provider_id(value: Any, *, prefix: str, kind: str) -> str:
    text = str(value or "")
    marker = f"provider-ref:stripe/test/{kind}/"
    if not text.startswith(marker):
        raise StripeExecutorError(f"Stripe {kind}_ref must be a test provider reference")
    provider_id = text[len(marker) :]
    if "/" in provider_id or not provider_id.startswith(prefix):
        raise StripeExecutorError(f"Stripe {kind}_ref contains an invalid provider id")
    return provider_id


def _optional_provider_id(value: Any, *, prefix: str, kind: str) -> str | None:
    if value is None:
        return None
    return _provider_id(value, prefix=prefix, kind=kind)


def _public_metadata(value: Any) -> JsonDict:
    if not isinstance(value, Mapping):
        raise StripeExecutorError("Stripe metadata must be a mapping")
    result: JsonDict = {}
    for key, item in value.items():
        name = str(key)
        if not name or _SENSITIVE_KEY_RE.search(name):
            raise StripeExecutorError("Stripe metadata contains a sensitive field")
        if isinstance(item, (Mapping, list, tuple, set, bytes, bytearray)):
            raise StripeExecutorError("Stripe metadata values must be public-safe scalars")
        result[name] = item
    return result


def _required_text(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise StripeExecutorError(f"{name} is required")
    return text


def _https_url(name: str, value: Any) -> str:
    text = str(value or "")
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise StripeExecutorError(f"Stripe {name} must be HTTPS")
    return text


def _stripe_hosted_url(value: str) -> None:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        hostname == "stripe.com" or hostname.endswith(".stripe.com")
    ):
        raise StripeExecutorError("Stripe returned a non-hosted session URL")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    expected = name.lower()
    for key, value in headers.items():
        if str(key).lower() == expected:
            return str(value)
    return None
