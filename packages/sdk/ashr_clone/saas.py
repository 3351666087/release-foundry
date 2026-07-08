from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib import error, request
from urllib.parse import urljoin

from .api_client import redact_sensitive, redact_text

JsonDict = dict[str, Any]
SAAS_CLIENT_VERSION = "ashr.clone.saas_ingestion_client.v1"
BLOCKED_CONTROL_PLANE_PATH_PARTS = {".secrets", "private_refs"}


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
        http_transport: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
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
        http_transport: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
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
        url = urljoin(self.base_url, f"{_operation_path(operation, payload)}")
        response = dict(self._http_transport(url, _drop_none(payload)))
        if {"schema_version", "operation", "result"}.issubset(response):
            return redact_sensitive(response)
        return _remote_envelope(operation, response)


_OPERATION_PATHS = {
    "bootstrap_project": "bootstrap",
    "create_api_key": "api-keys",
    "list_api_keys": "api-keys/list",
    "revoke_api_key": "api-keys/revoke",
    "verify_api_key_secret": "api-keys/verify",
    "configure_api_key_rate_limit": "api-keys/rate-limit",
    "api_key_rate_limit_snapshot": "api-keys/rate-limits",
    "sdk_submit": "runs/submit",
    "upload_run": "runs/upload",
    "ingest_trace": "traces/ingest",
    "lifecycle_snapshot": "lifecycle",
    "quota_snapshot": "quota",
    "usage_snapshot": "usage",
    "create_artifact_manifest": "artifact-manifests",
    "list_artifact_manifests": "artifact-manifests/list",
    "enqueue_worker_job": "worker-jobs",
    "lease_worker_job": "worker-jobs/lease",
    "heartbeat_worker_job": "worker-jobs/heartbeat",
    "complete_worker_job": "worker-jobs/complete",
    "fail_worker_job": "worker-jobs/fail",
    "list_worker_jobs": "worker-jobs",
    "verify_audit_chain": "audit-chain/verify",
    "release_evidence": "release-evidence",
    "verify_release_evidence_packet": "release-evidence/verify",
    "state": "state",
}


def _operation_path(operation: str, payload: Mapping[str, Any] | None = None) -> str:
    if operation in {"release_evidence", "verify_release_evidence_packet", "create_artifact_manifest", "list_artifact_manifests"} and payload is not None:
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            raise SaaSClientError("run_id is required for run-scoped SaaS operations")
        suffixes = {
            "release_evidence": "release-evidence",
            "verify_release_evidence_packet": "release-evidence/verify",
            "create_artifact_manifest": "artifact-manifests",
            "list_artifact_manifests": "artifact-manifests",
        }
        suffix = suffixes[operation]
        return f"runs/{run_id}/{suffix}"
    if operation in {"heartbeat_worker_job", "complete_worker_job", "fail_worker_job"} and payload is not None:
        job_id = str(payload.get("job_id") or "")
        if not job_id:
            raise SaaSClientError("job_id is required for worker-job SaaS operations")
        suffixes = {
            "heartbeat_worker_job": "heartbeat",
            "complete_worker_job": "complete",
            "fail_worker_job": "fail",
        }
        return f"worker-jobs/{job_id}/{suffixes[operation]}"
    return _OPERATION_PATHS.get(operation, operation.replace("_", "-"))


def _normalize_base_url(base_url: str) -> str:
    value = base_url.strip()
    if not value:
        raise SaaSClientError("base_url must not be empty")
    return value.rstrip("/") + "/"


def _drop_none(payload: Mapping[str, Any]) -> JsonDict:
    return {key: value for key, value in payload.items() if value is not None}


def _post_json(url: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
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
