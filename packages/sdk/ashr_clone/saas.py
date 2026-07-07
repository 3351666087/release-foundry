from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .api_client import redact_text

JsonDict = dict[str, Any]
SAAS_CLIENT_VERSION = "ashr.clone.saas_ingestion_client.v1"
BLOCKED_CONTROL_PLANE_PATH_PARTS = {".secrets", "private_refs"}


class SaaSClientError(RuntimeError):
    pass


class SecretInputError(SaaSClientError):
    pass


class SaaSIngestionClient:
    """Local-only SaaS ingestion client for the A1 Python SDK.

    The client intentionally models the SaaS ingestion/control-plane surface
    against the local ``services.api.control_plane`` runtime. It never reads
    API keys from environment variables and never accepts raw key material;
    callers pass public ``api_key_id`` handles for scoped local auth checks.
    """

    def __init__(self, *, service: Any | None = None) -> None:
        if service is None:
            service = _new_service()
        self.service = service

    @classmethod
    def from_state_file(cls, path: str | Path) -> "SaaSIngestionClient":
        _assert_public_control_plane_path(path)
        from services.api.control_plane import control_plane_from_state_file

        return cls(service=control_plane_from_state_file(str(path)))

    def write_state(self, path: str | Path) -> str:
        from services.api.control_plane import write_control_plane_state

        return write_control_plane_state(self.service, str(path))

    def snapshot_state(self) -> JsonDict:
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
        api_key: str | None = None,
    ) -> JsonDict:
        _reject_raw_api_key(api_key)
        result = self.service.create_api_key(
            tenant_id,
            project_id,
            name=name,
            scopes=[str(scope) for scope in scopes],
            key_id=key_id,
            auth_key_id=auth_key_id,
        )
        return _envelope("create_api_key", result)

    def list_api_keys(self, tenant_id: str, project_id: str, *, auth_key_id: str | None = None, api_key: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        return _envelope("list_api_keys", {"api_keys": self.service.list_api_keys(tenant_id, project_id, auth_key_id=auth_key_id)})

    def revoke_api_key(self, tenant_id: str, project_id: str, key_id: str, *, auth_key_id: str | None = None, api_key: str | None = None) -> JsonDict:
        _reject_raw_api_key(api_key)
        return _envelope("revoke_api_key", self.service.revoke_api_key(tenant_id, project_id, key_id, auth_key_id=auth_key_id))

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
        return _envelope("lifecycle_snapshot", self.service.lifecycle_snapshot(tenant_id, project_id, run_id))

    def quota_snapshot(self, tenant_id: str, project_id: str) -> JsonDict:
        return _envelope("quota_snapshot", self.service.cloud.quota_snapshot(tenant_id, project_id))


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
