from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from services.api.control_plane import CONTROL_PLANE_SCHEMA_VERSION
from services.api.control_plane_cli import invoke_json, run_command, build_parser
from services.api.runtime import ValidationError


def _cli(*args: str) -> dict:
    return invoke_json(list(args))


def test_control_plane_cli_bootstrap_submit_upload_trace_snapshot_and_state_roundtrip(tmp_path: Path):
    state = tmp_path / "control_plane_state.json"

    boot = _cli(
        "--state-output",
        str(state),
        "bootstrap",
        "--tenant-name",
        "CLI Tenant",
        "--project-name",
        "CLI Project",
        "--tenant-id",
        "tenant_cli",
        "--project-id",
        "project_cli",
        "--dataset-id",
        "dataset_cli",
        "--dataset-name",
        "CLI Dataset",
    )
    assert boot["schema_version"] == CONTROL_PLANE_SCHEMA_VERSION
    assert boot["metadata"] == {"local_only": True, "ashr_api_used": False}
    assert boot["result"]["tenant"]["tenant_id"] == "tenant_cli"
    assert boot["result"]["dataset"]["dataset_id"] == "dataset_cli"
    assert state.exists()

    submitted = _cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "sdk-submit",
        "--tenant-id",
        "tenant_cli",
        "--project-id",
        "project_cli",
        "--dataset-id",
        "dataset_cli",
        "--agent-ref",
        "examples.agents.mock_agent:RespondingMockAgent",
        "--run-id",
        "run_cli",
        "--metadata-json",
        '{"suite":"round16"}',
    )
    assert submitted["result"]["submission"]["status"] == "accepted"
    assert submitted["result"]["run"]["status"] == "queued"
    assert submitted["result"]["run"]["metadata"]["suite"] == "round16"

    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps({"run_id": "run_cli", "status": "completed", "cases": []}), encoding="utf-8")
    uploaded = _cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "run-upload",
        "--tenant-id",
        "tenant_cli",
        "--project-id",
        "project_cli",
        "--run-id",
        "run_cli",
        "--upload-id",
        "upload_cli",
        "--result-file",
        str(result_file),
    )
    uploaded_text = json.dumps(uploaded, sort_keys=True)
    assert uploaded["result"]["payload_keys"] == ["cases", "run_id", "status"]
    assert uploaded["result"]["raw_payload_included"] is False
    assert "completed" not in uploaded_text

    trace = _cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "trace-ingest",
        "--tenant-id",
        "tenant_cli",
        "--project-id",
        "project_cli",
        "--run-id",
        "run_cli",
        "--batch-id",
        "trace_cli",
        "--observations-json",
        '[{"observation_id":"obs_cli_1","type":"agent_message"},{"observation_id":"obs_cli_2","type":"tool_call"}]',
    )
    assert trace["result"]["observation_count"] == 2
    assert trace["result"]["observation_ids"] == ["obs_cli_1", "obs_cli_2"]

    snapshot = _cli(
        "--state-input",
        str(state),
        "lifecycle-snapshot",
        "--tenant-id",
        "tenant_cli",
        "--project-id",
        "project_cli",
        "--run-id",
        "run_cli",
    )
    assert snapshot["result"]["tenant_status"] == "active"
    assert len(snapshot["result"]["uploads"]) == 1
    assert len(snapshot["result"]["trace_batches"]) == 1
    assert snapshot["result"]["quota"]["used"]["run.submit"] == 1
    assert snapshot["result"]["quota"]["used"]["run.upload"] == 1
    assert snapshot["result"]["quota"]["used"]["trace.ingest"] == 2

    summary = _cli("--state-input", str(state), "state-read")
    assert summary["result"]["cloud_counts"]["runs"] == 1
    assert summary["result"]["control_plane_counts"]["uploads"] == 1
    assert summary["result"]["metadata"] == {"local_only": True, "ashr_api_used": False}

    full_state = json.loads(state.read_text(encoding="utf-8"))
    assert full_state["metadata"] == {"local_only": True, "ashr_api_used": False}
    assert full_state["control_plane"]["uploads"]["upload_cli"]["raw_payload_included"] is False


def test_control_plane_cli_api_key_outputs_are_redacted_and_persisted(tmp_path: Path):
    state = tmp_path / "state.json"
    _cli(
        "--state-output",
        str(state),
        "bootstrap",
        "--tenant-name",
        "Tenant",
        "--project-name",
        "Project",
        "--tenant-id",
        "tenant_key_cli",
        "--project-id",
        "project_key_cli",
    )

    created = _cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "api-key-create",
        "--tenant-id",
        "tenant_key_cli",
        "--project-id",
        "project_key_cli",
        "--name",
        "CI key",
        "--scope",
        "runs:write",
        "--scope",
        "traces:write",
        "--key-id",
        "key_cli",
    )
    listed = _cli(
        "--state-input",
        str(state),
        "api-key-list",
        "--tenant-id",
        "tenant_key_cli",
        "--project-id",
        "project_key_cli",
    )
    revoked = _cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "api-key-revoke",
        "--tenant-id",
        "tenant_key_cli",
        "--project-id",
        "project_key_cli",
        "--key-id",
        "key_cli",
    )

    combined = json.dumps({"created": created, "listed": listed, "revoked": revoked}, sort_keys=True)
    assert created["result"]["secret_value_present"] is False
    assert created["result"]["secret_hash_present"] is True
    assert listed["result"]["api_keys"][0]["prefix"] == "ashr_local_***"
    assert revoked["result"]["status"] == "revoked"
    assert "secret_hash_sha256" not in combined
    assert "ashr_local_key_cli" not in combined


def test_control_plane_cli_rejects_private_input_paths_without_reading(tmp_path: Path):
    private_dir = tmp_path / "docs" / "evidence" / "private_refs"
    private_dir.mkdir(parents=True)
    private_file = private_dir / "state.json"
    private_file.write_text("not json and must not be parsed", encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(["--state-input", str(private_file), "state-read"])
    with pytest.raises(ValidationError, match="private_refs"):
        run_command(args)


def test_control_plane_cli_module_entrypoint_prints_json(tmp_path: Path):
    state = tmp_path / "entry_state.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "services.api.control_plane_cli",
            "--state-output",
            str(state),
            "bootstrap",
            "--tenant-name",
            "Entrypoint Tenant",
            "--project-name",
            "Entrypoint Project",
            "--tenant-id",
            "tenant_entry",
            "--project-id",
            "project_entry",
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["command"] == "bootstrap"
    assert payload["metadata"]["ashr_api_used"] is False
    assert state.exists()
