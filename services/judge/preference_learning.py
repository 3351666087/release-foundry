"""Governed ReleaseFoundry-teacher preference pairs for A2 distillation."""

from __future__ import annotations

import math
import re
from typing import Any, Iterable

from .result_persistence import stable_hash
from .schemas import CANONICAL_FAILURE_CLASSES


SCHEMA_VERSION = "a2.governed_preference_pair.v1"
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PUBLIC_TEXT_PATTERNS = (
    re.compile(r"\b(?:sk|tp|releasefoundry_live)[-_][A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(
        r"[?&](?:signature|sig|token|key|credential|x-amz-signature)=",
        re.IGNORECASE,
    ),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs", re.IGNORECASE),
    re.compile(r"(?:^|[\s\"'])(?:[A-Za-z]:[\\/]|/Users/|/home/|/private/|/tmp/)"),
)
SEVERITIES = {"none", "low", "medium", "high", "critical"}
TEACHER_TYPES = {"strong_model", "local_judge"}

_CANDIDATE_FIELDS = {
    "candidate_id",
    "task_id",
    "sample_id",
    "dataset_identity_hash",
    "prompt_version",
    "prompt_hash",
    "media_evidence_hashes",
    "model_version",
    "trace_hash",
    "final_answer_hash",
}
_RELEASEFOUNDRY_EVALUATION_FIELDS = {
    "candidate_id",
    "action_scores",
    "final_answer_score",
    "overall_reward",
    "rank",
    "failure_type",
    "severity",
    "failure_action",
    "evidence_location",
    "failure_reason",
    "confidence",
    "receipt_hash",
    "receipt_verified",
}
_ACTION_SCORE_FIELDS = {
    "action_index",
    "score",
    "passed",
    "failure_type",
    "evidence_location",
    "reason",
}
_TEACHER_VOTE_FIELDS = {
    "teacher_id",
    "teacher_type",
    "chosen_candidate_id",
    "rejected_candidate_id",
    "confidence",
    "model_version",
    "evidence_hash",
    "evidence_verified",
    "reason_code",
}
_HUMAN_ADJUDICATION_FIELDS = {
    "review_status",
    "chosen_candidate_id",
    "rejected_candidate_id",
    "review_id_hash",
    "reviewer_receipt_hash",
    "reviewed_at_unix_ms",
    "review_reason_code",
}


class PreferenceLearningError(ValueError):
    """Raised when a preference sample is unsafe or not attributable."""


def build_governed_preference_pair(
    candidates: list[dict[str, Any]],
    releasefoundry_evaluations: list[dict[str, Any]],
    *,
    teacher_votes: list[dict[str, Any]] | None = None,
    human_adjudication: dict[str, Any] | None = None,
    allow_teacher_consensus: bool = False,
    known_failure_classes: Iterable[str] = (),
) -> dict[str, Any]:
    """Build one deterministic top-vs-bottom preference record.

    ReleaseFoundry alone may create only a provisional pair. Human adjudication is the
    default training authority. A deployment may explicitly allow consensus
    from at least two independent external teachers, but a local judge never
    counts as an independent teacher for that purpose.
    """
    normalized_candidates = _normalize_candidates(candidates)
    candidate_ids = {candidate["candidate_id"] for candidate in normalized_candidates}
    normalized_releasefoundry = _normalize_releasefoundry_evaluations(releasefoundry_evaluations, candidate_ids)
    normalized_votes = _normalize_teacher_votes(teacher_votes or [], candidate_ids)
    normalized_human = _normalize_human_adjudication(human_adjudication, candidate_ids)

    provisional, releasefoundry_blockers = _releasefoundry_preference(normalized_releasefoundry)
    strong_votes = [
        vote for vote in normalized_votes if vote["teacher_type"] == "strong_model"
    ]
    local_votes = [
        vote for vote in normalized_votes if vote["teacher_type"] == "local_judge"
    ]
    if len(local_votes) > 1:
        raise PreferenceLearningError("multiple_local_judge_votes")

    teacher_conflict = bool(
        provisional
        and any(not _same_pair(vote, provisional) for vote in strong_votes)
    )
    external_teacher_count = (1 if provisional else 0) + len(strong_votes)
    teacher_consensus = bool(
        provisional
        and external_teacher_count >= 2
        and not teacher_conflict
        and all(_same_pair(vote, provisional) for vote in strong_votes)
    )

    if normalized_human is not None:
        final_preference = _pair_from(normalized_human)
        authority = "human_gold"
        status = "training_eligible"
        training_eligible = True
        review_required = False
    elif provisional is None:
        final_preference = None
        authority = "none"
        status = "blocked"
        training_eligible = False
        review_required = True
    elif teacher_conflict:
        final_preference = provisional
        authority = "releasefoundry_provisional"
        status = "review_required"
        training_eligible = False
        review_required = True
    elif teacher_consensus:
        final_preference = provisional
        authority = "teacher_consensus"
        training_eligible = bool(allow_teacher_consensus)
        status = "training_eligible" if training_eligible else "review_required"
        review_required = not training_eligible
    else:
        final_preference = provisional
        authority = "releasefoundry_provisional"
        status = "provisional_preference"
        training_eligible = False
        review_required = True

    candidate_by_id = {
        candidate["candidate_id"]: candidate for candidate in normalized_candidates
    }
    chosen = (
        candidate_by_id[final_preference["chosen_candidate_id"]]
        if final_preference
        else None
    )
    rejected = (
        candidate_by_id[final_preference["rejected_candidate_id"]]
        if final_preference
        else None
    )
    active_learning = _active_learning_priority(
        provisional=provisional,
        local_vote=local_votes[0] if local_votes else None,
        teacher_conflict=teacher_conflict,
        releasefoundry_blockers=releasefoundry_blockers,
        releasefoundry_evaluations=normalized_releasefoundry,
        known_failure_classes=set(known_failure_classes),
    )
    scope = {
        key: normalized_candidates[0][key]
        for key in (
            "task_id",
            "sample_id",
            "dataset_identity_hash",
            "prompt_version",
            "prompt_hash",
            "media_evidence_hashes",
        )
    }
    core = {
        "schema_version": SCHEMA_VERSION,
        "scope": scope,
        "candidate_count": len(normalized_candidates),
        "candidates": normalized_candidates,
        "releasefoundry_evaluations": normalized_releasefoundry,
        "releasefoundry_provisional_preference": provisional,
        "teacher_votes": normalized_votes,
        "human_adjudication": normalized_human,
        "chosen": chosen,
        "rejected": rejected,
        "status": status,
        "preference_authority": authority,
        "training_eligible": training_eligible,
        "review_required": review_required,
        "teacher_conflict": teacher_conflict,
        "external_teacher_count": external_teacher_count,
        "releasefoundry_blockers": releasefoundry_blockers,
        "active_learning": active_learning,
        "metadata": {
            "public_safe": True,
            "raw_inputs_recorded": False,
            "raw_media_recorded": False,
            "raw_traces_recorded": False,
            "raw_final_answers_recorded": False,
            "releasefoundry_alone_is_human_gold": False,
            "local_judge_counts_as_external_teacher": False,
            "teacher_consensus_training_allowed": bool(allow_teacher_consensus),
        },
    }
    _validate_public_safe(core)
    return {"pair_id": stable_hash(core), **core}


def _normalize_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise PreferenceLearningError("at_least_two_candidates_required")
    normalized = []
    candidate_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        _exact_fields(candidate, _CANDIDATE_FIELDS, f"candidate[{index}]")
        value = {
            "candidate_id": _public_string(candidate["candidate_id"], "candidate_id"),
            "task_id": _public_string(candidate["task_id"], "task_id"),
            "sample_id": _public_string(candidate["sample_id"], "sample_id"),
            "dataset_identity_hash": _hash(
                candidate["dataset_identity_hash"], "dataset_identity_hash"
            ),
            "prompt_version": _public_string(
                candidate["prompt_version"], "prompt_version"
            ),
            "prompt_hash": _hash(candidate["prompt_hash"], "prompt_hash"),
            "media_evidence_hashes": _hash_list(
                candidate["media_evidence_hashes"], "media_evidence_hashes"
            ),
            "model_version": _public_string(candidate["model_version"], "model_version"),
            "trace_hash": _hash(candidate["trace_hash"], "trace_hash"),
            "final_answer_hash": _hash(
                candidate["final_answer_hash"], "final_answer_hash"
            ),
        }
        if value["candidate_id"] in candidate_ids:
            raise PreferenceLearningError("duplicate_candidate_id")
        candidate_ids.add(value["candidate_id"])
        normalized.append(value)

    scope_fields = (
        "task_id",
        "sample_id",
        "dataset_identity_hash",
        "prompt_version",
        "prompt_hash",
        "media_evidence_hashes",
    )
    expected_scope = {field: normalized[0][field] for field in scope_fields}
    for candidate in normalized[1:]:
        for field, expected in expected_scope.items():
            if candidate[field] != expected:
                raise PreferenceLearningError(f"cross_candidate_{field}_mismatch")
    return sorted(normalized, key=lambda item: item["candidate_id"])


def _normalize_releasefoundry_evaluations(
    evaluations: list[dict[str, Any]],
    candidate_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(evaluations, list):
        raise PreferenceLearningError("releasefoundry_evaluations_must_be_list")
    normalized = []
    seen: set[str] = set()
    for index, evaluation in enumerate(evaluations):
        _exact_fields(
            evaluation,
            _RELEASEFOUNDRY_EVALUATION_FIELDS,
            f"releasefoundry_evaluation[{index}]",
        )
        candidate_id = _public_string(evaluation["candidate_id"], "candidate_id")
        if candidate_id not in candidate_ids:
            raise PreferenceLearningError("releasefoundry_candidate_not_found")
        if candidate_id in seen:
            raise PreferenceLearningError("duplicate_releasefoundry_candidate_evaluation")
        seen.add(candidate_id)
        receipt_verified = evaluation["receipt_verified"]
        if receipt_verified is not True:
            raise PreferenceLearningError("releasefoundry_receipt_not_verified")
        failure_type = _failure_type(evaluation["failure_type"], "failure_type")
        severity = _severity(evaluation["severity"])
        failure_action = _public_string(
            evaluation["failure_action"],
            "failure_action",
            allow_empty=True,
        )
        failure_reason = _public_string(
            evaluation["failure_reason"],
            "failure_reason",
            allow_empty=True,
            max_length=2048,
        )
        evidence_location = _evidence_location(evaluation["evidence_location"])
        _validate_failure_details(
            failure_type=failure_type,
            severity=severity,
            failure_action=failure_action,
            failure_reason=failure_reason,
            evidence_location=evidence_location,
            prefix="releasefoundry",
        )
        rank = evaluation["rank"]
        if isinstance(rank, bool) or not isinstance(rank, int) or rank <= 0:
            raise PreferenceLearningError("releasefoundry_rank_must_be_positive_integer")
        normalized.append(
            {
                "candidate_id": candidate_id,
                "action_scores": _normalize_action_scores(
                    evaluation["action_scores"], candidate_id
                ),
                "final_answer_score": _number(
                    evaluation["final_answer_score"], "final_answer_score"
                ),
                "overall_reward": _number(
                    evaluation["overall_reward"], "overall_reward"
                ),
                "rank": rank,
                "failure_type": failure_type,
                "severity": severity,
                "failure_action": failure_action,
                "evidence_location": evidence_location,
                "failure_reason": failure_reason,
                "confidence": _probability(evaluation["confidence"], "confidence"),
                "receipt_hash": _hash(evaluation["receipt_hash"], "receipt_hash"),
                "receipt_verified": True,
            }
        )
    if seen != candidate_ids:
        raise PreferenceLearningError("releasefoundry_evaluation_candidate_coverage_mismatch")
    return sorted(normalized, key=lambda item: item["candidate_id"])


def _normalize_action_scores(
    action_scores: Any,
    candidate_id: str,
) -> list[dict[str, Any]]:
    if not isinstance(action_scores, list):
        raise PreferenceLearningError("action_scores_must_be_list")
    normalized = []
    seen_indexes: set[int] = set()
    for position, action in enumerate(action_scores):
        _exact_fields(action, _ACTION_SCORE_FIELDS, f"action_score[{position}]")
        action_index = action["action_index"]
        if (
            isinstance(action_index, bool)
            or not isinstance(action_index, int)
            or action_index < 0
        ):
            raise PreferenceLearningError("action_index_must_be_non_negative_integer")
        if action_index in seen_indexes:
            raise PreferenceLearningError("duplicate_action_index")
        seen_indexes.add(action_index)
        passed = action["passed"]
        if not isinstance(passed, bool):
            raise PreferenceLearningError("action_passed_must_be_boolean")
        failure_type = _failure_type(action["failure_type"], "action_failure_type")
        reason = _public_string(
            action["reason"],
            "action_reason",
            allow_empty=True,
            max_length=2048,
        )
        evidence_location = _evidence_location(action["evidence_location"])
        if passed and failure_type != "none":
            raise PreferenceLearningError("passed_action_has_failure_type")
        if not passed and failure_type == "none":
            raise PreferenceLearningError("failed_action_missing_failure_type")
        if not passed and (not reason or not _has_evidence(evidence_location)):
            raise PreferenceLearningError("failed_action_missing_reason_or_evidence")
        normalized.append(
            {
                "candidate_id": candidate_id,
                "action_index": action_index,
                "score": _number(action["score"], "action_score"),
                "passed": passed,
                "failure_type": failure_type,
                "evidence_location": evidence_location,
                "reason": reason,
            }
        )
    return sorted(normalized, key=lambda item: item["action_index"])


def _normalize_teacher_votes(
    teacher_votes: list[dict[str, Any]],
    candidate_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(teacher_votes, list):
        raise PreferenceLearningError("teacher_votes_must_be_list")
    normalized = []
    seen: set[str] = set()
    for index, vote in enumerate(teacher_votes):
        _exact_fields(vote, _TEACHER_VOTE_FIELDS, f"teacher_vote[{index}]")
        teacher_id = _public_string(vote["teacher_id"], "teacher_id")
        if teacher_id in seen:
            raise PreferenceLearningError("duplicate_teacher_id")
        seen.add(teacher_id)
        teacher_type = vote["teacher_type"]
        if teacher_type not in TEACHER_TYPES:
            raise PreferenceLearningError("unsupported_teacher_type")
        if vote["evidence_verified"] is not True:
            raise PreferenceLearningError("teacher_evidence_not_verified")
        chosen_candidate_id, rejected_candidate_id = _candidate_pair(
            vote["chosen_candidate_id"],
            vote["rejected_candidate_id"],
            candidate_ids,
        )
        normalized.append(
            {
                "teacher_id": teacher_id,
                "teacher_type": teacher_type,
                "chosen_candidate_id": chosen_candidate_id,
                "rejected_candidate_id": rejected_candidate_id,
                "confidence": _probability(vote["confidence"], "teacher_confidence"),
                "model_version": _public_string(
                    vote["model_version"], "teacher_model_version"
                ),
                "evidence_hash": _hash(vote["evidence_hash"], "teacher_evidence_hash"),
                "evidence_verified": True,
                "reason_code": _public_string(vote["reason_code"], "reason_code"),
            }
        )
    return sorted(normalized, key=lambda item: item["teacher_id"])


def _normalize_human_adjudication(
    adjudication: dict[str, Any] | None,
    candidate_ids: set[str],
) -> dict[str, Any] | None:
    if adjudication is None:
        return None
    _exact_fields(adjudication, _HUMAN_ADJUDICATION_FIELDS, "human_adjudication")
    if adjudication["review_status"] != "reviewed":
        raise PreferenceLearningError("human_adjudication_not_reviewed")
    chosen_candidate_id, rejected_candidate_id = _candidate_pair(
        adjudication["chosen_candidate_id"],
        adjudication["rejected_candidate_id"],
        candidate_ids,
    )
    reviewed_at = adjudication["reviewed_at_unix_ms"]
    if (
        isinstance(reviewed_at, bool)
        or not isinstance(reviewed_at, int)
        or reviewed_at <= 0
    ):
        raise PreferenceLearningError("reviewed_at_unix_ms_must_be_positive_integer")
    return {
        "review_status": "reviewed",
        "chosen_candidate_id": chosen_candidate_id,
        "rejected_candidate_id": rejected_candidate_id,
        "review_id_hash": _hash(adjudication["review_id_hash"], "review_id_hash"),
        "reviewer_receipt_hash": _hash(
            adjudication["reviewer_receipt_hash"], "reviewer_receipt_hash"
        ),
        "reviewed_at_unix_ms": reviewed_at,
        "review_reason_code": _public_string(
            adjudication["review_reason_code"], "review_reason_code"
        ),
        "authority": "human_gold",
    }


def _releasefoundry_preference(
    evaluations: list[dict[str, Any]],
) -> tuple[dict[str, str] | None, list[str]]:
    ranked = sorted(evaluations, key=lambda item: item["rank"])
    expected_ranks = list(range(1, len(ranked) + 1))
    observed_ranks = [item["rank"] for item in ranked]
    if observed_ranks != expected_ranks:
        return None, ["releasefoundry_rank_tie_or_gap"]
    for better, worse in zip(ranked, ranked[1:]):
        if better["overall_reward"] == worse["overall_reward"]:
            return None, ["releasefoundry_reward_tie"]
        if better["overall_reward"] < worse["overall_reward"]:
            return None, ["releasefoundry_rank_reward_conflict"]
    return (
        {
            "chosen_candidate_id": ranked[0]["candidate_id"],
            "rejected_candidate_id": ranked[-1]["candidate_id"],
        },
        [],
    )


def _active_learning_priority(
    *,
    provisional: dict[str, str] | None,
    local_vote: dict[str, Any] | None,
    teacher_conflict: bool,
    releasefoundry_blockers: list[str],
    releasefoundry_evaluations: list[dict[str, Any]],
    known_failure_classes: set[str],
) -> dict[str, Any]:
    components: dict[str, float] = {}
    reasons: list[str] = []
    if local_vote is None:
        components["local_uncertainty"] = 35.0
        reasons.append("local_judge_missing")
    else:
        uncertainty = round((1.0 - local_vote["confidence"]) * 35.0, 6)
        components["local_uncertainty"] = uncertainty
        if uncertainty > 10:
            reasons.append("local_judge_uncertain")
        if provisional and not _same_pair(local_vote, provisional):
            components["local_releasefoundry_disagreement"] = 25.0
            reasons.append("local_releasefoundry_disagreement")
    if teacher_conflict:
        components["external_teacher_conflict"] = 25.0
        reasons.append("external_teacher_conflict")
    if releasefoundry_blockers:
        components["releasefoundry_preference_blocked"] = 20.0
        reasons.extend(releasefoundry_blockers)
    if any(item["severity"] == "critical" for item in releasefoundry_evaluations):
        components["critical_severity"] = 15.0
        reasons.append("critical_severity")
    observed_failures = {
        item["failure_type"]
        for item in releasefoundry_evaluations
        if item["failure_type"] != "none"
    }
    novel_failures = sorted(observed_failures - known_failure_classes)
    if novel_failures:
        components["novel_failure_class"] = 10.0
        reasons.append("novel_failure_class")
    score = min(100.0, round(sum(components.values()), 6))
    if score >= 70:
        band = "critical"
    elif score >= 40:
        band = "high"
    elif score >= 20:
        band = "medium"
    else:
        band = "low"
    return {
        "score": score,
        "band": band,
        "components": dict(sorted(components.items())),
        "reasons": sorted(set(reasons)),
        "novel_failure_classes": novel_failures,
    }


def _candidate_pair(
    chosen_candidate_id: Any,
    rejected_candidate_id: Any,
    candidate_ids: set[str],
) -> tuple[str, str]:
    chosen = _public_string(chosen_candidate_id, "chosen_candidate_id")
    rejected = _public_string(rejected_candidate_id, "rejected_candidate_id")
    if chosen == rejected:
        raise PreferenceLearningError("chosen_and_rejected_must_be_distinct")
    if chosen not in candidate_ids or rejected not in candidate_ids:
        raise PreferenceLearningError("preference_candidate_not_found")
    return chosen, rejected


def _pair_from(value: dict[str, Any]) -> dict[str, str]:
    return {
        "chosen_candidate_id": value["chosen_candidate_id"],
        "rejected_candidate_id": value["rejected_candidate_id"],
    }


def _same_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["chosen_candidate_id"] == right["chosen_candidate_id"]
        and left["rejected_candidate_id"] == right["rejected_candidate_id"]
    )


def _exact_fields(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, dict):
        raise PreferenceLearningError(f"{label}_must_be_object")
    observed = set(value)
    missing = sorted(fields - observed)
    extra = sorted(observed - fields)
    if missing:
        raise PreferenceLearningError(f"{label}_missing_fields:{','.join(missing)}")
    if extra:
        raise PreferenceLearningError(f"{label}_unknown_fields:{','.join(extra)}")


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise PreferenceLearningError(f"{label}_must_be_sha256")
    return value


def _hash_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise PreferenceLearningError(f"{label}_must_be_list")
    hashes = [_hash(item, label) for item in value]
    if len(hashes) != len(set(hashes)):
        raise PreferenceLearningError(f"{label}_contains_duplicates")
    return hashes


def _public_string(
    value: Any,
    label: str,
    *,
    allow_empty: bool = False,
    max_length: int = 256,
) -> str:
    if not isinstance(value, str):
        raise PreferenceLearningError(f"{label}_must_be_string")
    if not allow_empty and not value:
        raise PreferenceLearningError(f"{label}_must_not_be_empty")
    if len(value) > max_length:
        raise PreferenceLearningError(f"{label}_too_long")
    _validate_public_safe(value)
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreferenceLearningError(f"{label}_must_be_number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise PreferenceLearningError(f"{label}_must_be_finite")
    return normalized


def _probability(value: Any, label: str) -> float:
    normalized = _number(value, label)
    if normalized < 0 or normalized > 1:
        raise PreferenceLearningError(f"{label}_must_be_probability")
    return normalized


def _failure_type(value: Any, label: str) -> str:
    normalized = _public_string(value, label)
    if normalized not in CANONICAL_FAILURE_CLASSES | {"none"}:
        raise PreferenceLearningError(f"{label}_not_canonical")
    return normalized


def _severity(value: Any) -> str:
    if value not in SEVERITIES:
        raise PreferenceLearningError("severity_not_supported")
    return str(value)


def _evidence_location(value: Any) -> Any:
    if not isinstance(value, (dict, list, str)):
        raise PreferenceLearningError("evidence_location_must_be_structured")
    _validate_public_safe(value)
    return value


def _validate_failure_details(
    *,
    failure_type: str,
    severity: str,
    failure_action: str,
    failure_reason: str,
    evidence_location: Any,
    prefix: str,
) -> None:
    if failure_type == "none":
        if severity != "none":
            raise PreferenceLearningError(f"{prefix}_pass_has_failure_severity")
        return
    if severity == "none":
        raise PreferenceLearningError(f"{prefix}_failure_missing_severity")
    if not failure_action or not failure_reason or not _has_evidence(evidence_location):
        raise PreferenceLearningError(f"{prefix}_failure_details_incomplete")


def _has_evidence(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value)
    return bool(value)


def _validate_public_safe(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_public_safe(str(key))
            _validate_public_safe(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_public_safe(item)
        return
    if not isinstance(value, str):
        return
    for pattern in PUBLIC_TEXT_PATTERNS:
        if pattern.search(value):
            raise PreferenceLearningError("private_or_secret_material_rejected")
