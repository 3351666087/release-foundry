import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from releasefoundry.dataset_adapter import (  # noqa: E402
    DATASET_ADAPTER_VERSION,
    DATASET_SOURCE_ADAPTER_VERSION,
    api_record_to_cases,
    case_from_source_run,
    cases_from_dataset_source,
    dataset_source_to_cases,
    extract_dataset_source,
    replay_fixture_from_source_run,
)
from releasefoundry.trace import build_vm_stream, validate_run_fixture  # noqa: E402
from services.runner.runner import run_agent_batch  # noqa: E402


SYNTHETIC_DATASET_SOURCE = {
    "dataset_type": "multi_run_storyboard",
    "total_runs": 1,
    "runs": {
        "run-alpha": {
            "run_id": "run-alpha",
            "title": "Order lookup",
            "description": "Synthetic support flow.",
            "intent": "answer order status",
            "intent_tags": ["support"],
            "audio_tags": [],
            "actions": [
                {"actor": "user", "name": "greeting", "content": "Where is order A-100?"},
                {
                    "actor": "agent",
                    "name": "lookup_order",
                    "content": "Confirmed booking.",
                    "expected_response": {
                        "text": "Confirmed booking.",
                        "tool_calls": [{"name": "lookup_order", "arguments_json": "{\"order_id\":\"A-100\"}"}],
                    },
                    "action_tags": ["tool"],
                },
                {"actor": "user", "name": "thanks", "content": "Thanks."},
                {"actor": "agent", "name": "final", "content": "Happy to help."},
            ],
        }
    },
}


class ScriptedDatasetAgent:
    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls = 0

    def respond(self, prompt):
        self.calls += 1
        if "Target agent action index: 1" in prompt:
            return {"text": "Confirmed booking.", "tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "A-100"}}]}
        return {"text": "Happy to help.", "tool_calls": []}


def test_dataset_source_to_cases_maps_agent_actions_to_a1_cases():
    cases = cases_from_dataset_source(SYNTHETIC_DATASET_SOURCE)

    assert len(cases) == 2
    assert cases[0]["case_id"] == "run-alpha-a001"
    assert cases[0]["scenario_id"] == "run-alpha"
    assert "Conversation so far" in cases[0]["prompt"]
    assert "Where is order A-100?" in cases[0]["prompt"]
    assert cases[0]["expected"]["text"] == "Confirmed booking."
    assert cases[0]["expected"]["tool_calls"] == [{"name": "lookup_order", "arguments": {"order_id": "A-100"}}]
    assert cases[0]["metadata"]["adapter_version"] == DATASET_ADAPTER_VERSION
    assert cases[0]["metadata"]["adapter_version"] == DATASET_SOURCE_ADAPTER_VERSION
    assert cases[0]["metadata"]["dataset_type"] == "multi_run_storyboard"
    assert "source_run_hash" in cases[0]["metadata"]
    assert "releasefoundry_run_id" not in cases[0]["metadata"]
    metadata_text = json.dumps(cases[0]["metadata"], sort_keys=True)
    assert "Where is order A-100?" not in metadata_text
    assert "Confirmed booking." not in metadata_text
    assert cases[1]["expected"]["text"] == "Happy to help."


def test_case_from_source_run_selects_agent_action_and_marks_external_judge():
    first_case = case_from_source_run(SYNTHETIC_DATASET_SOURCE["runs"]["run-alpha"], agent_action_ordinal=0, dataset_type="multi_run_storyboard")

    assert first_case["case_id"] == "run-alpha-a001"
    assert first_case["metadata"]["requires_external_judge"] is False

    source_run = {"run_id": "needs-judge", "actions": [{"actor": "agent", "name": "silent", "content": ""}]}
    needs_judge = case_from_source_run(source_run)

    assert needs_judge["expected"] == {}
    assert needs_judge["metadata"]["requires_external_judge"] is True


def test_dataset_source_to_cases_respects_zero_max_cases():
    assert cases_from_dataset_source(SYNTHETIC_DATASET_SOURCE, max_cases=0) == []


def test_api_record_to_cases_accepts_probe_record_shape():
    record = {"response": {"status": "ok", "dataset": {"dataset_source": SYNTHETIC_DATASET_SOURCE}}}

    assert extract_dataset_source(record)["dataset_type"] == "multi_run_storyboard"
    assert len(api_record_to_cases(record, max_cases=1)) == 1
    try:
        api_record_to_cases(record, max_cases=-1)
    except ValueError as exc:
        assert "max_cases must be non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("negative max_cases should be rejected")


def test_dataset_cases_run_through_local_runner_with_trace():
    cases = dataset_source_to_cases(SYNTHETIC_DATASET_SOURCE)

    result = run_agent_batch(ScriptedDatasetAgent, cases, dataset_id="releasefoundry-real-shape", runner_id="a1-dataset-adapter", max_workers=4, timeout_seconds=5)

    assert result["total_cases"] == 2
    assert result["passed"] == 2
    assert result["trace_completeness"] == 1.0
    assert result["cases"][0]["metadata"]["source"] == "releasefoundry_dataset_source"
    assert result["cases"][0]["observations"][1]["vm_stream"]["provider"] == "local-runner"


def test_replay_fixture_from_source_run_uses_strict_trace_helpers():
    fixture = replay_fixture_from_source_run(SYNTHETIC_DATASET_SOURCE["runs"]["run-alpha"])

    assert validate_run_fixture(fixture) is True
    assert build_vm_stream(fixture["events"]) == fixture["vm_stream"]
    assert fixture["run"]["agent"] == "releasefoundry-dataset-source"
    assert fixture["expected"]["source_actions"] == 4
    assert fixture["expected"]["agent_actions"] == 2
    streams = [frame["stream"] for frame in fixture["vm_stream"]]
    assert "stdin" in streams
    assert "stdout" in streams
    assert "tool_call" in streams
    assert "actions" not in json.dumps(fixture["events"][0]["metadata"], sort_keys=True)


def test_dataset_adapter_cli_writes_cases(tmp_path):
    input_path = tmp_path / "record.json"
    output_path = tmp_path / "cases.json"
    input_path.write_text(json.dumps({"response": {"dataset": {"dataset_source": SYNTHETIC_DATASET_SOURCE}}}), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-B", "-m", "services.runner.dataset_adapter", "--input", str(input_path), "--output", str(output_path), "--max-cases", "1"],
        cwd=str(Path(__file__).resolve().parents[2]),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "converted 1 ReleaseFoundry dataset case" in completed.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["adapter_version"] == DATASET_ADAPTER_VERSION
    assert len(payload["cases"]) == 1
