from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Iterable, Mapping
from uuid import uuid4

CLOUD_API_SCHEMA_VERSION = "ashr.clone.cloud_api.v1"

JsonDict = dict[str, Any]

DEFAULT_QUOTA_LIMITS: dict[str, int] = {
    "dataset.create": 1_000,
    "observation.write": 100_000,
    "request.create": 1_000,
    "run.submit": 10_000,
}


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
            result = {
                "schema_version": "ashr.clone.run_result.v1",
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
                "metadata": {"local_only": True, "ashr_api_used": False, "queued": True},
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
                "status_history": [{"status": "queued", "at": now}],
                "metadata": _jsonable(dict(metadata or {})),
            }
            self.store.runs[run_id] = record
            return _copy(record)

    def mark_run_running(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") == "cancelled":
                return _copy(run)
            if run.get("status") not in {"queued", "submitted", "running"}:
                raise ValidationError(f"run cannot transition to running from {run.get('status')}")
            now = _utc_now()
            run["status"] = "running"
            run["result_status"] = "running"
            run["updated_at"] = now
            if isinstance(run.get("result"), dict):
                run["result"]["status"] = "running"
            _append_status_history(run, "running", now)
            return _copy(run)

    def complete_run(self, tenant_id: str, project_id: str, run_id: str, run_result: Mapping[str, Any]) -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") == "cancelled":
                return _copy(run)
            if run.get("status") not in {"queued", "running", "submitted"}:
                raise ValidationError(f"run cannot complete from {run.get('status')}")
            result_payload = _jsonable(dict(run_result))
            observations = _extract_observations(result_payload)
            self.quota.check(str(tenant_id), str(project_id), "observation.write", units=max(1, len(observations)))
            self.quota.consume(str(tenant_id), str(project_id), "observation.write", units=max(1, len(observations)))
            now = _utc_now()
            run["status"] = _cloud_run_status(result_payload)
            run["result_status"] = str(result_payload.get("status") or "")
            run["runner_id"] = str(result_payload.get("runner_id") or run.get("runner_id") or "a1-local-runner")
            run["total_cases"] = int(result_payload.get("total_cases") or len(result_payload.get("cases") or []))
            run["observations"] = observations
            run["result"] = result_payload
            run["updated_at"] = now
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
    ) -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") == "cancelled":
                return _copy(run)
            now = _utc_now()
            error_payload = _jsonable(dict(error))
            run["status"] = "failed"
            run["result_status"] = str(result_status)
            run["updated_at"] = now
            run["observations"] = []
            run["result"] = {
                "schema_version": "ashr.clone.run_result.v1",
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
                "metadata": {"local_only": True, "ashr_api_used": False, "queued": True},
            }
            run["error"] = error_payload
            _append_status_history(run, "failed", now)
            return _copy(run)

    def cancel_run(self, tenant_id: str, project_id: str, run_id: str, *, reason: str = "cancelled") -> JsonDict:
        with self._lock:
            run = self._get_run_record(tenant_id, project_id, run_id)
            if run.get("status") in {"completed", "failed"}:
                raise ValidationError(f"run cannot be cancelled from {run.get('status')}")
            now = _utc_now()
            run["status"] = "cancelled"
            run["result_status"] = "cancelled"
            run["updated_at"] = now
            run["error"] = {"type": "Cancelled", "message": str(reason)}
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
            "metadata": {"local_only": True, "ashr_api_used": False},
        }

    def write_run_fixture(self, tenant_id: str, project_id: str, run_id: str, output_path: str | Path) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.export_run_fixture(tenant_id, project_id, run_id), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return path

    def _get_run_record(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        run = self.store.runs.get(str(run_id))
        if not run or run.get("tenant_id") != str(tenant_id) or run.get("project_id") != str(project_id):
            raise NotFoundError("run not found for tenant/project")
        return run


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
    if status in {"queued", "running", "completed", "failed", "cancelled"}:
        return status
    if run_result.get("ended_at") and isinstance(run_result.get("cases"), list):
        return "completed"
    return "submitted"


def _append_status_history(run: JsonDict, status: str, at: str) -> None:
    history = run.setdefault("status_history", [])
    if not isinstance(history, list):
        history = []
        run["status_history"] = history
    if history and isinstance(history[-1], Mapping) and history[-1].get("status") == status:
        history[-1]["at"] = at
        return
    history.append({"status": status, "at": at})


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
