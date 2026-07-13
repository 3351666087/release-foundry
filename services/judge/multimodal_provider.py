"""Provider-neutral multimodal invocation and conformance receipts for A2."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable
from urllib import error, request

from .result_persistence import stable_hash


CONFORMANCE_SCHEMA_VERSION = "a2.provider_conformance_receipt.v1"
SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg"})
RETRY_CLASSES = frozenset({"parse", "transport"})
PARSED_RESPONSE_SCHEMA_VERSION = "a2.parsed_multimodal_response.v1"
TRANSPORT_RECEIPT_SCHEMA_VERSION = "a2.provider_transport_receipt.v1"
RESPONSE_DURATION_RECEIPT_SCHEMA_VERSION = "a2.provider_response_duration_receipt.v1"
REQUEST_COUNT_RECEIPT_SCHEMA_VERSION = "a2.provider_request_count_receipt.v1"
USAGE_COST_RECEIPT_SCHEMA_VERSION = "a2.provider_usage_cost_receipt.v1"
PRICING_POLICY_SCHEMA_VERSION = "a2.provider_pricing_policy.v1"
CANCELLATION_HANDLE_RECEIPT_SCHEMA_VERSION = (
    "a2.provider_cancellation_handle_receipt.v1"
)


@runtime_checkable
class ProviderCancellationHandle(Protocol):
    """Optional adapter handle; acknowledgement is not proof of remote abort."""

    def cancel(self) -> bool: ...


@dataclass(frozen=True)
class ProviderCancellationHandleReceipt:
    """Public-safe record of one bounded cancellation request."""

    requested: bool
    supported: bool
    acknowledged: bool
    enforcement: str
    schema_version: str = CANCELLATION_HANDLE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CANCELLATION_HANDLE_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported provider cancellation handle receipt version")
        if self.acknowledged and not (self.requested and self.supported):
            raise ValueError(
                "cancellation acknowledgement requires a supported request"
            )
        if self.enforcement not in {
            "not_requested",
            "unsupported",
            "adapter_acknowledged",
            "adapter_rejected",
        }:
            raise ValueError("unsupported cancellation enforcement")
        expected = (
            "not_requested"
            if not self.requested
            else "unsupported"
            if not self.supported
            else "adapter_acknowledged"
            if self.acknowledged
            else "adapter_rejected"
        )
        if self.enforcement != expected:
            raise ValueError("cancellation enforcement contradicts receipt state")

    def public_receipt(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "requested": self.requested,
            "supported": self.supported,
            "acknowledged": self.acknowledged,
            "enforcement": self.enforcement,
            "remote_request_termination_proven": False,
            "raw_provider_state_included": False,
            "release_authority": False,
            "public_safe": True,
        }


def request_provider_cancellation(
    handle: ProviderCancellationHandle | None,
) -> dict[str, Any]:
    """Request cancellation once and fail closed without leaking adapter state."""

    if handle is None or not isinstance(handle, ProviderCancellationHandle):
        return ProviderCancellationHandleReceipt(
            requested=True,
            supported=False,
            acknowledged=False,
            enforcement="unsupported",
        ).public_receipt()
    try:
        acknowledged = handle.cancel() is True
    except Exception:
        acknowledged = False
    return ProviderCancellationHandleReceipt(
        requested=True,
        supported=True,
        acknowledged=acknowledged,
        enforcement=(
            "adapter_acknowledged" if acknowledged else "adapter_rejected"
        ),
    ).public_receipt()


@dataclass(frozen=True)
class ProviderTransportReceipt:
    """Public-safe provider transport classification without response bodies."""

    schema_version: str
    error_class: str
    http_status_class: str = ""
    response_body_retained: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != TRANSPORT_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported provider transport receipt version")
        if not self.error_class:
            raise ValueError("provider transport error class must not be empty")
        if self.http_status_class not in {"", "4xx", "5xx"}:
            raise ValueError("unsupported provider HTTP status class")
        if self.response_body_retained:
            raise ValueError("provider response body must not be retained")

    def public_receipt(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "error_class_hash": stable_hash(self.error_class),
            "http_status_class": self.http_status_class,
            "response_body_retained": False,
        }


class ClassifiedProviderTransportError(RuntimeError):
    """Provider-neutral fail-closed exception carrying only a safe receipt."""

    def __init__(self, receipt: ProviderTransportReceipt) -> None:
        super().__init__(receipt.error_class)
        self.receipt = receipt

    @property
    def error_class(self) -> str:
        return self.receipt.error_class

    @property
    def http_status_class(self) -> str:
        return self.receipt.http_status_class


def classified_transport_error(
    error_class: str, http_status_class: str = ""
) -> ClassifiedProviderTransportError:
    return ClassifiedProviderTransportError(
        ProviderTransportReceipt(
            schema_version=TRANSPORT_RECEIPT_SCHEMA_VERSION,
            error_class=error_class,
            http_status_class=http_status_class,
        )
    )


@dataclass(frozen=True)
class ProviderResponseDurationReceipt:
    """Public-safe duration projection with explicit measurement provenance."""

    wall_seconds: float
    provider_seconds: float | None = None
    provider_source: str = ""
    schema_version: str = RESPONSE_DURATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RESPONSE_DURATION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported provider response duration receipt version")
        if self.wall_seconds < 0:
            raise ValueError("wall duration cannot be negative")
        if self.provider_seconds is not None and self.provider_seconds < 0:
            raise ValueError("provider duration cannot be negative")
        if (self.provider_seconds is None) != (self.provider_source == ""):
            raise ValueError("provider duration and source must be present together")

    def public_receipt(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "wall_seconds": round(self.wall_seconds, 6),
            "provider_seconds": (
                round(self.provider_seconds, 6)
                if self.provider_seconds is not None
                else None
            ),
            "provider_source": self.provider_source,
            "effective_seconds": round(
                self.provider_seconds
                if self.provider_seconds is not None
                else self.wall_seconds,
                6,
            ),
            "effective_source": (
                "provider_native"
                if self.provider_seconds is not None
                else "wall_clock"
            ),
            "release_authority": False,
            "public_safe": True,
        }


@dataclass(frozen=True)
class ProviderRequestCountReceipt:
    """Provider-neutral, public-safe accounting for attempted network requests."""

    attempted: int
    completed: int
    failed: int
    maximum_allowed: int
    schema_version: str = REQUEST_COUNT_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REQUEST_COUNT_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported provider request count receipt version")
        if min(self.attempted, self.completed, self.failed) < 0:
            raise ValueError("request counts cannot be negative")
        if self.maximum_allowed < 1:
            raise ValueError("maximum request count must be positive")
        if self.completed + self.failed != self.attempted:
            raise ValueError("completed plus failed requests must equal attempted")
        if self.attempted > self.maximum_allowed:
            raise ValueError("attempted requests exceed the configured maximum")

    def public_receipt(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attempted": self.attempted,
            "completed": self.completed,
            "failed": self.failed,
            "maximum_allowed": self.maximum_allowed,
            "budget_exhausted": self.attempted >= self.maximum_allowed,
            "release_authority": False,
            "public_safe": True,
        }


@dataclass(frozen=True)
class ProviderPricingPolicy:
    """Versioned public-safe pricing provenance; source locations stay hashed."""

    provider_id: str
    model_id: str
    input_usd_per_million_tokens: float
    output_usd_per_million_tokens: float
    effective_at: str
    retrieved_at: str
    source_class: str
    source_uri_hash: str
    schema_version: str = PRICING_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PRICING_POLICY_SCHEMA_VERSION:
            raise ValueError("unsupported provider pricing policy version")
        if not all(
            (
                self.provider_id,
                self.model_id,
                self.effective_at,
                self.retrieved_at,
                self.source_class,
            )
        ):
            raise ValueError("provider pricing policy fields must not be empty")
        if min(
            self.input_usd_per_million_tokens,
            self.output_usd_per_million_tokens,
        ) < 0:
            raise ValueError("provider pricing rates cannot be negative")
        if not (
            self.source_uri_hash.startswith("sha256:")
            and len(self.source_uri_hash) == 71
        ):
            raise ValueError("provider pricing source URI must be hashed")

    def public_policy(self) -> dict[str, Any]:
        value = {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "currency": "USD",
            "input_usd_per_million_tokens": self.input_usd_per_million_tokens,
            "output_usd_per_million_tokens": self.output_usd_per_million_tokens,
            "effective_at": self.effective_at,
            "retrieved_at": self.retrieved_at,
            "source_class": self.source_class,
            "source_uri_hash": self.source_uri_hash,
            "release_authority": False,
            "public_safe": True,
        }
        return {**value, "content_hash": stable_hash(value)}


@dataclass(frozen=True)
class ProviderUsageCostReceipt:
    """Bounded token/cost projection without retaining provider payloads."""

    prompt_tokens: int
    completion_tokens: int
    input_usd_per_million_tokens: float | None
    output_usd_per_million_tokens: float | None
    maximum_estimated_cost_usd: float
    usage_complete: bool = True
    pricing_policy: Mapping[str, Any] | None = None
    schema_version: str = USAGE_COST_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != USAGE_COST_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported provider usage cost receipt version")
        if min(self.prompt_tokens, self.completion_tokens) < 0:
            raise ValueError("usage tokens cannot be negative")
        configured_rates = (
            self.input_usd_per_million_tokens,
            self.output_usd_per_million_tokens,
        )
        if any(value is not None and value < 0 for value in configured_rates):
            raise ValueError("cost values cannot be negative")
        if self.maximum_estimated_cost_usd < 0:
            raise ValueError("cost values cannot be negative")
        if self.pricing_policy is not None:
            policy = dict(self.pricing_policy)
            content_hash = policy.pop("content_hash", "")
            if content_hash != stable_hash(policy):
                raise ValueError("provider pricing policy content hash mismatch")
            if (
                policy.get("schema_version") != PRICING_POLICY_SCHEMA_VERSION
                or policy.get("input_usd_per_million_tokens")
                != self.input_usd_per_million_tokens
                or policy.get("output_usd_per_million_tokens")
                != self.output_usd_per_million_tokens
            ):
                raise ValueError("provider pricing policy does not bind receipt rates")

    @property
    def pricing_configured(self) -> bool:
        return (
            self.input_usd_per_million_tokens is not None
            and self.output_usd_per_million_tokens is not None
        )

    @property
    def estimated_cost_usd(self) -> float | None:
        if not self.pricing_configured or not self.usage_complete:
            return None
        assert self.input_usd_per_million_tokens is not None
        assert self.output_usd_per_million_tokens is not None
        return (
            self.prompt_tokens * self.input_usd_per_million_tokens
            + self.completion_tokens * self.output_usd_per_million_tokens
        ) / 1_000_000

    def public_receipt(self) -> dict[str, Any]:
        projected = self.estimated_cost_usd
        estimated = round(projected, 8) if projected is not None else None
        policy = dict(self.pricing_policy or {})
        return {
            "schema_version": self.schema_version,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "usage_accounting_state": (
                "complete" if self.usage_complete else "missing_or_invalid"
            ),
            "pricing_state": (
                "configured" if self.pricing_configured else "unavailable"
            ),
            "pricing_policy_version": policy.get("schema_version", ""),
            "pricing_policy_hash": policy.get("content_hash", ""),
            "pricing_effective_at": policy.get("effective_at", ""),
            "pricing_retrieved_at": policy.get("retrieved_at", ""),
            "pricing_source_hash": policy.get("source_uri_hash", ""),
            "input_usd_per_million_tokens": self.input_usd_per_million_tokens,
            "output_usd_per_million_tokens": self.output_usd_per_million_tokens,
            "estimated_cost_usd": estimated,
            "maximum_estimated_cost_usd": self.maximum_estimated_cost_usd,
            "within_cost_budget": (
                estimated <= self.maximum_estimated_cost_usd
                if estimated is not None
                else False
            ),
            "raw_payload_included": False,
            "release_authority": False,
            "public_safe": True,
        }


@dataclass(frozen=True)
class ParseRetryPolicy:
    max_retries: int = 0

    def should_retry(self, parse_state: str, retries_used: int) -> bool:
        return (
            retries_used < self.max_retries
            and parse_state
            in {"empty_response", "nonempty_invalid_json", "invalid_semantics"}
        )


@dataclass(frozen=True)
class TransportRetryPolicy:
    max_retries: int = 0

    def should_retry(self, error_class: str, retries_used: int) -> bool:
        return (
            retries_used < self.max_retries
            and error_class
            in {"timeout", "rate_limited", "provider_server_failure", "transport_failure"}
        )


class CredentialResolver(Protocol):
    def resolve(self, credential_ref: str) -> str: ...


@dataclass(frozen=True)
class ParsedMultimodalResponse:
    """Public-safe response projection; generated reasoning is never a verdict."""

    schema_version: str
    content_text: str
    thinking_text: str
    parse_source: str
    envelope_state: str
    content_hash: str
    thinking_hash: str
    raw_payload_included: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != PARSED_RESPONSE_SCHEMA_VERSION:
            raise ValueError("unsupported parsed multimodal response version")
        if self.envelope_state not in {"completed", "malformed_envelope"}:
            raise ValueError("unsupported multimodal envelope state")
        if self.raw_payload_included:
            raise ValueError("raw provider payload must not be included")

    def public_receipt(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("content_text")
        value.pop("thinking_text")
        value["content_present"] = bool(self.content_text)
        value["thinking_present"] = bool(self.thinking_text)
        return value


def _hashed_text(value: Any) -> tuple[str, str]:
    text = value if isinstance(value, str) else ""
    return text, stable_hash(text)


def _malformed_parsed_response(source: str) -> ParsedMultimodalResponse:
    empty_hash = stable_hash("")
    return ParsedMultimodalResponse(
        schema_version=PARSED_RESPONSE_SCHEMA_VERSION,
        content_text="",
        thinking_text="",
        parse_source=source,
        envelope_state="malformed_envelope",
        content_hash=empty_hash,
        thinking_hash=empty_hash,
    )


def parse_openai_compatible_response(
    envelope: Mapping[str, Any],
) -> ParsedMultimodalResponse:
    try:
        message = envelope["choices"][0]["message"]
        if not isinstance(message, Mapping):
            raise TypeError
    except (KeyError, IndexError, TypeError):
        return _malformed_parsed_response("choices[0].message")
    content, content_hash = _hashed_text(message.get("content"))
    thinking, thinking_hash = _hashed_text(
        message.get("reasoning_content") or message.get("thinking")
    )
    return ParsedMultimodalResponse(
        schema_version=PARSED_RESPONSE_SCHEMA_VERSION,
        content_text=content,
        thinking_text=thinking,
        parse_source="choices[0].message",
        envelope_state="completed",
        content_hash=content_hash,
        thinking_hash=thinking_hash,
    )


def parse_ollama_response(envelope: Mapping[str, Any]) -> ParsedMultimodalResponse:
    message = envelope.get("message")
    if isinstance(message, Mapping):
        content_value = message.get("content")
        thinking_value = message.get("thinking")
        source = "message"
    elif "response" in envelope or "thinking" in envelope:
        content_value = envelope.get("response")
        thinking_value = envelope.get("thinking")
        source = "generate"
    else:
        return _malformed_parsed_response("ollama")
    content, content_hash = _hashed_text(content_value)
    thinking, thinking_hash = _hashed_text(thinking_value)
    return ParsedMultimodalResponse(
        schema_version=PARSED_RESPONSE_SCHEMA_VERSION,
        content_text=content,
        thinking_text=thinking,
        parse_source=source,
        envelope_state="completed",
        content_hash=content_hash,
        thinking_hash=thinking_hash,
    )


@dataclass(frozen=True)
class MultimodalProviderDefinition:
    provider_id: str
    protocol: str
    endpoint: str
    credential_ref: str
    credential_source: str
    image_mime_types: frozenset[str]
    structured_output: bool
    retry_classes: frozenset[str]
    token_bound: int
    local: bool = False

    def __post_init__(self) -> None:
        if self.protocol not in {"openai_compatible", "offline_deterministic", "ollama"}:
            raise ValueError("unsupported multimodal provider protocol")
        if not self.image_mime_types <= SUPPORTED_IMAGE_MIME_TYPES:
            raise ValueError("unsupported provider image MIME type")
        if not self.retry_classes <= RETRY_CLASSES:
            raise ValueError("unsupported provider retry class")
        if self.token_bound < 1:
            raise ValueError("provider token bound must be positive")

    @property
    def capability_hash(self) -> str:
        return stable_hash(
            {
                "provider_id": self.provider_id,
                "protocol": self.protocol,
                "image_mime_types": sorted(self.image_mime_types),
                "structured_output": self.structured_output,
                "retry_classes": sorted(self.retry_classes),
                "token_bound": self.token_bound,
                "local": self.local,
            }
        )


class MultimodalProviderRegistry:
    def __init__(self, providers: list[MultimodalProviderDefinition]) -> None:
        self._providers = {item.provider_id: item for item in providers}

    def require(self, provider_id: str) -> MultimodalProviderDefinition:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ValueError(f"unknown multimodal provider: {provider_id}") from exc

    def discover(self, provider_id: str) -> dict[str, Any]:
        provider = self.require(provider_id)
        return {
            "provider_id": provider.provider_id,
            "protocol": provider.protocol,
            "image_mime_types": sorted(provider.image_mime_types),
            "structured_output": provider.structured_output,
            "retry_classes": sorted(provider.retry_classes),
            "token_bound": provider.token_bound,
            "local": provider.local,
            "capability_hash": provider.capability_hash,
        }


class OpenAICompatibleMultimodalAdapter:
    """Generic OpenAI-compatible chat-completions transport."""

    def __init__(self, credential_resolver: CredentialResolver) -> None:
        self.credential_resolver = credential_resolver

    def invoke(
        self,
        provider: MultimodalProviderDefinition,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        key = self.credential_resolver.resolve(provider.credential_ref)
        call = request.Request(
            provider.endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(call, timeout=timeout_seconds) as response:
                value = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            status_class = f"{exc.code // 100}xx"
            if exc.code in {401, 403}:
                error_class = "authentication_error"
            elif exc.code == 429:
                error_class = "rate_limited"
            elif 400 <= exc.code < 500:
                error_class = "http_client_error"
            else:
                error_class = "http_server_error"
            raise classified_transport_error(error_class, status_class) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise classified_transport_error("timeout") from exc
        except error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise classified_transport_error("timeout") from exc
            if isinstance(reason, (ConnectionResetError, ConnectionAbortedError)):
                raise classified_transport_error("connection_reset") from exc
            if isinstance(reason, ConnectionRefusedError):
                raise classified_transport_error("connection_refused") from exc
            raise classified_transport_error("connection_failure") from exc
        if not isinstance(value, dict):
            raise ProviderMalformedEnvelope
        return value


class OfflineDeterministicMultimodalAdapter:
    """Scripted deterministic adapter for valid and failure conformance tests."""

    def __init__(self, states: list[str]) -> None:
        self.states = list(states)
        self.calls = 0

    def invoke(
        self,
        provider: MultimodalProviderDefinition,
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        del provider, payload, timeout_seconds
        state = self.states[self.calls] if self.calls < len(self.states) else "valid"
        self.calls += 1
        if state == "valid":
            return {
                "model": "offline-deterministic-v1",
                "choices": [{"message": {"content": '{"risk":false,"risk_categories":[],"reason":"offline"}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        if state == "invalid":
            return {
                "model": "offline-deterministic-v1",
                "choices": [{"message": {"content": "not-json"}}],
                "usage": {},
            }
        if state == "timeout":
            raise TimeoutError
        if state == "rate_limit":
            raise ProviderRateLimited
        raise ValueError("unsupported offline deterministic state")


class ProviderRateLimited(Exception):
    pass


class ProviderServerFailure(Exception):
    pass


class ProviderTransportFailure(Exception):
    pass


class ProviderMalformedEnvelope(Exception):
    pass


def default_multimodal_provider_registry() -> MultimodalProviderRegistry:
    return MultimodalProviderRegistry(
        [
            MultimodalProviderDefinition(
                provider_id="dashscope",
                protocol="openai_compatible",
                endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                credential_ref="secret://dashscope/api-key",
                credential_source="environment:DASHSCOPE_API_KEY",
                image_mime_types=SUPPORTED_IMAGE_MIME_TYPES,
                structured_output=True,
                retry_classes=RETRY_CLASSES,
                token_bound=32768,
            ),
            MultimodalProviderDefinition(
                provider_id="dashscope-international",
                protocol="openai_compatible",
                endpoint="https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
                credential_ref="secret://dashscope/api-key",
                credential_source="environment:DASHSCOPE_API_KEY",
                image_mime_types=SUPPORTED_IMAGE_MIME_TYPES,
                structured_output=True,
                retry_classes=RETRY_CLASSES,
                token_bound=32768,
            ),
            MultimodalProviderDefinition(
                provider_id="offline-deterministic",
                protocol="offline_deterministic",
                endpoint="memory://a2/offline-deterministic",
                credential_ref="",
                credential_source="none",
                image_mime_types=SUPPORTED_IMAGE_MIME_TYPES,
                structured_output=True,
                retry_classes=RETRY_CLASSES,
                token_bound=4096,
                local=True,
            ),
            MultimodalProviderDefinition(
                provider_id="ollama-local",
                protocol="ollama",
                endpoint="http://127.0.0.1:11434/api/chat",
                credential_ref="",
                credential_source="none",
                image_mime_types=SUPPORTED_IMAGE_MIME_TYPES,
                structured_output=True,
                retry_classes=frozenset({"parse", "transport"}),
                token_bound=32768,
                local=True,
            ),
        ]
    )


def build_provider_conformance_receipt(
    *,
    provider: MultimodalProviderDefinition,
    adapter_class: str,
    checks: Mapping[str, bool],
    observed_states: list[str],
    generated_at: str,
    source_evidence_hashes: list[str] | None = None,
    predecessor_receipt_id: str | None = None,
    sequence: int = 1,
) -> dict[str, Any]:
    if sequence < 1:
        raise ValueError("provider conformance sequence must be positive")
    if sequence == 1 and predecessor_receipt_id is not None:
        raise ValueError("first provider conformance receipt cannot have a predecessor")
    if sequence > 1 and predecessor_receipt_id is None:
        raise ValueError("later provider conformance receipt requires a predecessor")
    normalized_checks = {key: bool(value) for key, value in sorted(checks.items())}
    blockers = sorted(key for key, passed in normalized_checks.items() if not passed)
    source_hashes = sorted(set(source_evidence_hashes or []))
    core = {
        "provider_id": provider.provider_id,
        "protocol": provider.protocol,
        "adapter_class": adapter_class,
        "capability_hash": provider.capability_hash,
        "checks": normalized_checks,
        "observed_states": sorted(set(observed_states)),
        "source_evidence_hashes": source_hashes,
        "predecessor_receipt_id": predecessor_receipt_id,
        "sequence": sequence,
    }
    return {
        "schema_version": CONFORMANCE_SCHEMA_VERSION,
        "generated_at": generated_at,
        **core,
        "receipt_id": stable_hash(core),
        "qualification_state": "conformant" if not blockers else "blocked",
        "blockers": blockers,
        "raw_payload_included": False,
        "secret_included": False,
        "release_authority": False,
        "public_safe": True,
    }


def measure_invocation(
    invoke: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any] | None, float, str]:
    started = time.monotonic()
    try:
        return invoke(), round(time.monotonic() - started, 6), "completed"
    except TimeoutError:
        return None, round(time.monotonic() - started, 6), "timeout"
    except ProviderRateLimited:
        return None, round(time.monotonic() - started, 6), "rate_limited"
    except Exception:
        return None, round(time.monotonic() - started, 6), "provider_failure"
