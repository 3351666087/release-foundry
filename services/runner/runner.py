from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterable, Mapping, MutableMapping

SDK_ROOT = Path(__file__).resolve().parents[2] / "packages" / "sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ashr_clone.adapter import AgentAdapter, AgentResult  # noqa: E402
from ashr_clone.types import CaseResult, GradeResult, Observation, RunResult  # noqa: E402

MIN_MAX_WORKERS = 4
DEFAULT_MAX_WORKERS = 4
DEFAULT_TIMEOUT_SECONDS = 30.0
SCHEMA_VERSION = "ashr.runner.v1"
A1_RUN_SCHEMA_VERSION = "ashr.clone.run_result.v1"
PASSED = "passed"
FAILED = "failed"
ERROR = "error"
TIMEOUT = "timeout"
_MISSING = object()


def normalize_max_workers(max_workers: int | None) -> int:
    requested = DEFAULT_MAX_WORKERS if max_workers is None else int(max_workers)
    if requested < 1:
        raise ValueError("max_workers must be positive")
    return max(MIN_MAX_WORKERS, requested)


def load_cases(path: str | Path) -> list[Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, Mapping) else payload
    if not isinstance(cases, list):
        raise ValueError("cases must be a JSON list")
    return list(cases)


def write_results_json(results: Mapping[str, Any], path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(_jsonable(results), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return output


class BatchRunner:
    def __init__(self, *, max_workers: int | None = DEFAULT_MAX_WORKERS, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.max_workers = normalize_max_workers(max_workers)
        self.timeout_seconds = timeout_seconds

    def run(self, cases: Iterable[Any]) -> dict[str, Any]:
        return run_batch(cases, max_workers=self.max_workers, timeout_seconds=self.timeout_seconds)


class LocalEvalRunner:
    def __init__(self, agent: Any, *, dataset_id: str = "local-dataset", runner_id: str = "a1-local-runner", max_workers: int | None = DEFAULT_MAX_WORKERS, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.agent = agent
        self.dataset_id = dataset_id
        self.runner_id = runner_id
        self.max_workers = normalize_max_workers(max_workers)
        self.timeout_seconds = timeout_seconds

    def run(self, cases: Iterable[Any]) -> dict[str, Any]:
        return run_agent_batch(self.agent, cases, dataset_id=self.dataset_id, runner_id=self.runner_id, max_workers=self.max_workers, timeout_seconds=self.timeout_seconds)


def run_file(input_path: str | Path, output_path: str | Path, *, max_workers: int | None = DEFAULT_MAX_WORKERS, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    results = run_batch(load_cases(input_path), max_workers=max_workers, timeout_seconds=timeout_seconds)
    write_results_json(results, output_path)
    return results


def run_agent_file(input_path: str | Path, output_path: str | Path, agent: Any, *, dataset_id: str = "local-dataset", runner_id: str = "a1-local-runner", max_workers: int | None = DEFAULT_MAX_WORKERS, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    results = run_agent_batch(agent, load_cases(input_path), dataset_id=dataset_id, runner_id=runner_id, max_workers=max_workers, timeout_seconds=timeout_seconds)
    write_results_json(results, output_path)
    return results


def run_batch(cases: Iterable[Any], *, max_workers: int | None = DEFAULT_MAX_WORKERS, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    case_list = list(cases)
    worker_count = normalize_max_workers(max_workers)
    ordered: list[dict[str, Any] | None] = [None] * len(case_list)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(run_case, case, index=index, timeout_seconds=timeout_seconds): index for index, case in enumerate(case_list)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                ordered[index] = future.result()
            except BaseException as exc:
                ordered[index] = _error_result(case_list[index], index, exc)
    return _batch_payload([item for item in ordered if item is not None], worker_count)


def run_cases(cases: Iterable[Any], *, max_workers: int | None = DEFAULT_MAX_WORKERS, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    return run_batch(cases, max_workers=max_workers, timeout_seconds=timeout_seconds)


def execute_batch(cases: Iterable[Any], *, max_workers: int | None = DEFAULT_MAX_WORKERS, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    return run_batch(cases, max_workers=max_workers, timeout_seconds=timeout_seconds)


def run_case(case: Any, *, index: int = 0, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    mapping, _ = _normalize_case(case, index)
    effective_timeout = _effective_timeout(mapping, timeout_seconds)
    if effective_timeout is None:
        return _execute_case(case, index)
    box: dict[str, dict[str, Any]] = {}
    thread = threading.Thread(target=lambda: box.setdefault("result", _execute_case(case, index)), daemon=True)
    thread.start()
    thread.join(effective_timeout)
    if thread.is_alive():
        return _timeout_result(case, index, effective_timeout)
    return box["result"]


def execute_case(case: Any, *, index: int = 0) -> dict[str, Any]:
    return _execute_case(case, index)


def run_agent_batch(agent: Any, cases: Iterable[Any], *, dataset_id: str = "local-dataset", runner_id: str = "a1-local-runner", max_workers: int | None = DEFAULT_MAX_WORKERS, timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    case_list = list(cases)
    worker_count = normalize_max_workers(max_workers)
    started_at = _utc_now()
    run_id = _stable_run_id(dataset_id, runner_id, case_list, started_at)
    ordered: list[dict[str, Any] | None] = [None] * len(case_list)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(_run_agent_case, _new_agent(agent), case, index, run_id, timeout_seconds): index for index, case in enumerate(case_list)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                ordered[index] = future.result()
            except BaseException as exc:
                ordered[index] = _agent_error_case(case_list[index], index, run_id, type(exc).__name__, str(exc))
    ended_at = _utc_now()
    case_results = [item for item in ordered if item is not None]
    passed = sum(1 for item in case_results if item["status"] == PASSED)
    failed = sum(1 for item in case_results if item["status"] == FAILED)
    errored = sum(1 for item in case_results if item["status"] == ERROR)
    timed_out = sum(1 for item in case_results if item["status"] == TIMEOUT)
    trace_completeness = _trace_completeness(case_results)
    result = RunResult(
        run_id=run_id,
        dataset_id=dataset_id,
        runner_id=runner_id,
        status=PASSED if passed == len(case_results) else "completed_with_errors" if errored or timed_out else FAILED,
        total_cases=len(case_results),
        passed=passed,
        failed=failed,
        errored=errored,
        timed_out=timed_out,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=_duration_ms(started_at, ended_at),
        max_workers=worker_count,
        trace_completeness=trace_completeness,
        cases=case_results,
        aggregate_metrics={"schema_version": A1_RUN_SCHEMA_VERSION, "trace_completeness": trace_completeness, "passed": passed, "failed": failed, "errored": errored, "timed_out": timed_out, "total_tool_calls": sum(len(c.get("agent_output", {}).get("tool_calls", [])) for c in case_results)},
        metadata={"local_only": True, "ashr_api_used": False},
    )
    return result.to_dict()


def load_agent_target(target: str) -> Any:
    return _resolve_target(target)


def _batch_payload(results: list[dict[str, Any]], max_workers: int) -> dict[str, Any]:
    summary = {"errors": sum(1 for item in results if item["status"] == ERROR), "failed": sum(1 for item in results if item["status"] == FAILED), "passed": sum(1 for item in results if item["status"] == PASSED), "timeouts": sum(1 for item in results if item["status"] == TIMEOUT), "total": len(results)}
    summary["completed"] = summary["passed"] + summary["failed"] + summary["errors"]
    return {"schema_version": SCHEMA_VERSION, "max_workers": max_workers, "summary": summary, "results": [_jsonable(item) for item in results]}


def _execute_case(case: Any, index: int) -> dict[str, Any]:
    mapping, case_id = _normalize_case(case, index)
    base = {"id": case_id, "case_id": case_id, "index": index}
    try:
        output = _run_case_target(mapping) if _has_target(mapping) else _literal_case_output(mapping)
        expected = _jsonable(mapping.get("expected"))
        if "expected" in mapping:
            base.update({"expected": expected, "passed": output == expected, "status": PASSED if output == expected else FAILED})
        else:
            base.update({"passed": True, "status": PASSED})
        base["output"] = _jsonable(output)
        return base
    except BaseException as exc:
        return _error_result(mapping, index, exc)


def _run_case_target(case: Mapping[str, Any]) -> Any:
    func = _resolve_target(case.get("target", case.get("callable", _MISSING)))
    kwargs = dict(case.get("kwargs") or {})
    if "args" in case:
        return func(*case["args"], **kwargs)
    if case.get("call_with") == "kwargs":
        return func(**dict(case.get("input", {})), **kwargs)
    if "input" in case:
        return func(case["input"], **kwargs)
    if "prompt" in case:
        return func(case["prompt"], **kwargs)
    return func(**kwargs)


def _resolve_target(target: Any) -> Callable[..., Any]:
    if callable(target):
        return target
    if not isinstance(target, str) or not target.strip():
        raise TypeError("target must be a callable or module:qualname string")
    module_name, sep, qualname = target.strip().partition(":")
    if not sep:
        module_name, _, qualname = target.strip().rpartition(".")
    module = importlib.import_module(module_name)
    resolved: Any = module
    for part in qualname.split("."):
        resolved = getattr(resolved, part)
    if not callable(resolved):
        raise TypeError(f"target {target!r} resolved to a non-callable value")
    return resolved


def _run_agent_case(agent: Any, case: Any, index: int, run_id: str, timeout_seconds: float | None) -> dict[str, Any]:
    mapping, _ = _normalize_case(case, index)
    effective_timeout = _effective_timeout(mapping, timeout_seconds)
    if effective_timeout is not None and effective_timeout <= 0:
        return _agent_timeout_case(mapping, index, run_id, effective_timeout)
    box: dict[str, dict[str, Any]] = {}
    error: dict[str, BaseException] = {}

    def worker() -> None:
        try:
            box["result"] = _execute_agent_case(agent, mapping, index, run_id)
        except BaseException as exc:
            error["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(effective_timeout)
    if thread.is_alive():
        return _agent_timeout_case(mapping, index, run_id, effective_timeout)
    if "error" in error:
        exc = error["error"]
        return _agent_error_case(mapping, index, run_id, type(exc).__name__, str(exc))
    return box["result"]


def _execute_agent_case(agent: Any, case: Mapping[str, Any], index: int, run_id: str) -> dict[str, Any]:
    started_at = _utc_now()
    case_id = str(case.get("case_id") or case.get("id") or f"case-{index + 1:03d}")
    scenario_id = str(case.get("scenario_id") or case.get("scenario") or case_id)
    prompt = _case_prompt(case)
    expected = _expected_payload(case)
    adapter = AgentAdapter(agent)
    reset_ok = adapter.reset()
    user_obs = _observation(run_id, case_id, 0, "message", "user", prompt, started_at, started_at, metadata={"scenario_id": scenario_id})
    turn = adapter.respond(prompt)
    ended_at = _utc_now()
    status = _case_status(turn, expected, reset_ok)
    grade = _grade_result(scenario_id, turn, expected, status, reset_ok)
    assistant_obs = _observation(run_id, case_id, 1, "agent_response", "assistant", turn.text, started_at, ended_at, tool_calls=turn.tool_calls, latency_ms=turn.latency_ms, status="error" if turn.error else "ok", error=turn.error.get("message") if turn.error else None, metadata={"reset_ok": reset_ok}, vm_stream=_case_vm_stream(case, turn, started_at, ended_at))
    return CaseResult(case_id=case_id, scenario_id=scenario_id, title=str(case.get("title") or case.get("name") or scenario_id), status=status, started_at=started_at, ended_at=ended_at, latency_ms=_duration_ms(started_at, ended_at), observations=[user_obs, assistant_obs], grade=grade.to_dict(), agent_output=turn.to_dict(), expected=expected, error=turn.error.get("message") if turn.error else None, metadata=_jsonable(case.get("metadata", {}))).to_dict()


def _new_agent(agent: Any) -> Any:
    if isinstance(agent, str):
        target = _resolve_target(agent)
        return target() if inspect.isclass(target) else target
    return agent() if inspect.isclass(agent) else agent


def _case_prompt(case: Mapping[str, Any]) -> str:
    for key in ("prompt", "input", "message", "user_text"):
        if key in case:
            value = case[key]
            return value if isinstance(value, str) else json.dumps(_jsonable(value), sort_keys=True)
    return ""


def _case_status(turn: AgentResult, expected: Mapping[str, Any], reset_ok: bool) -> str:
    if turn.error or not reset_ok:
        return ERROR
    return PASSED if _grade_result("scenario", turn, expected, PASSED, reset_ok).passed else FAILED


def _grade_result(scenario_id: str, turn: AgentResult, expected: Mapping[str, Any], status: str, reset_ok: bool) -> GradeResult:
    expected_text = expected.get("text") or expected.get("final_text")
    expected_tools = expected.get("tool_calls") or expected.get("tools") or []
    text_ok = True if expected_text is None else str(expected_text) == turn.text
    tools_ok = _tools_match(expected_tools, turn.tool_calls)
    passed = status == PASSED and reset_ok and text_ok and tools_ok and turn.error is None
    if not expected and reset_ok and turn.error is None:
        passed = True
    return GradeResult(scenario_id=scenario_id, passed=passed, score=1.0 if passed else 0.0, label=PASSED if passed else status, reason="local checks passed" if passed else "local expected/actual mismatch", expected=dict(expected), actual={"text": turn.text, "tool_calls": turn.tool_calls}, metrics={"text_match": text_ok, "tool_match": tools_ok, "reset_ok": reset_ok, "latency_ms": turn.latency_ms})


def _tools_match(expected: Any, actual: list[Mapping[str, Any]]) -> bool:
    if not expected:
        return True
    if isinstance(expected, Mapping):
        expected = [expected]
    names = [str(item.get("name")) for item in actual]
    return all((item in names if isinstance(item, str) else str(item.get("name")) in names) for item in expected)


def _observation(run_id: str, case_id: str, turn_index: int, event_type: str, role: str, content: Any, started_at: str, ended_at: str, *, tool_calls: list[Mapping[str, Any]] | None = None, latency_ms: int | None = None, status: str = "ok", error: str | None = None, metadata: Mapping[str, Any] | None = None, vm_stream: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return Observation(observation_id="obs_" + hashlib.sha256(f"{run_id}:{case_id}:{turn_index}:{event_type}".encode()).hexdigest()[:16], run_id=run_id, case_id=case_id, turn_index=turn_index, event_type=event_type, role=role, content=_jsonable(content), tool_calls=_jsonable(list(tool_calls or [])), started_at=started_at, ended_at=ended_at, latency_ms=latency_ms, status=status, error=error, metadata=_jsonable(dict(metadata or {})), vm_stream=_jsonable(dict(vm_stream)) if vm_stream else None).to_dict()


def _case_vm_stream(case: Mapping[str, Any], turn: AgentResult, started_at: str, ended_at: str) -> dict[str, Any]:
    logs = [{"ts": 0, "type": "action", "data": {"action": "respond", "input": _case_prompt(case)}}, {"ts": turn.latency_ms, "type": "console", "data": {"level": "error" if turn.error else "log", "message": turn.text}}]
    logs.extend({"ts": turn.latency_ms, "type": "tool_call", "data": dict(tool)} for tool in turn.tool_calls)
    return {"provider": "local-runner", "session_id": str(case.get("case_id") or case.get("id") or "local"), "duration_ms": _duration_ms(started_at, ended_at), "logs": _jsonable(logs), "metadata": {"synthetic": True}}


def _agent_timeout_case(case: Any, index: int, run_id: str, timeout_seconds: float | None) -> dict[str, Any]:
    return _agent_error_case(case, index, run_id, "TimeoutError", f"case timed out after {timeout_seconds:g} seconds", status=TIMEOUT)


def _agent_error_case(case: Any, index: int, run_id: str, error_type: str, message: str, status: str = ERROR) -> dict[str, Any]:
    mapping, case_id = _normalize_case(case, index)
    now = _utc_now()
    scenario_id = str(mapping.get("scenario_id") or mapping.get("scenario") or case_id)
    grade = GradeResult(scenario_id=scenario_id, passed=False, score=0.0, label=status, reason=message, expected=_expected_payload(mapping), actual={"error": {"type": error_type, "message": message}})
    obs = _observation(run_id, case_id, 0, status, "system", message, now, now, status="error", error=message)
    return CaseResult(case_id=case_id, scenario_id=scenario_id, title=str(mapping.get("title") or scenario_id), status=status, started_at=now, ended_at=now, latency_ms=0, observations=[obs], grade=grade.to_dict(), agent_output={"text": "", "tool_calls": [], "status": status, "error": {"type": error_type, "message": message}}, expected=_expected_payload(mapping), error=message).to_dict()


def _normalize_case(case: Any, index: int) -> tuple[dict[str, Any], str]:
    if dataclasses.is_dataclass(case):
        mapping: MutableMapping[str, Any] = dataclasses.asdict(case)
    elif isinstance(case, Mapping):
        mapping = dict(case)
    else:
        mapping = {"input": case}
    case_id = str(mapping.get("id", mapping.get("case_id", mapping.get("name", f"case-{index + 1:03d}"))))
    mapping.setdefault("id", case_id)
    mapping.setdefault("case_id", case_id)
    return dict(mapping), case_id


def _literal_case_output(case: Mapping[str, Any]) -> Any:
    for key in ("actual", "output", "result", "input"):
        if key in case:
            return case[key]
    return None


def _expected_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    expected = case.get("expected", {})
    if isinstance(expected, Mapping):
        return dict(expected)
    return {} if expected is None else {"text": expected}


def _effective_timeout(case: Mapping[str, Any], default_timeout: float | None) -> float | None:
    for key in ("timeout_seconds", "timeout", "case_timeout_seconds"):
        if key in case and case[key] is not None:
            return float(case[key])
    return None if default_timeout is None else float(default_timeout)


def _has_target(case: Mapping[str, Any]) -> bool:
    return "target" in case or "callable" in case


def _timeout_result(case: Any, index: int, timeout_seconds: float) -> dict[str, Any]:
    _, case_id = _normalize_case(case, index)
    return {"case_id": case_id, "id": case_id, "index": index, "status": TIMEOUT, "passed": False, "timeout_seconds": timeout_seconds, "error": {"type": "TimeoutError", "message": f"case timed out after {timeout_seconds:g} seconds"}}


def _error_result(case: Any, index: int, exc: BaseException) -> dict[str, Any]:
    _, case_id = _normalize_case(case, index)
    return {"case_id": case_id, "id": case_id, "index": index, "status": ERROR, "passed": False, "error": {"type": type(exc).__name__, "message": str(exc)}}


def _trace_completeness(cases: list[Mapping[str, Any]]) -> float:
    if not cases:
        return 1.0
    complete = sum(1 for case in cases if case.get("observations") and all(obs.get("started_at") and obs.get("ended_at") for obs in case["observations"]) and any(obs.get("vm_stream") for obs in case["observations"]))
    return round(complete / len(cases), 4)


def _stable_run_id(dataset_id: str, runner_id: str, cases: list[Any], started_at: str) -> str:
    return "run_" + hashlib.sha256(json.dumps(_jsonable({"dataset_id": dataset_id, "runner_id": runner_id, "cases": cases, "started_at": started_at}), sort_keys=True).encode()).hexdigest()[:16]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _duration_ms(started_at: str, ended_at: str) -> int:
    return max(0, int((_parse_time(ended_at) - _parse_time(started_at)).total_seconds() * 1000))


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=repr)]
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value
