from __future__ import annotations

import json
import re
import time
from datetime import datetime
from hashlib import sha256
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .adapter import AgentInput

MODEL_INPUT_PART_TYPES = frozenset({"text", "image", "audio", "file", "video"})
MODEL_PROVIDERS = frozenset({"openai_compatible", "ollama"})
MODEL_CAPABILITIES = frozenset({"text", "image", "audio", "file", "video", "stream", "tools", "usage"})
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"https?://[^\s?#]+\?[^\s]+"),
)


@dataclass(slots=True)
class ModelHTTPResponse:
    status_code: int
    body: bytes | str | Mapping[str, Any] | Iterable[bytes | str | Mapping[str, Any]]
    headers: Mapping[str, str] = field(default_factory=dict)


class ModelHTTPTransport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
        stream: bool,
    ) -> ModelHTTPResponse: ...


@dataclass(slots=True)
class ModelInputPart:
    type: str
    text: str | None = None
    url: str | None = None
    data: str | None = None
    media_type: str | None = None
    filename: str | None = None

    @classmethod
    def from_value(cls, value: str | Mapping[str, Any] | "ModelInputPart") -> "ModelInputPart":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(type="text", text=value)
        if not isinstance(value, Mapping):
            raise ModelAdapterError("invalid_input", "model input part must be text or a mapping")
        part_type = str(value.get("type") or "text").lower()
        if part_type not in MODEL_INPUT_PART_TYPES:
            raise ModelAdapterError("invalid_input", f"unsupported model input part type: {part_type}")
        media_type = value.get("media_type", value.get("mime_type", value.get("mimeType")))
        return cls(
            type=part_type,
            text=str(value.get("text", value.get("content", ""))) if part_type == "text" else None,
            url=_optional_string(value.get("url", value.get("path"))),
            data=_optional_string(value.get("data", value.get("base64"))),
            media_type=_optional_string(media_type),
            filename=_optional_string(value.get("filename", value.get("name"))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in {
            "type": self.type, "text": self.text, "url": self.url, "data": self.data,
            "media_type": self.media_type, "filename": self.filename,
        }.items() if value is not None}


@dataclass(slots=True)
class ModelMessage:
    role: str
    parts: list[ModelInputPart]
    name: str | None = None
    tool_call_id: str | None = None

    @classmethod
    def from_value(cls, value: "ModelMessage" | Mapping[str, Any] | AgentInput | str) -> "ModelMessage":
        if isinstance(value, cls):
            return value
        if isinstance(value, AgentInput):
            envelope = value.to_dict()
            return cls("user", [ModelInputPart.from_value(part) for part in envelope["parts"]])
        if isinstance(value, str):
            return cls("user", [ModelInputPart("text", text=value)])
        if not isinstance(value, Mapping):
            raise ModelAdapterError("invalid_input", "model message must be text, AgentInput, or a mapping")
        role = str(value.get("role") or "user")
        raw_parts = value.get("parts", value.get("content", []))
        if isinstance(raw_parts, str):
            raw_parts = [raw_parts]
        if not isinstance(raw_parts, (list, tuple)):
            raw_parts = [raw_parts]
        return cls(
            role=role,
            parts=[ModelInputPart.from_value(part) for part in raw_parts],
            name=_optional_string(value.get("name")),
            tool_call_id=_optional_string(value.get("tool_call_id")),
        )


@dataclass(slots=True)
class ModelToolCall:
    id: str
    name: str
    arguments: Any
    type: str = "function"


@dataclass(slots=True)
class ModelUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class ModelStreamChunk:
    text: str = ""
    tool_calls: list[ModelToolCall] = field(default_factory=list)
    usage: ModelUsage | None = None
    finish_reason: str | None = None
    raw: Any = None


@dataclass(slots=True)
class ModelResponse:
    text: str
    tool_calls: list[ModelToolCall] = field(default_factory=list)
    usage: ModelUsage = field(default_factory=ModelUsage)
    finish_reason: str = "unknown"
    model: str | None = None
    raw: Any = None


@dataclass(frozen=True, slots=True)
class ModelCapabilityCalibration:
    provider: str
    model: str
    endpoint_sha256: str
    calibrated_at: str
    evidence_sha256: str
    capabilities: Mapping[str, str]


def create_capability_calibration(
    *,
    provider: str,
    model: str,
    base_url: str,
    calibrated_at: str,
    evidence: bytes | str,
    capabilities: Mapping[str, str],
) -> ModelCapabilityCalibration:
    if provider not in MODEL_PROVIDERS:
        raise ValueError("unsupported provider")
    if not model.strip() or not base_url.startswith(("http://", "https://")):
        raise ValueError("model and HTTP(S) base_url are required")
    normalized = dict(capabilities)
    if not normalized or set(normalized) - MODEL_CAPABILITIES:
        raise ValueError("unsupported or empty capability calibration")
    if set(normalized.values()) - {"callable", "failed", "unsupported"}:
        raise ValueError("calibrated capabilities require terminal evidence states")
    evidence_bytes = evidence.encode("utf-8") if isinstance(evidence, str) else evidence
    if not evidence_bytes:
        raise ValueError("calibration evidence is required")
    try:
        parsed_at = datetime.fromisoformat(calibrated_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("calibrated_at must be a valid timezone-aware ISO-8601 timestamp") from exc
    if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
        raise ValueError("calibrated_at must be a valid timezone-aware ISO-8601 timestamp")
    return ModelCapabilityCalibration(
        provider=provider,
        model=model,
        endpoint_sha256=sha256(base_url.rstrip("/").encode("utf-8")).hexdigest(),
        calibrated_at=calibrated_at,
        evidence_sha256=sha256(evidence_bytes).hexdigest(),
        capabilities=MappingProxyType(normalized),
    )


class ModelAdapterError(RuntimeError):
    def __init__(self, kind: str, message: str, *, status_code: int | None = None, retryable: bool = False):
        self.kind = kind
        self.status_code = status_code
        self.retryable = retryable
        self.message = _redact(message)
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "status_code": self.status_code, "retryable": self.retryable}


class ProviderNeutralModelAdapter:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None = None,
        transport: ModelHTTPTransport | None = None,
        timeout: float = 30,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
        default_headers: Mapping[str, str] | None = None,
    ):
        if provider not in MODEL_PROVIDERS:
            raise ModelAdapterError("configuration", f"unsupported provider: {provider}")
        if not model.strip():
            raise ModelAdapterError("configuration", "model is required")
        if not base_url.startswith(("http://", "https://")):
            raise ModelAdapterError("configuration", "base_url must use http or https")
        self.provider = provider
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport or _urlopen_transport
        self.timeout = float(timeout)
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self.default_headers = dict(default_headers or {})

    @classmethod
    def for_openai_compatible(cls, *, model: str, base_url: str, **kwargs: Any) -> "ProviderNeutralModelAdapter":
        return cls(provider="openai_compatible", model=model, base_url=base_url, **kwargs)

    @classmethod
    def for_ollama(cls, *, model: str, base_url: str = "http://localhost:11434", **kwargs: Any) -> "ProviderNeutralModelAdapter":
        return cls(provider="ollama", model=model, base_url=base_url, **kwargs)

    def complete(
        self,
        messages: Iterable[ModelMessage | Mapping[str, Any] | AgentInput | str],
        *,
        tools: Iterable[Mapping[str, Any]] | None = None,
        tool_choice: Any = None,
        timeout: float | None = None,
        **options: Any,
    ) -> ModelResponse:
        payload = self._payload(messages, tools=tools, tool_choice=tool_choice, stream=False, options=options)
        response = self._request(payload, stream=False, timeout=timeout)
        data = _decode_json_body(response.body)
        return _parse_complete(self.provider, data)

    def stream(
        self,
        messages: Iterable[ModelMessage | Mapping[str, Any] | AgentInput | str],
        *,
        tools: Iterable[Mapping[str, Any]] | None = None,
        tool_choice: Any = None,
        timeout: float | None = None,
        **options: Any,
    ) -> Iterator[ModelStreamChunk]:
        payload = self._payload(messages, tools=tools, tool_choice=tool_choice, stream=True, options=options)
        response = self._request(payload, stream=True, timeout=timeout)
        events = _iter_events(response.body, self.provider)
        tool_state: dict[int, ModelToolCall] = {}
        try:
            for event in events:
                chunk = _parse_stream_event(self.provider, event)
                if chunk is not None:
                    if chunk.tool_calls:
                        chunk.tool_calls = _merge_stream_tool_calls(event, chunk.tool_calls, tool_state)
                    yield chunk
        except ModelAdapterError:
            raise
        except Exception as exc:
            raise _normalize_exception(exc) from exc

    def _request(self, payload: Mapping[str, Any], *, stream: bool, timeout: float | None) -> ModelHTTPResponse:
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream" if stream and self.provider == "openai_compatible" else "application/json", **self.default_headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request_timeout = self.timeout if timeout is None else float(timeout)
        url = self.base_url + ("/chat/completions" if self.provider == "openai_compatible" else "/api/chat")
        for attempt in range(self.max_retries + 1):
            try:
                response = self._transport("POST", url, headers, body, request_timeout, stream)
                if not isinstance(response, ModelHTTPResponse):
                    raise ModelAdapterError("transport", "transport must return ModelHTTPResponse")
                if 200 <= response.status_code < 300:
                    return response
                retryable = response.status_code in RETRYABLE_STATUS_CODES
                error = ModelAdapterError("http", f"model provider returned HTTP {response.status_code}", status_code=response.status_code, retryable=retryable)
            except Exception as exc:
                error = exc if isinstance(exc, ModelAdapterError) else _normalize_exception(exc)
                retryable = error.retryable
            if not retryable or attempt >= self.max_retries:
                raise error
            if self.retry_backoff_seconds:
                time.sleep(self.retry_backoff_seconds * (2 ** attempt))
        raise ModelAdapterError("transport", "model request failed")

    def _payload(self, messages: Iterable[Any], *, tools: Iterable[Mapping[str, Any]] | None, tool_choice: Any, stream: bool, options: Mapping[str, Any]) -> dict[str, Any]:
        normalized = [ModelMessage.from_value(message) for message in messages]
        if not normalized:
            raise ModelAdapterError("invalid_input", "at least one model message is required")
        encoded = [_encode_message(self.provider, message) for message in normalized]
        payload: dict[str, Any] = {"model": self.model, "messages": encoded, "stream": stream}
        if tools:
            payload["tools"] = list(tools)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if self.provider == "ollama":
            payload["options"] = dict(options)
        else:
            payload.update(options)
            if stream:
                payload.setdefault("stream_options", {"include_usage": True})
        return payload


def _encode_message(provider: str, message: ModelMessage) -> dict[str, Any]:
    result: dict[str, Any] = {"role": message.role}
    if message.name:
        result["name"] = message.name
    if message.tool_call_id:
        result["tool_call_id"] = message.tool_call_id
    if provider == "ollama":
        texts = [part.text or "" for part in message.parts if part.type == "text"]
        images = [_part_reference(part) for part in message.parts if part.type in {"image", "video"}]
        attachments = [part.to_dict() for part in message.parts if part.type in {"audio", "file", "video"}]
        result["content"] = "\n".join(filter(None, texts))
        if images:
            result["images"] = images
        if attachments:
            result["attachments"] = attachments
        return result
    content: list[dict[str, Any]] = []
    for part in message.parts:
        if part.type == "text":
            content.append({"type": "text", "text": part.text or ""})
        elif part.type == "image":
            content.append({"type": "image_url", "image_url": {"url": _part_reference(part)}})
        else:
            item = part.to_dict()
            item["type"] = f"input_{part.type}"
            content.append(item)
    result["content"] = content
    return result


def _part_reference(part: ModelInputPart) -> str:
    if part.url:
        return part.url
    if part.data:
        return f"data:{part.media_type or 'application/octet-stream'};base64,{part.data}"
    raise ModelAdapterError("invalid_input", f"{part.type} input requires url/path or data/base64")


def _parse_complete(provider: str, data: Mapping[str, Any]) -> ModelResponse:
    try:
        if provider == "openai_compatible":
            choice = data["choices"][0]
            message = choice.get("message") or {}
            return ModelResponse(
                text=_content_text(message.get("content")),
                tool_calls=_parse_tool_calls(message.get("tool_calls")),
                usage=_usage(data.get("usage")),
                finish_reason=_finish_reason(choice.get("finish_reason")),
                model=_optional_string(data.get("model")),
                raw=data,
            )
        message = data.get("message") or {}
        usage = {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
        }
        return ModelResponse(
            text=_content_text(message.get("content")),
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
            usage=_usage(usage),
            finish_reason=_finish_reason(data.get("done_reason") or ("stop" if data.get("done") else None)),
            model=_optional_string(data.get("model")),
            raw=data,
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelAdapterError("malformed_response", "model provider response has an invalid shape") from exc


def _parse_stream_event(provider: str, data: Mapping[str, Any]) -> ModelStreamChunk | None:
    if provider == "openai_compatible":
        choices = data.get("choices") or []
        if not choices:
            usage = _usage(data.get("usage"))
            return ModelStreamChunk(usage=usage, raw=data) if usage.total_tokens else None
        choice = choices[0]
        delta = choice.get("delta") or {}
        return ModelStreamChunk(
            text=_content_text(delta.get("content")),
            tool_calls=_parse_tool_calls(delta.get("tool_calls"), allow_fragments=True),
            usage=_usage(data.get("usage")) if data.get("usage") else None,
            finish_reason=_finish_reason(choice.get("finish_reason")) if choice.get("finish_reason") else None,
            raw=data,
        )
    message = data.get("message") or {}
    usage = None
    if data.get("done"):
        usage = _usage({"prompt_tokens": data.get("prompt_eval_count", 0), "completion_tokens": data.get("eval_count", 0)})
    return ModelStreamChunk(
        text=_content_text(message.get("content")),
        tool_calls=_parse_tool_calls(message.get("tool_calls"), allow_fragments=True),
        usage=usage,
        finish_reason=_finish_reason(data.get("done_reason") or "stop") if data.get("done") else None,
        raw=data,
    )


def _parse_tool_calls(value: Any, *, allow_fragments: bool = False) -> list[ModelToolCall]:
    calls: list[ModelToolCall] = []
    for index, item in enumerate(value or []):
        function = item.get("function") or {}
        raw_arguments = function.get("arguments", item.get("arguments", {}))
        arguments: Any = raw_arguments
        if isinstance(raw_arguments, str) and not allow_fragments:
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = raw_arguments
        calls.append(ModelToolCall(
            id=str(item.get("id") or item.get("index") or f"call_{index}"),
            name=str(function.get("name") or item.get("name") or ""),
            arguments=arguments,
            type=str(item.get("type") or "function"),
        ))
    return calls


def _merge_stream_tool_calls(
    event: Mapping[str, Any],
    fragments: list[ModelToolCall],
    state: dict[int, ModelToolCall],
) -> list[ModelToolCall]:
    raw_calls = _raw_stream_tool_calls(event)
    merged: list[ModelToolCall] = []
    for position, fragment in enumerate(fragments):
        raw = raw_calls[position] if position < len(raw_calls) else {}
        index = int(raw.get("index", position) or 0)
        previous = state.get(index)
        if previous is None:
            previous = ModelToolCall(id=fragment.id, name=fragment.name, arguments="", type=fragment.type)
        call_id = fragment.id if not fragment.id.startswith("call_") else previous.id
        name = fragment.name or previous.name
        if isinstance(previous.arguments, str) and isinstance(fragment.arguments, str):
            arguments: Any = previous.arguments + fragment.arguments
        else:
            arguments = fragment.arguments if fragment.arguments not in ("", None, {}) else previous.arguments
        current = ModelToolCall(id=call_id, name=name, arguments=arguments, type=fragment.type or previous.type)
        state[index] = current
        merged.append(current)
    return merged


def _raw_stream_tool_calls(event: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    choices = event.get("choices")
    if isinstance(choices, list) and choices:
        delta = choices[0].get("delta") if isinstance(choices[0], Mapping) else None
        value = delta.get("tool_calls") if isinstance(delta, Mapping) else None
    else:
        message = event.get("message")
        value = message.get("tool_calls") if isinstance(message, Mapping) else None
    return [item for item in (value or []) if isinstance(item, Mapping)]


def _usage(value: Any) -> ModelUsage:
    value = value if isinstance(value, Mapping) else {}
    input_tokens = int(value.get("prompt_tokens", value.get("input_tokens", 0)) or 0)
    output_tokens = int(value.get("completion_tokens", value.get("output_tokens", 0)) or 0)
    return ModelUsage(input_tokens, output_tokens, int(value.get("total_tokens", input_tokens + output_tokens) or 0))


def _finish_reason(value: Any) -> str:
    return str(value) if value not in (None, "") else "unknown"


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) for item in value if isinstance(item, Mapping))
    return ""


def _iter_events(body: Any, provider: str) -> Iterator[Mapping[str, Any]]:
    source = body if not isinstance(body, (bytes, str, Mapping)) else [body]
    buffer = ""
    for piece in source:
        if isinstance(piece, Mapping):
            yield piece
            continue
        buffer += piece.decode("utf-8") if isinstance(piece, bytes) else str(piece)
        separator = "\n\n" if provider == "openai_compatible" else "\n"
        while separator in buffer:
            raw, buffer = buffer.split(separator, 1)
            event = _decode_event(raw, provider)
            if event is not None:
                yield event
    if buffer.strip():
        event = _decode_event(buffer, provider)
        if event is not None:
            yield event


def _decode_event(raw: str, provider: str) -> Mapping[str, Any] | None:
    text = raw.strip()
    if provider == "openai_compatible":
        lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        if not lines:
            return None
        text = "\n".join(lines)
        if text == "[DONE]":
            return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelAdapterError("malformed_response", "model stream contained malformed JSON") from exc
    if not isinstance(value, Mapping):
        raise ModelAdapterError("malformed_response", "model stream event must be an object")
    return value


def _decode_json_body(body: Any) -> Mapping[str, Any]:
    if isinstance(body, Mapping):
        return body
    if not isinstance(body, (bytes, str)):
        body = b"".join(piece if isinstance(piece, bytes) else str(piece).encode() for piece in body)
    try:
        value = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ModelAdapterError("malformed_response", "model provider returned malformed JSON") from exc
    if not isinstance(value, Mapping):
        raise ModelAdapterError("malformed_response", "model provider response must be an object")
    return value


def _normalize_exception(exc: Exception) -> ModelAdapterError:
    if isinstance(exc, (TimeoutError,)):
        return ModelAdapterError("timeout", "model provider request timed out", retryable=True)
    if isinstance(exc, HTTPError):
        return ModelAdapterError("http", f"model provider returned HTTP {exc.code}", status_code=exc.code, retryable=exc.code in RETRYABLE_STATUS_CODES)
    if isinstance(exc, (URLError, ConnectionError, OSError)):
        return ModelAdapterError("network", f"model provider network failure: {exc}", retryable=True)
    return ModelAdapterError("transport", f"model provider transport failure: {exc}")


def _redact(value: str) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _urlopen_transport(method: str, url: str, headers: Mapping[str, str], body: bytes, timeout: float, stream: bool) -> ModelHTTPResponse:
    request = Request(url, data=body, headers=dict(headers), method=method)
    try:
        response = urlopen(request, timeout=timeout)
        if stream:
            return ModelHTTPResponse(response.status, response, dict(response.headers))
        with response:
            return ModelHTTPResponse(response.status, response.read(), dict(response.headers))
    except HTTPError as exc:
        return ModelHTTPResponse(exc.code, exc.read(), dict(exc.headers or {}))
