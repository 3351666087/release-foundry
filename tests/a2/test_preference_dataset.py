import copy

import pytest

from services.judge.preference_dataset import (
    PreferenceDatasetError,
    build_private_training_records,
    load_private_training_corpus,
    load_private_training_jsonl,
    verify_source_split_isolation,
    write_private_training_jsonl,
)
from services.judge.preference_learning import build_governed_preference_pair
from services.judge.result_persistence import stable_hash


def _hash(value) -> str:
    return stable_hash(value)


def _candidate(
    candidate_id: str,
    trace: list[dict],
    answer: dict,
    *,
    media_seed: str = "image-bytes-1",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "task_id": "task-1",
        "sample_id": "sample-1",
        "dataset_identity_hash": _hash({"dataset": "fixed-six-v1"}),
        "prompt_version": "prompt-v1",
        "prompt_hash": _hash({"text": "Weather in Shanghai?"}),
        "media_evidence_hashes": [_hash(media_seed)],
        "model_version": f"candidate-model-{candidate_id}-v1",
        "trace_hash": _hash(trace),
        "final_answer_hash": _hash(answer),
    }


def _evaluation(
    candidate_id: str,
    *,
    rank: int,
    reward: float,
    passed: bool,
) -> dict:
    failure_type = "none" if passed else "wrong_arguments"
    evidence = {} if passed else {"action_index": 0, "field": "city"}
    reason = "" if passed else "The required city argument was omitted."
    return {
        "candidate_id": candidate_id,
        "action_scores": [
            {
                "action_index": 0,
                "score": 1.0 if passed else 0.2,
                "passed": passed,
                "failure_type": failure_type,
                "evidence_location": evidence,
                "reason": reason,
            }
        ],
        "final_answer_score": 0.95 if passed else 0.25,
        "overall_reward": reward,
        "rank": rank,
        "failure_type": failure_type,
        "severity": "none" if passed else "high",
        "failure_action": "" if passed else "weather.lookup",
        "evidence_location": evidence,
        "failure_reason": reason,
        "confidence": 0.93,
        "receipt_hash": _hash({"receipt": candidate_id}),
        "receipt_verified": True,
    }


def _human(*, chosen: str = "candidate-a", rejected: str = "candidate-b") -> dict:
    return {
        "review_status": "reviewed",
        "chosen_candidate_id": chosen,
        "rejected_candidate_id": rejected,
        "review_id_hash": _hash("review-id"),
        "reviewer_receipt_hash": _hash("reviewer-receipt"),
        "reviewed_at_unix_ms": 1785060000000,
        "review_reason_code": "independent_gold_adjudication",
    }


def _pair_and_source(
    *,
    human_chosen: str = "candidate-a",
    human_rejected: str = "candidate-b",
    media_seed: str = "image-bytes-1",
    source_group_seed: str = "original-camera-capture-1",
    dataset_split: str = "train",
) -> tuple[dict, dict]:
    prompt = {"text": "Weather in Shanghai?"}
    traces = {
        "candidate-a": [
            {
                "tool": "weather.lookup",
                "arguments": {"city": "Shanghai"},
                "observation": {"condition": "rain"},
            }
        ],
        "candidate-b": [
            {
                "tool": "weather.lookup",
                "arguments": {},
                "observation": {"error": "city required"},
            }
        ],
    }
    answers = {
        "candidate-a": {"text": "It is raining in Shanghai."},
        "candidate-b": {"text": "The weather is sunny."},
    }
    candidates = [
        _candidate(
            "candidate-a",
            traces["candidate-a"],
            answers["candidate-a"],
            media_seed=media_seed,
        ),
        _candidate(
            "candidate-b",
            traces["candidate-b"],
            answers["candidate-b"],
            media_seed=media_seed,
        ),
    ]
    pair = build_governed_preference_pair(
        candidates,
        [
            _evaluation("candidate-a", rank=1, reward=0.95, passed=True),
            _evaluation("candidate-b", rank=2, reward=0.2, passed=False),
        ],
        human_adjudication=_human(
            chosen=human_chosen,
            rejected=human_rejected,
        ),
    )
    media_hash = candidates[0]["media_evidence_hashes"][0]
    source = {
        "pair_id": pair["pair_id"],
        "prompt": prompt,
        "media_artifacts": [
            {
                "content_hash": media_hash,
                "modality": "image",
                "mime_type": "image/png",
                "storage_ref": f"cas://{media_hash}",
                "source_group_hash": _hash(source_group_seed),
            }
        ],
        "candidates": [
            {
                "candidate_id": candidate_id,
                "model_version": f"candidate-model-{candidate_id}-v1",
                "execution_trace": traces[candidate_id],
                "final_answer": answers[candidate_id],
            }
            for candidate_id in ("candidate-a", "candidate-b")
        ],
        "governance": {
            "consent_id_hash": _hash("consent"),
            "lineage_hash": _hash("lineage"),
            "residency": "CN",
            "retention_until": "2027-07-26T00:00:00Z",
            "deletion_key_hash": _hash("delete"),
            "authorization_hash": _hash("authorization"),
            "dataset_split": dataset_split,
            "data_classification": "restricted_training",
        },
    }
    return pair, source


def test_human_gold_builds_reward_dpo_and_action_value_records():
    pair, source = _pair_and_source()

    records = build_private_training_records(pair, source)

    assert [record["purpose"] for record in records] == [
        "reward_model_training",
        "preference_optimization",
        "action_value_training",
        "action_value_training",
    ]
    reward = records[0]
    assert reward["payload"]["chosen"]["candidate_id"] == "candidate-a"
    assert reward["payload"]["rejected"]["candidate_id"] == "candidate-b"
    assert reward["payload"]["preference_label"]["authority"] == "human_gold"
    actions = records[2:]
    assert {record["payload"]["candidate_id"] for record in actions} == {
        "candidate-a",
        "candidate-b",
    }
    assert all(record["record_id"] == _hash(
        {key: value for key, value in record.items() if key != "record_id"}
    ) for record in records)


def test_human_override_remains_authoritative_when_releasefoundry_reward_is_opposite():
    pair, source = _pair_and_source(
        human_chosen="candidate-b",
        human_rejected="candidate-a",
    )

    records = build_private_training_records(
        pair,
        source,
        purposes=["reward_model_training"],
    )

    payload = records[0]["payload"]
    assert payload["chosen"]["candidate_id"] == "candidate-b"
    assert payload["chosen"]["releasefoundry_evaluation"]["overall_reward"] == 0.2
    assert payload["rejected"]["releasefoundry_evaluation"]["overall_reward"] == 0.95
    assert payload["preference_label"]["human_override_of_releasefoundry"] is True


def test_provisional_pair_is_rejected():
    pair, source = _pair_and_source()
    pair["human_adjudication"] = None
    pair["preference_authority"] = "releasefoundry_provisional"
    pair["status"] = "provisional_preference"
    pair["training_eligible"] = False
    pair["review_required"] = True
    pair["pair_id"] = _hash({key: value for key, value in pair.items() if key != "pair_id"})
    source["pair_id"] = pair["pair_id"]

    with pytest.raises(
        PreferenceDatasetError,
        match="preference_pair_not_training_eligible",
    ):
        build_private_training_records(pair, source)


def test_tampered_pair_id_is_rejected():
    pair, source = _pair_and_source()
    pair["pair_id"] = _hash("tampered")
    source["pair_id"] = pair["pair_id"]

    with pytest.raises(PreferenceDatasetError, match="preference_pair_id_mismatch"):
        build_private_training_records(pair, source)


def test_prompt_trace_and_answer_hash_mismatches_are_rejected():
    pair, source = _pair_and_source()
    prompt_mismatch = copy.deepcopy(source)
    prompt_mismatch["prompt"]["text"] = "Different prompt"
    with pytest.raises(PreferenceDatasetError, match="source_prompt_hash_mismatch"):
        build_private_training_records(pair, prompt_mismatch)

    trace_mismatch = copy.deepcopy(source)
    trace_mismatch["candidates"][0]["execution_trace"][0]["arguments"]["city"] = "Paris"
    with pytest.raises(PreferenceDatasetError, match="source_trace_hash_mismatch"):
        build_private_training_records(pair, trace_mismatch)

    answer_mismatch = copy.deepcopy(source)
    answer_mismatch["candidates"][0]["final_answer"]["text"] = "Different answer"
    with pytest.raises(
        PreferenceDatasetError,
        match="source_final_answer_hash_mismatch",
    ):
        build_private_training_records(pair, answer_mismatch)


def test_media_hash_and_storage_reference_mismatches_are_rejected():
    pair, source = _pair_and_source()
    media_mismatch = copy.deepcopy(source)
    other_hash = _hash("other-media")
    media_mismatch["media_artifacts"][0]["content_hash"] = other_hash
    media_mismatch["media_artifacts"][0]["storage_ref"] = f"cas://{other_hash}"
    with pytest.raises(PreferenceDatasetError, match="source_media_hash_mismatch"):
        build_private_training_records(pair, media_mismatch)

    ref_mismatch = copy.deepcopy(source)
    ref_mismatch["media_artifacts"][0]["storage_ref"] = (
        "https://example.invalid/media?signature=secret"
    )
    with pytest.raises(
        PreferenceDatasetError,
        match="secret_or_credential_material_rejected",
    ):
        build_private_training_records(pair, ref_mismatch)


def test_missing_extra_and_duplicate_source_candidates_are_rejected():
    pair, source = _pair_and_source()
    missing = copy.deepcopy(source)
    missing["candidates"].pop()
    with pytest.raises(
        PreferenceDatasetError,
        match="source_candidate_coverage_mismatch",
    ):
        build_private_training_records(pair, missing)

    extra = copy.deepcopy(source)
    extra["candidates"].append(
        {
            "candidate_id": "candidate-c",
            "model_version": "candidate-model-candidate-c-v1",
            "execution_trace": [],
            "final_answer": {},
        }
    )
    with pytest.raises(PreferenceDatasetError, match="source_candidate_not_in_pair"):
        build_private_training_records(pair, extra)

    duplicate = copy.deepcopy(source)
    duplicate["candidates"][1] = copy.deepcopy(duplicate["candidates"][0])
    with pytest.raises(PreferenceDatasetError, match="source_candidate_duplicate"):
        build_private_training_records(pair, duplicate)


@pytest.mark.parametrize(
    "unsafe_value",
    [
        "Bear" + "er live-secret",
        "releasefoundry_" + "live_hiddencredential",
        "C:" + r"\Users\private\raw.json",
        "https://example.invalid/file?" + "token=secret",
    ],
)
def test_raw_secret_authorization_signed_url_and_private_path_are_rejected(
    unsafe_value,
):
    pair, source = _pair_and_source()
    source["prompt"]["unsafe"] = unsafe_value

    with pytest.raises(
        PreferenceDatasetError,
        match="secret_or_credential_material_rejected",
    ):
        build_private_training_records(pair, source)


def test_sensitive_trace_key_is_rejected():
    pair, source = _pair_and_source()
    source["candidates"][0]["execution_trace"][0]["Authorization"] = "redacted"

    with pytest.raises(
        PreferenceDatasetError,
        match="secret_or_credential_material_rejected",
    ):
        build_private_training_records(pair, source)


def test_action_index_out_of_range_is_rejected_with_valid_pair_hash():
    pair, source = _pair_and_source()
    pair["releasefoundry_evaluations"][0]["action_scores"][0]["action_index"] = 1
    pair["pair_id"] = _hash({key: value for key, value in pair.items() if key != "pair_id"})
    source["pair_id"] = pair["pair_id"]

    with pytest.raises(PreferenceDatasetError, match="releasefoundry_action_index_out_of_range"):
        build_private_training_records(pair, source)


def test_writer_requires_explicit_private_authorization_and_root(tmp_path):
    pair, source = _pair_and_source()
    records = build_private_training_records(pair, source)
    private_root = tmp_path / "private"

    with pytest.raises(
        PreferenceDatasetError,
        match="private_write_requires_explicit_authorization",
    ):
        write_private_training_jsonl(
            private_root / "records.jsonl",
            records,
            private_root=private_root,
        )

    with pytest.raises(
        PreferenceDatasetError,
        match="private_path_outside_private_root",
    ):
        write_private_training_jsonl(
            tmp_path / "outside.jsonl",
            records,
            private_root=private_root,
            allow_private_write=True,
        )


def test_private_jsonl_round_trip_has_path_free_public_manifest(tmp_path):
    pair, source = _pair_and_source()
    records = build_private_training_records(pair, source)
    private_root = tmp_path / "private"
    path = private_root / "training" / "records.jsonl"

    manifest = write_private_training_jsonl(
        path,
        records,
        private_root=private_root,
        allow_private_write=True,
        created_at="2026-07-26T12:00:00Z",
    )
    loaded = load_private_training_jsonl(
        path,
        manifest,
        private_root=private_root,
    )

    assert loaded == records
    assert manifest["record_count"] == 4
    assert manifest["purpose_counts"] == {
        "action_value_training": 2,
        "preference_optimization": 1,
        "reward_model_training": 1,
    }
    assert manifest["public_safe"] is True
    assert manifest["private_artifact_required"] is True
    serialized = str(manifest)
    assert str(path) not in serialized
    assert "Weather in Shanghai?" not in serialized
    assert "storage_ref" not in serialized
    assert "execution_trace" not in serialized
    assert "final_answer" not in serialized
    assert not list(path.parent.glob("*.tmp"))


def test_private_jsonl_tampering_fails_closed(tmp_path):
    pair, source = _pair_and_source()
    records = build_private_training_records(pair, source)
    private_root = tmp_path / "private"
    path = private_root / "records.jsonl"
    manifest = write_private_training_jsonl(
        path,
        records,
        private_root=private_root,
        allow_private_write=True,
        created_at="2026-07-26T12:00:00Z",
    )
    path.write_text(path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

    with pytest.raises(PreferenceDatasetError):
        load_private_training_jsonl(path, manifest, private_root=private_root)


def test_manifest_tampering_fails_closed(tmp_path):
    pair, source = _pair_and_source()
    records = build_private_training_records(pair, source)
    private_root = tmp_path / "private"
    path = private_root / "records.jsonl"
    manifest = write_private_training_jsonl(
        path,
        records,
        private_root=private_root,
        allow_private_write=True,
        created_at="2026-07-26T12:00:00Z",
    )
    manifest["dataset_hash"] = _hash("tampered")

    with pytest.raises(
        PreferenceDatasetError,
        match="private_jsonl_dataset_hash_mismatch",
    ):
        load_private_training_jsonl(path, manifest, private_root=private_root)


def test_source_split_isolation_rejects_content_and_group_leakage():
    pair, source = _pair_and_source()
    train_records = build_private_training_records(
        pair,
        source,
        purposes=["reward_model_training"],
    )
    test_records = copy.deepcopy(train_records)
    test_records[0]["dataset_split"] = "test"
    test_records[0]["governance"]["dataset_split"] = "test"
    core = {
        key: value for key, value in test_records[0].items() if key != "record_id"
    }
    test_records[0]["record_id"] = _hash(core)

    with pytest.raises(
        PreferenceDatasetError,
        match="media_content_hash_split_leakage",
    ):
        verify_source_split_isolation(train_records + test_records)

    different_content = copy.deepcopy(test_records)
    other_hash = _hash("other-content")
    different_content[0]["media_artifacts"][0]["content_hash"] = other_hash
    different_content[0]["media_artifacts"][0]["storage_ref"] = f"cas://{other_hash}"
    with pytest.raises(
        PreferenceDatasetError,
        match="media_source_group_split_leakage",
    ):
        verify_source_split_isolation(train_records + different_content)


def test_private_training_corpus_enforces_cross_file_split_isolation(tmp_path):
    train_pair, train_source = _pair_and_source()
    train_records = build_private_training_records(
        train_pair,
        train_source,
        purposes=["reward_model_training"],
    )
    private_root = tmp_path / "private"
    train_path = private_root / "train.jsonl"
    train_manifest = write_private_training_jsonl(
        train_path,
        train_records,
        private_root=private_root,
        allow_private_write=True,
        created_at="2026-08-01T08:00:00Z",
    )

    safe_pair, safe_source = _pair_and_source(
        media_seed="independent-test-image",
        source_group_seed="independent-test-capture",
        dataset_split="test",
    )
    safe_records = build_private_training_records(
        safe_pair,
        safe_source,
        purposes=["reward_model_training"],
    )
    safe_path = private_root / "safe-test.jsonl"
    safe_manifest = write_private_training_jsonl(
        safe_path,
        safe_records,
        private_root=private_root,
        allow_private_write=True,
        created_at="2026-08-01T08:01:00Z",
    )

    loaded = load_private_training_corpus(
        [
            (train_path, train_manifest),
            (safe_path, safe_manifest),
        ],
        private_root=private_root,
    )

    assert loaded == train_records + safe_records

    leaked_pair, leaked_source = _pair_and_source(dataset_split="test")
    leaked_records = build_private_training_records(
        leaked_pair,
        leaked_source,
        purposes=["reward_model_training"],
    )
    leaked_path = private_root / "content-leak-test.jsonl"
    leaked_manifest = write_private_training_jsonl(
        leaked_path,
        leaked_records,
        private_root=private_root,
        allow_private_write=True,
        created_at="2026-08-01T08:02:00Z",
    )
    with pytest.raises(
        PreferenceDatasetError,
        match="media_content_hash_split_leakage",
    ):
        load_private_training_corpus(
            [
                (train_path, train_manifest),
                (leaked_path, leaked_manifest),
            ],
            private_root=private_root,
        )

    derived_pair, derived_source = _pair_and_source(
        media_seed="cropped-image-bytes",
        dataset_split="test",
    )
    derived_records = build_private_training_records(
        derived_pair,
        derived_source,
        purposes=["reward_model_training"],
    )
    derived_path = private_root / "source-group-leak-test.jsonl"
    derived_manifest = write_private_training_jsonl(
        derived_path,
        derived_records,
        private_root=private_root,
        allow_private_write=True,
        created_at="2026-08-01T08:03:00Z",
    )
    with pytest.raises(
        PreferenceDatasetError,
        match="media_source_group_split_leakage",
    ):
        load_private_training_corpus(
            [
                (train_path, train_manifest),
                (derived_path, derived_manifest),
            ],
            private_root=private_root,
        )


def test_training_record_output_is_deterministic_across_source_candidate_order():
    pair, source = _pair_and_source()

    first = build_private_training_records(pair, source)
    source["candidates"].reverse()
    second = build_private_training_records(pair, source)

    assert second == first
