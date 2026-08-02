"""Provider-independent, fail-closed model routing for A2 semantic evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib import request

from .provider_runtime import (
    CircuitBreaker,
    ProviderAuthenticationFailed,
    ProviderRateLimited,
    ProviderUnavailable,
    RetryPolicy,
)
from .result_persistence import stable_hash


SCHEMA_VERSION = "a2.provider_gateway.v1"
RECONCILIATION_SCHEMA_VERSION = "a2.provider_reconciliation.v1"
RECONCILIATION_MODES = frozenset({"unsupported", "provider_status_lookup"})
MODALITIES = frozenset({"text", "image", "audio", "file", "video"})
RECONCILIATION_STATUSES = frozenset(
    {
        "remote_completed",
        "remote_pending",
        "remote_not_found",
        "remote_unknown",
        "reconciliation_unsupported",
    }
)
TERMINAL_FAILURES = frozenset(
    {
        "blocked",
        "budget_blocked",
        "provider_error",
        "provider_unavailable",
        "rate_limited",
        "timeout",
        "invalid_response",
        "authentication_failed",
        "unsupported",
    }
)
MODEL_OPTION_ALLOWLISTS = {
    "ollama": frozenset({"temperature", "num_predict", "seed", "top_p", "top_k"}),
    "openai_compatible": frozenset({"temperature", "max_tokens", "seed", "top_p"}),
}
MAX_IDEMPOTENCY_KEY_LENGTH = 256


def validate_idempotency_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_IDEMPOTENCY_KEY_LENGTH
    ):
        raise ValueError(
            "idempotency_key must be a non-blank string of at most "
            f"{MAX_IDEMPOTENCY_KEY_LENGTH} characters"
        )
    return value


def validate_model_options(protocol: str, options: dict[str, Any]) -> dict[str, Any]:
    allowed = MODEL_OPTION_ALLOWLISTS.get(protocol)
    if allowed is None:
        return dict(options)
    unsupported = sorted(set(options) - allowed)
    if unsupported:
        label = "Ollama" if protocol == "ollama" else protocol
        raise ValueError(f"unsupported {label} model options: {','.join(unsupported)}")
    validators = {
        "temperature": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 2,
        "top_p": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 1,
        "top_k": lambda value: isinstance(value, int) and not isinstance(value, bool) and value >= 1,
        "seed": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "num_predict": lambda value: isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 32768,
        "max_tokens": lambda value: isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 32768,
    }
    invalid = sorted(name for name, value in options.items() if not validators[name](value))
    if invalid:
        raise ValueError(f"invalid {protocol} model option values: {','.join(invalid)}")
    return dict(options)


class ProviderAdapter(Protocol):
    def invoke(self, model: dict[str, Any], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ProviderDefinition:
    provider_id: str
    protocol: str
    base_url: str
    credential_ref: str
    allowed_modalities: frozenset[str]
    allowed_tenants: frozenset[str]
    enabled: bool = True
    data_residency: str = "unspecified"
    reconciliation_mode: str = "unsupported"

    def __post_init__(self) -> None:
        if self.reconciliation_mode not in RECONCILIATION_MODES:
            raise ValueError("unsupported Provider reconciliation mode")


class StrictFakeAdapter:
    """Deterministic adapter for contract, failure, and replay tests."""

    def __init__(self, response: dict[str, Any] | None = None, *, failure: str = "") -> None:
        self.response = response or {"output_text": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}
        self.failure = failure
        self.calls = 0

    def invoke(self, model: dict[str, Any], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        self.calls += 1
        if self.failure:
            raise RuntimeError(self.failure)
        return dict(self.response)


class StrictFakeReconciliationAdapter(StrictFakeAdapter):
    """Deterministic reconciliation adapter for governed recovery tests."""

    def __init__(
        self,
        response: dict[str, Any] | None = None,
        *,
        reconciliation_response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(response)
        self.reconciliation_response = reconciliation_response or {"status": "remote_unknown"}
        self.reconciliation_calls = 0

    def reconcile(
        self,
        model: dict[str, Any],
        reconciliation_request: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        self.reconciliation_calls += 1
        return dict(self.reconciliation_response)


class OllamaAdapter:
    """Minimal Ollama /api/chat adapter; credentials are intentionally unsupported."""

    def invoke(self, model: dict[str, Any], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        options = validate_model_options("ollama", dict(model.get("options") or {}))
        content = "\n".join(
            str(part.get("text") or "")
            for part in payload.get("parts", [])
            if part.get("modality") == "text"
        )
        images = [
            part["data"]
            for part in payload.get("parts", [])
            if part.get("modality") == "image" and isinstance(part.get("data"), str)
        ]
        message: dict[str, Any] = {"role": "user", "content": content}
        if images:
            message["images"] = images
        body = json.dumps(
            {
                "model": model["model_id"],
                "messages": [message],
                "stream": False,
                "format": model.get("response_format", "json"),
                "options": options,
            }
        ).encode("utf-8")
        endpoint = str(model["base_url"]).rstrip("/") + "/api/chat"
        call = request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(call, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        output_text = str(parsed.get("message", {}).get("content") or "")
        if not output_text.strip():
            # A private reasoning channel is not governed Judge output and
            # must not be promoted when the public assistant content is empty.
            raise ValueError("Ollama response message content is empty")
        return {
            "output_text": output_text,
            "usage": {
                "input_tokens": int(parsed.get("prompt_eval_count") or 0),
                "output_tokens": int(parsed.get("eval_count") or 0),
            },
            "provider_request_id": "",
        }


class ProviderGateway:
    """Route immutable evidence snapshots to explicitly allowed model providers."""

    def __init__(
        self,
        providers: list[ProviderDefinition],
        adapters: dict[str, ProviderAdapter],
        *,
        audit_writer: Callable[[dict[str, Any]], None] | None = None,
        request_authorizer: Callable[[dict[str, Any]], list[str]] | None = None,
        response_validator: Callable[[str], dict[str, Any]] | None = None,
        retry_policy: RetryPolicy | None = None,
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
    ) -> None:
        self.providers = {item.provider_id: item for item in providers}
        self.adapters = dict(adapters)
        self.audit_writer = audit_writer or (lambda event: None)
        self.request_authorizer = request_authorizer or (lambda context: [])
        self.response_validator = response_validator
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=1)
        self.circuit_breakers = circuit_breakers or {}
        self._results: dict[str, dict[str, Any]] = {}

    def invoke(
        self,
        *,
        tenant_id: str,
        snapshot: dict[str, Any],
        provider_id: str,
        model_id: str,
        parts: list[dict[str, Any]],
        idempotency_key: str,
        timeout_seconds: float = 30,
        max_cost_usd: float = 0,
        model_options: dict[str, Any] | None = None,
        credential_generation_marker: str = "",
    ) -> dict[str, Any]:
        idempotency_key = validate_idempotency_key(idempotency_key)
        if credential_generation_marker and not (
            credential_generation_marker.startswith("hmac-sha256:")
            and len(credential_generation_marker) == 76
            and all(char in "0123456789abcdef" for char in credential_generation_marker[12:])
        ):
            raise ValueError("credential_generation_marker must be empty or canonical hmac-sha256")
        normalized_options = validate_model_options(
            self.providers[provider_id].protocol if provider_id in self.providers else "",
            dict(model_options or {}),
        )
        request_core = {
            "schema_version": SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "snapshot_id": str(snapshot.get("snapshot_id") or ""),
            "snapshot_hash": str(snapshot.get("snapshot_hash") or ""),
            "provider_id": provider_id,
            "model_id": model_id,
            "modalities": sorted({str(part.get("modality") or "") for part in parts}),
            "payload_hash": stable_hash(parts),
            "idempotency_key": idempotency_key,
            "model_options_hash": stable_hash(normalized_options),
            "credential_generation_marker": credential_generation_marker,
        }
        logical_call_id = stable_hash(request_core)
        if logical_call_id in self._results:
            return dict(self._results[logical_call_id])

        blocker = self._preflight(tenant_id, snapshot, provider_id, parts, idempotency_key, max_cost_usd)
        if blocker:
            result = self._result(request_core, logical_call_id, blocker, attempts=[])
            self._results[logical_call_id] = result
            return dict(result)

        provider = self.providers[provider_id]
        policy_blockers = self.request_authorizer(
            {
                "tenant_id": tenant_id,
                "snapshot": snapshot,
                "provider": provider,
                "model_id": model_id,
                "parts": parts,
                "max_cost_usd": max_cost_usd,
            }
        )
        if policy_blockers:
            result = self._result(request_core, logical_call_id, "blocked", attempts=[])
            result["blockers"] = sorted(set(policy_blockers))
            self._results[logical_call_id] = result
            return dict(result)
        adapter = self.adapters.get(provider.protocol)
        if adapter is None:
            result = self._result(request_core, logical_call_id, "unsupported", attempts=[])
            self._results[logical_call_id] = result
            return dict(result)
        breaker = self.circuit_breakers.get(provider_id)
        if breaker is not None and not breaker.allow():
            result = self._result(request_core, logical_call_id, "provider_unavailable", attempts=[])
            result["blockers"] = ["circuit_open"]
            self._results[logical_call_id] = result
            return dict(result)

        audit_event = {
            "event": "provider_call_authorized",
            "logical_call_id": logical_call_id,
            "tenant_id": tenant_id,
            "snapshot_hash": request_core["snapshot_hash"],
            "provider_id": provider_id,
            "model_id": model_id,
            "credential_ref": provider.credential_ref,
            "credential_generation_marker": credential_generation_marker,
        }
        try:
            self.audit_writer(audit_event)
        except Exception:
            result = self._result(request_core, logical_call_id, "blocked", attempts=[])
            result["blockers"] = ["audit_write_failed"]
            self._results[logical_call_id] = result
            return dict(result)

        attempts = []
        for attempt_number in range(1, self.retry_policy.max_attempts + 1):
            attempt = {"attempt": attempt_number, "status": "started", "cost_usd": 0}
            attempts.append(attempt)
            try:
                response = adapter.invoke(
                    {
                        "model_id": model_id,
                        "base_url": provider.base_url,
                        "credential_ref": provider.credential_ref,
                        "response_format": "json",
                        "options": normalized_options,
                    },
                    {"parts": parts},
                    timeout_seconds,
                )
                if not isinstance(response, dict) or not isinstance(response.get("output_text"), str):
                    raise ValueError("provider response does not match normalized contract")
                validated = self.response_validator(response["output_text"]) if self.response_validator else None
                attempt["status"] = "completed"
                attempt["usage"] = response.get("usage", {})
                result = self._result(request_core, logical_call_id, "completed", attempts=attempts)
                result["response_hash"] = stable_hash(response)
                result["output_text"] = response["output_text"]
                if validated is not None:
                    result["structured_output_hash"] = stable_hash(validated)
                if breaker is not None:
                    breaker.record(True)
                break
            except TimeoutError:
                status = "timeout"
            except ProviderAuthenticationFailed:
                status = "authentication_failed"
            except ProviderRateLimited:
                status = "rate_limited"
            except ProviderUnavailable:
                status = "provider_unavailable"
            except (ValueError, TypeError) as exc:
                status = "invalid_response"
                failure_detail = (
                    "empty_public_content"
                    if "message content is empty" in str(exc)
                    else "malformed_or_invalid_output"
                )
            except Exception:
                status = "provider_error"
            attempt["status"] = status
            if not self.retry_policy.should_retry(status, attempt_number):
                result = self._result(request_core, logical_call_id, status, attempts=attempts)
                if status == "invalid_response":
                    result["failure_detail"] = failure_detail
                if breaker is not None:
                    breaker.record(False)
                break
        self._results[logical_call_id] = result
        return dict(result)

    def select(self, *, tenant_id: str, required_modalities: list[str]) -> list[str]:
        required = set(required_modalities)
        return sorted(
            item.provider_id
            for item in self.providers.values()
            if item.enabled
            and required <= item.allowed_modalities
            and (not item.allowed_tenants or tenant_id in item.allowed_tenants)
        )

    def reconcile(
        self,
        *,
        scope: dict[str, str],
        operation_id: str,
        provider_call_id: str,
        logical_call_id: str,
        provider_id: str,
        model_id: str,
        snapshot_hash: str,
        payload_hash: str,
        idempotency_key_hash: str,
        provider_endpoint_hash: str,
        provider_generation: int,
        timeout_seconds: float = 30,
    ) -> dict[str, Any]:
        """Query an explicitly capable Provider without authorizing blind replay."""
        request_core = {
            "schema_version": RECONCILIATION_SCHEMA_VERSION,
            "scope": dict(scope),
            "operation_id": operation_id,
            "provider_call_id": provider_call_id,
            "logical_call_id": logical_call_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "snapshot_hash": snapshot_hash,
            "payload_hash": payload_hash,
            "idempotency_key_hash": idempotency_key_hash,
            "provider_endpoint_hash": provider_endpoint_hash,
            "provider_generation": provider_generation,
        }
        blocker = self._reconciliation_preflight(request_core)
        if blocker:
            return self._reconciliation_result(request_core, blocker)
        provider = self.providers.get(provider_id)
        adapter = self.adapters.get(provider.protocol) if provider else None
        if provider is None or provider.reconciliation_mode != "provider_status_lookup":
            return self._reconciliation_result(request_core, "reconciliation_unsupported")
        reconcile = getattr(adapter, "reconcile", None)
        if not callable(reconcile):
            return self._reconciliation_result(request_core, "reconciliation_unsupported")
        try:
            response = reconcile(
                {
                    "model_id": model_id,
                    "base_url": provider.base_url,
                    "credential_ref": provider.credential_ref,
                },
                dict(request_core),
                timeout_seconds,
            )
            return self._normalize_reconciliation_response(request_core, response)
        except Exception:
            return self._reconciliation_result(request_core, "remote_unknown")

    def _preflight(
        self,
        tenant_id: str,
        snapshot: dict[str, Any],
        provider_id: str,
        parts: list[dict[str, Any]],
        idempotency_key: str,
        max_cost_usd: float,
    ) -> str:
        provider = self.providers.get(provider_id)
        if not provider or not provider.enabled:
            return "unsupported"
        if not idempotency_key:
            return "blocked"
        if snapshot.get("tenant_id") != tenant_id or snapshot.get("completeness") != "complete":
            return "blocked"
        if provider.allowed_tenants and tenant_id not in provider.allowed_tenants:
            return "blocked"
        requested = {str(part.get("modality") or "") for part in parts}
        if not requested or not requested <= MODALITIES or not requested <= provider.allowed_modalities:
            return "unsupported"
        for part in parts:
            modality = str(part.get("modality") or "")
            if modality == "text":
                if not isinstance(part.get("text"), str) or not part["text"].strip():
                    return "blocked"
                continue
            if not isinstance(part.get("data"), str) or not part["data"]:
                return "blocked"
            if not part.get("content_hash"):
                return "blocked"
        if max_cost_usd < 0:
            return "budget_blocked"
        return ""

    def _reconciliation_preflight(self, request_core: dict[str, Any]) -> str:
        scope = request_core.get("scope")
        if not isinstance(scope, dict) or set(scope) != {
            "organization_id", "tenant_id", "workspace_id", "project_id", "environment_id",
        }:
            return "remote_unknown"
        if any(not isinstance(value, str) or not value for value in scope.values()):
            return "remote_unknown"
        provider = self.providers.get(str(request_core.get("provider_id") or ""))
        if (
            provider is None
            or not provider.enabled
            or (provider.allowed_tenants and scope["tenant_id"] not in provider.allowed_tenants)
        ):
            return "reconciliation_unsupported"
        required_strings = (
            "operation_id", "provider_call_id", "logical_call_id", "model_id",
            "snapshot_hash", "payload_hash", "idempotency_key_hash", "provider_endpoint_hash",
        )
        if any(not isinstance(request_core.get(field), str) or not request_core[field] for field in required_strings):
            return "remote_unknown"
        generation = request_core.get("provider_generation")
        if isinstance(generation, bool) or not isinstance(generation, int) or generation <= 0:
            return "remote_unknown"
        return ""

    def _normalize_reconciliation_response(
        self,
        request_core: dict[str, Any],
        response: Any,
    ) -> dict[str, Any]:
        if not isinstance(response, dict) or set(response) - {
            "status", "provider_call_id", "logical_call_id", "provider_id", "model_id",
            "snapshot_hash", "payload_hash", "idempotency_key_hash",
            "provider_endpoint_hash", "scope", "operation_id", "provider_generation", "output",
        }:
            return self._reconciliation_result(request_core, "remote_unknown")
        status = response.get("status")
        if status not in RECONCILIATION_STATUSES:
            return self._reconciliation_result(request_core, "remote_unknown")
        if status != "remote_completed":
            return self._reconciliation_result(request_core, str(status))
        bindings = (
            "provider_call_id", "logical_call_id", "provider_id", "model_id",
            "snapshot_hash", "payload_hash", "idempotency_key_hash",
            "provider_endpoint_hash", "scope", "operation_id", "provider_generation",
        )
        if any(response.get(field) != request_core.get(field) for field in bindings):
            return self._reconciliation_result(request_core, "remote_unknown")
        output = response.get("output")
        if (
            not isinstance(output, dict)
            or not isinstance(output.get("output_text"), str)
            or self.response_validator is None
        ):
            return self._reconciliation_result(request_core, "remote_unknown")
        try:
            normalized_output = self.response_validator(output["output_text"])
        except (TypeError, ValueError):
            return self._reconciliation_result(request_core, "remote_unknown")
        result = self._reconciliation_result(request_core, "remote_completed")
        result["normalized_output"] = normalized_output
        result["output_hash"] = stable_hash(output)
        return result

    @staticmethod
    def _reconciliation_result(request_core: dict[str, Any], status: str) -> dict[str, Any]:
        return {
            **request_core,
            "status": status,
            "evaluation_eligible": status == "remote_completed",
            "retry_authorized": False,
            "release_authority": False,
            "public_safe": True,
            "raw_response_included": False,
            "blockers": [] if status == "remote_completed" else [status],
        }

    @staticmethod
    def _result(
        request_core: dict[str, Any],
        logical_call_id: str,
        status: str,
        *,
        attempts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            **request_core,
            "logical_call_id": logical_call_id,
            "status": status,
            "evaluation_eligible": status == "completed",
            "release_authority": False,
            "attempts": attempts,
            "blockers": [] if status == "completed" else [status],
            "raw_request_included": False,
            "raw_response_included": False,
            "secret_included": False,
        }


def default_provider_catalog() -> list[ProviderDefinition]:
    """Return disabled-by-default cloud routes plus an explicit local Ollama route."""
    return [
        ProviderDefinition(
            "ollama-local",
            "ollama",
            "http://127.0.0.1:11434",
            "",
            frozenset({"text", "image"}),
            frozenset(),
            data_residency="local",
        ),
        ProviderDefinition("openai", "openai_responses", "", "secret://openai/default", MODALITIES, frozenset(), False),
        ProviderDefinition("anthropic", "anthropic_messages", "", "secret://anthropic/default", frozenset({"text", "image", "file"}), frozenset(), False),
        ProviderDefinition("google", "google_genai", "", "secret://google/default", MODALITIES, frozenset(), False),
        ProviderDefinition("dashscope", "openai_compatible", "", "secret://dashscope/default", MODALITIES, frozenset(), False),
        ProviderDefinition("openrouter", "openai_compatible", "", "secret://openrouter/default", MODALITIES, frozenset(), False),
        ProviderDefinition("azure-openai", "openai_compatible", "", "secret://azure-openai/default", MODALITIES, frozenset(), False),
    ]
