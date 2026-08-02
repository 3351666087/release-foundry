from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from services.judge.releasefoundry_dataset_acquisition import (
    DatasetAcquisitionError,
    build_calibration_dataset_request,
    write_request_ref,
)
from services.judge.releasefoundry_dataset_mapping import build_dataset_mapping_proposal


ROOT = Path(__file__).resolve().parents[2]


def _spec():
    return build_calibration_dataset_request(root=ROOT)


def _generated_dataset(spec, *, ambiguous: bool = False):
    run_order = [5, 1, 0, 4, 2, 3]
    runs = []
    for contract_index in run_order:
        contract = spec.case_contracts[contract_index]
        anchors = [
            contract.title,
            contract.user_task,
            *contract.expected_behaviors[:2],
            contract.primary_failure_class,
        ]
        runs.append(
            {
                "run_id": f"server-{len(runs) + 1}",
                "title": anchors[0],
                "description": " | ".join(anchors[1:]),
                "actions": [{"actor": "user", "content": contract.user_task}],
            }
        )
    if ambiguous:
        runs[0] = dict(runs[1])
    return {
        "id": 42,
        "request_id": 7,
        "name": spec.server_dataset_name,
        "dataset_source": {
            "dataset_type": "multi_run_storyboard",
            "total_runs": 6,
            "runs": runs,
        },
    }


def test_mapping_proposal_is_unique_but_never_grants_authority():
    spec = _spec()

    proposal = build_dataset_mapping_proposal(
        _generated_dataset(spec),
        request_id=7,
        spec=spec,
    )

    assert len(proposal.mappings) == 6
    assert proposal.global_assignment_margin > 0
    assert all(mapping.margin > 0 for mapping in proposal.mappings)
    assert {mapping.server_slot for mapping in proposal.mappings} == set(range(1, 7))

    private = proposal.private_payload()
    public = proposal.public_receipt()
    assert private["mapping_authority"] == "machine_proposal_only"
    assert private["review_state"] == "pending_human_review"
    assert private["authority_limits"]["paid_create_run_allowed"] is False
    assert public["mapping_state"] == "machine_proposed"
    assert public["human_review_required"] is True
    assert public["exact_identity_verified"] is False
    assert public["human_adjudicated"] is False
    assert public["paid_create_run_allowed"] is False
    assert public["blockers"] == ["human_adjudicated_mapping_required"]
    assert "dataset_id" not in public
    assert "request_id" not in public


def test_mapping_proposal_rejects_ambiguous_server_runs():
    spec = _spec()

    with pytest.raises(
        DatasetAcquisitionError,
        match="dataset_mapping_.*ambiguous",
    ):
        build_dataset_mapping_proposal(
            _generated_dataset(spec, ambiguous=True),
            request_id=7,
            spec=spec,
        )


def test_mapping_proposal_rejects_request_binding_mismatch():
    spec = _spec()
    dataset = _generated_dataset(spec)
    dataset["request_id"] = 8

    with pytest.raises(
        DatasetAcquisitionError,
        match="dataset_request_id_mismatch",
    ):
        build_dataset_mapping_proposal(dataset, request_id=7, spec=spec)


def test_mapping_cli_dry_run_is_zero_network(capsys):
    script = _load_script()
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
    payload = json.loads(capsys.readouterr().out)
    assert payload["network_calls"] == 0
    assert payload["mutating_calls"] == 0
    assert payload["paid_create_run_allowed"] is False
    assert client_calls == []


def test_mapping_cli_fetch_is_read_only_and_writes_pending_review(
    tmp_path,
    monkeypatch,
):
    script = _load_script()
    spec = _spec()
    private_root = tmp_path / "private"
    request_ref = private_root / "request.json"
    private_review = private_root / "review.json"
    public_receipt = tmp_path / "receipt.json"
    write_request_ref(
        request_ref,
        private_root=private_root,
        request_id=7,
        spec=spec,
    )
    monkeypatch.setattr(script, "PRIVATE_ROOT", private_root.resolve())

    class ReadOnlyClient:
        def __init__(self):
            self.calls = []

        def get_request(self, request_id):
            self.calls.append(("get_request", request_id))
            return {"id": request_id, "request_status": "completed"}

        def list_datasets(self, **kwargs):
            self.calls.append(("list_datasets", kwargs))
            return {
                "datasets": [{"id": 42, "request_id": 7}],
                "next_cursor": None,
            }

        def get_dataset(self, dataset_id, include_signed_urls):
            self.calls.append(
                ("get_dataset", dataset_id, include_signed_urls)
            )
            return _generated_dataset(spec)

    client = ReadOnlyClient()
    result = script.main(
        [
            "--fetch",
            "--timeout",
            "1",
            "--poll-interval",
            "0.01",
            "--request-ref",
            str(request_ref),
            "--private-review",
            str(private_review),
            "--output",
            str(public_receipt),
        ],
        client_factory=lambda timeout: client,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": "synthetic-live-key-for-test"},
    )

    assert result == 0
    assert [call[0] for call in client.calls] == [
        "get_request",
        "list_datasets",
        "get_dataset",
    ]
    private = json.loads(private_review.read_text(encoding="utf-8"))
    public = json.loads(public_receipt.read_text(encoding="utf-8"))
    assert private["review_state"] == "pending_human_review"
    assert private["authority_limits"]["paid_create_run_allowed"] is False
    assert public["mapping_state"] == "machine_proposed"
    assert public["paid_create_run_allowed"] is False
    assert "synthetic-live-key-for-test" not in private_review.read_text(
        encoding="utf-8"
    )
    assert "synthetic-live-key-for-test" not in public_receipt.read_text(
        encoding="utf-8"
    )


def _load_script():
    script_path = ROOT / "scripts" / "a2_prepare_releasefoundry_dataset_mapping_review.py"
    spec = importlib.util.spec_from_file_location(
        "a2_prepare_releasefoundry_dataset_mapping_review",
        script_path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
