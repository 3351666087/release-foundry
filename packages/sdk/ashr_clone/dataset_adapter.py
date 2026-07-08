from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .trace import Observation, TraceRecorder, build_run_fixture, stable_id, validate_run_fixture

JsonDict = dict[str, Any]

DATASET_ADAPTER_VERSION = "ashr.clone.dataset_adapter.v1"
DATASET_SOURCE_ADAPTER_VERSION = DATASET_ADAPTER_VERSION


def dataset_source_to_cases(
    dataset_source: Mapping[str, Any],
    *,
    max_cases: int | None = None,
    include_agentless_runs: bool = False,
) -> list[JsonDict]:
    """Convert Ashr dataset_source.runs into A1 local runner cases."""
    max_cases = _normalize_max_cases(max_cases)
    if max_cases == 0:
        return []
    runs = _runs_items(dataset_source.get("runs"))
    cases: list[JsonDict] = []
    dataset_type = str(dataset_source.get("dataset_type") or "")
    total_runs = dataset_source.get("total_runs")

    for run_key, run in runs:
        if not isinstance(run, Mapping):
            continue
        run_id = str(run.get("run_id") or run_key)
        actions = _action_list(run.get("actions"))
        emitted_for_run = 0
        for action_index, action in enumerate(actions):
            if _actor(action) != "agent":
                continue
            case = case_from_source_run(run, action_index=action_index, run_key=run_key, dataset_type=dataset_type, total_runs=total_runs)
            cases.append(case)
            emitted_for_run += 1
            if max_cases is not None and len(cases) >= max_cases:
                return cases
        if include_agentless_runs and emitted_for_run == 0 and actions:
            cases.append(_case_from_agentless_run(run_id=run_id, run=run, actions=actions, dataset_type=dataset_type, total_runs=total_runs))
            if max_cases is not None and len(cases) >= max_cases:
                return cases
    return cases


def cases_from_dataset_source(
    dataset_source: Mapping[str, Any],
    *,
    max_cases: int | None = None,
    include_agentless_runs: bool = False,
) -> list[JsonDict]:
    return dataset_source_to_cases(dataset_source, max_cases=max_cases, include_agentless_runs=include_agentless_runs)


def case_from_source_run(
    source_run: Mapping[str, Any],
    *,
    action_index: int | None = None,
    agent_action_ordinal: int = 0,
    run_key: str | None = None,
    dataset_type: str = "",
    total_runs: Any = None,
) -> JsonDict:
    """Convert one agent action from a dataset_source run into an A1 runner case."""
    if not isinstance(source_run, Mapping):
        raise ValueError("source_run must be a JSON object")
    actions = _action_list(source_run.get("actions"))
    run_id = str(source_run.get("run_id") or run_key or stable_id("source_run", source_run))
    selected_index = _select_agent_action_index(actions, action_index=action_index, agent_action_ordinal=agent_action_ordinal)
    action = actions[selected_index]
    return _case_from_agent_action(
        run_id=run_id,
        run=source_run,
        actions=actions,
        action=action,
        action_index=selected_index,
        dataset_type=dataset_type,
        total_runs=total_runs,
    )


def api_record_to_cases(record: Mapping[str, Any], *, max_cases: int | None = None) -> list[JsonDict]:
    return dataset_source_to_cases(extract_dataset_source(record), max_cases=max_cases)


def extract_dataset_source(record_or_dataset: Mapping[str, Any]) -> JsonDict:
    """Extract dataset_source from an API probe record, get_dataset response, or dataset object."""
    current: Any = record_or_dataset
    if isinstance(current, Mapping) and "response" in current:
        current = current.get("response") or {}
    if isinstance(current, Mapping) and "dataset" in current:
        current = current.get("dataset") or {}
    if isinstance(current, Mapping) and "dataset_source" in current:
        source = current.get("dataset_source") or {}
    else:
        source = current
    if not isinstance(source, Mapping):
        raise ValueError("dataset_source must be a JSON object")
    if "runs" not in source:
        raise ValueError("dataset_source must contain runs")
    return dict(source)


def load_cases_from_api_record(path: str | Path, *, max_cases: int | None = None) -> list[JsonDict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("API record must be a JSON object")
    return api_record_to_cases(payload, max_cases=max_cases)


def write_cases(path: str | Path, cases: Iterable[Mapping[str, Any]]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"adapter_version": DATASET_ADAPTER_VERSION, "cases": [dict(case) for case in cases]}
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return output


def replay_fixture_from_source_run(
    source_run: Mapping[str, Any],
    *,
    run_key: str | None = None,
    agent: str = "ashr-dataset-source",
) -> JsonDict:
    """Build a strict A3 replay fixture from one Ashr dataset_source run."""
    if not isinstance(source_run, Mapping):
        raise ValueError("source_run must be a JSON object")
    actions = _action_list(source_run.get("actions"))
    source_run_id = str(source_run.get("run_id") or run_key or stable_id("source_run", source_run))
    replay_run_id = stable_id("dataset_replay", source_run_id, _action_summaries(actions))
    recorder = TraceRecorder(run_id=replay_run_id, source="ashr_dataset_source")
    agent_action_count = sum(1 for action in actions if _actor(action) == "agent")
    recorder.control(
        "source_run.start",
        data={
            "adapter_version": DATASET_SOURCE_ADAPTER_VERSION,
            "source_run_hash": stable_id("source_run", source_run_id),
            "action_count": len(actions),
            "agent_action_count": agent_action_count,
        },
    )
    for index, action in enumerate(actions):
        actor = _actor(action)
        text = _text(action.get("content") or action.get("message") or action.get("text") or action.get("name"))
        action_meta = _action_summary(action, index)
        if actor == "agent":
            for tool_index, tool_call in enumerate(_expected_from_agent_action(action).get("tool_calls", [])):
                recorder.tool_call(
                    str(tool_call.get("name") or f"tool_{tool_index}"),
                    tool_call.get("arguments", {}),
                    call_id=stable_id("call", replay_run_id, index, tool_index, tool_call),
                )
            recorder.message("assistant", text, data=action_meta)
        elif actor == "user":
            recorder.message("user", text, data=action_meta)
        else:
            recorder.append(Observation("state", channel="vm", text=text or actor or "action", data=action_meta), "vm", ("source_action",))
    recorder.metric("source_actions", len(actions))
    recorder.metric("source_agent_actions", agent_action_count)
    recorder.control("source_run.end", data={"adapter_version": DATASET_SOURCE_ADAPTER_VERSION})
    fixture = build_run_fixture(
        _case_title(source_run, "source-run-replay"),
        _text(source_run.get("intent") or source_run.get("description") or source_run.get("title") or source_run_id),
        recorder.events(),
        agent=agent,
        expected={"status": "ok", "source_actions": len(actions), "agent_actions": agent_action_count},
        replay={"mode": "source-run-replay", "entrypoint": "ashr_clone.dataset_adapter:replay_fixture_from_source_run"},
        labels=("a1", "ashr-dataset-source"),
    )
    validate_run_fixture(fixture)
    return fixture


def _case_from_agent_action(
    *,
    run_id: str,
    run: Mapping[str, Any],
    actions: list[JsonDict],
    action: Mapping[str, Any],
    action_index: int,
    dataset_type: str,
    total_runs: Any,
) -> JsonDict:
    expected = _expected_from_agent_action(action)
    prompt = _prompt_for_agent_action(run, actions[:action_index], action_index)
    action_name = str(action.get("name") or f"agent_action_{action_index}")
    case_id = f"{_safe_id(run_id)}-a{action_index:03d}"
    return {
        "id": case_id,
        "case_id": case_id,
        "scenario_id": run_id,
        "title": _case_title(run, action_name),
        "prompt": prompt,
        "expected": expected,
        "metadata": _metadata(
            run=run,
            action=action,
            action_index=action_index,
            dataset_type=dataset_type,
            total_runs=total_runs,
            action_count=len(actions),
            requires_external_judge=_requires_external_judge(action, expected),
        ),
    }


def _case_from_agentless_run(*, run_id: str, run: Mapping[str, Any], actions: list[JsonDict], dataset_type: str, total_runs: Any) -> JsonDict:
    case_id = f"{_safe_id(run_id)}-agentless"
    return {
        "id": case_id,
        "case_id": case_id,
        "scenario_id": run_id,
        "title": _case_title(run, "agentless"),
        "prompt": _prompt_for_agent_action(run, actions, len(actions)),
        "expected": {},
        "metadata": _metadata(
            run=run,
            action={},
            action_index=None,
            dataset_type=dataset_type,
            total_runs=total_runs,
            action_count=len(actions),
            requires_external_judge=True,
        ),
    }


def _prompt_for_agent_action(run: Mapping[str, Any], previous_actions: list[JsonDict], action_index: int) -> str:
    title = _text(run.get("title"))
    description = _text(run.get("description"))
    intent = _text(run.get("intent"))
    lines = []
    if title:
        lines.append(f"Scenario: {title}")
    if description:
        lines.append(f"Description: {description}")
    if intent:
        lines.append(f"Intent: {intent}")
    lines.append(f"Target agent action index: {action_index}")
    lines.append("")
    lines.append("Conversation so far:")
    if previous_actions:
        for index, action in enumerate(previous_actions):
            actor = _actor(action)
            content = _text(action.get("content"))
            name = _text(action.get("name"))
            label = actor if not name else f"{actor} ({name})"
            if content:
                lines.append(f"{index}. {label}: {content}")
    else:
        lines.append("(no prior actions)")
    lines.append("")
    lines.append("Respond as the agent to the latest user/environment context.")
    return "\n".join(lines)


def _expected_from_agent_action(action: Mapping[str, Any]) -> JsonDict:
    expected = action.get("expected_response")
    payload: JsonDict = dict(expected) if isinstance(expected, Mapping) else {}
    if "text" not in payload and action.get("content") not in (None, ""):
        payload["text"] = _text(action.get("content"))
    tool_calls = payload.get("tool_calls")
    if tool_calls is not None:
        payload["tool_calls"] = _normalize_tool_calls(tool_calls)
    return payload


def _normalize_tool_calls(tool_calls: Any) -> list[JsonDict]:
    if isinstance(tool_calls, Mapping):
        tool_calls = [tool_calls]
    if not isinstance(tool_calls, list):
        return []
    normalized: list[JsonDict] = []
    for index, call in enumerate(tool_calls):
        if not isinstance(call, Mapping):
            normalized.append({"name": str(call), "arguments": {}})
            continue
        name = str(call.get("name") or call.get("tool") or call.get("type") or f"tool_{index}")
        arguments = call.get("arguments", call.get("args", {}))
        if (arguments is None or arguments == {}) and call.get("arguments_json") is not None:
            arguments = call.get("arguments_json")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"value": arguments}
        if not isinstance(arguments, Mapping):
            arguments = {}
        normalized.append({"name": name, "arguments": dict(arguments)})
    return normalized


def _metadata(
    *,
    run: Mapping[str, Any],
    action: Mapping[str, Any],
    action_index: int | None,
    dataset_type: str,
    total_runs: Any,
    action_count: int,
    requires_external_judge: bool,
) -> JsonDict:
    source_run_id = _text(run.get("run_id"))
    return {
        "adapter_version": DATASET_SOURCE_ADAPTER_VERSION,
        "source": "ashr_dataset_source",
        "dataset_type": dataset_type,
        "total_runs": total_runs,
        "source_run_hash": stable_id("source_run", source_run_id) if source_run_id else "",
        "action_count": action_count,
        "action_index": action_index,
        "action_name": _text(action.get("name")),
        "action_type": _text(action.get("action_type")),
        "requires_external_judge": requires_external_judge,
        "intent_tags": _json_list(run.get("intent_tags")),
        "audio_tags": _json_list(run.get("audio_tags")),
        "action_tags": _json_list(action.get("action_tags")),
    }


def _runs_items(runs: Any) -> list[tuple[str, Any]]:
    if isinstance(runs, Mapping):
        return [(str(key), value) for key, value in runs.items()]
    if isinstance(runs, list):
        return [(str(index), value) for index, value in enumerate(runs)]
    return []


def _normalize_max_cases(max_cases: int | None) -> int | None:
    if max_cases is None:
        return None
    value = int(max_cases)
    if value < 0:
        raise ValueError("max_cases must be non-negative")
    return value


def _action_list(actions: Any) -> list[JsonDict]:
    if not isinstance(actions, list):
        return []
    return [dict(action) for action in actions if isinstance(action, Mapping)]


def _select_agent_action_index(actions: list[JsonDict], *, action_index: int | None, agent_action_ordinal: int) -> int:
    if action_index is not None:
        if action_index < 0 or action_index >= len(actions):
            raise ValueError("action_index is out of range")
        if _actor(actions[action_index]) != "agent":
            raise ValueError("selected action is not an agent action")
        return action_index
    agent_indexes = [index for index, action in enumerate(actions) if _actor(action) == "agent"]
    if agent_action_ordinal < 0 or agent_action_ordinal >= len(agent_indexes):
        raise ValueError("source_run does not contain the requested agent action")
    return agent_indexes[agent_action_ordinal]


def _actor(action: Mapping[str, Any]) -> str:
    return str(action.get("actor") or "").strip().lower()


def _case_title(run: Mapping[str, Any], action_name: str) -> str:
    title = _text(run.get("title")) or _text(run.get("run_id")) or "Ashr scenario"
    return f"{title} / {action_name}"


def _safe_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip())
    return safe or "run"


def _requires_external_judge(action: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return not bool(expected) and action.get("content") in (None, "")


def _action_summary(action: Mapping[str, Any], index: int) -> JsonDict:
    return {
        "action_index": index,
        "actor": _actor(action),
        "name": _text(action.get("name")),
        "action_type": _text(action.get("action_type")),
        "has_content": action.get("content") not in (None, ""),
        "has_expected_response": isinstance(action.get("expected_response"), Mapping),
        "has_output_path": action.get("output_path") not in (None, ""),
    }


def _action_summaries(actions: Iterable[Mapping[str, Any]]) -> list[JsonDict]:
    return [_action_summary(action, index) for index, action in enumerate(actions)]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]
