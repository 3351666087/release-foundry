from __future__ import annotations

import json
from io import BytesIO

from services.api.control_plane import (
    CONTROL_PLANE_SCHEMA_VERSION,
    SaaSControlPlaneService,
    create_control_plane_wsgi_app,
    serve_control_plane_http,
)
from services.api.platform import build_release_evidence_packet


def _invoke_wsgi(app, method: str, path: str, body: dict | None = None, query: str = ""):
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": str(len(raw)),
        "CONTENT_TYPE": "application/json" if raw else "",
        "wsgi.input": BytesIO(raw),
    }
    response_bytes = b"".join(app(environ, start_response))
    return captured, json.loads(response_bytes.decode("utf-8")), response_bytes.decode("utf-8")


def test_control_plane_wsgi_serves_healthz_and_openapi_without_secret_env(monkeypatch):
    monkeypatch.setenv("RELEASEFOUNDRY_API_KEY", "redacted-http-adapter-marker")
    app = create_control_plane_wsgi_app()

    health_meta, health, health_text = _invoke_wsgi(app, "GET", "/healthz")
    openapi_meta, openapi, openapi_text = _invoke_wsgi(app, "GET", "/openapi.json")

    assert str(health_meta["status"]).startswith("200 ")
    assert health == {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "status": "ok",
        "service": "releasefoundry-saas-control-plane",
        "local_only": True,
        "releasefoundry_api_used": False,
    }
    assert str(openapi_meta["status"]).startswith("200 ")
    assert openapi["openapi"] == "3.0.3"
    assert "/v1/bootstrap" in openapi["paths"]
    assert "/v1/projects/{project_id}/runs/{run_id}/trace-events" in openapi["paths"]
    assert "/v1/projects/{project_id}/audit-chain/verify" in openapi["paths"]
    assert "post" in openapi["paths"]["/v1/projects/{project_id}/audit-chain/verify"]
    assert "/v1/projects/{project_id}/runs/{run_id}/release-evidence" in openapi["paths"]
    assert "/v1/projects/{project_id}/runs/{run_id}/release-evidence/verify" in openapi["paths"]
    assert "/v1/projects/{project_id}/worker-jobs" in openapi["paths"]
    assert "get" in openapi["paths"]["/v1/projects/{project_id}/worker-jobs"]
    assert "/v1/projects/{project_id}/worker-jobs/enqueue" in openapi["paths"]
    assert "post" in openapi["paths"]["/v1/projects/{project_id}/worker-jobs/enqueue"]
    assert "/v1/projects/{project_id}/worker-jobs/lease" in openapi["paths"]
    assert "/v1/projects/{project_id}/worker-jobs/{job_id}/complete" in openapi["paths"]
    assert "/v1/projects/{project_id}/worker-jobs/{job_id}/fail" in openapi["paths"]
    assert "redacted-http-adapter-marker" not in health_text + openapi_text
    assert "RELEASEFOUNDRY_API_KEY" not in health_text + openapi_text


def test_control_plane_wsgi_routes_json_requests_and_redacts_outputs(monkeypatch):
    monkeypatch.setenv("RELEASEFOUNDRY_API_KEY", "redacted-router-flow-marker")
    service = SaaSControlPlaneService()
    app = create_control_plane_wsgi_app(service=service)

    _, boot, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/bootstrap",
        {
            "tenant_name": "Hosted Tenant",
            "project_name": "Self Host Project",
            "tenant_id": "tenant_http",
            "project_id": "project_http",
        },
    )
    assert boot["tenant"]["tenant_id"] == "tenant_http"
    service.cloud.create_dataset(
        "tenant_http",
        "project_http",
        name="HTTP dataset",
        dataset_id="dataset_http",
        cases=[{"id": "case_http", "prompt": "hello", "expected": {"text": "hello"}}],
    )

    _, key, key_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_http/api-keys",
        {
            "tenant_id": "tenant_http",
            "name": "HTTP key",
            "scopes": ["sdk:submit", "runs:write", "trace:ingest", "audit:read", "evidence:read"],
            "key_id": "key_http",
        },
    )
    assert key["key_id"] == "key_http"
    assert key["secret_value_present"] is False
    assert key["secret_hash_present"] is True
    assert "secret_hash_sha256" not in key_text
    assert "releasefoundry_local_key_http" not in key_text

    _, listed, listed_text = _invoke_wsgi(app, "GET", "/v1/projects/project_http/api-keys", query="tenant_id=tenant_http")
    assert listed["api_keys"][0]["prefix"] == "releasefoundry_local_***"
    assert "secret_hash_sha256" not in listed_text

    _, submitted, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_http/sdk-submit",
        {
            "tenant_id": "tenant_http",
            "api_key_id": "key_http",
            "dataset_id": "dataset_http",
            "agent_ref": "mock",
            "run_id": "run_http",
            "idempotency_key": "idem_http_submit",
        },
    )
    assert submitted["submission"]["status"] == "accepted"

    replay_meta, replayed, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_http/sdk-submit",
        {
            "tenant_id": "tenant_http",
            "api_key_id": "key_http",
            "dataset_id": "dataset_http",
            "agent_ref": "mock",
            "run_id": "run_http",
            "idempotency_key": "idem_http_submit",
        },
    )
    assert str(replay_meta["status"]).startswith("202 ")
    assert replayed["submission"]["status"] == "accepted"
    assert replayed["idempotent_replay"] is True

    conflict_meta, conflict, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_http/sdk-submit",
        {
            "tenant_id": "tenant_http",
            "api_key_id": "key_http",
            "dataset_id": "dataset_http",
            "agent_ref": "changed",
            "run_id": "run_http_changed",
            "idempotency_key": "idem_http_submit",
        },
    )
    assert str(conflict_meta["status"]).startswith("409 ")
    assert conflict["error"]["code"] == "idempotency_conflict"
    assert "run_http_changed" not in service.cloud.store.runs

    _, uploaded, uploaded_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_http/runs/run_http/upload",
        {
            "tenant_id": "tenant_http",
            "api_key_id": "key_http",
            "upload_id": "upload_http",
            "result": {"run_id": "run_http", "status": "completed", "cases": []},
        },
    )
    assert uploaded["payload_keys"] == ["cases", "run_id", "status"]
    assert "completed" not in uploaded_text

    _, trace, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_http/runs/run_http/trace-events",
        {
            "tenant_id": "tenant_http",
            "api_key_id": "key_http",
            "batch_id": "trace_http",
            "observations": [{"observation_id": "obs_http", "type": "agent_message"}],
        },
    )
    assert trace["observation_ids"] == ["obs_http"]

    _, lifecycle, lifecycle_text = _invoke_wsgi(app, "GET", "/v1/projects/project_http/runs/run_http/lifecycle", query="tenant_id=tenant_http")
    assert lifecycle["quota"]["used"]["sdk.submit"] == 1
    assert lifecycle["quota"]["used"]["run.upload"] == 1
    assert lifecycle["quota"]["used"]["trace.ingest"] == 1

    _, audit, audit_text = _invoke_wsgi(app, "POST", "/v1/projects/project_http/audit-chain/verify", {"tenant_id": "tenant_http", "api_key_id": "key_http"})
    assert audit["verification"]["verified"] is True
    assert audit["event_count"] >= 3

    _, built_packet, built_packet_text = _invoke_wsgi(app, "GET", "/v1/projects/project_http/runs/run_http/release-evidence", query="tenant_id=tenant_http&api_key_id=key_http")
    assert built_packet["run_id"] == "run_http"
    assert built_packet["integrity"]["packet_sha256"]

    _, packet_verification, packet_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_http/runs/run_http/release-evidence/verify",
        {"tenant_id": "tenant_http", "api_key_id": "key_http", "packet": built_packet},
    )
    assert packet_verification["verified"] is True
    assert packet_verification["bindings"]["usage"]["operation_totals"]["trace.ingest"] == 1
    assert packet_verification["source"] == "submitted_packet"
    stale_packet = build_release_evidence_packet(
        tenant_id="tenant_http",
        project_id="project_http",
        run_id="run_http",
        lifecycle=lifecycle,
        audit_chain=audit["verification"],
        packet_id="packet_http_stale",
    )
    _, stale_verification, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_http/runs/run_http/release-evidence/verify",
        {"tenant_id": "tenant_http", "api_key_id": "key_http", "packet": stale_packet},
    )
    assert stale_verification["verified"] is False
    assert "usage_operation_totals_mismatch" in {failure["reason"] for failure in stale_verification["failures"]}
    assert "secret_hash_sha256" not in audit_text + built_packet_text + packet_text
    assert "redacted-router-flow-marker" not in key_text + listed_text + uploaded_text + lifecycle_text + audit_text + built_packet_text + packet_text


def test_control_plane_wsgi_worker_job_routes_are_auth_scoped_and_public_safe(monkeypatch):
    monkeypatch.setenv("RELEASEFOUNDRY_API_KEY", "redacted-worker-http-marker")
    service = SaaSControlPlaneService()
    app = create_control_plane_wsgi_app(service=service)

    _invoke_wsgi(
        app,
        "POST",
        "/v1/bootstrap",
        {
            "tenant_name": "Worker Tenant",
            "project_name": "Worker Project",
            "tenant_id": "tenant_worker_http",
            "project_id": "project_worker_http",
        },
    )
    _, key, key_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/api-keys",
        {
            "tenant_id": "tenant_worker_http",
            "name": "Worker key",
            "scopes": ["worker:read", "worker:write", "audit:read"],
            "key_id": "key_worker_http",
        },
    )
    assert key["secret_value_present"] is False

    unauth_meta, unauth, unauth_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/worker-jobs/enqueue",
        {"tenant_id": "tenant_worker_http", "api_key_id": "missing", "job_type": "run.replay"},
    )
    assert str(unauth_meta["status"]).startswith("404 ")
    assert unauth["schema_version"] == CONTROL_PLANE_SCHEMA_VERSION
    assert unauth["error"]["code"] == "not_found"

    _, enqueued, enqueued_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/worker-jobs/enqueue",
        {
            "tenant_id": "tenant_worker_http",
            "api_key_id": "key_worker_http",
            "job_type": "run.replay",
            "target_id": "run_worker_http",
            "payload": {"run_id": "run_worker_http", "secret": "must-not-leak"},
            "job_id": "job_worker_http",
            "priority": 7,
            "max_attempts": 2,
            "idempotency_key": "idem_worker_http",
        },
    )
    assert enqueued["job_id"] == "job_worker_http"
    assert enqueued["raw_payload_included"] is False

    replay_meta, replay, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/worker-jobs/enqueue",
        {
            "tenant_id": "tenant_worker_http",
            "api_key_id": "key_worker_http",
            "job_type": "run.replay",
            "target_id": "run_worker_http",
            "payload": {"run_id": "run_worker_http", "secret": "must-not-leak"},
            "job_id": "job_worker_http",
            "priority": 7,
            "max_attempts": 2,
            "idempotency_key": "idem_worker_http",
        },
    )
    assert str(replay_meta["status"]).startswith("202 ")
    assert replay["idempotent_replay"] is True

    _, leased, leased_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/worker-jobs/lease",
        {
            "tenant_id": "tenant_worker_http",
            "api_key_id": "key_worker_http",
            "lease_owner_id": "worker-http-a",
            "lease_seconds": 30,
            "job_type": "run.replay",
        },
    )
    assert leased["leased"] is True
    assert leased["job"]["attempts"] == 1

    _, failed, failed_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/worker-jobs/job_worker_http/fail",
        {
            "tenant_id": "tenant_worker_http",
            "api_key_id": "key_worker_http",
            "lease_owner_id": "worker-http-a",
            "retry_after_seconds": 0,
            "error": {"type": "TransientError", "message": "retryable", "secret": "must-not-leak"},
        },
    )
    assert failed["status"] == "retrying"
    assert failed["last_error"]["raw_payload_included"] is False

    _, leased_again, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/worker-jobs/lease",
        {"tenant_id": "tenant_worker_http", "api_key_id": "key_worker_http", "lease_owner_id": "worker-http-b", "lease_seconds": 30},
    )
    assert leased_again["job"]["attempts"] == 2

    _, completed, completed_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/worker-jobs/job_worker_http/complete",
        {
            "tenant_id": "tenant_worker_http",
            "api_key_id": "key_worker_http",
            "lease_owner_id": "worker-http-b",
            "result": {"ok": True, "secret": "must-not-leak"},
        },
    )
    assert completed["status"] == "completed"
    assert completed["result_sha256"]

    _, listed, listed_text = _invoke_wsgi(
        app,
        "GET",
        "/v1/projects/project_worker_http/worker-jobs",
        query="tenant_id=tenant_worker_http&api_key_id=key_worker_http&status=completed&limit=1",
    )
    assert listed["count"] == 1
    assert listed["jobs"][0]["job_id"] == "job_worker_http"

    _, audit, audit_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_worker_http/audit-chain/verify",
        {"tenant_id": "tenant_worker_http", "api_key_id": "key_worker_http"},
    )
    assert audit["verification"]["verified"] is True
    _, audit_log, audit_log_text = _invoke_wsgi(
        app,
        "GET",
        "/v1/projects/project_worker_http/audit-log",
        query="tenant_id=tenant_worker_http&api_key_id=key_worker_http",
    )
    assert {event["action"] for event in audit_log["events"]} >= {"worker.job.enqueue", "worker.job.lease", "worker.job.fail", "worker.job.complete"}
    combined_text = key_text + unauth_text + enqueued_text + leased_text + failed_text + completed_text + listed_text + audit_text + audit_log_text
    assert "secret_hash_sha256" not in combined_text
    assert "must-not-leak" not in combined_text
    assert "redacted-worker-http-marker" not in combined_text


def test_control_plane_wsgi_rejects_invalid_json_with_public_error():
    app = create_control_plane_wsgi_app()
    captured: dict[str, object] = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/v1/bootstrap",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "1",
        "CONTENT_TYPE": "application/json",
        "wsgi.input": BytesIO(b"{"),
    }
    payload = json.loads(b"".join(app(environ, start_response)).decode("utf-8"))

    assert str(captured["status"]).startswith("400 ")
    assert payload["schema_version"] == CONTROL_PLANE_SCHEMA_VERSION
    assert payload["error"] == {"code": "validation_error", "message": "request body must be valid UTF-8 JSON"}


def test_control_plane_http_server_factory_uses_stdlib_wsgi_server():
    server = serve_control_plane_http("127.0.0.1", 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[1] > 0
        assert callable(server.get_app())
    finally:
        server.server_close()
