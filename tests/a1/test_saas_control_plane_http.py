from __future__ import annotations

import json
from io import BytesIO

from services.api.control_plane import (
    CONTROL_PLANE_SCHEMA_VERSION,
    SaaSControlPlaneService,
    create_control_plane_wsgi_app,
    serve_control_plane_http,
)


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
    monkeypatch.setenv("ASHR_API_KEY", "ashr_should_not_leak_http_adapter")
    app = create_control_plane_wsgi_app()

    health_meta, health, health_text = _invoke_wsgi(app, "GET", "/healthz")
    openapi_meta, openapi, openapi_text = _invoke_wsgi(app, "GET", "/openapi.json")

    assert str(health_meta["status"]).startswith("200 ")
    assert health == {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "status": "ok",
        "service": "ashr-saas-control-plane",
        "local_only": True,
        "ashr_api_used": False,
    }
    assert str(openapi_meta["status"]).startswith("200 ")
    assert openapi["openapi"] == "3.0.3"
    assert "/v1/bootstrap" in openapi["paths"]
    assert "/v1/projects/{project_id}/runs/{run_id}/trace-events" in openapi["paths"]
    assert "ashr_should_not_leak_http_adapter" not in health_text + openapi_text
    assert "ASHR_API_KEY" not in health_text + openapi_text


def test_control_plane_wsgi_routes_json_requests_and_redacts_outputs(monkeypatch):
    monkeypatch.setenv("ASHR_API_KEY", "ashr_should_not_leak_router_flow")
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
            "scopes": ["sdk:submit", "runs:write", "trace:ingest"],
            "key_id": "key_http",
        },
    )
    assert key["key_id"] == "key_http"
    assert key["secret_value_present"] is False
    assert key["secret_hash_present"] is True
    assert "secret_hash_sha256" not in key_text
    assert "ashr_local_key_http" not in key_text

    _, listed, listed_text = _invoke_wsgi(app, "GET", "/v1/projects/project_http/api-keys", query="tenant_id=tenant_http")
    assert listed["api_keys"][0]["prefix"] == "ashr_local_***"
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
        },
    )
    assert submitted["submission"]["status"] == "accepted"

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
    assert "ashr_should_not_leak_router_flow" not in key_text + listed_text + uploaded_text + lifecycle_text


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
