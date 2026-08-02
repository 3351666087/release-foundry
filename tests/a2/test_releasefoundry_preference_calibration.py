from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from scripts import a2_releasefoundry_live_calibration as calibration
from scripts import a2_releasefoundry_preference_calibration as preference
from scripts import a2_build_releasefoundry_disagreement_review_queue as review_queue
from services.judge.result_persistence import stable_hash


DATASET_IDENTITY_HASH = "sha256:" + ("d" * 64)


def _write_fixture(
    path: Path,
    *,
    final_response: str = "PRIVATE_OBSERVED_RESPONSE_8f47b312",
    tool_calls: list[dict[str, Any]] | None = None,
) -> None:
    path.write_text(
        json.dumps(
            {
                "run": {
                    "tool_calls": tool_calls or [],
                    "final_response": final_response,
                }
            }
        ),
        encoding="utf-8",
    )


def _variant(
    index: int,
    fixture_path: Path,
    *,
    expected_tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "variant_id": f"private-variant-{index:03d}",
        "case_id": f"private-case-{index:03d}",
        "fixture_ref": str(fixture_path.resolve()),
        "prompt": f"PRIVATE_PROMPT_{index:03d}_0eac71d9",
        "expected_response": f"PRIVATE_REFERENCE_{index:03d}_4c26f80a",
        "expected_tool_calls": expected_tool_calls or [],
        "prompt_variant": f"prompt-{index:03d}",
        "expected_variant": f"expected-{index:03d}",
        "channel": "text",
        "expected_passed": True,
    }


def _queue(variants: list[dict[str, Any]]) -> dict[str, Any]:
    items = []
    for variant in variants:
        variant_id = str(variant["variant_id"])
        items.append(
            {
                "review_item_id": stable_hash(f"review:{variant_id}"),
                "variant_id_hash": review_queue._sha256_text(
                    f"a2:releasefoundry-exploratory-variant:v1:{variant_id}"
                ),
                "case_id": variant["case_id"],
                "channel": variant["channel"],
                "prompt_variant": variant["prompt_variant"],
                "expected_variant": variant["expected_variant"],
            }
        )
    return {
        "schema_version": "test.queue.v1",
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "review_item_count": len(items),
        "items": items,
    }


def _graded_test(
    test_id: str,
    *,
    similarity: float,
    verdict: str,
    coherence: float,
) -> dict[str, Any]:
    return {
        "test_id": test_id,
        "status": "completed",
        "action_results": [
            {
                "actor": "agent",
                "action_type": "text",
                "action_index": 1,
                "actual_response": {"text": "PRIVATE_SERVER_RESPONSE_610a9bde"},
                "semantic_similarity": similarity,
                "llm_judgment": {"verdict": verdict},
            }
        ],
        "coherence": {
            "score": coherence,
            "summary": "PRIVATE_SERVER_SUMMARY_339ea64c",
            "issues": [],
        },
    }


def _dataset_binding(dataset_id: int = 42) -> dict[str, Any]:
    return {
        "schema_version": "test.dataset_binding.v1",
        "dataset_id": dataset_id,
        "dataset_name": "PRIVATE_FIXED_DATASET_c60a5a17",
        "dataset_content_sha256": DATASET_IDENTITY_HASH,
        "evidence_lane": calibration.EXPLORATORY_EVIDENCE_LANE,
        "training_eligible": False,
        "release_authority": False,
    }


def _journal(
    test_ids: list[str],
    *,
    run_id: str,
    similarity: float,
    verdict: str,
    coherence: float,
    binding: dict[str, Any] | None = None,
    create_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    dataset_binding = copy.deepcopy(binding or _dataset_binding())
    tests = [
        _graded_test(
            test_id,
            similarity=similarity,
            verdict=verdict,
            coherence=coherence,
        )
        for test_id in test_ids
    ]
    return {
        "dataset_binding": dataset_binding,
        "preflight_http_events": [],
        "batches": [
            {
                "status": "completed",
                "variant_ids": list(test_ids),
                "terminal_response": {
                    "id": run_id,
                    "dataset": dataset_binding["dataset_id"],
                    "result": {
                        "status": "completed",
                        "tests": tests,
                    },
                },
                "http_events": create_events
                if create_events is not None
                else [
                    {
                        "operation": "create_run",
                        "status": "ok",
                        "retry": False,
                    }
                ],
            }
        ],
    }


def _strategy_journals(
    matrices: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    scores = {
        "observed_fixture": (0.72, "acceptable", 0.8),
        "reference_aligned": (0.99, "match", 1.0),
        "degraded_control": (0.05, "major_issue", 0.2),
    }
    journals = {}
    for strategy in preference.STRATEGIES:
        similarity, verdict, coherence = scores[strategy]
        journals[strategy] = _journal(
            [str(item["variant_id"]) for item in matrices[strategy]],
            run_id=f"private-run-{strategy}",
            similarity=similarity,
            verdict=verdict,
            coherence=coherence,
        )
    return journals


def _generated_dataset(
    spec: calibration.CalibrationDatasetRequest,
    *,
    dataset_id: int = 42,
) -> dict[str, Any]:
    runs = []
    for contract_index in (5, 1, 0, 4, 2, 3):
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
                "actions": [
                    {"actor": "user", "content": contract.user_task}
                ],
            }
        )
    return {
        "id": dataset_id,
        "request_id": 7,
        "name": spec.server_dataset_name,
        "dataset_source": {
            "dataset_type": "multi_run_storyboard",
            "total_runs": len(runs),
            "runs": runs,
        },
    }


def _write_exploratory_mapping(
    root: Path,
) -> tuple[dict[str, Any], Path, Path]:
    spec = calibration.build_calibration_dataset_request(
        root=calibration.ROOT
    )
    dataset = _generated_dataset(spec)
    proposal = calibration.build_dataset_mapping_proposal(
        dataset,
        request_id=7,
        spec=spec,
    )
    private_path = root / "private" / "mapping.private.json"
    receipt_path = root / "mapping-receipt.json"
    private_path.write_text(
        json.dumps(proposal.private_payload()),
        encoding="utf-8",
    )
    receipt_path.write_text(
        json.dumps(proposal.public_receipt()),
        encoding="utf-8",
    )
    return dataset, private_path, receipt_path


def _live_args(
    *,
    private_mapping: Path,
    mapping_receipt: Path,
    private_journal: Path,
    public_output: Path,
    poll_timeout: int = 2,
) -> list[str]:
    return [
        "--execute",
        "--allow-mutate",
        "--allow-unverified-exploration",
        "--batch-size",
        "1",
        "--batches",
        "1",
        "--poll-timeout",
        str(poll_timeout),
        "--poll-interval",
        "0",
        "--max-retries",
        "0",
        "--mapping-private-review",
        str(private_mapping),
        "--mapping-receipt",
        str(mapping_receipt),
        "--private-journal",
        str(private_journal),
        "--public-output",
        str(public_output),
    ]


class SuccessfulReleaseFoundryClient:
    def __init__(
        self,
        dataset: dict[str, Any],
        *,
        run_id: int,
        submitted_result: dict[str, Any] | None = None,
    ) -> None:
        self.dataset = dataset
        self.run_id = run_id
        self.submitted_result = copy.deepcopy(submitted_result)
        self.calls: Counter[str] = Counter()

    def _make_request(self, function: str, **params: Any) -> dict[str, Any]:
        self.calls[function] += 1
        if function == "get_dataset":
            return copy.deepcopy(self.dataset)
        if function == "create_run":
            self.submitted_result = copy.deepcopy(params["result"])
            return {"id": self.run_id}
        if function == "get_run":
            if self.submitted_result is None:
                raise AssertionError("submitted result is required for polling")
            tests = copy.deepcopy(self.submitted_result["tests"])
            for test in tests:
                test["status"] = "completed"
                final = next(
                    action
                    for action in test["action_results"]
                    if action.get("actor") == "agent"
                    and action.get("action_type") == "text"
                )
                actual = final["actual_response"]["text"]
                if actual.startswith("PRIVATE_REFERENCE_"):
                    similarity, verdict, coherence = 0.99, "match", 1.0
                elif actual.startswith("PRIVATE_OBSERVED_RESPONSE_"):
                    similarity, verdict, coherence = (
                        0.72,
                        "acceptable",
                        0.8,
                    )
                else:
                    similarity, verdict, coherence = (
                        0.05,
                        "major_issue",
                        0.2,
                    )
                final["semantic_similarity"] = similarity
                final["llm_judgment"] = {"verdict": verdict}
                test["coherence"] = {
                    "score": coherence,
                    "summary": "server grading complete",
                    "issues": [],
                }
            return {
                "id": self.run_id,
                "dataset": self.dataset["id"],
                "result": {
                    "status": "completed",
                    "tests": tests,
                },
            }
        raise AssertionError(f"unexpected call: {function}")

    def get_dataset(
        self,
        dataset_id: int,
        *,
        include_signed_urls: bool,
    ) -> dict[str, Any]:
        return self._make_request(
            "get_dataset",
            dataset_id=dataset_id,
            include_signed_urls=include_signed_urls,
        )

    def create_run(
        self,
        *,
        dataset_id: int,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return self._make_request(
            "create_run",
            dataset_id=dataset_id,
            result=result,
        )

    def get_run(self, run_id: int) -> dict[str, Any]:
        return self._make_request("get_run", run_id=run_id)


def test_builds_35_fixed_candidates_with_identical_strategy_test_sets(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    variants = [_variant(index, fixture_path) for index in range(35)]
    queue = _queue(variants)

    matrices = preference.build_strategy_matrices(queue, variants)

    expected_ids = {item["variant_id"] for item in variants}
    assert {strategy: len(matrix) for strategy, matrix in matrices.items()} == {
        strategy: 35 for strategy in preference.STRATEGIES
    }
    assert all(
        {item["variant_id"] for item in matrices[strategy]} == expected_ids
        for strategy in preference.STRATEGIES
    )
    assert all(
        item["candidate_strategy"] == strategy
        for strategy in preference.STRATEGIES
        for item in matrices[strategy]
    )

    duplicate = copy.deepcopy(queue)
    duplicate["items"].append(copy.deepcopy(duplicate["items"][0]))
    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="queue_variant_hash_not_unique",
    ):
        preference.build_strategy_matrices(duplicate, variants)

    missing = copy.deepcopy(queue)
    missing["items"][0]["variant_id_hash"] = stable_hash("not-in-matrix")
    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="queue_variant_not_found_in_matrix",
    ):
        preference.build_strategy_matrices(missing, variants)


def test_quality_ladder_builds_eight_isolated_candidate_mutations(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    observed_tool_calls = [
        {
            "tool": "file.read",
            "args": {"path": "PRIVATE_OBSERVED_PATH_001"},
        }
    ]
    _write_fixture(
        fixture_path,
        final_response="Observed fixture response.",
        tool_calls=observed_tool_calls,
    )
    expected_tool_calls = [
        {
            "tool": "file.fetch",
            "args": {"url": "https://private.invalid/source"},
            "args_mode": "exact",
        },
        {
            "tool": "file.decode",
            "args": {"format": "png"},
            "args_mode": "exact",
        },
        {
            "tool": "vision.inspect",
            "args": {"region": "red Billing banner"},
            "args_mode": "exact",
        },
    ]
    variants = [
        _variant(
            index,
            fixture_path,
            expected_tool_calls=expected_tool_calls,
        )
        for index in range(12)
    ]
    for variant in variants:
        variant["expected_response"] = (
            "The red Billing banner is exactly visible."
        )
    matrices = preference.build_strategy_matrices(
        _queue(variants),
        variants,
        strategies=preference.QUALITY_LADDER_STRATEGIES,
    )

    expected_ids = {item["variant_id"] for item in variants}
    assert set(matrices) == set(preference.QUALITY_LADDER_STRATEGIES)
    assert all(
        len(matrices[strategy]) == 12
        and {
            item["variant_id"] for item in matrices[strategy]
        }
        == expected_ids
        for strategy in preference.QUALITY_LADDER_STRATEGIES
    )

    candidates = {
        strategy: matrices[strategy][0]["candidate_run"]
        for strategy in preference.QUALITY_LADDER_STRATEGIES
    }
    reference = candidates["reference_aligned"]
    assert candidates["minor_final_answer_defect"]["tool_calls"] == (
        reference["tool_calls"]
    )
    assert candidates["minor_final_answer_defect"]["final_response"] != (
        reference["final_response"]
    )
    assert candidates["wrong_final_answer"]["tool_calls"] == (
        reference["tool_calls"]
    )
    assert candidates["wrong_final_answer"]["final_response"] != (
        reference["final_response"]
    )

    argument_defect = candidates["minor_tool_argument_defect"]
    assert argument_defect["final_response"] == reference["final_response"]
    assert argument_defect["tool_calls"][:-1] == reference["tool_calls"][:-1]
    assert argument_defect["tool_calls"][-1]["tool"] == (
        reference["tool_calls"][-1]["tool"]
    )
    assert argument_defect["tool_calls"][-1]["args"] != (
        reference["tool_calls"][-1]["args"]
    )

    wrong_order = candidates["wrong_tool_order"]
    assert wrong_order["final_response"] == reference["final_response"]
    assert wrong_order["tool_calls"] == [
        reference["tool_calls"][1],
        reference["tool_calls"][0],
        reference["tool_calls"][2],
    ]

    premature_stop = candidates["premature_stop"]
    assert premature_stop["final_response"] == reference["final_response"]
    assert premature_stop["tool_calls"] == reference["tool_calls"][:-1]
    assert candidates["observed_fixture"] == {
        "tool_calls": observed_tool_calls,
        "final_response": "Observed fixture response.",
    }
    assert candidates["severe_control"] != reference


def test_quality_ladder_requires_label_and_plans_96_paid_evaluations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit):
        preference.main(
            ["--strategy-profile", "quality_ladder", "--dry-run"],
            environ={},
        )

    private_root = tmp_path / "private"
    private_root.mkdir()
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    expected_tool_calls = [
        {
            "tool": "file.fetch",
            "args": {"url": "https://private.invalid/source"},
            "args_mode": "exact",
        },
        {
            "tool": "file.decode",
            "args": {"format": "png"},
            "args_mode": "exact",
        },
    ]
    variants = [
        _variant(
            index,
            fixture_path,
            expected_tool_calls=expected_tool_calls,
        )
        for index in range(12)
    ]
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        json.dumps(_queue(variants)),
        encoding="utf-8",
    )
    public_output = tmp_path / "quality-ladder-public.json"
    monkeypatch.setattr(
        calibration,
        "PRIVATE_ROOT",
        private_root.resolve(),
    )
    monkeypatch.setattr(calibration, "build_matrix", lambda: variants)

    result = preference.main(
        [
            "--strategy-profile",
            "quality_ladder",
            "--experiment-label",
            "quality_ladder_test",
            "--dry-run",
            "--queue",
            str(queue_path),
            "--private-source",
            str(private_root / "source.private.json"),
            "--private-artifacts",
            str(private_root / "artifacts.private.json"),
            "--public-output",
            str(public_output),
        ],
        environ={},
    )

    assert result == 0
    public = json.loads(public_output.read_text(encoding="utf-8"))
    assert public["strategy_profile"] == "quality_ladder"
    assert public["experiment_label"] == "quality_ladder_test"
    assert public["experiment_plan"] == {
        "task_count": 12,
        "candidate_count_per_task": 8,
        "planned_paid_evaluations": 96,
        "planned_create_run_calls": 8,
        "create_run_retries_allowed": 0,
    }
    assert public["training_eligible"] is False
    assert public["c3_transition_allowed"] is False
    assert public["release_authority"] is False


def test_sensitivity_probe_targets_order_and_compound_defects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit):
        preference.main(
            ["--strategy-profile", "sensitivity_probe", "--dry-run"],
            environ={},
        )

    private_root = tmp_path / "private"
    private_root.mkdir()
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    expected_tool_calls = [
        {
            "tool": "file.fetch",
            "args": {"url": "https://private.invalid/source"},
            "args_mode": "exact",
        },
        {
            "tool": "file.decode",
            "args": {"format": "png"},
            "args_mode": "exact",
        },
        {
            "tool": "vision.inspect",
            "args": {"region": "red Billing banner"},
            "args_mode": "exact",
        },
    ]
    variants = [
        _variant(
            index,
            fixture_path,
            expected_tool_calls=expected_tool_calls,
        )
        for index in range(12)
    ]
    for variant in variants:
        variant["expected_response"] = (
            "The red Billing banner is exactly visible."
        )
    queue = _queue(variants)
    matrices = preference.build_strategy_matrices(
        queue,
        variants,
        strategies=preference.SENSITIVITY_PROBE_STRATEGIES,
    )
    candidates = {
        strategy: matrices[strategy][0]["candidate_run"]
        for strategy in preference.SENSITIVITY_PROBE_STRATEGIES
    }
    reference = candidates["reference_aligned"]

    assert candidates["wrong_tool_order"]["tool_calls"] == [
        reference["tool_calls"][1],
        reference["tool_calls"][0],
        reference["tool_calls"][2],
    ]
    assert candidates["reverse_tool_order"]["tool_calls"] == list(
        reversed(reference["tool_calls"])
    )
    assert candidates["missing_middle_tool"]["tool_calls"] == [
        reference["tool_calls"][0],
        reference["tool_calls"][2],
    ]
    assert candidates["wrong_tool_name"]["tool_calls"][:-1] == (
        reference["tool_calls"][:-1]
    )
    assert candidates["wrong_tool_name"]["tool_calls"][-1]["tool"].endswith(
        ".wrong"
    )

    double_argument = candidates["double_tool_argument_defect"]
    assert double_argument["tool_calls"][0]["args"] != (
        reference["tool_calls"][0]["args"]
    )
    assert double_argument["tool_calls"][1] == reference["tool_calls"][1]
    assert double_argument["tool_calls"][2]["args"] != (
        reference["tool_calls"][2]["args"]
    )
    assert double_argument["final_response"] == reference["final_response"]

    compound = candidates["tool_and_answer_defect"]
    assert compound["tool_calls"][:-1] == reference["tool_calls"][:-1]
    assert compound["tool_calls"][-1]["args"] != (
        reference["tool_calls"][-1]["args"]
    )
    assert compound["final_response"] != reference["final_response"]

    queue_path = tmp_path / "queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    public_output = tmp_path / "sensitivity-probe-public.json"
    monkeypatch.setattr(
        calibration,
        "PRIVATE_ROOT",
        private_root.resolve(),
    )
    monkeypatch.setattr(calibration, "build_matrix", lambda: variants)
    result = preference.main(
        [
            "--strategy-profile",
            "sensitivity_probe",
            "--experiment-label",
            "sensitivity_probe_test",
            "--dry-run",
            "--queue",
            str(queue_path),
            "--private-source",
            str(private_root / "source.private.json"),
            "--private-artifacts",
            str(private_root / "artifacts.private.json"),
            "--public-output",
            str(public_output),
        ],
        environ={},
    )

    assert result == 0
    public = json.loads(public_output.read_text(encoding="utf-8"))
    assert public["strategy_profile"] == "sensitivity_probe"
    assert public["candidate_strategies"] == list(
        preference.SENSITIVITY_PROBE_STRATEGIES
    )
    assert public["experiment_plan"] == {
        "task_count": 12,
        "candidate_count_per_task": 8,
        "planned_paid_evaluations": 96,
        "planned_create_run_calls": 8,
        "create_run_retries_allowed": 0,
    }


def test_action_value_probe_preserves_recovery_order_and_stop_decisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SystemExit):
        preference.main(
            ["--strategy-profile", "action_value_probe", "--dry-run"],
            environ={},
        )

    private_root = tmp_path / "private"
    private_root.mkdir()
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    expected_tool_calls = [
        {
            "tool": "file.fetch",
            "args": {"url": "https://private.invalid/source"},
            "args_mode": "exact",
        },
        {
            "tool": "file.decode",
            "args": {"format": "png"},
            "args_mode": "exact",
        },
        {
            "tool": "vision.inspect",
            "args": {"region": "red Billing banner"},
            "args_mode": "exact",
        },
    ]
    variants = [
        _variant(
            index,
            fixture_path,
            expected_tool_calls=expected_tool_calls,
        )
        for index in range(12)
    ]
    for variant in variants:
        variant["expected_response"] = (
            "The red Billing banner is exactly visible."
        )
    queue = _queue(variants)
    matrices = preference.build_strategy_matrices(
        queue,
        variants,
        strategies=preference.ACTION_VALUE_PROBE_STRATEGIES,
    )
    candidates = {
        strategy: matrices[strategy][0]["candidate_run"]
        for strategy in preference.ACTION_VALUE_PROBE_STRATEGIES
    }
    reference = candidates["reference_aligned"]

    assert candidates["premature_stop"]["tool_calls"] == (
        reference["tool_calls"][:-1]
    )
    assert candidates["hallucinated_without_tools"]["tool_calls"] == []
    assert candidates["hallucinated_without_tools"]["final_response"] == (
        reference["final_response"]
    )
    assert candidates["redundant_post_success_call"]["tool_calls"] == [
        *reference["tool_calls"],
        reference["tool_calls"][-1],
    ]

    recovered_argument = candidates["recovered_argument_error"]
    assert recovered_argument["tool_calls"][0]["tool"] == (
        reference["tool_calls"][0]["tool"]
    )
    assert recovered_argument["tool_calls"][0]["args"] != (
        reference["tool_calls"][0]["args"]
    )
    assert recovered_argument["tool_calls"][0]["error"] == (
        "simulated invalid arguments"
    )
    assert recovered_argument["tool_calls"][1:] == reference["tool_calls"]

    recovered_wrong_tool = candidates["recovered_wrong_tool"]
    assert recovered_wrong_tool["tool_calls"][0]["tool"].endswith(".wrong")
    assert recovered_wrong_tool["tool_calls"][0]["error"] == (
        "simulated wrong tool"
    )
    assert recovered_wrong_tool["tool_calls"][1:] == reference["tool_calls"]

    contradictory = candidates["contradictory_final_answer_after_tools"]
    assert contradictory["tool_calls"] == reference["tool_calls"]
    assert contradictory["final_response"] != reference["final_response"]

    queue_path = tmp_path / "queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    public_output = tmp_path / "action-value-probe-public.json"
    monkeypatch.setattr(
        calibration,
        "PRIVATE_ROOT",
        private_root.resolve(),
    )
    monkeypatch.setattr(calibration, "build_matrix", lambda: variants)
    result = preference.main(
        [
            "--strategy-profile",
            "action_value_probe",
            "--experiment-label",
            "action_value_probe_test",
            "--dry-run",
            "--queue",
            str(queue_path),
            "--private-source",
            str(private_root / "source.private.json"),
            "--private-artifacts",
            str(private_root / "artifacts.private.json"),
            "--public-output",
            str(public_output),
        ],
        environ={},
    )

    assert result == 0
    public = json.loads(public_output.read_text(encoding="utf-8"))
    assert public["strategy_profile"] == "action_value_probe"
    assert public["experiment_label"] == "action_value_probe_test"
    assert public["candidate_strategies"] == list(
        preference.ACTION_VALUE_PROBE_STRATEGIES
    )
    assert public["experiment_plan"] == {
        "task_count": 12,
        "candidate_count_per_task": 8,
        "planned_paid_evaluations": 96,
        "planned_create_run_calls": 8,
        "create_run_retries_allowed": 0,
    }


def test_decision_boundary_probe_builds_monotonic_defect_sweep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir()
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    expected_tool_calls = [
        {
            "tool": "file.fetch",
            "args": {"url": "https://private.invalid/source"},
            "args_mode": "exact",
        },
        {
            "tool": "file.decode",
            "args": {"format": "png"},
            "args_mode": "exact",
        },
        {
            "tool": "vision.inspect",
            "args": {"region": "red Billing banner"},
            "args_mode": "exact",
        },
    ]
    variants = [
        _variant(
            index,
            fixture_path,
            expected_tool_calls=expected_tool_calls,
        )
        for index in range(12)
    ]
    for variant in variants:
        variant["expected_response"] = (
            "The red Billing banner is exactly visible."
        )
    queue = _queue(variants)
    matrices = preference.build_strategy_matrices(
        queue,
        variants,
        strategies=preference.DECISION_BOUNDARY_PROBE_STRATEGIES,
    )
    candidates = {
        strategy: matrices[strategy][0]["candidate_run"]
        for strategy in preference.DECISION_BOUNDARY_PROBE_STRATEGIES
    }
    reference = candidates["reference_aligned"]

    for suffix, extra_count in (
        ("redundant_post_success_call", 1),
        ("redundant_post_success_calls_2", 2),
        ("redundant_post_success_calls_3", 3),
    ):
        assert candidates[suffix]["tool_calls"] == [
            *reference["tool_calls"],
            *([reference["tool_calls"][-1]] * extra_count),
        ]
    assert candidates["premature_stop"]["tool_calls"] == (
        reference["tool_calls"][:-1]
    )
    assert candidates["premature_stop_two_actions"]["tool_calls"] == (
        reference["tool_calls"][:-2]
    )
    minor = candidates["minor_final_answer_after_tools"]
    major = candidates["contradictory_final_answer_after_tools"]
    assert minor["tool_calls"] == reference["tool_calls"]
    assert major["tool_calls"] == reference["tool_calls"]
    assert minor["final_response"] != reference["final_response"]
    assert major["final_response"] != reference["final_response"]
    assert minor["final_response"] != major["final_response"]

    queue_path = tmp_path / "queue.json"
    queue_path.write_text(json.dumps(queue), encoding="utf-8")
    public_output = tmp_path / "decision-boundary-probe-public.json"
    monkeypatch.setattr(
        calibration,
        "PRIVATE_ROOT",
        private_root.resolve(),
    )
    monkeypatch.setattr(calibration, "build_matrix", lambda: variants)
    result = preference.main(
        [
            "--strategy-profile",
            "decision_boundary_probe",
            "--experiment-label",
            "decision_boundary_probe_test",
            "--dry-run",
            "--queue",
            str(queue_path),
            "--private-source",
            str(private_root / "source.private.json"),
            "--private-artifacts",
            str(private_root / "artifacts.private.json"),
            "--public-output",
            str(public_output),
        ],
        environ={},
    )

    assert result == 0
    public = json.loads(public_output.read_text(encoding="utf-8"))
    assert public["strategy_profile"] == "decision_boundary_probe"
    assert public["candidate_strategies"] == list(
        preference.DECISION_BOUNDARY_PROBE_STRATEGIES
    )
    assert public["experiment_plan"] == {
        "task_count": 12,
        "candidate_count_per_task": 8,
        "planned_paid_evaluations": 96,
        "planned_create_run_calls": 8,
        "create_run_retries_allowed": 0,
    }


def test_long_experiment_labels_use_compact_private_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(calibration, "PRIVATE_ROOT", tmp_path)
    label = "decision_boundary_repeat_1"

    first = preference._strategy_private_path(
        "contradictory_final_answer_after_tools",
        "journal",
        experiment_label=label,
    )
    second = preference._strategy_private_path(
        "contradictory_final_answer_after_tools",
        "journal",
        experiment_label=label,
    )

    assert first == second
    assert label not in first.name
    assert "_exp-" in first.name
    assert len(first.name) < 110
    assert preference._strategy_private_path(
        "reference_aligned",
        "journal",
        experiment_label="repeat_2",
    ).name.endswith("_reference_aligned_repeat_2_journal.private.json")


def test_candidate_override_is_used_in_the_releasefoundry_run_payload(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(
        fixture_path,
        final_response="PRIVATE_FIXTURE_RESPONSE_72e24f6c",
        tool_calls=[
            {
                "tool": "file.read",
                "args": {"path": "PRIVATE_FIXTURE_PATH_f7074a76"},
            }
        ],
    )
    variant = _variant(
        1,
        fixture_path,
        expected_tool_calls=[
            {
                "tool": "file.read",
                "args": {"path": "PRIVATE_EXPECTED_PATH_25998f92"},
                "args_mode": "exact",
            }
        ],
    )
    variant["candidate_run"] = {
        "tool_calls": [
            {
                "tool": "file.read",
                "args": {"path": "PRIVATE_OVERRIDE_PATH_9fc03f85"},
            }
        ],
        "final_response": "PRIVATE_OVERRIDE_RESPONSE_61fa4f75",
    }

    payload = calibration._build_run_result([variant])
    actions = payload["tests"][0]["action_results"]
    tool_action = next(
        action for action in actions if action["action_type"] == "tool_call"
    )
    final_action = next(
        action
        for action in actions
        if action["actor"] == "agent" and action["action_type"] == "text"
    )

    assert tool_action["tool_calls"][0]["actual"]["arguments"] == {
        "path": "PRIVATE_OVERRIDE_PATH_9fc03f85"
    }
    assert final_action["actual_response"]["text"] == (
        "PRIVATE_OVERRIDE_RESPONSE_61fa4f75"
    )
    with pytest.raises(ValueError, match="candidate_run_tool_calls_invalid"):
        calibration._candidate_run(
            {
                "candidate_run": {
                    "tool_calls": ["not-an-object"],
                    "final_response": "response",
                }
            },
            {},
        )


def test_releasefoundry_run_payload_preserves_tool_call_order(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    variant = _variant(
        1,
        fixture_path,
        expected_tool_calls=[
            {
                "tool": "tool.first",
                "args": {"value": "first"},
                "args_mode": "exact",
            },
            {
                "tool": "tool.second",
                "args": {"value": "second"},
                "args_mode": "exact",
            },
        ],
    )
    variant["candidate_run"] = {
        "tool_calls": [
            {"tool": "tool.second", "args": {"value": "second"}},
            {"tool": "tool.first", "args": {"value": "first"}},
        ],
        "final_response": variant["expected_response"],
    }

    payload = calibration._build_run_result([variant])
    tool_actions = [
        action
        for action in payload["tests"][0]["action_results"]
        if action["action_type"] == "tool_call"
    ]

    assert [
        (
            action["tool_calls"][0]["expected"]["name"],
            action["tool_calls"][0]["actual"]["name"],
            action["tool_calls"][0]["match_status"],
        )
        for action in tool_actions
    ] == [
        ("tool.first", "tool.second", "mismatch"),
        ("tool.second", "tool.first", "mismatch"),
    ]


def test_action_value_recovery_payload_preserves_failed_call_first(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    variant = _variant(
        1,
        fixture_path,
        expected_tool_calls=[
            {
                "tool": "tool.first",
                "args": {"value": "first"},
                "args_mode": "exact",
            },
            {
                "tool": "tool.second",
                "args": {"value": "second"},
                "args_mode": "exact",
            },
        ],
    )
    variant["candidate_run"] = {
        "tool_calls": [
            {
                "tool": "tool.first",
                "args": {"value": "near-miss"},
                "error": "simulated invalid arguments",
            },
            {"tool": "tool.first", "args": {"value": "first"}},
            {"tool": "tool.second", "args": {"value": "second"}},
        ],
        "final_response": variant["expected_response"],
    }

    payload = calibration._build_run_result([variant])
    tool_actions = [
        action
        for action in payload["tests"][0]["action_results"]
        if action["action_type"] == "tool_call"
    ]
    actuals = [
        action["tool_calls"][0]["actual"]
        for action in tool_actions
    ]

    assert [actual["name"] for actual in actuals] == [
        "tool.first",
        "tool.first",
        "tool.second",
    ]
    assert actuals[0]["error"] == "simulated invalid arguments"
    assert [
        action["tool_calls"][0]["expected"]["name"]
        for action in tool_actions
    ] == ["tool.first", "tool.second", "NONE_EXPECTED"]


def test_terminal_validation_rejects_duplicate_and_unexpected_tests() -> None:
    test_id = "private-test-001"
    journal = _journal(
        [test_id],
        run_id="private-run-001",
        similarity=0.9,
        verdict="match",
        coherence=1.0,
    )
    journal["batches"][0]["variant_ids"].append(test_id)
    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="completed_test_ids_not_unique",
    ):
        preference._completed_terminal(
            journal,
            expected_ids={test_id},
            strategy="observed_fixture",
        )

    run = _journal(
        [test_id],
        run_id="private-run-002",
        similarity=0.9,
        verdict="match",
        coherence=1.0,
    )["batches"][0]["terminal_response"]
    run["result"]["tests"].append(copy.deepcopy(run["result"]["tests"][0]))
    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="terminal_test_id_not_unique",
    ):
        preference._terminal_tests_by_id(run, {test_id})

    run["result"]["tests"] = [
        _graded_test(
            "unexpected-test",
            similarity=0.9,
            verdict="match",
            coherence=1.0,
        )
    ]
    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="terminal_test_set_mismatch",
    ):
        preference._terminal_tests_by_id(run, {test_id})


def test_receipt_bound_outputs_are_redacted_and_not_training_authority(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    private_tool_arg = "PRIVATE_TOOL_ARGUMENT_1d53a92e"
    _write_fixture(
        fixture_path,
        tool_calls=[
            {
                "tool": "file.read",
                "args": {"path": private_tool_arg},
            }
        ],
    )
    variants = [
        _variant(
            1,
            fixture_path,
            expected_tool_calls=[
                {
                    "tool": "file.read",
                    "args": {"path": private_tool_arg},
                    "args_mode": "exact",
                }
            ],
        )
    ]
    queue = _queue(variants)
    matrices = preference.build_strategy_matrices(queue, variants)
    journals = _strategy_journals(matrices)

    private, public = preference.build_preference_outputs(
        queue,
        matrices,
        journals,
        dataset_identity_hash=DATASET_IDENTITY_HASH,
    )

    assert len(private["items"]) == 1
    assert private["harness_revision"] == calibration.HARNESS_REVISION
    assert private["tool_call_alignment"] == "positional"
    assert public["harness_revision"] == calibration.HARNESS_REVISION
    assert public["tool_call_alignment"] == "positional"
    assert public["experiment_plan"] == {
        "task_count": 1,
        "candidate_count_per_task": 3,
        "planned_paid_evaluations": 3,
        "observed_paid_evaluations": 3,
        "planned_create_run_calls": 3,
        "observed_create_run_calls": 3,
        "create_run_retries": 0,
    }
    assert public["preference_summary"]["chosen_pairs"] == 1
    artifact = public["items"][0]["preference_artifact"]
    assert artifact["pair"]["chosen"]["candidate_id"] == "reference_aligned"
    assert artifact["pair"]["rejected"]["candidate_id"] == "degraded_control"
    assert artifact["training_eligible"] is False
    assert public["human_gold"] is False
    assert public["training_eligible"] is False
    assert public["c3_authority"] is False
    assert public["release_authority"] is False
    assert all(
        public["http_calls"]["by_strategy"][strategy]["create_run"]
        == {
            "attempt_count": 1,
            "success_count": 1,
            "error_count": 0,
            "retry_count": 0,
            "automatic_retry_enabled": False,
        }
        for strategy in preference.STRATEGIES
    )

    serialized = json.dumps(public, sort_keys=True)
    for value in (
        variants[0]["variant_id"],
        variants[0]["fixture_ref"],
        variants[0]["prompt"],
        variants[0]["expected_response"],
        private_tool_arg,
        "private-run-observed_fixture",
        "PRIVATE_SERVER_RESPONSE_610a9bde",
        "PRIVATE_SERVER_SUMMARY_339ea64c",
    ):
        assert value not in serialized


def test_outputs_require_identical_dataset_bindings_and_one_create_receipt(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    variants = [_variant(1, fixture_path)]
    queue = _queue(variants)
    matrices = preference.build_strategy_matrices(queue, variants)

    journals = _strategy_journals(matrices)
    journals["degraded_control"]["dataset_binding"]["dataset_name"] = (
        "PRIVATE_DIFFERENT_DATASET_59ba7461"
    )
    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="strategy_dataset_binding_mismatch",
    ):
        preference.build_preference_outputs(
            queue,
            matrices,
            journals,
            dataset_identity_hash=DATASET_IDENTITY_HASH,
        )

    journals = _strategy_journals(matrices)
    journals["observed_fixture"]["batches"][0]["http_events"] = []
    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="observed_fixture_create_run_receipt_invalid",
    ):
        preference.build_preference_outputs(
            queue,
            matrices,
            journals,
            dataset_identity_hash=DATASET_IDENTITY_HASH,
        )

    journals = _strategy_journals(matrices)
    journals["reference_aligned"]["batches"][0]["http_events"][0][
        "retry"
    ] = True
    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="reference_aligned_create_run_retry_forbidden",
    ):
        preference.build_preference_outputs(
            queue,
            matrices,
            journals,
            dataset_identity_hash=DATASET_IDENTITY_HASH,
        )


def test_preference_main_runs_each_strategy_once_and_skips_completed_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir()
    dataset, private_mapping, mapping_receipt = (
        _write_exploratory_mapping(tmp_path)
    )
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    variants = [_variant(1, fixture_path)]
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(json.dumps(_queue(variants)), encoding="utf-8")
    private_source = private_root / "source.private.json"
    private_artifacts = private_root / "artifacts.private.json"
    public_output = tmp_path / "public.json"
    clients: list[SuccessfulReleaseFoundryClient] = []

    def client_factory(timeout: int) -> SuccessfulReleaseFoundryClient:
        client = SuccessfulReleaseFoundryClient(
            dataset,
            run_id=100 + len(clients),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(
        calibration,
        "PRIVATE_ROOT",
        private_root.resolve(),
    )
    monkeypatch.setattr(calibration, "build_matrix", lambda: variants)
    args = [
        "--execute",
        "--allow-mutate",
        "--allow-unverified-exploration",
        "--queue",
        str(queue_path),
        "--mapping-private-review",
        str(private_mapping),
        "--mapping-receipt",
        str(mapping_receipt),
        "--private-source",
        str(private_source),
        "--private-artifacts",
        str(private_artifacts),
        "--public-output",
        str(public_output),
        "--poll-timeout",
        "2",
        "--poll-interval",
        "0",
        "--max-retries",
        "0",
    ]

    result = preference.main(
        args,
        client_factory=client_factory,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
    )

    assert result == 0
    assert len(clients) == 3
    assert all(client.calls["create_run"] == 1 for client in clients)
    assert all(client.calls["get_run"] == 1 for client in clients)
    public = json.loads(public_output.read_text(encoding="utf-8"))
    assert public["experiment_status"] == "completed"
    assert public["experiment_plan"]["observed_paid_evaluations"] == 3

    def forbidden_factory(timeout: int) -> SuccessfulReleaseFoundryClient:
        raise AssertionError("completed journals must not create a client")

    rerun = preference.main(
        args,
        client_factory=forbidden_factory,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
    )

    assert rerun == 0
    assert len(clients) == 3


def test_experiment_label_namespaces_repeat_journals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir()
    dataset, private_mapping, mapping_receipt = (
        _write_exploratory_mapping(tmp_path)
    )
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    variants = [_variant(1, fixture_path)]
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(json.dumps(_queue(variants)), encoding="utf-8")
    clients: list[SuccessfulReleaseFoundryClient] = []

    def client_factory(timeout: int) -> SuccessfulReleaseFoundryClient:
        client = SuccessfulReleaseFoundryClient(
            dataset,
            run_id=200 + len(clients),
        )
        clients.append(client)
        return client

    monkeypatch.setattr(
        calibration,
        "PRIVATE_ROOT",
        private_root.resolve(),
    )
    monkeypatch.setattr(calibration, "build_matrix", lambda: variants)
    args = [
        "--execute",
        "--allow-mutate",
        "--allow-unverified-exploration",
        "--experiment-label",
        "repeat_2",
        "--queue",
        str(queue_path),
        "--mapping-private-review",
        str(private_mapping),
        "--mapping-receipt",
        str(mapping_receipt),
        "--private-source",
        str(private_root / "source.private.json"),
        "--private-artifacts",
        str(private_root / "artifacts.private.json"),
        "--public-output",
        str(tmp_path / "public.json"),
        "--poll-timeout",
        "2",
        "--poll-interval",
        "0",
        "--max-retries",
        "0",
    ]

    result = preference.main(
        args,
        client_factory=client_factory,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
    )

    assert result == 0
    assert len(clients) == 3
    for strategy in preference.STRATEGIES:
        path = (
            private_root
            / (
                "a2_rf_exploratory_preference_"
                f"{strategy}_repeat_2_journal.private.json"
            )
        )
        journal = json.loads(path.read_text(encoding="utf-8"))
        assert journal["preference_experiment"]["experiment_label"] == (
            "repeat_2"
        )
        assert journal["preference_experiment"]["harness_revision"] == (
            calibration.HARNESS_REVISION
        )
        assert journal["preference_experiment"][
            "tool_call_alignment"
        ] == "positional"
    public = json.loads(
        (tmp_path / "public.json").read_text(encoding="utf-8")
    )
    assert public["experiment_label"] == "repeat_2"

    with pytest.raises(
        preference.ReleaseFoundryPreferenceCalibrationError,
        match="experiment_label_must_be_safe_slug",
    ):
        preference.main(
            ["--dry-run", "--experiment-label", "../unsafe"],
            environ={},
        )


def test_submitted_run_resumes_with_get_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir()
    dataset, private_mapping, mapping_receipt = (
        _write_exploratory_mapping(tmp_path)
    )
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    variants = [_variant(1, fixture_path)]
    journal_path = private_root / "resume.private.json"
    public_output = tmp_path / "resume-public.json"
    submitted: dict[str, Any] = {}

    class TimeoutClient(SuccessfulReleaseFoundryClient):
        def _make_request(
            self,
            function: str,
            **params: Any,
        ) -> dict[str, Any]:
            result = super()._make_request(function, **params)
            if function == "create_run":
                submitted["result"] = copy.deepcopy(self.submitted_result)
            return result

    monkeypatch.setattr(
        calibration,
        "PRIVATE_ROOT",
        private_root.resolve(),
    )
    timeout_client = TimeoutClient(dataset, run_id=701)
    first = calibration.main(
        _live_args(
            private_mapping=private_mapping,
            mapping_receipt=mapping_receipt,
            private_journal=journal_path,
            public_output=public_output,
            poll_timeout=0,
        ),
        client_factory=lambda timeout: timeout_client,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
        matrix_factory=lambda: variants,
    )

    assert first == 2
    assert timeout_client.calls["create_run"] == 1
    assert timeout_client.calls["get_run"] == 0

    recovery_client = SuccessfulReleaseFoundryClient(
        dataset,
        run_id=701,
        submitted_result=submitted["result"],
    )
    second = calibration.main(
        _live_args(
            private_mapping=private_mapping,
            mapping_receipt=mapping_receipt,
            private_journal=journal_path,
            public_output=public_output,
        ),
        client_factory=lambda timeout: recovery_client,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
        matrix_factory=lambda: variants,
    )

    assert second == 0
    assert recovery_client.calls["create_run"] == 0
    assert recovery_client.calls["get_run"] == 1


def test_create_failure_without_run_id_is_never_resubmitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_root = tmp_path / "private"
    private_root.mkdir()
    dataset, private_mapping, mapping_receipt = (
        _write_exploratory_mapping(tmp_path)
    )
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)
    variants = [_variant(1, fixture_path)]
    journal_path = private_root / "create-failed.private.json"
    public_output = tmp_path / "create-failed-public.json"

    class FailingCreateClient(SuccessfulReleaseFoundryClient):
        def _make_request(
            self,
            function: str,
            **params: Any,
        ) -> dict[str, Any]:
            if function == "create_run":
                self.calls[function] += 1
                raise ConnectionError("synthetic unknown create outcome")
            return super()._make_request(function, **params)

    monkeypatch.setattr(
        calibration,
        "PRIVATE_ROOT",
        private_root.resolve(),
    )
    failing = FailingCreateClient(dataset, run_id=801)
    first = calibration.main(
        _live_args(
            private_mapping=private_mapping,
            mapping_receipt=mapping_receipt,
            private_journal=journal_path,
            public_output=public_output,
        ),
        client_factory=lambda timeout: failing,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
        matrix_factory=lambda: variants,
    )

    assert first == 2
    assert failing.calls["create_run"] == 1

    recovery = SuccessfulReleaseFoundryClient(dataset, run_id=802)
    second = calibration.main(
        _live_args(
            private_mapping=private_mapping,
            mapping_receipt=mapping_receipt,
            private_journal=journal_path,
            public_output=public_output,
        ),
        client_factory=lambda timeout: recovery,
        environ={"RELEASEFOUNDRY_LABS_API_KEY": "tp_synthetic_test_key"},
        matrix_factory=lambda: variants,
    )

    assert second == 2
    assert recovery.calls["get_dataset"] == 1
    assert recovery.calls["create_run"] == 0
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["batches"][0]["status"] == "create_failed"
