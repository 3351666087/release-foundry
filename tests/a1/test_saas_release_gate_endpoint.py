from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Mapping

from services.api.control_plane import CONTROL_PLANE_SCHEMA_VERSION, SaaSControlPlaneService, create_control_plane_wsgi_app


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
    response_text = b"".join(app(environ, start_response)).decode("utf-8")
    return captured, json.loads(response_text), response_text


def _prepared_service(*, release_gate_evaluator=None) -> SaaSControlPlaneService:
    service = SaaSControlPlaneService(release_gate_evaluator=release_gate_evaluator)
    service.bootstrap_project(tenant_name="Gate Tenant", project_name="Gate Project", tenant_id="tenant_gate", project_id="project_gate")
    service.cloud.create_dataset(
        "tenant_gate",
        "project_gate",
        name="Gate dataset",
        dataset_id="dataset_gate",
        cases=[{"id": "case_gate", "prompt": "hello", "expected": {"text": "hello"}}],
    )
    service.create_api_key(
        "tenant_gate",
        "project_gate",
        name="Gate key",
        scopes=["sdk:submit", "run:upload", "trace:ingest", "release_gate:evaluate", "audit:read"],
        key_id="key_gate",
    )
    service.sdk_submit_run("tenant_gate", "project_gate", dataset_id="dataset_gate", agent_ref="mock", run_id="run_gate", api_key_id="key_gate")
    service.upload_run_result("tenant_gate", "project_gate", "run_gate", {"status": "completed", "cases": []}, upload_id="upload_gate", api_key_id="key_gate")
    service.ingest_trace("tenant_gate", "project_gate", "run_gate", [{"observation_id": "obs_gate", "type": "agent_message"}], batch_id="trace_gate", api_key_id="key_gate")
    return service


def test_release_gate_endpoint_uses_deterministic_local_stub_and_audits_result(monkeypatch):
    monkeypatch.setenv("ASHR_API_KEY", "ashr_should_not_leak_release_gate")
    service = _prepared_service()
    app = create_control_plane_wsgi_app(service=service)

    meta, gate, gate_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_gate/runs/run_gate/release-gate",
        {
            "tenant_id": "tenant_gate",
            "api_key_id": "key_gate",
            "request_id": "req_gate",
            "idempotency_key": "idem_gate",
            "policy": {"minimum_uploads": 1, "minimum_trace_batches": 1},
        },
    )

    assert str(meta["status"]).startswith("200 ")
    assert gate["schema_version"] == CONTROL_PLANE_SCHEMA_VERSION
    assert gate["local_only"] is True
    assert gate["ashr_api_used"] is False
    assert gate["target_contract"] == "A2.release_gate.evaluate"
    assert gate["transport"] == "local_callable"
    assert gate["grade_result"]["passed"] is True
    assert gate["grade_result"]["actual"] == {"run_status": "queued", "upload_count": 1, "trace_batch_count": 1}
    assert "ashr_should_not_leak_release_gate" not in gate_text

    _, audit, _ = _invoke_wsgi(
        app,
        "GET",
        "/v1/projects/project_gate/audit-log",
        query="tenant_id=tenant_gate&api_key_id=key_gate&action=release_gate.evaluate&target_id=run_gate",
    )
    assert [event["action"] for event in audit["events"]] == ["release_gate.evaluate"]
    assert audit["events"][0]["request_id"] == "req_gate"
    assert audit["events"][0]["idempotency_key"] == "idem_gate"
    assert audit["events"][0]["audit_event_sha256"]
    assert audit["chain"]["verified"] is True
    assert audit["chain"]["tail_audit_event_sha256"] == audit["events"][0]["audit_event_sha256"]


def test_release_gate_endpoint_can_use_registered_local_evaluator():
    seen_payloads: list[Mapping[str, Any]] = []

    def evaluator(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        seen_payloads.append(payload)
        return {
            "scenario_id": payload["run_id"],
            "passed": False,
            "score": 0.25,
            "label": "registered_hold",
            "reason": "registered evaluator forced a local hold",
            "expected": payload["policy"],
            "actual": payload["inputs"],
            "metrics": {"registered": True},
        }

    service = _prepared_service()
    service.register_release_gate_evaluator(evaluator)
    app = create_control_plane_wsgi_app(service=service)

    _, gate, _ = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_gate/runs/run_gate/release-gate",
        {"tenant_id": "tenant_gate", "api_key_id": "key_gate", "request_id": "req_registered", "idempotency_key": "idem_registered"},
    )

    assert gate["grade_result"]["passed"] is False
    assert gate["grade_result"]["label"] == "registered_hold"
    assert seen_payloads[0]["target_contract"] == "A2.release_gate.evaluate"
    assert seen_payloads[0]["inputs"]["run_status"] == "queued"
    assert seen_payloads[0]["inputs"]["upload_count"] == 1
    assert seen_payloads[0]["inputs"]["trace_batch_count"] == 1
