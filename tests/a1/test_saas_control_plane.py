from __future__ import annotations

import json

import pytest

from services.api.control_plane import CONTROL_PLANE_SCHEMA_VERSION, IdempotencyConflictError, SaaSControlPlaneService, verify_audit_chain
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


def test_saas_control_plane_audit_log_is_hash_chained_and_tamper_evident():
    control, tenant, project, dataset = _control_plane_with_dataset()
    control.create_api_key(tenant["tenant_id"], project["project_id"], name="Writer", scopes=["write:runs", "trace:ingest"], key_id="key_chain")
    submitted = control.sdk_submit_run(tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"], agent_ref="mock", run_id="run_chain", api_key_id="key_chain")
    control.upload_run_result(tenant["tenant_id"], project["project_id"], submitted["run"]["run_id"], {"status": "completed"}, upload_id="upload_chain", api_key_id="key_chain")
    control.ingest_trace(tenant["tenant_id"], project["project_id"], submitted["run"]["run_id"], [{"observation_id": "obs_chain"}], batch_id="trace_chain", api_key_id="key_chain")

    snapshot = control.audit_snapshot(tenant["tenant_id"], project["project_id"])
    events = snapshot["events"]
    assert snapshot["chain"]["verified"] is True
    assert snapshot["chain"]["event_count"] == len(events)
    filtered = control.audit_snapshot(tenant["tenant_id"], project["project_id"], action="run.upload", limit=1)
    assert filtered["events"][0]["action"] == "run.upload"
    assert filtered["chain"]["verified"] is True
    assert filtered["chain"]["event_count"] == len(events)
    assert events[0]["chain_position"] == 0
    assert events[0]["previous_audit_event_sha256"] is None
    for previous, current in zip(events, events[1:]):
        assert current["previous_audit_event_id"] == previous["audit_event_id"]
        assert current["previous_audit_event_sha256"] == previous["audit_event_sha256"]

    tampered = [dict(event) for event in events]
    tampered[1]["after_sha256"] = "0" * 64
    verification = verify_audit_chain(tampered)
    assert verification["verified"] is False
    assert any(failure["reason"] == "event_hash_mismatch" for failure in verification["failures"])


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


def test_saas_control_plane_idempotency_keys_enforce_request_fingerprints_before_mutation():
    control, tenant, project, dataset = _control_plane_with_dataset()
    control.create_api_key(
        tenant["tenant_id"],
        project["project_id"],
        name="Writer",
        scopes=["sdk:submit", "run:upload", "trace:ingest", "artifact:upload"],
        key_id="key_idem",
    )
    for operation in ["sdk:submit", "run:upload", "trace:ingest", "artifact:upload"]:
        control.configure_api_key_rate_limit(tenant["tenant_id"], project["project_id"], key_id="key_idem", operation=operation, limit=20)

    submitted = control.sdk_submit_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        agent_ref="mock",
        run_id="run_idem",
        api_key_id="key_idem",
        idempotency_key="idem_submit",
    )
    replayed_submit = control.sdk_submit_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        agent_ref="mock",
        run_id="run_idem",
        api_key_id="key_idem",
        idempotency_key="idem_submit",
    )
    assert replayed_submit["idempotent_replay"] is True
    assert replayed_submit["run"]["run_id"] == submitted["run"]["run_id"]

    uploaded = control.upload_run_result(
        tenant["tenant_id"],
        project["project_id"],
        "run_idem",
        {"run_id": "run_idem", "status": "completed", "cases": []},
        upload_id="upload_idem",
        api_key_id="key_idem",
        idempotency_key="idem_upload",
    )
    assert control.upload_run_result(
        tenant["tenant_id"],
        project["project_id"],
        "run_idem",
        {"run_id": "run_idem", "status": "completed", "cases": []},
        upload_id="upload_idem",
        api_key_id="key_idem",
        idempotency_key="idem_upload",
    )["idempotent_replay"] is True

    trace = control.ingest_trace(
        tenant["tenant_id"],
        project["project_id"],
        "run_idem",
        [{"observation_id": "obs_idem", "type": "agent_message"}],
        batch_id="trace_idem",
        api_key_id="key_idem",
        idempotency_key="idem_trace",
    )
    assert control.ingest_trace(
        tenant["tenant_id"],
        project["project_id"],
        "run_idem",
        [{"observation_id": "obs_idem", "type": "agent_message"}],
        batch_id="trace_idem",
        api_key_id="key_idem",
        idempotency_key="idem_trace",
    )["idempotent_replay"] is True

    artifact = control.create_artifact_manifest(
        tenant["tenant_id"],
        project["project_id"],
        "run_idem",
        {"schema_version": "ashr.clone.artifact_manifest.v1", "files": [{"path": "report.json", "sha256": "a" * 64}]},
        artifact_id="artifact_idem",
        api_key_id="key_idem",
        idempotency_key="idem_artifact",
    )
    assert control.create_artifact_manifest(
        tenant["tenant_id"],
        project["project_id"],
        "run_idem",
        {"schema_version": "ashr.clone.artifact_manifest.v1", "files": [{"path": "report.json", "sha256": "a" * 64}]},
        artifact_id="artifact_idem",
        api_key_id="key_idem",
        idempotency_key="idem_artifact",
    )["idempotent_replay"] is True
    assert artifact["artifact_id"] == "artifact_idem"
    assert uploaded["upload_id"] == "upload_idem"
    assert trace["batch_id"] == "trace_idem"
    rate_after_replays = control.api_key_rate_limit_snapshot(tenant["tenant_id"], project["project_id"], key_id="key_idem")["rate_limits"]
    assert {bucket["operation"]: bucket["used"] for bucket in rate_after_replays} == {"sdk:submit": 1, "run:upload": 1, "trace:ingest": 1, "artifact:upload": 1}

    quota_before = control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    rate_before = control.api_key_rate_limit_snapshot(tenant["tenant_id"], project["project_id"], key_id="key_idem")["rate_limits"]
    audit_before = len(control.store.audit_log)
    uploads_before = dict(control.store.uploads)
    trace_batches_before = dict(control.store.trace_batches)
    artifacts_before = dict(control.store.artifact_manifests)
    runs_before = dict(control.cloud.store.runs)

    with pytest.raises(IdempotencyConflictError, match="sdk.submit"):
        control.sdk_submit_run(
            tenant["tenant_id"],
            project["project_id"],
            dataset_id=dataset["dataset_id"],
            agent_ref="different",
            run_id="run_idem_conflict",
            api_key_id="key_idem",
            idempotency_key="idem_submit",
        )
    with pytest.raises(IdempotencyConflictError, match="run.upload"):
        control.upload_run_result(
            tenant["tenant_id"],
            project["project_id"],
            "run_idem",
            {"run_id": "run_idem", "status": "failed", "cases": []},
            upload_id="upload_idem_conflict",
            api_key_id="key_idem",
            idempotency_key="idem_upload",
        )
    with pytest.raises(IdempotencyConflictError, match="trace.ingest"):
        control.ingest_trace(
            tenant["tenant_id"],
            project["project_id"],
            "run_idem",
            [{"observation_id": "obs_idem_conflict", "type": "agent_message"}],
            batch_id="trace_idem_conflict",
            api_key_id="key_idem",
            idempotency_key="idem_trace",
        )
    with pytest.raises(IdempotencyConflictError, match="artifact.manifest"):
        control.create_artifact_manifest(
            tenant["tenant_id"],
            project["project_id"],
            "run_idem_missing",
            {"schema_version": "ashr.clone.artifact_manifest.v1", "files": [{"path": "other.json", "sha256": "b" * 64}]},
            artifact_id="artifact_idem_conflict",
            api_key_id="key_idem",
            idempotency_key="idem_artifact",
        )

    assert control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"] == quota_before
    assert control.api_key_rate_limit_snapshot(tenant["tenant_id"], project["project_id"], key_id="key_idem")["rate_limits"] == rate_before
    assert len(control.store.audit_log) == audit_before
    assert control.store.uploads == uploads_before
    assert control.store.trace_batches == trace_batches_before
    assert control.store.artifact_manifests == artifacts_before
    assert control.cloud.store.runs == runs_before


def test_saas_control_plane_authenticate_by_key_id_scope_never_returns_raw_secret():
    control, tenant, project, _dataset = _control_plane_with_dataset()
    control.create_api_key(
        tenant["tenant_id"],
        project["project_id"],
        name="Reader",
        scopes=["key:read"],
        key_id="key_reader",
    )

    authenticated = control.authenticate_api_key(
        tenant["tenant_id"], project["project_id"], key_id="key_reader", scope="key:read"
    )
    text = json.dumps(authenticated, sort_keys=True)

    assert authenticated["authenticated"] is True
    assert authenticated["required_scope"] == "key:read"
    assert authenticated["secret_value_present"] is False
    assert authenticated["api_key"]["last_used_at"] is not None
    assert "secret_hash_sha256" not in text
    assert "ashr_local_key_reader" not in text


def test_saas_control_plane_scoped_api_key_blocks_operations_before_quota_consumption():
    control, tenant, project, dataset = _control_plane_with_dataset()
    control.create_api_key(
        tenant["tenant_id"],
        project["project_id"],
        name="Trace only",
        scopes=["trace:ingest"],
        key_id="key_trace_only",
    )
    submitted = control.sdk_submit_run(
        tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"], agent_ref="mock", run_id="run_scoped_ok"
    )
    before = control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]

    with pytest.raises(ValidationError, match="missing required scope: sdk:submit"):
        control.sdk_submit_run(
            tenant["tenant_id"],
            project["project_id"],
            dataset_id=dataset["dataset_id"],
            agent_ref="mock",
            run_id="run_blocked_submit",
            api_key_id="key_trace_only",
        )
    with pytest.raises(ValidationError, match="missing required scope: run:upload"):
        control.upload_run_result(
            tenant["tenant_id"],
            project["project_id"],
            submitted["run"]["run_id"],
            {"run_id": submitted["run"]["run_id"], "status": "completed", "cases": []},
            upload_id="upload_blocked",
            api_key_id="key_trace_only",
        )

    after = control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    assert after == before
    assert "upload_blocked" not in control.store.uploads
    assert "run_blocked_submit" not in control.cloud.store.runs


def test_saas_control_plane_scoped_trace_ingest_blocks_before_trace_quota_or_append():
    control, tenant, project, dataset = _control_plane_with_dataset()
    control.create_api_key(
        tenant["tenant_id"],
        project["project_id"],
        name="Uploader",
        scopes=["run:upload"],
        key_id="key_uploader",
    )
    submitted = control.sdk_submit_run(
        tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"], agent_ref="mock", run_id="run_trace_scope"
    )
    before = control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]

    with pytest.raises(ValidationError, match="missing required scope: trace:ingest"):
        control.ingest_trace(
            tenant["tenant_id"],
            project["project_id"],
            submitted["run"]["run_id"],
            [{"observation_id": "obs_blocked", "type": "agent_message"}],
            batch_id="trace_blocked",
            api_key_id="key_uploader",
        )

    after = control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    run = control.cloud.get_run(tenant["tenant_id"], project["project_id"], submitted["run"]["run_id"])
    assert after == before
    assert run["observations"] == []
    assert "trace_blocked" not in control.store.trace_batches


def test_saas_control_plane_revoked_key_cannot_auth_or_consume_quota():
    control, tenant, project, dataset = _control_plane_with_dataset()
    control.create_api_key(
        tenant["tenant_id"],
        project["project_id"],
        name="Submitter",
        scopes=["sdk:submit"],
        key_id="key_revoked",
    )
    control.revoke_api_key(tenant["tenant_id"], project["project_id"], "key_revoked")
    before = control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]

    with pytest.raises(ValidationError, match="not active"):
        control.authenticate_api_key(tenant["tenant_id"], project["project_id"], key_id="key_revoked", scope="sdk:submit")
    with pytest.raises(ValidationError, match="not active"):
        control.sdk_submit_run(
            tenant["tenant_id"],
            project["project_id"],
            dataset_id=dataset["dataset_id"],
            agent_ref="mock",
            run_id="run_revoked_blocked",
            api_key_id="key_revoked",
        )

    after = control.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    assert after == before
    assert "run_revoked_blocked" not in control.cloud.store.runs


def test_saas_control_plane_worker_job_lease_retry_dead_letter_and_redaction():
    control, tenant, project, dataset = _control_plane_with_dataset()
    tenant_id = tenant["tenant_id"]
    project_id = project["project_id"]
    submitted = control.sdk_submit_run(tenant_id, project_id, dataset_id=dataset["dataset_id"], agent_ref="mock", run_id="run_worker_job")

    enqueued = control.enqueue_worker_job(
        tenant_id,
        project_id,
        job_type="run.replay",
        target_id=submitted["run"]["run_id"],
        payload={"run_id": submitted["run"]["run_id"], "secret": "must-not-be-stored"},
        job_id="job_replay_1",
        priority=5,
        max_attempts=2,
        idempotency_key="idem_job_1",
    )
    replay = control.enqueue_worker_job(
        tenant_id,
        project_id,
        job_type="run.replay",
        target_id=submitted["run"]["run_id"],
        payload={"run_id": submitted["run"]["run_id"], "secret": "must-not-be-stored"},
        job_id="job_replay_1",
        priority=5,
        max_attempts=2,
        idempotency_key="idem_job_1",
    )
    assert replay["idempotent_replay"] is True
    assert enqueued["raw_payload_included"] is False
    assert "secret" not in json.dumps(enqueued, sort_keys=True)

    leased = control.lease_worker_job(tenant_id, project_id, lease_owner_id="worker-a", lease_seconds=30, job_type="run.replay")
    assert leased["leased"] is True
    assert leased["job"]["attempts"] == 1
    assert leased["job"]["lease_owner_id"] == "worker-a"
    with pytest.raises(ValidationError, match="lease owner mismatch"):
        control.complete_worker_job(tenant_id, project_id, "job_replay_1", {"ok": True}, lease_owner_id="worker-b")

    failed = control.fail_worker_job(
        tenant_id,
        project_id,
        "job_replay_1",
        {"type": "TransientError", "message": "redacted network failure", "raw": "not stored"},
        lease_owner_id="worker-a",
        retry_after_seconds=0,
    )
    assert failed["status"] == "retrying"
    assert failed["last_error"]["raw_payload_included"] is False

    leased_again = control.lease_worker_job(tenant_id, project_id, lease_owner_id="worker-b", lease_seconds=30)
    assert leased_again["job"]["attempts"] == 2
    dead = control.fail_worker_job(tenant_id, project_id, "job_replay_1", {"type": "PermanentError"}, lease_owner_id="worker-b")
    assert dead["status"] == "dead_lettered"
    assert control.lease_worker_job(tenant_id, project_id, lease_owner_id="worker-c")["status"] == "empty"

    listed = control.list_worker_jobs(tenant_id, project_id, status="dead_lettered")
    assert listed["count"] == 1
    assert listed["returned_count"] == 1
    assert listed["total_count"] == 1
    assert listed["has_more"] is False
    assert listed["next_cursor"] is None
    assert listed["jobs"][0]["job_id"] == "job_replay_1"
    limited = control.list_worker_jobs(tenant_id, project_id, limit=1)
    assert limited["count"] == 1
    assert limited["returned_count"] == 1
    assert limited["total_count"] == 1
    assert limited["has_more"] is False
    assert control.cloud.quota_snapshot(tenant_id, project_id)["used"]["worker.job.fail"] == 2
    audit = control.audit_snapshot(tenant_id, project_id)
    assert {event["action"] for event in audit["events"]} >= {"worker.job.enqueue", "worker.job.lease", "worker.job.fail"}


def test_saas_control_plane_worker_job_can_be_released_after_expired_lease():
    control, tenant, project, _dataset = _control_plane_with_dataset()
    tenant_id = tenant["tenant_id"]
    project_id = project["project_id"]
    control.enqueue_worker_job(tenant_id, project_id, job_type="trace.compact", job_id="job_expiring", max_attempts=2)

    leased = control.lease_worker_job(tenant_id, project_id, lease_owner_id="worker-old", lease_seconds=1)
    assert leased["job"]["lease_owner_id"] == "worker-old"
    control.store.worker_jobs["job_expiring"]["lease_expires_at"] = "2000-01-01T00:00:00.000Z"

    leased_again = control.lease_worker_job(tenant_id, project_id, lease_owner_id="worker-new", lease_seconds=1)
    assert leased_again["leased"] is True
    assert leased_again["job"]["lease_owner_id"] == "worker-new"
    assert leased_again["job"]["attempts"] == 2


def test_saas_control_plane_worker_job_router_and_openapi_use_enqueue_route():
    from services.api.control_plane import SaaSControlPlaneRouter, control_plane_openapi_document

    control, tenant, project, _dataset = _control_plane_with_dataset()
    tenant_id = tenant["tenant_id"]
    project_id = project["project_id"]
    router = SaaSControlPlaneRouter(control)
    spec = control_plane_openapi_document()

    assert "/v1/projects/{project_id}/worker-jobs/enqueue" in spec["paths"]
    assert "post" not in spec["paths"]["/v1/projects/{project_id}/worker-jobs"]

    enqueued = router.handle(
        "POST",
        f"/v1/projects/{project_id}/worker-jobs/enqueue",
        {"tenant_id": tenant_id, "job_type": "trace.compact", "job_id": "job_route_enqueue", "payload": {"secret": "must-not-leak"}},
    )
    assert enqueued["status_code"] == 202
    assert enqueued["body"]["raw_payload_included"] is False
    assert "must-not-leak" not in json.dumps(enqueued, sort_keys=True)

    listed = router.handle("GET", f"/v1/projects/{project_id}/worker-jobs", {"tenant_id": tenant_id, "limit": 1})
    assert listed["status_code"] == 200
    assert listed["body"]["returned_count"] == 1
    assert listed["body"]["total_count"] == 1
    assert listed["body"]["has_more"] is False
    assert listed["body"]["next_cursor"] is None


def test_saas_control_plane_router_covers_key_sdk_upload_trace_lifecycle_and_redaction():
    from services.api.control_plane import SaaSControlPlaneRouter

    control, tenant, project, dataset = _control_plane_with_dataset()
    router = SaaSControlPlaneRouter(control)
    tenant_id = tenant["tenant_id"]
    project_id = project["project_id"]
    base_body = {"tenant_id": tenant_id}

    key = router.handle(
        "POST",
        f"/v1/projects/{project_id}/api-keys",
        {**base_body, "name": "SDK key", "scopes": ["sdk:submit", "run:upload", "trace:ingest"], "key_id": "key_router"},
    )
    assert key["status_code"] == 201
    assert key["body"]["secret_value_present"] is False

    authenticated = router.handle(
        "POST",
        f"/v1/projects/{project_id}/api-keys/key_router/authenticate",
        {**base_body, "scope": "sdk:submit"},
    )
    assert authenticated["status_code"] == 200
    assert authenticated["body"]["authenticated"] is True

    submitted = router.handle(
        "POST",
        f"/v1/projects/{project_id}/sdk-submit",
        {
            **base_body,
            "api_key_id": "key_router",
            "dataset_id": dataset["dataset_id"],
            "agent_ref": "examples.agents.mock_agent:RespondingMockAgent",
            "run_id": "run_router",
            "metadata": {"source": "router-test"},
        },
    )
    assert submitted["status_code"] == 202
    assert submitted["body"]["run"]["metadata"]["source"] == "router-test"

    uploaded = router.handle(
        "POST",
        f"/v1/projects/{project_id}/runs/run_router/upload",
        {
            **base_body,
            "api_key_id": "key_router",
            "upload_id": "upload_router",
            "result": {"run_id": "run_router", "status": "completed", "cases": []},
        },
    )
    assert uploaded["status_code"] == 202
    assert uploaded["body"]["payload_keys"] == ["cases", "run_id", "status"]

    trace = router.handle(
        "POST",
        f"/v1/projects/{project_id}/runs/run_router/trace-events",
        {
            **base_body,
            "api_key_id": "key_router",
            "batch_id": "trace_router",
            "observations": [{"observation_id": "obs_router", "type": "agent_message"}],
        },
    )
    assert trace["status_code"] == 202
    assert trace["body"]["observation_ids"] == ["obs_router"]

    snapshot = router.handle("GET", f"/v1/projects/{project_id}/runs/run_router/lifecycle", base_body)
    assert snapshot["status_code"] == 200
    assert snapshot["body"]["quota"]["used"]["sdk.submit"] == 1
    assert snapshot["body"]["quota"]["used"]["run.submit"] == 1
    assert snapshot["body"]["quota"]["used"]["run.upload"] == 1
    assert snapshot["body"]["quota"]["used"]["trace.ingest"] == 1

    revoked = router.handle(
        "POST",
        f"/v1/projects/{project_id}/api-keys/key_router/revoke",
        base_body,
    )
    assert revoked["status_code"] == 200
    assert revoked["body"]["status"] == "revoked"

    blocked = router.handle(
        "POST",
        f"/v1/projects/{project_id}/sdk-submit",
        {**base_body, "api_key_id": "key_router", "dataset_id": dataset["dataset_id"], "agent_ref": "mock", "run_id": "run_router_blocked"},
    )
    assert blocked["status_code"] == 400
    assert blocked["body"]["error"]["code"] == "validation_error"
    combined = json.dumps({"key": key, "authenticated": authenticated, "snapshot": snapshot, "revoked": revoked}, sort_keys=True)
    assert "secret_hash_sha256" not in combined
    assert "ashr_local_key_router" not in combined
    assert "completed" not in json.dumps(uploaded, sort_keys=True)


def test_saas_control_plane_state_roundtrip_preserves_control_plane_and_quota(tmp_path):
    from services.api.control_plane import control_plane_from_state_file, write_control_plane_state

    control, tenant, project, dataset = _control_plane_with_dataset()
    control.create_api_key(tenant["tenant_id"], project["project_id"], name="All ops", scopes=["*"], key_id="key_state")
    submitted = control.sdk_submit_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        agent_ref="mock",
        run_id="run_state",
        api_key_id="key_state",
    )
    control.upload_run_result(
        tenant["tenant_id"],
        project["project_id"],
        submitted["run"]["run_id"],
        {"run_id": "run_state", "status": "completed", "cases": []},
        upload_id="upload_state",
        api_key_id="key_state",
    )
    control.ingest_trace(
        tenant["tenant_id"],
        project["project_id"],
        submitted["run"]["run_id"],
        [{"observation_id": "obs_state", "type": "agent_message"}],
        batch_id="trace_state",
        api_key_id="key_state",
    )

    state_path = tmp_path / "control_plane_state.json"
    write_control_plane_state(control, str(state_path))
    state_text = state_path.read_text(encoding="utf-8")
    state_payload = json.loads(state_text)

    assert state_payload["schema_version"] == CONTROL_PLANE_SCHEMA_VERSION
    assert state_payload["metadata"] == {"local_only": True, "ashr_api_used": False}
    assert state_payload["control_plane"]["uploads"]["upload_state"]["raw_payload_included"] is False
    assert "ashr_local_key_state" not in state_text

    restored = control_plane_from_state_file(str(state_path))
    snapshot = restored.lifecycle_snapshot(tenant["tenant_id"], project["project_id"], "run_state")
    assert snapshot["uploads"][0]["upload_id"] == "upload_state"
    assert snapshot["trace_batches"][0]["batch_id"] == "trace_state"
    assert snapshot["quota"]["used"]["sdk.submit"] == 1
    assert snapshot["quota"]["used"]["run.upload"] == 1
    assert restored.authenticate_api_key(tenant["tenant_id"], project["project_id"], key_id="key_state", scope="trace:ingest")["authenticated"] is True


def test_saas_control_plane_router_maps_missing_resources_to_404():
    from services.api.control_plane import SaaSControlPlaneRouter

    control, tenant, project, _dataset = _control_plane_with_dataset()
    router = SaaSControlPlaneRouter(control)
    response = router.handle(
        "POST",
        f"/v1/projects/{project['project_id']}/api-keys/missing_key/authenticate",
        {"tenant_id": tenant["tenant_id"], "scope": "sdk:submit"},
    )

    assert response["status_code"] == 404
    assert response["body"]["error"]["code"] == "not_found"
