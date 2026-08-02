from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import Any, Iterable, Iterator, Mapping

from packages.sdk.releasefoundry.api_client import redact_text
from services.runner.runner import DEFAULT_MAX_WORKERS, DEFAULT_TIMEOUT_SECONDS, normalize_max_workers, normalize_timeout_seconds, run_agent_batch

from .runtime import DEFAULT_QUEUE_LEASE_SECONDS, DEFAULT_QUEUE_MAX_ATTEMPTS, TERMINAL_RUN_STATUSES, CloudApiService, JsonDict, NotFoundError, ValidationError
MIN_HEARTBEAT_INTERVAL_SECONDS = 0.05



@dataclass(frozen=True, slots=True)
class QueueRunRequest:
    tenant_id: str
    project_id: str
    dataset_id: str
    agent: Any
    runner_id: str = "a1-local-queue-worker"
    run_id: str | None = None
    max_workers: int | None = DEFAULT_MAX_WORKERS
    timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS
    lease_owner_id: str | None = None
    lease_seconds: float | None = DEFAULT_QUEUE_LEASE_SECONDS
    max_attempts: int = DEFAULT_QUEUE_MAX_ATTEMPTS
    metadata: Mapping[str, Any] | None = None


class CloudQueueWorker:
    """Local queue facade that drives queued runs through CloudApiService."""

    def __init__(self, service: CloudApiService | None = None, *, queue_workers: int | None = DEFAULT_MAX_WORKERS) -> None:
        self.service = service or CloudApiService()
        self.queue_workers = normalize_max_workers(queue_workers)
        self._executor = ThreadPoolExecutor(max_workers=self.queue_workers, thread_name_prefix="a1-cloud-queue")
        self._futures: dict[str, Future[JsonDict]] = {}

    def enqueue_agent_run(self, request: QueueRunRequest) -> JsonDict:
        runner_workers = normalize_max_workers(request.max_workers)
        timeout_seconds = normalize_timeout_seconds(request.timeout_seconds)
        queued = self.service.create_queued_run(
            request.tenant_id,
            request.project_id,
            dataset_id=request.dataset_id,
            runner_id=request.runner_id,
            run_id=request.run_id,
            max_attempts=request.max_attempts,
            metadata=self._execution_metadata(request, runner_workers=runner_workers),
        )
        normalized = QueueRunRequest(
            tenant_id=request.tenant_id,
            project_id=request.project_id,
            dataset_id=request.dataset_id,
            agent=request.agent,
            runner_id=request.runner_id,
            run_id=queued["run_id"],
            max_workers=runner_workers,
            timeout_seconds=timeout_seconds,
            lease_owner_id=request.lease_owner_id or self._lease_owner_id(queued["run_id"]),
            lease_seconds=request.lease_seconds,
            max_attempts=request.max_attempts,
            metadata=request.metadata,
        )
        self._futures[queued["run_id"]] = self._executor.submit(self._execute, normalized)
        return queued

    def poll_run(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        return self.service.poll_run(tenant_id, project_id, run_id)

    def replay_incomplete_runs(
        self,
        tenant_id: str,
        project_id: str,
        *,
        agent: Any,
        dataset_id: str | None = None,
        statuses: Iterable[str] = ("queued", "running", "failed"),
        max_runs: int = 100,
        max_workers: int | None = DEFAULT_MAX_WORKERS,
        timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
        lease_seconds: float | None = DEFAULT_QUEUE_LEASE_SECONDS,
        metadata: Mapping[str, Any] | None = None,
    ) -> list[JsonDict]:
        replay_statuses = {str(status) for status in statuses}
        if not replay_statuses:
            raise ValidationError("replay statuses must not be empty")
        unsupported = replay_statuses - {"queued", "running", "failed"}
        if unsupported:
            raise ValidationError(f"unsupported replay statuses: {', '.join(sorted(unsupported))}")
        limit = _normalize_replay_limit(max_runs)
        runner_workers = normalize_max_workers(max_workers)
        normalized_timeout = normalize_timeout_seconds(timeout_seconds)
        self.service.reclaim_expired_run_leases(tenant_id, project_id, dataset_id=dataset_id, statuses=replay_statuses)
        candidates = sorted(self.service.list_runs(tenant_id, project_id, dataset_id=dataset_id), key=_replay_order_key)
        replayed: list[JsonDict] = []
        for run in candidates:
            if len(replayed) >= limit:
                break
            if run.get("status") not in replay_statuses:
                continue
            if run.get("lease_owner_id") is not None:
                continue
            run_id = str(run["run_id"])
            if run.get("status") == "failed":
                run = self.service.retry_run(
                    str(run["tenant_id"]),
                    str(run["project_id"]),
                    run_id,
                    reason="worker replay",
                    metadata=metadata,
                )
                if run.get("status") == "dead_lettered":
                    replayed.append(run)
                    continue
            future = self._futures.get(run_id)
            if future is not None and not future.done():
                continue
            request = QueueRunRequest(
                tenant_id=str(run["tenant_id"]),
                project_id=str(run["project_id"]),
                dataset_id=str(run["dataset_id"]),
                agent=agent,
                runner_id=str(run.get("runner_id") or "a1-local-queue-worker"),
                run_id=run_id,
                max_workers=runner_workers,
                timeout_seconds=normalized_timeout,
                lease_owner_id=self._lease_owner_id(run_id),
                lease_seconds=lease_seconds,
                max_attempts=int(run.get("max_attempts") or DEFAULT_QUEUE_MAX_ATTEMPTS),
                metadata=metadata,
            )
            self._futures[run_id] = self._executor.submit(self._execute, request)
            replayed.append(run)
        return replayed

    def wait_for_run(
        self,
        tenant_id: str,
        project_id: str,
        run_id: str,
        *,
        timeout_seconds: float | None = None,
        require_terminal: bool = False,
    ) -> JsonDict:
        future = self._futures.get(str(run_id))
        if future is None:
            raise NotFoundError("queued run future not found")
        poll = self.service.poll_run(tenant_id, project_id, run_id)
        if poll["status"] in TERMINAL_RUN_STATUSES:
            return poll
        try:
            future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            poll = self.service.poll_run(tenant_id, project_id, run_id)
            if poll["status"] in TERMINAL_RUN_STATUSES:
                return poll
            if require_terminal:
                raise TimeoutError(f"queued run {run_id} did not reach a terminal status before timeout; current status={poll['status']}") from exc
            return poll
        except CancelledError as exc:
            poll = self.service.poll_run(tenant_id, project_id, run_id)
            if poll["status"] in TERMINAL_RUN_STATUSES:
                return poll
            if require_terminal:
                raise TimeoutError(f"queued run {run_id} future was cancelled before reaching a terminal status; current status={poll['status']}") from exc
            return poll
        poll = self.service.poll_run(tenant_id, project_id, run_id)
        if require_terminal and poll["status"] not in TERMINAL_RUN_STATUSES:
            raise TimeoutError(f"queued run {run_id} did not reach a terminal status; current status={poll['status']}")
        return poll

    def cancel_run(self, tenant_id: str, project_id: str, run_id: str, *, reason: str = "cancelled") -> JsonDict:
        future = self._futures.get(str(run_id))
        if future is not None:
            future.cancel()
        return self.service.cancel_run(tenant_id, project_id, run_id, reason=reason)

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def __enter__(self) -> CloudQueueWorker:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.shutdown(wait=exc_type is None)

    def _execute(self, request: QueueRunRequest) -> JsonDict:
        run_id = str(request.run_id)
        lease_owner_id = request.lease_owner_id or self._lease_owner_id(run_id)
        try:
            running = self.service.mark_run_running(
                request.tenant_id,
                request.project_id,
                run_id,
                lease_owner_id=lease_owner_id,
                lease_seconds=request.lease_seconds,
                reclaim_expired=True,
            )
            if running.get("status") == "cancelled":
                return running
            self._merge_execution_metadata(request)
            dataset = self.service.get_dataset(request.tenant_id, request.project_id, request.dataset_id)
            self.service.heartbeat_run(
                request.tenant_id,
                request.project_id,
                run_id,
                lease_owner_id=lease_owner_id,
                lease_seconds=request.lease_seconds,
            )
            with self._lease_renewer(request, lease_owner_id):
                result = run_agent_batch(
                    request.agent,
                    dataset["cases"],
                    dataset_id=dataset["dataset_id"],
                    runner_id=request.runner_id,
                    max_workers=request.max_workers,
                    timeout_seconds=request.timeout_seconds,
                    run_id=run_id,
                )
            return self.service.complete_run(request.tenant_id, request.project_id, run_id, result, lease_owner_id=lease_owner_id)
        except Exception as exc:
            return self._fail_or_poll_after_worker_error(request, lease_owner_id, exc)

    @contextmanager
    def _lease_renewer(self, request: QueueRunRequest, lease_owner_id: str) -> Iterator[None]:
        if request.lease_seconds is None:
            yield
            return
        interval = _heartbeat_interval(request.lease_seconds)
        stopped = threading.Event()

        def renew() -> None:
            while not stopped.wait(interval):
                try:
                    self.service.heartbeat_run(
                        request.tenant_id,
                        request.project_id,
                        str(request.run_id),
                        lease_owner_id=lease_owner_id,
                        lease_seconds=request.lease_seconds,
                    )
                except Exception:
                    stopped.set()
                    return

        thread = threading.Thread(target=renew, name=f"a1-lease-heartbeat-{request.run_id}", daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(timeout=1)

    def _fail_or_poll_after_worker_error(self, request: QueueRunRequest, lease_owner_id: str, exc: Exception) -> JsonDict:
        try:
            return self.service.fail_run(
                request.tenant_id,
                request.project_id,
                str(request.run_id),
                error={"type": type(exc).__name__, "message": redact_text(str(exc))},
                lease_owner_id=lease_owner_id,
            )
        except ValidationError:
            return self.service.poll_run(request.tenant_id, request.project_id, str(request.run_id))["run"]
    def _execution_metadata(self, request: QueueRunRequest, *, runner_workers: int | None = None) -> JsonDict:
        return {
            "source": "services.api.queue_worker",
            "queue_workers": self.queue_workers,
            "runner_max_workers": normalize_max_workers(request.max_workers) if runner_workers is None else runner_workers,
            "lease_owner_id": request.lease_owner_id,
            "lease_seconds": request.lease_seconds,
            **dict(request.metadata or {}),
        }

    def _merge_execution_metadata(self, request: QueueRunRequest) -> None:
        metadata = self._execution_metadata(request)
        with self.service._lock:
            run = self.service._get_run_record(request.tenant_id, request.project_id, str(request.run_id))
            run_metadata = run.get("metadata")
            if not isinstance(run_metadata, dict):
                run_metadata = {}
            run_metadata.update(metadata)
            run["metadata"] = run_metadata

    def _lease_owner_id(self, run_id: str) -> str:
        return f"worker-{id(self):x}:{run_id}"


def _normalize_replay_limit(max_runs: int) -> int:
    limit = int(max_runs)
    if limit < 1:
        raise ValidationError("max_runs must be positive")
    return limit


def _replay_order_key(run: Mapping[str, Any]) -> tuple[int, int, str, str]:
    metadata = run.get("metadata")
    order_value = None
    if isinstance(metadata, Mapping):
        order_value = metadata.get("replay_order", metadata.get("batch_index"))
    try:
        order = int(order_value) if order_value is not None else 0
        has_order = 0 if order_value is not None else 1
    except (TypeError, ValueError):
        order = 0
        has_order = 1
    return (has_order, order, str(run.get("created_at") or ""), str(run.get("run_id") or ""))


def _heartbeat_interval(lease_seconds: float) -> float:
    seconds = float(lease_seconds)
    if seconds <= 0:
        raise ValidationError("lease_seconds must be positive")
    return max(MIN_HEARTBEAT_INTERVAL_SECONDS, min(seconds / 3, 5.0))
