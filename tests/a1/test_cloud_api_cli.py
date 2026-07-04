import json
import subprocess
import sys
from pathlib import Path

from services.api.demo import run_agent_cloud_demo


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
