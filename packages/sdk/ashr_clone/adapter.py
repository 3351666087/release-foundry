from __future__ import annotations

import asyncio
import copy
import inspect
import json
import threading
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Mapping

from .types import JsonDict, ToolCall


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
        data = {"text": self.text, "tool_calls": _jsonable(self.tool_calls), "status": self.status, "latency_ms": self.latency_ms, "metadata": _jsonable(self.metadata)}
        if self.error:
            data["error"] = _jsonable(self.error)
        return data


AgentTurn = AgentResult


class AgentAdapter:
    def __init__(self, agent: Any, *, name: str | None = None, raise_errors: bool = False):
        responder = getattr(agent, "respond", None)
        if not callable(responder) and not callable(agent):
            raise AgentAdapterError("agent must expose respond(message) or be callable")
        self.agent = agent
        self.name = name or getattr(agent, "__name__", agent.__class__.__name__)
        self.raise_errors = raise_errors
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
                raise AgentAdapterError(f"agent reset failed: {exc}") from exc
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
                raise AgentAdapterError(f"agent reset failed: {exc}") from exc
            return False

    def respond(self, message: str, **kwargs: Any) -> AgentResult:
        result = self._respond_sync(message, kwargs)
        self.last_result = result
        self.history.append(result)
        return result

    async def arespond(self, message: str, **kwargs: Any) -> AgentResult:
        started = perf_counter()
        try:
            value, style = self._invoke(message, kwargs)
            if inspect.isawaitable(value):
                value = await value
            result = self._normalize(value, started, style)
        except Exception as exc:
            if self.raise_errors:
                raise
            result = AgentResult(text="", status="error", latency_ms=elapsed_ms(started), error=_error_payload(exc), metadata={"adapter_name": self.name, "style": "error"})
        self.last_result = result
        self.history.append(result)
        return result

    def run_turn(self, message: str, **kwargs: Any) -> AgentTurn:
        return self.respond(message, **kwargs)

    async def arun_turn(self, message: str, **kwargs: Any) -> AgentTurn:
        return await self.arespond(message, **kwargs)

    def _respond_sync(self, message: str, kwargs: JsonDict) -> AgentResult:
        started = perf_counter()
        try:
            value, style = self._invoke(message, kwargs)
            if inspect.isawaitable(value):
                value = _run_awaitable_sync(value)
            return self._normalize(value, started, style)
        except Exception as exc:
            if self.raise_errors:
                raise
            return AgentResult(text="", status="error", latency_ms=elapsed_ms(started), error=_error_payload(exc), metadata={"adapter_name": self.name, "style": "error", "kwargs": dict(kwargs)})

    def _invoke(self, message: str, kwargs: JsonDict) -> tuple[Any, str]:
        responder = getattr(self.agent, "respond", None)
        if callable(responder):
            return responder(message, **kwargs), "respond"
        if callable(self.agent):
            return self.agent(message, **kwargs), "callable"
        raise AgentAdapterError("agent must expose respond(message) or be callable")

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
            return value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return ""


def _object_text(value: Any) -> str:
    for attr in ("text", "message", "content", "response", "output"):
        if hasattr(value, attr):
            text = getattr(value, attr)
            return text if isinstance(text, str) else json.dumps(text, sort_keys=True)
    return str(value)


def _error_payload(exc: Exception) -> JsonDict:
    return {"type": exc.__class__.__name__, "message": str(exc)}


def _coerce_error(error: Any) -> JsonDict:
    if isinstance(error, dict):
        return dict(error)
    return {"type": "AgentError", "message": str(error)}


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
