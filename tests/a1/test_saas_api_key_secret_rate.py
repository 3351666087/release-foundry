from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from services.api.control_plane import CONTROL_PLANE_SCHEMA_VERSION, SaaSControlPlaneService
from services.api.runtime import ValidationError

ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from ashr_clone.saas import SaaSIngestionClient  # noqa: E402


def _service_with_dataset():
    control = SaaSControlPlaneService()
    control.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_secret", project_id="project_secret")
    control.cloud.create_dataset("tenant_secret", "project_secret", name="Dataset", dataset_id="dataset_secret", cases=[{"id": "case-1"}])
    return control


def test_api_key_one_time_secret_verify_and_public_redaction():
    control = _service_with_dataset()
    created = control.create_api_key(
        "tenant_secret",
        "project_secret",
        name="CI writer",
        scopes=["sdk:submit", "run:upload"],
        key_id="key_secret",
        reveal_secret=True,
    )
    secret = created["one_time_secret"]
    assert secret.startswith("ashr_local_key_secret_")
    assert created["secret_value_present"] is True
    assert created["one_time_secret_displayed"] is True
    assert "secret_hash_sha256" not in created

    listed = control.list_api_keys("tenant_secret", "project_secret")
    listed_text = json.dumps(listed, sort_keys=True)
    assert listed[0]["secret_value_present"] is False
    assert listed[0]["secret_hash_present"] is True
    assert secret not in listed_text
    assert "secret_hash_sha256" not in listed_text

    verified = control.verify_api_key_secret("tenant_secret", "project_secret", key_id="key_secret", secret=secret, scope="sdk:submit")
    assert verified["authenticated"] is True
    assert verified["api_key"]["key_id"] == "key_secret"
    assert verified["secret_value_present"] is False

    with pytest.raises(ValidationError, match="secret verification failed"):
        control.verify_api_key_secret("tenant_secret", "project_secret", key_id="key_secret", secret="wrong")


def test_api_key_rate_limit_blocks_before_mutation_and_records_snapshot():
    control = _service_with_dataset()
    created = control.create_api_key(
        "tenant_secret",
        "project_secret",
        name="Limited submitter",
        scopes=["sdk:submit"],
        key_id="key_limited",
        reveal_secret=True,
    )
    assert created["one_time_secret"]
    configured = control.configure_api_key_rate_limit(
        "tenant_secret",
        "project_secret",
        key_id="key_limited",
        operation="sdk:submit",
        limit=1,
    )
    assert configured["limit"] == 1
    assert configured["remaining"] == 1

    first = control.sdk_submit_run(
        "tenant_secret",
        "project_secret",
        dataset_id="dataset_secret",
        agent_ref="mock",
        run_id="run_rate_1",
        api_key_id="key_limited",
    )
    assert first["run"]["run_id"] == "run_rate_1"

    with pytest.raises(ValidationError, match="rate limit exceeded"):
        control.sdk_submit_run(
            "tenant_secret",
            "project_secret",
            dataset_id="dataset_secret",
            agent_ref="mock",
            run_id="run_rate_2",
            api_key_id="key_limited",
        )
    with pytest.raises(Exception):
        control.cloud.get_run("tenant_secret", "project_secret", "run_rate_2")

    snapshot = control.api_key_rate_limit_snapshot("tenant_secret", "project_secret", key_id="key_limited")
    assert snapshot["schema_version"] == CONTROL_PLANE_SCHEMA_VERSION
    assert snapshot["rate_limits"][0]["used"] == 1
    assert snapshot["rate_limits"][0]["remaining"] == 0


def test_sdk_client_exposes_api_key_secret_and_rate_limit_controls():
    control = _service_with_dataset()
    client = SaaSIngestionClient(service=control)

    created = client.create_api_key(
        "tenant_secret",
        "project_secret",
        name="SDK limited writer",
        scopes=["sdk:submit"],
        key_id="key_sdk_limited",
        reveal_secret=True,
    )
    secret = created["result"]["one_time_secret"]
    assert created["result"]["one_time_secret_displayed"] is True

    verified = client.verify_api_key_secret("tenant_secret", "project_secret", "key_sdk_limited", secret=secret, scope="sdk:submit")
    assert verified["result"]["authenticated"] is True
    assert verified["result"]["secret_value_present"] is False

    configured = client.configure_api_key_rate_limit(
        "tenant_secret",
        "project_secret",
        "key_sdk_limited",
        operation="sdk:submit",
        limit=1,
    )
    assert configured["result"]["remaining"] == 1

    submitted = client.sdk_submit(
        "tenant_secret",
        "project_secret",
        dataset_id="dataset_secret",
        agent_ref="mock",
        run_id="run_sdk_rate",
        api_key_id="key_sdk_limited",
    )
    assert submitted["result"]["run"]["run_id"] == "run_sdk_rate"

    snapshot = client.api_key_rate_limit_snapshot("tenant_secret", "project_secret", key_id="key_sdk_limited")
    assert snapshot["result"]["rate_limits"][0]["used"] == 1


def test_saas_cli_api_key_secret_and_rate_limit_round_trip(tmp_path: Path):
    state = tmp_path / "state.json"

    def cli(*args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, "-B", "-m", "ashr_clone.saas_cli", *args],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": os.pathsep.join([str(SDK_ROOT), str(ROOT)])},
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    cli(
        "--state-output",
        str(state),
        "bootstrap",
        "--tenant-name",
        "Tenant",
        "--project-name",
        "Project",
        "--tenant-id",
        "tenant_cli_secret",
        "--project-id",
        "project_cli_secret",
        "--dataset-id",
        "dataset_cli_secret",
    )
    created = cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "api-key-create",
        "--tenant-id",
        "tenant_cli_secret",
        "--project-id",
        "project_cli_secret",
        "--name",
        "CI writer",
        "--scope",
        "sdk:submit",
        "--key-id",
        "key_cli_secret",
        "--reveal-secret",
    )
    secret = created["result"]["one_time_secret"]
    assert secret.startswith("ashr_local_key_cli_secret_")

    verified = cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "api-key-verify",
        "--tenant-id",
        "tenant_cli_secret",
        "--project-id",
        "project_cli_secret",
        "--key-id",
        "key_cli_secret",
        "--secret",
        secret,
        "--scope",
        "sdk:submit",
    )
    assert verified["result"]["authenticated"] is True

    cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "api-key-rate-limit",
        "--tenant-id",
        "tenant_cli_secret",
        "--project-id",
        "project_cli_secret",
        "--key-id",
        "key_cli_secret",
        "--operation",
        "sdk:submit",
        "--limit",
        "1",
    )
    cli(
        "--state-input",
        str(state),
        "--state-output",
        str(state),
        "sdk-submit",
        "--tenant-id",
        "tenant_cli_secret",
        "--project-id",
        "project_cli_secret",
        "--dataset-id",
        "dataset_cli_secret",
        "--agent-ref",
        "mock",
        "--run-id",
        "run_cli_limited",
        "--api-key-id",
        "key_cli_secret",
    )
    snapshot = cli("--state-input", str(state), "api-key-rate-limits", "--tenant-id", "tenant_cli_secret", "--project-id", "project_cli_secret", "--key-id", "key_cli_secret")
    assert snapshot["result"]["rate_limits"][0]["remaining"] == 0
    env_key = os.environ.get("ASHR_API_KEY")
    if env_key:
        assert env_key not in state.read_text(encoding="utf-8")
