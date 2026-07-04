from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Mapping

from packages.sdk.ashr_clone.api_client import redact_text
from services.runner.runner import DEFAULT_MAX_WORKERS, DEFAULT_TIMEOUT_SECONDS, normalize_max_workers, normalize_timeout_seconds, run_agent_batch

from .runtime import CloudApiService, JsonDict, NotFoundError

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}


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
            metadata={
                "source": "services.api.queue_worker",
                "queue_workers": self.queue_workers,
                "runner_max_workers": runner_workers,
                **dict(request.metadata or {}),
            },
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
            metadata=request.metadata,
        )
        self._futures[queued["run_id"]] = self._executor.submit(self._execute, normalized)
        return queued

    def poll_run(self, tenant_id: str, project_id: str, run_id: str) -> JsonDict:
        return self.service.poll_run(tenant_id, project_id, run_id)

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
        try:
            future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            poll = self.service.poll_run(tenant_id, project_id, run_id)
            if require_terminal:
                raise TimeoutError(f"queued run {run_id} did not reach a terminal status before timeout; current status={poll['status']}") from exc
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
        try:
            running = self.service.mark_run_running(request.tenant_id, request.project_id, run_id)
            if running.get("status") == "cancelled":
                return running
            dataset = self.service.get_dataset(request.tenant_id, request.project_id, request.dataset_id)
            result = run_agent_batch(
                request.agent,
                dataset["cases"],
                dataset_id=dataset["dataset_id"],
                runner_id=request.runner_id,
                max_workers=request.max_workers,
                timeout_seconds=request.timeout_seconds,
                run_id=run_id,
            )
            return self.service.complete_run(request.tenant_id, request.project_id, run_id, result)
        except BaseException as exc:
            return self.service.fail_run(
                request.tenant_id,
                request.project_id,
                run_id,
                error={"type": type(exc).__name__, "message": redact_text(str(exc))},
            )
