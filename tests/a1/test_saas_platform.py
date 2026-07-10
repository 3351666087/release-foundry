from __future__ import annotations

import json
import re

import pytest

from services.api.control_plane import SaaSControlPlaneService
from services.api.platform import (
    PLATFORM_SCHEMA_VERSION,
    LocalObjectStore,
    WebhookRegistry,
    build_release_evidence_packet,
    platform_schema_manifest,
    platform_sql_migration_text,
    release_gate_bridge_payload,
    usage_billing_rollup,
    verify_release_evidence_packet,
)
from services.api.runtime import ValidationError


def test_platform_schema_manifest_covers_large_saas_tables_and_indexes():
    manifest = platform_schema_manifest()
    expected = {
        "organizations",
        "workspaces",
        "projects",
        "environments",
        "datasets",
        "runs",
        "case_results",
        "trace_events",
        "observations",
        "artifacts",
        "evidence_bundles",
        "api_keys",
        "webhook_endpoints",
        "webhook_deliveries",
        "usage_ledger",
        "quota_policies",
        "billing_accounts",
        "integrations",
        "audit_log",
    }
    assert manifest["schema_version"] == PLATFORM_SCHEMA_VERSION
    assert expected <= set(manifest["tables"])
    for name, table in manifest["tables"].items():
        if table["tenant_scoped"]:
            assert "organization_id" in table["columns"], name
    assert any(index["name"] == "idx_runs_tenant_scope" for index in manifest["indexes"])

    sql = platform_sql_migration_text()
    assert "CREATE TABLE IF NOT EXISTS runs" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_runs_tenant_scope" in sql


def test_local_object_store_records_artifacts_without_raw_payload():
    store = LocalObjectStore()
    artifact = store.put_artifact(
        tenant_id="tenant_obj",
        project_id="project_obj",
        run_id="run_obj",
        content=b"secret customer trace payload",
        content_type="application/json",
        artifact_id="artifact_obj",
        redaction_status="hash_only",
    )
    text = json.dumps(artifact, sort_keys=True)
    assert artifact["artifact_id"] == "artifact_obj"
    assert artifact["raw_payload_included"] is False
    assert artifact["size_bytes"] == len(b"secret customer trace payload")
    assert "secret customer trace payload" not in text

    signed = store.create_signed_upload_url(tenant_id="tenant_obj", project_id="project_obj", artifact_id="artifact_next")
    assert signed["method"] == "PUT"
    assert signed["url"].startswith("local://object-store/artifact_next?signature=")
    manifest = store.public_manifest("tenant_obj", "project_obj")
    assert manifest["artifacts"][0]["sha256"] == artifact["sha256"]

    with pytest.raises(ValidationError):
        store.put_artifact(tenant_id="t", project_id="p", run_id=None, content="x", content_type="text/plain", redaction_status="raw")


def test_webhook_registry_signs_delivery_without_exposing_secret_or_payload():
    registry = WebhookRegistry()
    endpoint = registry.register_endpoint(
        tenant_id="tenant_hook",
        project_id="project_hook",
        url="https://example.invalid/webhook",
        events=["run.completed"],
        webhook_id="webhook_hook",
    )
    assert endpoint["secret_value_present"] is False
    assert endpoint["secret_hash_present"] is True
    assert "secret_hash_sha256" not in endpoint

    delivered = registry.deliver(
        tenant_id="tenant_hook",
        project_id="project_hook",
        event_type="run.completed",
        payload={"run_id": "run_hook", "api_key": "tp_should_not_leak"},
    )
    assert len(delivered["deliveries"]) == 1
    delivery = delivered["deliveries"][0]
    assert delivery["raw_payload_included"] is False
    assert delivery["headers"]["x-ashr-signature-sha256"] == "present"
    assert delivery["signature_present"] is True
    assert delivery["signature_algorithm"] == "hmac-sha256"
    assert re.fullmatch(r"[0-9a-f]{64}", delivery["signed_payload_sha256"])
    delivered_text = json.dumps(delivered, sort_keys=True)
    assert "tp_should_not_leak" not in delivered_text
    assert "whsec_local_" not in delivered_text
    assert delivery["headers"] == {"x-ashr-event": "run.completed", "x-ashr-signature-sha256": "present"}

    with pytest.raises(ValidationError):
        registry.register_endpoint(tenant_id="t", project_id="p", url="http://evil.invalid", events=["*"])


def test_usage_rollup_and_release_gate_bridge_payload():
    control = SaaSControlPlaneService()
    control.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_gate", project_id="project_gate")
    control.cloud.create_dataset("tenant_gate", "project_gate", name="Dataset", dataset_id="dataset_gate", cases=[{"id": "case-1"}])
    key = control.create_api_key("tenant_gate", "project_gate", name="CI", scopes=["sdk:submit", "run:upload", "trace:ingest"], key_id="key_gate")
    assert key["key_id"] == "key_gate"
    submitted = control.sdk_submit_run("tenant_gate", "project_gate", dataset_id="dataset_gate", agent_ref="mock", run_id="run_gate", api_key_id="key_gate")
    control.upload_run_result("tenant_gate", "project_gate", submitted["run"]["run_id"], {"status": "completed"}, api_key_id="key_gate")
    control.ingest_trace("tenant_gate", "project_gate", submitted["run"]["run_id"], [{"observation_id": "obs_gate"}], api_key_id="key_gate")

    rollup = usage_billing_rollup(list(control.store.usage_ledger.values()), tenant_id="tenant_gate", project_id="project_gate", billing_period="2026-07")
    assert rollup["operation_totals"]["sdk.submit"] == 1
    assert rollup["operation_totals"]["run.upload"] == 1
    assert rollup["operation_totals"]["trace.ingest"] == 1
    assert rollup["billable_units"] >= 3

    lifecycle = control.lifecycle_snapshot("tenant_gate", "project_gate", "run_gate")
    bridge = release_gate_bridge_payload(tenant_id="tenant_gate", project_id="project_gate", run_id="run_gate", lifecycle=lifecycle)
    assert bridge["target_contract"] == "A2.release_gate.evaluate"
    assert bridge["decision_hint"] == "pass"
    assert bridge["inputs"]["upload_count"] == 1
    assert bridge["inputs"]["trace_batch_count"] == 1

def test_release_evidence_packet_closes_run_gate_webhook_loop_without_raw_payload():
    control = SaaSControlPlaneService()
    control.bootstrap_project(tenant_name="Tenant", project_name="Project", tenant_id="tenant_packet", project_id="project_packet")
    control.cloud.create_dataset("tenant_packet", "project_packet", name="Dataset", dataset_id="dataset_packet", cases=[{"id": "case-1"}])
    control.create_api_key("tenant_packet", "project_packet", name="CI", scopes=["sdk:submit", "run:upload", "trace:ingest"], key_id="key_packet")
    submitted = control.sdk_submit_run("tenant_packet", "project_packet", dataset_id="dataset_packet", agent_ref="mock", run_id="run_packet", api_key_id="key_packet")
    control.upload_run_result("tenant_packet", "project_packet", submitted["run"]["run_id"], {"status": "completed", "api_key": "tp_should_not_leak"}, upload_id="upload_packet", api_key_id="key_packet")
    control.ingest_trace("tenant_packet", "project_packet", submitted["run"]["run_id"], [{"observation_id": "obs_packet", "content": "customer secret"}], batch_id="trace_packet", api_key_id="key_packet")

    store = LocalObjectStore()
    artifact = store.put_artifact(
        tenant_id="tenant_packet",
        project_id="project_packet",
        run_id="run_packet",
        content=b"private artifact payload",
        content_type="application/json",
        artifact_id="artifact_packet",
        redaction_status="hash_only",
    )
    registry = WebhookRegistry()
    registry.register_endpoint(tenant_id="tenant_packet", project_id="project_packet", url="https://example.invalid/webhook", events=["release_gate.evaluated"], webhook_id="webhook_packet")
    delivery = registry.deliver(tenant_id="tenant_packet", project_id="project_packet", event_type="release_gate.evaluated", payload={"run_id": "run_packet", "api_key": "tp_delivery_secret"})
    lifecycle = control.lifecycle_snapshot("tenant_packet", "project_packet", "run_packet")
    audit = control.audit_snapshot("tenant_packet", "project_packet")
    rollup = usage_billing_rollup(list(control.store.usage_ledger.values()), tenant_id="tenant_packet", project_id="project_packet", billing_period="2026-07")
    packet = build_release_evidence_packet(
        tenant_id="tenant_packet",
        project_id="project_packet",
        run_id="run_packet",
        lifecycle=lifecycle,
        artifact_manifest=store.public_manifest("tenant_packet", "project_packet"),
        release_gate_result={"request_id": "req_packet", "grade_result": {"passed": True, "score": 1.0, "label": "release_gate_pass"}},
        webhook_delivery=delivery,
        billing_rollup=rollup,
        audit_chain=audit["chain"],
        packet_id="packet_round20",
    )

    text = json.dumps(packet, sort_keys=True)
    assert packet["packet_id"] == "packet_round20"
    assert packet["counts"] == {"uploads": 1, "trace_batches": 1, "artifacts": 1, "webhook_deliveries": 1}
    assert packet["release_gate"]["passed"] is True
    assert packet["usage"]["operation_totals"]["sdk.submit"] == 1
    assert packet["evidence_items"][0]["sha256"] == artifact["sha256"]
    assert packet["integrity"]["packet_sha256"]
    assert packet["audit_chain"]["verified"] is True
    assert packet["audit_chain"]["tail_audit_event_sha256"] == audit["chain"]["tail_audit_event_sha256"]
    assert verify_release_evidence_packet(packet)["verified"] is True
    assert packet["raw_payload_included"] is False
    assert "tp_should_not_leak" not in text
    assert "tp_delivery_secret" not in text
    assert "private artifact payload" not in text
    assert "customer secret" not in text

    tampered = json.loads(json.dumps(packet))
    tampered["counts"]["uploads"] = 99
    verification = verify_release_evidence_packet(tampered)
    assert verification["verified"] is False
    assert verification["failures"][0]["reason"] == "packet_sha256_mismatch"

    redaction_failure = json.loads(json.dumps(packet))
    redaction_failure["raw_payload_included"] = True
    redaction_failure["secret_value_present"] = True
    redaction_verification = verify_release_evidence_packet(redaction_failure)
    assert {failure["reason"] for failure in redaction_verification["failures"]} >= {"raw_payload_included", "secret_value_present"}

    leaked = json.loads(json.dumps(packet))
    leaked["evidence_items"].append({"name": "bad", "api_key": "redacted-by-test"})
    leaked_verification = verify_release_evidence_packet(leaked)
    assert any(failure["reason"] == "suspicious_field_present" and failure["path"].endswith(".api_key") for failure in leaked_verification["failures"])

    bundle = store.put_evidence_bundle(
        tenant_id="tenant_packet",
        project_id="project_packet",
        run_id="run_packet",
        packet=packet,
        bundle_id="bundle_packet",
        metadata={"release_gate": "passed", "retention": "enterprise_audit"},
    )
    bundle_text = json.dumps(bundle, sort_keys=True)
    assert bundle["schema_version"] == "ashr.clone.evidence_bundle_object.v1"
    assert bundle["bundle_id"] == "bundle_packet"
    assert bundle["packet_sha256"] == packet["integrity"]["packet_sha256"]
    assert bundle["object_key"] == "evidence-bundles/tenant_packet/project_packet/run_packet/bundle_packet.json"
    assert bundle["storage_uri"] == "local://object-store/evidence-bundles/tenant_packet/project_packet/run_packet/bundle_packet.json"
    assert bundle["evidence_item_count"] == len(packet["evidence_items"])
    assert bundle["raw_payload_included"] is False
    assert bundle["secret_value_present"] is False
    assert "private artifact payload" not in bundle_text
    assert "customer secret" not in bundle_text
    assert "tp_delivery_secret" not in bundle_text

    stored_verification = store.verify_stored_evidence_bundle(
        tenant_id="tenant_packet",
        project_id="project_packet",
        bundle_id="bundle_packet",
        expected_packet_sha256=packet["integrity"]["packet_sha256"],
    )
    assert stored_verification["verified"] is True
    assert stored_verification["object_key"] == bundle["object_key"]

    wrong_tenant = store.verify_stored_evidence_bundle(tenant_id="tenant_other", project_id="project_packet", bundle_id="bundle_packet")
    assert wrong_tenant["verified"] is False
    assert wrong_tenant["failures"][0]["reason"] == "tenant_project_mismatch"

    wrong_hash = store.verify_stored_evidence_bundle(
        tenant_id="tenant_packet",
        project_id="project_packet",
        bundle_id="bundle_packet",
        expected_packet_sha256="0" * 64,
    )
    assert wrong_hash["verified"] is False
    assert wrong_hash["failures"][0]["reason"] == "packet_sha256_mismatch"

    manifest_after_bundle = store.public_manifest("tenant_packet", "project_packet")
    assert manifest_after_bundle["evidence_bundles"][0]["bundle_id"] == "bundle_packet"

    with pytest.raises(ValidationError):
        store.put_evidence_bundle(tenant_id="tenant_packet", project_id="project_packet", run_id="run_packet", packet=tampered)
