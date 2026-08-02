import hashlib

import pytest

from services.judge.preference_learning import (
    PreferenceLearningError,
    build_governed_preference_pair,
)


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate(
    candidate_id: str,
    *,
    task_id: str = "task-1",
    sample_id: str = "sample-1",
    dataset_identity_hash: str | None = None,
    prompt_version: str = "prompt-v1",
    prompt_hash: str | None = None,
    media_evidence_hashes: list[str] | None = None,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "task_id": task_id,
        "sample_id": sample_id,
        "dataset_identity_hash": dataset_identity_hash or _hash("dataset"),
        "prompt_version": prompt_version,
        "prompt_hash": prompt_hash or _hash("prompt"),
        "media_evidence_hashes": media_evidence_hashes or [_hash("image-1")],
        "model_version": f"candidate-model-{candidate_id}-v1",
        "trace_hash": _hash(f"trace-{candidate_id}"),
        "final_answer_hash": _hash(f"answer-{candidate_id}"),
    }


def _releasefoundry_evaluation(
    candidate_id: str,
    *,
    rank: int,
    reward: float,
    passed: bool,
    receipt_verified: bool = True,
    receipt_hash: str | None = None,
    severity: str | None = None,
) -> dict:
    failure_type = "none" if passed else "wrong_arguments"
    failure_severity = severity or ("none" if passed else "high")
    evidence_location = {} if passed else {"action_index": 0, "field": "city"}
    reason = "" if passed else "The required city argument was omitted."
    return {
        "candidate_id": candidate_id,
        "action_scores": [
            {
                "action_index": 0,
                "score": 1.0 if passed else 0.2,
                "passed": passed,
                "failure_type": failure_type,
                "evidence_location": evidence_location,
                "reason": reason,
            }
        ],
        "final_answer_score": 0.95 if passed else 0.25,
        "overall_reward": reward,
        "rank": rank,
        "failure_type": failure_type,
        "severity": failure_severity,
        "failure_action": "" if passed else "weather.lookup",
        "evidence_location": evidence_location,
        "failure_reason": reason,
        "confidence": 0.93,
        "receipt_hash": receipt_hash or _hash(f"releasefoundry-receipt-{candidate_id}"),
        "receipt_verified": receipt_verified,
    }


def _strong_vote(
    *,
    teacher_id: str = "strong-a",
    chosen: str = "candidate-a",
    rejected: str = "candidate-b",
) -> dict:
    return {
        "teacher_id": teacher_id,
        "teacher_type": "strong_model",
        "chosen_candidate_id": chosen,
        "rejected_candidate_id": rejected,
        "confidence": 0.91,
        "model_version": f"{teacher_id}-v1",
        "evidence_hash": _hash(f"teacher-evidence-{teacher_id}"),
        "evidence_verified": True,
        "reason_code": "tool_arguments_and_grounding",
    }


def _local_vote(
    *,
    chosen: str = "candidate-a",
    rejected: str = "candidate-b",
    confidence: float = 0.8,
) -> dict:
    return {
        "teacher_id": "local-rm",
        "teacher_type": "local_judge",
        "chosen_candidate_id": chosen,
        "rejected_candidate_id": rejected,
        "confidence": confidence,
        "model_version": "local-rm-v1",
        "evidence_hash": _hash("local-rm-evidence"),
        "evidence_verified": True,
        "reason_code": "local_reward_prediction",
    }


def _human(
    *,
    chosen: str = "candidate-a",
    rejected: str = "candidate-b",
) -> dict:
    return {
        "review_status": "reviewed",
        "chosen_candidate_id": chosen,
        "rejected_candidate_id": rejected,
        "review_id_hash": _hash("review-id"),
        "reviewer_receipt_hash": _hash("reviewer-receipt"),
        "reviewed_at_unix_ms": 1785060000000,
        "review_reason_code": "independent_gold_adjudication",
    }


def _inputs() -> tuple[list[dict], list[dict]]:
    return (
        [_candidate("candidate-a"), _candidate("candidate-b")],
        [
            _releasefoundry_evaluation(
                "candidate-a",
                rank=1,
                reward=0.95,
                passed=True,
            ),
            _releasefoundry_evaluation(
                "candidate-b",
                rank=2,
                reward=0.2,
                passed=False,
            ),
        ],
    )


def test_releasefoundry_ranking_creates_only_a_provisional_preference_pair():
    candidates, evaluations = _inputs()

    record = build_governed_preference_pair(candidates, evaluations)

    assert record["status"] == "provisional_preference"
    assert record["preference_authority"] == "releasefoundry_provisional"
    assert record["training_eligible"] is False
    assert record["review_required"] is True
    assert record["chosen"]["candidate_id"] == "candidate-a"
    assert record["rejected"]["candidate_id"] == "candidate-b"
    assert record["releasefoundry_evaluations"][1]["failure_action"] == "weather.lookup"
    assert record["metadata"]["releasefoundry_alone_is_human_gold"] is False
    assert record["pair_id"].startswith("sha256:")


def test_matching_external_teacher_is_still_review_required_by_default():
    candidates, evaluations = _inputs()

    record = build_governed_preference_pair(
        candidates,
        evaluations,
        teacher_votes=[_strong_vote()],
    )

    assert record["preference_authority"] == "teacher_consensus"
    assert record["external_teacher_count"] == 2
    assert record["status"] == "review_required"
    assert record["training_eligible"] is False


def test_explicit_teacher_consensus_policy_can_enable_non_gold_training():
    candidates, evaluations = _inputs()

    record = build_governed_preference_pair(
        candidates,
        evaluations,
        teacher_votes=[_strong_vote()],
        allow_teacher_consensus=True,
    )

    assert record["status"] == "training_eligible"
    assert record["preference_authority"] == "teacher_consensus"
    assert record["training_eligible"] is True
    assert record["human_adjudication"] is None


def test_external_teacher_conflict_routes_to_human_review():
    candidates, evaluations = _inputs()

    record = build_governed_preference_pair(
        candidates,
        evaluations,
        teacher_votes=[
            _strong_vote(chosen="candidate-b", rejected="candidate-a"),
        ],
    )

    assert record["teacher_conflict"] is True
    assert record["status"] == "review_required"
    assert record["training_eligible"] is False
    assert "external_teacher_conflict" in record["active_learning"]["reasons"]


def test_reviewed_human_adjudication_overrides_teacher_conflict():
    candidates, evaluations = _inputs()

    record = build_governed_preference_pair(
        candidates,
        evaluations,
        teacher_votes=[
            _strong_vote(chosen="candidate-b", rejected="candidate-a"),
        ],
        human_adjudication=_human(
            chosen="candidate-b",
            rejected="candidate-a",
        ),
    )

    assert record["teacher_conflict"] is True
    assert record["status"] == "training_eligible"
    assert record["preference_authority"] == "human_gold"
    assert record["chosen"]["candidate_id"] == "candidate-b"
    assert record["rejected"]["candidate_id"] == "candidate-a"


def test_local_judge_does_not_count_as_an_independent_external_teacher():
    candidates, evaluations = _inputs()

    record = build_governed_preference_pair(
        candidates,
        evaluations,
        teacher_votes=[_local_vote()],
        allow_teacher_consensus=True,
    )

    assert record["external_teacher_count"] == 1
    assert record["preference_authority"] == "releasefoundry_provisional"
    assert record["training_eligible"] is False


def test_reward_tie_blocks_preference_without_human_gold():
    candidates, evaluations = _inputs()
    evaluations[0]["overall_reward"] = 0.5
    evaluations[1]["overall_reward"] = 0.5

    record = build_governed_preference_pair(candidates, evaluations)

    assert record["status"] == "blocked"
    assert record["chosen"] is None
    assert record["rejected"] is None
    assert record["releasefoundry_blockers"] == ["releasefoundry_reward_tie"]


def test_human_gold_can_resolve_an_releasefoundry_reward_tie():
    candidates, evaluations = _inputs()
    evaluations[0]["overall_reward"] = 0.5
    evaluations[1]["overall_reward"] = 0.5

    record = build_governed_preference_pair(
        candidates,
        evaluations,
        human_adjudication=_human(),
    )

    assert record["status"] == "training_eligible"
    assert record["preference_authority"] == "human_gold"
    assert record["releasefoundry_blockers"] == ["releasefoundry_reward_tie"]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("task_id", "task-2", "cross_candidate_task_id_mismatch"),
        ("sample_id", "sample-2", "cross_candidate_sample_id_mismatch"),
        (
            "dataset_identity_hash",
            _hash("other-dataset"),
            "cross_candidate_dataset_identity_hash_mismatch",
        ),
        ("prompt_version", "prompt-v2", "cross_candidate_prompt_version_mismatch"),
        ("prompt_hash", _hash("other-prompt"), "cross_candidate_prompt_hash_mismatch"),
        (
            "media_evidence_hashes",
            [_hash("other-image")],
            "cross_candidate_media_evidence_hashes_mismatch",
        ),
    ],
)
def test_cross_scope_candidate_pairing_is_rejected(field, value, error):
    candidates, evaluations = _inputs()
    candidates[1][field] = value

    with pytest.raises(PreferenceLearningError, match=error):
        build_governed_preference_pair(candidates, evaluations)


def test_duplicate_candidate_id_is_rejected():
    candidates, evaluations = _inputs()
    candidates[1]["candidate_id"] = "candidate-a"

    with pytest.raises(PreferenceLearningError, match="duplicate_candidate_id"):
        build_governed_preference_pair(candidates, evaluations)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("receipt_verified", False, "releasefoundry_receipt_not_verified"),
        ("receipt_hash", "not-a-hash", "receipt_hash_must_be_sha256"),
    ],
)
def test_unverified_or_unattributable_releasefoundry_receipt_is_rejected(field, value, error):
    candidates, evaluations = _inputs()
    evaluations[0][field] = value

    with pytest.raises(PreferenceLearningError, match=error):
        build_governed_preference_pair(candidates, evaluations)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "Bear" + "er hidden-secret-value",
        "releasefoundry_" + "live_hiddencredential",
        "docs/evidence/" + "private_refs/raw.json",
        "C:" + r"\Users\private\raw.json",
        "https://example.invalid/file?" + "signature=secret",
    ],
)
def test_secret_private_path_and_signed_url_material_is_rejected(unsafe_value):
    candidates, evaluations = _inputs()
    evaluations[1]["failure_reason"] = unsafe_value

    with pytest.raises(
        PreferenceLearningError,
        match="private_or_secret_material_rejected",
    ):
        build_governed_preference_pair(candidates, evaluations)


def test_raw_candidate_answer_field_is_rejected():
    candidates, evaluations = _inputs()
    candidates[0]["final_answer"] = "Do not persist raw training content here."

    with pytest.raises(PreferenceLearningError, match="unknown_fields:final_answer"):
        build_governed_preference_pair(candidates, evaluations)


def test_same_candidate_cannot_be_both_chosen_and_rejected():
    candidates, evaluations = _inputs()
    vote = _strong_vote(chosen="candidate-a", rejected="candidate-a")

    with pytest.raises(
        PreferenceLearningError,
        match="chosen_and_rejected_must_be_distinct",
    ):
        build_governed_preference_pair(
            candidates,
            evaluations,
            teacher_votes=[vote],
        )


def test_missing_releasefoundry_candidate_evaluation_is_rejected():
    candidates, evaluations = _inputs()

    with pytest.raises(
        PreferenceLearningError,
        match="releasefoundry_evaluation_candidate_coverage_mismatch",
    ):
        build_governed_preference_pair(candidates, evaluations[:1])


def test_rank_reward_conflict_blocks_the_pair():
    candidates, evaluations = _inputs()
    evaluations[0]["overall_reward"] = 0.1
    evaluations[1]["overall_reward"] = 0.9

    record = build_governed_preference_pair(candidates, evaluations)

    assert record["status"] == "blocked"
    assert record["releasefoundry_blockers"] == ["releasefoundry_rank_reward_conflict"]


def test_uncertain_disagreeing_local_judge_and_critical_failure_are_prioritized():
    candidates, evaluations = _inputs()
    evaluations[1]["severity"] = "critical"

    record = build_governed_preference_pair(
        candidates,
        evaluations,
        teacher_votes=[
            _local_vote(
                chosen="candidate-b",
                rejected="candidate-a",
                confidence=0.1,
            )
        ],
        known_failure_classes={"missing_required_tool"},
    )

    assert record["active_learning"]["band"] == "critical"
    assert record["active_learning"]["score"] == 81.5
    assert set(record["active_learning"]["reasons"]) >= {
        "local_judge_uncertain",
        "local_releasefoundry_disagreement",
        "critical_severity",
        "novel_failure_class",
    }


def test_output_and_pair_hash_are_deterministic_across_input_order():
    candidates, evaluations = _inputs()
    votes = [_strong_vote(), _local_vote()]

    first = build_governed_preference_pair(
        candidates,
        evaluations,
        teacher_votes=votes,
    )
    second = build_governed_preference_pair(
        list(reversed(candidates)),
        list(reversed(evaluations)),
        teacher_votes=list(reversed(votes)),
    )

    assert second == first
