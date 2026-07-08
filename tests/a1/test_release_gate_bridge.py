from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from services.api import (
    HttpReleaseGateBridgeClient,
    LocalReleaseGateBridgeClient,
    ReleaseGateBridgeError,
    ReleaseGateBridgeResponseError,
    SaaSControlPlaneService,
    evaluate_lifecycle_with_release_gate,
    lifecycle_to_release_gate_request,
)


def _lifecycle():
    control = SaaSControlPlaneService()
    control.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_bridge", project_id="project_bridge")
    control.cloud.create_dataset("tenant_bridge", "project_bridge", name="Dataset", dataset_id="dataset_bridge", cases=[{"id": "case-1"}])
    submitted = control.sdk_submit_run("tenant_bridge", "project_bridge", dataset_id="dataset_bridge", agent_ref="mock", run_id="run_bridge")
    control.upload_run_result("tenant_bridge", "project_bridge", submitted["run"]["run_id"], {"status": "completed", "api_key": "secret_should_not_leak"})
    control.ingest_trace("tenant_bridge", "project_bridge", submitted["run"]["run_id"], [{"observation_id": "obs_bridge", "token": "trace_secret"}])
    return control.lifecycle_snapshot("tenant_bridge", "project_bridge", "run_bridge")


def _grade(payload, *, passed=True):
    return {
        "scenario_id": payload["run_id"],
        "passed": passed,
        "score": 1.0 if passed else 0.25,
        "label": "release_gate_pass" if passed else "release_gate_review",
        "reason": "minimum uploads and trace batches satisfied" if passed else "release gate needs review",
        "expected": {"minimum_uploads": payload["policy"]["minimum_uploads"]},
        "actual": {"upload_count": payload["inputs"]["upload_count"], "trace_batch_count": payload["inputs"]["trace_batch_count"]},
        "metrics": {"decision_hint": payload["decision_hint"]},
    }


def test_lifecycle_to_release_gate_request_redacts_and_sets_idempotency_and_request_id():
    lifecycle = _lifecycle()
    lifecycle["api_key"] = "api_key=super_secret"
    request = lifecycle_to_release_gate_request(
        tenant_id="tenant_bridge",
        project_id="project_bridge",
        run_id="run_bridge",
        lifecycle=lifecycle,
        request_id="req_bridge",
        timeout_seconds=2,
    )

    text = json.dumps(request.payload, sort_keys=True)
    assert request.request_id == "req_bridge"
    assert request.idempotency_key.startswith("rgbi_")
    assert request.payload["target_contract"] == "A2.release_gate.evaluate"
    assert request.payload["bridge"]["timeout_seconds"] == 2.0
    assert "super_secret" not in text
    assert "trace_secret" not in text
    assert "secret_should_not_leak" not in text
    assert "[REDACTED]" in text


def test_local_callable_bridge_returns_grade_result_like_response_and_caches_by_idempotency():
    lifecycle = _lifecycle()
    calls = {"count": 0}

    def evaluator(payload):
        calls["count"] += 1
        assert payload["request_id"] == "req_local"
        return {"grade_result": _grade(payload)}

    client = LocalReleaseGateBridgeClient(evaluator)
    first = evaluate_lifecycle_with_release_gate(
        client,
        tenant_id="tenant_bridge",
        project_id="project_bridge",
        run_id="run_bridge",
        lifecycle=lifecycle,
        request_id="req_local",
        idempotency_key="idem_local",
    )
    second = evaluate_lifecycle_with_release_gate(
        client,
        tenant_id="tenant_bridge",
        project_id="project_bridge",
        run_id="run_bridge",
        lifecycle=lifecycle,
        request_id="req_local_changed",
        idempotency_key="idem_local",
    )

    assert calls["count"] == 1
    assert first == second
    assert first["transport"] == "local_callable"
    assert first["grade_result"]["passed"] is True
    assert first["grade_result"]["score"] == 1.0


def test_local_callable_bridge_redacts_errors():
    def evaluator(_payload):
        raise RuntimeError("failed with token=secret_should_not_leak")

    client = LocalReleaseGateBridgeClient(evaluator)
    with pytest.raises(ReleaseGateBridgeError) as excinfo:
        evaluate_lifecycle_with_release_gate(
            client,
            tenant_id="tenant_bridge",
            project_id="project_bridge",
            run_id="run_bridge",
            lifecycle={"uploads": [], "trace_batches": []},
            request_id="req_error",
        )
    assert "secret_should_not_leak" not in str(excinfo.value)
    assert "[REDACTED]" in str(excinfo.value)
    assert excinfo.value.request_id == "req_error"


def test_http_bridge_posts_json_headers_and_normalizes_grade_result():
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            seen["payload"] = payload
            seen["request_id"] = self.headers.get("x-request-id")
            seen["idempotency_key"] = self.headers.get("idempotency-key")
            response = json.dumps({"grade_result": _grade(payload)}).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = HttpReleaseGateBridgeClient(f"http://127.0.0.1:{server.server_port}/release-gate")
        result = evaluate_lifecycle_with_release_gate(
            client,
            tenant_id="tenant_bridge",
            project_id="project_bridge",
            run_id="run_bridge",
            lifecycle=_lifecycle(),
            request_id="req_http",
            idempotency_key="idem_http",
            timeout_seconds=2,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert seen["request_id"] == "req_http"
    assert seen["idempotency_key"] == "idem_http"
    assert seen["payload"]["target_contract"] == "A2.release_gate.evaluate"
    assert result["transport"] == "http"
    assert result["status_code"] == 200
    assert result["grade_result"]["scenario_id"] == "run_bridge"


def test_http_bridge_rejects_non_grade_result_like_response():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            response = b'{"ok": true}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = HttpReleaseGateBridgeClient(f"http://127.0.0.1:{server.server_port}/release-gate")
        with pytest.raises(ReleaseGateBridgeResponseError):
            evaluate_lifecycle_with_release_gate(
                client,
                tenant_id="tenant_bridge",
                project_id="project_bridge",
                run_id="run_bridge",
                lifecycle=_lifecycle(),
                request_id="req_bad_response",
            )
    finally:
        server.shutdown()
        server.server_close()
