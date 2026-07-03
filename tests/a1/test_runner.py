import json
import subprocess
import sys
import time
from pathlib import Path

from examples.agents.mock_agent import RespondingMockAgent
from services.runner.runner import BatchRunner, LocalEvalRunner, run_agent_batch, run_batch, run_case, write_results_json


class CloneTrackingAgent:
    def __init__(self):
        self.clone_count = 0
        self.history = []

    def clone(self):
        self.clone_count += 1
        return CloneTrackingAgent()

    def reset(self):
        self.history = []

    def respond(self, prompt):
        self.history.append(prompt)
        return {"text": f"{len(self.history)}:{prompt}"}


class MixedOutcomeAgent:
    def reset(self):
        pass

    def respond(self, prompt):
        if prompt == "error":
            raise RuntimeError("agent boom")
        if prompt == "slow":
            time.sleep(1)
            return {"text": "late"}
        return {"text": prompt}


class DeepcopyTrackingAgent:
    def __init__(self):
        self.history = []

    def __deepcopy__(self, memo):
        return DeepcopyTrackingAgent()

    def reset(self):
        self.history = []

    def respond(self, prompt):
        self.history.append(prompt)
        return {"text": f"{len(self.history)}:{prompt}"}


class LockedSharedAgent:
    def __init__(self):
        self.history = []

    def __deepcopy__(self, memo):
        raise TypeError("cannot deepcopy")

    def reset(self):
        self.history = []

    def respond(self, prompt):
        self.history.append(prompt)
        return {"text": f"{len(self.history)}:{prompt}"}


def test_run_batch_supports_30_cases_and_preserves_order():
    cases = [{"id": f"case-{index:02d}", "input": index, "expected": index} for index in range(30)]
    results = run_batch(cases, max_workers=1, timeout_seconds=None)
    assert results["max_workers"] >= 4
    assert results["summary"]["passed"] == 30
    assert [result["case_id"] for result in results["results"]] == [case["id"] for case in cases]


def test_run_batch_tracks_mixed_failure_error_and_timeout():
    def boom(_payload):
        raise RuntimeError("boom")

    def sleepy(_payload):
        time.sleep(1)
        return "late"

    cases = [
        {"id": "pass", "input": "ok", "expected": "ok"},
        {"id": "fail", "input": "actual", "expected": "expected"},
        {"id": "error", "target": boom, "input": {}},
        {"id": "timeout", "target": sleepy, "input": {}, "timeout_seconds": 0.05},
    ]
    results = run_batch(cases, max_workers=4, timeout_seconds=None)
    assert results["summary"]["passed"] == 1
    assert results["summary"]["failed"] == 1
    assert results["summary"]["errors"] == 1
    assert results["summary"]["timeouts"] == 1
    assert [result["status"] for result in results["results"]] == ["passed", "failed", "error", "timeout"]


def test_per_case_timeout_marks_case_without_blocking_batch():
    def sleepy(_payload):
        time.sleep(1)
        return "late"

    started = time.monotonic()
    result = run_case({"id": "sleepy", "target": sleepy, "input": {}, "timeout_seconds": 0.05})
    assert result["status"] == "timeout"
    assert time.monotonic() - started < 0.5


def test_json_output_is_deterministic(tmp_path):
    results = BatchRunner(max_workers=2, timeout_seconds=None).run([{"id": "b", "input": {"z": 1, "a": 2}, "expected": {"a": 2, "z": 1}}])
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_results_json(results, first)
    write_results_json(results, second)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_cli_writes_results_file(tmp_path):
    input_path = tmp_path / "cases.json"
    output_path = tmp_path / "results.json"
    input_path.write_text(json.dumps({"cases": [{"id": "literal", "input": "ok", "expected": "ok"}]}), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-B", "-m", "services.runner.cli", "--input", str(input_path), "--output", str(output_path), "--max-workers", "1", "--no-timeout"], cwd=str(Path(__file__).resolve().parents[2]), text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert output_path.exists()
    assert "1 passed" in completed.stdout
    assert json.loads(output_path.read_text(encoding="utf-8"))["summary"]["passed"] == 1


def test_cli_fail_on_case_failure_returns_nonzero_and_writes_json(tmp_path):
    input_path = tmp_path / "cases.json"
    output_path = tmp_path / "results.json"
    input_path.write_text(json.dumps({"cases": [{"id": "literal", "input": "actual", "expected": "expected"}]}), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-B", "-m", "services.runner.cli", "--input", str(input_path), "--output", str(output_path), "--max-workers", "4", "--no-timeout", "--fail-on-case-failure"], cwd=str(Path(__file__).resolve().parents[2]), text=True, capture_output=True, check=False)
    assert completed.returncode == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"]["failed"] == 1
    assert "1 failed" in completed.stdout


def test_agent_runner_emits_a3_run_result_with_complete_trace():
    cases = [{"id": f"math-{index:02d}", "scenario_id": f"scenario-{index:02d}", "prompt": "What is 19 + 23?", "expected": {"text": "The answer is 42.", "tool_calls": [{"name": "calculator"}]}} for index in range(30)]
    result = run_agent_batch(RespondingMockAgent, cases, dataset_id="a2-local-scenarios", runner_id="a1-local-runner", max_workers=1, timeout_seconds=5)
    assert result["total_cases"] == 30
    assert result["max_workers"] >= 4
    assert result["passed"] == 30
    assert result["trace_completeness"] >= 0.95
    assert result["cases"][0]["observations"][1]["vm_stream"]["provider"] == "local-runner"


def test_local_eval_runner_wrapper_uses_same_contract():
    result = LocalEvalRunner(RespondingMockAgent, max_workers=4, timeout_seconds=5).run([{"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}}])
    assert result["passed"] == 1
    assert result["cases"][0]["observations"][0]["role"] == "user"
    assert result["cases"][0]["observations"][1]["role"] == "assistant"


def test_existing_stateful_agent_instance_is_cloned_per_case():
    agent = CloneTrackingAgent()
    cases = [{"id": f"clone-{index}", "prompt": f"case {index}", "expected": {"text": f"1:case {index}"}} for index in range(8)]
    result = run_agent_batch(agent, cases, max_workers=4, timeout_seconds=5)
    assert result["passed"] == 8
    assert agent.clone_count == 8
    assert agent.history == []


def test_agent_runner_tracks_mixed_pass_fail_error_and_timeout():
    cases = [
        {"id": "pass", "prompt": "ok", "expected": {"text": "ok"}},
        {"id": "fail", "prompt": "actual", "expected": {"text": "expected"}},
        {"id": "error", "prompt": "error", "expected": {"text": "unused"}},
        {"id": "timeout", "prompt": "slow", "timeout_seconds": 0.05, "expected": {"text": "late"}},
    ]
    result = run_agent_batch(MixedOutcomeAgent, cases, max_workers=4, timeout_seconds=5)
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["errored"] == 1
    assert result["timed_out"] == 1
    assert result["status"] == "completed_with_errors"
    assert [case["status"] for case in result["cases"]] == ["passed", "failed", "error", "timeout"]
    assert result["cases"][2]["agent_output"]["error"]["type"] == "RuntimeError"


def test_agent_cli_fail_on_case_failure_returns_nonzero_and_writes_json(tmp_path):
    input_path = tmp_path / "agent_cases.json"
    output_path = tmp_path / "agent_results.json"
    input_path.write_text(json.dumps({"cases": [{"id": "fail", "prompt": "actual", "expected": {"text": "expected"}}]}), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-B", "-m", "services.runner.cli", "--input", str(input_path), "--output", str(output_path), "--agent", "tests.a1.test_runner:MixedOutcomeAgent", "--max-workers", "4", "--timeout", "5", "--fail-on-case-failure"], cwd=str(Path(__file__).resolve().parents[2]), text=True, capture_output=True, check=False)
    assert completed.returncode == 1
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["failed"] == 1
    assert "1 failed" in completed.stdout


def test_existing_agent_instance_deepcopy_fallback_isolated_per_case():
    agent = DeepcopyTrackingAgent()
    cases = [{"id": f"copy-{index}", "prompt": f"case {index}", "expected": {"text": f"1:case {index}"}} for index in range(8)]
    result = run_agent_batch(agent, cases, max_workers=4, timeout_seconds=5)
    assert result["passed"] == 8
    assert agent.history == []


def test_non_cloneable_agent_instance_uses_shared_lock():
    agent = LockedSharedAgent()
    cases = [{"id": f"locked-{index}", "prompt": f"case {index}", "expected": {"text": f"1:case {index}"}} for index in range(8)]
    result = run_agent_batch(agent, cases, max_workers=4, timeout_seconds=5)
    assert result["passed"] == 8
    assert len(agent.history) == 1
