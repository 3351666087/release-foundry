"""Fail-closed, per-test grading receipts for ReleaseFoundry run records."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any


PRIVATE_RECEIPT_SCHEMA_VERSION = "a2.releasefoundry_test_terminal_receipt_private.v2"
PUBLIC_RECEIPT_SCHEMA_VERSION = "a2.releasefoundry_test_terminal_receipt.v2"
TEST_SCORING_SUMMARY_SCHEMA_VERSION = (
    "a2.releasefoundry_test_terminal_scoring_summary.v1"
)
RUN_RESULT_TERMINAL_STATUSES = frozenset(
    {"completed", "completed_with_failures", "failed"}
)
OPTIONAL_GRADING_TERMINAL_STATUSES = frozenset(
    {"completed", "complete", "graded", "failed"}
)
SCORING_TERMINAL_STATUSES = frozenset({"completed", "failed"})
TEST_SCORING_SIGNAL_TYPES = frozenset(
    {
        "test_llm_judgment",
        "action_llm_judgment",
        "tool_llm_judgment",
        "tool_argument_comparison",
        "test_coherence",
    }
)

_JUDGE_VERSION_KEYS = ("judge_version", "grader_version")
RELEASEFOUNDRY_LLM_PASS_VERDICTS = frozenset(
    {"exact", "match", "pass", "passed", "acceptable"}
)
RELEASEFOUNDRY_LLM_FAIL_VERDICTS = frozenset(
    {"partial", "minor_issue", "major_issue", "divergent", "fail", "failed"}
)
RELEASEFOUNDRY_LLM_VERDICTS = RELEASEFOUNDRY_LLM_PASS_VERDICTS | RELEASEFOUNDRY_LLM_FAIL_VERDICTS
RELEASEFOUNDRY_ARGUMENT_PASS_STATUSES = frozenset({"exact", "match"})
RELEASEFOUNDRY_ARGUMENT_FAIL_STATUSES = frozenset(
    {"partial", "mismatch", "divergent"}
)
RELEASEFOUNDRY_ARGUMENT_COMPARISON_STATUSES = (
    RELEASEFOUNDRY_ARGUMENT_PASS_STATUSES | RELEASEFOUNDRY_ARGUMENT_FAIL_STATUSES
)
_LEGACY_ARGUMENT_COMPARISON_KEYS = frozenset(
    {"different", "extra", "matching", "missing"}
)
_PUBLIC_FORBIDDEN_KEYS = frozenset(
    {
        "run_id",
        "run_id_hash",
        "dataset_id",
        "dataset_id_hash",
        "expected_dataset_id",
        "expected_dataset_id_hash",
        "test_id",
        "test_id_hash",
        "response_hash",
        "server_test_result_hash",
        "run_result_hash",
        "identity_manifest_hash",
        "started_at",
        "completed_at",
        "api_key",
        "authorization",
        "access_token",
        "refresh_token",
        "signed_url",
        "secret",
    }
)
_SECRET_OR_AUTH_PATTERN = re.compile(
    r"(?i)(?:"
    r"\bauthorization\b|"
    r"\bbearer\s+[a-z0-9._-]+|"
    r"\b(?:sk|tp)_[a-z0-9_-]{8,}|"
    r"[?&](?:x-amz-signature|signature|sig|token)=[^&\s]+"
    r")"
)
_ABSOLUTE_WINDOWS_PATH_PATTERN = re.compile(r"^[a-zA-Z]:[\\/]")
_ABSOLUTE_POSIX_PATH_PATTERN = re.compile(r"^/")


class ReleaseFoundryTestReceiptError(ValueError):
    """Raised when a terminal receipt request itself is invalid."""


def build_releasefoundry_test_scoring_receipt(
    test: Mapping[str, Any],
    *,
    expected_test_id: str,
    case_id: str,
) -> dict[str, Any]:
    """Verify one ReleaseFoundry test has terminal response and server grading evidence."""
    if not isinstance(test, Mapping):
        raise ReleaseFoundryTestReceiptError("test_payload_invalid")
    if not isinstance(expected_test_id, str) or not expected_test_id:
        raise ReleaseFoundryTestReceiptError("expected_test_id_invalid")
    if not isinstance(case_id, str) or not case_id:
        raise ReleaseFoundryTestReceiptError("case_id_invalid")
    return _test_receipt(
        test,
        expected_test_id=expected_test_id,
        case_id=case_id,
    )


def public_releasefoundry_test_scoring_summary(
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Project the non-sensitive fields required by the public C3 gate."""
    return {
        "terminal_scoring_receipt_schema_version": (
            TEST_SCORING_SUMMARY_SCHEMA_VERSION
        ),
        "terminal_status": receipt.get("terminal_status"),
        "terminal_status_verified": receipt.get(
            "terminal_status_verified"
        ),
        "timestamps_verified": receipt.get("timestamps_verified"),
        "response_evidence_verified": receipt.get(
            "response_evidence_verified"
        ),
        "server_grading_signal_verified": receipt.get(
            "server_grading_signal_verified"
        ),
        "terminal_scoring_verified": receipt.get(
            "terminal_scoring_verified"
        ),
        "grading_signal_types": list(
            receipt.get("grading_signal_types")
            if isinstance(receipt.get("grading_signal_types"), list)
            else []
        ),
        "terminal_receipt_blockers": list(
            receipt.get("blockers")
            if isinstance(receipt.get("blockers"), list)
            else []
        ),
    }


def build_releasefoundry_test_terminal_receipt(
    run: Mapping[str, Any],
    *,
    case_map: Mapping[str, str],
    expected_dataset_id: int,
    expected_judge_version: str = "",
) -> dict[str, Any]:
    """Verify every expected test without trusting aggregate completion markers."""
    if not isinstance(run, Mapping):
        raise ReleaseFoundryTestReceiptError("run_payload_invalid")
    normalized_case_map = _normalize_case_map(case_map)
    expected_dataset_id = _positive_int(
        expected_dataset_id,
        "expected_dataset_id_invalid",
    )
    run_id = _required_identifier(run.get("id"), "run_id_missing")
    observed_dataset_id = run.get("dataset")
    result = run.get("result")
    if not isinstance(result, Mapping):
        result = {}

    blockers: list[str] = []
    run_dataset_id_verified = observed_dataset_id == expected_dataset_id
    if not run_dataset_id_verified:
        blockers.append("run_dataset_id_mismatch")

    run_result_status = _normalized_status(result.get("status"))
    run_result_terminal_verified = (
        run_result_status in RUN_RESULT_TERMINAL_STATUSES
    )
    if not run_result_terminal_verified:
        blockers.append("run_result_status_not_terminal")

    grading_lifecycle = _grading_lifecycle(run, result)
    blockers.extend(grading_lifecycle["blockers"])
    server_grading_lifecycle_verified = (
        run_result_terminal_verified
        and grading_lifecycle["optional_grading_status_veto_passed"]
    )

    judge_provenance = _judge_version_provenance(
        run,
        result,
        expected=expected_judge_version,
    )
    blockers.extend(judge_provenance["blockers"])

    tests = result.get("tests")
    test_collection_is_list = isinstance(tests, list)
    raw_test_entries = tests if test_collection_is_list else []
    if not test_collection_is_list:
        blockers.append("test_collection_missing_or_invalid")
    indexed, unidentified_test_count, malformed_test_count = _tests_by_id(
        raw_test_entries
    )
    if unidentified_test_count:
        blockers.append("test_id_missing_or_invalid")
    if malformed_test_count:
        blockers.append("test_entry_not_object")

    unexpected_test_ids = sorted(set(indexed) - set(normalized_case_map))
    unexpected_test_count = sum(
        len(indexed[test_id]) for test_id in unexpected_test_ids
    )
    if unexpected_test_count:
        blockers.append("unexpected_test_present")

    test_receipts: list[dict[str, Any]] = []
    for expected_test_id, case_id in normalized_case_map.items():
        matches = indexed.get(expected_test_id, [])
        if not matches:
            receipt = _missing_test_receipt(expected_test_id, case_id)
        elif len(matches) != 1:
            receipt = _duplicate_test_receipt(
                expected_test_id,
                case_id,
                len(matches),
            )
        else:
            receipt = build_releasefoundry_test_scoring_receipt(
                matches[0],
                expected_test_id=expected_test_id,
                case_id=case_id,
            )
        test_receipts.append(receipt)

    missing_count = sum(
        "test_missing" in item["blockers"] for item in test_receipts
    )
    duplicate_count = sum(
        "test_id_duplicate" in item["blockers"] for item in test_receipts
    )
    nonterminal_count = sum(
        "test_status_not_scoring_terminal" in item["blockers"]
        for item in test_receipts
    )
    verified_count = sum(
        bool(item["terminal_scoring_verified"]) for item in test_receipts
    )
    per_test_blockers = sorted(
        {
            blocker
            for item in test_receipts
            for blocker in item["blockers"]
        }
    )
    blockers.extend(per_test_blockers)

    aggregate_metrics = (
        result.get("aggregate_metrics")
        if isinstance(result.get("aggregate_metrics"), Mapping)
        else {}
    )
    aggregate_total = aggregate_metrics.get("total_tests")
    aggregate_total_present = aggregate_total is not None
    aggregate_total_consistent: bool | None = None
    if aggregate_total_present:
        aggregate_total_consistent = (
            isinstance(aggregate_total, int)
            and not isinstance(aggregate_total, bool)
            and aggregate_total == len(raw_test_entries)
        )
        if not aggregate_total_consistent:
            blockers.append("aggregate_total_mismatch")

    exact_test_set_verified = (
        test_collection_is_list
        and len(raw_test_entries) == len(normalized_case_map)
        and malformed_test_count == 0
        and unidentified_test_count == 0
        and unexpected_test_count == 0
        and missing_count == 0
        and duplicate_count == 0
    )
    all_terminal = (
        bool(test_receipts)
        and server_grading_lifecycle_verified
        and exact_test_set_verified
        and verified_count == len(test_receipts)
        and nonterminal_count == 0
    )
    blockers = list(dict.fromkeys(blockers))
    receipt_complete = (
        all_terminal
        and judge_provenance["judge_version_verified"]
        and not blockers
    )
    return {
        "schema_version": PRIVATE_RECEIPT_SCHEMA_VERSION,
        "verification_state": "verified" if receipt_complete else "blocked",
        "run_id": run_id,
        "dataset_id": observed_dataset_id,
        "expected_dataset_id": expected_dataset_id,
        "run_dataset_id_verified": run_dataset_id_verified,
        "run_result_status": run_result_status,
        "run_result_terminal_verified": run_result_terminal_verified,
        "grading_status": grading_lifecycle["grading_status"],
        "grading_status_present": grading_lifecycle["grading_status_present"],
        "grading_status_source_paths": grading_lifecycle[
            "grading_status_source_paths"
        ],
        "grading_status_terminal_verified": grading_lifecycle[
            "grading_status_terminal_verified"
        ],
        "server_grading_lifecycle_verified": (
            server_grading_lifecycle_verified
        ),
        "expected_judge_version": judge_provenance[
            "expected_judge_version"
        ],
        "observed_judge_version": judge_provenance[
            "observed_judge_version"
        ],
        "observed_judge_version_paths": judge_provenance[
            "observed_judge_version_paths"
        ],
        "judge_version_candidate_count": judge_provenance[
            "judge_version_candidate_count"
        ],
        "judge_version_source": judge_provenance["judge_version_source"],
        "judge_version_verified": judge_provenance[
            "judge_version_verified"
        ],
        "expected_test_count": len(normalized_case_map),
        "observed_test_count": len(raw_test_entries),
        "valid_test_object_count": (
            len(raw_test_entries) - malformed_test_count
        ),
        "verified_test_count": verified_count,
        "missing_test_count": missing_count,
        "duplicate_test_count": duplicate_count,
        "unexpected_test_count": unexpected_test_count,
        "unidentified_test_count": unidentified_test_count,
        "malformed_test_count": malformed_test_count,
        "nonterminal_test_count": nonterminal_count,
        "exact_test_set_verified": exact_test_set_verified,
        "aggregate_total_marker_present": aggregate_total_present,
        "aggregate_total_marker_consistent": aggregate_total_consistent,
        "aggregate_marker_used_as_acceptance_authority": False,
        "all_expected_tests_terminal_scoring_verified": all_terminal,
        "receipt_complete": receipt_complete,
        "tests": test_receipts,
        "blockers": blockers,
        "release_authority": False,
    }


def public_releasefoundry_test_terminal_receipt(
    private_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a receipt without raw ReleaseFoundry IDs, payloads, hashes, or timestamps."""
    public_tests: list[dict[str, Any]] = []
    tests = private_receipt.get("tests")
    for item in tests if isinstance(tests, list) else []:
        if not isinstance(item, Mapping):
            continue
        public_tests.append(
            {
                key: item.get(key)
                for key in (
                    "case_id",
                    "terminal_status",
                    "response_evidence_count",
                    "response_evidence_kinds",
                    "grading_signal_count",
                    "grading_signal_types",
                    "terminal_status_verified",
                    "timestamps_verified",
                    "response_evidence_verified",
                    "server_grading_signal_verified",
                    "terminal_scoring_verified",
                    "blockers",
                )
            }
        )
    public = {
        "schema_version": PUBLIC_RECEIPT_SCHEMA_VERSION,
        "verification_state": private_receipt.get("verification_state"),
        "run_dataset_id_verified": private_receipt.get(
            "run_dataset_id_verified"
        ),
        "run_result_status": private_receipt.get("run_result_status"),
        "run_result_terminal_verified": private_receipt.get(
            "run_result_terminal_verified"
        ),
        "grading_status": private_receipt.get("grading_status"),
        "grading_status_present": private_receipt.get(
            "grading_status_present"
        ),
        "grading_status_terminal_verified": private_receipt.get(
            "grading_status_terminal_verified"
        ),
        "server_grading_lifecycle_verified": private_receipt.get(
            "server_grading_lifecycle_verified"
        ),
        "expected_judge_version_supplied": bool(
            private_receipt.get("expected_judge_version")
        ),
        "observed_judge_version": private_receipt.get(
            "observed_judge_version"
        ),
        "judge_version_candidate_count": private_receipt.get(
            "judge_version_candidate_count"
        ),
        "judge_version_source": private_receipt.get("judge_version_source"),
        "judge_version_verified": private_receipt.get(
            "judge_version_verified"
        ),
        "expected_test_count": private_receipt.get("expected_test_count"),
        "observed_test_count": private_receipt.get("observed_test_count"),
        "valid_test_object_count": private_receipt.get(
            "valid_test_object_count"
        ),
        "verified_test_count": private_receipt.get("verified_test_count"),
        "missing_test_count": private_receipt.get("missing_test_count"),
        "duplicate_test_count": private_receipt.get("duplicate_test_count"),
        "unexpected_test_count": private_receipt.get(
            "unexpected_test_count"
        ),
        "unidentified_test_count": private_receipt.get(
            "unidentified_test_count"
        ),
        "malformed_test_count": private_receipt.get(
            "malformed_test_count"
        ),
        "nonterminal_test_count": private_receipt.get(
            "nonterminal_test_count"
        ),
        "exact_test_set_verified": private_receipt.get(
            "exact_test_set_verified"
        ),
        "aggregate_total_marker_present": private_receipt.get(
            "aggregate_total_marker_present"
        ),
        "aggregate_total_marker_consistent": private_receipt.get(
            "aggregate_total_marker_consistent"
        ),
        "aggregate_marker_used_as_acceptance_authority": False,
        "all_expected_tests_terminal_scoring_verified": private_receipt.get(
            "all_expected_tests_terminal_scoring_verified"
        ),
        "receipt_complete": private_receipt.get("receipt_complete"),
        "tests": public_tests,
        "blockers": list(private_receipt.get("blockers") or []),
        "release_authority": False,
        "public_safe": True,
        "raw_server_payload_included": False,
        "raw_releasefoundry_identifiers_included": False,
        "raw_payload_hashes_included": False,
        "public_case_ids_included": True,
    }
    assert_public_releasefoundry_test_terminal_receipt_safe(public)
    return public


def assert_public_releasefoundry_test_terminal_receipt_safe(payload: Any) -> None:
    """Reject public receipts containing private identifiers or secret-like data."""

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ReleaseFoundryTestReceiptError("public_receipt_non_string_key")
                if key.lower() in _PUBLIC_FORBIDDEN_KEYS:
                    raise ReleaseFoundryTestReceiptError(
                        f"public_receipt_forbidden_key:{key}"
                    )
                walk(item)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if isinstance(value, str):
            if _SECRET_OR_AUTH_PATTERN.search(value):
                raise ReleaseFoundryTestReceiptError(
                    "public_receipt_secret_or_auth_value"
                )
            if _ABSOLUTE_WINDOWS_PATH_PATTERN.match(value):
                raise ReleaseFoundryTestReceiptError(
                    "public_receipt_absolute_path_value"
                )
            if _ABSOLUTE_POSIX_PATH_PATTERN.match(value):
                raise ReleaseFoundryTestReceiptError(
                    "public_receipt_absolute_path_value"
                )

    walk(payload)


def _normalize_case_map(case_map: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(case_map, Mapping) or not case_map:
        raise ReleaseFoundryTestReceiptError("case_map_missing")
    normalized: dict[str, str] = {}
    case_ids: set[str] = set()
    for test_id, case_id in case_map.items():
        if not isinstance(test_id, str) or not test_id:
            raise ReleaseFoundryTestReceiptError("case_map_test_id_invalid")
        if not isinstance(case_id, str) or not case_id:
            raise ReleaseFoundryTestReceiptError("case_map_case_id_invalid")
        if case_id in case_ids:
            raise ReleaseFoundryTestReceiptError("case_map_case_id_duplicate")
        normalized[test_id] = case_id
        case_ids.add(case_id)
    return normalized


def _positive_int(value: Any, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ReleaseFoundryTestReceiptError(error)
    return value


def _required_identifier(value: Any, error: str) -> str | int:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or value == "":
        raise ReleaseFoundryTestReceiptError(error)
    return value


def _tests_by_id(
    tests: list[Any],
) -> tuple[dict[str, list[Mapping[str, Any]]], int, int]:
    indexed: dict[str, list[Mapping[str, Any]]] = {}
    unidentified_count = 0
    malformed_count = 0
    for test in tests:
        if not isinstance(test, Mapping):
            malformed_count += 1
            continue
        test_id = test.get("test_id")
        if isinstance(test_id, str) and test_id:
            indexed.setdefault(test_id, []).append(test)
        else:
            unidentified_count += 1
    return indexed, unidentified_count, malformed_count


def _missing_test_receipt(test_id: str, case_id: str) -> dict[str, Any]:
    return _empty_test_receipt(
        test_id=test_id,
        case_id=case_id,
        blockers=["test_missing"],
    )


def _duplicate_test_receipt(
    test_id: str,
    case_id: str,
    count: int,
) -> dict[str, Any]:
    receipt = _empty_test_receipt(
        test_id=test_id,
        case_id=case_id,
        blockers=["test_id_duplicate"],
    )
    receipt["duplicate_count"] = count
    return receipt


def _empty_test_receipt(
    *,
    test_id: str,
    case_id: str,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "test_id": test_id,
        "terminal_status": "",
        "started_at": "",
        "completed_at": "",
        "response_evidence_count": 0,
        "response_evidence_kinds": [],
        "response_evidence": [],
        "grading_signal_count": 0,
        "grading_signal_types": [],
        "terminal_status_verified": False,
        "timestamps_verified": False,
        "response_evidence_verified": False,
        "server_grading_signal_verified": False,
        "terminal_scoring_verified": False,
        "blockers": blockers,
    }


def _test_receipt(
    test: Mapping[str, Any],
    *,
    expected_test_id: str,
    case_id: str,
) -> dict[str, Any]:
    status = _normalized_status(test.get("status"))
    started_at = str(test.get("started_at") or "")
    completed_at = str(test.get("completed_at") or "")
    response_evidence = _actual_response_evidence(test)
    grading_signal_types = _backend_grading_signal_types(test)
    blockers: list[str] = []
    terminal_status_verified = status in SCORING_TERMINAL_STATUSES
    if not terminal_status_verified:
        blockers.append("test_status_not_scoring_terminal")
    timestamps_verified = _timestamps_are_ordered(started_at, completed_at)
    if not timestamps_verified:
        blockers.append("test_terminal_timestamps_missing_or_invalid")
    response_evidence_verified = bool(response_evidence)
    if not response_evidence_verified:
        blockers.append("test_response_evidence_missing")
    server_grading_signal_verified = bool(grading_signal_types)
    if not server_grading_signal_verified:
        blockers.append("test_server_grading_signal_missing")
    return {
        "case_id": case_id,
        "test_id": expected_test_id,
        "terminal_status": status,
        "started_at": started_at,
        "completed_at": completed_at,
        "response_evidence_count": len(response_evidence),
        "response_evidence_kinds": sorted(
            {item["evidence_kind"] for item in response_evidence}
        ),
        "response_evidence": response_evidence,
        "grading_signal_count": len(grading_signal_types),
        "grading_signal_types": sorted(set(grading_signal_types)),
        "terminal_status_verified": terminal_status_verified,
        "timestamps_verified": timestamps_verified,
        "response_evidence_verified": response_evidence_verified,
        "server_grading_signal_verified": server_grading_signal_verified,
        "terminal_scoring_verified": not blockers,
        "blockers": blockers,
    }


def _actual_response_evidence(
    test: Mapping[str, Any],
) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    actions = test.get("action_results")
    for action in actions if isinstance(actions, list) else []:
        if not isinstance(action, Mapping) or action.get("actor") != "agent":
            continue
        action_type = _normalized_status(action.get("action_type"))
        if action_type == "tool_call":
            calls = action.get("tool_calls")
            actual_count = 0
            for call in calls if isinstance(calls, list) else []:
                if (
                    isinstance(call, Mapping)
                    and "actual" in call
                    and _has_meaningful_json(call.get("actual"))
                ):
                    actual_count += 1
            if actual_count:
                projected.append(
                    {
                        "action_index": action.get("action_index"),
                        "action_type": action_type,
                        "evidence_kind": "tool_call_actual",
                        "actual_call_count": actual_count,
                    }
                )
            continue

        evidence_fields = [
            key
            for key in (
                "actual_response",
                "content",
                "text",
                "output_path",
                "name",
                "url",
                "media_url",
                "file_url",
                "mime_type",
                "vm_stream",
            )
            if key in action and _has_meaningful_json(action.get(key))
        ]
        if evidence_fields:
            projected.append(
                {
                    "action_index": action.get("action_index"),
                    "action_type": action_type,
                    "evidence_kind": "agent_output",
                    "evidence_fields": evidence_fields,
                }
            )
    return projected


def _has_meaningful_json(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return bool(value) and any(
            _has_meaningful_json(item) for item in value.values()
        )
    if isinstance(value, list):
        return bool(value) and any(_has_meaningful_json(item) for item in value)
    return False


def _backend_grading_signal_types(test: Mapping[str, Any]) -> list[str]:
    signals: list[str] = []
    if _valid_llm_judgment(test.get("llm_judgment")):
        signals.append("test_llm_judgment")
    actions = test.get("action_results")
    for action in actions if isinstance(actions, list) else []:
        if not isinstance(action, Mapping) or action.get("actor") != "agent":
            continue
        if _valid_llm_judgment(action.get("llm_judgment")):
            signals.append("action_llm_judgment")
        if action.get("action_type") == "tool_call":
            calls = action.get("tool_calls")
            for call in calls if isinstance(calls, list) else []:
                if not isinstance(call, Mapping):
                    continue
                if _valid_llm_judgment(call.get("llm_judgment")):
                    signals.append("tool_llm_judgment")
                if _valid_argument_comparison(call.get("argument_comparison")):
                    signals.append("tool_argument_comparison")
    if _valid_coherence(test.get("coherence")):
        signals.append("test_coherence")
    return signals


def _valid_llm_judgment(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    verdict = value.get("verdict")
    return (
        isinstance(verdict, str)
        and verdict.strip().lower() in RELEASEFOUNDRY_LLM_VERDICTS
    )


def _valid_argument_comparison(value: Any) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    status = value.get("status")
    has_current_schema = (
        isinstance(status, str)
        and status.strip().lower() in RELEASEFOUNDRY_ARGUMENT_COMPARISON_STATUSES
        and "actual_args" in value
        and isinstance(value.get("actual_args"), Mapping)
        and "expected_args" in value
        and isinstance(value.get("expected_args"), Mapping)
        and isinstance(value.get("exact_match"), bool)
    )
    if has_current_schema:
        return True
    has_legacy_schema = _LEGACY_ARGUMENT_COMPARISON_KEYS.issubset(value) and all(
        isinstance(value.get(key), (Mapping, list))
        for key in _LEGACY_ARGUMENT_COMPARISON_KEYS
    )
    return has_legacy_schema


def _valid_coherence(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    score = value.get("score")
    valid_score = (
        isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(float(score))
        and 0.0 <= float(score) <= 1.0
    )
    summary = value.get("summary")
    issues = value.get("issues")
    has_diagnostic = (
        isinstance(summary, str)
        and bool(summary.strip())
    ) or (
        isinstance(issues, list)
        and bool(issues)
    )
    return valid_score and has_diagnostic


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _timestamps_are_ordered(started_at: str, completed_at: str) -> bool:
    started = _parse_timestamp(started_at)
    completed = _parse_timestamp(completed_at)
    return started is not None and completed is not None and completed >= started


def _grading_lifecycle(
    run: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    observations: list[tuple[str, str]] = []
    for path, container in (("run", run), ("result", result)):
        if "grading_status" not in container:
            continue
        status = _normalized_status(container.get("grading_status"))
        if status:
            observations.append((f"{path}.grading_status", status))
        else:
            return {
                "grading_status": "",
                "grading_status_present": True,
                "grading_status_source_paths": [f"{path}.grading_status"],
                "grading_status_terminal_verified": False,
                "optional_grading_status_veto_passed": False,
                "blockers": ["grading_status_invalid"],
            }
    if not observations:
        return {
            "grading_status": "",
            "grading_status_present": False,
            "grading_status_source_paths": [],
            "grading_status_terminal_verified": None,
            "optional_grading_status_veto_passed": True,
            "blockers": [],
        }
    unique = {value for _, value in observations}
    if len(unique) != 1:
        return {
            "grading_status": "",
            "grading_status_present": True,
            "grading_status_source_paths": [path for path, _ in observations],
            "grading_status_terminal_verified": False,
            "optional_grading_status_veto_passed": False,
            "blockers": ["grading_status_ambiguous"],
        }
    status = next(iter(unique))
    terminal = status in OPTIONAL_GRADING_TERMINAL_STATUSES
    return {
        "grading_status": status,
        "grading_status_present": True,
        "grading_status_source_paths": [path for path, _ in observations],
        "grading_status_terminal_verified": terminal,
        "optional_grading_status_veto_passed": terminal,
        "blockers": [] if terminal else ["grading_status_not_terminal"],
    }


def _judge_version_provenance(
    run: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    expected: str,
) -> dict[str, Any]:
    expected = expected.strip() if isinstance(expected, str) else ""
    observations: list[tuple[str, str]] = []
    locations = [
        ("run", run),
        (
            "run.metadata",
            run.get("metadata")
            if isinstance(run.get("metadata"), Mapping)
            else {},
        ),
        ("result", result),
        (
            "result.metadata",
            result.get("metadata")
            if isinstance(result.get("metadata"), Mapping)
            else {},
        ),
    ]
    for prefix, location in locations:
        for key in _JUDGE_VERSION_KEYS:
            value = location.get(key)
            if isinstance(value, str) and value.strip():
                observations.append((f"{prefix}.{key}", value.strip()))

    unique = {value for _, value in observations}
    blockers: list[str] = []
    observed = ""
    source = "missing"
    verified = False
    if len(unique) > 1:
        blockers.append("judge_version_ambiguous")
        source = "server_observed_ambiguous"
    elif len(unique) == 1:
        observed = next(iter(unique))
        source = "server_observed"
        if expected and expected != observed:
            blockers.append("judge_version_mismatch")
        else:
            verified = True
    elif expected:
        blockers.append("judge_version_not_server_observed")
        source = "operator_attested_not_server_observed"
    else:
        blockers.append("judge_version_missing")

    return {
        "expected_judge_version": expected,
        "observed_judge_version": observed,
        "observed_judge_version_paths": [path for path, _ in observations],
        "judge_version_candidate_count": len(observations),
        "judge_version_source": source,
        "judge_version_verified": verified,
        "blockers": blockers,
    }


def _normalized_status(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""
