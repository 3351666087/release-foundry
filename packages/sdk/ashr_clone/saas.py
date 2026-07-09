from __future__ import annotations

import json
from inspect import signature
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib import error, request
from urllib.parse import urlencode, urljoin, quote

from .api_client import redact_sensitive, redact_text

JsonDict = dict[str, Any]
SAAS_CLIENT_VERSION = "ashr.clone.saas_ingestion_client.v1"
BLOCKED_CONTROL_PLANE_PATH_PARTS = {".secrets", "private_refs"}

HOSTED_ROUTE_SCOPE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "GET /v1/projects/{project_id}/api-keys": ("api_key:read",),
    "GET /v1/projects/{project_id}/api-keys/rate-limits": (),
    "GET /v1/projects/{project_id}/audit-log": ("audit:read",),
    "GET /v1/projects/{project_id}/runs/{run_id}/artifact-manifests": ("evidence:read",),
    "GET /v1/projects/{project_id}/runs/{run_id}/release-evidence": ("evidence:read",),
    "GET /v1/projects/{project_id}/usage": ("usage:read",),
    "GET /v1/projects/{project_id}/worker-jobs": ("worker_job:read",),
    "POST /v1/bootstrap": (),
    "POST /v1/projects/{project_id}/api-keys": ("api_key:write",),
    "POST /v1/projects/{project_id}/api-keys/{key_id}/rate-limit": ("api_key:write",),
    "POST /v1/projects/{project_id}/api-keys/{key_id}/revoke": ("api_key:write",),
    "POST /v1/projects/{project_id}/api-keys/{key_id}/verify": (),
    "POST /v1/projects/{project_id}/audit-chain/verify": ("audit:read",),
    "POST /v1/projects/{project_id}/runs/{run_id}/artifact-manifests": ("artifact:upload",),
    "POST /v1/projects/{project_id}/runs/{run_id}/release-evidence/verify": ("evidence:read",),
    "POST /v1/projects/{project_id}/runs/{run_id}/trace-events": ("trace:ingest",),
    "POST /v1/projects/{project_id}/runs/{run_id}/upload": ("run:upload",),
    "POST /v1/projects/{project_id}/sdk-submit": ("sdk:submit",),
    "POST /v1/projects/{project_id}/worker-jobs/enqueue": ("worker_job:write",),
    "POST /v1/projects/{project_id}/worker-jobs/lease": ("worker_job:write",),
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/complete": ("worker_job:write",),
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/fail": ("worker_job:write",),
    "POST /v1/projects/{project_id}/worker-jobs/{job_id}/heartbeat": ("worker_job:write",),
}


class SaaSClientError(RuntimeError):
    pass


class SecretInputError(SaaSClientError):
    pass


class SaaSIngestionClient:
    """SaaS ingestion client for the A1 Python SDK.

    By default the client uses the in-process ``services.api.control_plane``
    runtime. Passing ``base_url`` switches to HTTP JSON transport for a local
    hosted adapter. The client never reads API keys from environment variables
    and never accepts raw key material; callers pass public ``api_key_id``
    handles for scoped local auth checks.
    """

    def __init__(
        self,
        *,
        service: Any | None = None,
        base_url: str | None = None,
        http_transport: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        if service is not None and base_url is not None:
            raise SaaSClientError("provide either service or base_url, not both")
        self.base_url = _normalize_base_url(base_url) if base_url else None
        self._http_transport = http_transport or _post_json
        if self.base_url is None and service is None:
            service = _new_service()
        self.service = service

    @classmethod
    def from_state_file(cls, path: str | Path) -> "SaaSIngestionClient":
        _assert_public_control_plane_path(path)
        from services.api.control_plane import control_plane_from_state_file

        return cls(service=control_plane_from_state_file(str(path)))

    @classmethod
    def from_base_url(
        cls,
        base_url: str,
        *,
        http_transport: Callable[..., Mapping[str, Any]] | None = None,
    ) -> "SaaSIngestionClient":
        return cls(base_url=base_url, http_transport=http_transport)

    @property
    def uses_http(self) -> bool:
        return self.base_url is not None

    def write_state(self, path: str | Path) -> str:
        if self.uses_http:
            raise SaaSClientError("state files are only supported in in-process mode")
        from services.api.control_plane import write_control_plane_state

        return write_control_plane_state(self.service, str(path))

    def snapshot_state(self) -> JsonDict:
        if self.uses_http:
            return self._request("state", {})["result"]
        from services.api.control_plane import snapshot_control_plane

        return redact_sensitive(snapshot_control_plane(self.service))

    def bootstrap_project(
        self,
        *,
        tenant_name: str,
        project_name: str,
        tenant_id: str | None = None,
        project_id: str | None = None,
        dataset_id: str | None = None,
        dataset_name: str = "SDK Bootstrap Dataset",
        cases: Sequence[Mapping[str, Any]] | None = None,
    ) -> JsonDict:
        if self.uses_http:
            return self._request(
                "bootstrap_project",
                {
                    "tenant_name": tenant_name,
                    "project_name": project_name,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "dataset_name": dataset_name,
                    "cases": list(cases) if cases is not None else None,
                },
            )
        result = self.service.bootstrap_project(
            tenant_name=tenant_name,
            project_name=project_name,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if dataset_id is not None:
            case_payload = list(cases or [{"id": "sdk-bootstrap-case", "prompt": "local bootstrap", "expected": {"text": "local bootstrap"}}])
            result["dataset"] = self.service.cloud.create_dataset(
                result["tenant"]["tenant_id"],
                result["project"]["project_id"],
                name=dataset_name,
                dataset_id=dataset_id,
                cases=case_payload,
                metadata={"created_by": "ashr_clone.saas_client", "local_only": True},
            )
        return _envelope("bootstrap_project", result)

    def create_api_key(
        self,
        tenant_id: str,
        project_id: str,
        *,
        name: str,
        scopes: Sequence[str],
        key_id: str | None = None,
        auth_key_id: str | None = None,
        reveal_secret: bool = False,
        api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        if self.uses_http:
            return self._request(
                "create_api_key",
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "name": name,
                    "scopes": [str(scope) for scope in scopes],
                    "key_id": key_id,
                    "auth_key_id": auth_key_id,
                    "reveal_secret": bool(reveal_secret),
                },
            )
        result = self.service.create_api_key(
            tenant_id,
            project_id,
            name=name,
            scopes=[str(scope) for scope in scopes],
            key_id=key_id,
            auth_key_id=auth_key_id,
            reveal_secret=bool(reveal_secret),
        )
        return _envelope("create_api_key", result)

    def list_api_keys(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None, api_key: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        if self.uses_http:
            return self._request("list_api_keys", {"tenant_id": tenant_id, "project_id": project_id, "auth_key_id": auth_key_id})
        return _envelope("list_api_keys", {"api_keys": self.service.list_api_keys(tenant_id, project_id, auth_key_id=auth_key_id)})

    def revoke_api_key(self, tenant_id: str, project_id: str, key_id: str, *, auth_key_id: str | None = None, api_key: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        if self.uses_http:
            return self._request("revoke_api_key", {"tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "auth_key_id": auth_key_id})
        return _envelope("revoke_api_key", self.service.revoke_api_key(tenant_id, project_id, key_id, auth_key_id=auth_key_id))

    def verify_api_key_secret(
        self,
        tenant_id: str,
        project_id: str,
        key_id: str,
        *,
        secret: str,
        scope: str | None = None,
    ) -> JsonDict:
        if self.uses_http:
            return self._request("verify_api_key_secret", {"tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "secret": secret, "scope": scope})
        return _envelope("verify_api_key_secret", self.service.verify_api_key_secret(tenant_id, project_id, key_id=key_id, secret=secret, scope=scope))

    def configure_api_key_rate_limit(
        self,
        tenant_id: str,
        project_id: str,
        key_id: str,
        *,
        operation: str,
        limit: int,
        period: str = "local-window",
        auth_key_id: str | None = None,
        api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        if self.uses_http:
            return self._request(
                "configure_api_key_rate_limit",
                {"tenant_id": tenant_id, "project_id": project_id, "key_id": key_id, "operation": operation, "limit": int(limit), "period": period, "auth_key_id": auth_key_id},
            )
        return _envelope(
            "configure_api_key_rate_limit",
            self.service.configure_api_key_rate_limit(tenant_id, project_id, key_id=key_id, operation=operation, limit=int(limit), period=period, auth_key_id=auth_key_id),
        )

    def api_key_rate_limit_snapshot(self, tenant_id: str, project_id: str, *, key_id: str | None = None) -> JsonDict:
        if self.uses_http:
            return self._request("api_key_rate_limit_snapshot", {"tenant_id": tenant_id, "project_id": project_id, "key_id": key_id})
        return _envelope("api_key_rate_limit_snapshot", self.service.api_key_rate_limit_snapshot(tenant_id, project_id, key_id=key_id))

    def sdk_submit(
        self,
        tenant_id: str,
        project_id: str,
        *,
        dataset_id: str,
        agent_ref: str,
        run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        api_key_id: str | None = None,
        api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        if self.uses_http:
            return self._request(
                "sdk_submit",
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "agent_ref": agent_ref,
                    "run_id": run_id,
                    "metadata": {"client": SAAS_CLIENT_VERSION, **dict(metadata or {})},
                    "api_key_id": api_key_id,
                    "idempotency_key": idempotency_key,
                    "request_id": request_id,
                },
            )
        result = self.service.sdk_submit_run(
            tenant_id,
            project_id,
            dataset_id=dataset_id,
            agent_ref=agent_ref,
            run_id=run_id,
            metadata={"client": SAAS_CLIENT_VERSION, **dict(metadata or {})},
            api_key_id=api_key_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return _envelope("sdk_submit", result)

    def upload_run(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        result: Mapping[str, Any],
        *,
        upload_id: str | None = None,
        api_key_id: str | None = None,
        api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        if self.uses_http:
            return self._request(
                "upload_run",
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": run_id,
                    "result": dict(result),
                    "upload_id": upload_id,
                    "api_key_id": api_key_id,
                    "idempotency_key": idempotency_key,
                    "request_id": request_id,
                },
            )
        upload = self.service.upload_run_result(
            tenant_id,
            project_id,
            run_id,
            dict(result),
            upload_id=upload_id,
            api_key_id=api_key_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return _envelope("upload_run", upload)

    def ingest_trace(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        observations: Sequence[Mapping[str, Any]],
        *,
        batch_id: str | None = None,
        api_key_id: str | None = None,
        api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        if self.uses_http:
            return self._request(
                "ingest_trace",
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "run_id": run_id,
                    "observations": [dict(item) for item in observations],
                    "batch_id": batch_id,
                    "api_key_id": api_key_id,
                    "idempotency_key": idempotency_key,
                    "request_id": request_id,
                },
            )
        result = self.service.ingest_trace(
            tenant_id,
            project_id,
            run_id,
            [dict(item) for item in observations],
            batch_id=batch_id,
            api_key_id=api_key_id,
            idempotency_key=idempotency_key,
            request_id=request_id,
        )
        return _envelope("ingest_trace", result)

    def lifecycle_snapshot(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        if self.uses_http:
            return self._request("lifecycle_snapshot", {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id})
        return _envelope("lifecycle_snapshot", self.service.lifecycle_snapshot(tenant_id, project_id, run_id))

    def quota_snapshot(self, tenant_id: str, project_id: str) -> JsonDict:
        if self.uses_http:
            return self._request("quota_snapshot", {"tenant_id": tenant_id, "project_id": project_id})
        return _envelope("quota_snapshot", self.service.cloud.quota_snapshot(tenant_id, project_id))

    def usage_snapshot(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None) -> JsonDict:
        if self.uses_http:
            return self._request("usage_snapshot", {"tenant_id": tenant_id, "project_id": project_id, "auth_key_id": auth_key_id})
        return _envelope("usage_snapshot", self.service.usage_snapshot(tenant_id, project_id, auth_key_id=auth_key_id))

    def audit_log(
        self,
        tenant_id: str,
        project_id: str,
        *,
        auth_key_id: str | None = None,
        run_id: str | None = None,
        action: str | None = None,
        action_prefix: str | None = None,
        target_id: str | None = None,
        api_key_id: str | None = None,
        limit: int | None = None,
        api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        payload = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "auth_key_id": auth_key_id,
            "run_id": run_id,
            "action": action,
            "action_prefix": action_prefix,
            "target_id": target_id,
            "audit_api_key_id": api_key_id,
            "limit": limit,
        }
        if self.uses_http:
            return self._request("audit_log", payload)
        snapshot = dict(
            self.service.audit_snapshot(
                tenant_id,
                project_id,
                auth_key_id=auth_key_id,
                action=action,
                target_id=target_id or run_id,
                api_key_id=api_key_id,
                limit=limit,
            )
        )
        snapshot.setdefault("event_count", len(snapshot.get("events", [])) if isinstance(snapshot.get("events"), list) else 0)
        return _envelope("audit_log", snapshot)

    def create_artifact_manifest(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        manifest: Mapping[str, Any],
        *,
        artifact_id: str | None = None,
        api_key_id: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        payload = {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "manifest": dict(manifest), "artifact_id": artifact_id, "api_key_id": api_key_id, "idempotency_key": idempotency_key, "request_id": request_id}
        if self.uses_http:
            return self._request("create_artifact_manifest", payload)
        return _envelope("create_artifact_manifest", self.service.create_artifact_manifest(tenant_id, project_id, run_id, dict(manifest), artifact_id=artifact_id, api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id))

    def list_artifact_manifests(self, tenant_id: str, project_id: str, run_id: str, *, auth_key_id: str | None = None) -> JsonDict:
        if self.uses_http:
            return self._request("list_artifact_manifests", {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "auth_key_id": auth_key_id})
        return _envelope("list_artifact_manifests", {"artifact_manifests": self.service.list_artifact_manifests(tenant_id, project_id, run_id, auth_key_id=auth_key_id)})

    def enqueue_worker_job(
        self,
        tenant_id: str,
        project_id: str,
        *,
        job_type: str,
        target_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        job_id: str | None = None,
        priority: int = 100,
        max_attempts: int = 3,
        api_key_id: str | None = None,
        api_key: str | None = None,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        request_payload = {"tenant_id": tenant_id, "project_id": project_id, "job_type": job_type, "target_id": target_id, "payload": dict(payload or {}), "job_id": job_id, "priority": int(priority), "max_attempts": int(max_attempts), "api_key_id": api_key_id, "idempotency_key": idempotency_key, "request_id": request_id}
        if self.uses_http:
            return self._request("enqueue_worker_job", request_payload)
        return _envelope("enqueue_worker_job", self.service.enqueue_worker_job(tenant_id, project_id, job_type=job_type, target_id=target_id, payload=dict(payload or {}), job_id=job_id, priority=int(priority), max_attempts=int(max_attempts), api_key_id=api_key_id, idempotency_key=idempotency_key, request_id=request_id))

    def lease_worker_job(
        self,
        tenant_id: str,
        project_id: str,
        *,
        lease_owner_id: str,
        lease_seconds: float = 300.0,
        job_type: str | None = None,
        api_key_id: str | None = None,
        api_key: str | None = None,
        request_id: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "lease_owner_id": lease_owner_id, "lease_seconds": float(lease_seconds), "job_type": job_type, "api_key_id": api_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("lease_worker_job", payload)
        return _envelope("lease_worker_job", self.service.lease_worker_job(tenant_id, project_id, lease_owner_id=lease_owner_id, lease_seconds=float(lease_seconds), job_type=job_type, api_key_id=api_key_id, request_id=request_id))

    def heartbeat_worker_job(self, tenant_id: str, project_id: str, job_id: str, *, lease_owner_id: str, lease_seconds: float = 300.0, api_key_id: str | None = None, api_key: str | None = None, request_id: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "job_id": job_id, "lease_owner_id": lease_owner_id, "lease_seconds": float(lease_seconds), "api_key_id": api_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("heartbeat_worker_job", payload)
        return _envelope("heartbeat_worker_job", self.service.heartbeat_worker_job(tenant_id, project_id, job_id, lease_owner_id=lease_owner_id, lease_seconds=float(lease_seconds), api_key_id=api_key_id, request_id=request_id))

    def complete_worker_job(self, tenant_id: str, project_id: str, job_id: str, result: Mapping[str, Any] | None = None, *, lease_owner_id: str, api_key_id: str | None = None, api_key: str | None = None, request_id: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "job_id": job_id, "result": dict(result or {}), "lease_owner_id": lease_owner_id, "api_key_id": api_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("complete_worker_job", payload)
        return _envelope("complete_worker_job", self.service.complete_worker_job(tenant_id, project_id, job_id, dict(result or {}), lease_owner_id=lease_owner_id, api_key_id=api_key_id, request_id=request_id))

    def fail_worker_job(self, tenant_id: str, project_id: str, job_id: str, error_payload: Mapping[str, Any] | None = None, *, lease_owner_id: str, retry_after_seconds: float | None = None, api_key_id: str | None = None, api_key: str | None = None, request_id: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "job_id": job_id, "error": dict(error_payload or {}), "lease_owner_id": lease_owner_id, "retry_after_seconds": retry_after_seconds, "api_key_id": api_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("fail_worker_job", payload)
        return _envelope("fail_worker_job", self.service.fail_worker_job(tenant_id, project_id, job_id, dict(error_payload or {}), lease_owner_id=lease_owner_id, retry_after_seconds=retry_after_seconds, api_key_id=api_key_id, request_id=request_id))

    def list_worker_jobs(self, tenant_id: str, project_id: str, *, status: str | None = None, job_type: str | None = None, limit: int | None = None, auth_key_id: str | None = None, api_key: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "status": status, "job_type": job_type, "limit": limit, "auth_key_id": auth_key_id}
        if self.uses_http:
            return self._request("list_worker_jobs", payload)
        return _envelope("list_worker_jobs", self.service.list_worker_jobs(tenant_id, project_id, status=status, job_type=job_type, limit=limit, auth_key_id=auth_key_id))

    def verify_audit_chain(
        self,
        tenant_id: str,
        project_id: str,
        *,
        auth_key_id: str | None = None,
        action: str | None = None,
        target_id: str | None = None,
        api_key_id: str | None = None,
        limit: int | None = None,
        request_id: str | None = None,
        api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "auth_key_id": auth_key_id, "action": action, "target_id": target_id, "audit_api_key_id": api_key_id, "limit": limit, "request_id": request_id}
        if self.uses_http:
            return self._request("verify_audit_chain", payload)
        return _envelope("verify_audit_chain", self.service.verify_audit_chain_snapshot(tenant_id, project_id, auth_key_id=auth_key_id, action=action, target_id=target_id, api_key_id=api_key_id, limit=limit, request_id=request_id))

    def build_release_evidence_packet(self, tenant_id: str, project_id: str, run_id: str, *, auth_key_id: str | None = None) -> JsonDict:
        if self.uses_http:
            return self._request("release_evidence", {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "auth_key_id": auth_key_id})
        from services.api.platform import build_release_evidence_packet, usage_billing_rollup

        packet = build_release_evidence_packet(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run_id,
            lifecycle=self.service.lifecycle_snapshot(tenant_id, project_id, run_id),
            artifact_manifest={"artifacts": self.service.list_artifact_manifests(tenant_id, project_id, run_id, auth_key_id=auth_key_id)},
            billing_rollup=usage_billing_rollup(list(self.service.store.usage_ledger.values()), tenant_id=tenant_id, project_id=project_id, billing_period="local"),
            audit_chain=self.service.audit_snapshot(tenant_id, project_id, auth_key_id=auth_key_id, target_id=run_id).get("chain", {}),
        )
        return _envelope("release_evidence", packet)

    def verify_release_evidence_packet(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        packet: Mapping[str, Any] | None = None,
        auth_key_id: str | None = None,
        request_id: str | None = None,
        api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        payload = {"tenant_id": tenant_id, "project_id": project_id, "run_id": run_id, "packet": dict(packet) if packet is not None else None, "auth_key_id": auth_key_id, "request_id": request_id}
        if self.uses_http:
            return self._request("verify_release_evidence_packet", payload)
        source = "submitted_packet" if packet is not None else "current_snapshot"
        if packet is None:
            packet = self.build_release_evidence_packet(tenant_id, project_id, run_id, auth_key_id=auth_key_id)["result"]
        return _envelope("verify_release_evidence_packet", {**self.service.verify_release_evidence_packet(tenant_id, project_id, dict(packet), run_id=run_id, auth_key_id=auth_key_id, request_id=request_id), "source": source})

    def _request(self, operation: str, payload: Mapping[str, Any]) -> JsonDict:
        if not self.base_url:  # pragma: no cover
            raise SaaSClientError("HTTP transport requested without base_url")
        method, path = _operation_route(operation, payload)
        body = _drop_none(payload)
        url = urljoin(self.base_url, path.lstrip("/"))
        if method == "GET" and body:
            url = f"{url}?{urlencode(body)}"
        response = dict(_call_http_transport(self._http_transport, method, url, {} if method == "GET" else body))
        if {"schema_version", "operation", "result"}.issubset(response):
            return redact_sensitive(response)
        return _remote_envelope(operation, response)


_GET_OPERATIONS = {
    "list_api_keys",
    "api_key_rate_limit_snapshot",
    "lifecycle_snapshot",
    "quota_snapshot",
    "usage_snapshot",
    "audit_log",
    "list_artifact_manifests",
    "list_worker_jobs",
    "release_evidence",
    "state",
}


def _operation_route(operation: str, payload: Mapping[str, Any] | None = None) -> tuple[str, str]:
    payload = payload or {}
    method = "GET" if operation in _GET_OPERATIONS else "POST"
    if operation == "bootstrap_project":
        return method, "/v1/bootstrap"
    if operation == "state":
        return method, "/v1/state"
    project_id = _required_route_value(payload, "project_id", operation)
    project_path = f"/v1/projects/{_quote_path(project_id)}"
    if operation in {"create_api_key", "list_api_keys"}:
        return method, f"{project_path}/api-keys"
    if operation in {"revoke_api_key", "verify_api_key_secret", "configure_api_key_rate_limit"}:
        key_id = _required_route_value(payload, "key_id", operation)
        suffix = {"revoke_api_key": "revoke", "verify_api_key_secret": "verify", "configure_api_key_rate_limit": "rate-limit"}[operation]
        return method, f"{project_path}/api-keys/{_quote_path(key_id)}/{suffix}"
    if operation == "api_key_rate_limit_snapshot":
        return method, f"{project_path}/api-keys/rate-limits"
    if operation == "sdk_submit":
        return method, f"{project_path}/sdk-submit"
    if operation in {"upload_run", "ingest_trace", "lifecycle_snapshot", "create_artifact_manifest", "list_artifact_manifests", "release_evidence", "release_evidence_verify", "verify_release_evidence_packet"}:
        run_id = _required_route_value(payload, "run_id", operation)
        suffix = {
            "upload_run": "upload",
            "ingest_trace": "trace-events",
            "lifecycle_snapshot": "lifecycle",
            "create_artifact_manifest": "artifact-manifests",
            "list_artifact_manifests": "artifact-manifests",
            "release_evidence": "release-evidence",
            "release_evidence_verify": "release-evidence/verify",
            "verify_release_evidence_packet": "release-evidence/verify",
        }[operation]
        return method, f"{project_path}/runs/{_quote_path(run_id)}/{suffix}"
    if operation in {"quota_snapshot", "usage_snapshot"}:
        suffix = "quota" if operation == "quota_snapshot" else "usage"
        return method, f"{project_path}/{suffix}"
    if operation in {"enqueue_worker_job", "lease_worker_job", "list_worker_jobs"}:
        suffix = {"enqueue_worker_job": "worker-jobs/enqueue", "lease_worker_job": "worker-jobs/lease", "list_worker_jobs": "worker-jobs"}[operation]
        return method, f"{project_path}/{suffix}"
    if operation in {"heartbeat_worker_job", "complete_worker_job", "fail_worker_job"}:
        job_id = _required_route_value(payload, "job_id", operation)
        suffix = {"heartbeat_worker_job": "heartbeat", "complete_worker_job": "complete", "fail_worker_job": "fail"}[operation]
        return method, f"{project_path}/worker-jobs/{_quote_path(job_id)}/{suffix}"
    if operation == "verify_audit_chain":
        return method, f"{project_path}/audit-chain/verify"
    if operation == "audit_log":
        return method, f"{project_path}/audit-log"
    raise SaaSClientError(f"unsupported SaaS HTTP operation: {operation}")


def _required_route_value(payload: Mapping[str, Any], key: str, operation: str) -> str:
    value = str(payload.get(key) or "")
    if not value:
        raise SaaSClientError(f"{key} is required for {operation} SaaS operations")
    return value


def _quote_path(value: str) -> str:
    return quote(value, safe="")


def _normalize_base_url(base_url: str) -> str:
    value = base_url.strip()
    if not value:
        raise SaaSClientError("base_url must not be empty")
    return value.rstrip("/") + "/"


def _drop_none(payload: Mapping[str, Any]) -> JsonDict:
    return {key: value for key, value in payload.items() if value is not None}


def _call_http_transport(transport: Callable[..., Mapping[str, Any]], method: str, url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        return transport(url, payload, method=method)
    except TypeError as exc:
        try:
            signature(transport).bind(url, payload, method=method)
        except TypeError:
            return transport(url, payload)
        else:
            raise
        raise exc


def _post_json(url: str, payload: Mapping[str, Any], *, method: str = "POST") -> Mapping[str, Any]:
    upper_method = method.upper()
    body = None if upper_method == "GET" else json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method=upper_method)
    try:
        with request.urlopen(req, timeout=30) as resp:  # nosec - caller supplied local hosted adapter URL.
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SaaSClientError(f"HTTP {exc.code} from hosted adapter: {redact_text(detail)}") from exc
    except error.URLError as exc:
        raise SaaSClientError(f"hosted adapter request failed: {redact_text(str(exc.reason))}") from exc
    data = json.loads(raw or "{}")
    if not isinstance(data, Mapping):
        raise SaaSClientError("hosted adapter JSON response must be an object")
    return data


def _remote_envelope(operation: str, result: Mapping[str, Any]) -> JsonDict:
    return {
        "schema_version": SAAS_CLIENT_VERSION,
        "operation": operation,
        "result": redact_sensitive(result),
        "metadata": {"local_only": False, "ashr_api_used": False, "raw_auth_material_used": False, "transport": "http"},
    }


def load_json_file(path: str | Path) -> Any:
    _assert_public_control_plane_path(path)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def hosted_route_scope_manifest() -> JsonDict:
    return {
        "schema_version": "ashr.clone.hosted_route_scope_manifest.v1",
        "client": "python",
        "public_safe": True,
        "source_policy": {"private_evidence_read": False, "raw_payloads_included": False, "tokens_included": False},
        "routes": [
            {"route": route, "required_scopes": list(scopes)}
            for route, scopes in sorted(HOSTED_ROUTE_SCOPE_REQUIREMENTS.items())
        ],
    }


def consume_go_route_scope_manifest(manifest: Mapping[str, Any] | str | Path) -> JsonDict:
    snapshot = load_json_file(manifest) if isinstance(manifest, (str, Path)) else dict(manifest)
    if snapshot.get("public_safe") is not True:
        raise SaaSClientError("route/scope manifest must be public_safe")
    source_policy = snapshot.get("source_policy")
    if source_policy != {"private_evidence_read": False, "raw_payloads_included": False, "tokens_included": False}:
        raise SaaSClientError("route/scope manifest has unsafe source policy")

    go_routes = {str(route) for route in snapshot.get("go_manifest_routes", [])}
    hosted_routes = set(HOSTED_ROUTE_SCOPE_REQUIREMENTS)
    consumable_go_routes = sorted(go_routes & hosted_routes)
    return {
        "schema_version": "ashr.clone.go_route_scope_consumption.v1",
        "client": "python",
        "public_safe": True,
        "source_policy": source_policy,
        "consumable_go_routes": consumable_go_routes,
        "unsupported_go_routes": sorted(go_routes - hosted_routes),
        "client_only_routes": sorted(hosted_routes - go_routes),
        "route_scopes": [
            {"route": route, "required_scopes": list(HOSTED_ROUTE_SCOPE_REQUIREMENTS[route])}
            for route in consumable_go_routes
        ],
    }


def _new_service() -> Any:
    from services.api.control_plane import SaaSControlPlaneService

    return SaaSControlPlaneService()


def _envelope(operation: str, result: Mapping[str, Any]) -> JsonDict:
    payload = {
        "schema_version": SAAS_CLIENT_VERSION,
        "operation": operation,
        "result": result,
        "metadata": {"local_only": True, "ashr_api_used": False, "raw_auth_material_used": False},
    }
    return payload


def _reject_raw_api_key(api_key: str | None) -> None:
    if api_key:
        raise SecretInputError("raw API key values are not accepted; use a local api_key_id handle")


def _assert_public_control_plane_path(path: str | Path) -> None:
    parts = {part.lower() for part in Path(path).parts}
    if parts & BLOCKED_CONTROL_PLANE_PATH_PARTS:
        raise SecretInputError("refusing to read private_refs or .secrets input paths")


def redacted_error_message(exc: BaseException) -> str:
    return redact_text(str(exc))
