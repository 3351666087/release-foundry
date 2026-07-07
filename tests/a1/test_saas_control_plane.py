from __future__ import annotations

import json

import pytest

from services.api.control_plane import CONTROL_PLANE_SCHEMA_VERSION, SaaSControlPlaneService
from services.api.runtime import QuotaExceededError, ValidationError


def _control_plane_with_dataset():
    control = SaaSControlPlaneService()
    boot = control.bootstrap_project(tenant_name="Enterprise Tenant", project_name="Release Gate", tenant_id="tenant_saas", project_id="project_saas")
    dataset = control.cloud.create_dataset(
        "tenant_saas",
        "project_saas",
        name="Release dataset",
        dataset_id="dataset_saas",
        cases=[{"id": "case-1", "prompt": "hello", "expected": {"text": "Echo: hello"}}],
    )
    return control, boot["tenant"], boot["project"], dataset


def test_saas_control_plane_api_key_governance_never_returns_secret_values():
    control, tenant, project, _dataset = _control_plane_with_dataset()

    created = control.create_api_key(tenant["tenant_id"], project["project_id"], name="CI submitter", scopes=["sdk:submit", "trace:ingest"], key_id="key_ci")
    revoked = control.revoke_api_key(tenant["tenant_id"], project["project_id"], "key_ci")
    listed = control.list_api_keys(tenant["tenant_id"], project["project_id"])
    text = json.dumps({"created": created, "revoked": revoked, "listed": listed}, sort_keys=True)

    assert created["schema_version"] == CONTROL_PLANE_SCHEMA_VERSION
    assert created["secret_hash_present"] is True
    assert created["secret_value_present"] is False
    assert revoked["status"] == "revoked"
    assert listed[0]["prefix"] == "ashr_local_***"
    assert "secret_hash_sha256" not in text
    assert "ashr_local_key_ci" not in text


def test_saas_control_plane_sdk_submit_run_upload_trace_ingestion_and_lifecycle():
    control, tenant, project, dataset = _control_plane_with_dataset()

    submitted = control.sdk_submit_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        agent_ref="examples.agents.mock_agent:RespondingMockAgent",
        run_id="run_saas_submit",
    )
    uploaded = control.upload_run_result(
        tenant["tenant_id"],
        project["project_id"],
        submitted["run"]["run_id"],
        {"run_id": "run_saas_submit", "status": "completed", "cases": []},
        upload_id="upload_saas",
    )
    ingested = control.ingest_trace(
        tenant["tenant_id"],
        project["project_id"],
        submitted["run"]["run_id"],
        [
            {"observation_id": "obs_1", "type": "agent_message", "content": {"text": "hello"}},
            {"observation_id": "obs_2", "type": "tool_call", "tool_name": "search"},
        ],
        batch_id="trace_batch_saas",
    )
    snapshot = control.lifecycle_snapshot(tenant["tenant_id"], project["project_id"], submitted["run"]["run_id"])
    quota = snapshot["quota"]["used"]

    assert submitted["submission"]["status"] == "accepted"
    assert submitted["run"]["status"] == "queued"
    assert uploaded["raw_payload_included"] is False
    assert uploaded["payload_keys"] == ["cases", "run_id", "status"]
    assert ingested["observation_count"] == 2
    assert snapshot["tenant_status"] == "active"
    assert snapshot["project_status"] == "active"
    assert snapshot["run_status"] == "queued"
    assert len(snapshot["uploads"]) == 1
    assert len(snapshot["trace_batches"]) == 1
    assert quota["run.submit"] == 1
    assert quota["run.upload"] == 1
    assert quota["trace.ingest"] == 2
    assert quota["observation.write"] == 2


def test_saas_control_plane_quota_ledger_blocks_trace_ingestion_before_append():
    control, tenant, project, dataset = _control_plane_with_dataset()
    submitted = control.sdk_submit_run(tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"], agent_ref="mock", run_id="run_trace_quota")
    control.cloud.quota.configure(tenant["tenant_id"], project["project_id"], {"trace.ingest": 1})

    with pytest.raises(QuotaExceededError):
        control.ingest_trace(
            tenant["tenant_id"],
            project["project_id"],
            submitted["run"]["run_id"],
            [
                {"observation_id": "obs_1", "type": "agent_message"},
                {"observation_id": "obs_2", "type": "agent_message"},
            ],
        )

    run = control.cloud.get_run(tenant["tenant_id"], project["project_id"], submitted["run"]["run_id"])
    assert run["observations"] == []
    assert control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"].get("trace.ingest") is None


def test_saas_control_plane_validates_api_key_scope_and_trace_payload():
    control, tenant, project, dataset = _control_plane_with_dataset()
    submitted = control.sdk_submit_run(tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"], agent_ref="mock", run_id="run_validation")

    with pytest.raises(ValidationError, match="scopes"):
        control.create_api_key(tenant["tenant_id"], project["project_id"], name="bad", scopes=[])
    with pytest.raises(ValidationError, match="at least one observation"):
        control.ingest_trace(tenant["tenant_id"], project["project_id"], submitted["run"]["run_id"], [])
