from __future__ import annotations

import json
from io import BytesIO

from services.api.control_plane import SaaSControlPlaneService, create_control_plane_wsgi_app


RAW_AUTH_VALUES = ("Bearer releasefoundry_should_not_leak", "releasefoundry_api_key=should_not_leak", "sk_test_should_not_leak")


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


def _prepared_service() -> SaaSControlPlaneService:
    service = SaaSControlPlaneService()
    service.bootstrap_project(tenant_name="Quota Auth Tenant", project_name="Quota Auth Project", tenant_id="tenant_auth", project_id="project_auth")
    service.cloud.create_dataset(
        "tenant_auth",
        "project_auth",
        name="Quota auth dataset",
        dataset_id="dataset_auth",
        cases=[{"id": "case_auth", "prompt": "hello", "expected": {"text": "hello"}}],
    )
    service.create_api_key("tenant_auth", "project_auth", name="Runner", scopes=["sdk:submit", "run:upload", "trace:ingest", "artifact:upload"], key_id="key_runner")
    service.create_api_key("tenant_auth", "project_auth", name="Read only", scopes=["audit:read", "usage:read", "evidence:read"], key_id="key_reader")
    service.create_api_key("tenant_auth", "project_auth", name="Billing", scopes=["billing:write", "billing:webhook"], key_id="key_billing")
    service.sdk_submit_run("tenant_auth", "project_auth", dataset_id="dataset_auth", agent_ref="mock", run_id="run_auth", api_key_id="key_runner")
    service.upload_run_result("tenant_auth", "project_auth", "run_auth", {"status": "completed"}, upload_id="upload_auth", api_key_id="key_runner")
    return service


def _assert_public_safe(*texts: str) -> None:
    for text in texts:
        for raw in RAW_AUTH_VALUES:
            assert raw not in text
        assert "secret_hash_sha256" not in text
        assert "one_time_secret" not in text


def test_wrong_scope_denies_trace_ingest_and_appends_public_safe_receipts():
    service = _prepared_service()
    app = create_control_plane_wsgi_app(service=service)

    meta, denied, denied_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_auth/runs/run_auth/trace-events",
        {
            "tenant_id": "tenant_auth",
            "api_key_id": "key_reader",
            "request_id": "req_trace_denied",
            "idempotency_key": "idem_trace_denied",
            "observations": [{"type": "agent_message", "authorization": RAW_AUTH_VALUES[0]}],
        },
    )

    assert str(meta["status"]).startswith("400 ")
    assert denied["error"]["code"] == "validation_error"
    assert "trace:ingest" in denied["error"]["message"]

    _, audit, audit_text = _invoke_wsgi(app, "GET", "/v1/projects/project_auth/audit-log", query="tenant_id=tenant_auth&api_key_id=key_reader&action=auth.denied")
    assert [event["action"] for event in audit["events"]] == ["auth.denied"]
    assert audit["events"][0]["api_key_id"] == "key_reader"
    assert audit["events"][0]["request_id"] == "req_trace_denied"
    assert audit["events"][0]["idempotency_key"] == "idem_trace_denied"
    assert audit["events"][0]["after_sha256"]

    _, usage, usage_text = _invoke_wsgi(app, "GET", "/v1/projects/project_auth/usage", query="tenant_id=tenant_auth&api_key_id=key_reader")
    receipts = [event for event in usage["events"] if event.get("operation") == "trace.ingest" and event.get("denied") is True]
    assert len(receipts) == 1
    assert receipts[0]["units"] == 0
    assert receipts[0]["required_scope"] == "trace:ingest"
    assert receipts[0]["status"] == "denied"
    assert receipts[0]["secret_value_present"] is False
    assert receipts[0]["raw_payload_included"] is False
    _assert_public_safe(denied_text, audit_text, usage_text)


def test_missing_scope_denies_artifact_and_evidence_surfaces_with_receipts():
    service = _prepared_service()
    app = create_control_plane_wsgi_app(service=service)

    cases = [
        ("POST", "/v1/projects/project_auth/runs/run_auth/artifact-manifests", {"tenant_id": "tenant_auth", "request_id": "req_artifact_missing", "manifest": {"schema_version": "x", "bearer": RAW_AUTH_VALUES[0]}}, "artifact.manifest", "artifact:upload"),
        ("GET", "/v1/projects/project_auth/runs/run_auth/release-evidence", None, "release_evidence.read", "evidence:read"),
    ]

    for method, path, body, operation, required_scope in cases:
        meta, denied, denied_text = _invoke_wsgi(app, method, path, body, query="tenant_id=tenant_auth" if body is None else "")
        assert str(meta["status"]).startswith("400 ")
        assert required_scope in denied["error"]["message"]
        _assert_public_safe(denied_text)

    _, usage, usage_text = _invoke_wsgi(app, "GET", "/v1/projects/project_auth/usage", query="tenant_id=tenant_auth&api_key_id=key_reader")
    denied_by_operation = {event["operation"]: event for event in usage["events"] if event.get("denied") is True}
    assert denied_by_operation["artifact.manifest"]["required_scope"] == "artifact:upload"
    assert denied_by_operation["release_evidence.read"]["required_scope"] == "evidence:read"
    assert all(event["api_key_id"] is None for event in denied_by_operation.values())
    _assert_public_safe(usage_text)


def test_billing_and_webhook_surfaces_require_specific_scopes_without_auth_leaks():
    service = _prepared_service()
    app = create_control_plane_wsgi_app(service=service)

    meta, denied, denied_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_auth/billing/checkout-plan",
        {
            "tenant_id": "tenant_auth",
            "api_key_id": "key_reader",
            "request_id": "req_checkout_denied",
            "customer_ref": "cus_public",
            "price": {"amount_minor": 1000, "currency": "usd", "lookup_key": "starter"},
            "success_url": "https://example.invalid/success",
            "cancel_url": "https://example.invalid/cancel",
            "provider_config": {"provider": "stripe", "mode": "test", "secret_ref": "env:STRIPE_TEST_REF", "bearer": RAW_AUTH_VALUES[0]},
        },
    )
    assert str(meta["status"]).startswith("400 ")
    assert "billing:write" in denied["error"]["message"]
    _assert_public_safe(denied_text)

    meta, accepted, accepted_text = _invoke_wsgi(
        app,
        "POST",
        "/v1/projects/project_auth/billing/webhooks/ingest",
        {
            "tenant_id": "tenant_auth",
            "api_key_id": "key_billing",
            "provider": "stripe",
            "mode": "test",
            "event_type": "invoice.paid",
            "event_id": "evt_public",
            "payload_sha256": "a" * 64,
            "signature_header_present": True,
            "webhook_secret_ref": "env:STRIPE_TEST_WEBHOOK_REF",
            "verified": True,
            "metadata": {"api_key": RAW_AUTH_VALUES[2]},
        },
    )
    assert str(meta["status"]).startswith("202 ")
    assert accepted["verified"] is False
    assert "provider_specific_verification_required" in {failure["reason"] for failure in accepted["failures"]}
    assert accepted["secret_value_present"] is False
    _assert_public_safe(accepted_text)

    payment_snapshot = service.commercial_auth_payment_snapshot("tenant_auth", "project_auth")
    assert payment_snapshot["payment_mode_boundaries"] == []

    _, usage, usage_text = _invoke_wsgi(app, "GET", "/v1/projects/project_auth/usage", query="tenant_id=tenant_auth&api_key_id=key_reader")
    checkout_receipts = [event for event in usage["events"] if event.get("operation") == "billing.checkout_plan" and event.get("denied") is True]
    assert len(checkout_receipts) == 1
    assert checkout_receipts[0]["required_scope"] == "billing:write"
    assert checkout_receipts[0]["api_key_id"] == "key_reader"
    _assert_public_safe(usage_text)
