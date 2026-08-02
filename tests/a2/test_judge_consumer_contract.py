from __future__ import annotations

from copy import deepcopy

import pytest

from services.judge.blind_version_comparison import (
    VALID_RELEASE_RECOMMENDATIONS as BLIND_RELEASE_RECOMMENDATIONS,
)
from services.judge.judge_consumer_contract import (
    JudgeConsumerContractError,
    build_judge_consumer_contract,
    verify_judge_consumer_contract,
)
from services.judge.release_actions import (
    CANONICAL_RELEASE_ACTIONS,
    ReleaseActionError,
    normalize_release_action,
)
from services.judge.result_persistence import stable_hash
from services.judge.unified_label import (
    VALID_FAILURE_CLASSES,
    VALID_RELEASE_RECOMMENDATIONS as LABEL_RELEASE_RECOMMENDATIONS,
)


EXPECTED_RELEASE_ACTIONS = (
    "allow",
    "staged_rollout",
    "restrict_capability",
    "retest",
    "human_review",
    "block",
)


def test_publishes_one_canonical_six_action_vocabulary():
    assert CANONICAL_RELEASE_ACTIONS == EXPECTED_RELEASE_ACTIONS
    assert LABEL_RELEASE_RECOMMENDATIONS == frozenset(
        EXPECTED_RELEASE_ACTIONS
    )
    assert BLIND_RELEASE_RECOMMENDATIONS == frozenset(
        EXPECTED_RELEASE_ACTIONS
    )

    contract = build_judge_consumer_contract()
    assert tuple(
        item["id"] for item in contract["release_actions"]
    ) == EXPECTED_RELEASE_ACTIONS
    assert contract["release_action_policy"] == {
        "canonical_output_only": True,
        "unknown_input": "fail_closed",
    }


@pytest.mark.parametrize(
    "value,expected",
    [
        ("allow", "allow"),
        ("staged_rollout", "staged_rollout"),
        ("restrict_capability", "restrict_capability"),
        ("retest", "retest"),
        ("human_review", "human_review"),
        ("block", "block"),
        ("canary", "staged_rollout"),
        ("limit_capability", "restrict_capability"),
    ],
)
def test_normalizes_supported_actions_and_external_aliases(value, expected):
    assert normalize_release_action(value) == expected


@pytest.mark.parametrize("value", ["ship", "ALLOW", "", None, 1])
def test_unknown_or_malformed_release_action_fails_closed(value):
    with pytest.raises(ReleaseActionError):
        normalize_release_action(value)


def test_manifest_covers_every_a2_failure_type_without_private_inputs():
    contract = build_judge_consumer_contract()

    assert contract["failure_types"] == sorted(VALID_FAILURE_CLASSES)
    assert contract["failure_type_source"].endswith(
        "unified_label.VALID_FAILURE_CLASSES"
    )
    assert contract["data_boundary"] == {
        "public_safe_only": True,
        "raw_input_required": False,
        "raw_output_required": False,
        "raw_evidence_required": False,
        "private_evidence_required": False,
        "structured_evidence_locations_required": True,
    }


def test_manifest_is_deterministic_hash_bound_and_verifiable():
    contract = build_judge_consumer_contract()
    payload = {
        key: value
        for key, value in contract.items()
        if key != "contract_hash"
    }

    assert contract["contract_hash"] == stable_hash(payload)
    assert contract == build_judge_consumer_contract()
    verify_judge_consumer_contract(contract)


def test_verifier_rejects_tampered_contract():
    contract = deepcopy(build_judge_consumer_contract())
    contract["failure_types"].pop()

    with pytest.raises(
        JudgeConsumerContractError,
        match="contract_hash_mismatch",
    ):
        verify_judge_consumer_contract(contract)
