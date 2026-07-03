from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ashr_clone.trace import FIXED_STARTED_AT, TraceEvent, TraceRecorder, build_run_fixture, load_run_fixture, replay_observations, stable_id, trace_events_from_vm_stream, validate_run_fixture, write_run_fixture  # noqa: E402

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


@dataclass(frozen=True)
class Scenario:
    name: str
    task: str
    prompt: str
    labels: tuple[str, ...]


SCENARIOS = {
    "echo_success": Scenario("echo_success", "Return a concise echo of the user request.", "Say hello to the trace harness.", ("a3", "dialogue", "success")),
    "tool_math_success": Scenario("tool_math_success", "Use the local calculator tool and return the answer.", "What is 19 + 23?", ("a3", "tool", "success")),
    "recoverable_error": Scenario("recoverable_error", "Handle a missing local lookup and provide a fallback answer.", "Look up release channel beta-404 and continue if it is missing.", ("a3", "tool", "degraded")),
}


class SafeArithmetic:
    OPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}

    @classmethod
    def evaluate(cls, expression: str) -> int | float:
        return cls._eval(ast.parse(expression, mode="eval").body)

    @classmethod
    def _eval(cls, node: ast.AST) -> int | float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in cls.OPS:
            return cls.OPS[type(node.op)](cls._eval(node.left), cls._eval(node.right))
        raise ValueError("expression must contain only numbers and arithmetic operators")


def _extract_expression(prompt: str) -> str:
    matches = [m.group(0).strip() for m in re.finditer(r"[-+*/()\d\s.]+", prompt) if any(c.isdigit() for c in m.group(0))]
    if not matches:
        raise ValueError("no arithmetic expression found")
    return max(matches, key=len)


def _format_number(value: int | float) -> str:
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


class MockAgent:
    def __init__(self, name: str = "mock-agent", started_at: str = FIXED_STARTED_AT) -> None:
        self.name = name
        self.started_at = started_at

    def run(self, scenario: str, prompt: str | None = None) -> dict[str, Any]:
        spec = SCENARIOS[scenario]
        actual_prompt = prompt if prompt is not None else spec.prompt
        recorder = TraceRecorder(run_id=stable_id("run", self.name, scenario, actual_prompt), source=self.name, started_at=self.started_at)
        recorder.control("run.started", data={"scenario": scenario, "agent": self.name})
        recorder.message("user", actual_prompt, data={"scenario": scenario})
        if scenario == "echo_success":
            result = f"Echo: {actual_prompt.strip()}"
            recorder.message("assistant", result, data={"policy": "echo"})
            status = "ok"
        elif scenario == "tool_math_success":
            expression = _extract_expression(actual_prompt)
            call = recorder.tool_call("calculator", {"expression": expression})
            call_id = str(call.observation.data["call_id"])
            value = SafeArithmetic.evaluate(expression)
            recorder.tool_result("calculator", call_id, {"value": value, "expression": expression})
            result = f"The answer is {_format_number(value)}."
            recorder.message("assistant", result, data={"tool_call_id": call_id})
            status = "ok"
        else:
            key_match = re.search(r"\b(beta-\d+)\b", actual_prompt)
            key = key_match.group(1) if key_match else "unknown"
            call = recorder.tool_call("local_lookup", {"key": key, "fixture_only": True})
            call_id = str(call.observation.data["call_id"])
            recorder.tool_result("local_lookup", call_id, {"error": "not_found", "key": key, "fallback": "stable-default"}, status="error")
            result = f"No local record for {key}; continuing with stable-default."
            recorder.message("assistant", result, data={"tool_call_id": call_id, "fallback_used": True})
            status = "degraded"
        recorder.metric("events_emitted", len(recorder.events()) + 2)
        recorder.control("run.finished", status=status, data={"scenario": scenario, "result": result})
        events = recorder.events()
        return build_run_fixture(spec.name, spec.task, events, agent=self.name, expected={"status": status, "final_text": result, "event_count": len(events)}, replay={"entrypoint": "python examples/agents/mock_agent.py", "command": f"--scenario {scenario}", "mode": "deterministic-local"}, labels=spec.labels)

    def run_from_fixture(self, fixture: Mapping[str, Any]) -> list[TraceEvent]:
        validate_run_fixture(fixture)
        return trace_events_from_vm_stream(str(fixture["run"]["run_id"]), fixture["vm_stream"], source=self.name)


class RespondingMockAgent:
    def __init__(self) -> None:
        self.history: list[str] = []
        self.reset_count = 0

    def reset(self) -> None:
        self.history = []
        self.reset_count += 1

    def respond(self, prompt: str) -> dict[str, Any]:
        self.history.append(prompt)
        if any(c.isdigit() for c in prompt) and "+" in prompt:
            expression = _extract_expression(prompt)
            value = SafeArithmetic.evaluate(expression)
            return {"text": f"The answer is {_format_number(value)}.", "tool_calls": [{"name": "calculator", "arguments": {"expression": expression}, "output": {"value": value}}], "metadata": {"mock_agent": "responding"}}
        return {"text": f"Echo: {prompt.strip()}", "tool_calls": [], "metadata": {"mock_agent": "responding"}}


def build_default_fixtures(directory: str | Path = DEFAULT_FIXTURE_DIR) -> list[Path]:
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    agent = MockAgent()
    for scenario in SCENARIOS:
        path = output_dir / f"{scenario}.json"
        write_run_fixture(path, agent.run(scenario))
        paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Ashr trace mock-agent fixtures.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="echo_success")
    parser.add_argument("--prompt")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--write-fixtures", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--list-scenarios", action="store_true")
    args = parser.parse_args(argv)
    if args.list_scenarios:
        print("\n".join(sorted(SCENARIOS)))
        return 0
    if args.replay:
        fixture = load_run_fixture(args.replay)
        print(json.dumps({"name": fixture["name"], "run_id": fixture["run"]["run_id"], "observations": len(list(replay_observations(fixture["events"]))), "final_text": fixture["expected"].get("final_text")}, indent=2, sort_keys=True))
        return 0
    if args.write_fixtures:
        for path in build_default_fixtures(args.write_fixtures):
            print(path)
        return 0
    fixture = MockAgent().run(args.scenario, prompt=args.prompt)
    if args.out:
        write_run_fixture(args.out, fixture)
        print(args.out)
    else:
        print(json.dumps(fixture, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
