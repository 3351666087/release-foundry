from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping
from uuid import uuid4

from .runtime import CloudApiService, JsonDict, ValidationError, _jsonable, _utc_now

CONTROL_PLANE_SCHEMA_VERSION = "ashr.clone.saas_control_plane.v1"
SAAS_QUOTA_LIMITS = {
    "api_key.create": 100,
    "run.upload": 10_000,
    "sdk.submit": 10_000,
    "trace.ingest": 100_000,
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


@dataclass(slots=True)
class SaaSControlPlaneStore:
    api_keys: dict[str, JsonDict] = field(default_factory=dict)
    uploads: dict[str, JsonDict] = field(default_factory=dict)
    trace_batches: dict[str, JsonDict] = field(default_factory=dict)
    sdk_submissions: dict[str, JsonDict] = field(default_factory=dict)


class SaaSControlPlaneService:
    """Local enterprise SaaS control-plane wrapper around CloudApiService.

    This layer models buyer-facing Ashr++ SaaS surfaces without calling hosted
    billing or mutating Ashr APIs: API key governance, SDK submit, run upload,
    trace ingestion, quota ledger integration, and tenant/project/run lifecycle.
    """

    def __init__(self, cloud: CloudApiService | None = None, *, store: SaaSControlPlaneStore | None = None) -> None:
        self.cloud = cloud or CloudApiService()
        self.store = store or SaaSControlPlaneStore()

    def bootstrap_project(self, *, tenant_name: str, project_name: str, tenant_id: str | None = None, project_id: str | None = None) -> JsonDict:
        tenant = self.cloud.create_tenant(tenant_name, tenant_id=tenant_id)
        project = self.cloud.create_project(tenant["tenant_id"], project_name, project_id=project_id)
        self.cloud.quota.configure(tenant["tenant_id"], project["project_id"], SAAS_QUOTA_LIMITS)
        return {"schema_version": CONTROL_PLANE_SCHEMA_VERSION, "tenant": tenant, "project": project, "quota": self.cloud.quota_snapshot(tenant["tenant_id"], project["project_id"])}

    def create_api_key(self, tenant_id: str, project_id: str, *, name: str, scopes: list[str], key_id: str | None = None) -> JsonDict:
        project = self.cloud.get_project(tenant_id, project_id)
        if not scopes:
            raise ValidationError("api key scopes must not be empty")
        self.cloud.quota.consume(project["tenant_id"], project["project_id"], "api_key.create")
        key_id = key_id or _new_id("key")
        synthetic_secret = f"ashr_local_{key_id}_{uuid4().hex}"
        digest = hashlib.sha256(synthetic_secret.encode("utf-8")).hexdigest()
        now = _utc_now()
        record = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "tenant_id": project["tenant_id"],
            "project_id": project["project_id"],
            "key_id": key_id,
            "name": str(name),
            "prefix": "ashr_local_***",
            "secret_hash_sha256": digest,
            "secret_value_present": False,
            "status": "active",
            "scopes": list(scopes),
            "created_at": now,
            "revoked_at": None,
            "last_used_at": None,
        }
        self.store.api_keys[key_id] = record
        return _public_api_key(record)

    def revoke_api_key(self, tenant_id: str, project_id: str, key_id: str) -> JsonDict:
        record = self._api_key_record(tenant_id, project_id, key_id)
        record["status"] = "revoked"
        record["revoked_at"] = _utc_now()
        return _public_api_key(record)

    def list_api_keys(self, tenant_id: str, project_id: str) -> list[JsonDict]:
        self.cloud.get_project(tenant_id, project_id)
        return [_public_api_key(record) for record in self.store.api_keys.values() if record.get("tenant_id") == str(tenant_id) and record.get("project_id") == str(project_id)]

    def sdk_submit_run(self, tenant_id: str, project_id: str, *, dataset_id: str, agent_ref: str, run_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> JsonDict:
        run = self.cloud.create_queued_run(tenant_id, project_id, dataset_id=dataset_id, run_id=run_id, runner_id="sdk-submit", metadata={"submitted_by": "sdk", "agent_ref": agent_ref, **dict(metadata or {})})
        submission = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "submission_id": _new_id("sdksub"),
            "tenant_id": tenant_id,
            "project_id": project_id,
            "dataset_id": dataset_id,
            "run_id": run["run_id"],
            "agent_ref": str(agent_ref),
            "status": "accepted",
            "created_at": _utc_now(),
        }
        self.store.sdk_submissions[submission["submission_id"]] = submission
        return _jsonable({"submission": submission, "run": run})

    def upload_run_result(self, tenant_id: str, project_id: str, run_id: str, result: Mapping[str, Any], *, upload_id: str | None = None) -> JsonDict:
        run = self.cloud.get_run(tenant_id, project_id, run_id)
        self.cloud.quota.consume(tenant_id, project_id, "run.upload")
        upload_id = upload_id or _new_id("upload")
        payload = _jsonable(dict(result))
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        record = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "upload_id": upload_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run["run_id"],
            "payload_sha256": digest,
            "payload_keys": sorted(payload.keys()),
            "raw_payload_included": False,
            "status": "uploaded",
            "created_at": _utc_now(),
        }
        self.store.uploads[upload_id] = record
        return _jsonable(record)

    def ingest_trace(self, tenant_id: str, project_id: str, run_id: str, observations: list[Mapping[str, Any]], *, batch_id: str | None = None) -> JsonDict:
        self.cloud.get_run(tenant_id, project_id, run_id)
        if not observations:
            raise ValidationError("trace ingestion requires at least one observation")
        self.cloud.quota.consume(tenant_id, project_id, "trace.ingest", units=len(observations))
        appended = [self.cloud.append_observation(tenant_id, project_id, run_id, observation) for observation in observations]
        batch_id = batch_id or _new_id("tracebatch")
        record = {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "batch_id": batch_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "observation_count": len(appended),
            "observation_ids": [item.get("observation_id") for item in appended],
            "status": "ingested",
            "created_at": _utc_now(),
        }
        self.store.trace_batches[batch_id] = record
        return _jsonable(record)

    def lifecycle_snapshot(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        tenant = self.cloud.get_tenant(tenant_id)
        project = self.cloud.get_project(tenant_id, project_id)
        run = self.cloud.get_run(tenant_id, project_id, run_id)
        return {
            "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
            "tenant_id": tenant["tenant_id"],
            "project_id": project["project_id"],
            "run_id": run["run_id"],
            "tenant_status": "active",
            "project_status": "active",
            "run_status": run["status"],
            "run_result_status": run.get("result_status"),
            "status_history": run.get("status_history", []),
            "quota": self.cloud.quota_snapshot(tenant_id, project_id),
            "api_keys": self.list_api_keys(tenant_id, project_id),
            "uploads": [item for item in self.store.uploads.values() if item.get("run_id") == run_id],
            "trace_batches": [item for item in self.store.trace_batches.values() if item.get("run_id") == run_id],
        }

    def _api_key_record(self, tenant_id: str, project_id: str, key_id: str) -> JsonDict:
        record = self.store.api_keys.get(str(key_id))
        if not record or record.get("tenant_id") != str(tenant_id) or record.get("project_id") != str(project_id):
            raise ValidationError("api key not found for project")
        return record


def _public_api_key(record: Mapping[str, Any]) -> JsonDict:
    return {
        "schema_version": CONTROL_PLANE_SCHEMA_VERSION,
        "tenant_id": record.get("tenant_id"),
        "project_id": record.get("project_id"),
        "key_id": record.get("key_id"),
        "name": record.get("name"),
        "prefix": record.get("prefix"),
        "secret_hash_present": bool(record.get("secret_hash_sha256")),
        "secret_value_present": False,
        "status": record.get("status"),
        "scopes": list(record.get("scopes", [])),
        "created_at": record.get("created_at"),
        "revoked_at": record.get("revoked_at"),
        "last_used_at": record.get("last_used_at"),
    }
