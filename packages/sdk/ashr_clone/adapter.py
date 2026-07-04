from __future__ import annotations

import asyncio
import copy
import inspect
import json
import re
import threading
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Mapping

from .types import JsonDict, ToolCall

AGENT_TURN_SCHEMA_VERSION = "ashr.clone.agent_turn.v1"
AGENT_INPUT_SCHEMA_VERSION = "ashr.clone.agent_input.v1"
AGENT_INPUT_STYLES = {"text", "request", "keyword"}
AGENT_INPUT_PART_TYPES = {"text", "image", "audio", "file"}

_REDACTED = "[redacted]"
_SENSITIVE_KEY_PARTS = ("api_key", "apikey", "authorization", "bearer", "secret", "token", "password", "credential")
_SENSITIVE_EXACT_KEYS = {"key"}
_SIGNED_URL_PATTERN = re.compile(r"https?://[^\s?#]+(?:\?[^\s]*)", re.IGNORECASE)
_SECRET_LIKE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
)


class AgentAdapterError(RuntimeError):
    """Raised when an agent cannot be adapted."""


@dataclass(slots=True)
class AgentResult:
    text: str
    tool_calls: list[JsonDict] = field(default_factory=list)
    raw: Any = None
    status: str = "ok"
    latency_ms: int = 0
    error: JsonDict | None = None
    metadata: JsonDict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.error is None

    def copy(self) -> "AgentResult":
        return AgentResult(
            text=self.text,
            tool_calls=copy.deepcopy(self.tool_calls),
            raw=self.raw,
            status=self.status,
            latency_ms=self.latency_ms,
            error=copy.deepcopy(self.error),
            metadata=copy.deepcopy(self.metadata),
        )

    def to_dict(self) -> JsonDict:
        data = {
            "schema_version": AGENT_TURN_SCHEMA_VERSION,
            "text": _jsonable(self.text),
            "tool_calls": _jsonable(self.tool_calls),
            "status": _jsonable(self.status),
            "latency_ms": _jsonable(self.latency_ms),
            "metadata": _jsonable(self.metadata),
        }
        if self.error:
            data["error"] = _jsonable(self.error)
        return data


AgentTurn = AgentResult


@dataclass(slots=True)
class AgentInput:
    text: str = ""
    parts: list[JsonDict] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    @classmethod
    def from_text(cls, text: Any, *, metadata: Mapping[str, Any] | None = None) -> "AgentInput":
        return cls(text=_text_value(text), metadata=_jsonable(dict(metadata or {})))

    @classmethod
    def from_parts(cls, parts: Any, *, text: Any = "", metadata: Mapping[str, Any] | None = None) -> "AgentInput":
        return cls(text=_text_value(text), parts=_normalize_input_parts(parts), metadata=_jsonable(dict(metadata or {})))

    def copy(self) -> "AgentInput":
        return AgentInput(text=self.text, parts=copy.deepcopy(self.parts), metadata=copy.deepcopy(self.metadata))

    def to_dict(self) -> JsonDict:
        parts = copy.deepcopy(self.parts)
        if not parts and self.text:
            parts = [{"type": "text", "text": self.text}]
        text = self.text or _text_from_input_parts(parts)
        return {
            "schema_version": AGENT_INPUT_SCHEMA_VERSION,
            "text": _jsonable(text),
            "parts": _jsonable(parts),
            "metadata": _jsonable(self.metadata),
        }


def coerce_agent_input(value: Any, *, parts: Any = None, metadata: Mapping[str, Any] | None = None) -> AgentInput:
    if isinstance(value, AgentInput):
        agent_input = value.copy()
    elif isinstance(value, Mapping) and value.get("schema_version") == AGENT_INPUT_SCHEMA_VERSION:
        agent_input = AgentInput(
            text=_text_value(value.get("text", "")),
            parts=_normalize_input_parts(value.get("parts", [])),
            metadata=dict(value.get("metadata")) if isinstance(value.get("metadata"), Mapping) else {},
        )
    else:
        agent_input = AgentInput(text=_text_value(value))
    if parts is not None:
        agent_input.parts = _normalize_input_parts(parts)
    if metadata:
        agent_input.metadata.update(_jsonable(dict(metadata)))
    return agent_input


def to_a2_judge_run(
    agent_output: AgentResult | Mapping[str, Any],
    *,
    expected_keywords: list[str] | tuple[str, ...] | None = None,
    forbidden_keywords: list[str] | tuple[str, ...] | None = None,
) -> JsonDict:
    """Project an A1 agent turn into A2's local judge run shape."""
    output = agent_output.to_dict() if isinstance(agent_output, AgentResult) else _jsonable(dict(agent_output))
    tool_calls = [_a2_tool_call(call, index) for index, call in enumerate(normalize_tool_calls(output.get("tool_calls", [])))]
    run = {"tool_calls": tool_calls, "final_response": _text_value(output.get("text", ""))}
    if expected_keywords is not None:
        run["expected_keywords"] = _jsonable(list(expected_keywords))
    if forbidden_keywords is not None:
        run["forbidden_keywords"] = _jsonable(list(forbidden_keywords))
    return run


class AgentAdapter:
    def __init__(self, agent: Any, *, name: str | None = None, raise_errors: bool = False, input_style: str = "text", input_keyword: str = "agent_input"):
        responder = getattr(agent, "respond", None)
        if not callable(responder) and not callable(agent):
            raise AgentAdapterError("agent must expose respond(message) or be callable")
        if input_style not in AGENT_INPUT_STYLES:
            raise AgentAdapterError(f"input_style must be one of {sorted(AGENT_INPUT_STYLES)}")
        self.agent = agent
        self.name = name or getattr(agent, "__name__", agent.__class__.__name__)
        self.raise_errors = raise_errors
        self.input_style = input_style
        self.input_keyword = input_keyword
        self.history: list[AgentResult] = []
        self.last_result: AgentResult | None = None
        self.last_reset_error: JsonDict | None = None
        self.last_reset_latency_ms: int | None = None

    def reset(self) -> bool:
        started = perf_counter()
        reset = getattr(self.agent, "reset", None)
        if reset is None:
            self.last_reset_error = None
            self.last_reset_latency_ms = elapsed_ms(started)
            return True
        try:
            value = reset()
            if inspect.isawaitable(value):
                _run_awaitable_sync(value)
            self.last_reset_error = None
            self.last_reset_latency_ms = elapsed_ms(started)
            return True
        except Exception as exc:
            self.last_reset_error = _error_payload(exc)
            self.last_reset_latency_ms = elapsed_ms(started)
            if self.raise_errors:
                raise AgentAdapterError(f"agent reset failed: {_redact_text(str(exc))}") from exc
            return False

    async def areset(self) -> bool:
        started = perf_counter()
        reset = getattr(self.agent, "reset", None)
        if reset is None:
            self.last_reset_error = None
            self.last_reset_latency_ms = elapsed_ms(started)
            return True
        try:
            value = reset()
            if inspect.isawaitable(value):
                await value
            self.last_reset_error = None
            self.last_reset_latency_ms = elapsed_ms(started)
            return True
        except Exception as exc:
            self.last_reset_error = _error_payload(exc)
            self.last_reset_latency_ms = elapsed_ms(started)
            if self.raise_errors:
                raise AgentAdapterError(f"agent reset failed: {_redact_text(str(exc))}") from exc
            return False

    def respond(self, message: Any, **kwargs: Any) -> AgentResult:
        result = self._respond_sync(message, kwargs)
        self.last_result = result
        self.history.append(result)
        return result

    async def arespond(self, message: Any, **kwargs: Any) -> AgentResult:
        result = await self._respond_async(message, kwargs)
        self.last_result = result
        self.history.append(result)
        return result

    def respond_input(self, agent_input: AgentInput | Mapping[str, Any], **kwargs: Any) -> AgentResult:
        result = self._respond_sync(agent_input, kwargs, input_style="request")
        self.last_result = result
        self.history.append(result)
        return result

    async def arespond_input(self, agent_input: AgentInput | Mapping[str, Any], **kwargs: Any) -> AgentResult:
        result = await self._respond_async(agent_input, kwargs, input_style="request")
        self.last_result = result
        self.history.append(result)
        return result

    def run_turn(self, message: Any, **kwargs: Any) -> AgentTurn:
        return self.respond(message, **kwargs)

    async def arun_turn(self, message: Any, **kwargs: Any) -> AgentTurn:
        return await self.arespond(message, **kwargs)

    def run_input_turn(self, agent_input: AgentInput | Mapping[str, Any], **kwargs: Any) -> AgentTurn:
        return self.respond_input(agent_input, **kwargs)

    async def arun_input_turn(self, agent_input: AgentInput | Mapping[str, Any], **kwargs: Any) -> AgentTurn:
        return await self.arespond_input(agent_input, **kwargs)

    async def _respond_async(self, message: Any, kwargs: JsonDict, *, input_style: str | None = None) -> AgentResult:
        started = perf_counter()
        try:
            value, style = self._invoke(message, kwargs, input_style=input_style)
            if inspect.isawaitable(value):
                value = await value
            result = self._normalize(value, started, style)
        except Exception as exc:
            if self.raise_errors:
                raise
            result = AgentResult(text="", status="error", latency_ms=elapsed_ms(started), error=_error_payload(exc), metadata={"adapter_name": self.name, "style": "error", "kwargs": _redact_sensitive(dict(kwargs))})
        return result

    def _respond_sync(self, message: Any, kwargs: JsonDict, *, input_style: str | None = None) -> AgentResult:
        started = perf_counter()
        try:
            value, style = self._invoke(message, kwargs, input_style=input_style)
            if inspect.isawaitable(value):
                value = _run_awaitable_sync(value)
            return self._normalize(value, started, style)
        except Exception as exc:
            if self.raise_errors:
                raise
            return AgentResult(text="", status="error", latency_ms=elapsed_ms(started), error=_error_payload(exc), metadata={"adapter_name": self.name, "style": "error", "kwargs": _redact_sensitive(dict(kwargs))})

    def _invoke(self, message: Any, kwargs: JsonDict, *, input_style: str | None = None) -> tuple[Any, str]:
        style_mode = input_style or self.input_style
        agent_input, call_kwargs = self._prepare_agent_input(message, kwargs)
        responder = getattr(self.agent, "respond", None)
        if callable(responder):
            if style_mode == "keyword":
                return responder(**self._keyword_input_kwargs(agent_input, call_kwargs)), "respond:keyword"
            return responder(self._input_argument(agent_input, style_mode), **call_kwargs), "respond" if style_mode == "text" else "respond:request"
        if callable(self.agent):
            if style_mode == "keyword":
                return self.agent(**self._keyword_input_kwargs(agent_input, call_kwargs)), "callable:keyword"
            return self.agent(self._input_argument(agent_input, style_mode), **call_kwargs), "callable" if style_mode == "text" else "callable:request"
        raise AgentAdapterError("agent must expose respond(message) or be callable")

    def _prepare_agent_input(self, message: Any, kwargs: JsonDict) -> tuple[AgentInput, JsonDict]:
        call_kwargs = dict(kwargs)
        parts = call_kwargs.pop("input_parts", None)
        metadata = call_kwargs.pop("input_metadata", None)
        return coerce_agent_input(message, parts=parts, metadata=metadata), call_kwargs

    def _input_argument(self, agent_input: AgentInput, input_style: str) -> Any:
        if input_style == "request":
            return agent_input.to_dict()
        return agent_input.text

    def _keyword_input_kwargs(self, agent_input: AgentInput, kwargs: JsonDict) -> JsonDict:
        call_kwargs = dict(kwargs)
        call_kwargs[self.input_keyword] = agent_input.to_dict()
        return call_kwargs

    def _normalize(self, value: Any, started: float, style: str) -> AgentResult:
        if isinstance(value, AgentResult):
            result = value.copy()
            result.latency_ms = result.latency_ms or elapsed_ms(started)
            result.metadata.setdefault("adapter_name", self.name)
            result.metadata.setdefault("style", style)
            return result
        if isinstance(value, str):
            return AgentResult(text=value, raw=value, latency_ms=elapsed_ms(started), metadata={"adapter_name": self.name, "style": style})
        if isinstance(value, dict):
            metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
            metadata = dict(metadata)
            metadata.setdefault("adapter_name", self.name)
            metadata.setdefault("style", style)
            return AgentResult(
                text=_extract_text(value),
                tool_calls=normalize_tool_calls(_extract_tool_calls(value)),
                raw=value,
                status=str(value.get("status") or "ok"),
                latency_ms=elapsed_ms(started),
                error=_coerce_error(value.get("error")) if value.get("error") else None,
                metadata=metadata,
            )
        return AgentResult(text=_object_text(value), tool_calls=normalize_tool_calls(getattr(value, "tool_calls", [])), raw=value, latency_ms=elapsed_ms(started), metadata={"adapter_name": self.name, "style": style})


def normalize_tool_calls(tool_calls: Any) -> list[JsonDict]:
    if tool_calls is None:
        return []
    if isinstance(tool_calls, dict):
        tool_calls = [tool_calls]
    return [_normalize_tool_call(call, index) for index, call in enumerate(tool_calls)]


def elapsed_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def _normalize_tool_call(call: Any, index: int) -> JsonDict:
    if isinstance(call, ToolCall):
        return call.to_dict()
    if not isinstance(call, dict):
        return ToolCall(name=str(call), call_id=f"tool_{index}").to_dict()
    function = call.get("function") if isinstance(call.get("function"), dict) else {}
    name = str(call.get("name") or call.get("tool") or function.get("name") or call.get("type") or f"tool_{index}")
    arguments = call.get("arguments", call.get("args", call.get("input", {})))
    if arguments == {} and "arguments" in function:
        arguments = function.get("arguments")
    arguments_json = call.get("arguments_json")
    if isinstance(arguments, str):
        if arguments_json is None:
            arguments_json = arguments
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"value": arguments}
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {"value": arguments}
    if arguments_json is None and isinstance(call.get("arguments"), str):
        arguments_json = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    return ToolCall(name=name, arguments=arguments, arguments_json=str(arguments_json) if arguments_json is not None else None, call_id=call.get("id") or call.get("call_id"), output=call.get("output") or call.get("result"), latency_ms=call.get("latency_ms"), error=call.get("error")).to_dict()


def _a2_tool_call(call: JsonDict, index: int) -> JsonDict:
    name = str(call.get("tool") or call.get("name") or f"tool_{index}")
    args = call.get("args") if isinstance(call.get("args"), dict) else call.get("arguments")
    if not isinstance(args, dict):
        args = {}
    projected = dict(call)
    projected["tool"] = name
    projected["args"] = _jsonable(args)
    projected.setdefault("name", name)
    projected.setdefault("arguments", _jsonable(args))
    call_id = call.get("id") or call.get("call_id")
    if call_id is not None:
        projected["id"] = str(call_id)
    return _jsonable(projected)


def _extract_text(data: JsonDict) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            return _first_text(message, ("content", "text", "message", "response", "output"))
    message = data.get("message")
    if isinstance(message, dict):
        return _first_text(message, ("content", "text", "message", "response", "output"))
    return _first_text(data, ("text", "message", "content", "response", "output"))


def _extract_tool_calls(data: JsonDict) -> Any:
    for key in ("tool_calls", "tools", "toolCalls", "actions"):
        if key in data and data[key]:
            return data[key]
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            return message.get("tool_calls") or message.get("toolCalls") or []
    message = data.get("message")
    if isinstance(message, dict):
        return message.get("tool_calls") or message.get("toolCalls") or []
    return []


def _first_text(data: JsonDict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return _text_value(value)
    return ""


def _object_text(value: Any) -> str:
    for attr in ("text", "message", "content", "response", "output"):
        if hasattr(value, attr):
            return _text_value(getattr(value, attr))
    return str(value)


def _error_payload(exc: Exception) -> JsonDict:
    return {"type": exc.__class__.__name__, "message": _redact_text(str(exc))}


def _coerce_error(error: Any) -> JsonDict:
    if isinstance(error, dict):
        return _redact_sensitive(dict(error))
    return {"type": "AgentError", "message": _redact_text(str(error))}


def _run_awaitable_sync(value: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = asyncio.run(value)
        except BaseException as exc:
            box["error"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=repr)]
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return copy.deepcopy(value)


def _normalize_input_parts(parts: Any) -> list[JsonDict]:
    if parts is None:
        return []
    if isinstance(parts, Mapping) or isinstance(parts, str):
        parts = [parts]
    if not isinstance(parts, (list, tuple)):
        raise AgentAdapterError("agent input parts must be a mapping or list of mappings")
    return [_normalize_input_part(part, index) for index, part in enumerate(parts)]


def _normalize_input_part(part: Any, index: int) -> JsonDict:
    if isinstance(part, str):
        return {"type": "text", "text": part}
    if not isinstance(part, Mapping):
        raise AgentAdapterError(f"agent input part {index} must be a mapping")
    normalized = _jsonable(dict(part))
    part_type = str(normalized.get("type") or "text").lower()
    if part_type not in AGENT_INPUT_PART_TYPES:
        raise AgentAdapterError(f"agent input part {index} has unsupported type: {part_type}")
    normalized["type"] = part_type
    if "mimeType" in normalized and "mime_type" not in normalized:
        normalized["mime_type"] = normalized.pop("mimeType")
    if part_type == "text":
        normalized["text"] = _text_value(normalized.get("text", normalized.get("content", "")))
        normalized.pop("content", None)
    return normalized


def _text_from_input_parts(parts: Any) -> str:
    texts: list[str] = []
    for part in _normalize_input_parts(parts):
        if part.get("type") == "text":
            text = _text_value(part.get("text", ""))
            if text:
                texts.append(text)
    return "\n".join(texts)


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    part_text = _text_from_content_parts(value)
    if part_text is not None:
        return part_text
    return json.dumps(_jsonable(value), sort_keys=True)


def _text_from_content_parts(value: Any) -> str | None:
    if isinstance(value, Mapping):
        return _text_from_content_part(value)
    if not isinstance(value, (list, tuple)):
        return None
    saw_part = False
    texts: list[str] = []
    for item in value:
        if isinstance(item, str):
            texts.append(item)
            continue
        if not isinstance(item, Mapping) or "type" not in item:
            return None if not saw_part else "\n".join(texts)
        saw_part = True
        text = _text_from_content_part(item)
        if text:
            texts.append(text)
    if saw_part or texts:
        return "\n".join(texts)
    return None


def _text_from_content_part(part: Mapping[str, Any]) -> str | None:
    part_type = str(part.get("type") or "").lower()
    if part_type not in {"text", "input_text", "output_text"}:
        return None
    for key in ("text", "content", "value"):
        if key in part:
            value = part[key]
            return value if isinstance(value, str) else json.dumps(_jsonable(value), sort_keys=True)
    return ""


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: JsonDict = {}
        for key, item in value.items():
            text_key = str(key)
            normalized_key = text_key.lower().replace("-", "_")
            if normalized_key in _SENSITIVE_EXACT_KEYS or any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                redacted[text_key] = _REDACTED
            else:
                redacted[text_key] = _redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, set):
        return [_redact_sensitive(item) for item in sorted(value, key=repr)]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    redacted = _SIGNED_URL_PATTERN.sub(lambda match: match.group(0).split("?", 1)[0] + "?[redacted]", value)
    for pattern in _SECRET_LIKE_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted
