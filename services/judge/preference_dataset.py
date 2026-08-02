"""Private, governed training exports for A2 preference learning.

The public preference-pair record deliberately contains only hashes and
teacher labels.  This module joins that record to a separately governed
private source bundle and emits records suitable for reward-model, preference,
and action-value training.  Raw prompts, media locators, traces, and answers
never appear in the returned public manifest.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping

from .preference_learning import SCHEMA_VERSION as PREFERENCE_PAIR_SCHEMA_VERSION
from .result_persistence import canonical_json, stable_hash


TRAINING_RECORD_SCHEMA_VERSION = "a2.private_preference_training_record.v1"
TRAINING_MANIFEST_SCHEMA_VERSION = "a2.private_preference_training_manifest.v1"
WRITER_VERSION = "a2.private_preference_dataset.v1"
TRAINING_AUTHORITIES = {"human_gold", "teacher_consensus"}
TRAINING_PURPOSES = {
    "reward_model_training",
    "preference_optimization",
    "action_value_training",
}
DATASET_SPLITS = {"train", "validation", "test"}
DATA_CLASSIFICATIONS = {"internal_training", "restricted_training"}
MEDIA_MODALITIES = {"image", "audio", "video", "file"}
HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
CAS_PATTERN = re.compile(r"^cas://sha256:[0-9a-f]{64}$")
ISO_UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"\b(?:sk|tp|releasefoundry_live)[-_][A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(
        r"[?&](?:signature|sig|token|key|credential|x-amz-signature)=",
        re.IGNORECASE,
    ),
    re.compile(r"docs[\\/]+evidence[\\/]+private_refs", re.IGNORECASE),
    re.compile(r"(?:^|[\s\"'])(?:[A-Za-z]:[\\/]|/Users/|/home/|/private/|/tmp/)"),
)
SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "releasefoundry_api_key",
    "authorization",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "client_secret",
    "credential",
    "credentials",
}

_PAIR_FIELDS = {
    "pair_id",
    "schema_version",
    "scope",
    "candidate_count",
    "candidates",
    "releasefoundry_evaluations",
    "releasefoundry_provisional_preference",
    "teacher_votes",
    "human_adjudication",
    "chosen",
    "rejected",
    "status",
    "preference_authority",
    "training_eligible",
    "review_required",
    "teacher_conflict",
    "external_teacher_count",
    "releasefoundry_blockers",
    "active_learning",
    "metadata",
}
_SOURCE_FIELDS = {
    "pair_id",
    "prompt",
    "media_artifacts",
    "candidates",
    "governance",
}
_SOURCE_CANDIDATE_FIELDS = {
    "candidate_id",
    "model_version",
    "execution_trace",
    "final_answer",
}
_MEDIA_FIELDS = {
    "content_hash",
    "modality",
    "mime_type",
    "storage_ref",
    "source_group_hash",
}
_GOVERNANCE_FIELDS = {
    "consent_id_hash",
    "lineage_hash",
    "residency",
    "retention_until",
    "deletion_key_hash",
    "authorization_hash",
    "dataset_split",
    "data_classification",
}
_RECORD_FIELDS = {
    "record_id",
    "schema_version",
    "purpose",
    "pair_id",
    "preference_authority",
    "dataset_split",
    "scope",
    "governance",
    "source_bundle_hash",
    "media_artifacts",
    "payload",
}
_MANIFEST_FIELDS = {
    "schema_version",
    "writer_version",
    "created_at",
    "record_count",
    "file_sha256",
    "record_hashes",
    "dataset_hash",
    "purpose_counts",
    "pair_ids",
    "authority_counts",
    "dataset_split_counts",
    "file_write_state",
    "file_fsync_state",
    "atomic_replace_state",
    "post_replace_reopen_state",
    "public_safe",
    "private_artifact_required",
    "raw_training_content_in_manifest",
    "path_in_manifest",
}


class PreferenceDatasetError(ValueError):
    """Raised when a private training export is unsafe or unverifiable."""


def build_private_training_records(
    pair: Mapping[str, Any],
    source_bundle: Mapping[str, Any],
    *,
    purposes: Iterable[str] = (
        "reward_model_training",
        "preference_optimization",
        "action_value_training",
    ),
) -> list[dict[str, Any]]:
    """Join one governed preference pair to its private source material."""
    normalized_pair = _validate_pair(pair)
    normalized_source = _validate_source_bundle(source_bundle, normalized_pair)
    normalized_purposes = _normalize_purposes(purposes)

    pair_id = normalized_pair["pair_id"]
    authority = normalized_pair["preference_authority"]
    scope = normalized_pair["scope"]
    governance = normalized_source["governance"]
    media_artifacts = normalized_source["media_artifacts"]
    source_bundle_hash = stable_hash(normalized_source)
    source_candidates = {
        item["candidate_id"]: item for item in normalized_source["candidates"]
    }
    evaluations = {
        item["candidate_id"]: item for item in normalized_pair["releasefoundry_evaluations"]
    }
    chosen_id = normalized_pair["chosen"]["candidate_id"]
    rejected_id = normalized_pair["rejected"]["candidate_id"]

    common = {
        "schema_version": TRAINING_RECORD_SCHEMA_VERSION,
        "pair_id": pair_id,
        "preference_authority": authority,
        "dataset_split": governance["dataset_split"],
        "scope": scope,
        "governance": governance,
        "source_bundle_hash": source_bundle_hash,
        "media_artifacts": media_artifacts,
    }
    preference_label = {
        "chosen_candidate_id": chosen_id,
        "rejected_candidate_id": rejected_id,
        "authority": authority,
        "releasefoundry_provisional_preference": normalized_pair[
            "releasefoundry_provisional_preference"
        ],
        "human_override_of_releasefoundry": bool(
            authority == "human_gold"
            and normalized_pair["releasefoundry_provisional_preference"] is not None
            and normalized_pair["releasefoundry_provisional_preference"]
            != {
                "chosen_candidate_id": chosen_id,
                "rejected_candidate_id": rejected_id,
            }
        ),
    }
    records: list[dict[str, Any]] = []

    if "reward_model_training" in normalized_purposes:
        records.append(
            _record(
                common,
                "reward_model_training",
                {
                    "prompt": normalized_source["prompt"],
                    "chosen": _candidate_payload(
                        source_candidates[chosen_id],
                        evaluations[chosen_id],
                    ),
                    "rejected": _candidate_payload(
                        source_candidates[rejected_id],
                        evaluations[rejected_id],
                    ),
                    "preference_label": preference_label,
                },
            )
        )

    if "preference_optimization" in normalized_purposes:
        records.append(
            _record(
                common,
                "preference_optimization",
                {
                    "prompt": normalized_source["prompt"],
                    "chosen": _candidate_training_payload(
                        source_candidates[chosen_id]
                    ),
                    "rejected": _candidate_training_payload(
                        source_candidates[rejected_id]
                    ),
                    "teacher_labels": {
                        "preference": preference_label,
                        "chosen_releasefoundry": evaluations[chosen_id],
                        "rejected_releasefoundry": evaluations[rejected_id],
                    },
                },
            )
        )

    if "action_value_training" in normalized_purposes:
        for candidate_id in sorted(source_candidates):
            source_candidate = source_candidates[candidate_id]
            evaluation = evaluations[candidate_id]
            trace = source_candidate["execution_trace"]
            preference_role = (
                "chosen"
                if candidate_id == chosen_id
                else "rejected"
                if candidate_id == rejected_id
                else "other"
            )
            for action_score in evaluation["action_scores"]:
                action_index = action_score["action_index"]
                if action_index >= len(trace):
                    raise PreferenceDatasetError("releasefoundry_action_index_out_of_range")
                records.append(
                    _record(
                        common,
                        "action_value_training",
                        {
                            "prompt": normalized_source["prompt"],
                            "candidate_id": candidate_id,
                            "model_version": source_candidate["model_version"],
                            "execution_prefix": trace[:action_index],
                            "action": trace[action_index],
                            "action_index": action_index,
                            "releasefoundry_action_label": action_score,
                            "candidate_outcome_label": {
                                "preference_role": preference_role,
                                "authoritative_preference": preference_label,
                                "releasefoundry_final_answer_score": evaluation[
                                    "final_answer_score"
                                ],
                                "releasefoundry_overall_reward": evaluation["overall_reward"],
                                "releasefoundry_rank": evaluation["rank"],
                                "failure_type": evaluation["failure_type"],
                                "severity": evaluation["severity"],
                                "confidence": evaluation["confidence"],
                            },
                        },
                    )
                )

    _validate_records(records)
    verify_source_split_isolation(records)
    return records


def write_private_training_jsonl(
    path: str | Path,
    records: list[dict[str, Any]],
    *,
    private_root: str | Path,
    allow_private_write: bool = False,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Atomically write private JSONL and return a path-free public manifest."""
    if allow_private_write is not True:
        raise PreferenceDatasetError("private_write_requires_explicit_authorization")
    destination = _validated_private_path(path, private_root=private_root)
    _validate_records(records)
    verify_source_split_isolation(records)
    destination.parent.mkdir(parents=True, exist_ok=True)

    text = "".join(canonical_json(record) + "\n" for record in records)
    expected_bytes = text.encode("utf-8")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(expected_bytes)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    observed_bytes = destination.read_bytes()
    if observed_bytes != expected_bytes:
        raise PreferenceDatasetError("private_jsonl_post_replace_mismatch")
    observed_records = _decode_jsonl(observed_bytes)
    if observed_records != records:
        raise PreferenceDatasetError("private_jsonl_round_trip_mismatch")

    manifest = _build_manifest(records, expected_bytes, created_at=created_at)
    _validate_manifest_public_safe(manifest)
    return manifest


def load_private_training_jsonl(
    path: str | Path,
    manifest: Mapping[str, Any],
    *,
    private_root: str | Path,
) -> list[dict[str, Any]]:
    """Load private training records only when the path-free manifest verifies."""
    destination = _validated_private_path(path, private_root=private_root)
    normalized_manifest = _validate_manifest(manifest)
    if not destination.is_file():
        raise PreferenceDatasetError("private_jsonl_missing")
    payload = destination.read_bytes()
    records = _decode_jsonl(payload)
    _validate_records(records)
    verify_source_split_isolation(records)

    expected = _build_manifest(
        records,
        payload,
        created_at=normalized_manifest["created_at"],
    )
    for field in (
        "record_count",
        "file_sha256",
        "record_hashes",
        "dataset_hash",
        "purpose_counts",
        "pair_ids",
        "authority_counts",
        "dataset_split_counts",
    ):
        if normalized_manifest[field] != expected[field]:
            raise PreferenceDatasetError(f"private_jsonl_{field}_mismatch")
    return records


def load_private_training_corpus(
    datasets: Iterable[tuple[str | Path, Mapping[str, Any]]],
    *,
    private_root: str | Path,
) -> list[dict[str, Any]]:
    """Load multiple verified JSONL files and enforce corpus-wide isolation."""
    entries = list(datasets)
    if not entries:
        raise PreferenceDatasetError("private_training_corpus_must_be_non_empty")

    records: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    seen_record_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise PreferenceDatasetError("private_training_corpus_entry_invalid")
        path, manifest = entry
        destination = _validated_private_path(path, private_root=private_root)
        if destination in seen_paths:
            raise PreferenceDatasetError("private_training_corpus_path_duplicate")
        seen_paths.add(destination)

        dataset_records = load_private_training_jsonl(
            destination,
            manifest,
            private_root=private_root,
        )
        for record in dataset_records:
            record_id = record["record_id"]
            if record_id in seen_record_ids:
                raise PreferenceDatasetError(
                    "private_training_corpus_record_duplicate"
                )
            seen_record_ids.add(record_id)
        records.extend(dataset_records)

    _validate_records(records)
    verify_source_split_isolation(records)
    return records


def verify_source_split_isolation(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Reject source media or source groups reused across dataset splits."""
    content_splits: dict[str, set[str]] = {}
    group_splits: dict[str, set[str]] = {}
    record_count = 0
    for record in records:
        record_count += 1
        if not isinstance(record, Mapping):
            raise PreferenceDatasetError("training_record_must_be_object")
        split = record.get("dataset_split")
        if split not in DATASET_SPLITS:
            raise PreferenceDatasetError("dataset_split_not_supported")
        media = record.get("media_artifacts")
        if not isinstance(media, list):
            raise PreferenceDatasetError("media_artifacts_must_be_list")
        for artifact in media:
            if not isinstance(artifact, Mapping):
                raise PreferenceDatasetError("media_artifact_must_be_object")
            content_splits.setdefault(str(artifact.get("content_hash")), set()).add(
                str(split)
            )
            group_splits.setdefault(
                str(artifact.get("source_group_hash")), set()
            ).add(str(split))
    if any(len(splits) > 1 for splits in content_splits.values()):
        raise PreferenceDatasetError("media_content_hash_split_leakage")
    if any(len(splits) > 1 for splits in group_splits.values()):
        raise PreferenceDatasetError("media_source_group_split_leakage")
    return {
        "state": "verified",
        "record_count": record_count,
        "media_content_hash_count": len(content_splits),
        "source_group_hash_count": len(group_splits),
        "public_safe": True,
    }


def _validate_pair(pair: Mapping[str, Any]) -> dict[str, Any]:
    _exact_fields(pair, _PAIR_FIELDS, "pair")
    normalized = dict(pair)
    if normalized["schema_version"] != PREFERENCE_PAIR_SCHEMA_VERSION:
        raise PreferenceDatasetError("preference_pair_schema_unsupported")
    pair_id = _hash(normalized["pair_id"], "pair_id")
    core = {key: value for key, value in normalized.items() if key != "pair_id"}
    if pair_id != stable_hash(core):
        raise PreferenceDatasetError("preference_pair_id_mismatch")
    if normalized["status"] != "training_eligible":
        raise PreferenceDatasetError("preference_pair_not_training_eligible")
    if normalized["training_eligible"] is not True:
        raise PreferenceDatasetError("preference_pair_not_training_eligible")
    if normalized["preference_authority"] not in TRAINING_AUTHORITIES:
        raise PreferenceDatasetError("preference_authority_not_training_eligible")
    if not isinstance(normalized["chosen"], Mapping) or not isinstance(
        normalized["rejected"], Mapping
    ):
        raise PreferenceDatasetError("authoritative_preference_missing")
    if normalized["chosen"].get("candidate_id") == normalized["rejected"].get(
        "candidate_id"
    ):
        raise PreferenceDatasetError("authoritative_preference_invalid")
    candidates = normalized["candidates"]
    evaluations = normalized["releasefoundry_evaluations"]
    if not isinstance(candidates, list) or len(candidates) < 2:
        raise PreferenceDatasetError("preference_candidates_invalid")
    if normalized["candidate_count"] != len(candidates):
        raise PreferenceDatasetError("preference_candidate_count_mismatch")
    candidate_ids = [item.get("candidate_id") for item in candidates]
    if any(not isinstance(value, str) or not value for value in candidate_ids):
        raise PreferenceDatasetError("preference_candidate_id_invalid")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise PreferenceDatasetError("preference_candidate_id_duplicate")
    if not isinstance(evaluations, list):
        raise PreferenceDatasetError("releasefoundry_evaluations_invalid")
    evaluation_ids = [item.get("candidate_id") for item in evaluations]
    if sorted(evaluation_ids) != sorted(candidate_ids):
        raise PreferenceDatasetError("releasefoundry_evaluation_candidate_coverage_mismatch")
    for evaluation in evaluations:
        if evaluation.get("receipt_verified") is not True:
            raise PreferenceDatasetError("releasefoundry_receipt_not_verified")
        _hash(evaluation.get("receipt_hash"), "releasefoundry_receipt_hash")
        if not isinstance(evaluation.get("action_scores"), list):
            raise PreferenceDatasetError("releasefoundry_action_scores_invalid")
    _ensure_json_safe(normalized)
    return normalized


def _validate_source_bundle(
    source_bundle: Mapping[str, Any],
    pair: Mapping[str, Any],
) -> dict[str, Any]:
    _exact_fields(source_bundle, _SOURCE_FIELDS, "source_bundle")
    normalized = dict(source_bundle)
    if normalized["pair_id"] != pair["pair_id"]:
        raise PreferenceDatasetError("source_pair_id_mismatch")
    _ensure_json_safe(normalized)
    _reject_sensitive_material(normalized)
    if stable_hash(normalized["prompt"]) != pair["scope"]["prompt_hash"]:
        raise PreferenceDatasetError("source_prompt_hash_mismatch")

    media_artifacts = _normalize_media_artifacts(normalized["media_artifacts"])
    observed_media_hashes = [item["content_hash"] for item in media_artifacts]
    if observed_media_hashes != pair["scope"]["media_evidence_hashes"]:
        raise PreferenceDatasetError("source_media_hash_mismatch")
    normalized["media_artifacts"] = media_artifacts

    source_candidates = normalized["candidates"]
    if not isinstance(source_candidates, list):
        raise PreferenceDatasetError("source_candidates_must_be_list")
    candidate_by_id = {item["candidate_id"]: item for item in pair["candidates"]}
    observed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, candidate in enumerate(source_candidates):
        _exact_fields(
            candidate,
            _SOURCE_CANDIDATE_FIELDS,
            f"source_candidate[{index}]",
        )
        candidate_id = _string(candidate["candidate_id"], "source_candidate_id")
        if candidate_id in seen:
            raise PreferenceDatasetError("source_candidate_duplicate")
        seen.add(candidate_id)
        expected = candidate_by_id.get(candidate_id)
        if expected is None:
            raise PreferenceDatasetError("source_candidate_not_in_pair")
        model_version = _string(
            candidate["model_version"], "source_candidate_model_version"
        )
        if model_version != expected["model_version"]:
            raise PreferenceDatasetError("source_candidate_model_version_mismatch")
        trace = candidate["execution_trace"]
        answer = candidate["final_answer"]
        _ensure_json_safe(trace)
        _ensure_json_safe(answer)
        if not isinstance(trace, list):
            raise PreferenceDatasetError("execution_trace_must_be_list")
        if stable_hash(trace) != expected["trace_hash"]:
            raise PreferenceDatasetError("source_trace_hash_mismatch")
        if stable_hash(answer) != expected["final_answer_hash"]:
            raise PreferenceDatasetError("source_final_answer_hash_mismatch")
        observed.append(
            {
                "candidate_id": candidate_id,
                "model_version": model_version,
                "execution_trace": trace,
                "final_answer": answer,
            }
        )
    if seen != set(candidate_by_id):
        raise PreferenceDatasetError("source_candidate_coverage_mismatch")
    normalized["candidates"] = sorted(
        observed,
        key=lambda item: item["candidate_id"],
    )
    normalized["governance"] = _normalize_governance(normalized["governance"])
    return normalized


def _normalize_media_artifacts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise PreferenceDatasetError("media_artifacts_must_be_list")
    normalized: list[dict[str, str]] = []
    content_hashes: set[str] = set()
    for index, artifact in enumerate(value):
        _exact_fields(artifact, _MEDIA_FIELDS, f"media_artifact[{index}]")
        content_hash = _hash(artifact["content_hash"], "media_content_hash")
        if content_hash in content_hashes:
            raise PreferenceDatasetError("media_content_hash_duplicate")
        content_hashes.add(content_hash)
        modality = _string(artifact["modality"], "media_modality")
        if modality not in MEDIA_MODALITIES:
            raise PreferenceDatasetError("media_modality_not_supported")
        mime_type = _string(artifact["mime_type"], "media_mime_type")
        storage_ref = _string(artifact["storage_ref"], "media_storage_ref")
        if not CAS_PATTERN.fullmatch(storage_ref):
            raise PreferenceDatasetError("media_storage_ref_not_content_addressed")
        if storage_ref.removeprefix("cas://") != content_hash:
            raise PreferenceDatasetError("media_storage_ref_hash_mismatch")
        normalized.append(
            {
                "content_hash": content_hash,
                "modality": modality,
                "mime_type": mime_type,
                "storage_ref": storage_ref,
                "source_group_hash": _hash(
                    artifact["source_group_hash"],
                    "media_source_group_hash",
                ),
            }
        )
    return normalized


def _normalize_governance(value: Any) -> dict[str, str]:
    _exact_fields(value, _GOVERNANCE_FIELDS, "governance")
    normalized = {
        "consent_id_hash": _hash(value["consent_id_hash"], "consent_id_hash"),
        "lineage_hash": _hash(value["lineage_hash"], "lineage_hash"),
        "residency": _string(value["residency"], "residency"),
        "retention_until": _string(value["retention_until"], "retention_until"),
        "deletion_key_hash": _hash(
            value["deletion_key_hash"], "deletion_key_hash"
        ),
        "authorization_hash": _hash(
            value["authorization_hash"], "authorization_hash"
        ),
        "dataset_split": _string(value["dataset_split"], "dataset_split"),
        "data_classification": _string(
            value["data_classification"], "data_classification"
        ),
    }
    if not ISO_UTC_PATTERN.fullmatch(normalized["retention_until"]):
        raise PreferenceDatasetError("retention_until_must_be_utc_timestamp")
    if normalized["dataset_split"] not in DATASET_SPLITS:
        raise PreferenceDatasetError("dataset_split_not_supported")
    if normalized["data_classification"] not in DATA_CLASSIFICATIONS:
        raise PreferenceDatasetError("data_classification_not_supported")
    return normalized


def _normalize_purposes(purposes: Iterable[str]) -> list[str]:
    if isinstance(purposes, (str, bytes)):
        raise PreferenceDatasetError("training_purposes_must_be_iterable")
    try:
        normalized = list(purposes)
    except TypeError as exc:
        raise PreferenceDatasetError("training_purposes_must_be_iterable") from exc
    if not normalized:
        raise PreferenceDatasetError("training_purposes_must_not_be_empty")
    if any(purpose not in TRAINING_PURPOSES for purpose in normalized):
        raise PreferenceDatasetError("training_purpose_not_supported")
    if len(normalized) != len(set(normalized)):
        raise PreferenceDatasetError("training_purpose_duplicate")
    return sorted(normalized)


def _candidate_payload(
    source_candidate: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **_candidate_training_payload(source_candidate),
        "releasefoundry_evaluation": dict(evaluation),
    }


def _candidate_training_payload(
    source_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "candidate_id": source_candidate["candidate_id"],
        "model_version": source_candidate["model_version"],
        "execution_trace": source_candidate["execution_trace"],
        "final_answer": source_candidate["final_answer"],
    }


def _record(
    common: Mapping[str, Any],
    purpose: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    core = {**dict(common), "purpose": purpose, "payload": dict(payload)}
    _ensure_json_safe(core)
    return {"record_id": stable_hash(core), **core}


def _validate_records(records: Any) -> None:
    if not isinstance(records, list) or not records:
        raise PreferenceDatasetError("training_records_must_be_non_empty_list")
    for index, record in enumerate(records):
        _exact_fields(record, _RECORD_FIELDS, f"record[{index}]")
        if record["schema_version"] != TRAINING_RECORD_SCHEMA_VERSION:
            raise PreferenceDatasetError("training_record_schema_unsupported")
        if record["purpose"] not in TRAINING_PURPOSES:
            raise PreferenceDatasetError("training_purpose_not_supported")
        if record["preference_authority"] not in TRAINING_AUTHORITIES:
            raise PreferenceDatasetError("training_record_authority_invalid")
        if record["dataset_split"] not in DATASET_SPLITS:
            raise PreferenceDatasetError("dataset_split_not_supported")
        _hash(record["pair_id"], "pair_id")
        _hash(record["source_bundle_hash"], "source_bundle_hash")
        _normalize_governance(record["governance"])
        _normalize_media_artifacts(record["media_artifacts"])
        _ensure_json_safe(record)
        _reject_sensitive_material(record)
        core = {key: value for key, value in record.items() if key != "record_id"}
        if _hash(record["record_id"], "record_id") != stable_hash(core):
            raise PreferenceDatasetError("training_record_id_mismatch")


def _build_manifest(
    records: list[dict[str, Any]],
    payload: bytes,
    *,
    created_at: str | None,
) -> dict[str, Any]:
    timestamp = created_at or datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    if not isinstance(timestamp, str) or not ISO_UTC_PATTERN.fullmatch(timestamp):
        raise PreferenceDatasetError("manifest_created_at_must_be_utc_timestamp")
    record_hashes = [stable_hash(record) for record in records]
    manifest = {
        "schema_version": TRAINING_MANIFEST_SCHEMA_VERSION,
        "writer_version": WRITER_VERSION,
        "created_at": timestamp,
        "record_count": len(records),
        "file_sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "record_hashes": record_hashes,
        "dataset_hash": stable_hash(records),
        "purpose_counts": dict(
            sorted(Counter(record["purpose"] for record in records).items())
        ),
        "pair_ids": sorted({record["pair_id"] for record in records}),
        "authority_counts": dict(
            sorted(
                Counter(
                    record["preference_authority"] for record in records
                ).items()
            )
        ),
        "dataset_split_counts": dict(
            sorted(Counter(record["dataset_split"] for record in records).items())
        ),
        "file_write_state": "completed",
        "file_fsync_state": "verified",
        "atomic_replace_state": "verified",
        "post_replace_reopen_state": "verified",
        "public_safe": True,
        "private_artifact_required": True,
        "raw_training_content_in_manifest": False,
        "path_in_manifest": False,
    }
    return manifest


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    _exact_fields(manifest, _MANIFEST_FIELDS, "manifest")
    normalized = dict(manifest)
    if normalized["schema_version"] != TRAINING_MANIFEST_SCHEMA_VERSION:
        raise PreferenceDatasetError("training_manifest_schema_unsupported")
    if normalized["writer_version"] != WRITER_VERSION:
        raise PreferenceDatasetError("training_manifest_writer_unsupported")
    for field in (
        "file_write_state",
        "file_fsync_state",
        "atomic_replace_state",
        "post_replace_reopen_state",
    ):
        if normalized[field] != "verified" and not (
            field == "file_write_state" and normalized[field] == "completed"
        ):
            raise PreferenceDatasetError("training_manifest_durability_unverified")
    if (
        normalized["public_safe"] is not True
        or normalized["private_artifact_required"] is not True
        or normalized["raw_training_content_in_manifest"] is not False
        or normalized["path_in_manifest"] is not False
    ):
        raise PreferenceDatasetError("training_manifest_safety_flags_invalid")
    _hash(normalized["file_sha256"], "manifest_file_sha256")
    _hash(normalized["dataset_hash"], "manifest_dataset_hash")
    if not isinstance(normalized["record_hashes"], list):
        raise PreferenceDatasetError("manifest_record_hashes_invalid")
    for record_hash in normalized["record_hashes"]:
        _hash(record_hash, "manifest_record_hash")
    _validate_manifest_public_safe(normalized)
    return normalized


def _validate_manifest_public_safe(manifest: Mapping[str, Any]) -> None:
    _ensure_json_safe(manifest)
    _reject_sensitive_material(manifest)
    forbidden_keys = {
        "path",
        "prompt",
        "storage_ref",
        "execution_trace",
        "final_answer",
        "payload",
        "media_artifacts",
    }
    if any(str(key).lower() in forbidden_keys for key in _all_keys(manifest)):
        raise PreferenceDatasetError("private_training_content_in_manifest")


def _decode_jsonl(payload: bytes) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreferenceDatasetError("private_jsonl_not_utf8") from exc
    records: list[dict[str, Any]] = []
    try:
        for line in text.splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise PreferenceDatasetError("training_record_must_be_object")
                records.append(value)
    except json.JSONDecodeError as exc:
        raise PreferenceDatasetError("private_jsonl_parse_failure") from exc
    return records


def _validated_private_path(
    path: str | Path,
    *,
    private_root: str | Path,
) -> Path:
    root = Path(private_root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PreferenceDatasetError("private_path_outside_private_root") from exc
    if candidate == root:
        raise PreferenceDatasetError("private_path_must_be_file")
    return candidate


def _exact_fields(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, Mapping):
        raise PreferenceDatasetError(f"{label}_must_be_object")
    observed = set(value)
    missing = sorted(fields - observed)
    extra = sorted(observed - fields)
    if missing:
        raise PreferenceDatasetError(f"{label}_missing_fields:{','.join(missing)}")
    if extra:
        raise PreferenceDatasetError(f"{label}_unknown_fields:{','.join(extra)}")


def _hash(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HASH_PATTERN.fullmatch(value):
        raise PreferenceDatasetError(f"{label}_must_be_sha256")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PreferenceDatasetError(f"{label}_must_be_non_empty_string")
    if len(value) > 2048:
        raise PreferenceDatasetError(f"{label}_too_long")
    return value


def _ensure_json_safe(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PreferenceDatasetError("non_finite_number_rejected")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PreferenceDatasetError("json_object_key_must_be_string")
            _ensure_json_safe(item)
        return
    if isinstance(value, list):
        for item in value:
            _ensure_json_safe(item)
        return
    raise PreferenceDatasetError("non_json_training_value_rejected")


def _reject_sensitive_material(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).strip().lower().replace("-", "_")
            if normalized_key in SENSITIVE_KEYS:
                raise PreferenceDatasetError("secret_or_credential_material_rejected")
            _reject_sensitive_material(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_sensitive_material(item)
        return
    if not isinstance(value, str):
        return
    for pattern in SENSITIVE_VALUE_PATTERNS:
        if pattern.search(value):
            raise PreferenceDatasetError("secret_or_credential_material_rejected")


def _all_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_keys(item)
