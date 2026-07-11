"""Provider-independent, fail-closed model routing for A2 semantic evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib import request

from .provider_runtime import CircuitBreaker, ProviderRateLimited, ProviderUnavailable, RetryPolicy
from .result_persistence import stable_hash


SCHEMA_VERSION = "a2.provider_gateway.v1"
MODALITIES = frozenset({"text", "image", "audio", "file", "video"})
TERMINAL_FAILURES = frozenset(
    {
        "blocked",
        "budget_blocked",
        "provider_error",
        "provider_unavailable",
        "rate_limited",
        "timeout",
        "invalid_response",
        "unsupported",
    }
)


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


class OllamaAdapter:
    """Minimal Ollama /api/chat adapter; credentials are intentionally unsupported."""

    def invoke(self, model: dict[str, Any], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
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
                "options": model.get("options", {}),
            }
        ).encode("utf-8")
        endpoint = str(model["base_url"]).rstrip("/") + "/api/chat"
        call = request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(call, timeout=timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        return {
            "output_text": str(parsed.get("message", {}).get("content") or ""),
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
    ) -> dict[str, Any]:
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
            except ProviderRateLimited:
                status = "rate_limited"
            except ProviderUnavailable:
                status = "provider_unavailable"
            except (ValueError, TypeError):
                status = "invalid_response"
            except Exception:
                status = "provider_error"
            attempt["status"] = status
            if not self.retry_policy.should_retry(status, attempt_number):
                result = self._result(request_core, logical_call_id, status, attempts=attempts)
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
        if any("data" in part and part.get("modality") != "text" and not part.get("content_hash") for part in parts):
            return "blocked"
        if max_cost_usd < 0:
            return "budget_blocked"
        return ""

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
