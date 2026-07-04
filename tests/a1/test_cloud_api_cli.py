import json
import subprocess
import sys
from pathlib import Path

from services.api.demo import run_agent_cloud_demo, run_agent_cloud_queue_demo


ROOT = Path(__file__).resolve().parents[2]
AGENT_TARGET = "examples.agents.mock_agent:RespondingMockAgent"


def _write_cases(tmp_path):
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "case-1", "prompt": "hello", "expected": {"text": "Echo: hello"}},
                    {"id": "case-2", "prompt": "What is 19 + 23?", "expected": {"text": "The answer is 42.", "tool_calls": [{"name": "calculator"}]}},
                ]
            }
        ),
        encoding="utf-8",
    )
    return cases_path


def test_run_agent_cloud_demo_executes_external_agent_and_writes_fixture(tmp_path):
    fixture_output = tmp_path / "cloud_fixture.json"

    summary = run_agent_cloud_demo(
        agent=AGENT_TARGET,
        input_path=_write_cases(tmp_path),
        fixture_output_path=fixture_output,
        tenant_id="tenant_demo_test",
        project_id="project_demo_test",
        dataset_id="dataset_demo_test",
        runner_id="a1-demo-test",
        timeout_seconds=5,
    )

    fixture = json.loads(fixture_output.read_text(encoding="utf-8"))
    assert summary["run"]["status"] == "completed"
    assert summary["run"]["result_status"] == "passed"
    assert summary["run"]["total_cases"] == 2
    assert summary["run"]["observations"] == 4
    assert summary["outputs"]["fixture"] == str(fixture_output)
    assert summary["metadata"] == {"ashr_api_used": False, "local_only": True}
    assert fixture["metadata"]["ashr_api_used"] is False
    assert fixture["run_result"]["runner_id"] == "a1-demo-test"
    assert fixture["run_result"]["passed"] == 2
    assert len(fixture["observations"]) == 4


def test_cloud_api_cli_demo_run_uses_local_runtime_only(tmp_path):
    cases_path = _write_cases(tmp_path)
    fixture_output = tmp_path / "cli_fixture.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.api.cli",
            "run-agent",
            "--agent",
            AGENT_TARGET,
            "--input",
            str(cases_path),
            "--fixture-output",
            str(fixture_output),
            "--tenant-id",
            "tenant_cli_test",
            "--project-id",
            "project_cli_test",
            "--dataset-id",
            "dataset_cli_test",
            "--runner-id",
            "a1-cli-demo-test",
            "--timeout",
            "5",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Traceback" not in completed.stderr
    summary = json.loads(completed.stdout)
    fixture = json.loads(fixture_output.read_text(encoding="utf-8"))
    assert summary["tenant"]["tenant_id"] == "tenant_cli_test"
    assert summary["project"]["project_id"] == "project_cli_test"
    assert summary["dataset"]["dataset_id"] == "dataset_cli_test"
    assert summary["run"]["status"] == "completed"
    assert summary["metadata"]["ashr_api_used"] is False
    assert fixture["schema_version"] == "ashr.clone.cloud_api.v1"
    assert fixture["run_result"]["runner_id"] == "a1-cli-demo-test"


def test_run_agent_cloud_queue_demo_executes_through_queue_and_writes_fixture(tmp_path):
    fixture_output = tmp_path / "queue_fixture.json"
    summary_output = tmp_path / "queue_summary.json"

    summary = run_agent_cloud_queue_demo(
        agent=AGENT_TARGET,
        input_path=_write_cases(tmp_path),
        fixture_output_path=fixture_output,
        summary_output_path=summary_output,
        tenant_id="tenant_queue_demo_test",
        project_id="project_queue_demo_test",
        dataset_id="dataset_queue_demo_test",
        runner_id="a1-queue-demo-test",
        queue_workers=1,
        max_workers=1,
        timeout_seconds=5,
    )

    fixture = json.loads(fixture_output.read_text(encoding="utf-8"))
    written_summary = json.loads(summary_output.read_text(encoding="utf-8"))
    statuses = [item["status"] for item in summary["queue"]["status_history"]]
    assert summary["run"]["status"] == "completed"
    assert summary["queue"]["queued_status"] == "queued"
    assert statuses == ["queued", "running", "completed"]
    assert summary["queue"]["queue_workers"] == 4
    assert summary["queue"]["runner_max_workers"] == 4
    assert written_summary == summary
    assert fixture["run_result"]["runner_id"] == "a1-queue-demo-test"
    assert fixture["metadata"]["ashr_api_used"] is False


def test_run_agent_cloud_queue_demo_timeout_does_not_write_incomplete_outputs(tmp_path):
    fixture_output = tmp_path / "queue_timeout_fixture.json"
    summary_output = tmp_path / "queue_timeout_summary.json"
    run_output = tmp_path / "queue_timeout_run.json"

    try:
        run_agent_cloud_queue_demo(
            agent="tests.a1.fixtures_sensitive_agent:SlowAgent",
            input_path=_write_cases(tmp_path),
            fixture_output_path=fixture_output,
            summary_output_path=summary_output,
            run_output_path=run_output,
            tenant_id="tenant_queue_timeout_test",
            project_id="project_queue_timeout_test",
            dataset_id="dataset_queue_timeout_test",
            runner_id="a1-queue-timeout-test",
            queue_workers=1,
            max_workers=1,
            timeout_seconds=5,
            wait_timeout_seconds=0.01,
        )
    except TimeoutError as exc:
        assert "did not reach a terminal status" in str(exc)
    else:
        raise AssertionError("queue demo timeout should raise before writing outputs")

    assert not fixture_output.exists()
    assert not summary_output.exists()
    assert not run_output.exists()


def test_cloud_api_cli_queued_demo_uses_local_runtime_only(tmp_path):
    cases_path = _write_cases(tmp_path)
    fixture_output = tmp_path / "cli_queue_fixture.json"
    summary_output = tmp_path / "cli_queue_summary.json"
    run_output = tmp_path / "cli_queue_run.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.api.cli",
            "run-agent-queued",
            "--agent",
            AGENT_TARGET,
            "--input",
            str(cases_path),
            "--fixture-output",
            str(fixture_output),
            "--summary-output",
            str(summary_output),
            "--run-output",
            str(run_output),
            "--tenant-id",
            "tenant_cli_queue_test",
            "--project-id",
            "project_cli_queue_test",
            "--dataset-id",
            "dataset_cli_queue_test",
            "--runner-id",
            "a1-cli-queue-demo-test",
            "--queue-workers",
            "1",
            "--max-workers",
            "1",
            "--timeout",
            "5",
            "--wait-timeout",
            "10",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Traceback" not in completed.stderr
    summary = json.loads(completed.stdout)
    fixture = json.loads(fixture_output.read_text(encoding="utf-8"))
    run_result = json.loads(run_output.read_text(encoding="utf-8"))
    assert summary["run"]["status"] == "completed"
    assert summary["queue"]["queued_status"] == "queued"
    assert summary["metadata"]["ashr_api_used"] is False
    assert fixture["schema_version"] == "ashr.clone.cloud_api.v1"
    assert fixture["run_result"]["runner_id"] == "a1-cli-queue-demo-test"
    assert run_result["run_id"] == fixture["run_id"]


def test_cloud_api_cli_queued_demo_timeout_returns_nonzero_without_outputs(tmp_path):
    cases_path = _write_cases(tmp_path)
    fixture_output = tmp_path / "cli_queue_timeout_fixture.json"
    summary_output = tmp_path / "cli_queue_timeout_summary.json"
    run_output = tmp_path / "cli_queue_timeout_run.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.api.cli",
            "run-agent-queued",
            "--agent",
            "tests.a1.fixtures_sensitive_agent:SlowAgent",
            "--input",
            str(cases_path),
            "--fixture-output",
            str(fixture_output),
            "--summary-output",
            str(summary_output),
            "--run-output",
            str(run_output),
            "--tenant-id",
            "tenant_cli_queue_timeout_test",
            "--project-id",
            "project_cli_queue_timeout_test",
            "--dataset-id",
            "dataset_cli_queue_timeout_test",
            "--runner-id",
            "a1-cli-queue-timeout-test",
            "--queue-workers",
            "1",
            "--max-workers",
            "1",
            "--timeout",
            "5",
            "--wait-timeout",
            "0.01",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "did not reach a terminal status" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "sk-" not in completed.stderr
    assert "owner@example.com" not in completed.stderr
    assert not fixture_output.exists()
    assert not summary_output.exists()
    assert not run_output.exists()


def test_cloud_api_cli_redacts_operational_errors(tmp_path):
    cases_path = _write_cases(tmp_path)
    fixture_output = tmp_path / "redacted_fixture.json"
    run_output = tmp_path / "redacted_run.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.api.cli",
            "run-agent",
            "--agent",
            "tests.a1.fixtures_sensitive_agent:SensitiveBoomAgent",
            "--input",
            str(cases_path),
            "--fixture-output",
            str(fixture_output),
            "--run-output",
            str(run_output),
            "--timeout",
            "5",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "sk-testtest" not in completed.stdout
    assert "owner@example.com" not in completed.stdout
    assert "sig=secret" not in completed.stdout
    fixture_text = fixture_output.read_text(encoding="utf-8")
    run_text = run_output.read_text(encoding="utf-8")
    for text in (fixture_text, run_text):
        assert "sk-testtest" not in text
        assert "owner@example.com" not in text
        assert "sig=secret" not in text
        assert "[redacted]" in text
