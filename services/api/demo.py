from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from services.runner.runner import DEFAULT_MAX_WORKERS, DEFAULT_TIMEOUT_SECONDS, load_cases, normalize_timeout_seconds, run_agent_batch, write_results_json

from .runtime import CLOUD_API_SCHEMA_VERSION, CloudApiService

JsonDict = dict[str, Any]


def run_agent_cloud_demo(
    *,
    input_path: str | Path,
    agent: str,
    fixture_output_path: str | Path,
    summary_output_path: str | Path | None = None,
    run_output_path: str | Path | None = None,
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
    summary = _demo_summary(
        tenant=tenant,
        project=project,
        dataset=dataset,
        run=run,
        poll=poll,
        quota=service.quota_snapshot(tenant["tenant_id"], project["project_id"]),
        fixture_path=fixture_path,
        run_output_path=run_output_path,
    )
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
        },
        "metadata": {"local_only": True, "ashr_api_used": False},
    }
    return summary


def _write_json(payload: Mapping[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path
