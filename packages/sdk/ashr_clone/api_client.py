from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

JsonDict = dict[str, Any]
TransportResponse = tuple[int, bytes] | tuple[int, bytes, Mapping[str, str]]
Transport = Callable[[str, Mapping[str, str], bytes, int], TransportResponse]
FailureResult = str | Mapping[str, Any] | None

ASHR_DEFAULT_BASE_URL = "https://api.ashr.io/testing-platform-api"
ASHR_API_ENV_VAR = "ASHR_API_KEY"
ASHR_LABS_API_ENV_VAR = "ASHR_LABS_API_KEY"
ASHR_LABS_BASE_URL_ENV_VAR = "ASHR_LABS_BASE_URL"
ASHR_API_FIELD_MAP_VERSION = "a1-api-calibration-2026-07-04"
DEFAULT_REQUEST_INPUT_SCHEMA: JsonDict = {"type": "object", "additionalProperties": True}
AGENT_INPUT_SCHEMA_VERSION = "ashr.clone.agent_input.v1"
AGENT_INPUT_PART_TYPES = ("text", "image", "audio", "file", "video")
_NON_TEXT_AGENT_INPUT_PART_TYPES = ("image", "audio", "file", "video")

_REDACTED = "[redacted]"
_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "authorization", "bearer", "secret", "token", "password", "credential")
_SENSITIVE_EXACT_KEYS = {"key"}
_FAILURE_EXACT_KEYS = {"_failure", "failure", "failures", "failed", "error", "errors", "reason", "reasons", "message", "messages", "detail", "details", "exception", "traceback"}
_FAILURE_KEY_PREFIXES = ("failure_", "error_", "reason_", "message_", "detail_", "exception_", "traceback_")
_FAILURE_KEY_SUFFIXES = ("_failure", "_error", "_reason", "_message", "_detail", "_exception", "_traceback")
_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
_SECRET_LIKE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
)


class MissingAshrApiKeyError(RuntimeError):
    pass


class AshrApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response: Mapping[str, Any] | None = None,
        response_headers: Mapping[str, str] | None = None,
        error_kind: str = "api",
    ) -> None:
        safe_message = redact_text(message)
        super().__init__(safe_message)
        self.message = safe_message
        self.status_code = status_code
        self.response = redact_sensitive(response or {})
        self.response_headers = redact_sensitive(response_headers or {})
        self.error_kind = error_kind

    def to_dict(self) -> JsonDict:
        return {"message": self.message, "status_code": self.status_code, "error_kind": self.error_kind, "response": self.response, "response_headers": self.response_headers}


@dataclass(slots=True)
class AshrApiCallPlan:
    function: str
    params: JsonDict = field(default_factory=dict)
    preflight: JsonDict | None = None
    purpose: str = ""
    estimated_calls: int = 1
    mutates: bool = False
    output_path: str | None = None
    notes: list[str] = field(default_factory=list)
    base_url: str = ASHR_DEFAULT_BASE_URL
    field_map_version: str = ASHR_API_FIELD_MAP_VERSION

    def to_dict(self) -> JsonDict:
        return redact_sensitive(asdict(self))


@dataclass(slots=True)
class AshrApiCallRecord:
    function: str
    dry_run: bool
    purpose: str
    started_at: str
    ended_at: str
    duration_ms: int
    attempts: int
    status: str
    status_code: int | None
    request: JsonDict
    response: JsonDict | None = None
    response_headers: JsonDict = field(default_factory=dict)
    error: JsonDict | None = None
    output_path: str | None = None
    field_map_version: str = ASHR_API_FIELD_MAP_VERSION

    def to_dict(self) -> JsonDict:
        return redact_sensitive(asdict(self))


class AshrApiClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = ASHR_DEFAULT_BASE_URL,
        timeout: int = 30,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
        transport: Transport | None = None,
    ) -> None:
        self._api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._transport = transport or _urlopen_transport
        self._tenant_id: int | None = None
        self._user_id: int | None = None

    @classmethod
    def from_env(cls, *, required: bool = True, **kwargs: Any) -> "AshrApiClient":
        api_key = os.environ.get(ASHR_API_ENV_VAR) or os.environ.get(ASHR_LABS_API_ENV_VAR)
        if "base_url" not in kwargs:
            kwargs["base_url"] = os.environ.get(ASHR_LABS_BASE_URL_ENV_VAR, ASHR_DEFAULT_BASE_URL)
        if required and not api_key:
            raise MissingAshrApiKeyError(f"{ASHR_API_ENV_VAR} or {ASHR_LABS_API_ENV_VAR} environment variable is not set")
        return cls(api_key=api_key, **kwargs)

    def plan(
        self,
        function: str,
        *,
        params: Mapping[str, Any] | None = None,
        purpose: str = "",
        estimated_calls: int = 1,
        mutates: bool = False,
        preflight: Mapping[str, Any] | None = None,
        output_path: str | Path | None = None,
        notes: list[str] | None = None,
    ) -> AshrApiCallPlan:
        return AshrApiCallPlan(
            function=function,
            params=redact_sensitive(params or {}),
            preflight=redact_sensitive(preflight) if preflight is not None else None,
            purpose=purpose,
            estimated_calls=max(1, int(estimated_calls)),
            mutates=mutates,
            output_path=str(output_path) if output_path is not None else None,
            notes=notes or [],
            base_url=self.base_url,
        )

    def call(
        self,
        function: str,
        *,
        params: Mapping[str, Any] | None = None,
        record_params: Mapping[str, Any] | None = None,
        purpose: str = "",
        estimated_calls: int = 1,
        mutates: bool = False,
        preflight: Mapping[str, Any] | None = None,
        output_path: str | Path | None = None,
        dry_run: bool = True,
    ) -> JsonDict:
        plan = self.plan(
            function,
            params=record_params if record_params is not None else params,
            purpose=purpose,
            estimated_calls=estimated_calls,
            mutates=mutates,
            preflight=preflight,
            output_path=output_path,
        )
        request_summary = _request_summary(function, plan.params, plan.estimated_calls, mutates, plan.preflight)
        started = utc_now()
        start = time.monotonic()

        if dry_run:
            record = AshrApiCallRecord(
                function=function,
                dry_run=True,
                purpose=purpose,
                started_at=started,
                ended_at=utc_now(),
                duration_ms=elapsed_ms(start),
                attempts=0,
                status="planned",
                status_code=None,
                request=request_summary,
                response={"plan": plan.to_dict()},
                output_path=str(output_path) if output_path is not None else None,
            )
            payload = record.to_dict()
            maybe_write_json(output_path, payload)
            return payload

        if not self._api_key:
            raise MissingAshrApiKeyError(f"{ASHR_API_ENV_VAR} or {ASHR_LABS_API_ENV_VAR} environment variable is required for non-dry-run calls")

        attempts = 0
        last_error: AshrApiError | None = None
        status_code: int | None = None
        for retry_index in range(self.max_retries + 1):
            attempts += 1
            try:
                status_code, response, response_headers = self._request(function, params or {})
                record = AshrApiCallRecord(
                    function=function,
                    dry_run=False,
                    purpose=purpose,
                    started_at=started,
                    ended_at=utc_now(),
                    duration_ms=elapsed_ms(start),
                    attempts=attempts,
                    status="ok",
                    status_code=status_code,
                    request=request_summary,
                    response=response,
                    response_headers=response_headers,
                    output_path=str(output_path) if output_path is not None else None,
                )
                payload = record.to_dict()
                _attach_response_summary(payload)
                maybe_write_json(output_path, payload)
                return payload
            except AshrApiError as exc:
                last_error = exc
                status_code = exc.status_code
                if status_code not in _RETRYABLE_STATUS_CODES or retry_index >= self.max_retries:
                    break
                time.sleep(self.retry_backoff_seconds * (2 ** retry_index))

        record = AshrApiCallRecord(
            function=function,
            dry_run=False,
            purpose=purpose,
            started_at=started,
            ended_at=utc_now(),
            duration_ms=elapsed_ms(start),
            attempts=attempts,
            status="error",
            status_code=status_code,
            request=request_summary,
            error=last_error.to_dict() if last_error is not None else {"message": "unknown Ashr API error", "status_code": status_code},
            output_path=str(output_path) if output_path is not None else None,
        )
        payload = record.to_dict()
        maybe_write_json(output_path, payload)
        raise AshrApiError(payload["error"]["message"], status_code=status_code, response=payload, error_kind=payload["error"].get("error_kind", "api"))

    def init(self, **kwargs: Any) -> JsonDict:
        return self.call("init", purpose="Resolve Ashr session context", estimated_calls=1, mutates=False, **kwargs)

    def health_check(self, **kwargs: Any) -> JsonDict:
        return self.call("keep_alive", purpose="Check Ashr API reachability", estimated_calls=1, mutates=False, **kwargs)

    def list_datasets(self, *, limit: int = 5, cursor: int | None = None, **kwargs: Any) -> JsonDict:
        params: JsonDict = {"limit": limit, "include_signed_urls": False}
        if cursor is not None:
            params["cursor"] = cursor
        return self._call_with_session("list_datasets", params=params, tenant=True, purpose="List datasets for field calibration", estimated_calls=2, mutates=False, **kwargs)

    def get_dataset(self, dataset_id: int, **kwargs: Any) -> JsonDict:
        return self.call("get_dataset", params={"dataset_id": dataset_id, "include_signed_urls": False}, purpose="Fetch one dataset shape for replay calibration", estimated_calls=2, mutates=False, **kwargs)

    def list_runs(self, *, dataset_id: int | None = None, limit: int = 5, **kwargs: Any) -> JsonDict:
        params: JsonDict = {"limit": limit}
        if dataset_id is not None:
            params["dataset_id"] = dataset_id
        return self._call_with_session("list_runs", params=params, tenant=True, purpose="List run shapes for polling calibration", estimated_calls=2, mutates=False, **kwargs)

    def get_run(self, run_id: int, **kwargs: Any) -> JsonDict:
        return self.call("get_run", params={"run_id": run_id}, purpose="Fetch one run shape for polling calibration", estimated_calls=1, mutates=False, **kwargs)

    def create_run(self, *, dataset_id: int, result: Mapping[str, Any], runner_id: int | None = None, **kwargs: Any) -> JsonDict:
        self._require_zero_retries_for_mutation("create_run", dry_run=bool(kwargs.get("dry_run", True)))
        params: JsonDict = {"dataset_id": dataset_id, "result": dict(result)}
        if runner_id is not None:
            params["runner_id"] = runner_id
        return self._call_with_session("create_run", params=params, tenant=True, purpose="Deploy local run result to Ashr", estimated_calls=2, mutates=True, **kwargs)

    def poll_run(self, *, run_id: int, timeout_seconds: int = 300, poll_interval_seconds: int = 20, **kwargs: Any) -> JsonDict:
        estimated_calls = max(1, int(timeout_seconds / max(1, poll_interval_seconds)) + 1)
        params = {"run_id": run_id, "timeout_seconds": timeout_seconds, "poll_interval_seconds": poll_interval_seconds}
        if kwargs.get("dry_run", True):
            return self.call("poll_run", params=params, purpose="Poll deployed run grading status", estimated_calls=estimated_calls, mutates=False, **kwargs)
        return self._poll_until(
            function="get_run",
            params={"run_id": run_id},
            complete=lambda response: _run_has_result(response.get("run")),
            failure=lambda _response: None,
            purpose="Poll deployed run grading status",
            estimated_calls=estimated_calls,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            **kwargs,
        )

    def create_request(self, *, request_name: str, request: Mapping[str, Any], request_input_schema: Mapping[str, Any] | None = None, requestor_id: int | None = None, **kwargs: Any) -> JsonDict:
        self._require_zero_retries_for_mutation("create_request", dry_run=bool(kwargs.get("dry_run", True)))
        params: JsonDict = {"request_name": request_name, "request": dict(request)}
        params["request_input_schema"] = build_default_request_input_schema(request) if request_input_schema is None else dict(request_input_schema)
        if requestor_id is not None:
            params["requestor_id"] = requestor_id
        preflight = kwargs.get("preflight") if isinstance(kwargs.get("preflight"), Mapping) else None
        record_params = _create_request_record_params(params, preflight=preflight)
        return self._call_with_session("create_request", params=params, record_params=record_params, tenant=True, user=requestor_id is None, purpose="Create dataset generation request", estimated_calls=2, mutates=True, **kwargs)

    def list_requests(self, *, limit: int = 5, status: str | None = None, cursor: int | None = None, **kwargs: Any) -> JsonDict:
        params: JsonDict = {"limit": limit}
        if status is not None:
            params["status"] = status
        if cursor is not None:
            params["cursor"] = cursor
        return self._call_with_session("list_requests", params=params, tenant=True, purpose="List generation request shapes", estimated_calls=2, mutates=False, **kwargs)

    def list_agents(self, **kwargs: Any) -> JsonDict:
        return self.call("list_agents", purpose="List tenant agents for SDK parity calibration", estimated_calls=1, mutates=False, **kwargs)

    def get_request(self, request_id: int, **kwargs: Any) -> JsonDict:
        return self.call("get_request", params={"request_id": request_id}, purpose="Poll one generation request", estimated_calls=1, mutates=False, **kwargs)

    def poll_request(self, *, request_id: int, timeout_seconds: int = 600, poll_interval_seconds: int = 5, **kwargs: Any) -> JsonDict:
        estimated_calls = max(1, int(timeout_seconds / max(1, poll_interval_seconds)) + 1)
        params = {"request_id": request_id, "timeout_seconds": timeout_seconds, "poll_interval_seconds": poll_interval_seconds}
        if kwargs.get("dry_run", True):
            return self.call("poll_request", params=params, purpose="Poll generation request status", estimated_calls=estimated_calls, mutates=False, **kwargs)
        return self._poll_until(
            function="get_request",
            params={"request_id": request_id},
            complete=lambda response: response.get("request", {}).get("request_status") == "completed",
            failure=_request_failure_result,
            purpose="Poll generation request status",
            estimated_calls=estimated_calls,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            **kwargs,
        )

    def _poll_until(
        self,
        *,
        function: str,
        params: Mapping[str, Any],
        complete: Callable[[JsonDict], bool],
        failure: Callable[[JsonDict], FailureResult],
        purpose: str,
        estimated_calls: int,
        timeout_seconds: int,
        poll_interval_seconds: int,
        output_path: str | Path | None = None,
        dry_run: bool = False,
        mutates: bool = False,
    ) -> JsonDict:
        started = utc_now()
        start = time.monotonic()
        attempts = 0
        last_response: JsonDict | None = None
        while True:
            attempts += 1
            status_code, response, response_headers = self._request(function, params)
            last_response = response
            failure_result = failure(response)
            if failure_result:
                failure_error = _poll_failure_error(failure_result, status_code)
                record = AshrApiCallRecord(
                    function=function,
                    dry_run=dry_run,
                    purpose=purpose,
                    started_at=started,
                    ended_at=utc_now(),
                    duration_ms=elapsed_ms(start),
                    attempts=attempts,
                    status="error",
                    status_code=status_code,
                    request={"function": function, "params": redact_sensitive(params), "estimated_calls": estimated_calls, "mutates": mutates},
                    response=response,
                    response_headers=response_headers,
                    error=failure_error,
                    output_path=str(output_path) if output_path is not None else None,
                )
                payload = record.to_dict()
                _attach_response_summary(payload)
                maybe_write_json(output_path, payload)
                raise AshrApiError(failure_error["message"], status_code=status_code, response=payload)
            if complete(response):
                record = AshrApiCallRecord(
                    function=function,
                    dry_run=dry_run,
                    purpose=purpose,
                    started_at=started,
                    ended_at=utc_now(),
                    duration_ms=elapsed_ms(start),
                    attempts=attempts,
                    status="ok",
                    status_code=status_code,
                    request={"function": function, "params": redact_sensitive(params), "estimated_calls": estimated_calls, "mutates": mutates},
                    response=response,
                    response_headers=response_headers,
                    output_path=str(output_path) if output_path is not None else None,
                )
                payload = record.to_dict()
                _attach_response_summary(payload)
                maybe_write_json(output_path, payload)
                return payload
            if (time.monotonic() - start) >= timeout_seconds:
                record = AshrApiCallRecord(
                    function=function,
                    dry_run=dry_run,
                    purpose=purpose,
                    started_at=started,
                    ended_at=utc_now(),
                    duration_ms=elapsed_ms(start),
                    attempts=attempts,
                    status="timeout",
                    status_code=status_code,
                    request={"function": function, "params": redact_sensitive(params), "estimated_calls": estimated_calls, "mutates": mutates},
                    response=last_response,
                    response_headers=response_headers,
                    error={"message": f"{function} did not complete within {timeout_seconds}s", "status_code": status_code},
                    output_path=str(output_path) if output_path is not None else None,
                )
                payload = record.to_dict()
                _attach_response_summary(payload)
                maybe_write_json(output_path, payload)
                raise TimeoutError(payload["error"]["message"])
            time.sleep(max(0, poll_interval_seconds))

    def _call_with_session(
        self,
        function: str,
        *,
        params: Mapping[str, Any],
        tenant: bool = False,
        user: bool = False,
        dry_run: bool = True,
        **kwargs: Any,
    ) -> JsonDict:
        final_params = dict(params)
        if not dry_run and (tenant or user):
            self._ensure_session_context()
            if tenant and "tenant_id" not in final_params:
                final_params["tenant_id"] = self._tenant_id
            if user and "requestor_id" not in final_params and "user_id" not in final_params:
                final_params["requestor_id"] = self._user_id
        return self.call(function, params=final_params, dry_run=dry_run, **kwargs)

    def _ensure_session_context(self) -> None:
        if self._tenant_id is not None and self._user_id is not None:
            return
        if not self._api_key:
            raise MissingAshrApiKeyError(f"{ASHR_API_ENV_VAR} or {ASHR_LABS_API_ENV_VAR} environment variable is required for session resolution")
        _status_code, session, _headers = self._request("init", {})
        user = session.get("user") if isinstance(session.get("user"), Mapping) else {}
        tenant = session.get("tenant") if isinstance(session.get("tenant"), Mapping) else {}
        self._tenant_id = int(tenant["id"])
        self._user_id = int(user["id"])

    def _require_zero_retries_for_mutation(self, function: str, *, dry_run: bool) -> None:
        if not dry_run and self.max_retries != 0:
            raise ValueError(f"{function} execution requires max_retries=0 to avoid duplicate mutation on retry")

    def _request(self, function: str, params: Mapping[str, Any]) -> tuple[int, JsonDict, JsonDict]:
        payload = {"function": function, **dict(params)}
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"}
        status_code, response_body, response_headers = _normalize_transport_response(self._transport(self.base_url, headers, body, self.timeout))
        selected_headers = _selected_response_headers(response_headers)
        response = parse_json_body(response_body)
        if status_code >= 400:
            raise AshrApiError(_error_message(response, f"HTTP {status_code}"), status_code=status_code, response=response, response_headers=selected_headers, error_kind="http")
        if response.get("status") == "error":
            raise AshrApiError(_error_message(response, "Ashr API error"), status_code=status_code, response=response, response_headers=selected_headers, error_kind="api")
        return status_code, response, selected_headers

    def __repr__(self) -> str:
        key_state = "set" if self._api_key else "unset"
        return f"AshrApiClient(base_url='{self.base_url}', api_key={key_state})"


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: JsonDict = {}
        for key, item in value.items():
            text_key = str(key)
            normalized_key = text_key.lower().replace("-", "_")
            if normalized_key in _SENSITIVE_EXACT_KEYS or any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                redacted[text_key] = _REDACTED
            else:
                redacted[text_key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, set):
        return [redact_sensitive(item) for item in sorted(value, key=repr)]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_LIKE_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def summarize_request_failure(response: Mapping[str, Any]) -> JsonDict:
    request = response.get("request") if isinstance(response.get("request"), Mapping) else {}
    nested_request = request.get("request") if isinstance(request.get("request"), Mapping) else {}
    summary: JsonDict = {
        "request_status": request.get("request_status") if isinstance(request.get("request_status"), str) else None,
        "top_level_failure_like_keys": _failure_like_keys(request),
        "nested_request_keys": sorted(str(key) for key in nested_request.keys()) if isinstance(nested_request, Mapping) else [],
    }
    failure_sources: JsonDict = {}
    if isinstance(nested_request, Mapping) and nested_request.get("_failure") is not None:
        failure_sources["request._failure"] = _safe_value_shape(nested_request["_failure"], depth=2)
    if request.get("_failure") is not None:
        failure_sources["_failure"] = _safe_value_shape(request["_failure"], depth=2)
    for key in ("failure", "error", "message", "detail", "reason"):
        if request.get(key) is not None:
            failure_sources[key] = _safe_value_shape(request[key], depth=1)
    if failure_sources:
        summary["failure_sources"] = failure_sources
    return summary



def summarize_quota_error(value: Mapping[str, Any]) -> JsonDict | None:
    """Return a public-safe hosted quota summary from an API record or response."""
    candidates = _quota_candidates(value)
    quota_candidates = [candidate for candidate in candidates if isinstance(candidate, Mapping) and isinstance(candidate.get("quota"), Mapping)]
    message_candidates = [candidate for candidate in candidates if isinstance(candidate, Mapping) and not isinstance(candidate.get("quota"), Mapping)]
    for candidate in quota_candidates + message_candidates:
        quota = candidate.get("quota")
        message = candidate.get("message")
        if isinstance(quota, Mapping):
            summary: JsonDict = {
                "blocked": True,
                "message": redact_text(str(message)) if isinstance(message, str) else None,
                "quota_keys": sorted(str(key) for key in quota.keys()),
            }
            for key in ("resource", "limit", "used", "requested", "remaining"):
                if key in quota and isinstance(quota[key], (str, int, float, bool)):
                    summary[key] = quota[key]
            return redact_sensitive(summary)
        if isinstance(message, str) and "Usage limit exceeded" in message:
            return {"blocked": True, "message": redact_text(message), "quota_keys": []}
    return None


def _quota_candidates(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates: list[Mapping[str, Any]] = [value]
    for key in ("error", "response"):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            candidates.append(nested)
            nested_response = nested.get("response")
            if isinstance(nested_response, Mapping):
                candidates.append(nested_response)
            nested_error = nested.get("error")
            if isinstance(nested_error, Mapping):
                candidates.append(nested_error)
    return candidates

def build_default_request_input_schema(request: Mapping[str, Any] | None = None) -> JsonDict:
    schema: JsonDict = dict(DEFAULT_REQUEST_INPUT_SCHEMA)
    agent = request.get("agent") if isinstance(request, Mapping) else None
    if isinstance(agent, Mapping) and isinstance(agent.get("tools"), list):
        schema["tools"] = redact_sensitive(agent["tools"])
    enabled_part_types = _enabled_agent_input_part_types(request)
    if any(part_type in enabled_part_types for part_type in _NON_TEXT_AGENT_INPUT_PART_TYPES):
        schema.update(_agent_input_schema(enabled_part_types))
    return schema


def _create_request_record_params(params: Mapping[str, Any], *, preflight: Mapping[str, Any] | None = None) -> JsonDict:
    request = params.get("request") if isinstance(params.get("request"), Mapping) else {}
    schema = params.get("request_input_schema") if isinstance(params.get("request_input_schema"), Mapping) else {}
    record: JsonDict = {
        "request_name": params.get("request_name"),
        "request": _generation_request_shape(request),
        "request_input_schema": _schema_shape(schema),
    }
    if "requestor_id" in params:
        record["requestor_id_present"] = params.get("requestor_id") is not None
    if preflight is not None:
        record["preflight_summary"] = redact_sensitive(preflight)
    return record


def _generation_request_shape(request: Mapping[str, Any]) -> JsonDict:
    agent = request.get("agent") if isinstance(request.get("agent"), Mapping) else {}
    generation_options = request.get("generation_options") if isinstance(request.get("generation_options"), Mapping) else {}
    test_config = request.get("test_config") if isinstance(request.get("test_config"), Mapping) else {}
    metadata = request.get("metadata") if isinstance(request.get("metadata"), Mapping) else {}
    accepted_inputs = agent.get("accepted_inputs") if isinstance(agent, Mapping) and isinstance(agent.get("accepted_inputs"), Mapping) else {}
    return {
        "top_level_keys": sorted(str(key) for key in request.keys()),
        "agent_keys": sorted(str(key) for key in agent.keys()) if isinstance(agent, Mapping) else [],
        "agent_name_present": bool(agent.get("name")) if isinstance(agent, Mapping) else False,
        "tools_count": len(agent.get("tools", [])) if isinstance(agent, Mapping) and isinstance(agent.get("tools"), list) else 0,
        "accepted_input_flags": {key: _truthy_enabled(accepted_inputs.get(key)) for key in ("text", "audio", "file", "image", "video", "conversation")},
        "generation_options": {key: bool(generation_options.get(key)) for key in ("generate_audio", "generate_files", "generate_images", "generate_videos", "generate_simulations")},
        "metadata_keys": sorted(str(key) for key in metadata.keys()) if isinstance(metadata, Mapping) else [],
        "test_config_keys": sorted(str(key) for key in test_config.keys()) if isinstance(test_config, Mapping) else [],
        "num_variations": test_config.get("num_variations") if isinstance(test_config, Mapping) else None,
    }


def _schema_shape(schema: Mapping[str, Any]) -> JsonDict:
    properties = schema.get("properties") if isinstance(schema.get("properties"), Mapping) else {}
    defs = schema.get("$defs") if isinstance(schema.get("$defs"), Mapping) else {}
    agent_input_parts = defs.get("agent_input_part") if isinstance(defs.get("agent_input_part"), Mapping) else {}
    return {
        "keys": sorted(str(key) for key in schema.keys()),
        "type": schema.get("type"),
        "additionalProperties": schema.get("additionalProperties"),
        "tools_count": len(schema.get("tools", [])) if isinstance(schema.get("tools"), list) else 0,
        "property_keys": sorted(str(key) for key in properties.keys()),
        "defs_keys": sorted(str(key) for key in defs.keys()),
        "agent_input_schema_version": properties.get("schema_version", {}).get("const") if isinstance(properties.get("schema_version"), Mapping) else None,
        "agent_input_part_types": _schema_agent_input_part_types(agent_input_parts),
    }


def _truthy_enabled(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value.get("enabled"))
    return bool(value)


def _enabled_agent_input_part_types(request: Mapping[str, Any] | None) -> list[str]:
    agent = request.get("agent") if isinstance(request, Mapping) else None
    accepted_inputs = agent.get("accepted_inputs") if isinstance(agent, Mapping) and isinstance(agent.get("accepted_inputs"), Mapping) else None
    enabled: list[str] = []
    if accepted_inputs is None or _truthy_enabled(accepted_inputs.get("text")):
        enabled.append("text")
    for part_type in _NON_TEXT_AGENT_INPUT_PART_TYPES:
        if accepted_inputs is not None and _truthy_enabled(accepted_inputs.get(part_type)):
            enabled.append(part_type)
    return enabled


def _agent_input_schema(enabled_part_types: list[str]) -> JsonDict:
    part_types = [part_type for part_type in AGENT_INPUT_PART_TYPES if part_type in set(enabled_part_types)]
    return {
        "properties": {
            "schema_version": {"const": AGENT_INPUT_SCHEMA_VERSION},
            "text": {"type": "string"},
            "parts": {"type": "array", "items": {"$ref": "#/$defs/agent_input_part"}},
            "metadata": {"type": "object"},
        },
        "$defs": {"agent_input_part": _agent_input_part_schema(part_types)},
    }


def _agent_input_part_schema(part_types: list[str]) -> JsonDict:
    text_part: JsonDict = {
        "type": "object",
        "required": ["type", "text"],
        "properties": {"type": {"const": "text"}, "text": {"type": "string"}},
        "additionalProperties": True,
    }
    media_part_types = [part_type for part_type in part_types if part_type in _NON_TEXT_AGENT_INPUT_PART_TYPES]
    variants: list[JsonDict] = []
    if "text" in part_types:
        variants.append(text_part)
    if media_part_types:
        variants.append(
            {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {"enum": media_part_types},
                    "path": {"type": "string"},
                    "url": {"type": "string"},
                    "source": {"type": "string"},
                    "mime_type": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "additionalProperties": True,
            }
        )
    if not variants:
        return text_part
    if len(variants) == 1:
        return variants[0]
    return {"oneOf": variants}


def _schema_agent_input_part_types(part_schema: Mapping[str, Any]) -> list[str]:
    if part_schema.get("properties") and isinstance(part_schema.get("properties"), Mapping):
        part_type_schema = part_schema["properties"].get("type")
        if isinstance(part_type_schema, Mapping):
            if part_type_schema.get("const"):
                return [str(part_type_schema["const"])]
            enum = part_type_schema.get("enum")
            if isinstance(enum, list):
                return sorted(str(item) for item in enum)
    types: set[str] = set()
    for variant in part_schema.get("oneOf", []) if isinstance(part_schema.get("oneOf"), list) else []:
        if not isinstance(variant, Mapping):
            continue
        properties = variant.get("properties") if isinstance(variant.get("properties"), Mapping) else {}
        part_type_schema = properties.get("type") if isinstance(properties.get("type"), Mapping) else {}
        if part_type_schema.get("const"):
            types.add(str(part_type_schema["const"]))
        enum = part_type_schema.get("enum")
        if isinstance(enum, list):
            types.update(str(item) for item in enum)
    return sorted(types)


def _request_failure_result(response: JsonDict) -> JsonDict | None:
    request = response.get("request") if isinstance(response.get("request"), Mapping) else {}
    if request.get("request_status") != "failed":
        return None
    return {"message": "request failed", "failure_summary": summarize_request_failure(response)}


def _poll_failure_error(failure_result: str | Mapping[str, Any], status_code: int | None) -> JsonDict:
    if isinstance(failure_result, Mapping):
        error = redact_sensitive(dict(failure_result))
        message = error.get("message")
        if not isinstance(message, str) or not message:
            message = "request failed"
        error["message"] = redact_text(message)
        error["status_code"] = status_code
        return error
    return {"message": redact_text(str(failure_result)), "status_code": status_code}


def _attach_response_summary(payload: JsonDict) -> None:
    response = payload.get("response")
    if not isinstance(response, Mapping):
        return
    request_failure = summarize_request_failure(response)
    if _has_request_failure_summary(request_failure):
        response_summary = payload.setdefault("response_summary", {})
        if isinstance(response_summary, dict):
            response_summary["request_failure"] = request_failure


def _has_request_failure_summary(summary: Mapping[str, Any]) -> bool:
    return (
        summary.get("request_status") == "failed"
        or bool(summary.get("top_level_failure_like_keys"))
        or bool(summary.get("failure_sources"))
    )


def _failure_like_keys(value: Mapping[str, Any]) -> list[str]:
    return sorted(str(key) for key in value.keys() if _is_failure_like_key(str(key)))


def _is_failure_like_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _FAILURE_EXACT_KEYS or normalized.startswith(_FAILURE_KEY_PREFIXES) or normalized.endswith(_FAILURE_KEY_SUFFIXES)


def _safe_value_shape(value: Any, *, depth: int) -> JsonDict:
    shape: JsonDict = {"type": _safe_type_name(value), "present": value is not None}
    if isinstance(value, Mapping):
        shape["keys"] = sorted(str(key) for key in value.keys())
        if depth > 0:
            shape["fields"] = {str(key): _safe_value_shape(item, depth=depth - 1) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    elif isinstance(value, list):
        shape["count"] = len(value)
        shape["item_types"] = sorted({_safe_type_name(item) for item in value})
    elif isinstance(value, str):
        shape["length"] = len(value)
    return shape


def _safe_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def maybe_write_json(path: str | Path | None, payload: Mapping[str, Any]) -> None:
    if path is None:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(redact_sensitive(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_json_body(body: bytes) -> JsonDict:
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AshrApiError(f"Invalid JSON response: {exc}", error_kind="client") from exc
    if not isinstance(data, dict):
        raise AshrApiError(f"Expected JSON object response, got {type(data).__name__}", error_kind="client")
    return data


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _request_summary(function: str, params: JsonDict, estimated_calls: int, mutates: bool, preflight: JsonDict | None = None) -> JsonDict:
    summary: JsonDict = {"function": function, "params": params, "estimated_calls": estimated_calls, "mutates": mutates}
    if preflight is not None:
        summary["preflight"] = preflight
    return summary


def _urlopen_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: int) -> TransportResponse:
    request = Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items()) if exc.headers else {}
    except URLError as exc:
        raise AshrApiError(f"Network error: {exc.reason}", error_kind="network") from exc
    except TimeoutError as exc:
        raise AshrApiError("Request timed out", error_kind="network") from exc


def _normalize_transport_response(response: TransportResponse) -> tuple[int, bytes, Mapping[str, str]]:
    if len(response) == 2:
        status_code, body = response
        return status_code, body, {}
    status_code, body, headers = response
    return status_code, body, headers


def _selected_response_headers(headers: Mapping[str, str]) -> JsonDict:
    selected: JsonDict = {}
    for key, value in headers.items():
        lower_key = key.lower()
        if lower_key == "retry-after" or lower_key.startswith("x-ratelimit"):
            selected[key] = value
    return selected


def _error_message(response: Mapping[str, Any], fallback: str) -> str:
    for key in ("message", "error", "detail"):
        value = response.get(key)
        if isinstance(value, str) and value:
            return redact_text(value)
    return fallback


def _run_has_result(run: Any) -> bool:
    if not isinstance(run, Mapping):
        return False
    result = run.get("result")
    if not isinstance(result, Mapping):
        return False
    if result.get("aggregate_metrics") is not None:
        return True
    return any(key in result for key in ("status", "total_cases", "passed", "failed", "errored", "timed_out", "trace_completeness"))
