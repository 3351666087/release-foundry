from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

from packages.sdk.ashr_clone.saas import SaaSIngestionClient

ROOT = Path(__file__).resolve().parents[2]
GO_MODULE = ROOT / "packages" / "go" / "ashrclone"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str, timeout: float = 15.0) -> None:
    import urllib.request

    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/health", timeout=1) as resp:  # nosec - local test server only.
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - startup polling preserves last failure.
            last_error = exc
        time.sleep(0.1)
    raise AssertionError(f"Go API did not become healthy: {last_error}")


@pytest.mark.skipif(os.environ.get("A1_SKIP_GO_SERVER_SMOKE") == "1", reason="Go server smoke explicitly skipped")
def test_python_sdk_calls_go_http_server_vertical_slice():
    port = _free_port()
    env = dict(os.environ)
    env["ASHR_GO_API_ADDR"] = f"127.0.0.1:{port}"
    proc = subprocess.Popen(
        ["go", "run", "./cmd/ashr-api"],
        cwd=GO_MODULE,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(base_url)
        client = SaaSIngestionClient.from_base_url(base_url)
        boot = client.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_go_py", project_id="project_go_py", dataset_id="dataset_go_py")
        assert boot["operation"] == "bootstrap_project"
        assert boot["result"]["dataset"]["dataset_id"] == "dataset_go_py"

        run = client.sdk_submit("tenant_go_py", "project_go_py", dataset_id="dataset_go_py", agent_ref="agent:py", run_id="run_go_py", idempotency_key="idem_go_py")
        assert run["operation"] == "sdk_submit"
        assert run["result"]["run_id"] == "run_go_py"

        job = client.enqueue_worker_job("tenant_go_py", "project_go_py", job_type="release_gate", target_id="run_go_py", payload={"run_id": "run_go_py"}, job_id="job_go_py", idempotency_key="idem_job_go_py")
        assert job["result"]["raw_payload_included"] is False
        lease = client.lease_worker_job("tenant_go_py", "project_go_py", lease_owner_id="worker_py", job_type="release_gate")
        assert lease["result"]["leased"] is True
        complete = client.complete_worker_job("tenant_go_py", "project_go_py", "job_go_py", {"status": "ok"}, lease_owner_id="worker_py")
        assert complete["result"]["status"] == "completed"
        listed = client.list_worker_jobs("tenant_go_py", "project_go_py", status="completed")
        assert listed["result"]["count"] == 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.returncode not in (0, -15, 1):
            stderr = proc.stderr.read() if proc.stderr else ""
            stdout = proc.stdout.read() if proc.stdout else ""
            raise AssertionError(f"unexpected Go API exit {proc.returncode}\nstdout={stdout}\nstderr={stderr}")
