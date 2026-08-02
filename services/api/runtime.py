from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
from typing import Any, Iterable, Mapping
from uuid import uuid4

CLOUD_API_SCHEMA_VERSION = "releasefoundry.cloud_api.v1"

JsonDict = dict[str, Any]

DEFAULT_QUOTA_LIMITS: dict[str, int] = {
    "dataset.create": 1_000,
    "observation.write": 100_000,
    "request.create": 1_000,
    "run.submit": 10_000,
}

DEFAULT_QUEUE_LEASE_SECONDS = 300.0
DEFAULT_QUEUE_MAX_ATTEMPTS = 3
TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled", "dead_lettered"}


class CloudApiError(RuntimeError):
    code = "cloud_api_error"

    def to_dict(self) -> JsonDict:
        return {"code": self.code, "message": str(self)}


class ValidationError(CloudApiError):
    code = "validation_error"


class NotFoundError(CloudApiError):
    code = "not_found"


class QuotaExceededError(CloudApiError):
    code = "quota_exceeded"


@dataclass(slots=True)
class QuotaLedger:
    default_limits: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_QUOTA_LIMITS))
    limits: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)
    used: dict[tuple[str, str], dict[str, int]] = field(default_factory=dict)

    def configure(self, tenant_id: str, project_id: str, limits: Mapping[str, int]) -> JsonDict:
        key = self._key(tenant_id, project_id)
        current = dict(self.limits.get(key, self.default_limits))
        for operation, limit in limits.items():
            parsed = int(limit)
            if parsed < 0:
                raise ValidationError("quota limits must be non-negative")
            current[str(operation)] = parsed
        self.limits[key] = current
        self.used.setdefault(key, {})
        return self.snapshot(tenant_id, project_id)

    def check(self, tenant_id: str, project_id: str, operation: str, *, units: int = 1) -> None:
        units = _positive_units(units)
        key = self._key(tenant_id, project_id)
        limit = self._limit_for(key, operation)
        used = self.used.get(key, {}).get(operation, 0)
        if used + units > limit:
            raise QuotaExceededError(
                f"quota exceeded for {operation}: requested {units}, remaining {max(0, limit - used)}"
            )

    def consume(self, tenant_id: str, project_id: str, operation: str, *, units: int = 1) -> JsonDict:
        units = _positive_units(units)
        self.check(tenant_id, project_id, operation, units=units)
        key = self._key(tenant_id, project_id)
        bucket = self.used.setdefault(key, {})
        bucket[operation] = bucket.get(operation, 0) + units
        limit = self._limit_for(key, operation)
        return {
            "operation": operation,
            "units": units,
            "used": bucket[operation],
            "limit": limit,
            "remaining": max(0, limit - bucket[operation]),
        }

    def snapshot(self, tenant_id: str, project_id: str) -> JsonDict:
        key = self._key(tenant_id, project_id)
        limits = dict(self.limits.get(key, self.default_limits))
        used = dict(self.used.get(key, {}))
        return {
            "schema_version": CLOUD_API_SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "limits": limits,
            "used": used,
            "remaining": {operation: max(0, limit - used.get(operation, 0)) for operation, limit in limits.items()},
        }

    def _limit_for(self, key: tuple[str, str], operation: str) -> int:
        return int(self.limits.get(key, self.default_limits).get(operation, self.default_limits.get(operation, 0)))

    @staticmethod
    def _key(tenant_id: str, project_id: str) -> tuple[str, str]:
        return str(tenant_id), str(project_id)


@dataclass(slots=True)
class InMemoryCloudStore:
    tenants: dict[str, JsonDict] = field(default_factory=dict)
    projects: dict[str, JsonDict] = field(default_factory=dict)
    datasets: dict[str, JsonDict] = field(default_factory=dict)
    requests: dict[str, JsonDict] = field(default_factory=dict)
    runs: dict[str, JsonDict] = field(default_factory=dict)

    def snapshot(self) -> JsonDict:
        return _jsonable(
            {
                "schema_version": CLOUD_API_SCHEMA_VERSION,
                "tenants": self.tenants,
                "projects": self.projects,
                "datasets": self.datasets,
                "requests": self.requests,
                "runs": self.runs,
            }
        )


class CloudApiService:
    def __init__(self, *, store: InMemoryCloudStore | None = None, quota: QuotaLedger | None = None) -> None:
        self.store = store or InMemoryCloudStore()
        self.quota = quota or QuotaLedger()
        self._lock = threading.RLock()

    def create_tenant(self, name: str, *, tenant_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> JsonDict:
        tenant_id = tenant_id or _new_id("tenant")
        _require_id(tenant_id, "tenant_id")
        if tenant_id in self.store.tenants:
            raise ValidationError(f"tenant already exists: {tenant_id}")
        record = {
            "schema_version": CLOUD_API_SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "name": _require_text(name, "name"),
            "created_at": _utc_now(),
            "metadata": _jsonable(dict(metadata or {})),
        }
        self.store.tenants[tenant_id] = record
        return _copy(record)

    def create_project(self, tenant_id: str, name: str, *, project_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> JsonDict:
        tenant = self.get_tenant(tenant_id)
        project_id = project_id or _new_id("project")
        _require_id(project_id, "project_id")
        if project_id in self.store.projects:
            raise ValidationError(f"project already exists: {project_id}")
        record = {
            "schema_version": CLOUD_API_SCHEMA_VERSION,
            "tenant_id": tenant["tenant_id"],
            "project_id": project_id,
            "name": _require_text(name, "name"),
            "created_at": _utc_now(),
            "metadata": _jsonable(dict(metadata or {})),
        }
        self.store.projects[project_id] = record
        self.quota.configure(tenant["tenant_id"], project_id, {})
        return _copy(record)

    def get_tenant(self, tenant_id: str) -> JsonDict:
        try:
            return _copy(self.store.tenants[str(tenant_id)])
        except KeyError as exc:
            raise NotFoundError("tenant not found") from exc

    def get_project(self, tenant_id: str, project_id: str) -> JsonDict:
        project = self.store.projects.get(str(project_id))
        if not project or project.get("tenant_id") != str(tenant_id):
            raise NotFoundError("project not found for tenant")
        return _copy(project)

    def create_dataset(
        self,
        tenant_id: str,
        project_id: str,
        *,
        name: str,
        cases: Iterable[Mapping[str, Any]],
        dataset_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        project = self.get_project(tenant_id, project_id)
        cases_payload = [_jsonable(case) for case in cases]
        if not cases_payload:
            raise ValidationError("dataset cases must not be empty")
        dataset_name = _require_text(name, "name")
        self.quota.check(project["tenant_id"], project["project_id"], "dataset.create")
        dataset_id = dataset_id or _new_id("dataset")
        _require_id(dataset_id, "dataset_id")
        if dataset_id in self.store.datasets:
            raise ValidationError(f"dataset already exists: {dataset_id}")
        self.quota.consume(project["tenant_id"], project["project_id"], "dataset.create")
        record = {
            "schema_version": CLOUD_API_SCHEMA_VERSION,
            "tenant_id": project["tenant_id"],
            "project_id": project["project_id"],
            "dataset_id": dataset_id,
            "name": dataset_name,
            "case_count": len(cases_payload),
            "cases": cases_payload,
            "created_at": _utc_now(),
            "metadata": _jsonable(dict(metadata or {})),
        }
        self.store.datasets[dataset_id] = record
        return _copy(record)

    def get_dataset(self, tenant_id: str, project_id: str, dataset_id: str) -> JsonDict:
        dataset = self.store.datasets.get(str(dataset_id))
        if not dataset or dataset.get("tenant_id") != str(tenant_id) or dataset.get("project_id") != str(project_id):
            raise NotFoundError("dataset not found for tenant/project")
        return _copy(dataset)

    def list_datasets(self, tenant_id: str, project_id: str) -> list[JsonDict]:
        self.get_project(tenant_id, project_id)
        return [
            _copy(dataset)
            for dataset in self.store.datasets.values()
            if dataset.get("tenant_id") == str(tenant_id) and dataset.get("project_id") == str(project_id)
        ]

    def create_request(
        self,
        tenant_id: str,
        project_id: str,
        *,
        name: str,
        request_input_schema: Mapping[str, Any] | None = None,
        accepted_inputs: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        project = self.get_project(tenant_id, project_id)
        request_name = _require_text(name, "name")
        self.quota.check(project["tenant_id"], project["project_id"], "request.create")
        request_id = request_id or _new_id("request")
        _require_id(request_id, "request_id")
        if request_id in self.store.requests:
            raise ValidationError(f"request already exists: {request_id}")
        self.quota.consume(project["tenant_id"], project["project_id"], "request.create")
        record = {
            "schema_version": CLOUD_API_SCHEMA_VERSION,
            "tenant_id": project["tenant_id"],
            "project_id": project["project_id"],
            "request_id": request_id,
            "name": request_name,
            "status": "created",
            "request_input_schema": _jsonable(dict(request_input_schema or {})),
            "accepted_inputs": _jsonable(dict(accepted_inputs or {"text": True})),
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "metadata": _jsonable(dict(metadata or {})),
        }
        self.store.requests[request_id] = record
        return _copy(record)

    def get_request(self, tenant_id: str, project_id: str, request_id: str) -> JsonDict:
        request = self.store.requests.get(str(request_id))
        if not request or request.get("tenant_id") != str(tenant_id) or request.get("project_id") != str(project_id):
            raise NotFoundError("request not found for tenant/project")
        return _copy(request)

    def list_requests(self, tenant_id: str, project_id: str) -> list[JsonDict]:
        self.get_project(tenant_id, project_id)
        return [
            _copy(request)
            for request in self.store.requests.values()
            if request.get("tenant_id") == str(tenant_id) and request.get("project_id") == str(project_id)
        ]

    def submit_run(
        self,
        tenant_id: str,
        project_id: str,
        *,
        dataset_id: str,
        run_result: Mapping[str, Any],
        run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        dataset = self.get_dataset(tenant_id, project_id, dataset_id)
        result_payload = _jsonable(dict(run_result))
        observations = _extract_observations(result_payload)
        self.quota.check(dataset["tenant_id"], dataset["project_id"], "run.submit")
        self.quota.check(dataset["tenant_id"], dataset["project_id"], "observation.write", units=max(1, len(observations)))
        run_id = run_id or str(result_payload.get("run_id") or _new_id("run"))
        _require_id(run_id, "run_id")
        if run_id in self.store.runs:
            raise ValidationError(f"run already exists: {run_id}")
        self.quota.consume(dataset["tenant_id"], dataset["project_id"], "run.submit")
        self.quota.consume(dataset["tenant_id"], dataset["project_id"], "observation.write", units=max(1, len(observations)))
        now = _utc_now()
        record = {
            "schema_version": CLOUD_API_SCHEMA_VERSION,
            "tenant_id": dataset["tenant_id"],
            "project_id": dataset["project_id"],
            "dataset_id": dataset["dataset_id"],
            "run_id": run_id,
            "status": _cloud_run_status(result_payload),
            "result_status": str(result_payload.get("status") or ""),
            "runner_id": str(result_payload.get("runner_id") or "a1-local-runner"),
            "total_cases": int(result_payload.get("total_cases") or len(result_payload.get("cases") or [])),
            "observations": observations,
            "result": result_payload,
            "created_at": now,
            "updated_at": now,
            "status_history": [{"status": _cloud_run_status(result_payload), "at": now}],
            "metadata": _jsonable(dict(metadata or {})),
        }
        self.store.runs[run_id] = record
        return _copy(record)

    def create_queued_run(
        self,
        tenant_id: str,
        project_id: str,
        *,
        dataset_id: str,
        runner_id: str = "a1-local-queue-worker",
        run_id: str | None = None,
        max_attempts: int = DEFAULT_QUEUE_MAX_ATTEMPTS,
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        dataset = self.get_dataset(tenant_id, project_id, dataset_id)
        with self._lock:
            self.quota.check(dataset["tenant_id"], dataset["project_id"], "run.submit")
            run_id = run_id or _new_id("run")
            _require_id(run_id, "run_id")
            if run_id in self.store.runs:
                raise ValidationError(f"run already exists: {run_id}")
            self.quota.consume(dataset["tenant_id"], dataset["project_id"], "run.submit")
            now = _utc_now()
            normalized_max_attempts = _normalize_max_attempts(max_attempts)
            result = {
                "schema_version": "releasefoundry.run_result.v1",
                "run_id": run_id,
                "dataset_id": dataset["dataset_id"],
                "runner_id": str(runner_id),
                "status": "queued",
                "total_cases": dataset["case_count"],
                "passed": 0,
                "failed": 0,
                "errored": 0,
                "timed_out": 0,
                "cases": [],
                "metadata": {"local_only": True, "releasefoundry_api_used": False, "queued": True},
            }
            record = {
                "schema_version": CLOUD_API_SCHEMA_VERSION,
                "tenant_id": dataset["tenant_id"],
                "project_id": dataset["project_id"],
                "dataset_id": dataset["dataset_id"],
                "run_id": run_id,
                "status": "queued",
                "result_status": "queued",
                "runner_id": str(runner_id),
                "total_cases": dataset["case_count"],
                "observations": [],
                "result": _jsonable(result),
                "created_at": now,
                "updated_at": now,
                "lease_owner_id": None,
                "lease_expires_at": None,
                "lease_heartbeat_at": None,
                "lease_reclaim_count": 0,
                "attempt": 0,
                "max_attempts": normalized_max_attempts,
                "last_error": None,
                "dead_letter_reason": None,
                "status_history": [{"status": "queued", "at": now}],
                "metadata": _jsonable(dict(metadata or {})),
            }
            self.store.runs[run_id] = record
            return _copy(record)

    def mark_run_running(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        lease_owner_id: str | None = None,
        lease_seconds: float | None = DEFAULT_QUEUE_LEASE_SECONDS,
        reclaim_expired: bool = False,
    ) -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") == "cancelled":
                return _copy(run)
            if run.get("status") == "dead_lettered":
                return _copy(run)
            if run.get("status") not in {"queued", "submitted", "running"}:
                raise ValidationError(f"run cannot transition to running from {run.get('status')}")
            now = _utc_now()
            self._claim_or_validate_run_lease(
                run,
                lease_owner_id=lease_owner_id,
                lease_seconds=lease_seconds,
                now=now,
                reclaim_expired=reclaim_expired,
            )
            run["status"] = "running"
            run["result_status"] = "running"
            if run.get("status_history") and isinstance(run.get("status_history"), list):
                last_status = run["status_history"][-1].get("status") if isinstance(run["status_history"][-1], Mapping) else None
            else:
                last_status = None
            if last_status != "running":
                run["attempt"] = int(run.get("attempt") or 0) + 1
            run["updated_at"] = now
            if isinstance(run.get("result"), dict):
                run["result"]["status"] = "running"
            _append_status_history(run, "running", now)
            return _copy(run)

    def heartbeat_run(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        lease_owner_id: str,
        lease_seconds: float | None = DEFAULT_QUEUE_LEASE_SECONDS,
    ) -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") not in {"queued", "submitted", "running"}:
                raise ValidationError(f"run cannot heartbeat from {run.get('status')}")
            self._require_run_lease_owner(run, lease_owner_id)
            now = _utc_now()
            if lease_seconds is None:
                raise ValidationError("lease_seconds is required when renewing a run lease")
            run["lease_heartbeat_at"] = now
            run["lease_expires_at"] = _lease_expires_at(now, lease_seconds)
            run["updated_at"] = now
            return _copy(run)

    def reclaim_expired_run_leases(
        self,
        tenant_id: str,
        project_id: str,
        *,
        dataset_id: str | None = None,
        statuses: Iterable[str] = ("queued", "running", "submitted"),
        now: str | None = None,
    ) -> list[JsonDict]:
        self.get_project(tenant_id, project_id)
        reclaim_statuses = {str(status) for status in statuses}
        reclaimed: list[JsonDict] = []
        with self._lock:
            for run in self.store.runs.values():
                if run.get("tenant_id") != str(tenant_id) or run.get("project_id") != str(project_id):
                    continue
                if dataset_id is not None and run.get("dataset_id") != str(dataset_id):
                    continue
                if run.get("status") not in reclaim_statuses:
                    continue
                if run.get("lease_owner_id") is None or not _lease_expired(run.get("lease_expires_at"), now=now):
                    continue
                run["lease_owner_id"] = None
                run["lease_expires_at"] = None
                run["lease_heartbeat_at"] = None
                run["lease_reclaim_count"] = int(run.get("lease_reclaim_count") or 0) + 1
                if run.get("status") == "running":
                    run["status"] = "queued"
                    run["result_status"] = "queued"
                    if isinstance(run.get("result"), dict):
                        run["result"]["status"] = "queued"
                    _append_status_history(run, "queued", now or _utc_now())
                run["updated_at"] = now or _utc_now()
                reclaimed.append(_copy(run))
        return reclaimed

    def complete_run(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        run_result: Mapping[str, Any],
        *,
        lease_owner_id: str | None = None,
    ) -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") == "cancelled":
                return _copy(run)
            if run.get("status") == "dead_lettered":
                return _copy(run)
            if run.get("status") not in {"queued", "running", "submitted"}:
                raise ValidationError(f"run cannot complete from {run.get('status')}")
            if run.get("lease_owner_id") is not None and lease_owner_id is None:
                raise ValidationError("run lease owner is required for leased run")
            if lease_owner_id is not None:
                self._require_run_lease_owner(run, lease_owner_id)
            result_payload = _jsonable(dict(run_result))
            next_status = _cloud_run_status(result_payload)
            if next_status not in {"completed", "failed", "cancelled"}:
                raise ValidationError(f"run completion requires a terminal status, got {next_status}")
            observations = _extract_observations(result_payload)
            self.quota.check(str(tenant_id), str(project_id), "observation.write", units=max(1, len(observations)))
            self.quota.consume(str(tenant_id), str(project_id), "observation.write", units=max(1, len(observations)))
            now = _utc_now()
            run["status"] = next_status
            run["result_status"] = str(result_payload.get("status") or "")
            run["runner_id"] = str(result_payload.get("runner_id") or run.get("runner_id") or "a1-local-runner")
            run["total_cases"] = int(result_payload.get("total_cases") or len(result_payload.get("cases") or []))
            run["observations"] = observations
            run["result"] = result_payload
            if next_status == "failed":
                error = result_payload.get("error") if isinstance(result_payload.get("error"), Mapping) else None
                run["last_error"] = _jsonable(dict(error)) if error is not None else {"type": "RunFailed", "message": "run result status failed"}
            run["updated_at"] = now
            self._clear_run_lease(run)
            _append_status_history(run, run["status"], now)
            return _copy(run)

    def fail_run(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        error: Mapping[str, Any],
        result_status: str = "error",
        lease_owner_id: str | None = None,
    ) -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") == "cancelled":
                return _copy(run)
            if run.get("status") == "dead_lettered":
                return _copy(run)
            if run.get("lease_owner_id") is not None and lease_owner_id is None:
                raise ValidationError("run lease owner is required for leased run")
            if lease_owner_id is not None:
                self._require_run_lease_owner(run, lease_owner_id)
            now = _utc_now()
            error_payload = _jsonable(dict(error))
            run["status"] = "failed"
            run["result_status"] = str(result_status)
            run["updated_at"] = now
            run["observations"] = []
            run["result"] = {
                "schema_version": "releasefoundry.run_result.v1",
                "run_id": run["run_id"],
                "dataset_id": run["dataset_id"],
                "runner_id": run["runner_id"],
                "status": result_status,
                "total_cases": run["total_cases"],
                "passed": 0,
                "failed": 0,
                "errored": run["total_cases"],
                "timed_out": 0,
                "cases": [],
                "error": error_payload,
                "metadata": {"local_only": True, "releasefoundry_api_used": False, "queued": True},
            }
            run["error"] = error_payload
            run["last_error"] = error_payload
            self._clear_run_lease(run)
            _append_status_history(run, "failed", now)
            return _copy(run)

    def retry_run(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        reason: str = "retry scheduled",
        metadata: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") != "failed":
                raise ValidationError(f"run cannot be retried from {run.get('status')}")
            if not _run_has_retry_capacity(run):
                return self.dead_letter_run(tenant_id, project_id, run_id, reason="max attempts exhausted")
            now = _utc_now()
            run["status"] = "queued"
            run["result_status"] = "queued"
            run["updated_at"] = now
            self._clear_run_lease(run)
            if isinstance(run.get("metadata"), dict):
                run["metadata"].update(_jsonable(dict(metadata or {})))
                run["metadata"]["retry_reason"] = str(reason)
            else:
                run["metadata"] = {"retry_reason": str(reason), **_jsonable(dict(metadata or {}))}
            if isinstance(run.get("result"), dict):
                run["result"]["status"] = "queued"
            _append_status_history(run, "queued", now)
            return _copy(run)

    def dead_letter_run(self, tenant_id: str, project_id: str, run_id: str, *, reason: str = "max attempts exhausted") -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") == "dead_lettered":
                return _copy(run)
            if run.get("status") in {"completed", "cancelled"}:
                raise ValidationError(f"run cannot be dead-lettered from {run.get('status')}")
            now = _utc_now()
            run["status"] = "dead_lettered"
            run["result_status"] = "dead_lettered"
            run["updated_at"] = now
            run["dead_letter_reason"] = str(reason)
            self._clear_run_lease(run)
            if isinstance(run.get("result"), dict):
                run["result"]["status"] = "dead_lettered"
                run["result"]["dead_letter_reason"] = str(reason)
            _append_status_history(run, "dead_lettered", now)
            return _copy(run)

    def cancel_run(self, tenant_id: str, project_id: str, run_id: str, *, reason: str = "cancelled") -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") in {"completed", "failed", "dead_lettered"}:
                raise ValidationError(f"run cannot be cancelled from {run.get('status')}")
            now = _utc_now()
            run["status"] = "cancelled"
            run["result_status"] = "cancelled"
            run["updated_at"] = now
            run["error"] = {"type": "Cancelled", "message": str(reason)}
            self._clear_run_lease(run)
            if isinstance(run.get("result"), dict):
                run["result"]["status"] = "cancelled"
                run["result"]["error"] = run["error"]
            _append_status_history(run, "cancelled", now)
            return _copy(run)

    def append_observation(self, tenant_id: str, project_id: str, run_id: str, observation: Mapping[str, Any]) -> JsonDict:
        run = self._get_run_record(tenant_id, project_id, run_id)
        self.quota.consume(str(tenant_id), str(project_id), "observation.write")
        payload = _jsonable(dict(observation))
        run["observations"].append(payload)
        run["updated_at"] = _utc_now()
        return _copy(payload)

    def get_run(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        return _copy(self._get_run_record(tenant_id, project_id, run_id))

    def list_runs(self, tenant_id: str, project_id: str, *, dataset_id: str | None = None) -> list[JsonDict]:
        self.get_project(tenant_id, project_id)
        return [
            _copy(run)
            for run in self.store.runs.values()
            if run.get("tenant_id") == str(tenant_id)
            and run.get("project_id") == str(project_id)
            and (dataset_id is None or run.get("dataset_id") == str(dataset_id))
        ]

    def poll_run(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        run = self.get_run(tenant_id, project_id, run_id)
        return {
            "schema_version": CLOUD_API_SCHEMA_VERSION,
            "tenant_id": run["tenant_id"],
            "project_id": run["project_id"],
            "run_id": run["run_id"],
            "status": run["status"],
            "updated_at": run["updated_at"],
            "run": run,
        }

    def quota_snapshot(self, tenant_id: str, project_id: str) -> JsonDict:
        self.get_project(tenant_id, project_id)
        return self.quota.snapshot(tenant_id, project_id)

    def export_run_fixture(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        run = self.get_run(tenant_id, project_id, run_id)
        return {
            "schema_version": CLOUD_API_SCHEMA_VERSION,
            "tenant_id": run["tenant_id"],
            "project_id": run["project_id"],
            "dataset_id": run["dataset_id"],
            "run_id": run["run_id"],
            "status": run["status"],
            "run_result": run["result"],
            "observations": run["observations"],
            "metadata": {"local_only": True, "releasefoundry_api_used": False},
        }

    def write_run_fixture(self, tenant_id: str, project_id: str, run_id: str, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.export_run_fixture(tenant_id, project_id, run_id), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return path

    def snapshot_state(self) -> JsonDict:
        with self._lock:
            return {
                "schema_version": CLOUD_API_SCHEMA_VERSION,
                "state_version": 1,
                "kind": "local_cloud_state",
                "store": self.store.snapshot(),
                "quota": _quota_state(self.quota),
                "metadata": {"local_only": True, "releasefoundry_api_used": False},
            }

    def write_state(self, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.snapshot_state(), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return path

    @classmethod
    def from_state(cls, payload: Mapping[str, Any]) -> CloudApiService:
        if not isinstance(payload, Mapping):
            raise ValidationError("cloud state payload must be a JSON object")
        return cls(store=_store_from_state(payload), quota=_quota_from_state(payload.get("quota", {})))

    @classmethod
    def from_state_file(cls, input_path: str | Path) -> CloudApiService:
        return cls.from_state(json.loads(Path(input_path).read_text(encoding="utf-8")))

    def _get_run_record(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        run = self.store.runs.get(str(run_id))
        if not run or run.get("tenant_id") != str(tenant_id) or run.get("project_id") != str(project_id):
            raise NotFoundError("run not found for tenant/project")
        return run

    def _claim_or_validate_run_lease(
        self,
        run: JsonDict,
        *,
        lease_owner_id: str | None,
        lease_seconds: float | None,
        now: str,
        reclaim_expired: bool,
    ) -> None:
        current_owner = run.get("lease_owner_id")
        if lease_owner_id is None:
            if current_owner is not None:
                raise ValidationError("run lease owner is required for leased run")
            return
        owner = _require_text(str(lease_owner_id), "lease_owner_id")
        if lease_seconds is None:
            raise ValidationError("lease_seconds is required when claiming a run lease")
        if current_owner not in {None, owner}:
            if not (reclaim_expired and _lease_expired(run.get("lease_expires_at"), now=now)):
                raise ValidationError("run is leased by another worker")
            run["lease_reclaim_count"] = int(run.get("lease_reclaim_count") or 0) + 1
        run["lease_owner_id"] = owner
        run["lease_heartbeat_at"] = now
        run["lease_expires_at"] = _lease_expires_at(now, lease_seconds)

    def _require_run_lease_owner(self, run: JsonDict, lease_owner_id: str) -> None:
        owner = _require_text(str(lease_owner_id), "lease_owner_id")
        if run.get("lease_owner_id") != owner:
            raise ValidationError("run lease is not owned by this worker")

    @staticmethod
    def _clear_run_lease(run: JsonDict) -> None:
        run["lease_owner_id"] = None
        run["lease_expires_at"] = None
        run["lease_heartbeat_at"] = None


def _extract_observations(run_result: Mapping[str, Any]) -> list[JsonDict]:
    observations: list[JsonDict] = []
    for case in run_result.get("cases") or []:
        if isinstance(case, Mapping):
            for observation in case.get("observations") or []:
                if isinstance(observation, Mapping):
                    observations.append(_jsonable(dict(observation)))
    return observations


def _cloud_run_status(run_result: Mapping[str, Any]) -> str:
    status = str(run_result.get("status") or "").lower()
    if status in {"queued", "running", "completed", "failed", "cancelled", "dead_lettered"}:
        return status
    if run_result.get("ended_at") and isinstance(run_result.get("cases"), list):
        return "completed"
    return "submitted"


def _normalize_max_attempts(max_attempts: int) -> int:
    parsed = int(max_attempts)
    if parsed < 1:
        raise ValidationError("max_attempts must be positive")
    return parsed


def _run_has_retry_capacity(run: Mapping[str, Any]) -> bool:
    attempt = int(run.get("attempt") or 0)
    max_attempts = _normalize_max_attempts(int(run.get("max_attempts") or DEFAULT_QUEUE_MAX_ATTEMPTS))
    return attempt < max_attempts


def _append_status_history(run: JsonDict, status: str, at: str) -> None:
    history = run.setdefault("status_history", [])
    if not isinstance(history, list):
        history = []
        run["status_history"] = history
    if history and isinstance(history[-1], Mapping) and history[-1].get("status") == status:
        history[-1]["at"] = at
        return
    history.append({"status": status, "at": at})


def _quota_state(quota: QuotaLedger) -> JsonDict:
    project_keys = set(quota.limits) | set(quota.used)
    return _jsonable(
        {
            "default_limits": dict(quota.default_limits),
            "projects": [
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "limits": dict(quota.limits.get((tenant_id, project_id), {})),
                    "used": dict(quota.used.get((tenant_id, project_id), {})),
                }
                for tenant_id, project_id in sorted(project_keys)
            ],
        }
    )


def _quota_from_state(payload: Any) -> QuotaLedger:
    if not isinstance(payload, Mapping):
        return QuotaLedger()
    default_limits = payload.get("default_limits")
    ledger = QuotaLedger(default_limits=dict(default_limits) if isinstance(default_limits, Mapping) else dict(DEFAULT_QUOTA_LIMITS))
    projects = payload.get("projects") or []
    if not isinstance(projects, list):
        raise ValidationError("quota projects must be a list")
    for entry in projects:
        if not isinstance(entry, Mapping):
            raise ValidationError("quota project entries must be objects")
        tenant_id = str(entry.get("tenant_id") or "")
        project_id = str(entry.get("project_id") or "")
        _require_id(tenant_id, "tenant_id")
        _require_id(project_id, "project_id")
        key = (tenant_id, project_id)
        limits = entry.get("limits") or {}
        used = entry.get("used") or {}
        if not isinstance(limits, Mapping) or not isinstance(used, Mapping):
            raise ValidationError("quota limits and used values must be objects")
        ledger.limits[key] = {str(operation): int(limit) for operation, limit in limits.items()}
        ledger.used[key] = {str(operation): int(units) for operation, units in used.items()}
    return ledger


def _store_from_state(payload: Mapping[str, Any]) -> InMemoryCloudStore:
    store_payload = payload.get("store", payload)
    if not isinstance(store_payload, Mapping):
        raise ValidationError("cloud state store must be a JSON object")
    return InMemoryCloudStore(
        tenants=_state_bucket(store_payload, "tenants"),
        projects=_state_bucket(store_payload, "projects"),
        datasets=_state_bucket(store_payload, "datasets"),
        requests=_state_bucket(store_payload, "requests"),
        runs=_state_bucket(store_payload, "runs"),
    )


def _state_bucket(payload: Mapping[str, Any], key: str) -> dict[str, JsonDict]:
    bucket = payload.get(key) or {}
    if not isinstance(bucket, Mapping):
        raise ValidationError(f"cloud state {key} must be an object")
    records: dict[str, JsonDict] = {}
    for item_key, item_value in bucket.items():
        if not isinstance(item_value, Mapping):
            raise ValidationError(f"cloud state {key} records must be objects")
        records[str(item_key)] = _jsonable(dict(item_value))
    return records


def _positive_units(units: int) -> int:
    parsed = int(units)
    if parsed <= 0:
        raise ValidationError("quota units must be positive")
    return parsed


def _require_id(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    return value


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _lease_expires_at(now: str, lease_seconds: float | None) -> str | None:
    if lease_seconds is None:
        return None
    seconds = float(lease_seconds)
    if seconds <= 0:
        raise ValidationError("lease_seconds must be positive")
    parsed_now = _parse_utc(now) or datetime.now(timezone.utc)
    return (parsed_now + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _lease_expired(expires_at: Any, *, now: str | None = None) -> bool:
    parsed_expires_at = _parse_utc(expires_at)
    if parsed_expires_at is None:
        return False
    parsed_now = _parse_utc(now) if now is not None else datetime.now(timezone.utc)
    if parsed_now is None:
        parsed_now = datetime.now(timezone.utc)
    return parsed_expires_at <= parsed_now


def _copy(value: Any) -> Any:
    return copy.deepcopy(_jsonable(value))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=repr)]
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value
