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

ASHR_DEFAULT_BASE_URL = "https://api.ashr.io/testing-platform-api"
ASHR_API_ENV_VAR = "ASHR_API_KEY"
ASHR_LABS_API_ENV_VAR = "ASHR_LABS_API_KEY"
ASHR_LABS_BASE_URL_ENV_VAR = "ASHR_LABS_BASE_URL"
ASHR_API_FIELD_MAP_VERSION = "a1-api-calibration-2026-07-04"
DEFAULT_REQUEST_INPUT_SCHEMA: JsonDict = {"type": "object", "additionalProperties": True}

_REDACTED = "[redacted]"
_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "authorization", "bearer", "secret", "token", "password", "credential")
_SENSITIVE_EXACT_KEYS = {"key"}
_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
_SECRET_LIKE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
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
        purpose: str = "",
        estimated_calls: int = 1,
        mutates: bool = False,
        preflight: Mapping[str, Any] | None = None,
        output_path: str | Path | None = None,
        dry_run: bool = True,
    ) -> JsonDict:
        plan = self.plan(
            function,
            params=params,
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
        params: JsonDict = {"request_name": request_name, "request": dict(request)}
        params["request_input_schema"] = build_default_request_input_schema(request) if request_input_schema is None else dict(request_input_schema)
        if requestor_id is not None:
            params["requestor_id"] = requestor_id
        return self._call_with_session("create_request", params=params, tenant=True, user=requestor_id is None, purpose="Create dataset generation request", estimated_calls=2, mutates=True, **kwargs)

    def list_requests(self, *, limit: int = 5, status: str | None = None, cursor: int | None = None, **kwargs: Any) -> JsonDict:
        params: JsonDict = {"limit": limit}
        if status is not None:
            params["status"] = status
        if cursor is not None:
            params["cursor"] = cursor
        return self._call_with_session("list_requests", params=params, tenant=True, purpose="List generation request shapes", estimated_calls=2, mutates=False, **kwargs)

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
            failure=lambda response: "request failed" if response.get("request", {}).get("request_status") == "failed" else None,
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
        failure: Callable[[JsonDict], str | None],
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
            failure_message = failure(response)
            if failure_message:
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
                    error={"message": failure_message, "status_code": status_code},
                    output_path=str(output_path) if output_path is not None else None,
                )
                payload = record.to_dict()
                maybe_write_json(output_path, payload)
                raise AshrApiError(failure_message, status_code=status_code, response=payload)
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


def build_default_request_input_schema(request: Mapping[str, Any] | None = None) -> JsonDict:
    schema: JsonDict = dict(DEFAULT_REQUEST_INPUT_SCHEMA)
    agent = request.get("agent") if isinstance(request, Mapping) else None
    if isinstance(agent, Mapping) and isinstance(agent.get("tools"), list):
        schema["tools"] = redact_sensitive(agent["tools"])
    return schema


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
