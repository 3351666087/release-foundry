import importlib.util
import json
import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from services.judge.releasefoundry_dataset_acquisition import (
    EXPECTED_CASE_COUNT,
    EXPECTED_DATASET_NAME,
    EXPECTED_SERVER_DATASET_NAME,
    EXPECTED_SERVER_DATASET_TYPE,
    DatasetAcquisitionError,
    assert_no_sensitive_material,
    assert_paid_run_allowed,
    atomic_write_private_json,
    build_calibration_dataset_request,
    create_request_once,
    create_run_once_with_verified_identity,
    fetch_and_verify_dataset,
    find_single_dataset_for_request,
    load_verified_manifest,
    verify_calibration_dataset,
    verify_dataset_case_contracts,
    wait_for_request_terminal,
    write_verified_manifest,
)


ROOT = Path(__file__).resolve().parents[2]


def _spec():
    return build_calibration_dataset_request(root=ROOT)


def _live_dataset(
    spec,
    *,
    dataset_id=42,
    request_id=7,
    dataset_name=EXPECTED_SERVER_DATASET_NAME,
):
    runs = []
    for contract in spec.case_contracts:
        anchors = " | ".join(contract.semantic_anchors)
        runs.append(
            {
                "run_id": contract.test_id,
                "title": (
                    f"{contract.test_id} {contract.semantic_contract_sha256} "
                    f"{contract.scenario_id} {contract.title}"
                ),
                "description": anchors,
                "intent": contract.user_task,
                "actions": [
                    {
                        "actor": "user",
                        "content": contract.user_task,
                    }
                ],
            }
        )
    return {
        "id": dataset_id,
        "request_id": request_id,
        "name": dataset_name,
        "created_at": "2026-07-26T00:00:00Z",
        "dataset_source": {
            "dataset_type": EXPECTED_SERVER_DATASET_TYPE,
            "runs": runs,
            "total_runs": EXPECTED_CASE_COUNT,
        },
    }


class _FakeClient:
    def __init__(
        self,
        *,
        request_responses=None,
        dataset_pages=None,
        datasets=None,
        create_request_response=None,
        create_request_error=None,
        create_run_response=None,
        create_run_error=None,
    ):
        self.timeout = 30
        self.request_responses = list(request_responses or [])
        self.dataset_pages = dict(dataset_pages or {})
        self.datasets = dict(datasets or {})
        self.create_request_response = create_request_response or {"id": 7}
        self.create_request_error = create_request_error
        self.create_run_response = create_run_response or {"id": 99}
        self.create_run_error = create_run_error
        self.create_request_calls = []
        self.get_request_calls = []
        self.list_dataset_calls = []
        self.get_dataset_calls = []
        self.create_run_calls = []

    def create_request(self, **kwargs):
        self.create_request_calls.append(kwargs)
        if self.create_request_error is not None:
            raise self.create_request_error
        return self.create_request_response

    def get_request(self, request_id):
        self.get_request_calls.append(
            {"request_id": request_id, "timeout": self.timeout}
        )
        if not self.request_responses:
            raise AssertionError("no fake request response")
        return self.request_responses.pop(0)

    def list_datasets(self, **kwargs):
        self.list_dataset_calls.append(kwargs)
        return self.dataset_pages[kwargs.get("cursor")]

    def get_dataset(self, dataset_id, **kwargs):
        self.get_dataset_calls.append(
            {"dataset_id": dataset_id, **kwargs}
        )
        return self.datasets[dataset_id]

    def create_run(self, **kwargs):
        self.create_run_calls.append(kwargs)
        if self.create_run_error is not None:
            raise self.create_run_error
        return self.create_run_response


class _FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def _load_acquisition_script():
    script_path = ROOT / "scripts" / "a2_acquire_releasefoundry_calibration_dataset.py"
    spec = importlib.util.spec_from_file_location(
        "a2_acquire_releasefoundry_calibration_dataset",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_request_builder_is_deterministic_and_exactly_six_cases():
    first = _spec()
    second = _spec()

    assert first.request_sha256 == second.request_sha256
    assert (
        first.request_sha256
        == "sha256:df6b771a9b1bc5858424b93cc49ddbe2bdaf4a32b25efe2318abeffe294c36f9"
    )
    assert first.case_contract_set_sha256 == second.case_contract_set_sha256
    assert first.dataset_name == EXPECTED_DATASET_NAME
    assert first.server_dataset_name == EXPECTED_SERVER_DATASET_NAME
    assert first.request["metadata"]["dataset_name"] == EXPECTED_DATASET_NAME
    assert len(first.case_contracts) == EXPECTED_CASE_COUNT
    assert len({case.test_id for case in first.case_contracts}) == 6
    assert first.request["generation_options"]["scenario_count"] == 6
    assert first.request["test_config"]["num_variations"] == 6
    assert all(
        not first.request["agent"]["accepted_inputs"][modality]
        for modality in ("audio", "file", "image", "video", "conversation")
    )
    assert first.request["agent"]["accepted_inputs"]["text"] is True


def test_request_omits_raw_candidate_answers_and_synthetic_secret():
    spec = _spec()
    serialized = json.dumps(spec.request, sort_keys=True)

    assert "API key is releasefoundry_live_" not in serialized
    assert "I moved the meeting to next Friday." not in serialized
    assert "candidate_trace_sha256" in serialized
    assert_no_sensitive_material(spec.request)


def test_request_builder_rejects_case_map_projection_tampering(tmp_path):
    scratch_root = tmp_path / "repo"
    packet = json.loads(
        (
            ROOT
            / "fixtures/a2/calibration/a2_releasefoundry_grading_collection_packet.json"
        ).read_text(encoding="utf-8")
    )
    packet["cases"][0]["case_id"] = "sample-a2-wrong"
    packet_path = scratch_root / "packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    required_refs = {
        "packages/scenarios/a2_g3_full_pack.json",
        "fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json",
        *(case["fixture_ref"] for case in packet["cases"]),
    }
    for ref in required_refs:
        destination = scratch_root / ref
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / ref, destination)

    with pytest.raises(
        DatasetAcquisitionError,
        match="case_map_binding_mismatch",
    ):
        build_calibration_dataset_request(
            root=scratch_root,
            packet_path=packet_path,
        )


def test_create_request_is_called_exactly_once_on_success():
    spec = _spec()
    client = _FakeClient(create_request_response={"id": 17})

    request_id = create_request_once(client, spec)

    assert request_id == 17
    assert len(client.create_request_calls) == 1
    assert client.create_request_calls[0]["request_name"] == spec.request_name


def test_create_request_is_not_retried_after_exception():
    spec = _spec()
    client = _FakeClient(create_request_error=RuntimeError("timeout"))

    with pytest.raises(RuntimeError, match="timeout"):
        create_request_once(client, spec)

    assert len(client.create_request_calls) == 1


def test_wait_for_request_terminal_accepts_completed_and_bounds_timeout():
    client = _FakeClient(
        request_responses=[
            {"id": 7, "request_status": "queued"},
            {"id": 7, "request_status": "processing"},
            {"id": 7, "request_status": "completed"},
        ]
    )
    clock = _FakeClock()

    response = wait_for_request_terminal(
        client,
        7,
        timeout_seconds=10,
        poll_interval_seconds=2,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert response["request_status"] == "completed"
    assert clock.sleeps == [2, 2]
    assert [call["timeout"] for call in client.get_request_calls] == [10, 8, 6]
    assert client.timeout == 30


@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("failed", "request_terminal_failure:failed"),
        ("cancelled", "request_terminal_failure:cancelled"),
        ("mystery", "request_status_unknown:mystery"),
    ],
)
def test_wait_for_request_terminal_fails_closed_on_terminal_or_unknown_state(
    status,
    error,
):
    client = _FakeClient(
        request_responses=[{"id": 7, "request_status": status}]
    )

    with pytest.raises(DatasetAcquisitionError, match=error):
        wait_for_request_terminal(
            client,
            7,
            timeout_seconds=10,
            poll_interval_seconds=1,
        )


def test_wait_for_request_terminal_uses_monotonic_timeout():
    client = _FakeClient(
        request_responses=[
            {"id": 7, "request_status": "queued"},
            {"id": 7, "request_status": "queued"},
        ]
    )
    clock = _FakeClock()

    with pytest.raises(DatasetAcquisitionError, match="request_poll_timeout"):
        wait_for_request_terminal(
            client,
            7,
            timeout_seconds=2,
            poll_interval_seconds=2,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

    assert len(client.get_request_calls) == 1


def test_dataset_discovery_pages_by_request_id_not_list_position():
    client = _FakeClient(
        dataset_pages={
            None: {
                "datasets": [
                    {"id": 1, "request_id": 1},
                    {"id": 2, "request_id": 2},
                ],
                "next_cursor": 2,
            },
            2: {
                "datasets": [
                    {"id": 3, "request_id": 7},
                    {"id": 4, "request_id": 4},
                ],
                "next_cursor": None,
            },
        }
    )

    dataset = find_single_dataset_for_request(client, 7, page_limit=2)

    assert dataset["id"] == 3
    assert [call["cursor"] for call in client.list_dataset_calls] == [None, 2]
    assert all(
        call["include_signed_urls"] is False
        for call in client.list_dataset_calls
    )


@pytest.mark.parametrize(
    ("datasets", "error"),
    [
        ([{"id": 1, "request_id": 1}], "request_dataset_not_found"),
        (
            [
                {"id": 1, "request_id": 7},
                {"id": 2, "request_id": 7},
            ],
            "request_dataset_ambiguous",
        ),
    ],
)
def test_dataset_discovery_requires_exactly_one_request_match(datasets, error):
    client = _FakeClient(
        dataset_pages={
            None: {
                "datasets": datasets,
                "next_cursor": None,
            }
        }
    )

    with pytest.raises(DatasetAcquisitionError, match=error):
        find_single_dataset_for_request(client, 7)


def test_dataset_discovery_rejects_cursor_loop():
    client = _FakeClient(
        dataset_pages={
            None: {"datasets": [], "next_cursor": 9},
            9: {"datasets": [], "next_cursor": 9},
        }
    )

    with pytest.raises(DatasetAcquisitionError, match="dataset_cursor_loop"):
        find_single_dataset_for_request(client, 7)


def test_fetch_dataset_rejects_response_id_different_from_requested_id():
    spec = _spec()
    client = _FakeClient(
        dataset_pages={
            None: {
                "datasets": [{"id": 42, "request_id": 7}],
                "next_cursor": None,
            }
        },
        datasets={42: _live_dataset(spec, dataset_id=43)},
    )

    with pytest.raises(
        DatasetAcquisitionError,
        match="get_dataset_id_mismatch",
    ):
        fetch_and_verify_dataset(client, request_id=7, spec=spec)


def test_verify_dataset_accepts_dict_or_list_runs():
    spec = _spec()
    list_dataset = _live_dataset(spec)
    dict_dataset = deepcopy(list_dataset)
    dict_dataset["dataset_source"]["runs"] = {
        run["run_id"]: run for run in dict_dataset["dataset_source"]["runs"]
    }

    first = verify_calibration_dataset(list_dataset, request_id=7, spec=spec)
    second = verify_calibration_dataset(dict_dataset, request_id=7, spec=spec)

    assert first.dataset_id == 42
    assert second.dataset_id == 42
    assert first.dataset_content_sha256 != second.dataset_content_sha256


@pytest.mark.parametrize(
    ("mutator", "error"),
    [
        (
            lambda dataset: dataset.update({"request_id": 8}),
            "dataset_request_id_mismatch",
        ),
        (
            lambda dataset: dataset.update({"name": "wrong"}),
            "dataset_name_mismatch",
        ),
        (
            lambda dataset: dataset["dataset_source"].update(
                {"dataset_type": "runs"}
            ),
            "dataset_type_mismatch",
        ),
        (
            lambda dataset: dataset["dataset_source"].update({"total_runs": 5}),
            "dataset_total_runs_mismatch",
        ),
        (
            lambda dataset: dataset["dataset_source"]["runs"].pop(),
            "dataset_run_count_mismatch",
        ),
        (
            lambda dataset: dataset["dataset_source"]["runs"][0].update(
                {"title": "marker removed"}
            ),
            "dataset_run_contract_hash_missing",
        ),
    ],
)
def test_verify_dataset_rejects_identity_and_content_mismatches(
    mutator,
    error,
):
    spec = _spec()
    dataset = _live_dataset(spec)
    mutator(dataset)

    with pytest.raises(DatasetAcquisitionError, match=error):
        verify_calibration_dataset(dataset, request_id=7, spec=spec)


def test_verify_dataset_rejects_duplicate_marker():
    spec = _spec()
    dataset = _live_dataset(spec)
    dataset["dataset_source"]["runs"][1] = deepcopy(
        dataset["dataset_source"]["runs"][0]
    )

    with pytest.raises(
        DatasetAcquisitionError,
        match="dataset_run_case_marker_duplicate",
    ):
        verify_dataset_case_contracts(dataset, spec.case_contracts)


def test_verify_dataset_rejects_unexpected_marker():
    spec = _spec()
    dataset = _live_dataset(spec)
    dataset["dataset_source"]["runs"][0]["description"] += (
        " releasefoundry-a2-g3-unexpected"
    )

    with pytest.raises(
        DatasetAcquisitionError,
        match="dataset_run_unexpected_case_marker",
    ):
        verify_dataset_case_contracts(dataset, spec.case_contracts)


def test_verify_dataset_rejects_semantic_anchor_tampering():
    spec = _spec()
    dataset = _live_dataset(spec)
    contract = spec.case_contracts[0]
    run = dataset["dataset_source"]["runs"][0]
    run["description"] = run["description"].replace(
        contract.expected_behaviors[0],
        "different behavior",
    )

    with pytest.raises(
        DatasetAcquisitionError,
        match="dataset_run_semantic_anchor_missing",
    ):
        verify_dataset_case_contracts(dataset, spec.case_contracts)


@pytest.mark.parametrize(
    "payload",
    [
        {"authorization": "redacted"},
        {"nested": {"signed_url": "https://example.invalid"}},
        {"value": "https://x.invalid?a=1&X-Amz-Signature=abc"},
        {"value": r"C:\Users\private\evidence.json"},
        {"value": "/home/user/private/evidence.json"},
    ],
)
def test_sensitive_material_scanner_fails_closed(payload):
    with pytest.raises(DatasetAcquisitionError):
        assert_no_sensitive_material(payload)


@pytest.mark.parametrize(
    "synthetic_value",
    [
        "Bearer abcdefghijklmnop",
        "sk-synthetic-security-test-only",
        "releasefoundry_live_synthetic_security_test_only",
        "AKIASYNTHETICEXAMPLE",
    ],
)
def test_sensitive_material_scanner_allows_synthetic_attack_evidence(
    synthetic_value,
):
    assert_no_sensitive_material({"security_test_input": synthetic_value})


def test_sensitive_material_scanner_rejects_exact_live_secret_only():
    live_secret = "releasefoundry_live_actual_private_value"

    assert_no_sensitive_material(
        {"security_test_input": "releasefoundry_live_different_synthetic_value"},
        forbidden_values=(live_secret,),
    )
    with pytest.raises(
        DatasetAcquisitionError,
        match="forbidden_value_detected",
    ):
        assert_no_sensitive_material(
            {"value": f"Bearer {live_secret}"},
            forbidden_values=(live_secret,),
        )


def test_dataset_discovery_rejects_exact_live_secret_without_exposing_it():
    live_secret = "releasefoundry_live_actual_private_value"
    client = _FakeClient(
        dataset_pages={
            None: {
                "datasets": [
                    {
                        "id": 3,
                        "request_id": 7,
                        "description": f"Bearer {live_secret}",
                    }
                ],
                "next_cursor": None,
            }
        }
    )

    with pytest.raises(
        DatasetAcquisitionError,
        match="forbidden_value_detected",
    ) as exc_info:
        find_single_dataset_for_request(
            client,
            7,
            forbidden_values=(live_secret,),
        )

    assert live_secret not in str(exc_info.value)


def test_private_writer_rejects_path_outside_private_root(tmp_path):
    private_root = tmp_path / "private"
    outside = tmp_path / "outside.json"

    with pytest.raises(
        DatasetAcquisitionError,
        match="private_path_outside_private_root",
    ):
        atomic_write_private_json(
            outside,
            {"safe": True},
            private_root=private_root,
        )


def test_verified_manifest_is_atomic_and_loadable(tmp_path):
    spec = _spec()
    manifest = verify_calibration_dataset(
        _live_dataset(spec),
        request_id=7,
        spec=spec,
    )
    private_root = tmp_path / "private"
    path = private_root / "manifest.json"

    write_verified_manifest(path, manifest, private_root=private_root)
    loaded = load_verified_manifest(path, private_root=private_root)

    assert loaded == manifest
    assert not list(private_root.glob("*.tmp"))


def test_paid_gate_returns_explicit_dataset_id_only_for_verified_live_content():
    spec = _spec()
    dataset = _live_dataset(spec)
    manifest = verify_calibration_dataset(dataset, request_id=7, spec=spec)

    assert (
        assert_paid_run_allowed(
            manifest,
            live_dataset=dataset,
            spec=spec,
        )
        == 42
    )

    tampered = deepcopy(dataset)
    tampered["dataset_source"]["runs"][0]["description"] += " changed"
    with pytest.raises(
        DatasetAcquisitionError,
        match="paid_gate_dataset_content_mismatch",
    ):
        assert_paid_run_allowed(
            manifest,
            live_dataset=tampered,
            spec=spec,
        )


def test_paid_gate_binds_server_dataset_name_not_request_metadata_name():
    spec = _spec()
    dataset = _live_dataset(spec)
    manifest = verify_calibration_dataset(dataset, request_id=7, spec=spec)
    wrong_name_manifest = replace(manifest, dataset_name=spec.dataset_name)

    with pytest.raises(
        DatasetAcquisitionError,
        match="paid_gate_dataset_name_mismatch",
    ):
        assert_paid_run_allowed(
            wrong_name_manifest,
            live_dataset=dataset,
            spec=spec,
        )


def test_paid_create_run_is_blocked_before_client_when_manifest_missing(
    tmp_path,
):
    spec = _spec()
    client = _FakeClient()
    private_root = tmp_path / "private"

    with pytest.raises(DatasetAcquisitionError):
        create_run_once_with_verified_identity(
            client,
            manifest_path=private_root / "missing.json",
            private_root=private_root,
            spec=spec,
            result={"tests": []},
        )

    assert client.get_dataset_calls == []
    assert client.create_run_calls == []


def test_paid_create_run_does_not_mutate_when_manifest_is_stale(tmp_path):
    spec = _spec()
    dataset = _live_dataset(spec)
    manifest = verify_calibration_dataset(dataset, request_id=7, spec=spec)
    payload = manifest.private_payload()
    payload["request_sha256"] = "sha256:" + ("0" * 64)
    private_root = tmp_path / "private"
    path = private_root / "manifest.json"
    atomic_write_private_json(path, payload, private_root=private_root)
    client = _FakeClient(datasets={42: dataset})

    with pytest.raises(
        DatasetAcquisitionError,
        match="paid_gate_request_hash_mismatch",
    ):
        create_run_once_with_verified_identity(
            client,
            manifest_path=path,
            private_root=private_root,
            spec=spec,
            result={"tests": []},
        )

    assert client.get_dataset_calls == []
    assert client.create_run_calls == []


def test_paid_create_run_fetches_without_signed_urls_then_mutates_once(tmp_path):
    spec = _spec()
    dataset = _live_dataset(spec)
    manifest = verify_calibration_dataset(dataset, request_id=7, spec=spec)
    private_root = tmp_path / "private"
    path = private_root / "manifest.json"
    write_verified_manifest(path, manifest, private_root=private_root)
    client = _FakeClient(datasets={42: dataset})

    result = create_run_once_with_verified_identity(
        client,
        manifest_path=path,
        private_root=private_root,
        spec=spec,
        result={"tests": [{"test_id": "one"}]},
    )

    assert result == {"id": 99}
    assert client.get_dataset_calls == [
        {"dataset_id": 42, "include_signed_urls": False}
    ]
    assert client.create_run_calls == [
        {
            "dataset_id": 42,
            "result": {"tests": [{"test_id": "one"}]},
        }
    ]


def test_paid_create_run_is_not_retried_after_exception(tmp_path):
    spec = _spec()
    dataset = _live_dataset(spec)
    manifest = verify_calibration_dataset(dataset, request_id=7, spec=spec)
    private_root = tmp_path / "private"
    path = private_root / "manifest.json"
    write_verified_manifest(path, manifest, private_root=private_root)
    client = _FakeClient(
        datasets={42: dataset},
        create_run_error=RuntimeError("ambiguous timeout"),
    )

    with pytest.raises(RuntimeError, match="ambiguous timeout"):
        create_run_once_with_verified_identity(
            client,
            manifest_path=path,
            private_root=private_root,
            spec=spec,
            result={"tests": []},
        )

    assert len(client.create_run_calls) == 1


def test_cli_default_dry_run_does_not_require_key_or_create_client(capsys):
    script = _load_acquisition_script()
    client_calls = []

    def forbidden_client_factory(timeout):
        client_calls.append(timeout)
        raise AssertionError("dry-run must not construct a client")

    assert (
        script.main(
            [],
            client_factory=forbidden_client_factory,
            environ={},
        )
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["mode"] == "dry_run"
    assert summary["network_calls"] == 0
    assert summary["mutating_calls"] == 0
    assert client_calls == []


def test_cli_resume_passes_live_key_only_to_exact_secret_scanner(
    tmp_path,
    monkeypatch,
    capsys,
):
    script = _load_acquisition_script()
    private_root = tmp_path / "private"
    request_ref = private_root / "request.json"
    manifest_path = private_root / "manifest.json"
    output = tmp_path / "receipt.json"
    spec = _spec()
    script.write_request_ref(
        request_ref,
        private_root=private_root,
        request_id=7,
        spec=spec,
    )
    monkeypatch.setattr(script, "PRIVATE_ROOT", private_root.resolve())
    captured = {}

    def blocked_fetch(
        client,
        *,
        request_id,
        spec,
        forbidden_values,
    ):
        captured["forbidden_values"] = forbidden_values
        raise DatasetAcquisitionError("expected_test_blocker")

    monkeypatch.setattr(script, "fetch_and_verify_dataset", blocked_fetch)
    client = _FakeClient(
        request_responses=[
            {"id": 7, "request_status": "completed"},
        ]
    )
    live_secret = "releasefoundry_live_test_value_never_persist"

    result = script.main(
        [
            "--resume",
            "--request-ref",
            str(request_ref),
            "--private-manifest",
            str(manifest_path),
            "--output",
            str(output),
        ],
        client_factory=lambda timeout: client,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": live_secret},
    )

    assert result == 2
    assert captured["forbidden_values"] == (live_secret,)
    receipt_text = output.read_text(encoding="utf-8")
    captured_output = capsys.readouterr()
    assert live_secret not in receipt_text
    assert live_secret not in captured_output.out
    assert live_secret not in captured_output.err


@pytest.mark.parametrize(
    "args",
    [
        ["--execute"],
        ["--allow-mutate"],
        ["--resume", "--allow-mutate"],
    ],
)
def test_cli_requires_unambiguous_mutation_authorization(args):
    script = _load_acquisition_script()

    with pytest.raises(SystemExit):
        script.main(args, client_factory=lambda timeout: None, environ={})
