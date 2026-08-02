from __future__ import annotations

import copy

import pytest

from services.judge.releasefoundry_preference_evaluation import (
    ReleaseFoundryPreferenceEvaluationError,
    build_releasefoundry_run_binding_receipt,
    build_public_provisional_preference_artifact,
    build_provisional_preference_artifact,
    verify_releasefoundry_run_binding_receipt,
    verify_releasefoundry_score_receipt,
)
from services.judge.result_persistence import stable_hash


def _hash(value: str) -> str:
    return stable_hash(value)


def _candidate(candidate_id: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "task_id": "task-1",
        "sample_id": "sample-1",
        "dataset_identity_hash": _hash("dataset"),
        "prompt_version": "prompt-v1",
        "prompt_hash": _hash("prompt"),
        "media_evidence_hashes": [],
        "model_version": f"candidate-{candidate_id}-v1",
        "trace_hash": _hash(f"trace-{candidate_id}"),
        "final_answer_hash": _hash(f"answer-{candidate_id}"),
    }


def _tool_action(
    action_index: int,
    *,
    status: str = "exact",
    expected_name: str = "media.fetch",
    actual_name: str = "media.fetch",
    matching: int = 1,
    missing: int = 0,
    extra: int = 0,
    different: int = 0,
) -> dict:
    def fields(count: int) -> dict:
        return {f"field-{index}": True for index in range(count)}

    return {
        "actor": "agent",
        "action_type": "tool_call",
        "action_index": action_index,
        "tool_calls": [
            {
                "expected": {"name": expected_name},
                "actual": {"name": actual_name},
                "match_status": status,
                "argument_comparison": {
                    "matching": fields(matching),
                    "missing": fields(missing),
                    "extra": fields(extra),
                    "different": fields(different),
                },
            }
        ],
    }


def _test(
    test_id: str,
    *,
    tool_action: dict | None = None,
    similarity: float = 0.95,
    verdict: str = "match",
    coherence: float = 1.0,
) -> dict:
    actions = [
        {
            "actor": "user",
            "action_type": "text",
            "action_index": 0,
            "text": "private prompt",
        }
    ]
    if tool_action is not None:
        actions.append(tool_action)
    actions.append(
        {
            "actor": "agent",
            "action_type": "text",
            "action_index": 2,
            "actual_response": {"text": "private candidate"},
            "match_status": "exact" if verdict == "match" else "mismatch",
            "semantic_similarity": similarity,
            "llm_judgment": {"verdict": verdict},
        }
    )
    return {
        "test_id": test_id,
        "status": "completed",
        "started_at": "2026-07-27T00:00:00Z",
        "completed_at": "2026-07-27T00:00:01Z",
        "action_results": actions,
        "coherence": {
            "score": coherence,
            "summary": "server observation",
            "issues": [],
        },
    }


def _run(run_id: str, test: dict) -> dict:
    return {
        "id": run_id,
        "dataset": 42,
        "result": {
            "status": "completed",
            "tests": [test],
        },
    }


def _observation(candidate_id: str, test: dict, run_id: str) -> dict:
    receipt = build_releasefoundry_run_binding_receipt(
        _run(run_id, test),
        expected_test_ids=[test["test_id"]],
        expected_dataset_id=42,
        dataset_identity_hash=_hash("dataset"),
    )
    return {
        "candidate_id": candidate_id,
        "expected_test_id": test["test_id"],
        "server_test_result": test,
        "run_receipt": receipt,
    }


def test_run_receipt_requires_exact_unique_fully_graded_tests():
    good = _test("test-1", tool_action=_tool_action(1))
    receipt = build_releasefoundry_run_binding_receipt(
        _run("run-1", good),
        expected_test_ids=["test-1"],
        expected_dataset_id=42,
        dataset_identity_hash=_hash("dataset"),
    )

    verify_releasefoundry_run_binding_receipt(receipt)
    assert receipt["exact_test_set_verified"] is True
    assert receipt["per_test_server_grading_verified"] is True
    assert receipt["per_test_final_answer_grading_verified"] is True
    assert receipt["aggregate_marker_used_as_authority"] is False

    duplicate = _run("run-1", good)
    duplicate["result"]["tests"].append(copy.deepcopy(good))
    with pytest.raises(
        ReleaseFoundryPreferenceEvaluationError,
        match="run_test_id_not_unique",
    ):
        build_releasefoundry_run_binding_receipt(
            duplicate,
            expected_test_ids=["test-1"],
            expected_dataset_id=42,
            dataset_identity_hash=_hash("dataset"),
        )

    incomplete = copy.deepcopy(good)
    incomplete["action_results"][-1].pop("semantic_similarity")
    incomplete["action_results"][-1].pop("llm_judgment")
    with pytest.raises(
        ReleaseFoundryPreferenceEvaluationError,
        match="test_final_answer_grading_not_unique",
    ):
        build_releasefoundry_run_binding_receipt(
            _run("run-1", incomplete),
            expected_test_ids=["test-1"],
            expected_dataset_id=42,
            dataset_identity_hash=_hash("dataset"),
        )


@pytest.mark.parametrize(
    ("test_ids", "expected_error"),
    [
        (["test-1", "unexpected"], "run_test_set_mismatch"),
        (["test-1", "test-1"], "expected_test_ids_duplicate"),
    ],
)
def test_run_receipt_rejects_unexpected_or_duplicate_expected_tests(
    test_ids: list[str],
    expected_error: str,
):
    test = _test("test-1", tool_action=_tool_action(1))

    with pytest.raises(ReleaseFoundryPreferenceEvaluationError, match=expected_error):
        build_releasefoundry_run_binding_receipt(
            _run("run-1", test),
            expected_test_ids=test_ids,
            expected_dataset_id=42,
            dataset_identity_hash=_hash("dataset"),
        )


def test_run_receipt_hash_tampering_is_rejected():
    test = _test("test-1", tool_action=_tool_action(1))
    receipt = build_releasefoundry_run_binding_receipt(
        _run("run-1", test),
        expected_test_ids=["test-1"],
        expected_dataset_id=42,
        dataset_identity_hash=_hash("dataset"),
    )
    receipt["run_result_status"] = "failed"

    with pytest.raises(
        ReleaseFoundryPreferenceEvaluationError,
        match="run_receipt_hash_mismatch",
    ):
        verify_releasefoundry_run_binding_receipt(receipt)


def test_real_observations_build_only_a_provisional_preference():
    candidates = [
        _candidate("observed_fixture"),
        _candidate("reference_aligned"),
        _candidate("degraded_control"),
    ]
    observed = _test(
        "task-1",
        tool_action=_tool_action(
            1,
            status="partial",
            matching=2,
            different=1,
        ),
        similarity=0.8,
        verdict="acceptable",
        coherence=0.9,
    )
    reference = _test(
        "task-1",
        tool_action=_tool_action(1),
        similarity=0.98,
        verdict="match",
        coherence=1.0,
    )
    degraded = _test(
        "task-1",
        tool_action=_tool_action(
            1,
            status="mismatch",
            actual_name="NOT_CALLED",
            matching=0,
            missing=1,
        ),
        similarity=0.1,
        verdict="major_issue",
        coherence=0.2,
    )
    artifact = build_provisional_preference_artifact(
        candidate_batch_id=_hash("batch-1"),
        candidates=candidates,
        observations=[
            _observation("observed_fixture", observed, "run-observed"),
            _observation("reference_aligned", reference, "run-reference"),
            _observation("degraded_control", degraded, "run-degraded"),
        ],
    )

    pair = artifact["pair"]
    assert pair["status"] == "provisional_preference"
    assert pair["preference_authority"] == "releasefoundry_provisional"
    assert pair["chosen"]["candidate_id"] == "reference_aligned"
    assert pair["rejected"]["candidate_id"] == "degraded_control"
    assert pair["training_eligible"] is False
    assert pair["review_required"] is True
    assert artifact["human_gold"] is False
    assert artifact["c3_authority"] is False
    assert artifact["release_authority"] is False
    assert artifact["ranking"]["source"] == "derived_from_releasefoundry_observations"
    assert artifact["ranking"]["server_native_pairwise_ranking"] is False
    assert all(
        evaluation["receipt_verified"] is True
        for evaluation in pair["releasefoundry_evaluations"]
    )
    assert "private prompt" not in str(artifact)
    assert "private candidate" not in str(artifact)


def test_reward_tie_is_preserved_and_blocks_preference():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    first = _test("task-1", tool_action=_tool_action(1))
    second = copy.deepcopy(first)
    artifact = build_provisional_preference_artifact(
        candidate_batch_id=_hash("batch-tie"),
        candidates=candidates,
        observations=[
            _observation("candidate-a", first, "run-a"),
            _observation("candidate-b", second, "run-b"),
        ],
    )

    assert artifact["pair"]["status"] == "blocked"
    assert artifact["pair"]["releasefoundry_blockers"] == ["releasefoundry_rank_tie_or_gap"]
    assert artifact["pair"]["training_eligible"] is False


def test_score_receipt_binds_the_full_normalized_evaluation():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    first = _test("task-1", tool_action=_tool_action(1), similarity=0.95)
    second = _test(
        "task-1",
        tool_action=_tool_action(1),
        similarity=0.4,
        verdict="major_issue",
    )
    artifact = build_provisional_preference_artifact(
        candidate_batch_id=_hash("batch-score"),
        candidates=candidates,
        observations=[
            _observation("candidate-a", first, "run-a"),
            _observation("candidate-b", second, "run-b"),
        ],
    )
    before = {
        item["candidate_id"]: item["receipt_hash"]
        for item in artifact["score_receipts"]
    }

    changed = copy.deepcopy(second)
    changed["action_results"][-1]["semantic_similarity"] = 0.2
    changed_artifact = build_provisional_preference_artifact(
        candidate_batch_id=_hash("batch-score"),
        candidates=candidates,
        observations=[
            _observation("candidate-a", first, "run-a"),
            _observation("candidate-b", changed, "run-b"),
        ],
    )
    after = {
        item["candidate_id"]: item["receipt_hash"]
        for item in changed_artifact["score_receipts"]
    }

    assert before["candidate-a"] == after["candidate-a"]
    assert before["candidate-b"] != after["candidate-b"]


def test_score_receipt_tampering_and_misbinding_are_rejected():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    first = _test("task-1", tool_action=_tool_action(1), similarity=0.95)
    second = _test(
        "task-1",
        tool_action=_tool_action(1),
        similarity=0.4,
        verdict="major_issue",
    )
    artifact = build_provisional_preference_artifact(
        candidate_batch_id=_hash("batch-score-verify"),
        candidates=candidates,
        observations=[
            _observation("candidate-a", first, "run-a"),
            _observation("candidate-b", second, "run-b"),
        ],
    )
    receipt = artifact["score_receipts"][0]
    evaluation = next(
        item
        for item in artifact["pair"]["releasefoundry_evaluations"]
        if item["candidate_id"] == receipt["candidate_id"]
    )
    verify_releasefoundry_score_receipt(receipt, evaluation=evaluation)

    tampered = copy.deepcopy(receipt)
    tampered["normalization_version"] = "tampered"
    with pytest.raises(
        ReleaseFoundryPreferenceEvaluationError,
        match="score_receipt_hash_mismatch",
    ):
        verify_releasefoundry_score_receipt(tampered, evaluation=evaluation)

    misbound = copy.deepcopy(evaluation)
    misbound["overall_reward"] -= 1.0
    with pytest.raises(
        ReleaseFoundryPreferenceEvaluationError,
        match="score_receipt_evaluation_hash_mismatch",
    ):
        verify_releasefoundry_score_receipt(receipt, evaluation=misbound)


def test_public_projection_omits_private_receipt_fields_and_payloads():
    candidates = [_candidate("candidate-a"), _candidate("candidate-b")]
    first = _test("private-test-id", tool_action=_tool_action(1), similarity=0.95)
    second = _test(
        "private-test-id",
        tool_action=_tool_action(1),
        similarity=0.4,
        verdict="major_issue",
    )
    private = build_provisional_preference_artifact(
        candidate_batch_id=_hash("batch-public"),
        candidates=candidates,
        observations=[
            _observation("candidate-a", first, "private-run-a"),
            _observation("candidate-b", second, "private-run-b"),
        ],
    )
    public = build_public_provisional_preference_artifact(private)

    assert public["private_artifact_hash"] == private["artifact_hash"]
    assert public["observation_summary"] == {
        "candidate_count": 2,
        "score_receipt_count": 2,
        "all_score_receipts_verified": True,
    }
    assert public["training_eligible"] is False
    assert public["human_gold"] is False
    assert "score_receipts" not in public
    serialized = str(public)
    for private_value in (
        "private-test-id",
        "private-run-a",
        "private-run-b",
        "private prompt",
        "private candidate",
    ):
        assert private_value not in serialized
    forbidden_keys = {
        "releasefoundry_test_id_hash",
        "server_test_result_hash",
        "run_receipt_hash",
        "run_id",
        "expected_dataset_id",
        "expected_test_id",
        "test_id",
    }
    assert not (_recursive_keys(public) & forbidden_keys)


def _recursive_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for child in value.values()
            for key in _recursive_keys(child)
        }
    if isinstance(value, list):
        return {
            key
            for child in value
            for key in _recursive_keys(child)
        }
    return set()
