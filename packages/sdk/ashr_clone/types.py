from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from typing import Any

JsonDict = dict[str, Any]


@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: JsonDict = field(default_factory=dict)
    arguments_json: str | None = None
    call_id: str | None = None
    output: Any = None
    latency_ms: int | None = None
    error: str | None = None

    def to_dict(self) -> JsonDict:
        return _drop_none(asdict(self))


@dataclass(slots=True)
class Observation:
    observation_id: str
    run_id: str
    case_id: str
    turn_index: int
    event_type: str
    role: str
    content: Any = None
    tool_calls: list[JsonDict] = field(default_factory=list)
    started_at: str | None = None
    ended_at: str | None = None
    latency_ms: int | None = None
    status: str = "ok"
    error: str | None = None
    metadata: JsonDict = field(default_factory=dict)
    vm_stream: JsonDict | None = None

    def to_dict(self) -> JsonDict:
        return _drop_none(asdict(self))


@dataclass(slots=True)
class GradeResult:
    scenario_id: str
    passed: bool
    score: float
    label: str
    reason: str = ""
    expected: JsonDict = field(default_factory=dict)
    actual: JsonDict = field(default_factory=dict)
    metrics: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return _drop_none(asdict(self))


@dataclass(slots=True)
class CaseResult:
    case_id: str
    scenario_id: str
    title: str
    status: str
    started_at: str
    ended_at: str
    latency_ms: int
    observations: list[JsonDict]
    grade: JsonDict
    agent_output: JsonDict = field(default_factory=dict)
    expected: JsonDict = field(default_factory=dict)
    error: str | None = None
    metadata: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return _drop_none(asdict(self))


@dataclass(slots=True)
class RunResult:
    run_id: str
    dataset_id: str
    runner_id: str
    status: str
    total_cases: int
    passed: int
    failed: int
    errored: int
    timed_out: int
    started_at: str
    ended_at: str
    duration_ms: int
    max_workers: int
    trace_completeness: float
    cases: list[JsonDict]
    aggregate_metrics: JsonDict = field(default_factory=dict)
    metadata: JsonDict = field(default_factory=dict)
    field_map_version: str = "a1-local-2026-07-03"

    def to_dict(self) -> JsonDict:
        return _drop_none(asdict(self))


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _drop_none(value[key]) for key in sorted(value, key=lambda item: str(item)) if value[key] is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    if isinstance(value, tuple):
        return [_drop_none(item) for item in value]
    if isinstance(value, set):
        return [_drop_none(item) for item in sorted(value, key=repr)]
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value
