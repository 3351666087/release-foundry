import json
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

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
        self.active = 0
        self.max_active = 0

    def __deepcopy__(self, memo):
        raise TypeError("cannot deepcopy")

    def reset(self):
        self.history = []

    def respond(self, prompt):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        time.sleep(0.01)
        self.history.append(prompt)
        result = {"text": f"{len(self.history)}:{prompt}"}
        self.active -= 1
        return result


def assert_a3_run_result_schema_guard(result):
    required_run_keys = {"run_id", "dataset_id", "runner_id", "status", "total_cases", "passed", "failed", "errored", "timed_out", "started_at", "ended_at", "duration_ms", "max_workers", "trace_completeness", "cases", "aggregate_metrics", "metadata", "field_map_version"}
    assert required_run_keys <= set(result)
    assert result["total_cases"] >= 0
    assert result["passed"] >= 0
    assert result["failed"] >= 0
    assert result["errored"] >= 0
    assert result["timed_out"] >= 0
    assert result["duration_ms"] >= 0
    assert result["max_workers"] >= 4
    assert 0 <= result["trace_completeness"] <= 1
    assert result["metadata"]["local_only"] is True
    assert result["metadata"]["ashr_api_used"] is False
    assert result["aggregate_metrics"]["schema_version"] == "ashr.clone.run_result.v1"

    required_case_keys = {"case_id", "scenario_id", "title", "status", "started_at", "ended_at", "latency_ms", "observations", "grade", "agent_output", "expected", "metadata"}
    required_observation_keys = {"observation_id", "run_id", "case_id", "turn_index", "event_type", "role", "started_at", "ended_at", "status", "metadata"}
    required_grade_keys = {"scenario_id", "passed", "score", "label", "reason", "expected", "actual"}
    required_agent_keys = {"schema_version", "text", "tool_calls", "status", "latency_ms", "metadata"}
    for case in result["cases"]:
        assert required_case_keys <= set(case)
        assert case["latency_ms"] >= 0
        assert required_grade_keys <= set(case["grade"])
        assert 0 <= case["grade"]["score"] <= 1
        assert required_agent_keys <= set(case["agent_output"])
        assert case["agent_output"]["schema_version"] == "ashr.clone.agent_turn.v1"
        assert case["agent_output"]["latency_ms"] >= 0
        for observation in case["observations"]:
            assert required_observation_keys <= set(observation)
            assert observation["turn_index"] >= 0
            if observation.get("latency_ms") is not None:
                assert observation["latency_ms"] >= 0
            if observation.get("vm_stream"):
                stream = observation["vm_stream"]
                assert {"provider", "session_id", "duration_ms", "logs", "metadata"} <= set(stream)
                assert stream["duration_ms"] >= 0


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


def test_negative_default_timeout_is_rejected():
    cases = [{"id": "literal", "input": "ok", "expected": "ok"}]
    try:
        run_batch(cases, timeout_seconds=-0.1)
    except ValueError as exc:
        assert "timeout_seconds must be non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("negative timeout should be rejected")

    try:
        run_agent_batch(RespondingMockAgent, cases, timeout_seconds=-0.1)
    except ValueError as exc:
        assert "timeout_seconds must be non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("negative agent timeout should be rejected")


def test_negative_agent_case_timeout_is_schema_safe_error():
    case = {"id": "bad-timeout", "prompt": "hello", "timeout_seconds": -0.1, "expected": {"text": "Echo: hello"}}
    result = run_agent_batch(RespondingMockAgent, [case], max_workers=4, timeout_seconds=5)
    emitted = result["cases"][0]
    assert emitted["status"] == "error"
    assert emitted["latency_ms"] == 0
    assert emitted["agent_output"]["latency_ms"] == 0
    assert emitted["observations"][1]["latency_ms"] == 0
    assert emitted["observations"][1]["vm_stream"]["duration_ms"] == 0
    assert "timeout_seconds must be non-negative" in emitted["error"]


def test_emitted_mixed_agent_run_result_matches_schema_guard():
    cases = [
        {"id": "pass", "prompt": "ok", "expected": {"text": "ok"}},
        {"id": "fail", "prompt": "actual", "expected": {"text": "expected"}},
        {"id": "error", "prompt": "error", "expected": {"text": "unused"}},
        {"id": "timeout", "prompt": "slow", "timeout_seconds": 0.05, "expected": {"text": "late"}},
        {"id": "bad-timeout", "prompt": "ok", "timeout_seconds": -0.1, "expected": {"text": "ok"}},
    ]
    result = run_agent_batch(MixedOutcomeAgent, cases, max_workers=4, timeout_seconds=5)
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["errored"] == 2
    assert result["timed_out"] == 1
    assert_a3_run_result_schema_guard(result)


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


def test_cli_rejects_negative_timeout(tmp_path):
    input_path = tmp_path / "cases.json"
    output_path = tmp_path / "results.json"
    input_path.write_text(json.dumps({"cases": [{"id": "literal", "input": "ok", "expected": "ok"}]}), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-B", "-m", "services.runner.cli", "--input", str(input_path), "--output", str(output_path), "--timeout", "-0.1"], cwd=str(Path(__file__).resolve().parents[2]), text=True, capture_output=True, check=False)
    assert completed.returncode == 2
    assert "--timeout must be non-negative" in completed.stderr
    assert not output_path.exists()


def test_agent_runner_emits_a3_run_result_with_complete_trace():
    cases = [{"id": f"math-{index:02d}", "scenario_id": f"scenario-{index:02d}", "prompt": "What is 19 + 23?", "expected": {"text": "The answer is 42.", "tool_calls": [{"name": "calculator"}]}} for index in range(80)]
    result = run_agent_batch(RespondingMockAgent, cases, dataset_id="a2-local-scenarios", runner_id="a1-local-runner", max_workers=1, timeout_seconds=5)
    assert result["total_cases"] == 80
    assert result["max_workers"] >= 4
    assert result["passed"] == 80
    assert result["trace_completeness"] >= 0.95
    assert result["cases"][0]["observations"][1]["vm_stream"]["provider"] == "local-runner"


def test_agent_runner_compares_expected_tool_arguments_when_present():
    class WrongArgumentAgent:
        def reset(self):
            pass

        def respond(self, prompt):
            return {"text": "done", "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "A-999"}}]}

    cases = [{"id": "wrong-args", "prompt": "lookup", "expected": {"text": "done", "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "A-100"}}]}}]
    result = run_agent_batch(WrongArgumentAgent, cases, max_workers=4, timeout_seconds=5)

    assert result["failed"] == 1
    assert result["cases"][0]["grade"]["metrics"]["tool_match"] is False
    assert result["cases"][0]["status"] == "failed"


def test_agent_runner_keeps_name_only_tool_expectations_compatible():
    class DifferentArgumentAgent:
        def reset(self):
            pass

        def respond(self, prompt):
            return {"text": "done", "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "A-999"}}]}

    cases = [{"id": "name-only", "prompt": "lookup", "expected": {"text": "done", "tool_calls": [{"name": "lookup_order"}]}}]
    result = run_agent_batch(DifferentArgumentAgent, cases, max_workers=4, timeout_seconds=5)

    assert result["passed"] == 1


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
    timeout_case = result["cases"][3]
    assert timeout_case["grade"]["actual"]["error"]["type"] == "TimeoutError"
    assert timeout_case["agent_output"]["schema_version"] == "ashr.clone.agent_turn.v1"
    assert timeout_case["agent_output"]["latency_ms"] == 50
    assert timeout_case["agent_output"]["metadata"]["synthetic"] is True
    assert len(timeout_case["observations"]) == 2
    assert timeout_case["observations"][0]["role"] == "user"
    assert timeout_case["observations"][1]["vm_stream"]["metadata"]["failure"] == "timeout"
    started = datetime.fromisoformat(timeout_case["started_at"].replace("Z", "+00:00"))
    ended = datetime.fromisoformat(timeout_case["ended_at"].replace("Z", "+00:00"))
    assert int((ended - started).total_seconds() * 1000) == timeout_case["latency_ms"]
    assert result["trace_completeness"] == 1.0


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
    assert agent.max_active == 1
