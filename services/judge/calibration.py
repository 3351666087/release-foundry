"""Calibration matrix for local, ReleaseFoundry, and LLM judge comparisons."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .releasefoundry_test_receipts import (
    RELEASEFOUNDRY_ARGUMENT_FAIL_STATUSES,
    RELEASEFOUNDRY_ARGUMENT_PASS_STATUSES,
    RELEASEFOUNDRY_LLM_FAIL_VERDICTS,
    RELEASEFOUNDRY_LLM_PASS_VERDICTS,
    PUBLIC_RECEIPT_SCHEMA_VERSION,
    assert_public_releasefoundry_test_terminal_receipt_safe,
    build_releasefoundry_test_scoring_receipt,
    build_releasefoundry_test_terminal_receipt,
    public_releasefoundry_test_scoring_summary,
    public_releasefoundry_test_terminal_receipt,
)
from .releasefoundry_dataset_identity import (
    RECEIPT_SCHEMA_VERSION as DATASET_IDENTITY_RECEIPT_SCHEMA_VERSION,
    VerifiedDatasetIdentityBinding,
)
from .coverage import DEFAULT_RUN_FIXTURES
from .result_persistence import stable_hash
from .runner import DEFAULT_SCENARIO_PACK, grade_run
from .schemas import CANONICAL_FAILURE_CLASSES


DEFAULT_CALIBRATION_OBSERVATIONS = Path("fixtures/a2/calibration/a2_g3_calibration_observations.json")
DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET = Path(
    "fixtures/a2/calibration/a2_semantic_judge_collection_packet.json"
)
REQUIRED_SOURCES = ("local_judge", "releasefoundry_grading", "llm_judge")
OFFLINE_SEMANTIC_PROVIDERS = {"offline_reference", "offline reference judge samples"}
EXTERNAL_OBSERVATION_FIELDS = frozenset(
    {
        "case_id",
        "scenario_id",
        "source",
        "status",
        "provider",
        "model",
        "passed",
        "primary_failure_class",
        "score",
        "confidence",
        "rationale",
        "cost",
        "evidence_ref",
        "metadata",
    }
)
EXTERNAL_COST_FIELDS = frozenset(
    {"prompt_tokens", "completion_tokens", "estimated_usd"}
)
REVIEWED_SEMANTIC_METADATA_FIELDS = (
    "prompt_template_id",
    "prompt_hash",
    "response_hash",
    "review_status",
    "sdk_language",
)
REQUIRED_SEMANTIC_SDK_LANGUAGES = {"python", "typescript"}
PASSING_TEXT_STATUSES = {"exact", "similar", "match"}
PASSING_TOOL_STATUSES = {"exact", "match"}
PRIVATE_EVIDENCE_PREFIX = "docs/evidence/private_refs/"
EVIDENCE_PATH_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9._\-]+")
EVIDENCE_FRAGMENT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\-]*")
REVIEWER_RECEIPT_PATTERN = re.compile(r"sha256:[a-f0-9]{64}")
SHA256_12_PATTERN = re.compile(r"[a-f0-9]{12}")
SEMANTIC_COLLECTION_PACKET_SCHEMA_VERSION = "a2.semantic_judge_collection_packet.v1"
SEMANTIC_HUMAN_REVIEW_RECEIPT_SCHEMA_VERSION = (
    "a2.semantic_human_review_receipt.v1"
)
SEMANTIC_HUMAN_REVIEW_SCOPE = "a2_c4_semantic_judge_acceptance"
SEMANTIC_COLLECTION_BINDING_METADATA_FIELDS = (
    "semantic_collection_packet_schema_version",
    "semantic_collection_packet_id",
    "semantic_collection_packet_sha256",
    "semantic_collection_dataset_id",
    "semantic_collection_case_count",
    "semantic_collection_target_observation_count",
    "semantic_collection_case_id",
    "semantic_collection_case_sdk_language",
    "semantic_collection_case_prompt_template_id",
    "semantic_collection_case_prompt_material_sha256",
)
SEMANTIC_REVIEW_RECEIPT_METADATA_FIELDS = {
    "schema_version": "semantic_review_receipt_schema_version",
    "verification_state": "semantic_review_verification_state",
    "review_scope": "semantic_review_scope",
    "expected_case_count": "semantic_review_expected_case_count",
    "reviewed_case_count": "semantic_review_reviewed_case_count",
    "receipt_complete": "semantic_review_receipt_complete",
    "public_safe": "semantic_review_receipt_public_safe",
    "raw_review_notes_included": "semantic_review_raw_review_notes_included",
    "raw_reviewer_identity_included": (
        "semantic_review_raw_reviewer_identity_included"
    ),
}
SEMANTIC_REVIEW_RECEIPT_FIELDS = {
    *SEMANTIC_REVIEW_RECEIPT_METADATA_FIELDS,
    "cases",
}
SEMANTIC_REVIEW_RECEIPT_CASE_FIELDS = {
    "case_id",
    "scenario_id",
    "review_status",
    "reviewer_receipt",
    "reviewed_at_unix_ms",
    "provider",
    "model",
    "passed",
    "primary_failure_class",
    "score",
    "confidence",
    "prompt_hash",
    "response_hash",
    "sdk_language",
    "evidence_ref",
    "rationale_sha256",
}
RELEASEFOUNDRY_RUN_RECEIPT_METADATA_FIELDS = {
    "schema_version": "run_terminal_receipt_schema_version",
    "expected_test_count": "run_expected_test_count",
    "verified_test_count": "run_verified_test_count",
    "receipt_complete": "run_receipt_complete",
    "run_dataset_id_verified": "run_dataset_id_verified",
    "run_result_terminal_verified": "run_result_terminal_verified",
    "server_grading_lifecycle_verified": "server_grading_lifecycle_verified",
    "exact_test_set_verified": "exact_test_set_verified",
    "all_expected_tests_terminal_scoring_verified": (
        "all_expected_tests_terminal_scoring_verified"
    ),
    "observed_judge_version": "observed_judge_version",
    "judge_version_source": "judge_version_source",
    "judge_version_verified": "judge_version_verified",
    "aggregate_marker_used_as_acceptance_authority": (
        "aggregate_marker_used_as_acceptance_authority"
    ),
    "blockers": "run_terminal_receipt_blockers",
}
RELEASEFOUNDRY_TEST_RECEIPT_METADATA_FIELDS = {
    "terminal_status": "terminal_status",
    "response_evidence_count": "response_evidence_count",
    "response_evidence_kinds": "response_evidence_kinds",
    "grading_signal_count": "grading_signal_count",
    "grading_signal_types": "grading_signal_types",
    "terminal_status_verified": "terminal_status_verified",
    "timestamps_verified": "timestamps_verified",
    "response_evidence_verified": "response_evidence_verified",
    "server_grading_signal_verified": "server_grading_signal_verified",
    "terminal_scoring_verified": "terminal_scoring_verified",
    "blockers": "terminal_receipt_blockers",
}
RELEASEFOUNDRY_METADATA_STRING_FIELDS = frozenset(
    {
        "raw_case_id",
        "review_status",
        "reviewer_receipt",
        "terminal_scoring_receipt_schema_version",
        "terminal_status",
        "run_terminal_receipt_schema_version",
        "run_terminal_receipt_sha256",
        "observed_judge_version",
        "judge_version_source",
        "dataset_identity_receipt_schema_version",
        "dataset_identity_receipt_sha256",
        "dataset_identity_manifest_sha256",
        "dataset_identity_content_sha256",
        "dataset_identity_content_collection",
    }
)
RELEASEFOUNDRY_METADATA_INTEGER_FIELDS = frozenset(
    {
        "response_evidence_count",
        "grading_signal_count",
        "run_expected_test_count",
        "run_verified_test_count",
        "dataset_identity_content_item_count",
    }
)
RELEASEFOUNDRY_METADATA_BOOLEAN_FIELDS = frozenset(
    {
        "terminal_status_verified",
        "timestamps_verified",
        "response_evidence_verified",
        "server_grading_signal_verified",
        "terminal_scoring_verified",
        "run_receipt_complete",
        "run_dataset_id_verified",
        "run_result_terminal_verified",
        "server_grading_lifecycle_verified",
        "exact_test_set_verified",
        "all_expected_tests_terminal_scoring_verified",
        "judge_version_verified",
        "aggregate_marker_used_as_acceptance_authority",
        "dataset_identity_verified",
    }
)
RELEASEFOUNDRY_METADATA_STRING_LIST_FIELDS = frozenset(
    {
        "match_statuses",
        "response_evidence_kinds",
        "grading_signal_types",
        "terminal_receipt_blockers",
        "run_terminal_receipt_blockers",
        "dataset_identity_blockers",
    }
)
RELEASEFOUNDRY_METADATA_INTEGER_LIST_FIELDS = frozenset({"action_indexes"})
RELEASEFOUNDRY_METADATA_FIELDS = frozenset(
    {
        "reviewed_at_unix_ms",
        *RELEASEFOUNDRY_METADATA_STRING_FIELDS,
        *RELEASEFOUNDRY_METADATA_INTEGER_FIELDS,
        *RELEASEFOUNDRY_METADATA_BOOLEAN_FIELDS,
        *RELEASEFOUNDRY_METADATA_STRING_LIST_FIELDS,
        *RELEASEFOUNDRY_METADATA_INTEGER_LIST_FIELDS,
    }
)
SEMANTIC_METADATA_STRING_FIELDS = frozenset(
    {
        "raw_case_id",
        "prompt_template_id",
        "prompt_hash",
        "response_hash",
        "review_status",
        "sdk_language",
        "reviewer_receipt",
        "semantic_review_receipt_sha256",
        *SEMANTIC_COLLECTION_BINDING_METADATA_FIELDS,
        *SEMANTIC_REVIEW_RECEIPT_METADATA_FIELDS.values(),
    }
    - {
        "semantic_collection_case_count",
        "semantic_collection_target_observation_count",
        "semantic_review_expected_case_count",
        "semantic_review_reviewed_case_count",
        "semantic_review_receipt_complete",
        "semantic_review_receipt_public_safe",
        "semantic_review_raw_review_notes_included",
        "semantic_review_raw_reviewer_identity_included",
    }
)
SEMANTIC_METADATA_INTEGER_FIELDS = frozenset(
    {
        "semantic_collection_case_count",
        "semantic_collection_target_observation_count",
        "semantic_review_expected_case_count",
        "semantic_review_reviewed_case_count",
    }
)
SEMANTIC_METADATA_BOOLEAN_FIELDS = frozenset(
    {
        "semantic_review_receipt_complete",
        "semantic_review_receipt_public_safe",
        "semantic_review_raw_review_notes_included",
        "semantic_review_raw_reviewer_identity_included",
    }
)
SEMANTIC_METADATA_FIELDS = frozenset(
    {
        "reviewed_at_unix_ms",
        *SEMANTIC_METADATA_STRING_FIELDS,
        *SEMANTIC_METADATA_INTEGER_FIELDS,
        *SEMANTIC_METADATA_BOOLEAN_FIELDS,
    }
)
SECRET_LIKE_PATTERNS = (
    re.compile(r"tp_[A-Za-z0-9_\-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
)


def build_calibration_matrix(
    *,
    pack_path: str | Path = DEFAULT_SCENARIO_PACK,
    run_dir: str | Path = DEFAULT_RUN_FIXTURES,
    observations_path: str | Path = DEFAULT_CALIBRATION_OBSERVATIONS,
) -> dict[str, Any]:
    observations_payload = load_calibration_observations(observations_path)
    fixture_by_case = load_run_fixtures_by_case(run_dir)
    observations = _observations_by_case_and_source(observations_payload.get("observations", []))
    source_notes = observations_payload.get("source_notes", {})
    cases = []

    for case in observations_payload.get("cases", []):
        case_id = str(case["case_id"])
        fixture = fixture_by_case[case_id]
        local = grade_run(
            fixture["scenario_id"],
            fixture.get("run", fixture),
            pack_path=pack_path,
            case_id=case_id,
        )
        sources = {
            "local_judge": _local_source(local),
            "releasefoundry_grading": _external_source(
                observations.get((case_id, "releasefoundry_grading")),
                source_notes.get("releasefoundry_grading", {}),
            ),
            "llm_judge": _external_source(
                observations.get((case_id, "llm_judge")),
                source_notes.get("llm_judge", {}),
            ),
        }
        cases.append(
            {
                "case_id": case_id,
                "scenario_id": fixture["scenario_id"],
                "fixture_ref": str(case.get("fixture_ref", "")),
                "calibration_focus": case.get("calibration_focus", []),
                "expected": fixture.get("expected", {}),
                "sources": sources,
                "diffs": _case_diffs(sources),
                "calibration_tags": _calibration_tags(fixture.get("expected", {}), sources),
            }
        )

    matrix = {
        "schema_version": "a2.calibration_matrix.v1",
        "matrix_id": observations_payload.get("matrix_id", "a2_g3_calibration_matrix"),
        "dataset_id": observations_payload.get("dataset_id", "a2-g3-calibration"),
        "scenario_pack": _display_path(pack_path),
        "case_count": len(cases),
        "sources": list(REQUIRED_SOURCES),
        "source_coverage": _source_coverage(cases),
        "agreement_summary": {
            "local_vs_releasefoundry_grading": _agreement_summary(cases, "local_judge", "releasefoundry_grading"),
            "local_vs_llm_judge": _agreement_summary(cases, "local_judge", "llm_judge"),
            "releasefoundry_grading_vs_llm_judge": _agreement_summary(cases, "releasefoundry_grading", "llm_judge"),
        },
        "cost_ledger": _cost_ledger(cases),
        "calibration_warnings": _calibration_warnings(cases),
        "cases": cases,
        "metadata": {
            "deterministic": True,
            "observation_source": _display_path(observations_path),
            "notes": observations_payload.get("notes", []),
        },
    }
    if "releasefoundry_run_terminal_receipt" in observations_payload:
        matrix["releasefoundry_run_terminal_receipt"] = observations_payload[
            "releasefoundry_run_terminal_receipt"
        ]
    if "semantic_human_review_receipt" in observations_payload:
        matrix["semantic_human_review_receipt"] = observations_payload[
            "semantic_human_review_receipt"
        ]
    return matrix


def load_calibration_observations(path: str | Path = DEFAULT_CALIBRATION_OBSERVATIONS) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_run_fixtures_by_case(path: str | Path = DEFAULT_RUN_FIXTURES) -> dict[str, dict[str, Any]]:
    fixtures = {}
    for fixture_path in sorted(Path(path).glob("*.json")):
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        fixtures[str(fixture["case_id"])] = fixture
    return fixtures


def import_releasefoundry_grading_observations(
    payload: dict[str, Any] | list[Any],
    *,
    case_map: dict[str, str] | None = None,
    evidence_ref: str = "",
    provider: str = "releasefoundry server-side grading",
    review_status: str = "unreviewed",
    reviewer_receipt: Any = None,
    reviewed_at_unix_ms: Any = None,
    expected_case_ids: Iterable[str] | None = None,
    require_reviewed: bool = False,
    require_complete: bool = False,
    expected_dataset_id: int | None = None,
    expected_judge_version: str = "",
    verified_dataset_identity: VerifiedDatasetIdentityBinding | None = None,
) -> list[dict[str, Any]]:
    """Convert redacted ReleaseFoundry run records into A2 calibration observations."""
    mapped_cases = case_map or {}
    strict = require_reviewed or require_complete
    runs = extract_releasefoundry_runs(payload, reject_malformed_records=strict)
    run_receipt_metadata: dict[str, Any] = {}
    dataset_identity_metadata: dict[str, Any] = {}
    if strict:
        if (
            not isinstance(expected_dataset_id, int)
            or isinstance(expected_dataset_id, bool)
            or expected_dataset_id <= 0
        ):
            raise ValueError(
                "strict ReleaseFoundry grading import requires a positive expected_dataset_id"
            )
        if not mapped_cases:
            raise ValueError(
                "strict ReleaseFoundry grading import requires a non-empty case_map"
            )
        if verified_dataset_identity is None:
            raise ValueError(
                "strict ReleaseFoundry grading import requires a verified dataset identity binding"
            )
        if (
            verified_dataset_identity.expectation.dataset_id
            != expected_dataset_id
        ):
            raise ValueError(
                "verified dataset identity does not match expected_dataset_id"
            )
        if verified_dataset_identity.content_item_count != len(mapped_cases):
            raise ValueError(
                "verified dataset identity item count does not match case_map"
            )
        if len(runs) != 1:
            raise ValueError(
                "strict ReleaseFoundry grading import requires exactly one acceptance run"
            )
        private_run_receipt = build_releasefoundry_test_terminal_receipt(
            runs[0],
            case_map=mapped_cases,
            expected_dataset_id=expected_dataset_id,
            expected_judge_version=expected_judge_version,
        )
        if private_run_receipt.get("receipt_complete") is not True:
            blockers = ", ".join(private_run_receipt.get("blockers") or [])
            raise ValueError(
                "ReleaseFoundry grading acceptance run lacks a complete terminal receipt: "
                f"{blockers or 'receipt_incomplete'}"
            )
        run_receipt_metadata = _releasefoundry_run_terminal_receipt_metadata(
            public_releasefoundry_test_terminal_receipt(private_run_receipt)
        )
        dataset_identity_metadata = _verified_dataset_identity_metadata(
            verified_dataset_identity
        )
    observations = []
    for run in runs:
        for test in _releasefoundry_tests(run):
            raw_case_id = str(test.get("test_id") or test.get("case_id") or "")
            if not raw_case_id:
                continue
            case_id = str(mapped_cases.get(raw_case_id, raw_case_id))
            terminal_receipt = build_releasefoundry_test_scoring_receipt(
                test,
                expected_test_id=raw_case_id,
                case_id=case_id,
            )
            if strict and not terminal_receipt["terminal_scoring_verified"]:
                blockers = ", ".join(terminal_receipt["blockers"])
                raise ValueError(
                    f"ReleaseFoundry grading test {raw_case_id!r} lacks verified terminal "
                    f"scoring evidence: {blockers}"
                )
            failure = _classify_releasefoundry_test(test)
            metadata = {
                "raw_case_id": _redact_text(raw_case_id),
                "review_status": _redact_text(review_status),
                "action_indexes": failure["action_indexes"],
                "match_statuses": _releasefoundry_match_statuses(test),
                **_releasefoundry_terminal_receipt_metadata(terminal_receipt),
                **run_receipt_metadata,
                **dataset_identity_metadata,
            }
            if reviewer_receipt is not None:
                metadata["reviewer_receipt"] = _redact_text(str(reviewer_receipt))
            if reviewed_at_unix_ms is not None:
                metadata["reviewed_at_unix_ms"] = reviewed_at_unix_ms
            observations.append(
                {
                    "case_id": case_id,
                    "scenario_id": case_id,
                    "source": "releasefoundry_grading",
                    "status": "available",
                    "provider": provider,
                    "model": "releasefoundry-server-side",
                    "passed": failure["primary_failure_class"] == "none",
                    "primary_failure_class": failure["primary_failure_class"],
                    "score": _releasefoundry_score(test, failure["primary_failure_class"] == "none"),
                    "confidence": failure["confidence"],
                    "rationale": _redact_text(failure["summary"]),
                    "cost": _empty_cost(),
                    "evidence_ref": _prepare_external_evidence_ref(evidence_ref, strict=strict),
                    "metadata": metadata,
                }
            )
    _validate_external_observations(
        observations,
        source="releasefoundry_grading",
        expected_case_ids=expected_case_ids,
        require_reviewed=require_reviewed,
        require_complete=require_complete,
    )
    return observations


def _releasefoundry_terminal_receipt_metadata(
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Project only non-sensitive per-test scoring facts into an observation."""
    return {
        **public_releasefoundry_test_scoring_summary(receipt),
        "response_evidence_count": receipt.get("response_evidence_count"),
        "response_evidence_kinds": list(
            receipt.get("response_evidence_kinds")
            if isinstance(receipt.get("response_evidence_kinds"), list)
            else []
        ),
        "grading_signal_count": receipt.get("grading_signal_count"),
    }


def _releasefoundry_run_terminal_receipt_metadata(
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Project only public-safe run provenance required by the C3 gate."""
    return {
        "run_terminal_receipt_schema_version": receipt.get("schema_version"),
        "run_terminal_receipt_sha256": stable_hash(receipt),
        "run_expected_test_count": receipt.get("expected_test_count"),
        "run_verified_test_count": receipt.get("verified_test_count"),
        "run_receipt_complete": receipt.get("receipt_complete"),
        "run_dataset_id_verified": receipt.get("run_dataset_id_verified"),
        "run_result_terminal_verified": receipt.get(
            "run_result_terminal_verified"
        ),
        "server_grading_lifecycle_verified": receipt.get(
            "server_grading_lifecycle_verified"
        ),
        "exact_test_set_verified": receipt.get("exact_test_set_verified"),
        "all_expected_tests_terminal_scoring_verified": receipt.get(
            "all_expected_tests_terminal_scoring_verified"
        ),
        "observed_judge_version": receipt.get("observed_judge_version"),
        "judge_version_source": receipt.get("judge_version_source"),
        "judge_version_verified": receipt.get("judge_version_verified"),
        "aggregate_marker_used_as_acceptance_authority": receipt.get(
            "aggregate_marker_used_as_acceptance_authority"
        ),
        "run_terminal_receipt_blockers": list(
            receipt.get("blockers")
            if isinstance(receipt.get("blockers"), list)
            else []
        ),
    }


def _verified_dataset_identity_metadata(
    binding: VerifiedDatasetIdentityBinding,
) -> dict[str, Any]:
    """Project only public-safe immutable dataset provenance."""
    return {
        "dataset_identity_receipt_schema_version": (
            DATASET_IDENTITY_RECEIPT_SCHEMA_VERSION
        ),
        "dataset_identity_verified": True,
        "dataset_identity_receipt_sha256": binding.identity_receipt_sha256,
        "dataset_identity_manifest_sha256": binding.identity_manifest_sha256,
        "dataset_identity_content_sha256": (
            binding.expectation.dataset_content_sha256
        ),
        "dataset_identity_content_collection": binding.content_collection,
        "dataset_identity_content_item_count": binding.content_item_count,
        "dataset_identity_blockers": [],
    }


def import_semantic_judge_observations(
    payload: dict[str, Any] | list[Any],
    *,
    case_map: dict[str, str] | None = None,
    evidence_ref: str = "",
    expected_case_ids: Iterable[str] | None = None,
    require_reviewed: bool = False,
    require_complete: bool = False,
    collection_packet: dict[str, Any] | None = None,
    collection_packet_path: str | Path = DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET,
) -> list[dict[str, Any]]:
    """Convert reviewed semantic judge summaries into A2 llm_judge observations."""
    mapped_cases = case_map or {}
    strict = require_reviewed or require_complete
    observations = []
    for item in _semantic_judge_items(payload):
        raw_case_id = str(item.get("case_id") or item.get("raw_case_id") or "")
        if not raw_case_id:
            continue
        case_id = str(mapped_cases.get(raw_case_id, raw_case_id))
        output = item.get("output") if isinstance(item.get("output"), dict) else item
        primary = str(output.get("primary_failure_class", ""))
        if primary not in CANONICAL_FAILURE_CLASSES | {"none"}:
            raise ValueError(f"semantic judge case {case_id!r} has unknown primary_failure_class {primary!r}")
        passed = output.get("passed")
        if not isinstance(passed, bool):
            raise ValueError(f"semantic judge case {case_id!r} must have a boolean passed value")
        score = _normalize_score(output.get("score"))
        if score is None:
            raise ValueError(
                f"semantic judge case {case_id!r} must have a finite numeric score between 0 and 100"
            )

        raw_cost = item.get("cost") if isinstance(item.get("cost"), dict) else {}
        try:
            confidence = _normalize_confidence(output.get("confidence"))
            cost = _normalize_cost(
                raw_cost,
                require_fields=True,
                require_positive=True,
            )
        except ValueError as exc:
            raise ValueError(f"semantic judge case {case_id!r} {exc}") from exc
        observations.append(
            {
                "case_id": case_id,
                "scenario_id": str(item.get("scenario_id") or case_id),
                "source": "llm_judge",
                "status": "available",
                "provider": _redact_text(str(item.get("provider", ""))),
                "model": _redact_text(str(item.get("model", ""))),
                "passed": passed,
                "primary_failure_class": primary,
                "score": score,
                "confidence": confidence,
                "rationale": _redact_text(str(output.get("rationale", ""))),
                "cost": cost,
                "evidence_ref": _semantic_evidence_ref(
                    item,
                    output,
                    evidence_ref,
                    strict=strict,
                ),
                "metadata": _semantic_metadata(item, raw_case_id),
            }
        )
    _validate_external_observations(
        observations,
        source="llm_judge",
        expected_case_ids=expected_case_ids,
        require_reviewed=require_reviewed,
        require_complete=require_complete,
        semantic_collection_packet=collection_packet,
        semantic_collection_packet_path=collection_packet_path,
        semantic_human_review_receipt=(
            payload.get("semantic_human_review_receipt")
            if isinstance(payload, dict)
            else None
        ),
    )
    return observations


def merge_calibration_observations(
    base_payload: Any,
    incoming_payload: Any,
    *,
    source: str = "releasefoundry_grading",
    require_reviewed: bool = False,
    require_complete: bool = False,
    semantic_collection_packet: dict[str, Any] | None = None,
    semantic_collection_packet_path: str | Path = DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET,
) -> dict[str, Any]:
    """Merge reviewed external observations into an A2 calibration payload."""
    if source == "local_judge" or source not in REQUIRED_SOURCES:
        raise ValueError(f"source must be an external calibration source, got {source!r}")
    strict = require_reviewed or require_complete

    if not isinstance(base_payload, dict):
        raise ValueError("base calibration payload must be a JSON object")
    try:
        merged = json.loads(json.dumps(base_payload))
    except (TypeError, ValueError) as exc:
        raise ValueError("base calibration payload must be JSON-serializable") from exc

    known_cases = _calibration_case_index(merged)
    observations_by_key = _observations_by_case_and_source(
        merged.get("observations"),
        known_cases=known_cases,
        context="base",
    )
    incoming = _extract_observations(incoming_payload)
    if not incoming:
        raise ValueError("incoming payload does not contain observations")

    seen: set[tuple[str, str]] = set()
    for index, observation in enumerate(incoming):
        case_id, incoming_source = _calibration_observation_key(
            observation,
            index=index,
            context="incoming",
            known_cases=known_cases,
        )
        key = (case_id, incoming_source)
        if incoming_source != source:
            raise ValueError(f"incoming observation {case_id!r} has source {incoming_source!r}, expected {source!r}")
        if key in seen:
            raise ValueError(f"duplicate incoming observation for {case_id!r}/{incoming_source!r}")
        seen.add(key)

        normalized = dict(observation)
        normalized["case_id"] = case_id
        normalized["scenario_id"] = known_cases[case_id]
        observations_by_key[key] = normalized

    merged["observations"] = _sorted_observations(observations_by_key, known_cases)
    merged_source_observations = [
        observation
        for observation in merged["observations"]
        if observation.get("source") == source
    ]
    _validate_external_observations(
        merged_source_observations,
        source=source,
        expected_case_ids=known_cases,
        require_reviewed=require_reviewed,
        require_complete=require_complete,
        semantic_collection_packet=semantic_collection_packet,
        semantic_collection_packet_path=semantic_collection_packet_path,
        semantic_human_review_receipt=(
            incoming_payload.get("semantic_human_review_receipt")
            if isinstance(incoming_payload, dict)
            else None
        ),
    )
    if source == "releasefoundry_grading" and strict:
        run_receipt = (
            incoming_payload.get("run_terminal_receipt")
            if isinstance(incoming_payload, dict)
            else None
        )
        binding = validate_releasefoundry_run_receipt_binding(
            merged_source_observations,
            run_receipt,
            expected_case_ids=known_cases,
        )
        if not binding["valid"]:
            raise ValueError(
                "ReleaseFoundry run terminal receipt binding failed: "
                + ", ".join(binding["blockers"])
            )
        merged["releasefoundry_run_terminal_receipt"] = json.loads(
            json.dumps(run_receipt)
        )
    elif source == "releasefoundry_grading":
        merged.pop("releasefoundry_run_terminal_receipt", None)
    if source == "llm_judge" and strict:
        merged["semantic_human_review_receipt"] = json.loads(
            json.dumps(incoming_payload["semantic_human_review_receipt"])
        )
    elif source == "llm_judge":
        merged.pop("semantic_human_review_receipt", None)
    return merged


def validate_releasefoundry_run_receipt_binding(
    observations: list[dict[str, Any]],
    public_receipt: Any,
    *,
    expected_case_ids: Iterable[str],
) -> dict[str, Any]:
    """Bind reviewed ReleaseFoundry observations to one retained public run receipt."""
    blockers: list[str] = []
    expected = {
        str(case_id).strip()
        for case_id in expected_case_ids
        if str(case_id).strip()
    }
    if not expected:
        blockers.append("expected_case_ids_missing")

    artifact_present = isinstance(public_receipt, dict)
    artifact_hash = stable_hash(public_receipt) if artifact_present else ""
    if not artifact_present:
        blockers.append("run_receipt_artifact_missing")
        return _releasefoundry_run_receipt_binding_result(
            artifact_present=False,
            artifact_hash="",
            expected_count=len(expected),
            observation_count=len(observations),
            receipt_test_count=0,
            blockers=blockers,
        )

    try:
        assert_public_releasefoundry_test_terminal_receipt_safe(public_receipt)
    except ValueError as exc:
        blockers.append(f"run_receipt_artifact_not_public_safe:{exc}")

    expected_count = len(expected)
    exact_run_fields = {
        "schema_version": PUBLIC_RECEIPT_SCHEMA_VERSION,
        "verification_state": "verified",
        "expected_test_count": expected_count,
        "observed_test_count": expected_count,
        "valid_test_object_count": expected_count,
        "verified_test_count": expected_count,
        "missing_test_count": 0,
        "duplicate_test_count": 0,
        "unexpected_test_count": 0,
        "unidentified_test_count": 0,
        "malformed_test_count": 0,
        "nonterminal_test_count": 0,
        "receipt_complete": True,
        "run_dataset_id_verified": True,
        "run_result_terminal_verified": True,
        "server_grading_lifecycle_verified": True,
        "exact_test_set_verified": True,
        "all_expected_tests_terminal_scoring_verified": True,
        "judge_version_source": "server_observed",
        "judge_version_verified": True,
        "aggregate_marker_used_as_acceptance_authority": False,
        "blockers": [],
        "public_safe": True,
        "raw_server_payload_included": False,
        "raw_releasefoundry_identifiers_included": False,
        "raw_payload_hashes_included": False,
        "public_case_ids_included": True,
    }
    for field, expected_value in exact_run_fields.items():
        if public_receipt.get(field) != expected_value:
            blockers.append(f"run_receipt_{field}_invalid")
    observed_judge_version = public_receipt.get("observed_judge_version")
    if (
        not isinstance(observed_judge_version, str)
        or not observed_judge_version.strip()
    ):
        blockers.append("run_receipt_observed_judge_version_invalid")

    receipt_tests = public_receipt.get("tests")
    if not isinstance(receipt_tests, list):
        receipt_tests = []
        blockers.append("run_receipt_tests_missing_or_invalid")
    receipt_by_case: dict[str, dict[str, Any]] = {}
    receipt_case_ids: list[str] = []
    for index, receipt_test in enumerate(receipt_tests):
        if not isinstance(receipt_test, dict):
            blockers.append(f"run_receipt_test_{index}_not_object")
            continue
        case_id = str(receipt_test.get("case_id", "")).strip()
        if not case_id:
            blockers.append(f"run_receipt_test_{index}_case_id_missing")
            continue
        receipt_case_ids.append(case_id)
        if case_id in receipt_by_case:
            blockers.append("run_receipt_case_id_duplicate")
            continue
        receipt_by_case[case_id] = receipt_test

    receipt_case_set = set(receipt_case_ids)
    if expected - receipt_case_set:
        blockers.append("run_receipt_expected_case_missing")
    if receipt_case_set - expected:
        blockers.append("run_receipt_unexpected_case_present")
    if len(receipt_case_ids) != expected_count:
        blockers.append("run_receipt_test_count_mismatch")

    observation_by_case: dict[str, dict[str, Any]] = {}
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            blockers.append(f"releasefoundry_observation_{index}_not_object")
            continue
        case_id = str(observation.get("case_id", "")).strip()
        if not case_id:
            blockers.append(f"releasefoundry_observation_{index}_case_id_missing")
            continue
        if case_id in observation_by_case:
            blockers.append("releasefoundry_observation_case_id_duplicate")
            continue
        observation_by_case[case_id] = observation

    observation_case_set = set(observation_by_case)
    if expected - observation_case_set:
        blockers.append("releasefoundry_observation_expected_case_missing")
    if observation_case_set - expected:
        blockers.append("releasefoundry_observation_unexpected_case_present")
    if len(observations) != expected_count:
        blockers.append("releasefoundry_observation_count_mismatch")

    for case_id in sorted(expected & observation_case_set):
        observation = observation_by_case[case_id]
        metadata = (
            observation.get("metadata")
            if isinstance(observation.get("metadata"), dict)
            else {}
        )
        if metadata.get("run_terminal_receipt_sha256") != artifact_hash:
            blockers.append(
                f"releasefoundry_observation_{case_id}_run_terminal_receipt_sha256_mismatch"
            )
        for receipt_field, metadata_field in RELEASEFOUNDRY_RUN_RECEIPT_METADATA_FIELDS.items():
            if metadata.get(metadata_field) != public_receipt.get(receipt_field):
                blockers.append(
                    f"releasefoundry_observation_{case_id}_{metadata_field}_mismatch"
                )

        receipt_test = receipt_by_case.get(case_id)
        if receipt_test is None:
            continue
        for receipt_field, metadata_field in RELEASEFOUNDRY_TEST_RECEIPT_METADATA_FIELDS.items():
            if metadata.get(metadata_field) != receipt_test.get(receipt_field):
                blockers.append(
                    f"releasefoundry_observation_{case_id}_{metadata_field}_mismatch"
                )

    return _releasefoundry_run_receipt_binding_result(
        artifact_present=True,
        artifact_hash=artifact_hash,
        expected_count=expected_count,
        observation_count=len(observations),
        receipt_test_count=len(receipt_tests),
        blockers=blockers,
    )


def validate_semantic_review_receipt_binding(
    observations: list[dict[str, Any]],
    public_receipt: Any,
    *,
    expected_case_ids: Iterable[str],
) -> dict[str, Any]:
    """Bind reviewed semantic observations to one public-safe review receipt."""
    return _semantic_review_receipt_binding(
        observations,
        public_receipt,
        expected_case_ids=expected_case_ids,
        project_metadata=False,
    )


def _semantic_review_receipt_binding(
    observations: list[dict[str, Any]],
    public_receipt: Any,
    *,
    expected_case_ids: Iterable[str],
    project_metadata: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    expected = {
        str(case_id).strip()
        for case_id in expected_case_ids
        if str(case_id).strip()
    }
    if not expected:
        blockers.append("expected_case_ids_missing")

    artifact_present = isinstance(public_receipt, dict)
    artifact_hash = stable_hash(public_receipt) if artifact_present else ""
    if not artifact_present:
        blockers.append("semantic_review_receipt_artifact_missing")
        return _semantic_review_receipt_binding_result(
            artifact_present=False,
            artifact_hash="",
            expected_count=len(expected),
            observation_count=len(observations),
            receipt_case_count=0,
            blockers=blockers,
        )

    receipt_fields = set(public_receipt)
    for field in sorted(SEMANTIC_REVIEW_RECEIPT_FIELDS - receipt_fields):
        blockers.append(f"semantic_review_receipt_{field}_missing")
    for field in sorted(receipt_fields - SEMANTIC_REVIEW_RECEIPT_FIELDS):
        blockers.append(f"semantic_review_receipt_{field}_unexpected")

    expected_count = len(expected)
    exact_receipt_fields = {
        "schema_version": SEMANTIC_HUMAN_REVIEW_RECEIPT_SCHEMA_VERSION,
        "verification_state": "verified",
        "review_scope": SEMANTIC_HUMAN_REVIEW_SCOPE,
        "expected_case_count": expected_count,
        "reviewed_case_count": expected_count,
        "receipt_complete": True,
        "public_safe": True,
        "raw_review_notes_included": False,
        "raw_reviewer_identity_included": False,
    }
    for field, expected_value in exact_receipt_fields.items():
        if public_receipt.get(field) != expected_value:
            blockers.append(f"semantic_review_receipt_{field}_invalid")
    for field in ("expected_case_count", "reviewed_case_count"):
        value = public_receipt.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            blockers.append(f"semantic_review_receipt_{field}_not_integer")

    receipt_cases = public_receipt.get("cases")
    if not isinstance(receipt_cases, list):
        receipt_cases = []
        blockers.append("semantic_review_receipt_cases_missing_or_invalid")
    receipt_by_case: dict[str, dict[str, Any]] = {}
    receipt_case_ids: list[str] = []
    for index, receipt_case in enumerate(receipt_cases):
        if not isinstance(receipt_case, dict):
            blockers.append(f"semantic_review_receipt_case_{index}_not_object")
            continue
        case_fields = set(receipt_case)
        for field in sorted(SEMANTIC_REVIEW_RECEIPT_CASE_FIELDS - case_fields):
            blockers.append(
                f"semantic_review_receipt_case_{index}_{field}_missing"
            )
        for field in sorted(case_fields - SEMANTIC_REVIEW_RECEIPT_CASE_FIELDS):
            blockers.append(
                f"semantic_review_receipt_case_{index}_{field}_unexpected"
            )

        case_id = str(receipt_case.get("case_id", "")).strip()
        if not case_id:
            blockers.append(f"semantic_review_receipt_case_{index}_case_id_invalid")
            continue
        receipt_case_ids.append(case_id)
        if case_id in receipt_by_case:
            blockers.append("semantic_review_receipt_case_id_duplicate")
            continue
        receipt_by_case[case_id] = receipt_case
        _validate_semantic_review_receipt_case(
            receipt_case,
            case_id=case_id,
            blockers=blockers,
        )

    receipt_case_set = set(receipt_case_ids)
    if expected - receipt_case_set:
        blockers.append("semantic_review_receipt_expected_case_missing")
    if receipt_case_set - expected:
        blockers.append("semantic_review_receipt_unexpected_case_present")
    if len(receipt_cases) != expected_count:
        blockers.append("semantic_review_receipt_case_count_mismatch")

    observation_by_case: dict[str, dict[str, Any]] = {}
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            blockers.append(f"semantic_observation_{index}_not_object")
            continue
        case_id = str(observation.get("case_id", "")).strip()
        if not case_id:
            blockers.append(f"semantic_observation_{index}_case_id_missing")
            continue
        if case_id in observation_by_case:
            blockers.append("semantic_observation_case_id_duplicate")
            continue
        observation_by_case[case_id] = observation

    observation_case_set = set(observation_by_case)
    if expected - observation_case_set:
        blockers.append("semantic_observation_expected_case_missing")
    if observation_case_set - expected:
        blockers.append("semantic_observation_unexpected_case_present")
    if len(observations) != expected_count:
        blockers.append("semantic_observation_count_mismatch")

    for case_id in sorted(expected & observation_case_set):
        observation = observation_by_case[case_id]
        receipt_case = receipt_by_case.get(case_id)
        if receipt_case is not None:
            _compare_semantic_review_receipt_case(
                observation,
                receipt_case,
                case_id=case_id,
                blockers=blockers,
            )
        _bind_semantic_review_receipt_metadata(
            observation,
            public_receipt,
            artifact_hash=artifact_hash,
            case_id=case_id,
            blockers=blockers,
            project_metadata=project_metadata,
        )

    return _semantic_review_receipt_binding_result(
        artifact_present=True,
        artifact_hash=artifact_hash,
        expected_count=expected_count,
        observation_count=len(observations),
        receipt_case_count=len(receipt_cases),
        blockers=blockers,
    )


def _validate_semantic_review_receipt_case(
    receipt_case: dict[str, Any],
    *,
    case_id: str,
    blockers: list[str],
) -> None:
    if receipt_case.get("review_status") != "reviewed":
        blockers.append(
            f"semantic_review_receipt_{case_id}_review_status_invalid"
        )
    reviewer_receipt = receipt_case.get("reviewer_receipt")
    if (
        not isinstance(reviewer_receipt, str)
        or REVIEWER_RECEIPT_PATTERN.fullmatch(reviewer_receipt) is None
    ):
        blockers.append(
            f"semantic_review_receipt_{case_id}_reviewer_receipt_invalid"
        )
    reviewed_at = receipt_case.get("reviewed_at_unix_ms")
    if (
        isinstance(reviewed_at, bool)
        or not isinstance(reviewed_at, int)
        or reviewed_at <= 0
    ):
        blockers.append(
            f"semantic_review_receipt_{case_id}_reviewed_at_unix_ms_invalid"
        )
    for field in ("scenario_id", "provider", "model"):
        value = receipt_case.get(field)
        if not isinstance(value, str) or not value.strip():
            blockers.append(
                f"semantic_review_receipt_{case_id}_{field}_invalid"
            )
    if not isinstance(receipt_case.get("passed"), bool):
        blockers.append(f"semantic_review_receipt_{case_id}_passed_invalid")
    if receipt_case.get("primary_failure_class") not in (
        CANONICAL_FAILURE_CLASSES | {"none"}
    ):
        blockers.append(
            f"semantic_review_receipt_{case_id}_primary_failure_class_invalid"
        )
    if not _is_calibration_score(receipt_case.get("score")):
        blockers.append(f"semantic_review_receipt_{case_id}_score_invalid")
    try:
        _normalize_confidence(receipt_case.get("confidence"))
    except ValueError:
        blockers.append(f"semantic_review_receipt_{case_id}_confidence_invalid")
    for field in ("prompt_hash", "response_hash", "rationale_sha256"):
        value = receipt_case.get(field)
        if (
            not isinstance(value, str)
            or REVIEWER_RECEIPT_PATTERN.fullmatch(value) is None
        ):
            blockers.append(
                f"semantic_review_receipt_{case_id}_{field}_invalid"
            )
    if str(receipt_case.get("sdk_language", "")).strip().lower() not in (
        REQUIRED_SEMANTIC_SDK_LANGUAGES
    ):
        blockers.append(
            f"semantic_review_receipt_{case_id}_sdk_language_invalid"
        )
    if not is_canonical_private_evidence_ref(receipt_case.get("evidence_ref")):
        blockers.append(
            f"semantic_review_receipt_{case_id}_evidence_ref_invalid"
        )


def _compare_semantic_review_receipt_case(
    observation: dict[str, Any],
    receipt_case: dict[str, Any],
    *,
    case_id: str,
    blockers: list[str],
) -> None:
    metadata = (
        observation.get("metadata")
        if isinstance(observation.get("metadata"), dict)
        else {}
    )
    observation_values = {
        "case_id": observation.get("case_id"),
        "scenario_id": observation.get("scenario_id"),
        "review_status": metadata.get("review_status"),
        "reviewer_receipt": metadata.get("reviewer_receipt"),
        "reviewed_at_unix_ms": metadata.get("reviewed_at_unix_ms"),
        "provider": observation.get("provider"),
        "model": observation.get("model"),
        "passed": observation.get("passed"),
        "primary_failure_class": observation.get("primary_failure_class"),
        "score": observation.get("score"),
        "confidence": observation.get("confidence"),
        "prompt_hash": metadata.get("prompt_hash"),
        "response_hash": metadata.get("response_hash"),
        "sdk_language": metadata.get("sdk_language"),
        "evidence_ref": observation.get("evidence_ref"),
        "rationale_sha256": stable_hash(observation.get("rationale", "")),
    }
    for field in sorted(SEMANTIC_REVIEW_RECEIPT_CASE_FIELDS):
        if receipt_case.get(field) != observation_values[field]:
            blockers.append(
                f"semantic_review_receipt_{case_id}_{field}_mismatch"
            )


def _bind_semantic_review_receipt_metadata(
    observation: dict[str, Any],
    public_receipt: dict[str, Any],
    *,
    artifact_hash: str,
    case_id: str,
    blockers: list[str],
    project_metadata: bool,
) -> None:
    metadata = observation.get("metadata")
    if not isinstance(metadata, dict):
        blockers.append(f"semantic_observation_{case_id}_metadata_missing")
        return
    expected_metadata = {
        "semantic_review_receipt_sha256": artifact_hash,
        **{
            metadata_field: public_receipt.get(receipt_field)
            for receipt_field, metadata_field in (
                SEMANTIC_REVIEW_RECEIPT_METADATA_FIELDS.items()
            )
        },
    }
    for field, expected_value in expected_metadata.items():
        if field not in metadata:
            if not project_metadata:
                blockers.append(
                    f"semantic_observation_{case_id}_{field}_missing"
                )
            else:
                metadata[field] = expected_value
        elif metadata[field] != expected_value:
            blockers.append(f"semantic_observation_{case_id}_{field}_mismatch")


def _semantic_review_receipt_binding_result(
    *,
    artifact_present: bool,
    artifact_hash: str,
    expected_count: int,
    observation_count: int,
    receipt_case_count: int,
    blockers: list[str],
) -> dict[str, Any]:
    blockers = list(dict.fromkeys(blockers))
    return {
        "valid": not blockers,
        "artifact_present": artifact_present,
        "artifact_sha256": artifact_hash,
        "expected_case_count": expected_count,
        "observation_count": observation_count,
        "receipt_case_count": receipt_case_count,
        "blockers": blockers,
    }


def _releasefoundry_run_receipt_binding_result(
    *,
    artifact_present: bool,
    artifact_hash: str,
    expected_count: int,
    observation_count: int,
    receipt_test_count: int,
    blockers: list[str],
) -> dict[str, Any]:
    blockers = list(dict.fromkeys(blockers))
    return {
        "valid": not blockers,
        "artifact_present": artifact_present,
        "artifact_sha256": artifact_hash,
        "expected_case_count": expected_count,
        "observation_count": observation_count,
        "receipt_test_count": receipt_test_count,
        "blockers": blockers,
    }


def _validate_external_observations(
    observations: list[dict[str, Any]],
    *,
    source: str,
    expected_case_ids: Iterable[str] | None,
    require_reviewed: bool,
    require_complete: bool,
    semantic_collection_packet: dict[str, Any] | None = None,
    semantic_collection_packet_path: str | Path = DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET,
    semantic_human_review_receipt: Any = None,
) -> None:
    strict = require_reviewed or require_complete
    for observation in observations:
        case_id = str(observation.get("case_id", "")).strip()
        _validate_external_observation_public_shape(
            observation,
            source=source,
            case_id=case_id,
        )
        if not _is_calibration_score(observation.get("score")):
            raise ValueError(
                f"{source} observation {case_id!r} must have a finite numeric score between 0 and 100"
            )
        if source == "llm_judge":
            try:
                _normalize_confidence(observation.get("confidence"))
                _normalize_cost(
                    observation.get("cost")
                    if isinstance(observation.get("cost"), dict)
                    else {},
                    require_fields=True,
                )
            except ValueError as exc:
                raise ValueError(f"llm_judge observation {case_id!r} {exc}") from exc
    if not strict:
        return
    if not observations:
        raise ValueError(f"{source} strict validation requires at least one observation")

    expected = {
        str(case_id).strip()
        for case_id in expected_case_ids or []
        if str(case_id).strip()
    }
    if require_complete and not expected:
        raise ValueError(f"{source} complete validation requires expected_case_ids")

    seen: set[str] = set()
    sdk_languages: set[str] = set()
    for observation in observations:
        case_id = str(observation.get("case_id", "")).strip()
        if not case_id:
            raise ValueError(f"{source} observation is missing case_id")
        if case_id in seen:
            raise ValueError(f"duplicate {source} observation for case_id {case_id!r}")
        seen.add(case_id)

        incoming_source = str(observation.get("source", "")).strip()
        if incoming_source != source:
            raise ValueError(
                f"{source} strict validation received observation {case_id!r} "
                f"with source {incoming_source!r}"
            )
        if observation.get("status") != "available":
            raise ValueError(f"{source} observation {case_id!r} must have status='available'")
        if not str(observation.get("provider", "")).strip():
            raise ValueError(f"{source} observation {case_id!r} is missing provider")
        observation["evidence_ref"] = _validate_private_evidence_ref(
            observation.get("evidence_ref"),
            source=source,
            case_id=case_id,
        )
        if not isinstance(observation.get("passed"), bool):
            raise ValueError(f"{source} observation {case_id!r} must have a boolean passed value")

        primary = str(observation.get("primary_failure_class", "")).strip()
        if primary not in CANONICAL_FAILURE_CLASSES | {"none"}:
            raise ValueError(
                f"{source} observation {case_id!r} has unknown primary_failure_class {primary!r}"
            )

        metadata = observation.get("metadata") if isinstance(observation.get("metadata"), dict) else {}
        review_status = str(metadata.get("review_status", "")).strip().lower()
        if review_status != "reviewed":
            raise ValueError(
                f"{source} observation {case_id!r} must have metadata.review_status='reviewed'"
            )
        if not _has_canonical_reviewer_receipt(metadata):
            raise ValueError(
                f"{source} observation {case_id!r} requires a canonical "
                "metadata.reviewer_receipt"
            )
        if not _has_valid_reviewed_timestamp(metadata):
            raise ValueError(
                f"{source} observation {case_id!r} requires "
                "metadata.reviewed_at_unix_ms > 0"
            )

        if source == "llm_judge":
            provider = str(observation.get("provider", "")).strip().lower()
            if provider in OFFLINE_SEMANTIC_PROVIDERS:
                raise ValueError(
                    f"llm_judge observation {case_id!r} uses offline provider {provider!r}"
                )
            if not str(observation.get("model", "")).strip():
                raise ValueError(f"llm_judge observation {case_id!r} is missing model")
            missing_metadata = [
                field
                for field in REVIEWED_SEMANTIC_METADATA_FIELDS
                if not str(metadata.get(field, "")).strip()
            ]
            if missing_metadata:
                raise ValueError(
                    f"llm_judge observation {case_id!r} is missing reviewed metadata: "
                    f"{', '.join(missing_metadata)}"
                )
            for field in ("prompt_hash", "response_hash"):
                if not _has_canonical_sha256_metadata(metadata, field):
                    raise ValueError(
                        f"llm_judge observation {case_id!r} requires canonical "
                        f"metadata.{field}"
                    )
            sdk_language = str(metadata["sdk_language"]).strip().lower()
            if sdk_language not in REQUIRED_SEMANTIC_SDK_LANGUAGES:
                raise ValueError(
                    f"llm_judge observation {case_id!r} has unsupported sdk_language "
                    f"{sdk_language!r}"
                )
            sdk_languages.add(sdk_language)

            try:
                _normalize_cost(
                    observation["cost"],
                    require_fields=True,
                    require_positive=True,
                )
            except ValueError as exc:
                raise ValueError(f"llm_judge observation {case_id!r} {exc}") from exc

    if require_complete:
        missing = sorted(expected - seen)
        unexpected = sorted(seen - expected)
        if missing or unexpected:
            details = []
            if missing:
                details.append(f"missing={missing}")
            if unexpected:
                details.append(f"unexpected={unexpected}")
            raise ValueError(f"{source} observations do not exactly cover expected cases: {'; '.join(details)}")
        if source == "llm_judge":
            missing_languages = sorted(REQUIRED_SEMANTIC_SDK_LANGUAGES - sdk_languages)
            if missing_languages:
                raise ValueError(
                    "complete llm_judge observations must cover SDK languages: "
                    f"{', '.join(missing_languages)}"
                )
    if source == "llm_judge":
        _bind_semantic_observations_to_collection_packet(
            observations,
            expected_case_ids=expected,
            require_complete=require_complete,
            collection_packet=semantic_collection_packet,
            collection_packet_path=semantic_collection_packet_path,
        )
        if not isinstance(semantic_human_review_receipt, dict):
            raise ValueError(
                "semantic human review receipt artifact missing"
            )
        review_binding = _semantic_review_receipt_binding(
            observations,
            semantic_human_review_receipt,
            expected_case_ids=expected or seen,
            project_metadata=True,
        )
        if not review_binding["valid"]:
            raise ValueError(
                "semantic review receipt binding failed: "
                + ", ".join(review_binding["blockers"])
            )


def _validate_external_observation_public_shape(
    observation: dict[str, Any],
    *,
    source: str,
    case_id: str,
) -> None:
    unknown_fields = sorted(set(observation) - EXTERNAL_OBSERVATION_FIELDS)
    if unknown_fields:
        raise ValueError(
            f"{source} observation {case_id!r} has unsupported fields: "
            + ", ".join(unknown_fields)
        )

    for field in (
        "case_id",
        "scenario_id",
        "source",
        "status",
        "provider",
        "model",
        "primary_failure_class",
        "rationale",
        "evidence_ref",
    ):
        if field in observation and not isinstance(observation[field], str):
            raise ValueError(
                f"{source} observation {case_id!r} field {field} must be a string"
            )
    if "passed" in observation and not isinstance(observation["passed"], bool):
        raise ValueError(
            f"{source} observation {case_id!r} field passed must be a boolean"
        )

    cost = observation.get("cost")
    if not isinstance(cost, dict):
        raise ValueError(
            f"{source} observation {case_id!r} field cost must be an object"
        )
    unknown_cost_fields = sorted(set(cost) - EXTERNAL_COST_FIELDS)
    if unknown_cost_fields:
        raise ValueError(
            f"{source} observation {case_id!r} has unsupported cost fields: "
            + ", ".join(unknown_cost_fields)
        )

    if "metadata" not in observation:
        return
    metadata = observation["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError(
            f"{source} observation {case_id!r} field metadata must be an object"
        )

    if source == "releasefoundry_grading":
        allowed_fields = RELEASEFOUNDRY_METADATA_FIELDS
        string_fields = RELEASEFOUNDRY_METADATA_STRING_FIELDS
        integer_fields = RELEASEFOUNDRY_METADATA_INTEGER_FIELDS
        boolean_fields = RELEASEFOUNDRY_METADATA_BOOLEAN_FIELDS
        string_list_fields = RELEASEFOUNDRY_METADATA_STRING_LIST_FIELDS
        integer_list_fields = RELEASEFOUNDRY_METADATA_INTEGER_LIST_FIELDS
    else:
        allowed_fields = SEMANTIC_METADATA_FIELDS
        string_fields = SEMANTIC_METADATA_STRING_FIELDS
        integer_fields = SEMANTIC_METADATA_INTEGER_FIELDS
        boolean_fields = SEMANTIC_METADATA_BOOLEAN_FIELDS
        string_list_fields = frozenset()
        integer_list_fields = frozenset()

    unknown_metadata_fields = sorted(set(metadata) - allowed_fields)
    if unknown_metadata_fields:
        raise ValueError(
            f"{source} observation {case_id!r} has unsupported metadata fields: "
            + ", ".join(unknown_metadata_fields)
        )

    if "reviewed_at_unix_ms" in metadata and not _has_valid_reviewed_timestamp(
        metadata
    ):
        raise ValueError(
            f"{source} observation {case_id!r} requires "
            "metadata.reviewed_at_unix_ms > 0"
        )
    for field in string_fields & metadata.keys():
        if not isinstance(metadata[field], str):
            raise ValueError(
                f"{source} observation {case_id!r} metadata.{field} must be a string"
            )
    for field in integer_fields & metadata.keys():
        if isinstance(metadata[field], bool) or not isinstance(metadata[field], int):
            raise ValueError(
                f"{source} observation {case_id!r} metadata.{field} must be an integer"
            )
    for field in boolean_fields & metadata.keys():
        if not isinstance(metadata[field], bool):
            raise ValueError(
                f"{source} observation {case_id!r} metadata.{field} must be a boolean"
            )
    for field in string_list_fields & metadata.keys():
        value = metadata[field]
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError(
                f"{source} observation {case_id!r} metadata.{field} "
                "must contain only strings"
            )
    for field in integer_list_fields & metadata.keys():
        value = metadata[field]
        if not isinstance(value, list) or any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in value
        ):
            raise ValueError(
                f"{source} observation {case_id!r} metadata.{field} "
                "must contain only integers"
            )


def semantic_collection_packet_binding(
    packet: dict[str, Any],
) -> dict[str, Any]:
    """Validate and reduce a C4 collection packet to its binding authority."""
    if not isinstance(packet, dict):
        raise ValueError("semantic collection packet must be a JSON object")
    if packet.get("schema_version") != SEMANTIC_COLLECTION_PACKET_SCHEMA_VERSION:
        raise ValueError(
            "semantic collection packet has unsupported schema_version"
        )

    artifact_hash = packet.get("artifact_hash")
    if not isinstance(artifact_hash, str) or REVIEWER_RECEIPT_PATTERN.fullmatch(
        artifact_hash
    ) is None:
        raise ValueError(
            "semantic collection packet requires a canonical artifact_hash"
        )
    packet_core = {
        key: value
        for key, value in packet.items()
        if key != "artifact_hash"
    }
    if stable_hash(packet_core) != artifact_hash:
        raise ValueError("semantic collection packet artifact_hash mismatch")

    packet_id = _canonical_calibration_id(
        packet.get("packet_id"),
        label="semantic collection packet packet_id",
    )
    dataset_id = _canonical_calibration_id(
        packet.get("dataset_id"),
        label="semantic collection packet dataset_id",
    )
    cases = packet.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(
            "semantic collection packet must contain a non-empty cases list"
        )

    case_count = packet.get("case_count")
    target_count = packet.get("target_observation_count")
    for field, value in (
        ("case_count", case_count),
        ("target_observation_count", target_count),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise ValueError(
                f"semantic collection packet {field} must be a positive integer"
            )
    if case_count != len(cases) or target_count != len(cases):
        raise ValueError(
            "semantic collection packet counts must equal the number of cases"
        )

    contract = (
        packet.get("semantic_judge_contract")
        if isinstance(packet.get("semantic_judge_contract"), dict)
        else {}
    )
    contract_template_id = _canonical_calibration_id(
        contract.get("prompt_template_id"),
        label="semantic collection packet contract prompt_template_id",
    )
    case_bindings: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(
                f"semantic collection packet case at index {index} must be an object"
            )
        case_id = _canonical_calibration_id(
            case.get("case_id"),
            label=f"semantic collection packet case at index {index} case_id",
        )
        if case_id in case_bindings:
            raise ValueError(
                f"semantic collection packet has duplicate case_id {case_id!r}"
            )
        scenario_id = _canonical_calibration_id(
            case.get("scenario_id"),
            label=f"semantic collection packet case {case_id!r} scenario_id",
        )
        sdk_language = str(case.get("sdk_language", "")).strip().lower()
        if sdk_language not in REQUIRED_SEMANTIC_SDK_LANGUAGES:
            raise ValueError(
                f"semantic collection packet case {case_id!r} has unsupported "
                f"sdk_language {sdk_language!r}"
            )
        prompt_template_id = _canonical_calibration_id(
            case.get("prompt_template_id"),
            label=(
                f"semantic collection packet case {case_id!r} "
                "prompt_template_id"
            ),
        )
        if prompt_template_id != contract_template_id:
            raise ValueError(
                f"semantic collection packet case {case_id!r} prompt_template_id "
                "does not match the packet contract"
            )
        prompt_material_sha256 = case.get("prompt_material_sha256")
        if (
            not isinstance(prompt_material_sha256, str)
            or REVIEWER_RECEIPT_PATTERN.fullmatch(prompt_material_sha256) is None
        ):
            raise ValueError(
                f"semantic collection packet case {case_id!r} requires canonical "
                "prompt_material_sha256"
            )
        short_hash = case.get("prompt_material_sha256_12")
        if (
            not isinstance(short_hash, str)
            or SHA256_12_PATTERN.fullmatch(short_hash) is None
            or prompt_material_sha256.removeprefix("sha256:")[:12] != short_hash
        ):
            raise ValueError(
                f"semantic collection packet case {case_id!r} has inconsistent "
                "prompt material hashes"
            )
        case_bindings[case_id] = {
            "case_id": case_id,
            "scenario_id": scenario_id,
            "sdk_language": sdk_language,
            "prompt_template_id": prompt_template_id,
            "prompt_material_sha256": prompt_material_sha256,
        }

    allocation = (
        packet.get("sdk_language_plan", {}).get("allocation_counts")
        if isinstance(packet.get("sdk_language_plan"), dict)
        else None
    )
    actual_allocation = dict(
        sorted(
            Counter(
                case["sdk_language"]
                for case in case_bindings.values()
            ).items()
        )
    )
    if allocation != actual_allocation:
        raise ValueError(
            "semantic collection packet SDK allocation_counts do not match cases"
        )

    return {
        "schema_version": SEMANTIC_COLLECTION_PACKET_SCHEMA_VERSION,
        "packet_id": packet_id,
        "packet_sha256": artifact_hash,
        "dataset_id": dataset_id,
        "case_count": case_count,
        "target_observation_count": target_count,
        "cases": case_bindings,
    }


def load_semantic_collection_packet_binding(
    path: str | Path = DEFAULT_SEMANTIC_JUDGE_COLLECTION_PACKET,
) -> dict[str, Any]:
    """Load and validate the committed C4 collection packet."""
    try:
        packet = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"unable to load semantic collection packet from {path}"
        ) from exc
    return semantic_collection_packet_binding(packet)


def _bind_semantic_observations_to_collection_packet(
    observations: list[dict[str, Any]],
    *,
    expected_case_ids: set[str],
    require_complete: bool,
    collection_packet: dict[str, Any] | None,
    collection_packet_path: str | Path,
) -> None:
    binding = (
        semantic_collection_packet_binding(collection_packet)
        if collection_packet is not None
        else load_semantic_collection_packet_binding(collection_packet_path)
    )
    packet_cases = binding["cases"]
    packet_case_ids = set(packet_cases)
    if expected_case_ids and expected_case_ids != packet_case_ids:
        raise ValueError(
            "llm_judge expected_case_ids do not exactly match the semantic "
            "collection packet"
        )

    seen = set()
    for observation in observations:
        case_id = str(observation.get("case_id", "")).strip()
        expected_case = packet_cases.get(case_id)
        if expected_case is None:
            raise ValueError(
                f"llm_judge observation {case_id!r} is not in the semantic "
                "collection packet"
            )
        seen.add(case_id)
        metadata = (
            observation.get("metadata")
            if isinstance(observation.get("metadata"), dict)
            else {}
        )
        sdk_language = str(metadata.get("sdk_language", "")).strip().lower()
        if sdk_language != expected_case["sdk_language"]:
            raise ValueError(
                f"llm_judge observation {case_id!r} sdk_language does not match "
                "the semantic collection packet"
            )
        prompt_template_id = str(
            metadata.get("prompt_template_id", "")
        ).strip()
        if prompt_template_id != expected_case["prompt_template_id"]:
            raise ValueError(
                f"llm_judge observation {case_id!r} prompt_template_id does not "
                "match the semantic collection packet"
            )
        prompt_hash = metadata.get("prompt_hash")
        if prompt_hash != expected_case["prompt_material_sha256"]:
            raise ValueError(
                f"llm_judge observation {case_id!r} prompt_hash does not match "
                "the semantic collection packet prompt material"
            )

        projected = {
            "semantic_collection_packet_schema_version": binding[
                "schema_version"
            ],
            "semantic_collection_packet_id": binding["packet_id"],
            "semantic_collection_packet_sha256": binding["packet_sha256"],
            "semantic_collection_dataset_id": binding["dataset_id"],
            "semantic_collection_case_count": binding["case_count"],
            "semantic_collection_target_observation_count": binding[
                "target_observation_count"
            ],
            "semantic_collection_case_id": case_id,
            "semantic_collection_case_sdk_language": expected_case[
                "sdk_language"
            ],
            "semantic_collection_case_prompt_template_id": expected_case[
                "prompt_template_id"
            ],
            "semantic_collection_case_prompt_material_sha256": expected_case[
                "prompt_material_sha256"
            ],
        }
        for field, value in projected.items():
            if field in metadata and metadata[field] != value:
                raise ValueError(
                    f"llm_judge observation {case_id!r} metadata.{field} does "
                    "not match the semantic collection packet"
                )
        metadata.update(projected)
        observation["metadata"] = metadata
        observation["scenario_id"] = expected_case["scenario_id"]

    if require_complete and seen != packet_case_ids:
        missing = sorted(packet_case_ids - seen)
        unexpected = sorted(seen - packet_case_ids)
        details = []
        if missing:
            details.append(f"missing={missing}")
        if unexpected:
            details.append(f"unexpected={unexpected}")
        raise ValueError(
            "complete llm_judge observations do not exactly cover the semantic "
            f"collection packet: {'; '.join(details)}"
        )


def extract_releasefoundry_runs(
    payload: dict[str, Any] | list[Any],
    *,
    reject_malformed_records: bool = False,
) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if reject_malformed_records and any(
            not isinstance(item, dict) for item in payload
        ):
            raise ValueError(
                "strict ReleaseFoundry grading payload contains a non-object run record"
            )
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    response = payload.get("response")
    if isinstance(response, dict):
        runs = extract_releasefoundry_runs(
            response,
            reject_malformed_records=reject_malformed_records,
        )
        if runs:
            return runs
    run = payload.get("run")
    if isinstance(run, dict):
        return [run]
    runs = payload.get("runs")
    if isinstance(runs, list):
        if reject_malformed_records and any(
            not isinstance(item, dict) for item in runs
        ):
            raise ValueError(
                "strict ReleaseFoundry grading payload contains a non-object run record"
            )
        return [item for item in runs if isinstance(item, dict)]
    if payload.get("id") is not None and isinstance(payload.get("result"), dict):
        return [payload]
    return []


def _semantic_judge_items(payload: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    observations = payload.get("observations")
    if isinstance(observations, list):
        return [item for item in observations if isinstance(item, dict)]
    cases = payload.get("cases")
    if isinstance(cases, list):
        return [item for item in cases if isinstance(item, dict)]
    if payload.get("case_id") or payload.get("raw_case_id"):
        return [payload]
    return []


def _calibration_case_index(payload: dict[str, Any]) -> dict[str, str]:
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("base calibration payload must contain a non-empty cases list")

    known_cases: dict[str, str] = {}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"base case at index {index} must be an object")
        case_id = _canonical_calibration_id(
            case.get("case_id"),
            label=f"base case at index {index} case_id",
        )
        scenario_id = _canonical_calibration_id(
            case.get("scenario_id"),
            label=f"base case {case_id!r} scenario_id",
        )
        if case_id in known_cases:
            raise ValueError(f"duplicate base case_id {case_id!r}")
        known_cases[case_id] = scenario_id
    return known_cases


def _canonical_calibration_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a canonical non-empty string")
    return value


def _observation_objects(items: Any, *, context: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError(f"{context} observations must be a list")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{context} observation at index {index} must be an object")
    return items


def _extract_observations(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _observation_objects(payload, context="incoming")
    if not isinstance(payload, dict):
        raise ValueError("incoming calibration payload must be a JSON object or list")
    if "observations" in payload:
        return _observation_objects(payload["observations"], context="incoming")
    if "case_id" in payload or "source" in payload:
        return [payload]
    return []


def _calibration_observation_key(
    observation: dict[str, Any],
    *,
    index: int,
    context: str,
    known_cases: dict[str, str] | None = None,
) -> tuple[str, str]:
    case_id = _canonical_calibration_id(
        observation.get("case_id"),
        label=f"{context} observation at index {index} case_id",
    )
    source = _canonical_calibration_id(
        observation.get("source"),
        label=f"{context} observation at index {index} source",
    )
    if source not in REQUIRED_SOURCES:
        raise ValueError(f"{context} observation {case_id!r} has unknown source {source!r}")
    if known_cases is not None and case_id not in known_cases:
        raise ValueError(f"{context} observation has unknown case_id {case_id!r}")
    return case_id, source


def _observations_by_case_and_source(
    observations: Any,
    *,
    known_cases: dict[str, str] | None = None,
    context: str = "calibration",
) -> dict[tuple[str, str], dict[str, Any]]:
    observation_rows = _observation_objects(observations, context=context)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for index, observation in enumerate(observation_rows):
        key = _calibration_observation_key(
            observation,
            index=index,
            context=context,
            known_cases=known_cases,
        )
        if key in result:
            raise ValueError(f"duplicate {context} observation for {key[0]!r}/{key[1]!r}")
        result[key] = observation
    return result


def _sorted_observations(
    observations_by_key: dict[tuple[str, str], dict[str, Any]],
    known_cases: dict[str, str],
) -> list[dict[str, Any]]:
    case_order = {case_id: index for index, case_id in enumerate(known_cases)}
    source_order = {source: index for index, source in enumerate(REQUIRED_SOURCES)}
    return [
        observation
        for _, observation in sorted(
            observations_by_key.items(),
            key=lambda item: (
                case_order.get(item[0][0], len(case_order)),
                source_order.get(item[0][1], len(source_order)),
                item[0][1],
                item[0][0],
            ),
        )
    ]


def _local_source(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": True,
        "status": "available",
        "source": "local_judge",
        "provider": "services.judge.runner.grade_run",
        "passed": result["passed"],
        "primary_failure_class": result["primary_failure_class"],
        "score": result["score"],
        "confidence": 1.0,
        "rationale": "Deterministic local A2 judge result.",
        "cost": _empty_cost(),
        "evidence_ref": "fixtures/a2/results/a2_g3_grade_results.json",
    }


def _external_source(observation: dict[str, Any] | None, source_note: dict[str, Any]) -> dict[str, Any]:
    if not observation or observation.get("status") != "available":
        return {
            "available": False,
            "status": observation.get("status", "missing") if observation else "missing",
            "source": observation.get("source", source_note.get("source", "")) if observation else source_note.get("source", ""),
            "provider": observation.get("provider", source_note.get("provider", "")) if observation else source_note.get("provider", ""),
            "reason": observation.get("reason", source_note.get("reason", "No calibration observation supplied."))
            if observation
            else source_note.get("reason", "No calibration observation supplied."),
            "cost": _empty_cost(),
        }

    source = {
        "available": True,
        "status": "available",
        "source": observation["source"],
        "provider": observation.get("provider", ""),
        "model": observation.get("model", ""),
        "passed": observation["passed"],
        "primary_failure_class": observation["primary_failure_class"],
        "score": observation.get("score", 0),
        "confidence": observation.get("confidence", 0),
        "rationale": observation.get("rationale", ""),
        "cost": _normalize_cost(observation.get("cost", {})),
        "evidence_ref": observation.get("evidence_ref", ""),
    }
    if isinstance(observation.get("metadata"), dict):
        source["metadata"] = observation["metadata"]
    return source


def _case_diffs(sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _source_diff(sources, "local_judge", "releasefoundry_grading"),
        _source_diff(sources, "local_judge", "llm_judge"),
        _source_diff(sources, "releasefoundry_grading", "llm_judge"),
    ]


def _source_diff(sources: dict[str, dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    left_result = sources[left]
    right_result = sources[right]
    comparable = left_result.get("available") is True and right_result.get("available") is True
    diff = {
        "left": left,
        "right": right,
        "comparable": comparable,
        "passed_match": None,
        "failure_class_match": None,
        "score_delta": None,
        "status": "missing_source",
    }
    if not comparable:
        return diff

    diff["passed_match"] = left_result["passed"] == right_result["passed"]
    diff["failure_class_match"] = left_result["primary_failure_class"] == right_result["primary_failure_class"]
    diff["score_delta"] = round(left_result.get("score", 0) - right_result.get("score", 0), 2)
    diff["status"] = "match" if diff["passed_match"] and diff["failure_class_match"] else "mismatch"
    return diff


def _calibration_tags(expected: dict[str, Any], sources: dict[str, dict[str, Any]]) -> list[str]:
    tags = []
    local = sources["local_judge"]
    if expected and (
        local.get("passed") != expected.get("passed")
        or local.get("primary_failure_class") != expected.get("primary_failure_class")
    ):
        tags.append("local_expected_mismatch")
    if any(diff["status"] == "mismatch" for diff in _case_diffs(sources)):
        tags.append("judge_disagreement_regression")
    if sources["releasefoundry_grading"].get("available") is not True:
        tags.append("needs_releasefoundry_grading")
    if not tags:
        tags.append("calibrated_agreement")
    return tags


def _source_coverage(cases: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    coverage = {}
    for source in REQUIRED_SOURCES:
        available = sum(1 for case in cases if case["sources"][source].get("available") is True)
        coverage[source] = {
            "available": available,
            "missing": len(cases) - available,
            "coverage_ratio": round(available / len(cases), 3) if cases else 0,
        }
    return coverage


def _agreement_summary(cases: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    diffs = [
        diff
        for case in cases
        for diff in case["diffs"]
        if diff["left"] == left and diff["right"] == right
    ]
    comparable = [diff for diff in diffs if diff["comparable"]]
    mismatches = [
        {
            "case_id": case["case_id"],
            "scenario_id": case["scenario_id"],
            "status": diff["status"],
            "passed_match": diff["passed_match"],
            "failure_class_match": diff["failure_class_match"],
        }
        for case in cases
        for diff in case["diffs"]
        if diff["left"] == left and diff["right"] == right and diff["status"] == "mismatch"
    ]
    return {
        "comparable": len(comparable),
        "missing": len(diffs) - len(comparable),
        "passed_agreement": sum(1 for diff in comparable if diff["passed_match"]),
        "failure_class_agreement": sum(1 for diff in comparable if diff["failure_class_match"]),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def _cost_ledger(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for source in REQUIRED_SOURCES:
        provider_counts = Counter()
        prompt_tokens = 0
        completion_tokens = 0
        estimated_usd = 0.0
        sample_count = 0
        for case in cases:
            result = case["sources"][source]
            if result.get("available") is not True:
                continue
            sample_count += 1
            provider_counts[str(result.get("provider", ""))] += 1
            cost = _normalize_cost(result.get("cost", {}))
            prompt_tokens += cost["prompt_tokens"]
            completion_tokens += cost["completion_tokens"]
            estimated_usd += cost["estimated_usd"]
        rows.append(
            {
                "source": source,
                "sample_count": sample_count,
                "provider_counts": dict(sorted(provider_counts.items())),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "estimated_usd": round(estimated_usd, 6),
            }
        )
    return rows


def _calibration_warnings(cases: list[dict[str, Any]]) -> list[str]:
    warnings = []
    coverage = _source_coverage(cases)
    for source, counts in coverage.items():
        if counts["missing"]:
            warnings.append(f"{source} is missing {counts['missing']} of {len(cases)} calibration cases.")
    local_llm = _agreement_summary(cases, "local_judge", "llm_judge")
    if local_llm["mismatch_count"]:
        warnings.append(
            f"local_judge vs llm_judge has {local_llm['mismatch_count']} disagreement regression candidates."
        )
    return warnings


def _normalize_cost(
    cost: dict[str, Any],
    *,
    require_fields: bool = False,
    require_positive: bool = False,
) -> dict[str, Any]:
    qualifier = "positive" if require_positive else "non-negative"
    minimum = 1 if require_positive else 0
    tokens = {}
    for field in ("prompt_tokens", "completion_tokens"):
        value = cost.get(field, 0)
        if (
            (require_fields and field not in cost)
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
        ):
            raise ValueError(f"must have {qualifier} cost.{field}")
        tokens[field] = value

    estimated_usd = cost.get("estimated_usd", 0.0)
    if (
        (require_fields and "estimated_usd" not in cost)
        or isinstance(estimated_usd, bool)
        or not isinstance(estimated_usd, (int, float))
        or not math.isfinite(float(estimated_usd))
        or (float(estimated_usd) <= 0 if require_positive else float(estimated_usd) < 0)
    ):
        raise ValueError(f"must have {qualifier} cost.estimated_usd")

    return {
        **tokens,
        "estimated_usd": float(estimated_usd),
    }


def _empty_cost() -> dict[str, Any]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "estimated_usd": 0.0}


def _releasefoundry_tests(run: dict[str, Any]) -> list[dict[str, Any]]:
    result = run.get("result") if isinstance(run.get("result"), dict) else {}
    tests = result.get("tests")
    return [item for item in tests if isinstance(item, dict)] if isinstance(tests, list) else []


def _classify_releasefoundry_test(test: dict[str, Any]) -> dict[str, Any]:
    action_results = test.get("action_results") if isinstance(test.get("action_results"), list) else []
    for action in action_results:
        if not isinstance(action, dict) or action.get("action_type") != "tool_call":
            continue
        for call in action.get("tool_calls", []) if isinstance(action.get("tool_calls"), list) else []:
            if not isinstance(call, dict):
                continue
            status = _tool_match_status(action, call).strip().lower()
            if not status or status in PASSING_TOOL_STATUSES:
                continue
            expected = call.get("expected") if isinstance(call.get("expected"), dict) else {}
            actual = call.get("actual") if isinstance(call.get("actual"), dict) else {}
            primary = _tool_failure_class(expected, actual)
            return {
                "primary_failure_class": primary,
                "confidence": 0.86,
                "summary": call.get("divergence_notes")
                or action.get("divergence_notes")
                or f"ReleaseFoundry tool-call match status was {status}.",
                "action_indexes": _action_indexes(action),
            }

    for action in action_results:
        if not isinstance(action, dict):
            continue
        status = str(action.get("match_status", "")).strip().lower()
        if action.get("actor") == "agent" and action.get("action_type") == "text" and status and status not in PASSING_TEXT_STATUSES:
            return {
                "primary_failure_class": "wrong_intent",
                "confidence": 0.72,
                "summary": action.get("divergence_notes") or f"ReleaseFoundry text match status was {status}.",
                "action_indexes": _action_indexes(action),
            }

    explicit_grading_failure = _explicit_releasefoundry_grading_failure(
        test,
        action_results,
    )
    if explicit_grading_failure is not None:
        return explicit_grading_failure

    test_status = str(test.get("status", "")).strip().lower()
    if test_status in {"failed", "fail"}:
        return {
            "primary_failure_class": "wrong_intent",
            "confidence": 0.66,
            "summary": (
                "ReleaseFoundry test reached terminal failed status without an "
                "interpretable failure classification."
            ),
            "action_indexes": [],
        }
    if test_status and test_status not in {"completed", "passed"}:
        return {
            "primary_failure_class": "poor_failure_recovery",
            "confidence": 0.6,
            "summary": f"ReleaseFoundry test status was {test_status}.",
            "action_indexes": [],
        }

    return {
        "primary_failure_class": "none",
        "confidence": 0.82,
        "summary": "ReleaseFoundry action results passed or had no failure signal.",
        "action_indexes": [],
    }


def _explicit_releasefoundry_grading_failure(
    test: dict[str, Any],
    action_results: list[Any],
) -> dict[str, Any] | None:
    for action in action_results:
        if not isinstance(action, dict) or action.get("actor") != "agent":
            continue
        if action.get("action_type") == "tool_call":
            calls = (
                action.get("tool_calls")
                if isinstance(action.get("tool_calls"), list)
                else []
            )
            for call in calls:
                if not isinstance(call, dict):
                    continue
                if "argument_comparison" in call:
                    outcome = _argument_comparison_outcome(
                        call.get("argument_comparison")
                    )
                    if outcome != "pass":
                        return {
                            "primary_failure_class": _tool_call_failure_class(call),
                            "confidence": 0.88 if outcome == "fail" else 0.7,
                            "summary": (
                                call.get("divergence_notes")
                                or (
                                    "ReleaseFoundry tool argument comparison reported a failure."
                                    if outcome == "fail"
                                    else "ReleaseFoundry tool argument comparison was not interpretable."
                                )
                            ),
                            "action_indexes": _action_indexes(action),
                        }
                if "llm_judgment" in call:
                    failure = _llm_judgment_failure(
                        call.get("llm_judgment"),
                        failure_class=_tool_call_failure_class(call),
                        signal_name="tool-call",
                        action_indexes=_action_indexes(action),
                    )
                    if failure is not None:
                        return failure

        if "llm_judgment" in action:
            failure_class = "wrong_intent"
            if action.get("action_type") == "tool_call":
                calls = (
                    action.get("tool_calls")
                    if isinstance(action.get("tool_calls"), list)
                    else []
                )
                first_call = next(
                    (call for call in calls if isinstance(call, dict)),
                    None,
                )
                failure_class = (
                    _tool_call_failure_class(first_call)
                    if first_call is not None
                    else "wrong_arguments"
                )
            failure = _llm_judgment_failure(
                action.get("llm_judgment"),
                failure_class=failure_class,
                signal_name="action",
                action_indexes=_action_indexes(action),
            )
            if failure is not None:
                return failure

    if "llm_judgment" in test:
        failure = _llm_judgment_failure(
            test.get("llm_judgment"),
            failure_class="wrong_intent",
            signal_name="test",
            action_indexes=[],
        )
        if failure is not None:
            return failure

    if "coherence" in test:
        coherence = test.get("coherence")
        outcome = _coherence_outcome(coherence)
        if outcome != "pass":
            summary = (
                coherence.get("summary")
                if isinstance(coherence, dict)
                and isinstance(coherence.get("summary"), str)
                and coherence.get("summary", "").strip()
                else (
                    "ReleaseFoundry coherence grading reported a failure."
                    if outcome == "fail"
                    else "ReleaseFoundry coherence grading was not interpretable."
                )
            )
            return {
                "primary_failure_class": "wrong_intent",
                "confidence": 0.84 if outcome == "fail" else 0.7,
                "summary": summary,
                "action_indexes": [],
            }
    return None


def _llm_judgment_failure(
    judgment: Any,
    *,
    failure_class: str,
    signal_name: str,
    action_indexes: list[int],
) -> dict[str, Any] | None:
    verdict = ""
    if isinstance(judgment, dict):
        verdict = str(judgment.get("verdict", "")).strip().lower()
    if verdict in RELEASEFOUNDRY_LLM_PASS_VERDICTS:
        return None
    outcome = "fail" if verdict in RELEASEFOUNDRY_LLM_FAIL_VERDICTS else "ambiguous"
    summary = ""
    if isinstance(judgment, dict):
        summary = str(
            judgment.get("summary")
            or judgment.get("reason")
            or ""
        ).strip()
    if not summary:
        summary = (
            f"ReleaseFoundry {signal_name} LLM judgment verdict was {verdict}."
            if outcome == "fail"
            else f"ReleaseFoundry {signal_name} LLM judgment was not interpretable."
        )
    return {
        "primary_failure_class": failure_class,
        "confidence": 0.9 if outcome == "fail" else 0.7,
        "summary": summary,
        "action_indexes": action_indexes,
    }


def _argument_comparison_outcome(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "ambiguous"
    status = value.get("status")
    if isinstance(status, str) and status.strip():
        normalized = status.strip().lower()
        if normalized in RELEASEFOUNDRY_ARGUMENT_PASS_STATUSES:
            return "pass"
        if normalized in RELEASEFOUNDRY_ARGUMENT_FAIL_STATUSES:
            return "fail"
        return "ambiguous"

    legacy_keys = {"different", "extra", "matching", "missing"}
    if not legacy_keys.issubset(value):
        return "ambiguous"
    buckets = [value.get(key) for key in legacy_keys]
    if not all(isinstance(bucket, (dict, list)) for bucket in buckets):
        return "ambiguous"
    if any(value.get(key) for key in ("different", "extra", "missing")):
        return "fail"
    return "pass"


def _coherence_outcome(value: Any) -> str:
    if not isinstance(value, dict):
        return "ambiguous"
    score = value.get("score")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
        or not 0 <= float(score) <= 1
    ):
        return "ambiguous"
    issues = value.get("issues")
    if "issues" in value and not isinstance(issues, list):
        return "ambiguous"
    if issues or float(score) < 1.0:
        return "fail"
    return "pass"


def _tool_call_failure_class(call: dict[str, Any]) -> str:
    expected = call.get("expected") if isinstance(call.get("expected"), dict) else {}
    actual = call.get("actual") if isinstance(call.get("actual"), dict) else {}
    if not expected and not actual:
        return "wrong_arguments"
    return _tool_failure_class(expected, actual)


def _tool_match_status(action: dict[str, Any], call: dict[str, Any]) -> str:
    comparison = call.get("argument_comparison") if isinstance(call.get("argument_comparison"), dict) else {}
    return str(call.get("match_status") or action.get("match_status") or comparison.get("status") or "")


def _tool_failure_class(expected: dict[str, Any], actual: dict[str, Any]) -> str:
    expected_tool = expected.get("tool_name") or expected.get("name")
    actual_tool = actual.get("tool_name") or actual.get("name")
    if not actual_tool:
        return "missing_required_tool"
    if not expected_tool:
        return "unnecessary_tool_call"
    if str(expected_tool) != str(actual_tool):
        return "wrong_tool"
    return "wrong_arguments"


def _releasefoundry_score(test: dict[str, Any], passed: bool) -> float:
    action_results = test.get("action_results") if isinstance(test.get("action_results"), list) else []
    scores = []
    for action in action_results:
        if not isinstance(action, dict) or action.get("semantic_similarity") is None:
            continue
        score = _normalize_score(action.get("semantic_similarity"))
        if score is None:
            test_id = str(test.get("test_id") or test.get("case_id") or "")
            raise ValueError(
                f"ReleaseFoundry grading test {test_id!r} must have a finite numeric "
                "semantic_similarity between 0 and 100"
            )
        scores.append(score)
    if scores:
        return round(sum(scores) / len(scores), 2)
    return 100.0 if passed else 0.0


def _normalize_score(value: Any) -> float | None:
    if not _is_calibration_score(value):
        return None
    numeric = float(value)
    if numeric <= 1:
        return round(numeric * 100, 2)
    return round(numeric, 2)


def _is_calibration_score(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    numeric = float(value)
    return math.isfinite(numeric) and 0 <= numeric <= 100


def _normalize_confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must have confidence in (0, 1]")
    numeric = float(value)
    if not math.isfinite(numeric) or not 0 < numeric <= 1:
        raise ValueError("must have confidence in (0, 1]")
    return round(numeric, 3)


def _semantic_metadata(item: dict[str, Any], raw_case_id: str) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    reviewer_receipt = (
        item.get("reviewer_receipt")
        if "reviewer_receipt" in item
        else metadata.get("reviewer_receipt")
    )
    reviewed_at_unix_ms = (
        item.get("reviewed_at_unix_ms")
        if "reviewed_at_unix_ms" in item
        else metadata.get("reviewed_at_unix_ms")
    )
    result = {
        "raw_case_id": _redact_text(raw_case_id),
        "prompt_template_id": _redact_text(str(item.get("prompt_template_id") or metadata.get("prompt_template_id", ""))),
        "prompt_hash": _redact_text(str(item.get("prompt_hash") or metadata.get("prompt_hash", ""))),
        "response_hash": _redact_text(str(item.get("response_hash") or metadata.get("response_hash", ""))),
        "review_status": _redact_text(str(item.get("review_status") or metadata.get("review_status", ""))),
        "sdk_language": _redact_text(str(item.get("sdk_language") or metadata.get("sdk_language", ""))),
        "reviewer_receipt": (
            _redact_text(str(reviewer_receipt))
            if reviewer_receipt is not None
            else None
        ),
        "reviewed_at_unix_ms": reviewed_at_unix_ms,
    }
    for field in SEMANTIC_COLLECTION_BINDING_METADATA_FIELDS:
        if field in item:
            result[field] = item[field]
        elif field in metadata:
            result[field] = metadata[field]
    for field in (
        "semantic_review_receipt_sha256",
        *SEMANTIC_REVIEW_RECEIPT_METADATA_FIELDS.values(),
    ):
        if field in item:
            result[field] = item[field]
        elif field in metadata:
            result[field] = metadata[field]
    return {
        key: value
        for key, value in result.items()
        if value is not None and (not isinstance(value, str) or value)
    }


def _semantic_evidence_ref(
    item: dict[str, Any],
    output: dict[str, Any],
    fallback: str,
    *,
    strict: bool,
) -> Any:
    evidence_refs = output.get("evidence_refs")
    if isinstance(evidence_refs, list) and evidence_refs:
        value = evidence_refs[0]
    else:
        value = item.get("evidence_ref") or fallback
    return _prepare_external_evidence_ref(value, strict=strict)


def _prepare_external_evidence_ref(value: Any, *, strict: bool) -> Any:
    if strict:
        return value
    return _redact_text(str(value))


def is_canonical_private_evidence_ref(value: Any) -> bool:
    try:
        _validate_private_evidence_ref(
            value,
            source="readiness",
            case_id="public-matrix",
        )
    except ValueError:
        return False
    return True


def has_valid_review_attestation(metadata: Any) -> bool:
    return (
        isinstance(metadata, dict)
        and str(metadata.get("review_status", "")).strip().lower() == "reviewed"
        and _has_canonical_reviewer_receipt(metadata)
        and _has_valid_reviewed_timestamp(metadata)
    )


def _has_canonical_reviewer_receipt(metadata: dict[str, Any]) -> bool:
    reviewer_receipt = metadata.get("reviewer_receipt")
    return (
        isinstance(reviewer_receipt, str)
        and REVIEWER_RECEIPT_PATTERN.fullmatch(reviewer_receipt) is not None
    )


def _has_canonical_sha256_metadata(
    metadata: dict[str, Any],
    field: str,
) -> bool:
    value = metadata.get(field)
    return (
        isinstance(value, str)
        and REVIEWER_RECEIPT_PATTERN.fullmatch(value) is not None
    )


def _has_valid_reviewed_timestamp(metadata: dict[str, Any]) -> bool:
    reviewed_at = metadata.get("reviewed_at_unix_ms")
    return (
        not isinstance(reviewed_at, bool)
        and isinstance(reviewed_at, int)
        and reviewed_at > 0
    )


def _validate_private_evidence_ref(value: Any, *, source: str, case_id: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            f"{source} observation {case_id!r} must have a string evidence_ref"
        )

    reference = value.strip()
    if not reference:
        raise ValueError(f"{source} observation {case_id!r} is missing evidence_ref")
    if reference != value:
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref must not contain surrounding whitespace"
        )
    if any(pattern.search(reference) for pattern in SECRET_LIKE_PATTERNS) or (
        "[redacted]" in reference.lower()
    ):
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref contains secret-like content"
        )

    path, separator, fragment = reference.partition("#")
    if separator and (not fragment or "#" in fragment):
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref has an invalid fragment"
        )
    if fragment and EVIDENCE_FRAGMENT_PATTERN.fullmatch(fragment) is None:
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref has an invalid fragment"
        )
    if "\\" in path:
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref must use repository-relative POSIX separators"
        )
    if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", path) or path.startswith("/"):
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref must be repository-relative"
        )

    segments = path.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref contains an invalid path segment"
        )
    if any(EVIDENCE_PATH_SEGMENT_PATTERN.fullmatch(segment) is None for segment in segments):
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref contains an invalid path segment"
        )
    if not path.startswith(PRIVATE_EVIDENCE_PREFIX):
        raise ValueError(
            f"{source} observation {case_id!r} evidence_ref must stay under "
            f"{PRIVATE_EVIDENCE_PREFIX}"
        )

    return reference


def _releasefoundry_match_statuses(test: dict[str, Any]) -> list[str]:
    action_results = test.get("action_results") if isinstance(test.get("action_results"), list) else []
    statuses = []
    for action in action_results:
        if not isinstance(action, dict):
            continue
        if action.get("match_status"):
            statuses.append(str(action["match_status"]))
        for call in action.get("tool_calls", []) if isinstance(action.get("tool_calls"), list) else []:
            if isinstance(call, dict) and call.get("match_status"):
                statuses.append(str(call["match_status"]))
    return statuses


def _action_indexes(action: dict[str, Any]) -> list[int]:
    index = action.get("action_index")
    return [int(index)] if isinstance(index, int) else []


def _redact_text(value: str) -> str:
    redacted = str(value)
    for pattern in SECRET_LIKE_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _display_path(path: str | Path) -> str:
    resolved = Path(path)
    try:
        return resolved.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return resolved.as_posix()
