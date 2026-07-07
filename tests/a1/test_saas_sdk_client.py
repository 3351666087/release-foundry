import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ashr_clone.saas import SaaSIngestionClient, SecretInputError  # noqa: E402


def test_sdk_saas_client_end_to_end_without_raw_keys(tmp_path: Path):
    client = SaaSIngestionClient()
    boot = client.bootstrap_project(
        tenant_name="Tenant",
        project_name="Project",
        tenant_id="tenant_sdk_client",
        project_id="project_sdk_client",
        dataset_id="dataset_sdk_client",
    )
    assert boot["metadata"] == {"local_only": True, "ashr_api_used": False, "raw_auth_material_used": False}

    key = client.create_api_key(
        "tenant_sdk_client",
        "project_sdk_client",
        name="ingester",
        scopes=["sdk:submit", "run:upload", "trace:ingest"],
        key_id="key_sdk_client",
    )
    assert key["result"]["secret_value_present"] is False
    assert key["result"]["secret_hash_present"] is True

    submitted = client.sdk_submit(
        "tenant_sdk_client",
        "project_sdk_client",
        dataset_id="dataset_sdk_client",
        agent_ref="examples.agents.mock_agent:RespondingMockAgent",
        run_id="run_sdk_client",
        api_key_id="key_sdk_client",
        metadata={"purpose": "unit"},
    )
    assert submitted["result"]["run"]["status"] == "queued"
    assert submitted["result"]["submission"]["status"] == "accepted"

    upload = client.upload_run(
        "tenant_sdk_client",
        "project_sdk_client",
        "run_sdk_client",
        {"run_id": "run_sdk_client", "status": "completed", "api_key": "tp_should_redact"},
        upload_id="upload_sdk_client",
        api_key_id="key_sdk_client",
    )
    assert upload["result"]["raw_payload_included"] is False
    assert upload["result"]["payload_keys"] == ["api_key", "run_id", "status"]

    trace = client.ingest_trace(
        "tenant_sdk_client",
        "project_sdk_client",
        "run_sdk_client",
        [{"observation_id": "obs_sdk_1", "type": "agent_message"}],
        batch_id="trace_sdk_client",
        api_key_id="key_sdk_client",
    )
    assert trace["result"]["observation_ids"] == ["obs_sdk_1"]

    quota = client.quota_snapshot("tenant_sdk_client", "project_sdk_client")
    assert quota["result"]["used"]["run.submit"] == 1
    assert quota["result"]["used"]["run.upload"] == 1
    assert quota["result"]["used"]["trace.ingest"] == 1

    lifecycle = client.lifecycle_snapshot("tenant_sdk_client", "project_sdk_client", "run_sdk_client")
    assert lifecycle["result"]["tenant_status"] == "active"
    assert len(lifecycle["result"]["uploads"]) == 1
    assert len(lifecycle["result"]["trace_batches"]) == 1

    state_path = tmp_path / "state.json"
    client.write_state(state_path)
    state_text = state_path.read_text(encoding="utf-8")
    assert "tp_should_redact" not in state_text
    assert "secret_hash_sha256" in state_text  # local private state stores digest only, never raw secret.
    restored = SaaSIngestionClient.from_state_file(state_path)
    restored_keys = restored.list_api_keys("tenant_sdk_client", "project_sdk_client")
    assert restored_keys["result"]["api_keys"][0]["key_id"] == "key_sdk_client"


def test_sdk_saas_client_rejects_raw_api_key_values():
    client = SaaSIngestionClient()
    client.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_raw", project_id="project_raw")
    with pytest.raises(SecretInputError, match="raw API key values are not accepted"):
        client.sdk_submit(
            "tenant_raw",
            "project_raw",
            dataset_id="dataset_raw",
            agent_ref="mock",
            api_key="tp_not_allowed",
        )


def test_sdk_saas_cli_end_to_end_and_redacts(tmp_path: Path):
    state = tmp_path / "sdk_cli_state.json"

    def cli(*args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "ashr_clone.saas_cli", *args],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(SDK_ROOT) + ";" + str(ROOT)},
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    boot = cli("--state-output", str(state), "bootstrap", "--tenant-name", "Tenant", "--project-name", "Project", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--dataset-id", "dataset_sdk_cli")
    assert boot["operation"] == "bootstrap_project"

    cli("--state-input", str(state), "--state-output", str(state), "api-key-create", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--name", "ingester", "--scope", "sdk:submit", "--scope", "run:upload", "--scope", "trace:ingest", "--key-id", "key_sdk_cli")
    cli("--state-input", str(state), "--state-output", str(state), "sdk-submit", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--dataset-id", "dataset_sdk_cli", "--agent-ref", "mock", "--run-id", "run_sdk_cli", "--api-key-id", "key_sdk_cli")
    uploaded = cli("--state-input", str(state), "--state-output", str(state), "run-upload", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--run-id", "run_sdk_cli", "--upload-id", "upload_sdk_cli", "--api-key-id", "key_sdk_cli", "--result-json", '{"status":"completed","api_key":"tp_cli_redact"}')
    assert uploaded["result"]["raw_payload_included"] is False
    trace = cli("--state-input", str(state), "--state-output", str(state), "trace-ingest", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--run-id", "run_sdk_cli", "--batch-id", "trace_sdk_cli", "--api-key-id", "key_sdk_cli", "--observations-json", '[{"observation_id":"obs_cli_sdk","type":"tool_call"}]')
    assert trace["result"]["observation_count"] == 1
    quota = cli("--state-input", str(state), "quota", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli")
    assert quota["result"]["used"]["trace.ingest"] == 1
    assert "tp_cli_redact" not in state.read_text(encoding="utf-8")


def test_sdk_saas_cli_rejects_private_input_paths_without_reading(tmp_path: Path):
    private_dir = tmp_path / ".secrets"
    private_dir.mkdir()
    private_state = private_dir / "state.json"
    private_state.write_text("not json and must not be parsed", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "ashr_clone.saas_cli", "--state-input", str(private_state), "state"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(SDK_ROOT) + ";" + str(ROOT)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "refusing to read private_refs or .secrets" in proc.stderr
    assert "not json" not in proc.stderr
