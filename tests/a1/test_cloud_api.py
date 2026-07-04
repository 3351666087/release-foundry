import json
from pathlib import Path

import pytest

from examples.agents.mock_agent import RespondingMockAgent
from packages.sdk.ashr_clone.api_client import build_default_request_input_schema
from services.api import CloudApiService, NotFoundError, QuotaExceededError, ValidationError
from services.runner.runner import run_agent_batch


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
