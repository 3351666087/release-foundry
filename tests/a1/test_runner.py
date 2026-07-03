import json
import subprocess
import sys
import time
from pathlib import Path

from examples.agents.mock_agent import RespondingMockAgent
from services.runner.runner import BatchRunner, LocalEvalRunner, run_agent_batch, run_batch, run_case, write_results_json


def test_run_batch_supports_30_cases_and_preserves_order():
    cases = [{"id": f"case-{index:02d}", "input": index, "expected": index} for index in range(30)]
    results = run_batch(cases, max_workers=1, timeout_seconds=None)
    assert results["max_workers"] >= 4
    assert results["summary"]["passed"] == 30
    assert [result["case_id"] for result in results["results"]] == [case["id"] for case in cases]


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
    completed = subprocess.run([sys.executable, "-m", "services.runner.cli", "--input", str(input_path), "--output", str(output_path), "--max-workers", "1", "--no-timeout"], cwd=str(Path(__file__).resolve().parents[2]), text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr


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
