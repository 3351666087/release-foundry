import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from examples.agents.mock_agent import RespondingMockAgent
from packages.sdk.ashr_clone.api_client import build_default_request_input_schema
from services.api import CloudApiService, CloudQueueWorker, NotFoundError, QueueRunRequest, QuotaExceededError, ValidationError, run_agent_cloud_demo
from services.runner.runner import run_agent_batch

ROOT = Path(__file__).resolve().parents[2]


def _service_with_project():
    service = CloudApiService()
    tenant = service.create_tenant("Tenant One", tenant_id="tenant_one")
    project = service.create_project(tenant["tenant_id"], "Project One", project_id="project_one")
    return service, tenant, project


def test_cloud_api_imports_dataset_submits_run_and_polls_completed():
    service, tenant, project = _service_with_project()
    cases = [
        {"id": "case-1", "prompt": "hello", "expected": {"text": "Echo: hello"}},
        {"id": "case-2", "prompt": "What is 19 + 23?", "expected": {"text": "The answer is 42.", "tool_calls": [{"name": "calculator"}]}},
    ]
    dataset = service.create_dataset(tenant["tenant_id"], project["project_id"], name="Smoke Dataset", cases=cases, dataset_id="dataset_smoke")
    run_result = run_agent_batch(RespondingMockAgent, cases, dataset_id=dataset["dataset_id"], runner_id="a1-cloud-smoke", max_workers=4, timeout_seconds=5)

    run = service.submit_run(tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"], run_result=run_result)
    polled = service.poll_run(tenant["tenant_id"], project["project_id"], run["run_id"])
    fixture = service.export_run_fixture(tenant["tenant_id"], project["project_id"], run["run_id"])

    assert dataset["case_count"] == 2
    assert run["status"] == "completed"
    assert run["result_status"] == "passed"
    assert run["total_cases"] == 2
    assert len(run["observations"]) == 4
    assert polled["status"] == "completed"
    assert fixture["run_result"]["run_id"] == run_result["run_id"]
    assert fixture["metadata"]["ashr_api_used"] is False
    assert service.list_runs(tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"])[0]["run_id"] == run["run_id"]


def test_cloud_api_enforces_tenant_project_isolation():
    service = CloudApiService()
    tenant_a = service.create_tenant("Tenant A", tenant_id="tenant_a")
    project_a = service.create_project(tenant_a["tenant_id"], "Project A", project_id="project_a")
    tenant_b = service.create_tenant("Tenant B", tenant_id="tenant_b")
    project_b = service.create_project(tenant_b["tenant_id"], "Project B", project_id="project_b")
    dataset = service.create_dataset(tenant_a["tenant_id"], project_a["project_id"], name="A", cases=[{"id": "a", "prompt": "a"}], dataset_id="dataset_a")

    assert service.list_datasets(tenant_a["tenant_id"], project_a["project_id"])[0]["dataset_id"] == dataset["dataset_id"]
    assert service.list_datasets(tenant_b["tenant_id"], project_b["project_id"]) == []
    with pytest.raises(NotFoundError):
        service.get_dataset(tenant_b["tenant_id"], project_b["project_id"], dataset["dataset_id"])
    with pytest.raises(NotFoundError):
        service.submit_run(tenant_b["tenant_id"], project_b["project_id"], dataset_id=dataset["dataset_id"], run_result={"run_id": "run_wrong", "cases": []})


def test_cloud_api_quota_blocks_before_dataset_write():
    service, tenant, project = _service_with_project()
    service.quota.configure(tenant["tenant_id"], project["project_id"], {"dataset.create": 0})

    with pytest.raises(QuotaExceededError):
        service.create_dataset(tenant["tenant_id"], project["project_id"], name="Blocked", cases=[{"id": "x"}])

    assert service.list_datasets(tenant["tenant_id"], project["project_id"]) == []
    assert service.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"].get("dataset.create") is None


def test_cloud_api_validation_errors_do_not_consume_quota():
    service, tenant, project = _service_with_project()

    with pytest.raises(ValidationError):
        service.create_dataset(tenant["tenant_id"], project["project_id"], name="", cases=[{"id": "x"}])
    with pytest.raises(ValidationError):
        service.create_request(tenant["tenant_id"], project["project_id"], name="")

    quota = service.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    assert quota.get("dataset.create") is None
    assert quota.get("request.create") is None


def test_cloud_api_request_schema_preserves_media_agent_input_shape():
    service, tenant, project = _service_with_project()
    accepted_inputs = {"text": True, "image": True, "audio": True, "file": True}
    schema = build_default_request_input_schema({"agent": {"accepted_inputs": accepted_inputs}})

    request = service.create_request(
        tenant["tenant_id"],
        project["project_id"],
        name="Media interface",
        request_input_schema=schema,
        accepted_inputs=accepted_inputs,
        request_id="request_media",
    )

    part_schema = request["request_input_schema"]["$defs"]["agent_input_part"]
    part_types = set()
    for variant in part_schema["oneOf"]:
        type_schema = variant["properties"]["type"]
        part_types.update(type_schema.get("enum", []))
        if "const" in type_schema:
            part_types.add(type_schema["const"])
    assert request["status"] == "created"
    assert request["accepted_inputs"]["file"] is True
    assert part_types == {"audio", "file", "image", "text"}
    assert json.dumps(request, sort_keys=True)


def test_cloud_api_observation_quota_blocks_run_before_write():
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(tenant["tenant_id"], project["project_id"], name="Dataset", cases=[{"id": "case-1", "prompt": "hello"}], dataset_id="dataset_quota")
    result = run_agent_batch(RespondingMockAgent, [{"id": "case-1", "prompt": "hello", "expected": {"text": "Echo: hello"}}], dataset_id=dataset["dataset_id"], max_workers=4, timeout_seconds=5)
    service.quota.configure(tenant["tenant_id"], project["project_id"], {"observation.write": 1})

    with pytest.raises(QuotaExceededError):
        service.submit_run(tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"], run_result=result)

    assert service.list_runs(tenant["tenant_id"], project["project_id"]) == []


def test_cloud_api_can_write_a_synthetic_run_fixture(tmp_path):
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(tenant["tenant_id"], project["project_id"], name="Dataset", cases=[{"id": "case-1", "prompt": "hello"}], dataset_id="dataset_fixture")
    result = run_agent_batch(RespondingMockAgent, [{"id": "case-1", "prompt": "hello", "expected": {"text": "Echo: hello"}}], dataset_id=dataset["dataset_id"], max_workers=4, timeout_seconds=5)
    run = service.submit_run(tenant["tenant_id"], project["project_id"], dataset_id=dataset["dataset_id"], run_result=result)
    output = service.write_run_fixture(tenant["tenant_id"], project["project_id"], run["run_id"], tmp_path / "fixture.json")

    payload = json.loads(Path(output).read_text(encoding="utf-8"))
    assert payload["schema_version"] == "ashr.clone.cloud_api.v1"
    assert payload["observations"]


def test_cloud_queue_worker_transitions_run_and_preserves_fixture_shape(tmp_path):
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="Queued Dataset",
        cases=[
            {"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}},
            {"id": "math", "prompt": "What is 19 + 23?", "expected": {"text": "The answer is 42.", "tool_calls": [{"name": "calculator"}]}},
        ],
        dataset_id="dataset_queued",
    )

    with CloudQueueWorker(service, queue_workers=1) as worker:
        queued = worker.enqueue_agent_run(
            QueueRunRequest(
                tenant_id=tenant["tenant_id"],
                project_id=project["project_id"],
                dataset_id=dataset["dataset_id"],
                agent="examples.agents.mock_agent:RespondingMockAgent",
                runner_id="a1-queue-test",
                max_workers=1,
                timeout_seconds=5,
                run_id="run_queued_test",
            )
        )
        completed = worker.wait_for_run(tenant["tenant_id"], project["project_id"], queued["run_id"], timeout_seconds=10)["run"]

    fixture_path = service.write_run_fixture(tenant["tenant_id"], project["project_id"], completed["run_id"], tmp_path / "queued_fixture.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    statuses = [item["status"] for item in completed["status_history"]]
    quota = service.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    assert queued["status"] == "queued"
    assert completed["status"] == "completed"
    assert completed["result_status"] == "passed"
    assert statuses == ["queued", "running", "completed"]
    assert completed["metadata"]["queue_workers"] == 4
    assert completed["metadata"]["runner_max_workers"] == 4
    assert completed["result"]["max_workers"] == 4
    assert len(completed["observations"]) == 4
    assert quota["run.submit"] == 1
    assert quota["observation.write"] == 4
    assert fixture["run_result"]["run_id"] == "run_queued_test"
    assert fixture["metadata"]["ashr_api_used"] is False


def test_cloud_queue_worker_quota_failure_keeps_failed_run_without_observation_write():
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="Queued Dataset",
        cases=[{"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}}],
        dataset_id="dataset_queued_quota",
    )
    service.quota.configure(tenant["tenant_id"], project["project_id"], {"observation.write": 1})

    with CloudQueueWorker(service, queue_workers=4) as worker:
        queued = worker.enqueue_agent_run(
            QueueRunRequest(
                tenant_id=tenant["tenant_id"],
                project_id=project["project_id"],
                dataset_id=dataset["dataset_id"],
                agent=RespondingMockAgent,
                runner_id="a1-queue-quota-test",
                timeout_seconds=5,
                run_id="run_queued_quota",
            )
        )
        failed = worker.wait_for_run(tenant["tenant_id"], project["project_id"], queued["run_id"], timeout_seconds=10)["run"]

    quota = service.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    statuses = [item["status"] for item in failed["status_history"]]
    assert failed["status"] == "failed"
    assert failed["result_status"] == "error"
    assert failed["error"]["type"] == "QuotaExceededError"
    assert statuses == ["queued", "running", "failed"]
    assert quota["run.submit"] == 1
    assert quota.get("observation.write") is None
    assert service.list_runs(tenant["tenant_id"], project["project_id"])[0]["run_id"] == "run_queued_quota"


def test_cloud_queue_worker_wait_returns_cancelled_running_run_without_future_timeout():
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="Slow Queue Dataset",
        cases=[{"id": "slow", "prompt": "hello"}],
        dataset_id="dataset_cancel_running",
    )

    with CloudQueueWorker(service, queue_workers=1) as worker:
        queued = worker.enqueue_agent_run(
            QueueRunRequest(
                tenant_id=tenant["tenant_id"],
                project_id=project["project_id"],
                dataset_id=dataset["dataset_id"],
                agent="tests.a1.fixtures_sensitive_agent:SlowAgent",
                runner_id="a1-queue-cancel-running-test",
                max_workers=1,
                timeout_seconds=5,
                run_id="run_cancel_running",
            )
        )
        for _ in range(50):
            if worker.poll_run(tenant["tenant_id"], project["project_id"], queued["run_id"])["status"] == "running":
                break
            time.sleep(0.01)
        else:
            raise AssertionError("queued run did not reach running before cancellation")

        cancelled = worker.cancel_run(tenant["tenant_id"], project["project_id"], queued["run_id"], reason="test cancellation")
        waited = worker.wait_for_run(tenant["tenant_id"], project["project_id"], queued["run_id"], timeout_seconds=0.01, require_terminal=True)

    assert cancelled["status"] == "cancelled"
    assert waited["status"] == "cancelled"
    assert [item["status"] for item in waited["run"]["status_history"]] == ["queued", "running", "cancelled"]


def test_cloud_queue_worker_wait_returns_cancelled_pending_run_without_cancelled_error():
    service, tenant, project = _service_with_project()
    first_dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="First Slow Queue Dataset",
        cases=[{"id": f"first-{index}", "prompt": "hello"} for index in range(8)],
        dataset_id="dataset_cancel_pending_first",
    )
    second_dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="Second Slow Queue Dataset",
        cases=[{"id": "second", "prompt": "hello"}],
        dataset_id="dataset_cancel_pending_second",
    )

    with CloudQueueWorker(service, queue_workers=1) as worker:
        for index in range(worker.queue_workers):
            worker.enqueue_agent_run(
                QueueRunRequest(
                    tenant_id=tenant["tenant_id"],
                    project_id=project["project_id"],
                    dataset_id=first_dataset["dataset_id"],
                    agent="tests.a1.fixtures_sensitive_agent:SlowAgent",
                    runner_id="a1-queue-cancel-pending-test",
                    max_workers=1,
                    timeout_seconds=5,
                    run_id=f"run_cancel_pending_blocker_{index}",
                )
            )
        queued = worker.enqueue_agent_run(
            QueueRunRequest(
                tenant_id=tenant["tenant_id"],
                project_id=project["project_id"],
                dataset_id=second_dataset["dataset_id"],
                agent="tests.a1.fixtures_sensitive_agent:SlowAgent",
                runner_id="a1-queue-cancel-pending-test",
                max_workers=1,
                timeout_seconds=5,
                run_id="run_cancel_pending_second",
            )
        )

        cancelled = worker.cancel_run(tenant["tenant_id"], project["project_id"], queued["run_id"], reason="test cancellation")
        waited = worker.wait_for_run(tenant["tenant_id"], project["project_id"], queued["run_id"], timeout_seconds=0.01, require_terminal=True)

    assert cancelled["status"] == "cancelled"
    assert waited["status"] == "cancelled"
    assert [item["status"] for item in waited["run"]["status_history"]] == ["queued", "cancelled"]


def test_cloud_api_state_snapshot_roundtrips_store_and_quota(tmp_path):
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="Persisted Queue Dataset",
        cases=[{"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}}],
        dataset_id="dataset_state_roundtrip",
    )
    queued = service.create_queued_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        runner_id="a1-state-roundtrip-test",
        run_id="run_state_roundtrip",
        metadata={"source": "state-roundtrip-test"},
    )

    state_path = service.write_state(tmp_path / "cloud_state.json")
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    restored = CloudApiService.from_state_file(state_path)

    assert state_payload["kind"] == "local_cloud_state"
    assert state_payload["metadata"]["ashr_api_used"] is False
    assert restored.get_dataset(tenant["tenant_id"], project["project_id"], dataset["dataset_id"])["case_count"] == 1
    assert restored.poll_run(tenant["tenant_id"], project["project_id"], queued["run_id"])["status"] == "queued"
    quota = restored.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    assert quota["dataset.create"] == 1
    assert quota["run.submit"] == 1


def test_cloud_queue_worker_replays_persisted_queued_run_and_writes_fixture(tmp_path):
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="Replay Queue Dataset",
        cases=[{"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}}],
        dataset_id="dataset_queue_replay",
    )
    service.create_queued_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        runner_id="a1-queue-replay-test",
        run_id="run_queue_replay",
    )
    restored = CloudApiService.from_state_file(service.write_state(tmp_path / "cloud_state.json"))

    with CloudQueueWorker(restored, queue_workers=1) as worker:
        replayed = worker.replay_incomplete_runs(
            tenant["tenant_id"],
            project["project_id"],
            agent="examples.agents.mock_agent:RespondingMockAgent",
            max_runs=1,
            max_workers=1,
            timeout_seconds=5,
        )
        completed = worker.wait_for_run(tenant["tenant_id"], project["project_id"], "run_queue_replay", timeout_seconds=10, require_terminal=True)["run"]

    fixture_path = restored.write_run_fixture(tenant["tenant_id"], project["project_id"], "run_queue_replay", tmp_path / "queue_replay_fixture.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    quota = restored.quota_snapshot(tenant["tenant_id"], project["project_id"])["used"]
    assert [run["run_id"] for run in replayed] == ["run_queue_replay"]
    assert [item["status"] for item in completed["status_history"]] == ["queued", "running", "completed"]
    assert completed["result"]["run_id"] == "run_queue_replay"
    assert completed["result_status"] == "passed"
    assert len(completed["observations"]) == 2
    assert quota["run.submit"] == 1
    assert quota["observation.write"] == 2
    assert fixture["run_result"]["run_id"] == "run_queue_replay"
    assert fixture["metadata"]["ashr_api_used"] is False


def test_cloud_queue_worker_replay_respects_max_runs_bound(tmp_path):
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="Bounded Replay Dataset",
        cases=[{"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}}],
        dataset_id="dataset_queue_replay_bound",
    )
    for run_id in ("run_queue_replay_a", "run_queue_replay_b"):
        service.create_queued_run(
            tenant["tenant_id"],
            project["project_id"],
            dataset_id=dataset["dataset_id"],
            runner_id="a1-queue-replay-bound-test",
            run_id=run_id,
        )
    restored = CloudApiService.from_state(service.snapshot_state())

    with CloudQueueWorker(restored, queue_workers=1) as worker:
        replayed = worker.replay_incomplete_runs(
            tenant["tenant_id"],
            project["project_id"],
            agent=RespondingMockAgent,
            max_runs=1,
            max_workers=1,
            timeout_seconds=5,
        )
        completed = worker.wait_for_run(tenant["tenant_id"], project["project_id"], replayed[0]["run_id"], timeout_seconds=10, require_terminal=True)

    assert [run["run_id"] for run in replayed] == ["run_queue_replay_a"]
    assert completed["status"] == "completed"
    assert restored.poll_run(tenant["tenant_id"], project["project_id"], "run_queue_replay_b")["status"] == "queued"


def test_cloud_queue_worker_replay_uses_batch_order_metadata(tmp_path):
    service, tenant, project = _service_with_project()
    dataset = service.create_dataset(
        tenant["tenant_id"],
        project["project_id"],
        name="Ordered Replay Dataset",
        cases=[{"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}}],
        dataset_id="dataset_queue_ordered_replay",
    )
    service.create_queued_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        runner_id="a1-queue-order-test",
        run_id="run_order_second",
        metadata={"batch_index": 1, "batch_size": 2},
    )
    service.create_queued_run(
        tenant["tenant_id"],
        project["project_id"],
        dataset_id=dataset["dataset_id"],
        runner_id="a1-queue-order-test",
        run_id="run_order_first",
        metadata={"batch_index": 0, "batch_size": 2},
    )

    with CloudQueueWorker(CloudApiService.from_state(service.snapshot_state()), queue_workers=1) as worker:
        replayed = worker.replay_incomplete_runs(
            tenant["tenant_id"],
            project["project_id"],
            agent=RespondingMockAgent,
            max_runs=2,
            max_workers=1,
            timeout_seconds=5,
        )
        completed = [
            worker.wait_for_run(tenant["tenant_id"], project["project_id"], run["run_id"], timeout_seconds=10, require_terminal=True)["run"]
            for run in replayed
        ]

    assert [run["run_id"] for run in replayed] == ["run_order_first", "run_order_second"]
    assert [run["run_id"] for run in completed] == ["run_order_first", "run_order_second"]
    assert all(run["status"] == "completed" for run in completed)
    assert all(run["metadata"]["queue_workers"] == 4 for run in completed)
    assert all(run["metadata"]["runner_max_workers"] == 4 for run in completed)


def test_cloud_api_demo_runs_agent_submits_polls_and_writes_outputs(tmp_path):
    input_path = tmp_path / "cases.json"
    fixture_path = tmp_path / "fixture.json"
    summary_path = tmp_path / "summary.json"
    run_path = tmp_path / "run.json"
    input_path.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}},
                    {"id": "math", "prompt": "What is 19 + 23?", "expected": {"text": "The answer is 42.", "tool_calls": [{"name": "calculator"}]}},
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = run_agent_cloud_demo(
        input_path=input_path,
        agent="examples.agents.mock_agent:RespondingMockAgent",
        fixture_output_path=fixture_path,
        summary_output_path=summary_path,
        run_output_path=run_path,
        tenant_id="tenant_demo",
        project_id="project_demo",
        dataset_id="dataset_demo",
        max_workers=4,
        timeout_seconds=5,
    )

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    written_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    run_result = json.loads(run_path.read_text(encoding="utf-8"))
    assert summary["schema_version"] == "ashr.clone.cloud_api.v1"
    assert summary["run"]["status"] == "completed"
    assert summary["run"]["result_status"] == "passed"
    assert summary["run"]["trace_completeness"] == 1.0
    assert summary["quota"]["used"]["dataset.create"] == 1
    assert summary["quota"]["used"]["run.submit"] == 1
    assert summary["quota"]["used"]["observation.write"] == 4
    assert written_summary == summary
    assert fixture["run_result"]["run_id"] == run_result["run_id"]
    assert fixture["metadata"]["ashr_api_used"] is False


def test_cloud_api_cli_run_agent_fresh_setup(tmp_path):
    input_path = tmp_path / "cases.json"
    fixture_path = tmp_path / "fixture.json"
    summary_path = tmp_path / "summary.json"
    run_path = tmp_path / "run.json"
    input_path.write_text(json.dumps({"cases": [{"id": "echo", "prompt": "hello", "expected": {"text": "Echo: hello"}}]}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.api.cli",
            "run-agent",
            "--input",
            str(input_path),
            "--agent",
            "examples.agents.mock_agent:RespondingMockAgent",
            "--fixture-output",
            str(fixture_path),
            "--summary-output",
            str(summary_path),
            "--run-output",
            str(run_path),
            "--tenant-id",
            "tenant_cli",
            "--project-id",
            "project_cli",
            "--dataset-id",
            "dataset_cli",
            "--max-workers",
            "1",
            "--timeout",
            "5",
            "--fail-on-case-failure",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    stdout_summary = json.loads(completed.stdout)
    assert stdout_summary["tenant"]["tenant_id"] == "tenant_cli"
    assert stdout_summary["run"]["passed"] == 1
    assert stdout_summary["run"]["observations"] == 2
    assert fixture_path.exists()
    assert summary_path.exists()
    assert run_path.exists()


def test_cloud_api_cli_fail_on_case_failure_returns_nonzero_and_writes_outputs(tmp_path):
    input_path = tmp_path / "cases.json"
    fixture_path = tmp_path / "fixture.json"
    summary_path = tmp_path / "summary.json"
    input_path.write_text(json.dumps({"cases": [{"id": "fail", "prompt": "hello", "expected": {"text": "not hello"}}]}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.api.cli",
            "run-agent",
            "--input",
            str(input_path),
            "--agent",
            "examples.agents.mock_agent:RespondingMockAgent",
            "--fixture-output",
            str(fixture_path),
            "--summary-output",
            str(summary_path),
            "--fail-on-case-failure",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert json.loads(summary_path.read_text(encoding="utf-8"))["run"]["failed"] == 1
    assert fixture_path.exists()


def test_cloud_api_cli_rejects_negative_timeout_without_outputs(tmp_path):
    input_path = tmp_path / "cases.json"
    fixture_path = tmp_path / "fixture.json"
    summary_path = tmp_path / "summary.json"
    input_path.write_text(json.dumps({"cases": [{"id": "echo", "prompt": "hello"}]}), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.api.cli",
            "run-agent",
            "--input",
            str(input_path),
            "--agent",
            "examples.agents.mock_agent:RespondingMockAgent",
            "--fixture-output",
            str(fixture_path),
            "--summary-output",
            str(summary_path),
            "--timeout",
            "-0.1",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "--timeout must be non-negative" in completed.stderr
    assert not fixture_path.exists()
    assert not summary_path.exists()


def test_cloud_api_cli_redacts_operational_error_text(tmp_path):
    missing_input = tmp_path / "owner@example.com-sk-testtesttest.json"
    fixture_path = tmp_path / "fixture.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "services.api.cli",
            "run-agent",
            "--input",
            str(missing_input),
            "--agent",
            "examples.agents.mock_agent:RespondingMockAgent",
            "--fixture-output",
            str(fixture_path),
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "owner@example.com" not in completed.stderr
    assert "sk-testtesttest" not in completed.stderr
    assert "[redacted]" in completed.stderr
    assert not fixture_path.exists()
