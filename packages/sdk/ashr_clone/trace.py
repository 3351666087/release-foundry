from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

TRACE_SCHEMA = "ashr.clone.trace.v1"
RUN_FIXTURE_SCHEMA = "ashr.clone.run.v1"
VM_STREAM_SCHEMA = "ashr.clone.vm_stream.v1"
FIXED_STARTED_AT = "2026-01-01T00:00:00.000Z"
VM_FRAME_KEYS = {"schema", "seq", "timestamp", "event_id", "stream", "status", "text", "data"}
VM_STREAMS = {"stdin", "stdout", "tool_call", "tool_result", "lifecycle", "metric", "stderr", "state"}


def stable_id(prefix: str, *parts: Any, size: int = 16) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:size]}"


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timestamp_for(seq: int, started_at: str = FIXED_STARTED_AT, step_ms: int = 50) -> str:
    value = _parse_timestamp(started_at) + timedelta(milliseconds=seq * step_ms)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _json_normalize(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


@dataclass(frozen=True)
class Observation:
    kind: str
    text: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    channel: str = "agent"
    status: str = "ok"

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _json_normalize(dict(self.data)))

    @classmethod
    def message(cls, role: str, text: str, data: Mapping[str, Any] | None = None) -> "Observation":
        return cls(kind="message", channel=role, text=text, data=data or {})

    @classmethod
    def tool_call(cls, name: str, args: Mapping[str, Any], call_id: str) -> "Observation":
        return cls(kind="tool_call", channel="tool", text=f"call {name}", data={"name": name, "args": dict(args), "call_id": call_id})

    @classmethod
    def tool_result(cls, name: str, call_id: str, result: Any, status: str = "ok") -> "Observation":
        return cls(kind="tool_result", channel="tool", status=status, text=f"{name} result", data={"name": name, "call_id": call_id, "result": result})

    @classmethod
    def control(cls, name: str, status: str = "ok", data: Mapping[str, Any] | None = None) -> "Observation":
        return cls(kind="control", channel="system", status=status, text=name, data=data or {})

    @classmethod
    def metric(cls, name: str, value: Any, unit: str = "count") -> "Observation":
        return cls(kind="metric", channel="system", text=name, data={"name": name, "value": value, "unit": unit})

    @classmethod
    def error(cls, text: str, data: Mapping[str, Any] | None = None) -> "Observation":
        return cls(kind="error", channel="vm", status="error", text=text, data=data or {})

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "channel": self.channel, "status": self.status, "text": self.text, "data": dict(self.data)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Observation":
        return cls(kind=str(payload["kind"]), channel=str(payload.get("channel", "agent")), status=str(payload.get("status", "ok")), text=str(payload.get("text", "")), data=payload.get("data", {}))


@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    event_id: str
    seq: int
    timestamp: str
    phase: str
    source: str
    observation: Observation
    parent_id: str | None = None
    tags: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        return f"{self.phase}.{self.observation.kind}"

    def to_dict(self) -> dict[str, Any]:
        return {"schema": TRACE_SCHEMA, "type": "trace_event", "event_type": self.event_type, "run_id": self.run_id, "event_id": self.event_id, "seq": self.seq, "timestamp": self.timestamp, "phase": self.phase, "source": self.source, "parent_id": self.parent_id, "tags": list(self.tags), "observation": self.observation.to_dict(), "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TraceEvent":
        if payload.get("schema") != TRACE_SCHEMA:
            raise ValueError(f"unsupported trace schema: {payload.get('schema')}")
        return cls(run_id=str(payload["run_id"]), event_id=str(payload["event_id"]), seq=int(payload["seq"]), timestamp=str(payload["timestamp"]), phase=str(payload["phase"]), source=str(payload["source"]), parent_id=payload.get("parent_id"), tags=tuple(payload.get("tags", ())), observation=Observation.from_dict(payload["observation"]), metadata=payload.get("metadata", {}))


EventInput = TraceEvent | Mapping[str, Any]


def _as_event(event: EventInput) -> TraceEvent:
    return event if isinstance(event, TraceEvent) else TraceEvent.from_dict(event)


class TraceRecorder:
    def __init__(self, run_id: str | None = None, source: str = "mock_agent", started_at: str = FIXED_STARTED_AT) -> None:
        self.run_id = run_id or stable_id("run", source, started_at)
        self.source = source
        self.started_at = started_at
        self._events: list[TraceEvent] = []

    def append(self, observation: Observation, phase: str, tags: Sequence[str] = (), metadata: Mapping[str, Any] | None = None) -> TraceEvent:
        seq = len(self._events)
        event = TraceEvent(run_id=self.run_id, event_id=stable_id("evt", self.run_id, seq, observation.to_dict(), phase), seq=seq, timestamp=timestamp_for(seq, self.started_at), phase=phase, source=self.source, tags=tuple(tags), metadata=metadata or {}, observation=observation)
        self._events.append(event)
        return event

    def control(self, name: str, status: str = "ok", data: Mapping[str, Any] | None = None) -> TraceEvent:
        return self.append(Observation.control(name, status=status, data=data), "lifecycle", ("control",))

    def message(self, role: str, text: str, data: Mapping[str, Any] | None = None) -> TraceEvent:
        return self.append(Observation.message(role, text, data=data), "dialogue", (role,))

    def tool_call(self, name: str, args: Mapping[str, Any], call_id: str | None = None) -> TraceEvent:
        actual_call_id = call_id or stable_id("call", self.run_id, len(self._events), name, args)
        return self.append(Observation.tool_call(name, args, actual_call_id), "tool", ("tool_call", name))

    def tool_result(self, name: str, call_id: str, result: Any, status: str = "ok") -> TraceEvent:
        return self.append(Observation.tool_result(name, call_id, result, status=status), "tool", ("tool_result", name))

    def metric(self, name: str, value: Any, unit: str = "count") -> TraceEvent:
        return self.append(Observation.metric(name, value, unit), "telemetry", ("metric", name))

    def events(self) -> list[TraceEvent]:
        return list(self._events)


def replay_observations(events: Iterable[EventInput]) -> Iterator[Observation]:
    for event in sorted((_as_event(item) for item in events), key=lambda item: item.seq):
        yield event.observation


def build_vm_frame(event: EventInput) -> dict[str, Any]:
    parsed = _as_event(event)
    obs = parsed.observation
    if obs.kind == "message":
        stream = "stdin" if obs.channel == "user" else "stdout" if obs.channel == "assistant" else "lifecycle"
    elif obs.kind in {"tool_call", "tool_result"}:
        stream = obs.kind
    elif obs.kind == "control":
        stream = "lifecycle"
    elif obs.kind == "metric":
        stream = "metric"
    elif obs.kind == "error":
        stream = "stderr"
    else:
        stream = "state"
    return {"schema": VM_STREAM_SCHEMA, "seq": parsed.seq, "timestamp": parsed.timestamp, "event_id": parsed.event_id, "stream": stream, "status": obs.status, "text": obs.text, "data": dict(obs.data)}


def build_vm_stream(events: Iterable[EventInput]) -> list[dict[str, Any]]:
    return [build_vm_frame(event) for event in sorted((_as_event(item) for item in events), key=lambda item: item.seq)]


def trace_events_from_vm_stream(run_id: str, frames: Iterable[Mapping[str, Any]], source: str = "vm_replay", started_at: str = FIXED_STARTED_AT) -> list[TraceEvent]:
    recorder = TraceRecorder(run_id=run_id, source=source, started_at=started_at)
    frame_list = [_validate_vm_frame_shape(frame) for frame in frames]
    seqs = [frame["seq"] for frame in sorted(frame_list, key=lambda item: item["seq"])]
    if seqs != list(range(len(seqs))):
        raise ValueError("vm_stream frame seqs must be contiguous from zero")
    for frame in sorted(frame_list, key=lambda item: item["seq"]):
        stream = str(frame["stream"])
        text = str(frame.get("text", ""))
        data = frame.get("data", {})
        if stream == "stdin":
            recorder.message("user", text, data=data)
        elif stream == "stdout":
            recorder.message("assistant", text, data=data)
        elif stream == "tool_call":
            recorder.append(Observation("tool_call", channel="tool", text=text, data=data), "tool")
        elif stream == "tool_result":
            recorder.append(Observation("tool_result", channel="tool", text=text, data=data, status=str(frame.get("status", "ok"))), "tool")
        elif stream == "metric":
            recorder.append(Observation("metric", channel="system", text=text, data=data), "telemetry")
        elif stream == "stderr":
            recorder.append(Observation.error(text, data=data), "vm")
        elif stream == "state":
            recorder.append(Observation("state", channel="vm", text=text, data=data, status=str(frame.get("status", "ok"))), "vm")
        else:
            recorder.control(text, status=str(frame.get("status", "ok")), data=data)
    return recorder.events()


def build_run_fixture(name: str, task: str, events: Iterable[EventInput], agent: str = "mock-agent", expected: Mapping[str, Any] | None = None, replay: Mapping[str, Any] | None = None, labels: Sequence[str] = ()) -> dict[str, Any]:
    event_list = sorted((_as_event(item) for item in events), key=lambda item: item.seq)
    if not event_list:
        raise ValueError("run fixture requires at least one event")
    run_id = event_list[0].run_id
    fixture = {"schema": RUN_FIXTURE_SCHEMA, "name": name, "labels": list(labels), "run": {"run_id": run_id, "agent": agent, "task": task, "status": (expected or {}).get("status", event_list[-1].observation.status), "started_at": event_list[0].timestamp, "finished_at": event_list[-1].timestamp}, "events": [event.to_dict() for event in event_list], "vm_stream": build_vm_stream(event_list), "expected": dict(expected or {}), "replay": dict(replay or {})}
    validate_run_fixture(fixture)
    return fixture


def validate_run_fixture(fixture: Mapping[str, Any]) -> bool:
    if fixture.get("schema") != RUN_FIXTURE_SCHEMA:
        raise ValueError(f"unsupported run fixture schema: {fixture.get('schema')}")
    events = fixture.get("events")
    frames = fixture.get("vm_stream")
    run = fixture.get("run")
    if not isinstance(run, Mapping) or not run.get("run_id") or not isinstance(events, list) or not events:
        raise ValueError("invalid run fixture")
    if not isinstance(frames, list) or len(frames) != len(events):
        raise ValueError("vm_stream must contain one frame per event")
    parsed = [TraceEvent.from_dict(event) for event in events]
    run_id = str(run["run_id"])
    if any(event.run_id != run_id for event in parsed):
        raise ValueError("all events must match run.run_id")
    if [event.seq for event in parsed] != list(range(len(parsed))):
        raise ValueError("event seqs must be contiguous from zero")
    for event in parsed:
        _parse_timestamp(event.timestamp)
    replay = fixture.get("replay", {})
    if replay and (not isinstance(replay, Mapping) or any(key in replay and not isinstance(replay[key], str) for key in ("entrypoint", "command", "mode"))):
        raise ValueError("replay metadata must contain string entrypoint/command/mode values when present")
    normalized_frames = [_validate_vm_frame_shape(frame) for frame in frames]
    if [frame["seq"] for frame in normalized_frames] != list(range(len(normalized_frames))):
        raise ValueError("vm_stream frame seqs must be contiguous from zero")
    expected_frames = build_vm_stream(parsed)
    if normalized_frames != expected_frames:
        raise ValueError("vm_stream frames must match trace events")
    return True


def _validate_vm_frame_shape(frame: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(frame, Mapping):
        raise ValueError("vm_stream frame must be a mapping")
    keys = set(frame)
    if keys != VM_FRAME_KEYS:
        raise ValueError(f"vm_stream frame keys must be {sorted(VM_FRAME_KEYS)}")
    if frame.get("schema") != VM_STREAM_SCHEMA:
        raise ValueError(f"unsupported vm_stream schema: {frame.get('schema')}")
    seq = frame.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int):
        raise ValueError("vm_stream frame seq must be an integer")
    timestamp = frame.get("timestamp")
    event_id = frame.get("event_id")
    stream = frame.get("stream")
    status = frame.get("status")
    text = frame.get("text")
    data = frame.get("data")
    if not isinstance(timestamp, str):
        raise ValueError("vm_stream frame timestamp must be a string")
    _parse_timestamp(timestamp)
    if not isinstance(event_id, str):
        raise ValueError("vm_stream frame event_id must be a string")
    if not isinstance(stream, str) or stream not in VM_STREAMS:
        raise ValueError(f"unsupported vm_stream stream: {stream}")
    if not isinstance(status, str):
        raise ValueError("vm_stream frame status must be a string")
    if not isinstance(text, str):
        raise ValueError("vm_stream frame text must be a string")
    if not isinstance(data, Mapping):
        raise ValueError("vm_stream frame data must be a mapping")
    return {"schema": frame["schema"], "seq": seq, "timestamp": timestamp, "event_id": event_id, "stream": stream, "status": status, "text": text, "data": _json_normalize(dict(data))}


def write_run_fixture(path: str | Path, fixture: Mapping[str, Any]) -> None:
    validate_run_fixture(fixture)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_run_fixture(path: str | Path) -> dict[str, Any]:
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_run_fixture(fixture)
    return fixture
