"""Commercial provider runtime contracts built around the A2 Provider Gateway."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol
from urllib import error, request

from .result_persistence import stable_hash


MODEL_REGISTRY_SCHEMA_VERSION = "a2.model_registry.v1"
PROVENANCE_SCHEMA_VERSION = "a2.provider_provenance_handoff.v1"
AUTHENTICATED_BUNDLE_SCHEMA_VERSION = "ashr.a1.authenticated_evidence_bundle.v2"
SCOPE_FIELDS = ("organization_id", "tenant_id", "workspace_id", "project_id", "environment_id")
RETRYABLE_STATUSES = frozenset({"timeout", "rate_limited", "provider_unavailable"})


class CredentialResolver(Protocol):
    def resolve(self, credential_ref: str) -> str: ...


class EnvironmentCredentialResolver:
    """Resolve allowlisted secret references only at the adapter boundary."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)

    def resolve(self, credential_ref: str) -> str:
        if not credential_ref.startswith("secret://"):
            raise ValueError("credential_ref must use secret://")
        value = self._values.get(credential_ref, "")
        if not value:
            raise KeyError("credential unavailable")
        return value


@dataclass(frozen=True)
class ModelRecord:
    provider_id: str
    model_id: str
    version: str
    modalities: frozenset[str]
    lifecycle: str = "active"
    context_window: int = 0
    local: bool = False

    @property
    def record_id(self) -> str:
        return stable_hash(
            {
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "version": self.version,
                "modalities": sorted(self.modalities),
            }
        )


class ModelRegistry:
    def __init__(self, records: list[ModelRecord] | None = None) -> None:
        self._records = {(item.provider_id, item.model_id): item for item in records or []}

    def upsert(self, record: ModelRecord) -> None:
        if record.lifecycle not in {"active", "preview", "deprecated", "disabled"}:
            raise ValueError("unsupported model lifecycle")
        self._records[(record.provider_id, record.model_id)] = record

    def select(
        self,
        *,
        provider_ids: set[str] | None = None,
        required_modalities: set[str] | None = None,
        include_preview: bool = False,
    ) -> list[ModelRecord]:
        providers = provider_ids or set()
        required = required_modalities or set()
        allowed_lifecycle = {"active", "preview"} if include_preview else {"active"}
        return sorted(
            (
                item
                for item in self._records.values()
                if (not providers or item.provider_id in providers)
                and required <= item.modalities
                and item.lifecycle in allowed_lifecycle
            ),
            key=lambda item: (not item.local, item.provider_id, item.model_id),
        )

    def export_public(self) -> dict[str, Any]:
        records = [
            {
                "record_id": item.record_id,
                "provider_id": item.provider_id,
                "model_id": item.model_id,
                "version": item.version,
                "modalities": sorted(item.modalities),
                "lifecycle": item.lifecycle,
                "context_window": item.context_window,
                "local": item.local,
            }
            for item in self.select(include_preview=True)
        ]
        return {"schema_version": MODEL_REGISTRY_SCHEMA_VERSION, "models": records}


class OllamaDiscovery:
    def discover(self, base_url: str, *, timeout_seconds: float = 2) -> list[ModelRecord]:
        payload = _json_get(str(base_url).rstrip("/") + "/api/tags", timeout_seconds)
        records = []
        for item in payload.get("models", []):
            model_id = str(item.get("name") or item.get("model") or "")
            if model_id:
                records.append(
                    ModelRecord(
                        "ollama-local",
                        model_id,
                        str(item.get("digest") or "unversioned"),
                        _infer_ollama_modalities(item),
                        local=True,
                    )
                )
        return records

    def health(self, base_url: str, *, timeout_seconds: float = 2) -> dict[str, Any]:
        started = time.monotonic()
        try:
            records = self.discover(base_url, timeout_seconds=timeout_seconds)
            return {
                "status": "ready",
                "model_count": len(records),
                "latency_ms": round((time.monotonic() - started) * 1000),
            }
        except TimeoutError:
            return {"status": "timeout", "model_count": 0}
        except Exception:
            return {"status": "unavailable", "model_count": 0}


class OpenAICompatibleAdapter:
    """One normalized adapter for OpenAI-compatible chat completion endpoints."""

    def __init__(self, credential_resolver: CredentialResolver) -> None:
        self.credential_resolver = credential_resolver

    def invoke(self, model: dict[str, Any], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        key = self.credential_resolver.resolve(str(model.get("credential_ref") or ""))
        content = [_openai_part(part) for part in payload.get("parts", [])]
        body = json.dumps(
            {
                "model": model["model_id"],
                "messages": [{"role": "user", "content": content}],
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")
        endpoint = str(model["base_url"]).rstrip("/") + "/chat/completions"
        call = request.Request(
            endpoint,
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(call, timeout=timeout_seconds) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code == 429:
                raise ProviderRateLimited from exc
            if exc.code >= 500:
                raise ProviderUnavailable from exc
            raise
        choice = (parsed.get("choices") or [{}])[0]
        usage = parsed.get("usage") or {}
        return {
            "output_text": str(choice.get("message", {}).get("content") or ""),
            "usage": {
                "input_tokens": int(usage.get("prompt_tokens") or 0),
                "output_tokens": int(usage.get("completion_tokens") or 0),
            },
            "provider_request_id": str(parsed.get("id") or ""),
        }


class ProviderRateLimited(RuntimeError):
    pass


class ProviderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class TenantProviderPolicy:
    allowed_providers: frozenset[str]
    allowed_models: frozenset[str] = frozenset()
    allowed_residencies: frozenset[str] = frozenset({"local", "unspecified"})
    max_parts: int = 32
    max_total_bytes: int = 10 * 1024 * 1024
    max_part_bytes: Mapping[str, int] = field(
        default_factory=lambda: {
            "text": 256 * 1024,
            "image": 8 * 1024 * 1024,
            "audio": 20 * 1024 * 1024,
            "file": 20 * 1024 * 1024,
            "video": 100 * 1024 * 1024,
        }
    )

    def authorize(
        self,
        *,
        provider_id: str,
        model_id: str,
        data_residency: str,
        parts: list[dict[str, Any]],
    ) -> list[str]:
        blockers = []
        if provider_id not in self.allowed_providers:
            blockers.append("provider_not_allowed")
        if self.allowed_models and model_id not in self.allowed_models:
            blockers.append("model_not_allowed")
        if data_residency not in self.allowed_residencies:
            blockers.append("data_residency_not_allowed")
        if len(parts) > self.max_parts:
            blockers.append("part_count_exceeded")
        total = 0
        for part in parts:
            modality = str(part.get("modality") or "")
            size = _part_size(part)
            total += size
            if size > int(self.max_part_bytes.get(modality, 0)):
                blockers.append(f"{modality}_part_size_exceeded")
        if total > self.max_total_bytes:
            blockers.append("total_payload_size_exceeded")
        return sorted(set(blockers))


@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: str
    estimated_cost_usd: float
    allowed: bool
    blocker: str = ""


class BudgetManager:
    def __init__(self, remaining_usd: float, prices_per_1k: Mapping[str, tuple[float, float]]) -> None:
        self.remaining_usd = float(remaining_usd)
        self.prices_per_1k = dict(prices_per_1k)
        self.ledger: list[dict[str, Any]] = []

    def reserve(self, model_id: str, estimated_input_tokens: int, max_output_tokens: int) -> BudgetReservation:
        input_rate, output_rate = self.prices_per_1k.get(model_id, (0.0, 0.0))
        estimate = round(
            estimated_input_tokens / 1000 * input_rate + max_output_tokens / 1000 * output_rate,
            8,
        )
        allowed = estimate <= self.remaining_usd
        reservation = BudgetReservation(
            stable_hash({"model_id": model_id, "estimate": estimate, "sequence": len(self.ledger)}),
            estimate,
            allowed,
            "" if allowed else "budget_exceeded",
        )
        self.ledger.append(
            {
                "event": "reserved" if allowed else "blocked",
                "reservation_id": reservation.reservation_id,
                "estimated_cost_usd": estimate,
            }
        )
        if allowed:
            self.remaining_usd -= estimate
        return reservation

    def settle(
        self,
        reservation: BudgetReservation,
        *,
        input_tokens: int,
        output_tokens: int,
        model_id: str,
        attempt: int,
    ) -> dict[str, Any]:
        input_rate, output_rate = self.prices_per_1k.get(model_id, (0.0, 0.0))
        actual = round(input_tokens / 1000 * input_rate + output_tokens / 1000 * output_rate, 8)
        event = {
            "event": "settled",
            "reservation_id": reservation.reservation_id,
            "attempt": attempt,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "actual_cost_usd": actual,
            "raw_payload_included": False,
        }
        self.ledger.append(event)
        return event


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    retryable_statuses: frozenset[str] = RETRYABLE_STATUSES

    def should_retry(self, status: str, attempt: int) -> bool:
        return attempt < self.max_attempts and status in self.retryable_statuses


class CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown_seconds: float = 30) -> None:
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.failures = 0
        self.opened_at = 0.0

    def allow(self, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        return self.failures < self.threshold or current - self.opened_at >= self.cooldown_seconds

    def record(self, success: bool, now: float | None = None) -> None:
        if success:
            self.failures = 0
            self.opened_at = 0
            return
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic() if now is None else now


def validate_semantic_judge_output(value: str | dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(value) if isinstance(value, str) else dict(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("semantic judge output must be JSON") from exc
    required = {"passed", "score", "reason", "failure_classes", "evidence_refs", "abstained"}
    if set(payload) != required:
        raise ValueError("semantic judge output fields do not match contract")
    if not isinstance(payload["passed"], bool) or not isinstance(payload["abstained"], bool):
        raise ValueError("passed and abstained must be boolean")
    if not isinstance(payload["score"], (int, float)) or not 0 <= payload["score"] <= 1:
        raise ValueError("score must be within 0..1")
    if not isinstance(payload["reason"], str) or not payload["reason"].strip():
        raise ValueError("reason is required")
    for field_name in ("failure_classes", "evidence_refs"):
        if not isinstance(payload[field_name], list) or not all(isinstance(item, str) for item in payload[field_name]):
            raise ValueError(f"{field_name} must be a string array")
    if payload["abstained"] and payload["passed"]:
        raise ValueError("an abstained judge cannot pass")
    return payload


def verify_authenticated_evidence_bundle(
    bundle: dict[str, Any],
    *,
    key_resolver: Callable[[str], bytes],
    tenant_id: str,
    project_id: str,
    now_unix_ms: int,
) -> dict[str, Any]:
    required = {
        "schema_version",
        "algorithm",
        "key_id",
        "bundle_id_digest",
        "tenant_digest",
        "project_digest",
        "evidence",
        "evidence_digest",
        "issued_at_unix_ms",
        "expires_at_unix_ms",
        "signature",
    }
    if set(bundle) != required:
        raise ValueError("bundle fields do not match authenticated contract")
    if bundle["schema_version"] != AUTHENTICATED_BUNDLE_SCHEMA_VERSION or bundle["algorithm"] != "hmac-sha256":
        raise ValueError("unsupported authenticated bundle contract")
    if not bundle["issued_at_unix_ms"] <= now_unix_ms <= bundle["expires_at_unix_ms"]:
        raise ValueError("authenticated bundle is outside its validity window")
    if bundle["tenant_digest"] != _sha256_hex(tenant_id.encode()) or bundle["project_digest"] != _sha256_hex(project_id.encode()):
        raise ValueError("authenticated bundle scope mismatch")
    evidence_bytes = _canonical_json(bundle["evidence"])
    if bundle["evidence_digest"] != _sha256_hex(evidence_bytes):
        raise ValueError("authenticated evidence digest mismatch")
    signing_fields = {
        key: bundle[key]
        for key in (
            "schema_version",
            "algorithm",
            "key_id",
            "bundle_id_digest",
            "tenant_digest",
            "project_digest",
            "evidence_digest",
            "issued_at_unix_ms",
            "expires_at_unix_ms",
        )
    }
    canonical = _canonical_json(signing_fields)
    key = key_resolver(bundle["key_id"])
    expected = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, str(bundle["signature"])):
        raise ValueError("authenticated bundle signature mismatch")
    return {
        "verification_level": "manifest_authenticated",
        "manifest_authenticated": True,
        "authenticated_bundle_digest": _sha256_hex(canonical),
        "evidence_items": len(bundle["evidence"]),
    }


def build_provider_provenance_handoff(
    *,
    tenant_scope: dict[str, str],
    snapshot: dict[str, Any],
    provider_result: dict[str, Any],
    semantic_output: dict[str, Any] | None,
    bundle_verification: dict[str, Any],
) -> dict[str, Any]:
    missing_scope = [field for field in SCOPE_FIELDS if not tenant_scope.get(field)]
    blockers = list(provider_result.get("blockers") or [])
    if missing_scope:
        blockers.append("scope_incomplete")
    if bundle_verification.get("manifest_authenticated") is not True:
        blockers.append("bundle_not_authenticated")
    if provider_result.get("release_authority") is not False:
        blockers.append("provider_authority_invalid")
    if provider_result.get("status") != "completed":
        blockers.append("provider_not_completed")
    if semantic_output is None:
        blockers.append("semantic_output_not_validated")
    ready = not blockers
    handoff = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "status": "ready" if ready else "blocked",
        "tenant_scope": tenant_scope,
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_hash": snapshot.get("snapshot_hash"),
        "logical_call_id": provider_result.get("logical_call_id"),
        "provider_id": provider_result.get("provider_id"),
        "model_id": provider_result.get("model_id"),
        "attempt_count": len(provider_result.get("attempts") or []),
        "evaluation_eligible": ready,
        "release_authority": False,
        "decision_authority": "a2.release_gate.v1",
        "blockers": sorted(set(blockers)),
        "raw_payload_included": False,
        "secret_included": False,
    }
    if provider_result.get("response_hash") is not None:
        handoff["response_hash"] = provider_result["response_hash"]
    if bundle_verification.get("authenticated_bundle_digest") is not None:
        handoff["bundle_digest"] = bundle_verification["authenticated_bundle_digest"]
    return handoff


def build_local_smoke_evidence(
    *,
    modality: str,
    model_id: str,
    provider_result: dict[str, Any],
    content_hashes: list[str],
    model_digest: str = "",
) -> dict[str, Any]:
    status = str(provider_result.get("status", "blocked"))
    return {
        "schema_version": "a2.local_provider_smoke.v1",
        "provider_id": "ollama-local",
        "model_id": model_id,
        "model_digest": model_digest,
        "modality": modality,
        "status": status,
        "capability_state": (
            "callable"
            if status == "completed"
            else "protocol_reachable"
            if status in {"timeout", "invalid_response"}
            else "unavailable"
        ),
        # A smoke call proves transport/runtime callability only. It never
        # substitutes for golden regression, disagreement analysis, or review.
        "calibration_state": "uncalibrated",
        "logical_call_id": provider_result.get("logical_call_id"),
        "response_hash": provider_result.get("response_hash"),
        "content_hashes": content_hashes,
        "raw_payload_included": False,
        "secret_included": False,
    }


def _infer_ollama_modalities(item: dict[str, Any]) -> frozenset[str]:
    families = {str(value).lower() for value in item.get("details", {}).get("families", [])}
    family = str(item.get("details", {}).get("family") or "").lower()
    if family:
        families.add(family)
    vision_markers = {"clip", "llava", "mllama", "qwen2vl", "qwen3vl", "gemma3"}
    return frozenset({"text", "image"} if families & vision_markers else {"text"})


def _openai_part(part: dict[str, Any]) -> dict[str, Any]:
    modality = part.get("modality")
    if modality == "text":
        return {"type": "text", "text": str(part.get("text") or "")}
    if modality == "image":
        return {"type": "image_url", "image_url": {"url": str(part.get("data") or "")}}
    return {"type": "text", "text": f"[{modality} artifact:{part.get('content_hash', 'unverified')}]"}


def _part_size(part: dict[str, Any]) -> int:
    if isinstance(part.get("size_bytes"), int):
        return max(0, part["size_bytes"])
    value = part.get("text") if part.get("modality") == "text" else part.get("data", "")
    return len(value.encode("utf-8")) if isinstance(value, str) else 0


def _json_get(url: str, timeout_seconds: float) -> dict[str, Any]:
    try:
        with request.urlopen(url, timeout=timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise TimeoutError from exc
        raise
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
