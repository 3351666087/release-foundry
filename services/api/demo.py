from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from services.runner.runner import DEFAULT_MAX_WORKERS, DEFAULT_TIMEOUT_SECONDS, load_cases, normalize_timeout_seconds, run_agent_batch, write_results_json

from .queue_worker import TERMINAL_RUN_STATUSES, CloudQueueWorker, QueueRunRequest
from .runtime import CLOUD_API_SCHEMA_VERSION, CloudApiService, ValidationError

JsonDict = dict[str, Any]


def run_agent_cloud_demo(
    *,
    input_path: str | Path,
    agent: str,
    fixture_output_path: str | Path,
    summary_output_path: str | Path | None = None,
    run_output_path: str | Path | None = None,
    state_output_path: str | Path | None = None,
    tenant_id: str = "tenant_local_demo",
    project_id: str = "project_local_demo",
    tenant_name: str = "Local Demo Tenant",
    project_name: str = "Local Demo Project",
    dataset_id: str = "dataset_local_demo",
    dataset_name: str = "Local Demo Dataset",
    runner_id: str = "a1-cloud-demo-runner",
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
) -> JsonDict:
    cases = load_cases(input_path)
    service = CloudApiService()
    tenant = service.create_tenant(tenant_name, tenant_id=tenant_id, metadata={"local_only": True})
    project = service.create_project(tenant["tenant_id"], project_name, project_id=project_id, metadata={"local_only": True})
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name=dataset_name,
        cases=cases,
        dataset_id=dataset_id,
        metadata={"source": "services.api.demo", "input_path": str(input_path)},
    )
    result = run_agent_batch(
        agent,
        cases,
        dataset_id=dataset["dataset_id"],
        runner_id=runner_id,
        max_workers=max_workers,
        timeout_seconds=normalize_timeout_seconds(timeout_seconds),
    )
    run = service.submit_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        run_result=result,
        metadata={"source": "services.api.demo"},
    )
    poll = service.poll_run(tenant["tenant_id"], project["project_id"], run["run_id"])
    fixture_path = service.write_run_fixture(tenant["tenant_id"], project["project_id"], run["run_id"], fixture_output_path)
    if run_output_path is not None:
        write_results_json(result, run_output_path)
    state_path = service.write_state(state_output_path) if state_output_path is not None else None
    summary = _demo_summary(
        tenant=tenant,
        project=project,
        dataset=dataset,
        run=run,
        poll=poll,
        quota=service.quota_snapshot(tenant["tenant_id"], project["project_id"]),
        fixture_path=fixture_path,
        run_output_path=run_output_path,
        state_path=state_path,
    )
    if summary_output_path is not None:
        _write_json(summary, summary_output_path)
    return summary


def run_agent_cloud_queue_demo(
    *,
    input_path: str | Path,
    agent: str,
    fixture_output_path: str | Path,
    summary_output_path: str | Path | None = None,
    run_output_path: str | Path | None = None,
    state_output_path: str | Path | None = None,
    tenant_id: str = "tenant_local_queue_demo",
    project_id: str = "project_local_queue_demo",
    tenant_name: str = "Local Queue Demo Tenant",
    project_name: str = "Local Queue Demo Project",
    dataset_id: str = "dataset_local_queue_demo",
    dataset_name: str = "Local Queue Demo Dataset",
    runner_id: str = "a1-cloud-queue-runner",
    queue_workers: int | None = DEFAULT_MAX_WORKERS,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
    wait_timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
) -> JsonDict:
    cases = load_cases(input_path)
    service = CloudApiService()
    tenant = service.create_tenant(tenant_name, tenant_id=tenant_id, metadata={"local_only": True})
    project = service.create_project(tenant["tenant_id"], project_name, project_id=project_id, metadata={"local_only": True})
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name=dataset_name,
        cases=cases,
        dataset_id=dataset_id,
        metadata={"source": "services.api.demo.queue", "input_path": str(input_path)},
    )
    with CloudQueueWorker(service, queue_workers=queue_workers) as worker:
        queued = worker.enqueue_agent_run(
            QueueRunRequest(
                tenant_id=tenant["tenant_id"],
                project_id=project["project_id"],
                dataset_id=dataset["dataset_id"],
                agent=agent,
                runner_id=runner_id,
                max_workers=max_workers,
                timeout_seconds=normalize_timeout_seconds(timeout_seconds),
                metadata={"source": "services.api.demo.queue"},
            )
        )
        completed = worker.wait_for_run(
            tenant["tenant_id"],
            project["project_id"],
            queued["run_id"],
            timeout_seconds=wait_timeout_seconds,
            require_terminal=True,
        )["run"]
    fixture_path = service.write_run_fixture(tenant["tenant_id"], project["project_id"], completed["run_id"], fixture_output_path)
    if run_output_path is not None:
        write_results_json(completed["result"], run_output_path)
    state_path = service.write_state(state_output_path) if state_output_path is not None else None
    summary = _demo_summary(
        tenant=tenant,
        project=project,
        dataset=dataset,
        run=completed,
        poll=service.poll_run(tenant["tenant_id"], project["project_id"], completed["run_id"]),
        quota=service.quota_snapshot(tenant["tenant_id"], project["project_id"]),
        fixture_path=fixture_path,
        run_output_path=run_output_path,
        state_path=state_path,
    )
    summary["queue"] = {
        "queued_status": queued["status"],
        "queue_workers": completed.get("metadata", {}).get("queue_workers"),
        "runner_max_workers": completed.get("metadata", {}).get("runner_max_workers"),
        "status_history": completed.get("status_history", []),
    }
    if summary_output_path is not None:
        _write_json(summary, summary_output_path)
    return summary


def create_agent_cloud_queue_state(
    *,
    input_path: str | Path,
    state_output_path: str | Path,
    summary_output_path: str | Path | None = None,
    tenant_id: str = "tenant_local_queue_state",
    project_id: str = "project_local_queue_state",
    tenant_name: str = "Local Queue State Tenant",
    project_name: str = "Local Queue State Project",
    dataset_id: str = "dataset_local_queue_state",
    dataset_name: str = "Local Queue State Dataset",
    runner_id: str = "a1-cloud-queue-runner",
    run_id: str | None = None,
    run_ids: Iterable[str] | None = None,
    run_count: int = 1,
) -> JsonDict:
    cases = load_cases(input_path)
    service = CloudApiService()
    tenant = service.create_tenant(tenant_name, tenant_id=tenant_id, metadata={"local_only": True})
    project = service.create_project(tenant["tenant_id"], project_name, project_id=project_id, metadata={"local_only": True})
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name=dataset_name,
        cases=cases,
        dataset_id=dataset_id,
        metadata={"source": "services.api.demo.queue_state", "input_path": str(input_path)},
    )
    queue_run_ids = _queue_run_ids(dataset["dataset_id"], run_id=run_id, run_ids=run_ids, run_count=run_count)
    queued_runs = []
    for index, queued_run_id in enumerate(queue_run_ids):
        queued_runs.append(
            service.create_queued_run(
                tenant["tenant_id"],
                project["project_id"],
                dataset_id=dataset["dataset_id"],
                runner_id=runner_id,
                run_id=queued_run_id,
                metadata={
                    "source": "services.api.demo.queue_state",
                    "batch_index": index,
                    "batch_size": len(queue_run_ids),
                    "replay_order": index,
                },
            )
        )
    state_path = service.write_state(state_output_path)
    summary = _state_summary(
        tenant=tenant,
        project=project,
        dataset=dataset,
        runs=queued_runs,
        quota=service.quota_snapshot(tenant["tenant_id"], project["project_id"]),
        state_input_path=None,
        state_output_path=state_path,
    )
    summary["queue"] = _queue_batch_summary(queued_runs)
    if summary_output_path is not None:
        _write_json(summary, summary_output_path)
    return summary


def replay_agent_cloud_queue_state(
    *,
    state_input_path: str | Path,
    agent: str,
    tenant_id: str,
    project_id: str,
    fixture_output_path: str | Path | None = None,
    fixture_output_dir: str | Path | None = None,
    summary_output_path: str | Path | None = None,
    run_output_path: str | Path | None = None,
    run_output_dir: str | Path | None = None,
    state_output_path: str | Path | None = None,
    dataset_id: str | None = None,
    statuses: Iterable[str] = ("queued", "running"),
    max_runs: int = 100,
    queue_workers: int | None = DEFAULT_MAX_WORKERS,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
    wait_timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
) -> JsonDict:
    service = CloudApiService.from_state_file(state_input_path)
    with CloudQueueWorker(service, queue_workers=queue_workers) as worker:
        replayed = worker.replay_incomplete_runs(
            tenant_id,
            project_id,
            agent=agent,
            dataset_id=dataset_id,
            statuses=statuses,
            max_runs=max_runs,
            max_workers=max_workers,
            timeout_seconds=normalize_timeout_seconds(timeout_seconds),
            metadata={"source": "services.api.demo.queue_replay", "state_input_path": str(state_input_path)},
        )
        completed = [
            worker.wait_for_run(
                tenant_id,
                project_id,
                str(run["run_id"]),
                timeout_seconds=wait_timeout_seconds,
                require_terminal=True,
            )["run"]
            for run in replayed
        ]
    outputs = _write_replayed_outputs(
        service=service,
        tenant_id=tenant_id,
        project_id=project_id,
        runs=completed,
        fixture_output_path=fixture_output_path,
        fixture_output_dir=fixture_output_dir,
        run_output_path=run_output_path,
        run_output_dir=run_output_dir,
    )
    state_path = service.write_state(state_output_path) if state_output_path is not None else None
    quota = service.quota_snapshot(tenant_id, project_id)
    summary = _state_summary(
        tenant=service.get_tenant(tenant_id),
        project=service.get_project(tenant_id, project_id),
        dataset=service.get_dataset(tenant_id, project_id, dataset_id or str(completed[0]["dataset_id"] if completed else replayed[0]["dataset_id"])) if (completed or replayed) else None,
        runs=completed,
        quota=quota,
        state_input_path=state_input_path,
        state_output_path=state_path,
    )
    summary["replay"] = {
        "replayed": [run["run_id"] for run in replayed],
        "completed": [{"run_id": run["run_id"], "status": run["status"]} for run in completed],
        "status_histories": {str(run["run_id"]): run.get("status_history", []) for run in completed},
        "statuses": [str(status) for status in statuses],
        "max_runs": int(max_runs),
    }
    summary["outputs"].update(outputs)
    if summary_output_path is not None:
        _write_json(summary, summary_output_path)
    return summary


def export_run_fixture_from_state(
    *,
    state_input_path: str | Path,
    tenant_id: str,
    project_id: str,
    run_id: str,
    fixture_output_path: str | Path,
    summary_output_path: str | Path | None = None,
    allow_incomplete: bool = False,
) -> JsonDict:
    service = CloudApiService.from_state_file(state_input_path)
    poll = service.poll_run(tenant_id, project_id, run_id)
    if not allow_incomplete and poll["status"] not in TERMINAL_RUN_STATUSES:
        raise ValidationError(f"run {run_id} must be terminal before fixture export; current status={poll['status']}")
    fixture_path = service.write_run_fixture(tenant_id, project_id, run_id, fixture_output_path)
    run = poll["run"]
    summary = _state_summary(
        tenant=service.get_tenant(tenant_id),
        project=service.get_project(tenant_id, project_id),
        dataset=service.get_dataset(tenant_id, project_id, run["dataset_id"]),
        runs=[run],
        quota=service.quota_snapshot(tenant_id, project_id),
        state_input_path=state_input_path,
        state_output_path=None,
    )
    summary["outputs"]["fixture"] = str(fixture_path)
    summary["export"] = {"run_id": run_id, "status": poll["status"], "allow_incomplete": allow_incomplete}
    if summary_output_path is not None:
        _write_json(summary, summary_output_path)
    return summary


def _demo_summary(
    *,
    tenant: Mapping[str, Any],
    project: Mapping[str, Any],
    dataset: Mapping[str, Any],
    run: Mapping[str, Any],
    poll: Mapping[str, Any],
    quota: Mapping[str, Any],
    fixture_path: str | Path,
    run_output_path: str | Path | None,
    state_path: str | Path | None,
) -> JsonDict:
    result = run.get("result") if isinstance(run.get("result"), Mapping) else {}
    summary = {
        "schema_version": CLOUD_API_SCHEMA_VERSION,
        "tenant": {"tenant_id": tenant["tenant_id"], "name": tenant["name"]},
        "project": {"project_id": project["project_id"], "tenant_id": project["tenant_id"], "name": project["name"]},
        "dataset": {"dataset_id": dataset["dataset_id"], "case_count": dataset["case_count"], "name": dataset["name"]},
        "run": {
            "run_id": run["run_id"],
            "dataset_id": run["dataset_id"],
            "status": run["status"],
            "result_status": run["result_status"],
            "runner_id": run["runner_id"],
            "total_cases": run["total_cases"],
            "passed": result.get("passed"),
            "failed": result.get("failed"),
            "errored": result.get("errored"),
            "timed_out": result.get("timed_out"),
            "trace_completeness": result.get("trace_completeness"),
            "observations": len(run.get("observations") or []),
        },
        "poll": {"status": poll["status"], "run_id": poll["run_id"]},
        "quota": {
            "used": quota.get("used", {}),
            "remaining": quota.get("remaining", {}),
        },
        "outputs": {
            "fixture": str(fixture_path),
            "run_result": str(run_output_path) if run_output_path is not None else None,
            "state": str(state_path) if state_path is not None else None,
        },
        "metadata": {"local_only": True, "releasefoundry_api_used": False},
    }
    return summary


def _state_summary(
    *,
    tenant: Mapping[str, Any],
    project: Mapping[str, Any],
    dataset: Mapping[str, Any] | None,
    runs: Iterable[Mapping[str, Any]],
    quota: Mapping[str, Any],
    state_input_path: str | Path | None,
    state_output_path: str | Path | None,
) -> JsonDict:
    run_list = list(runs)
    run_summaries = [
        {
            "run_id": run["run_id"],
            "dataset_id": run["dataset_id"],
            "status": run["status"],
            "result_status": run["result_status"],
            "runner_id": run["runner_id"],
            "total_cases": run["total_cases"],
            "passed": (run.get("result") or {}).get("passed") if isinstance(run.get("result"), Mapping) else None,
            "failed": (run.get("result") or {}).get("failed") if isinstance(run.get("result"), Mapping) else None,
            "errored": (run.get("result") or {}).get("errored") if isinstance(run.get("result"), Mapping) else None,
            "timed_out": (run.get("result") or {}).get("timed_out") if isinstance(run.get("result"), Mapping) else None,
            "observations": len(run.get("observations") or []),
            "status_history": run.get("status_history", []),
        }
        for run in run_list
    ]
    return {
        "schema_version": CLOUD_API_SCHEMA_VERSION,
        "tenant": {"tenant_id": tenant["tenant_id"], "name": tenant["name"]},
        "project": {"project_id": project["project_id"], "tenant_id": project["tenant_id"], "name": project["name"]},
        "dataset": (
            {"dataset_id": dataset["dataset_id"], "case_count": dataset["case_count"], "name": dataset["name"]}
            if dataset is not None
            else None
        ),
        "run_ids": [run["run_id"] for run in run_list],
        "runs": run_summaries,
        "quota": {
            "used": quota.get("used", {}),
            "remaining": quota.get("remaining", {}),
        },
        "outputs": {
            "state_input": str(state_input_path) if state_input_path is not None else None,
            "state": str(state_output_path) if state_output_path is not None else None,
        },
        "metadata": {"local_only": True, "releasefoundry_api_used": False},
    }


def _queue_run_ids(
    dataset_id: str,
    *,
    run_id: str | None,
    run_ids: Iterable[str] | None,
    run_count: int,
) -> list[str | None]:
    try:
        count = int(run_count)
    except (TypeError, ValueError) as exc:
        raise ValidationError("run_count must be positive") from exc
    if count < 1:
        raise ValidationError("run_count must be positive")
    explicit_run_ids = []
    if run_id is not None:
        explicit_run_ids.append(str(run_id))
    explicit_run_ids.extend(str(item) for item in (run_ids or []))
    if explicit_run_ids:
        if count != 1 and count != len(explicit_run_ids):
            raise ValidationError("run_count must match the number of explicit run IDs")
        if len(set(explicit_run_ids)) != len(explicit_run_ids):
            raise ValidationError("run IDs must be unique")
        return explicit_run_ids
    if count == 1:
        return [None]
    prefix = _safe_run_filename(str(dataset_id)) or "dataset"
    return [f"run_{prefix}_{index + 1:03d}" for index in range(count)]


def _queue_batch_summary(runs: Iterable[Mapping[str, Any]]) -> JsonDict:
    run_list = list(runs)
    first = run_list[0] if run_list else {}
    return {
        "queued_status": first.get("status"),
        "status_history": first.get("status_history", []),
        "run_ids": [run["run_id"] for run in run_list],
        "queued_statuses": [{"run_id": run["run_id"], "status": run["status"]} for run in run_list],
        "status_histories": {str(run["run_id"]): run.get("status_history", []) for run in run_list},
        "batch_size": len(run_list),
    }


def _write_replayed_outputs(
    *,
    service: CloudApiService,
    tenant_id: str,
    project_id: str,
    runs: Iterable[Mapping[str, Any]],
    fixture_output_path: str | Path | None,
    fixture_output_dir: str | Path | None,
    run_output_path: str | Path | None,
    run_output_dir: str | Path | None,
) -> JsonDict:
    run_list = list(runs)
    if fixture_output_path is not None and fixture_output_dir is not None:
        raise ValidationError("use either fixture_output_path or fixture_output_dir")
    if run_output_path is not None and run_output_dir is not None:
        raise ValidationError("use either run_output_path or run_output_dir")
    if fixture_output_path is not None and len(run_list) != 1:
        raise ValidationError("fixture output path requires exactly one replayed run; use fixture output dir for multiple runs")
    if run_output_path is not None and len(run_list) != 1:
        raise ValidationError("run output path requires exactly one replayed run; use run output dir for multiple runs")

    fixture_path: Path | None = None
    run_result_path: Path | None = None
    fixture_paths: dict[str, str] = {}
    run_result_paths: dict[str, str] = {}

    if fixture_output_path is not None and run_list:
        run = run_list[0]
        fixture_path = service.write_run_fixture(tenant_id, project_id, str(run["run_id"]), fixture_output_path)
    if run_output_path is not None and run_list:
        run = run_list[0]
        run_result_path = write_results_json(run["result"], run_output_path)
    if fixture_output_dir is not None:
        output_dir = Path(fixture_output_dir)
        for run in run_list:
            run_id = str(run["run_id"])
            output_path = output_dir / f"{_safe_run_filename(run_id)}.fixture.json"
            fixture_paths[run_id] = str(service.write_run_fixture(tenant_id, project_id, run_id, output_path))
    if run_output_dir is not None:
        output_dir = Path(run_output_dir)
        for run in run_list:
            run_id = str(run["run_id"])
            output_path = output_dir / f"{_safe_run_filename(run_id)}.run.json"
            run_result_paths[run_id] = str(write_results_json(run["result"], output_path))

    return {
        "fixture": str(fixture_path) if fixture_path is not None else None,
        "run_result": str(run_result_path) if run_result_path is not None else None,
        "fixtures": fixture_paths,
        "run_results": run_result_paths,
    }


def _safe_run_filename(run_id: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in run_id)
    return safe.strip("._") or "run"


def _write_json(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path
