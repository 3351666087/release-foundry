from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping
from uuid import uuid4

from .platform import PLATFORM_SCHEMA_VERSION, release_gate_bridge_payload
from .runtime import JsonDict, ValidationError, _jsonable, _utc_now

A2_RELEASE_GATE_CONTRACT = "A2.release_gate.evaluate"
_DEFAULT_TIMEOUT_SECONDS = 5.0
_SENSITIVE_KEY_RE = re.compile(r"(api[_-]?key|authorization|bearer|secret|token|password|credential)", re.IGNORECASE)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~+/=-]+|api[_-]?key\s*[=:]\s*[^\s,;]+|secret\s*[=:]\s*[^\s,;]+|token\s*[=:]\s*[^\s,;]+)"
)


class ReleaseGateBridgeError(RuntimeError):
    """Public-safe bridge failure with redacted diagnostic text."""

    code = "release_gate_bridge_error"

    def __init__(self, message: str, *, request_id: str | None = None, status_code: int | None = None) -> None:
        super().__init__(_redact_text(message))
        self.request_id = request_id
        self.status_code = status_code

    def to_dict(self) -> JsonDict:
        payload: JsonDict = {"code": self.code, "message": str(self)}
        if self.request_id is not None:
            payload["request_id"] = self.request_id
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        return payload


class ReleaseGateBridgeTimeout(ReleaseGateBridgeError):
    code = "release_gate_bridge_timeout"


class ReleaseGateBridgeResponseError(ReleaseGateBridgeError):
    code = "release_gate_bridge_response_error"


@dataclass(frozen=True, slots=True)
class ReleaseGateBridgeRequest:
    """Normalized A1-to-A2 release-gate request envelope."""

    payload: JsonDict
    request_id: str
    idempotency_key: str
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class ReleaseGateBridgeResult:
    """GradeResult-like A2 response plus bridge metadata."""

    grade_result: JsonDict
    request_id: str
    idempotency_key: str
    transport: str
    status_code: int | None = None
    created_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> JsonDict:
        return {
            "schema_version": PLATFORM_SCHEMA_VERSION,
            "target_contract": A2_RELEASE_GATE_CONTRACT,
            "request_id": self.request_id,
            "idempotency_key": self.idempotency_key,
            "transport": self.transport,
            "status_code": self.status_code,
            "grade_result": _jsonable(self.grade_result),
            "raw_payload_included": False,
            "created_at": self.created_at,
        }


def lifecycle_to_release_gate_request(
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    lifecycle: Mapping[str, Any],
    policy: Mapping[str, Any] | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> ReleaseGateBridgeRequest:
    """Convert an A1 lifecycle snapshot into the canonical A2 release-gate request."""

    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise ValidationError("release gate bridge timeout must be positive")
    rid = str(request_id or f"rgbr_{uuid4().hex}")
    payload = release_gate_bridge_payload(tenant_id=tenant_id, project_id=project_id, run_id=run_id, lifecycle=lifecycle, policy=policy)
    payload["request_id"] = rid
    payload["bridge"] = {
        "transport_contract": A2_RELEASE_GATE_CONTRACT,
        "request_id": rid,
        "timeout_seconds": timeout,
        "idempotency_key_present": True,
    }
    idem = str(idempotency_key or _stable_idempotency_key(payload))
    payload["idempotency_key"] = idem
    return ReleaseGateBridgeRequest(payload=_redact_json(payload), request_id=rid, idempotency_key=idem, timeout_seconds=timeout)


@dataclass(slots=True)
class LocalReleaseGateBridgeClient:
    """Self-host/local callable A2 release-gate client.

    The callable receives the redacted A2 payload and should return either a
    GradeResult-like mapping or an envelope with a ``grade_result`` field.
    Responses are cached by idempotency key to mirror remote idempotency.
    """

    evaluator: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    _cache: dict[str, ReleaseGateBridgeResult] = field(default_factory=dict)

    def evaluate(self, request: ReleaseGateBridgeRequest) -> ReleaseGateBridgeResult:
        cached = self._cache.get(request.idempotency_key)
        if cached is not None:
            return cached
        timeout = request.timeout_seconds or self.timeout_seconds
        if timeout <= 0:
            raise ValidationError("release gate bridge timeout must be positive")
        try:
            raw = self.evaluator(_jsonable(request.payload))
        except TimeoutError as exc:
            raise ReleaseGateBridgeTimeout(str(exc), request_id=request.request_id) from exc
        except Exception as exc:  # noqa: BLE001 - bridge boundary must redact arbitrary local failures.
            raise ReleaseGateBridgeError(str(exc), request_id=request.request_id) from exc
        grade = normalize_grade_result(raw, request_id=request.request_id)
        result = ReleaseGateBridgeResult(
            grade_result=grade,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            transport="local_callable",
            status_code=None,
        )
        self._cache[request.idempotency_key] = result
        return result


@dataclass(slots=True)
class HttpReleaseGateBridgeClient:
    """Standard-library HTTP A2 release-gate client using urllib."""

    endpoint_url: str
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
    user_agent: str = "ashr-a1-release-gate-bridge/1"
    _cache: dict[str, ReleaseGateBridgeResult] = field(default_factory=dict)

    def evaluate(self, request: ReleaseGateBridgeRequest) -> ReleaseGateBridgeResult:
        cached = self._cache.get(request.idempotency_key)
        if cached is not None:
            return cached
        timeout = request.timeout_seconds or self.timeout_seconds
        if timeout <= 0:
            raise ValidationError("release gate bridge timeout must be positive")
        body = json.dumps(request.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        http_request = urllib.request.Request(
            self.endpoint_url,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "accept": "application/json",
                "user-agent": self.user_agent,
                "x-request-id": request.request_id,
                "idempotency-key": request.idempotency_key,
            },
        )
        try:
            with urllib.request.urlopen(http_request, timeout=timeout) as response:  # noqa: S310 - endpoint is explicit user/config input.
                status_code = int(response.getcode() or 0)
                response_body = response.read().decode("utf-8")
        except socket.timeout as exc:
            raise ReleaseGateBridgeTimeout("A2 release gate request timed out", request_id=request.request_id) from exc
        except urllib.error.HTTPError as exc:
            detail = _read_error_body(exc)
            raise ReleaseGateBridgeError(
                f"A2 release gate HTTP {exc.code}: {detail}", request_id=request.request_id, status_code=int(exc.code)
            ) from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, socket.timeout):
                raise ReleaseGateBridgeTimeout("A2 release gate request timed out", request_id=request.request_id) from exc
            raise ReleaseGateBridgeError(f"A2 release gate connection failed: {reason}", request_id=request.request_id) from exc
        except TimeoutError as exc:
            raise ReleaseGateBridgeTimeout("A2 release gate request timed out", request_id=request.request_id) from exc

        try:
            decoded = json.loads(response_body or "{}")
        except json.JSONDecodeError as exc:
            raise ReleaseGateBridgeResponseError("A2 release gate returned non-JSON response", request_id=request.request_id, status_code=status_code) from exc
        grade = normalize_grade_result(decoded, request_id=request.request_id)
        result = ReleaseGateBridgeResult(
            grade_result=grade,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            transport="http",
            status_code=status_code,
        )
        self._cache[request.idempotency_key] = result
        return result


def evaluate_lifecycle_with_release_gate(
    client: LocalReleaseGateBridgeClient | HttpReleaseGateBridgeClient,
    *,
    tenant_id: str,
    project_id: str,
    run_id: str,
    lifecycle: Mapping[str, Any],
    policy: Mapping[str, Any] | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
) -> JsonDict:
    request = lifecycle_to_release_gate_request(
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run_id,
        lifecycle=lifecycle,
        policy=policy,
        request_id=request_id,
        idempotency_key=idempotency_key,
        timeout_seconds=timeout_seconds,
    )
    return client.evaluate(request).to_dict()


def normalize_grade_result(response: Mapping[str, Any], *, request_id: str | None = None) -> JsonDict:
    if not isinstance(response, Mapping):
        raise ReleaseGateBridgeResponseError("A2 release gate response must be an object", request_id=request_id)
    candidate = response.get("grade_result") if isinstance(response.get("grade_result"), Mapping) else response
    if not isinstance(candidate, Mapping):
        raise ReleaseGateBridgeResponseError("A2 release gate grade_result must be an object", request_id=request_id)
    result = _redact_json(candidate)
    required = {"scenario_id", "passed", "score", "label", "reason", "expected", "actual"}
    missing = sorted(required - set(result))
    if missing:
        raise ReleaseGateBridgeResponseError(f"A2 release gate response missing fields: {', '.join(missing)}", request_id=request_id)
    if not isinstance(result.get("passed"), bool):
        raise ReleaseGateBridgeResponseError("A2 release gate response field passed must be boolean", request_id=request_id)
    try:
        score = float(result.get("score"))
    except (TypeError, ValueError) as exc:
        raise ReleaseGateBridgeResponseError("A2 release gate response field score must be numeric", request_id=request_id) from exc
    if score < 0 or score > 1:
        raise ReleaseGateBridgeResponseError("A2 release gate response field score must be between 0 and 1", request_id=request_id)
    if not isinstance(result.get("expected"), Mapping) or not isinstance(result.get("actual"), Mapping):
        raise ReleaseGateBridgeResponseError("A2 release gate response expected/actual must be objects", request_id=request_id)
    result["score"] = score
    result.setdefault("metrics", {})
    return _jsonable(result)


def _stable_idempotency_key(payload: Mapping[str, Any]) -> str:
    stable = dict(payload)
    stable.pop("created_at", None)
    stable.pop("idempotency_key", None)
    encoded = json.dumps(_jsonable(stable), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "rgbi_" + json_hash(encoded)[:32]


def json_hash(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")[:500]
    except Exception:  # noqa: BLE001
        return ""


def _redact_text(text: Any) -> str:
    value = str(text)
    value = _SENSITIVE_VALUE_RE.sub("[REDACTED]", value)
    return value


def _redact_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: JsonDict = {}
        for key, item in value.items():
            key_text = str(key)
            if _SENSITIVE_KEY_RE.search(key_text):
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = _redact_json(item)
        return redacted
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value
