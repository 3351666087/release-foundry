import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

import pytest

from services.api.control_plane import IdempotencyConflictError
from services.api.platform import build_release_evidence_packet

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
    assert boot["metadata"]["local_only"] is True
    assert boot["metadata"]["ashr_api_used"] is False
    assert boot["metadata"]["raw_auth_material_used"] is False

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


def test_sdk_saas_client_exposes_audit_and_release_evidence_verification():
    client = SaaSIngestionClient()
    client.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_verify", project_id="project_verify", dataset_id="dataset_verify")
    client.create_api_key(
        "tenant_verify",
        "project_verify",
        name="verifier",
        scopes=["sdk:submit", "run:upload", "trace:ingest", "audit:read", "evidence:read"],
        key_id="key_verify",
    )
    client.sdk_submit("tenant_verify", "project_verify", dataset_id="dataset_verify", agent_ref="mock", run_id="run_verify", api_key_id="key_verify")
    client.upload_run("tenant_verify", "project_verify", "run_verify", {"status": "completed"}, upload_id="upload_verify", api_key_id="key_verify")
    client.ingest_trace("tenant_verify", "project_verify", "run_verify", [{"observation_id": "obs_verify", "type": "agent_message"}], batch_id="trace_verify", api_key_id="key_verify")

    audit = client.verify_audit_chain("tenant_verify", "project_verify", auth_key_id="key_verify")
    assert audit["operation"] == "verify_audit_chain"
    assert audit["result"]["verification"]["verified"] is True
    assert audit["result"]["event_count"] >= 3

    packet = client.build_release_evidence_packet("tenant_verify", "project_verify", "run_verify", auth_key_id="key_verify")["result"]
    verified = client.verify_release_evidence_packet("tenant_verify", "project_verify", "run_verify", packet=packet, auth_key_id="key_verify")
    assert verified["operation"] == "verify_release_evidence_packet"
    assert verified["result"]["verified"] is True
    assert verified["result"]["bindings"]["usage"]["operation_totals"]["run.upload"] == 1
    assert verified["result"]["usage_event_id"].startswith("usage_")

    tampered = json.loads(json.dumps(packet))
    tampered["project_id"] = "project_other"
    mismatch = client.verify_release_evidence_packet("tenant_verify", "project_verify", "run_verify", packet=tampered, auth_key_id="key_verify")
    assert mismatch["result"]["verified"] is False
    assert {failure["reason"] for failure in mismatch["result"]["failures"]} >= {"packet_sha256_mismatch", "project_id_mismatch"}
    stale = build_release_evidence_packet(
        tenant_id="tenant_verify",
        project_id="project_verify",
        run_id="run_verify",
        lifecycle=client.lifecycle_snapshot("tenant_verify", "project_verify", "run_verify")["result"],
        audit_chain=audit["result"]["verification"],
        packet_id="packet_verify_stale",
    )
    stale_result = client.verify_release_evidence_packet("tenant_verify", "project_verify", "run_verify", packet=stale, auth_key_id="key_verify")
    assert stale_result["result"]["verified"] is False
    assert "usage_operation_totals_mismatch" in {failure["reason"] for failure in stale_result["result"]["failures"]}


def test_sdk_saas_client_sdk_submit_idempotency_conflicts_on_changed_fingerprint():
    client = SaaSIngestionClient()
    client.bootstrap_project(
        tenant_name="Tenant",
        project_name="Project",
        tenant_id="tenant_sdk_idem",
        project_id="project_sdk_idem",
        dataset_id="dataset_sdk_idem",
    )
    client.create_api_key("tenant_sdk_idem", "project_sdk_idem", name="Submitter", scopes=["sdk:submit"], key_id="key_sdk_idem")

    submitted = client.sdk_submit(
        "tenant_sdk_idem",
        "project_sdk_idem",
        dataset_id="dataset_sdk_idem",
        agent_ref="mock",
        run_id="run_sdk_idem",
        api_key_id="key_sdk_idem",
        idempotency_key="idem_sdk_submit",
    )
    replayed = client.sdk_submit(
        "tenant_sdk_idem",
        "project_sdk_idem",
        dataset_id="dataset_sdk_idem",
        agent_ref="mock",
        run_id="run_sdk_idem",
        api_key_id="key_sdk_idem",
        idempotency_key="idem_sdk_submit",
    )
    quota_before = client.quota_snapshot("tenant_sdk_idem", "project_sdk_idem")["result"]["used"]

    assert replayed["result"]["idempotent_replay"] is True
    assert replayed["result"]["run"]["run_id"] == submitted["result"]["run"]["run_id"]
    with pytest.raises(IdempotencyConflictError, match="sdk.submit"):
        client.sdk_submit(
            "tenant_sdk_idem",
            "project_sdk_idem",
            dataset_id="dataset_sdk_idem",
            agent_ref="changed",
            run_id="run_sdk_idem_changed",
            api_key_id="key_sdk_idem",
            idempotency_key="idem_sdk_submit",
        )
    assert client.quota_snapshot("tenant_sdk_idem", "project_sdk_idem")["result"]["used"] == quota_before


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
            env={**os.environ, "PYTHONPATH": os.pathsep.join([str(SDK_ROOT), str(ROOT)])},
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    boot = cli("--state-output", str(state), "bootstrap", "--tenant-name", "Tenant", "--project-name", "Project", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--dataset-id", "dataset_sdk_cli")
    assert boot["operation"] == "bootstrap_project"

    cli("--state-input", str(state), "--state-output", str(state), "api-key-create", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--name", "ingester", "--scope", "sdk:submit", "--scope", "run:upload", "--scope", "trace:ingest", "--scope", "audit:read", "--scope", "evidence:read", "--key-id", "key_sdk_cli")
    cli("--state-input", str(state), "--state-output", str(state), "sdk-submit", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--dataset-id", "dataset_sdk_cli", "--agent-ref", "mock", "--run-id", "run_sdk_cli", "--api-key-id", "key_sdk_cli")
    uploaded = cli("--state-input", str(state), "--state-output", str(state), "run-upload", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--run-id", "run_sdk_cli", "--upload-id", "upload_sdk_cli", "--api-key-id", "key_sdk_cli", "--result-json", '{"status":"completed","api_key":"tp_cli_redact"}')
    assert uploaded["result"]["raw_payload_included"] is False
    trace = cli("--state-input", str(state), "--state-output", str(state), "trace-ingest", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--run-id", "run_sdk_cli", "--batch-id", "trace_sdk_cli", "--api-key-id", "key_sdk_cli", "--observations-json", '[{"observation_id":"obs_cli_sdk","type":"tool_call"}]')
    assert trace["result"]["observation_count"] == 1
    quota = cli("--state-input", str(state), "quota", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli")
    assert quota["result"]["used"]["trace.ingest"] == 1

    audit = cli("--state-input", str(state), "audit-chain-verify", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--auth-key-id", "key_sdk_cli")
    assert audit["operation"] == "verify_audit_chain"
    assert audit["result"]["verification"]["verified"] is True

    packet = cli("--state-input", str(state), "release-evidence", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--run-id", "run_sdk_cli", "--auth-key-id", "key_sdk_cli")["result"]
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    verified = cli("--state-input", str(state), "release-evidence-verify", "--tenant-id", "tenant_sdk_cli", "--project-id", "project_sdk_cli", "--run-id", "run_sdk_cli", "--auth-key-id", "key_sdk_cli", "--packet-file", str(packet_path))
    assert verified["operation"] == "verify_release_evidence_packet"
    assert verified["result"]["verified"] is True
    assert "tp_cli_redact" not in state.read_text(encoding="utf-8")


def test_sdk_saas_cli_rejects_private_input_paths_without_reading(tmp_path: Path):
    private_dir = tmp_path / ".secrets"
    private_dir.mkdir()
    private_state = private_dir / "state.json"
    private_state.write_text("not json and must not be parsed", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "ashr_clone.saas_cli", "--state-input", str(private_state), "state"],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(SDK_ROOT), str(ROOT)])},
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "refusing to read private_refs or .secrets" in proc.stderr
    assert "not json" not in proc.stderr


def test_sdk_saas_cli_rejects_private_release_packet_paths_without_reading(tmp_path: Path):
    private_dir = tmp_path / "docs" / "evidence" / "private_refs"
    private_dir.mkdir(parents=True)
    private_packet = private_dir / "packet.json"
    private_packet.write_text("not json and must not be parsed", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "ashr_clone.saas_cli", "release-evidence-verify", "--tenant-id", "tenant", "--project-id", "project", "--run-id", "run", "--packet-file", str(private_packet)],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(SDK_ROOT), str(ROOT)])},
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert "refusing to read private_refs or .secrets" in proc.stderr
    assert "not json" not in proc.stderr


def test_sdk_saas_client_base_url_uses_http_transport_without_real_keys():
    calls: list[tuple[str, dict]] = []

    def transport(url: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        data = dict(payload)
        calls.append((url, data))
        assert "api_key" not in data
        if url.endswith("/runs/submit"):
            return {"run_id": data["run_id"], "status": "submitted", "echo_metadata": data["metadata"]}
        if url.endswith("/runs/upload"):
            return {
                "upload_id": data["upload_id"],
                "raw_payload_included": False,
                "payload": data["result"],
            }
        if url.endswith("/traces/ingest"):
            observations = data["observations"]
            return {"batch_id": data["batch_id"], "observation_count": len(observations)}
        if url.endswith("/quota"):
            return {"used": {"run.submit": 1}}
        if url.endswith("/audit-chain/verify"):
            return {"verification": {"verified": True}, "event_count": 1}
        if url.endswith("/runs/run_http/release-evidence/verify"):
            return {"verified": True, "packet_id": data["packet"]["packet_id"]}
        if url.endswith("/worker-jobs") and data.get("job_type") == "run.replay":
            return {"job_id": data["job_id"], "raw_payload_included": False, "payload": data["payload"], "status": "queued"}
        if url.endswith("/worker-jobs/lease"):
            return {"status": "leased", "leased": True, "job": {"job_id": "job_http", "attempts": 1, "lease_owner_id": data["lease_owner_id"]}}
        if url.endswith("/worker-jobs/job_http/fail"):
            return {"job_id": "job_http", "status": "retrying", "last_error": {"raw_payload_included": False, "message": data["error"]["message"]}}
        if url.endswith("/worker-jobs") and data.get("status") == "retrying":
            return {"count": 1, "jobs": [{"job_id": "job_http", "status": "retrying"}]}
        raise AssertionError(url)

    client = SaaSIngestionClient.from_base_url("http://127.0.0.1:8765/a1", http_transport=transport)

    submitted = client.sdk_submit(
        "tenant_http",
        "project_http",
        dataset_id="dataset_http",
        agent_ref="mock",
        run_id="run_http",
        metadata={"source": "test"},
        api_key_id="key_http",
        idempotency_key="idem_http",
        request_id="req_http",
    )
    assert submitted["metadata"]["transport"] == "http"
    assert submitted["metadata"]["local_only"] is False
    assert submitted["result"]["echo_metadata"]["client"] == "ashr.clone.saas_ingestion_client.v1"

    uploaded = client.upload_run(
        "tenant_http",
        "project_http",
        "run_http",
        {"status": "completed", "api_key": "tp_should_redact"},
        upload_id="upload_http",
        api_key_id="key_http",
    )
    assert uploaded["result"]["raw_payload_included"] is False
    assert uploaded["result"]["payload"]["api_key"] == "[redacted]"

    trace = client.ingest_trace(
        "tenant_http",
        "project_http",
        "run_http",
        [{"observation_id": "obs_http", "type": "agent_message"}],
        batch_id="trace_http",
        api_key_id="key_http",
    )
    assert trace["result"]["observation_count"] == 1
    assert client.quota_snapshot("tenant_http", "project_http")["result"]["used"]["run.submit"] == 1
    assert client.verify_audit_chain("tenant_http", "project_http", auth_key_id="key_http")["result"]["verification"]["verified"] is True
    assert client.verify_release_evidence_packet("tenant_http", "project_http", "run_http", packet={"packet_id": "packet_http"}, auth_key_id="key_http")["result"]["packet_id"] == "packet_http"
    enqueued = client.enqueue_worker_job(
        "tenant_http",
        "project_http",
        job_type="run.replay",
        target_id="run_http",
        payload={"run_id": "run_http", "api_key": "tp_should_redact"},
        job_id="job_http",
        api_key_id="key_http",
        idempotency_key="idem_job_http",
    )
    assert enqueued["result"]["raw_payload_included"] is False
    assert enqueued["result"]["payload"]["api_key"] == "[redacted]"
    assert client.lease_worker_job("tenant_http", "project_http", lease_owner_id="worker-http", api_key_id="key_http")["result"]["leased"] is True
    assert client.fail_worker_job("tenant_http", "project_http", "job_http", {"message": "retry"}, lease_owner_id="worker-http", retry_after_seconds=0, api_key_id="key_http")["result"]["status"] == "retrying"
    assert client.list_worker_jobs("tenant_http", "project_http", status="retrying", auth_key_id="key_http")["result"]["count"] == 1
    assert [url for url, _payload in calls] == [
        "http://127.0.0.1:8765/a1/runs/submit",
        "http://127.0.0.1:8765/a1/runs/upload",
        "http://127.0.0.1:8765/a1/traces/ingest",
        "http://127.0.0.1:8765/a1/quota",
        "http://127.0.0.1:8765/a1/audit-chain/verify",
        "http://127.0.0.1:8765/a1/runs/run_http/release-evidence/verify",
        "http://127.0.0.1:8765/a1/worker-jobs",
        "http://127.0.0.1:8765/a1/worker-jobs/lease",
        "http://127.0.0.1:8765/a1/worker-jobs/job_http/fail",
        "http://127.0.0.1:8765/a1/worker-jobs",
    ]
    assert calls[0][1]["api_key_id"] == "key_http"


def test_sdk_saas_client_base_url_rejects_raw_api_key_before_transport():
    called = False

    def transport(url: str, payload: Mapping[str, object]) -> Mapping[str, object]:
        nonlocal called
        called = True
        return {}

    client = SaaSIngestionClient.from_base_url("http://localhost:9000", http_transport=transport)
    with pytest.raises(SecretInputError, match="raw API key values are not accepted"):
        client.sdk_submit("tenant", "project", dataset_id="dataset", agent_ref="mock", api_key="tp_not_allowed")
    assert called is False



def test_sdk_saas_cli_base_url_selects_http_client(monkeypatch):
    from ashr_clone import saas_cli

    captured: dict[str, object] = {}

    class FakeHttpClient:
        uses_http = True

        def sdk_submit(self, tenant_id: str, project_id: str, **kwargs: object) -> Mapping[str, object]:
            captured["tenant_id"] = tenant_id
            captured["project_id"] = project_id
            captured["kwargs"] = kwargs
            return {
                "schema_version": "ashr.clone.saas_ingestion_client.v1",
                "operation": "sdk_submit",
                "result": {"run_id": kwargs["run_id"]},
                "metadata": {"local_only": False, "ashr_api_used": False, "raw_auth_material_used": False, "transport": "http"},
            }

    def fake_from_base_url(base_url: str) -> FakeHttpClient:
        captured["base_url"] = base_url
        return FakeHttpClient()

    monkeypatch.setattr(saas_cli.SaaSIngestionClient, "from_base_url", staticmethod(fake_from_base_url))
    args = saas_cli.build_parser().parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8765/a1",
            "sdk-submit",
            "--tenant-id",
            "tenant_cli_http",
            "--project-id",
            "project_cli_http",
            "--dataset-id",
            "dataset_cli_http",
            "--agent-ref",
            "mock",
            "--run-id",
            "run_cli_http",
            "--api-key-id",
            "key_cli_http",
        ]
    )

    envelope = saas_cli.run_command(args)

    assert captured["base_url"] == "http://127.0.0.1:8765/a1"
    assert captured["tenant_id"] == "tenant_cli_http"
    assert captured["project_id"] == "project_cli_http"
    assert captured["kwargs"]["api_key_id"] == "key_cli_http"
    assert envelope["metadata"]["transport"] == "http"


def test_sdk_saas_cli_base_url_rejects_state_files():
    from ashr_clone import saas_cli

    parser = saas_cli.build_parser()
    args = parser.parse_args(["--base-url", "http://localhost:9000", "--state-input", "state.json", "state"])
    with pytest.raises(SecretInputError, match="--base-url cannot be combined with --state-input"):
        saas_cli.run_command(args)
