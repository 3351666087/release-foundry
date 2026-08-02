"""Receipt-bound ReleaseFoundry observations for governed preference learning.

ReleaseFoundry currently exposes per-action comparison signals and final-answer grading,
but not a native multi-candidate ranking endpoint. This adapter therefore:

1. verifies the exact run/test set and per-test grading markers;
2. deterministically normalizes only observed ReleaseFoundry signals;
3. binds the normalized scores to the raw server test result by hash;
4. derives an explicitly non-native ranking from those observations; and
5. delegates governance to ``build_governed_preference_pair``.

The resulting pair is provisional only. It is not human gold, training
authority, C3 evidence, or release authority.
"""

from __future__ import annotations

import copy
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .preference_learning import build_governed_preference_pair
from .result_persistence import stable_hash


RUN_RECEIPT_SCHEMA_VERSION = "a2.releasefoundry_preference_run_receipt_private.v1"
SCORE_RECEIPT_SCHEMA_VERSION = "a2.releasefoundry_preference_score_receipt.v1"
ARTIFACT_SCHEMA_VERSION = "a2.releasefoundry_provisional_preference_artifact.v1"
PUBLIC_ARTIFACT_SCHEMA_VERSION = (
    "a2.releasefoundry_provisional_preference_public_artifact.v1"
)
NORMALIZATION_VERSION = "a2.releasefoundry_observation_normalization.v1"
RANKING_SOURCE = "derived_from_releasefoundry_observations"
SERVER_NATIVE_PAIRWISE_RANKING = False
ACTION_WEIGHT = 0.50
FINAL_ANSWER_WEIGHT = 0.40
COHERENCE_WEIGHT = 0.10
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
TERMINAL_RUN_STATUSES = {"completed", "completed_with_failures", "failed"}
TERMINAL_TEST_STATUSES = {"completed", "failed"}
PASS_MATCH_STATUSES = {"exact", "match", "passed"}
PASS_FINAL_VERDICTS = {"exact", "match", "pass", "passed", "acceptable"}
FINAL_VERDICT_SCORE_CAPS = {
    "minor_issue": 70.0,
    "partial": 60.0,
    "major_issue": 25.0,
    "divergent": 10.0,
    "mismatch": 10.0,
    "fail": 0.0,
    "failed": 0.0,
}


class ReleaseFoundryPreferenceEvaluationError(ValueError):
    """Raised when an ReleaseFoundry preference observation cannot be verified."""


def build_releasefoundry_run_binding_receipt(
    run: Mapping[str, Any],
    *,
    expected_test_ids: Sequence[str],
    expected_dataset_id: int | str,
    dataset_identity_hash: str,
) -> dict[str, Any]:
    """Bind one paid run to an exact dataset and exact, fully graded test set."""

    if not isinstance(run, Mapping):
        raise ReleaseFoundryPreferenceEvaluationError("run_payload_invalid")
    expected = _unique_strings(expected_test_ids, "expected_test_ids")
    if not expected:
        raise ReleaseFoundryPreferenceEvaluationError("expected_test_ids_missing")
    _require_hash(dataset_identity_hash, "dataset_identity_hash")

    observed_dataset_id = run.get("dataset")
    if observed_dataset_id != expected_dataset_id:
        raise ReleaseFoundryPreferenceEvaluationError("run_dataset_id_mismatch")
    result = run.get("result")
    if not isinstance(result, Mapping):
        raise ReleaseFoundryPreferenceEvaluationError("run_result_missing")
    status = str(result.get("status", "")).strip().lower()
    if status not in TERMINAL_RUN_STATUSES:
        raise ReleaseFoundryPreferenceEvaluationError("run_result_not_terminal")

    tests = result.get("tests")
    if not isinstance(tests, list):
        raise ReleaseFoundryPreferenceEvaluationError("run_tests_missing")
    indexed: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for test in tests:
        if not isinstance(test, Mapping):
            raise ReleaseFoundryPreferenceEvaluationError("run_test_not_object")
        test_id = test.get("test_id")
        if not isinstance(test_id, str) or not test_id:
            raise ReleaseFoundryPreferenceEvaluationError("run_test_id_missing")
        indexed[test_id].append(test)

    expected_set = set(expected)
    if set(indexed) != expected_set:
        raise ReleaseFoundryPreferenceEvaluationError("run_test_set_mismatch")
    if any(len(indexed[test_id]) != 1 for test_id in expected):
        raise ReleaseFoundryPreferenceEvaluationError("run_test_id_not_unique")

    test_receipts = []
    for test_id in expected:
        test = indexed[test_id][0]
        _assert_test_fully_graded(test, expected_test_id=test_id)
        test_receipts.append(
            {
                "test_id": test_id,
                "server_test_result_hash": stable_hash(test),
                "server_grading_marker_verified": True,
                "final_answer_grading_marker_verified": True,
            }
        )

    core = {
        "schema_version": RUN_RECEIPT_SCHEMA_VERSION,
        "dataset_identity_hash": dataset_identity_hash,
        "expected_dataset_id": expected_dataset_id,
        "run_id": _required_identifier(run.get("id"), "run_id_missing"),
        "run_result_status": status,
        "expected_test_count": len(expected),
        "exact_test_set_verified": True,
        "per_test_server_grading_verified": True,
        "per_test_final_answer_grading_verified": True,
        "aggregate_marker_used_as_authority": False,
        "test_receipts": sorted(test_receipts, key=lambda item: item["test_id"]),
        "run_result_hash": stable_hash(result),
        "judge_version_observed": _judge_version_observed(run, result),
        "acceptance_authority": False,
        "training_authority": False,
        "release_authority": False,
    }
    return {**core, "receipt_hash": stable_hash(core)}


def verify_releasefoundry_run_binding_receipt(receipt: Mapping[str, Any]) -> None:
    """Reject a missing, incomplete, or tampered private run receipt."""

    if not isinstance(receipt, Mapping):
        raise ReleaseFoundryPreferenceEvaluationError("run_receipt_invalid")
    receipt_hash = receipt.get("receipt_hash")
    _require_hash(receipt_hash, "run_receipt_hash")
    core = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if stable_hash(core) != receipt_hash:
        raise ReleaseFoundryPreferenceEvaluationError("run_receipt_hash_mismatch")
    if receipt.get("schema_version") != RUN_RECEIPT_SCHEMA_VERSION:
        raise ReleaseFoundryPreferenceEvaluationError("run_receipt_schema_mismatch")
    for field in (
        "exact_test_set_verified",
        "per_test_server_grading_verified",
        "per_test_final_answer_grading_verified",
    ):
        if receipt.get(field) is not True:
            raise ReleaseFoundryPreferenceEvaluationError(f"run_receipt_{field}_required")
    if receipt.get("aggregate_marker_used_as_authority") is not False:
        raise ReleaseFoundryPreferenceEvaluationError("aggregate_marker_authority_forbidden")


def build_provisional_preference_artifact(
    *,
    candidate_batch_id: str,
    candidates: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    known_failure_classes: Sequence[str] = (),
) -> dict[str, Any]:
    """Normalize real ReleaseFoundry observations and build one governed provisional pair.

    Each observation must contain:

    - ``candidate_id``
    - ``expected_test_id``
    - ``server_test_result``
    - ``run_receipt``
    """

    _require_hash(candidate_batch_id, "candidate_batch_id")
    candidate_ids = _candidate_ids(candidates)
    by_candidate = _normalize_observations(observations, candidate_ids)

    unranked: list[dict[str, Any]] = []
    receipt_context: dict[str, dict[str, Any]] = {}
    for candidate_id in sorted(candidate_ids):
        observation = by_candidate[candidate_id]
        run_receipt = observation["run_receipt"]
        verify_releasefoundry_run_binding_receipt(run_receipt)
        test = observation["server_test_result"]
        expected_test_id = observation["expected_test_id"]
        _assert_test_receipt_membership(
            run_receipt,
            expected_test_id=expected_test_id,
            test=test,
        )
        evaluation = _normalize_server_test(candidate_id, test)
        unranked.append(evaluation)
        receipt_context[candidate_id] = {
            "expected_test_id": expected_test_id,
            "run_receipt_hash": run_receipt["receipt_hash"],
            "server_test_result_hash": stable_hash(test),
        }

    ranks = _derived_ranks(unranked)
    evaluations = []
    score_receipts = []
    for evaluation in unranked:
        candidate_id = evaluation["candidate_id"]
        normalized = {**evaluation, "rank": ranks[candidate_id]}
        context = receipt_context[candidate_id]
        receipt_core = {
            "schema_version": SCORE_RECEIPT_SCHEMA_VERSION,
            "candidate_batch_id": candidate_batch_id,
            "candidate_id": candidate_id,
            "releasefoundry_test_id_hash": stable_hash(context["expected_test_id"]),
            "server_test_result_hash": context["server_test_result_hash"],
            "run_receipt_hash": context["run_receipt_hash"],
            "normalization_version": NORMALIZATION_VERSION,
            "ranking_source": RANKING_SOURCE,
            "server_native_pairwise_ranking": SERVER_NATIVE_PAIRWISE_RANKING,
            "normalized_evaluation_hash": stable_hash(normalized),
            "score_binding_verified": True,
            "human_gold": False,
            "training_authority": False,
            "release_authority": False,
        }
        score_receipt = {**receipt_core, "receipt_hash": stable_hash(receipt_core)}
        score_receipts.append(score_receipt)
        evaluations.append(
            {
                **normalized,
                "receipt_hash": score_receipt["receipt_hash"],
                "receipt_verified": True,
            }
        )

    pair = build_governed_preference_pair(
        candidates,
        evaluations,
        known_failure_classes=known_failure_classes,
    )
    artifact_core = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "candidate_batch_id": candidate_batch_id,
        "ranking": {
            "source": RANKING_SOURCE,
            "server_native_pairwise_ranking": SERVER_NATIVE_PAIRWISE_RANKING,
            "normalization_version": NORMALIZATION_VERSION,
            "weights": {
                "action": ACTION_WEIGHT,
                "final_answer": FINAL_ANSWER_WEIGHT,
                "coherence": COHERENCE_WEIGHT,
            },
            "ties_block_preference": True,
        },
        "pair": pair,
        "score_receipts": score_receipts,
        "human_gold": False,
        "human_review_required": True,
        "training_eligible": False,
        "c3_authority": False,
        "c3_transition_allowed": False,
        "release_authority": False,
        "private_source_required_for_training": True,
    }
    return {**artifact_core, "artifact_hash": stable_hash(artifact_core)}


def verify_releasefoundry_score_receipt(
    receipt: Mapping[str, Any],
    *,
    evaluation: Mapping[str, Any] | None = None,
) -> None:
    """Reject a missing, incomplete, tampered, or misbound score receipt."""

    if not isinstance(receipt, Mapping):
        raise ReleaseFoundryPreferenceEvaluationError("score_receipt_invalid")
    receipt_hash = receipt.get("receipt_hash")
    _require_hash(receipt_hash, "score_receipt_hash")
    core = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if stable_hash(core) != receipt_hash:
        raise ReleaseFoundryPreferenceEvaluationError("score_receipt_hash_mismatch")
    if receipt.get("schema_version") != SCORE_RECEIPT_SCHEMA_VERSION:
        raise ReleaseFoundryPreferenceEvaluationError("score_receipt_schema_mismatch")
    if receipt.get("score_binding_verified") is not True:
        raise ReleaseFoundryPreferenceEvaluationError("score_binding_verification_required")
    for field in ("human_gold", "training_authority", "release_authority"):
        if receipt.get(field) is not False:
            raise ReleaseFoundryPreferenceEvaluationError(
                f"score_receipt_{field}_must_be_false"
            )
    if evaluation is None:
        return
    if not isinstance(evaluation, Mapping):
        raise ReleaseFoundryPreferenceEvaluationError("score_evaluation_invalid")
    if evaluation.get("candidate_id") != receipt.get("candidate_id"):
        raise ReleaseFoundryPreferenceEvaluationError("score_receipt_candidate_mismatch")
    normalized = _score_bound_evaluation(evaluation)
    if stable_hash(normalized) != receipt.get("normalized_evaluation_hash"):
        raise ReleaseFoundryPreferenceEvaluationError(
            "score_receipt_evaluation_hash_mismatch"
        )
    if evaluation.get("receipt_hash") != receipt_hash:
        raise ReleaseFoundryPreferenceEvaluationError("score_receipt_reference_mismatch")
    if evaluation.get("receipt_verified") is not True:
        raise ReleaseFoundryPreferenceEvaluationError("score_receipt_not_verified")


def build_public_provisional_preference_artifact(
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a private score-bound artifact into commit-safe evidence."""

    if not isinstance(artifact, Mapping):
        raise ReleaseFoundryPreferenceEvaluationError("private_artifact_invalid")
    artifact_hash = artifact.get("artifact_hash")
    _require_hash(artifact_hash, "private_artifact_hash")
    core = {key: value for key, value in artifact.items() if key != "artifact_hash"}
    if stable_hash(core) != artifact_hash:
        raise ReleaseFoundryPreferenceEvaluationError("private_artifact_hash_mismatch")
    if artifact.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ReleaseFoundryPreferenceEvaluationError("private_artifact_schema_mismatch")

    pair = artifact.get("pair")
    receipts = artifact.get("score_receipts")
    if not isinstance(pair, Mapping) or not isinstance(receipts, list):
        raise ReleaseFoundryPreferenceEvaluationError("private_artifact_content_missing")
    evaluations = pair.get("releasefoundry_evaluations")
    if not isinstance(evaluations, list):
        raise ReleaseFoundryPreferenceEvaluationError("private_artifact_evaluations_missing")
    by_candidate = {
        item.get("candidate_id"): item
        for item in evaluations
        if isinstance(item, Mapping)
        and isinstance(item.get("candidate_id"), str)
    }
    if len(by_candidate) != len(evaluations):
        raise ReleaseFoundryPreferenceEvaluationError(
            "private_artifact_evaluation_ids_invalid"
        )
    seen_receipts: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            raise ReleaseFoundryPreferenceEvaluationError("score_receipt_invalid")
        candidate_id = receipt.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in seen_receipts:
            raise ReleaseFoundryPreferenceEvaluationError("score_receipt_candidate_invalid")
        evaluation = by_candidate.get(candidate_id)
        if evaluation is None:
            raise ReleaseFoundryPreferenceEvaluationError(
                "score_receipt_candidate_coverage_mismatch"
            )
        verify_releasefoundry_score_receipt(receipt, evaluation=evaluation)
        seen_receipts.add(candidate_id)
    if seen_receipts != set(by_candidate):
        raise ReleaseFoundryPreferenceEvaluationError(
            "score_receipt_candidate_coverage_mismatch"
        )

    public_core = {
        "schema_version": PUBLIC_ARTIFACT_SCHEMA_VERSION,
        "private_artifact_hash": artifact_hash,
        "candidate_batch_id": artifact.get("candidate_batch_id"),
        "ranking": copy.deepcopy(artifact.get("ranking")),
        "pair": copy.deepcopy(pair),
        "observation_summary": {
            "candidate_count": len(evaluations),
            "score_receipt_count": len(receipts),
            "all_score_receipts_verified": True,
        },
        "human_gold": False,
        "human_review_required": True,
        "training_eligible": False,
        "c3_authority": False,
        "c3_transition_allowed": False,
        "release_authority": False,
        "private_source_required_for_training": True,
    }
    return {**public_core, "artifact_hash": stable_hash(public_core)}


def _normalize_server_test(
    candidate_id: str,
    test: Mapping[str, Any],
) -> dict[str, Any]:
    _assert_test_fully_graded(test, expected_test_id=str(test.get("test_id", "")))
    action_scores = _tool_action_scores(test)
    final = _final_answer_observation(test)
    coherence_score = _coherence_score(test)
    action_mean = (
        sum(item["score"] for item in action_scores) / len(action_scores)
        if action_scores
        else None
    )
    if action_mean is None:
        overall_reward = 0.9 * final["score"] + 0.1 * coherence_score
    else:
        overall_reward = (
            ACTION_WEIGHT * action_mean
            + FINAL_ANSWER_WEIGHT * final["score"]
            + COHERENCE_WEIGHT * coherence_score
        )

    failed_action = next(
        (item for item in action_scores if not item["passed"]),
        None,
    )
    if failed_action is not None:
        failure_type = failed_action["failure_type"]
        severity = _severity_for_failure(failure_type)
        failure_action = f"action_index:{failed_action['action_index']}"
        evidence_location: dict[str, Any] = dict(failed_action["evidence_location"])
        failure_reason = failed_action["reason"]
    elif not final["passed"]:
        failure_type = "wrong_intent"
        severity = "medium"
        failure_action = f"action_index:{final['action_index']}"
        evidence_location = {
            "action_index": final["action_index"],
            "field": "final_response_grading",
        }
        failure_reason = f"releasefoundry_final_verdict:{final['verdict'] or 'unknown'}"
    else:
        failure_type = "none"
        severity = "none"
        failure_action = ""
        evidence_location = {}
        failure_reason = ""

    return {
        "candidate_id": candidate_id,
        "action_scores": action_scores,
        "final_answer_score": round(final["score"], 4),
        "overall_reward": round(overall_reward, 4),
        "failure_type": failure_type,
        "severity": severity,
        "failure_action": failure_action,
        "evidence_location": evidence_location,
        "failure_reason": failure_reason,
        "confidence": _observation_confidence(test, final),
    }


def _tool_action_scores(test: Mapping[str, Any]) -> list[dict[str, Any]]:
    scores = []
    actions = test.get("action_results")
    for action in actions if isinstance(actions, list) else []:
        if (
            not isinstance(action, Mapping)
            or action.get("actor") != "agent"
            or action.get("action_type") != "tool_call"
        ):
            continue
        action_index = _non_negative_int(
            action.get("action_index"),
            "tool_action_index_invalid",
        )
        calls = action.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            raise ReleaseFoundryPreferenceEvaluationError("tool_action_calls_missing")
        if len(calls) != 1:
            raise ReleaseFoundryPreferenceEvaluationError("tool_action_call_count_unsupported")
        call = calls[0]
        if not isinstance(call, Mapping):
            raise ReleaseFoundryPreferenceEvaluationError("tool_call_result_invalid")
        status = str(call.get("match_status", "")).strip().lower()
        passed = status in PASS_MATCH_STATUSES
        failure_type = "none" if passed else _tool_failure_type(call)
        score = _tool_score(call, passed=passed)
        scores.append(
            {
                "action_index": action_index,
                "score": round(score, 4),
                "passed": passed,
                "failure_type": failure_type,
                "evidence_location": {
                    "action_index": action_index,
                    "field": "tool_call_comparison",
                },
                "reason": "" if passed else f"releasefoundry_tool_match_status:{status or 'missing'}",
            }
        )
    return sorted(scores, key=lambda item: item["action_index"])


def _score_bound_evaluation(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {
        key: copy.deepcopy(value)
        for key, value in evaluation.items()
        if key not in {"receipt_hash", "receipt_verified"}
    }
    action_scores = normalized.get("action_scores")
    if isinstance(action_scores, list):
        normalized["action_scores"] = [
            {
                key: value
                for key, value in action.items()
                if key != "candidate_id"
            }
            if isinstance(action, Mapping)
            else action
            for action in action_scores
        ]
    return normalized


def _final_answer_observation(test: Mapping[str, Any]) -> dict[str, Any]:
    actions = test.get("action_results")
    matches = []
    for action in actions if isinstance(actions, list) else []:
        if (
            isinstance(action, Mapping)
            and action.get("actor") == "agent"
            and action.get("action_type") == "text"
            and _has_final_answer_grading_marker(action)
        ):
            matches.append(action)
    if len(matches) != 1:
        raise ReleaseFoundryPreferenceEvaluationError("final_answer_grading_not_unique")
    action = matches[0]
    action_index = _non_negative_int(
        action.get("action_index"),
        "final_action_index_invalid",
    )
    similarity = action.get("semantic_similarity")
    if not _finite_number(similarity):
        raise ReleaseFoundryPreferenceEvaluationError("final_semantic_similarity_missing")
    score = float(similarity)
    score = score * 100.0 if score <= 1.0 else score
    score = max(0.0, min(100.0, score))
    judgment = action.get("llm_judgment")
    verdict = ""
    if isinstance(judgment, Mapping):
        verdict = str(judgment.get("verdict", "")).strip().lower()
    if verdict in FINAL_VERDICT_SCORE_CAPS:
        score = min(score, FINAL_VERDICT_SCORE_CAPS[verdict])
    match_status = str(action.get("match_status", "")).strip().lower()
    passed = (
        verdict in PASS_FINAL_VERDICTS
        and match_status not in {"mismatch", "failed", "fail", "divergent"}
        and score >= 70.0
    )
    return {
        "action_index": action_index,
        "score": score,
        "verdict": verdict,
        "match_status": match_status,
        "passed": passed,
    }


def _tool_score(call: Mapping[str, Any], *, passed: bool) -> float:
    if passed:
        return 100.0
    expected = call.get("expected")
    actual = call.get("actual")
    expected_name = _tool_name(expected)
    actual_name = _tool_name(actual)
    if actual_name in {"", "NOT_CALLED"}:
        return 0.0
    if expected_name == "NONE_EXPECTED" or expected_name != actual_name:
        return 0.0
    comparison = call.get("argument_comparison")
    if not isinstance(comparison, Mapping):
        return 0.0
    counts = {
        key: _comparison_size(comparison.get(key))
        for key in ("matching", "missing", "extra", "different")
    }
    total = sum(counts.values())
    return 100.0 * counts["matching"] / total if total else 0.0


def _tool_failure_type(call: Mapping[str, Any]) -> str:
    expected_name = _tool_name(call.get("expected"))
    actual_name = _tool_name(call.get("actual"))
    if actual_name in {"", "NOT_CALLED"}:
        return "missing_required_tool"
    if expected_name == "NONE_EXPECTED":
        return "unnecessary_tool_call"
    if expected_name != actual_name:
        return "wrong_tool"
    return "wrong_arguments"


def _coherence_score(test: Mapping[str, Any]) -> float:
    coherence = test.get("coherence")
    if not isinstance(coherence, Mapping):
        return 0.0
    value = coherence.get("score")
    if not _finite_number(value):
        return 0.0
    numeric = float(value)
    numeric = numeric * 100.0 if numeric <= 1.0 else numeric
    return max(0.0, min(100.0, numeric))


def _derived_ranks(evaluations: list[dict[str, Any]]) -> dict[str, int]:
    ordered = sorted(
        evaluations,
        key=lambda item: (-item["overall_reward"], item["candidate_id"]),
    )
    ranks: dict[str, int] = {}
    previous_reward: float | None = None
    previous_rank = 0
    for position, evaluation in enumerate(ordered, start=1):
        reward = float(evaluation["overall_reward"])
        if previous_reward is None or not math.isclose(
            reward,
            previous_reward,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            previous_rank = position
            previous_reward = reward
        ranks[evaluation["candidate_id"]] = previous_rank
    return ranks


def _normalize_observations(
    observations: list[dict[str, Any]],
    candidate_ids: set[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(observations, list):
        raise ReleaseFoundryPreferenceEvaluationError("observations_must_be_list")
    normalized: dict[str, dict[str, Any]] = {}
    required = {
        "candidate_id",
        "expected_test_id",
        "server_test_result",
        "run_receipt",
    }
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) != required:
            raise ReleaseFoundryPreferenceEvaluationError("observation_fields_invalid")
        candidate_id = observation.get("candidate_id")
        if candidate_id not in candidate_ids:
            raise ReleaseFoundryPreferenceEvaluationError("observation_candidate_unknown")
        if candidate_id in normalized:
            raise ReleaseFoundryPreferenceEvaluationError("observation_candidate_duplicate")
        expected_test_id = observation.get("expected_test_id")
        if not isinstance(expected_test_id, str) or not expected_test_id:
            raise ReleaseFoundryPreferenceEvaluationError("expected_test_id_invalid")
        test = observation.get("server_test_result")
        if not isinstance(test, Mapping):
            raise ReleaseFoundryPreferenceEvaluationError("server_test_result_invalid")
        if test.get("test_id") != expected_test_id:
            raise ReleaseFoundryPreferenceEvaluationError("server_test_id_mismatch")
        normalized[str(candidate_id)] = observation
    if set(normalized) != candidate_ids:
        raise ReleaseFoundryPreferenceEvaluationError("observation_candidate_coverage_mismatch")
    return normalized


def _assert_test_receipt_membership(
    run_receipt: Mapping[str, Any],
    *,
    expected_test_id: str,
    test: Mapping[str, Any],
) -> None:
    receipts = run_receipt.get("test_receipts")
    if not isinstance(receipts, list):
        raise ReleaseFoundryPreferenceEvaluationError("run_receipt_tests_missing")
    matches = [
        item
        for item in receipts
        if isinstance(item, Mapping) and item.get("test_id") == expected_test_id
    ]
    if len(matches) != 1:
        raise ReleaseFoundryPreferenceEvaluationError("run_receipt_test_membership_invalid")
    if matches[0].get("server_test_result_hash") != stable_hash(test):
        raise ReleaseFoundryPreferenceEvaluationError("server_test_result_hash_mismatch")
    if matches[0].get("server_grading_marker_verified") is not True:
        raise ReleaseFoundryPreferenceEvaluationError("server_grading_receipt_missing")
    if matches[0].get("final_answer_grading_marker_verified") is not True:
        raise ReleaseFoundryPreferenceEvaluationError("final_answer_receipt_missing")


def _assert_test_fully_graded(
    test: Mapping[str, Any],
    *,
    expected_test_id: str,
) -> None:
    if test.get("test_id") != expected_test_id:
        raise ReleaseFoundryPreferenceEvaluationError("test_id_mismatch")
    status = str(test.get("status", "")).strip().lower()
    if status not in TERMINAL_TEST_STATUSES:
        raise ReleaseFoundryPreferenceEvaluationError("test_status_not_terminal")
    if not _has_server_grading_marker(test):
        raise ReleaseFoundryPreferenceEvaluationError("test_server_grading_missing")
    actions = test.get("action_results")
    final_count = sum(
        isinstance(action, Mapping)
        and action.get("actor") == "agent"
        and action.get("action_type") == "text"
        and _has_final_answer_grading_marker(action)
        for action in actions if isinstance(actions, list)
    )
    if final_count != 1:
        raise ReleaseFoundryPreferenceEvaluationError("test_final_answer_grading_not_unique")


def _has_server_grading_marker(test: Mapping[str, Any]) -> bool:
    actions = test.get("action_results")
    for action in actions if isinstance(actions, list) else []:
        if not isinstance(action, Mapping) or action.get("actor") != "agent":
            continue
        if isinstance(action.get("llm_judgment"), Mapping):
            return True
        if action.get("action_type") != "tool_call":
            continue
        calls = action.get("tool_calls")
        for call in calls if isinstance(calls, list) else []:
            if not isinstance(call, Mapping):
                continue
            if isinstance(call.get("llm_judgment"), Mapping):
                return True
            comparison = call.get("argument_comparison")
            if isinstance(comparison, Mapping) and all(
                key in comparison
                for key in ("matching", "missing", "extra", "different")
            ):
                return True
    coherence = test.get("coherence")
    return isinstance(coherence, Mapping) and _finite_number(coherence.get("score"))


def _has_final_answer_grading_marker(action: Mapping[str, Any]) -> bool:
    if isinstance(action.get("llm_judgment"), Mapping):
        return True
    return _finite_number(action.get("semantic_similarity"))


def _candidate_ids(candidates: list[dict[str, Any]]) -> set[str]:
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise ReleaseFoundryPreferenceEvaluationError("at_least_two_candidates_required")
    values = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ReleaseFoundryPreferenceEvaluationError("candidate_invalid")
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ReleaseFoundryPreferenceEvaluationError("candidate_id_invalid")
        values.append(candidate_id)
    if len(values) != len(set(values)):
        raise ReleaseFoundryPreferenceEvaluationError("candidate_id_duplicate")
    return set(values)


def _severity_for_failure(failure_type: str) -> str:
    if failure_type in {"forbidden_tool_call", "unsafe_or_policy_violation"}:
        return "critical"
    if failure_type in {"missing_required_tool", "wrong_tool", "wrong_arguments"}:
        return "high"
    return "medium"


def _observation_confidence(
    test: Mapping[str, Any],
    final: Mapping[str, Any],
) -> float:
    coherence = test.get("coherence")
    has_coherence = (
        isinstance(coherence, Mapping)
        and _finite_number(coherence.get("score"))
    )
    has_verdict = bool(final.get("verdict"))
    return 0.95 if has_coherence and has_verdict else 0.9


def _judge_version_observed(
    run: Mapping[str, Any],
    result: Mapping[str, Any],
) -> bool:
    for container in (run, result):
        for key in ("judge_version", "grader_version"):
            if isinstance(container.get(key), str) and container[key].strip():
                return True
    return False


def _tool_name(value: Any) -> str:
    if not isinstance(value, Mapping):
        return ""
    return str(value.get("tool_name") or value.get("name") or "")


def _comparison_size(value: Any) -> int:
    if isinstance(value, (Mapping, list)):
        return len(value)
    return 0


def _required_identifier(value: Any, error: str) -> str | int:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or value == "":
        raise ReleaseFoundryPreferenceEvaluationError(error)
    return value


def _non_negative_int(value: Any, error: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReleaseFoundryPreferenceEvaluationError(error)
    return value


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _unique_strings(values: Sequence[str], label: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ReleaseFoundryPreferenceEvaluationError(f"{label}_invalid")
    normalized = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise ReleaseFoundryPreferenceEvaluationError(f"{label}_invalid")
        normalized.append(value)
    if len(normalized) != len(set(normalized)):
        raise ReleaseFoundryPreferenceEvaluationError(f"{label}_duplicate")
    return normalized


def _require_hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise ReleaseFoundryPreferenceEvaluationError(f"{label}_invalid")
    return value
