"""Acquire and bind the fixed six-case ReleaseFoundry calibration dataset safely.

This module deliberately separates three concerns:

* deterministic construction of the six-case generation request;
* one-shot request creation plus read-only polling and dataset discovery;
* a fail-closed gate that permits ``create_run`` only for a live dataset that
  still matches the verified private manifest.

No function retries a mutating ReleaseFoundry call. Private service identifiers are
written only under ``docs/evidence/private_refs`` (or an explicitly supplied
private root in tests).
"""

from __future__ import annotations

import hmac
import json
import math
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .releasefoundry_dataset_identity import (
    CANONICALIZATION_VERSION,
    DatasetIdentityError,
    dataset_content_sha256,
)
from .result_persistence import stable_hash


EXPECTED_CASE_COUNT = 6
REQUEST_NAME = "A2 fixed six-case calibration dataset v1"
EXPECTED_DATASET_NAME = "a2-g3-calibration"
EXPECTED_SERVER_DATASET_NAME = REQUEST_NAME
EXPECTED_SERVER_DATASET_TYPE = "multi_run_storyboard"

CASE_CONTRACT_SCHEMA_VERSION = "a2.releasefoundry_calibration_case_contract.v1"
REQUEST_SCHEMA_VERSION = "a2.releasefoundry_dataset_request.v1"
REQUEST_REF_SCHEMA_VERSION = "a2.releasefoundry_dataset_request_private.v1"
PRIVATE_MANIFEST_SCHEMA_VERSION = "a2.releasefoundry_dataset_acquisition_private.v1"
PUBLIC_RECEIPT_SCHEMA_VERSION = "a2.releasefoundry_dataset_acquisition_receipt.v1"

_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_CASE_MARKER_PATTERN = re.compile(r"\breleasefoundry-a2-g3-[a-z0-9-]+\b")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"^\\\\[^\\]+\\[^\\]+")
_POSIX_PRIVATE_PATH = re.compile(r"^/(?:Users|home|tmp|var/tmp)/")
_SIGNED_QUERY = re.compile(
    r"(?:[?&](?:X-Amz-(?:Signature|Credential)|Signature|sig|token)=)",
    re.IGNORECASE,
)
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "access_token",
    "refresh_token",
    "id_token",
    "api_token",
    "bearer_token",
    "client_secret",
    "password",
    "credential",
    "signed_url",
    "presigned_url",
)
_COMPLETED_REQUEST_STATES = frozenset({"completed"})
_FAILED_REQUEST_STATES = frozenset(
    {"failed", "cancelled", "canceled", "rejected", "expired"}
)
_PENDING_REQUEST_STATES = frozenset(
    {
        "accepted",
        "created",
        "in_progress",
        "pending",
        "processing",
        "queued",
        "running",
        "submitted",
    }
)


class DatasetAcquisitionError(ValueError):
    """Raised when fixed-dataset acquisition cannot be proved safely."""


@dataclass(frozen=True)
class CalibrationCaseContract:
    test_id: str
    case_id: str
    scenario_id: str
    title: str
    family: str
    user_task: str
    expected_behaviors: tuple[str, ...]
    policy_tool_names: tuple[str, ...]
    primary_failure_class: str
    expected_passed: bool
    expected_primary_failure_class: str
    candidate_trace_sha256: str
    semantic_contract_sha256: str

    @property
    def semantic_anchors(self) -> tuple[str, ...]:
        anchors = (
            self.scenario_id,
            self.title,
            self.family,
            self.user_task,
            *self.expected_behaviors,
            *self.policy_tool_names,
            self.primary_failure_class,
            self.expected_primary_failure_class,
        )
        return tuple(dict.fromkeys(anchor for anchor in anchors if anchor))

    def request_example(self) -> dict[str, Any]:
        return {
            "a2_case_marker": self.test_id,
            "semantic_contract_sha256": self.semantic_contract_sha256,
            "scenario_id": self.scenario_id,
            "scenario_title": self.title,
            "scenario_family": self.family,
            "user_task": self.user_task,
            "expected_behaviors": list(self.expected_behaviors),
            "policy_tool_names": list(self.policy_tool_names),
            "scenario_primary_failure_class": self.primary_failure_class,
            "candidate_expected": {
                "passed": self.expected_passed,
                "primary_failure_class": self.expected_primary_failure_class,
            },
            "candidate_trace_sha256": self.candidate_trace_sha256,
        }


@dataclass(frozen=True)
class CalibrationDatasetRequest:
    request_name: str
    dataset_name: str
    server_dataset_name: str
    request: dict[str, Any]
    request_input_schema: dict[str, Any]
    request_sha256: str
    case_contracts: tuple[CalibrationCaseContract, ...]
    case_contract_set_sha256: str

    def public_summary(self) -> dict[str, Any]:
        return {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "mode": "dry_run",
            "request_name": self.request_name,
            "dataset_name": self.dataset_name,
            "server_dataset_name": self.server_dataset_name,
            "case_count": len(self.case_contracts),
            "case_markers": [case.test_id for case in self.case_contracts],
            "request_sha256": self.request_sha256,
            "case_contract_set_sha256": self.case_contract_set_sha256,
            "mutating_calls": 0,
            "network_calls": 0,
            "public_safe": True,
        }


@dataclass(frozen=True)
class VerifiedDatasetManifest:
    request_id: int
    dataset_id: int
    dataset_name: str
    request_sha256: str
    dataset_content_sha256: str
    case_contract_set_sha256: str
    case_count: int

    def private_payload(self) -> dict[str, Any]:
        return {
            "schema_version": PRIVATE_MANIFEST_SCHEMA_VERSION,
            "verification_state": "verified",
            "request_id": self.request_id,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "request_sha256": self.request_sha256,
            "dataset_content_sha256": self.dataset_content_sha256,
            "case_contract_set_sha256": self.case_contract_set_sha256,
            "case_count": self.case_count,
            "canonicalization_version": CANONICALIZATION_VERSION,
        }


def build_calibration_dataset_request(
    *,
    root: str | Path,
    packet_path: str | Path = (
        "fixtures/a2/calibration/a2_releasefoundry_grading_collection_packet.json"
    ),
    pack_path: str | Path = "packages/scenarios/a2_g3_full_pack.json",
    case_map_path: str | Path = (
        "fixtures/a2/calibration/releasefoundry_grading_batch_case_map.json"
    ),
) -> CalibrationDatasetRequest:
    """Build and locally validate the deterministic fixed-six request."""
    repo_root = Path(root).resolve()
    packet = _read_mapping(_repo_path(repo_root, packet_path), "collection_packet")
    pack = _read_mapping(_repo_path(repo_root, pack_path), "scenario_pack")
    case_map = _read_mapping(_repo_path(repo_root, case_map_path), "case_map")

    packet_cases = packet.get("cases")
    if not isinstance(packet_cases, list) or len(packet_cases) != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("collection_packet_must_have_exactly_six_cases")
    if packet.get("case_count") != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("collection_packet_case_count_mismatch")
    if len(case_map) != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("case_map_must_have_exactly_six_cases")

    scenarios = pack.get("scenarios")
    if not isinstance(scenarios, list):
        raise DatasetAcquisitionError("scenario_pack_invalid")
    scenarios_by_id = _unique_index(scenarios, key="id", error_prefix="scenario")

    contracts: list[CalibrationCaseContract] = []
    seen_test_ids: set[str] = set()
    seen_case_ids: set[str] = set()
    seen_scenario_ids: set[str] = set()
    for packet_case in packet_cases:
        if not isinstance(packet_case, Mapping):
            raise DatasetAcquisitionError("collection_packet_case_invalid")
        test_id = _required_string(packet_case, "releasefoundry_test_id")
        case_id = _required_string(packet_case, "case_id")
        scenario_id = _required_string(packet_case, "scenario_id")
        if test_id in seen_test_ids:
            raise DatasetAcquisitionError("duplicate_releasefoundry_test_id")
        if case_id in seen_case_ids:
            raise DatasetAcquisitionError("duplicate_case_id")
        if scenario_id in seen_scenario_ids:
            raise DatasetAcquisitionError("duplicate_scenario_id")
        seen_test_ids.add(test_id)
        seen_case_ids.add(case_id)
        seen_scenario_ids.add(scenario_id)

        if not _CASE_MARKER_PATTERN.fullmatch(test_id):
            raise DatasetAcquisitionError("releasefoundry_test_id_invalid")
        if case_map.get(test_id) != case_id:
            raise DatasetAcquisitionError("case_map_binding_mismatch")

        scenario = scenarios_by_id.get(scenario_id)
        if scenario is None:
            raise DatasetAcquisitionError("scenario_not_found")
        _verify_packet_scenario_projection(packet_case, scenario)

        fixture_ref = _required_string(packet_case, "fixture_ref")
        fixture = _read_mapping(
            _repo_path(repo_root, fixture_ref),
            f"run_fixture:{case_id}",
        )
        if fixture.get("scenario_id") != scenario_id:
            raise DatasetAcquisitionError("fixture_scenario_id_mismatch")
        if fixture.get("case_id") != case_id:
            raise DatasetAcquisitionError("fixture_case_id_mismatch")
        expected = fixture.get("expected")
        if not isinstance(expected, Mapping):
            raise DatasetAcquisitionError("fixture_expected_invalid")
        packet_expected = packet_case.get("expected")
        if packet_expected != expected:
            raise DatasetAcquisitionError("fixture_expected_projection_mismatch")
        run = fixture.get("run")
        if not isinstance(run, Mapping):
            raise DatasetAcquisitionError("fixture_run_invalid")

        contract_payload = _case_contract_payload(
            test_id=test_id,
            case_id=case_id,
            scenario=scenario,
            run=run,
            expected=expected,
        )
        contract_hash = stable_hash(contract_payload)
        contracts.append(
            CalibrationCaseContract(
                test_id=test_id,
                case_id=case_id,
                scenario_id=scenario_id,
                title=_required_string(scenario, "title"),
                family=_required_string(scenario, "family"),
                user_task=_required_string(scenario, "userTask"),
                expected_behaviors=tuple(
                    _required_string_list(scenario, "expectedBehaviors")
                ),
                policy_tool_names=tuple(_policy_tool_names(scenario)),
                primary_failure_class=_required_string(
                    scenario,
                    "primaryFailureClass",
                ),
                expected_passed=_required_bool(expected, "passed"),
                expected_primary_failure_class=_required_string(
                    expected,
                    "primary_failure_class",
                ),
                candidate_trace_sha256=stable_hash(run),
                semantic_contract_sha256=contract_hash,
            )
        )

    if set(case_map) != seen_test_ids:
        raise DatasetAcquisitionError("case_map_contains_unexpected_test_ids")

    contracts.sort(key=lambda item: item.test_id)
    contract_set_hash = stable_hash(
        [
            {
                "test_id": contract.test_id,
                "semantic_contract_sha256": contract.semantic_contract_sha256,
            }
            for contract in contracts
        ]
    )
    tools = _request_tools(contracts)
    request = {
        "agent": {
            "name": "A2 calibration trace evaluator",
            "description": (
                "Evaluates fixed text and tool-execution traces for the A2 "
                "commercial-readiness calibration lane."
            ),
            "system_prompt": (
                "Generate exactly six runs: exactly one for each sample example. "
                "Never merge, omit, duplicate, or invent a case. Preserve each "
                "a2_case_marker, semantic_contract_sha256, scenario_id, title, "
                "family, user_task, expected behavior, tool name, and failure "
                "class verbatim in that run's stable text fields. These are "
                "trace-level calibration cases; do not claim that text "
                "descriptions are native image, audio, video, or file evidence."
            ),
            "tools": tools,
            "accepted_inputs": {
                "text": True,
                "audio": False,
                "file": False,
                "image": False,
                "video": False,
                "conversation": False,
            },
            "output_format": {"type": "text"},
        },
        "context": {
            "domain": "AI agent evaluation and release safety",
            "use_case": (
                "Generate an immutable six-case calibration dataset for action, "
                "answer, safety, recovery, clarification, and trace-grounding "
                "judgment."
            ),
            "scenario_context": (
                "Every generated run must retain one and only one fixed A2 case "
                f"contract. Contract set: {contract_set_hash}."
            ),
            "sample_data": {
                "schema_version": REQUEST_SCHEMA_VERSION,
                "examples": [contract.request_example() for contract in contracts],
            },
        },
        "generation_options": {
            "scenario_count": EXPECTED_CASE_COUNT,
            "generate_audio": False,
            "generate_files": False,
            "generate_images": False,
            "generate_videos": False,
            "generate_simulations": False,
        },
        "test_config": {
            "num_variations": EXPECTED_CASE_COUNT,
            "strategy": "focused",
            "coverage": {
                "happy_path": True,
                "edge_cases": True,
                "error_handling": True,
            },
        },
        "metadata": {
            "dataset_name": EXPECTED_DATASET_NAME,
            "description": (
                "Fixed six-case A2 C3 calibration dataset; identity is accepted "
                "only after request binding, semantic contracts, and content "
                "hash are verified."
            ),
        },
    }
    request_input_schema = {
        "type": "object",
        "properties": {},
        "tools": tools,
    }
    request_hash = stable_hash(
        {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "request_name": REQUEST_NAME,
            "dataset_name": EXPECTED_DATASET_NAME,
            "request": request,
            "request_input_schema": request_input_schema,
        }
    )
    spec = CalibrationDatasetRequest(
        request_name=REQUEST_NAME,
        dataset_name=EXPECTED_DATASET_NAME,
        server_dataset_name=EXPECTED_SERVER_DATASET_NAME,
        request=request,
        request_input_schema=request_input_schema,
        request_sha256=request_hash,
        case_contracts=tuple(contracts),
        case_contract_set_sha256=contract_set_hash,
    )
    assert_no_sensitive_material(spec.public_summary())
    assert_no_sensitive_material(request)
    assert_no_sensitive_material(request_input_schema)
    return spec


def create_request_once(client: Any, spec: CalibrationDatasetRequest) -> int:
    """Call the official mutating endpoint exactly once and return its ID."""
    response = client.create_request(
        request_name=spec.request_name,
        request=spec.request,
        request_input_schema=spec.request_input_schema,
    )
    if not isinstance(response, Mapping):
        raise DatasetAcquisitionError("create_request_response_invalid")
    return _positive_int(response.get("id"), "request_id_invalid")


def wait_for_request_terminal(
    client: Any,
    request_id: int,
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, Any]:
    """Poll a request with a monotonic deadline and fail on unknown states."""
    request_id = _positive_int(request_id, "request_id_invalid")
    timeout_seconds = _positive_number(timeout_seconds, "request_timeout_invalid")
    poll_interval_seconds = _positive_number(
        poll_interval_seconds,
        "request_poll_interval_invalid",
    )
    deadline = monotonic() + timeout_seconds

    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise DatasetAcquisitionError("request_poll_timeout")
        response = _call_with_remaining_timeout(
            client,
            "get_request",
            remaining,
            request_id,
        )
        if not isinstance(response, Mapping):
            raise DatasetAcquisitionError("get_request_response_invalid")
        observed_id = response.get("id")
        if observed_id is not None and observed_id != request_id:
            raise DatasetAcquisitionError("get_request_id_mismatch")
        status = _request_status(response)
        if status in _COMPLETED_REQUEST_STATES:
            return response
        if status in _FAILED_REQUEST_STATES:
            raise DatasetAcquisitionError(f"request_terminal_failure:{status}")
        if status not in _PENDING_REQUEST_STATES:
            raise DatasetAcquisitionError(f"request_status_unknown:{status}")

        remaining = deadline - monotonic()
        if remaining <= 0:
            raise DatasetAcquisitionError("request_poll_timeout")
        sleep(min(poll_interval_seconds, remaining))


def find_single_dataset_for_request(
    client: Any,
    request_id: int,
    *,
    page_limit: int = 50,
    max_pages: int = 100,
    forbidden_values: Sequence[str] = (),
) -> Mapping[str, Any]:
    """Page every dataset and return the sole exact request-ID match."""
    request_id = _positive_int(request_id, "request_id_invalid")
    if not isinstance(page_limit, int) or isinstance(page_limit, bool) or page_limit <= 0:
        raise DatasetAcquisitionError("dataset_page_limit_invalid")
    if not isinstance(max_pages, int) or isinstance(max_pages, bool) or max_pages <= 0:
        raise DatasetAcquisitionError("dataset_max_pages_invalid")

    cursor: int | None = None
    seen_cursors: set[int] = set()
    matches: list[Mapping[str, Any]] = []
    for _ in range(max_pages):
        response = client.list_datasets(
            limit=page_limit,
            cursor=cursor,
            include_signed_urls=False,
        )
        if not isinstance(response, Mapping):
            raise DatasetAcquisitionError("dataset_list_response_invalid")
        assert_no_sensitive_material(
            response,
            forbidden_values=forbidden_values,
        )
        datasets = response.get("datasets")
        if not isinstance(datasets, list):
            raise DatasetAcquisitionError("dataset_list_invalid")
        for dataset in datasets:
            if not isinstance(dataset, Mapping):
                raise DatasetAcquisitionError("dataset_list_item_invalid")
            if dataset.get("request_id") == request_id:
                matches.append(dataset)

        next_cursor = response.get("next_cursor")
        if next_cursor is None:
            break
        next_cursor = _positive_int(next_cursor, "dataset_next_cursor_invalid")
        if next_cursor in seen_cursors or next_cursor == cursor:
            raise DatasetAcquisitionError("dataset_cursor_loop")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    else:
        raise DatasetAcquisitionError("dataset_page_limit_exceeded")

    if not matches:
        raise DatasetAcquisitionError("request_dataset_not_found")
    if len(matches) != 1:
        raise DatasetAcquisitionError("request_dataset_ambiguous")
    return matches[0]


def fetch_and_verify_dataset(
    client: Any,
    *,
    request_id: int,
    spec: CalibrationDatasetRequest,
    forbidden_values: Sequence[str] = (),
) -> tuple[VerifiedDatasetManifest, dict[str, Any]]:
    """Discover, fetch, and strictly verify the generated six-case dataset."""
    listed = find_single_dataset_for_request(
        client,
        request_id,
        forbidden_values=forbidden_values,
    )
    dataset_id = _positive_int(listed.get("id"), "dataset_id_invalid")
    dataset = client.get_dataset(dataset_id, include_signed_urls=False)
    if not isinstance(dataset, Mapping):
        raise DatasetAcquisitionError("get_dataset_response_invalid")
    if _positive_int(dataset.get("id"), "dataset_id_invalid") != dataset_id:
        raise DatasetAcquisitionError("get_dataset_id_mismatch")
    manifest = verify_calibration_dataset(
        dataset,
        request_id=request_id,
        spec=spec,
        forbidden_values=forbidden_values,
    )
    receipt = public_verification_receipt(manifest)
    return manifest, receipt


def verify_calibration_dataset(
    dataset: Mapping[str, Any],
    *,
    request_id: int,
    spec: CalibrationDatasetRequest,
    forbidden_values: Sequence[str] = (),
) -> VerifiedDatasetManifest:
    """Verify request binding, exact name, six contracts, and content hash."""
    request_id = _positive_int(request_id, "request_id_invalid")
    assert_no_sensitive_material(
        dataset,
        forbidden_values=forbidden_values,
    )
    dataset_id = _positive_int(dataset.get("id"), "dataset_id_invalid")
    if dataset.get("request_id") != request_id:
        raise DatasetAcquisitionError("dataset_request_id_mismatch")
    observed_name = dataset.get("name")
    if not isinstance(observed_name, str) or not hmac.compare_digest(
        observed_name,
        spec.server_dataset_name,
    ):
        raise DatasetAcquisitionError("dataset_name_mismatch")
    verify_dataset_case_contracts(dataset, spec.case_contracts)
    try:
        content_hash = dataset_content_sha256(dataset)
    except DatasetIdentityError as exc:
        raise DatasetAcquisitionError(str(exc)) from exc
    return VerifiedDatasetManifest(
        request_id=request_id,
        dataset_id=dataset_id,
        dataset_name=spec.server_dataset_name,
        request_sha256=spec.request_sha256,
        dataset_content_sha256=content_hash,
        case_contract_set_sha256=spec.case_contract_set_sha256,
        case_count=len(spec.case_contracts),
    )


def verify_dataset_case_contracts(
    dataset: Mapping[str, Any],
    contracts: Sequence[CalibrationCaseContract],
) -> None:
    """Require one exact marker and semantic contract per source run."""
    if len(contracts) != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("expected_case_contract_count_invalid")
    dataset_source = dataset.get("dataset_source")
    if not isinstance(dataset_source, Mapping):
        raise DatasetAcquisitionError("dataset_source_missing")
    if dataset_source.get("dataset_type") != EXPECTED_SERVER_DATASET_TYPE:
        raise DatasetAcquisitionError("dataset_type_mismatch")
    if dataset_source.get("total_runs") != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("dataset_total_runs_mismatch")
    source_runs = dataset_source.get("runs")
    if isinstance(source_runs, Mapping):
        runs = list(source_runs.values())
    elif isinstance(source_runs, list):
        runs = source_runs
    else:
        raise DatasetAcquisitionError("dataset_runs_invalid")
    if len(runs) != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("dataset_run_count_mismatch")
    if any(not isinstance(run, Mapping) for run in runs):
        raise DatasetAcquisitionError("dataset_run_invalid")

    contracts_by_marker = {contract.test_id: contract for contract in contracts}
    if len(contracts_by_marker) != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("case_contract_marker_duplicate")
    expected_markers = set(contracts_by_marker)
    expected_hashes = {
        contract.semantic_contract_sha256 for contract in contracts
    }
    observed_markers: list[str] = []
    for run in runs:
        strings = tuple(_string_values(run))
        marker_tokens = {
            token
            for text in strings
            for token in _CASE_MARKER_PATTERN.findall(text)
        }
        unexpected = marker_tokens - expected_markers
        if unexpected:
            raise DatasetAcquisitionError("dataset_run_unexpected_case_marker")
        matched_markers = marker_tokens & expected_markers
        if not matched_markers:
            raise DatasetAcquisitionError("dataset_run_case_marker_missing")
        if len(matched_markers) != 1:
            raise DatasetAcquisitionError("dataset_run_case_marker_mixed")
        marker = next(iter(matched_markers))
        contract = contracts_by_marker[marker]

        matched_hashes = {
            contract_hash
            for contract_hash in expected_hashes
            if any(contract_hash in text for text in strings)
        }
        if contract.semantic_contract_sha256 not in matched_hashes:
            raise DatasetAcquisitionError("dataset_run_contract_hash_missing")
        if matched_hashes != {contract.semantic_contract_sha256}:
            raise DatasetAcquisitionError("dataset_run_contract_hash_mixed")
        for anchor in contract.semantic_anchors:
            if not any(anchor in text for text in strings):
                raise DatasetAcquisitionError(
                    f"dataset_run_semantic_anchor_missing:{marker}"
                )
        actions = run.get("actions")
        if not isinstance(actions, list) or not actions:
            raise DatasetAcquisitionError("dataset_run_actions_missing")
        observed_markers.append(marker)

    if len(set(observed_markers)) != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("dataset_run_case_marker_duplicate")
    if set(observed_markers) != expected_markers:
        raise DatasetAcquisitionError("dataset_run_case_marker_set_mismatch")


def public_verification_receipt(
    manifest: VerifiedDatasetManifest,
) -> dict[str, Any]:
    """Return a receipt without raw ReleaseFoundry request or dataset identifiers."""
    receipt = {
        "schema_version": PUBLIC_RECEIPT_SCHEMA_VERSION,
        "verification_state": "verified",
        "request_status": "completed",
        "request_identity_exact_match": True,
        "dataset_request_binding_exact_match": True,
        "dataset_name_exact_match": True,
        "dataset_content_sha256_exact_match": True,
        "six_case_contracts_exact_match": True,
        "request_sha256": manifest.request_sha256,
        "dataset_content_sha256": manifest.dataset_content_sha256,
        "case_contract_set_sha256": manifest.case_contract_set_sha256,
        "case_count": manifest.case_count,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "paid_create_run_allowed": True,
        "release_authority": False,
        "blockers": [],
        "public_safe": True,
    }
    assert_no_sensitive_material(receipt)
    return receipt


def blocked_public_receipt(
    spec: CalibrationDatasetRequest,
    *,
    blocker: str,
    phase: str,
) -> dict[str, Any]:
    """Build a public-safe fail-closed receipt after an acquisition failure."""
    receipt = {
        "schema_version": PUBLIC_RECEIPT_SCHEMA_VERSION,
        "verification_state": "blocked",
        "phase": phase,
        "case_count": len(spec.case_contracts),
        "request_sha256": spec.request_sha256,
        "case_contract_set_sha256": spec.case_contract_set_sha256,
        "paid_create_run_allowed": False,
        "release_authority": False,
        "blockers": [blocker],
        "public_safe": True,
    }
    assert_no_sensitive_material(receipt)
    return receipt


def write_request_ref(
    path: str | Path,
    *,
    private_root: str | Path,
    request_id: int,
    spec: CalibrationDatasetRequest,
) -> Path:
    payload = {
        "schema_version": REQUEST_REF_SCHEMA_VERSION,
        "request_id": _positive_int(request_id, "request_id_invalid"),
        "request_name": spec.request_name,
        "request_sha256": spec.request_sha256,
        "case_contract_set_sha256": spec.case_contract_set_sha256,
    }
    assert_no_sensitive_material(payload)
    return atomic_write_private_json(path, payload, private_root=private_root)


def load_request_ref(
    path: str | Path,
    *,
    private_root: str | Path,
    spec: CalibrationDatasetRequest,
) -> int:
    private_path = validated_private_path(path, private_root=private_root)
    payload = _read_mapping(private_path, "request_ref")
    if payload.get("schema_version") != REQUEST_REF_SCHEMA_VERSION:
        raise DatasetAcquisitionError("request_ref_schema_unsupported")
    if payload.get("request_name") != spec.request_name:
        raise DatasetAcquisitionError("request_ref_name_mismatch")
    if payload.get("request_sha256") != spec.request_sha256:
        raise DatasetAcquisitionError("request_ref_hash_mismatch")
    if payload.get("case_contract_set_sha256") != spec.case_contract_set_sha256:
        raise DatasetAcquisitionError("request_ref_contract_set_mismatch")
    assert_no_sensitive_material(payload)
    return _positive_int(payload.get("request_id"), "request_id_invalid")


def write_verified_manifest(
    path: str | Path,
    manifest: VerifiedDatasetManifest,
    *,
    private_root: str | Path,
) -> Path:
    payload = manifest.private_payload()
    assert_no_sensitive_material(payload)
    return atomic_write_private_json(path, payload, private_root=private_root)


def load_verified_manifest(
    path: str | Path,
    *,
    private_root: str | Path,
) -> VerifiedDatasetManifest:
    private_path = validated_private_path(path, private_root=private_root)
    payload = _read_mapping(private_path, "verified_dataset_manifest")
    if payload.get("schema_version") != PRIVATE_MANIFEST_SCHEMA_VERSION:
        raise DatasetAcquisitionError("verified_manifest_schema_unsupported")
    if payload.get("verification_state") != "verified":
        raise DatasetAcquisitionError("verified_manifest_state_invalid")
    if payload.get("canonicalization_version") != CANONICALIZATION_VERSION:
        raise DatasetAcquisitionError("verified_manifest_canonicalization_stale")
    manifest = VerifiedDatasetManifest(
        request_id=_positive_int(payload.get("request_id"), "request_id_invalid"),
        dataset_id=_positive_int(payload.get("dataset_id"), "dataset_id_invalid"),
        dataset_name=_required_string(payload, "dataset_name"),
        request_sha256=_required_sha256(payload, "request_sha256"),
        dataset_content_sha256=_required_sha256(
            payload,
            "dataset_content_sha256",
        ),
        case_contract_set_sha256=_required_sha256(
            payload,
            "case_contract_set_sha256",
        ),
        case_count=_positive_int(payload.get("case_count"), "case_count_invalid"),
    )
    assert_no_sensitive_material(payload)
    return manifest


def assert_paid_run_allowed(
    manifest: VerifiedDatasetManifest,
    *,
    live_dataset: Mapping[str, Any],
    spec: CalibrationDatasetRequest,
    forbidden_values: Sequence[str] = (),
) -> int:
    """Return the explicit dataset ID only when every live binding still holds."""
    if manifest.request_sha256 != spec.request_sha256:
        raise DatasetAcquisitionError("paid_gate_request_hash_mismatch")
    if manifest.case_contract_set_sha256 != spec.case_contract_set_sha256:
        raise DatasetAcquisitionError("paid_gate_contract_set_mismatch")
    if manifest.dataset_name != spec.server_dataset_name:
        raise DatasetAcquisitionError("paid_gate_dataset_name_mismatch")
    if manifest.case_count != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("paid_gate_case_count_mismatch")

    observed = verify_calibration_dataset(
        live_dataset,
        request_id=manifest.request_id,
        spec=spec,
        forbidden_values=forbidden_values,
    )
    if observed.dataset_id != manifest.dataset_id:
        raise DatasetAcquisitionError("paid_gate_dataset_id_mismatch")
    if not hmac.compare_digest(
        observed.dataset_content_sha256,
        manifest.dataset_content_sha256,
    ):
        raise DatasetAcquisitionError("paid_gate_dataset_content_mismatch")
    return manifest.dataset_id


def create_run_once_with_verified_identity(
    client: Any,
    *,
    manifest_path: str | Path,
    private_root: str | Path,
    spec: CalibrationDatasetRequest,
    result: dict[str, Any],
    forbidden_values: Sequence[str] = (),
) -> Any:
    """Fetch identity once, then issue one non-retried paid ``create_run``."""
    manifest = load_verified_manifest(
        manifest_path,
        private_root=private_root,
    )
    if manifest.request_sha256 != spec.request_sha256:
        raise DatasetAcquisitionError("paid_gate_request_hash_mismatch")
    if manifest.case_contract_set_sha256 != spec.case_contract_set_sha256:
        raise DatasetAcquisitionError("paid_gate_contract_set_mismatch")
    if manifest.dataset_name != spec.server_dataset_name:
        raise DatasetAcquisitionError("paid_gate_dataset_name_mismatch")
    if manifest.case_count != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("paid_gate_case_count_mismatch")

    live_dataset = client.get_dataset(
        manifest.dataset_id,
        include_signed_urls=False,
    )
    if not isinstance(live_dataset, Mapping):
        raise DatasetAcquisitionError("get_dataset_response_invalid")
    dataset_id = assert_paid_run_allowed(
        manifest,
        live_dataset=live_dataset,
        spec=spec,
        forbidden_values=forbidden_values,
    )
    return client.create_run(dataset_id=dataset_id, result=result)


def validated_private_path(
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
        raise DatasetAcquisitionError("private_path_outside_private_root") from exc
    if candidate == root:
        raise DatasetAcquisitionError("private_path_must_be_file")
    return candidate


def atomic_write_private_json(
    path: str | Path,
    payload: Mapping[str, Any],
    *,
    private_root: str | Path,
) -> Path:
    destination = validated_private_path(path, private_root=private_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return _atomic_write_json(destination, payload)


def atomic_write_public_json(
    path: str | Path,
    payload: Mapping[str, Any],
) -> Path:
    assert_no_sensitive_material(payload)
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    return _atomic_write_json(destination, payload)


def assert_no_sensitive_material(
    payload: Any,
    *,
    forbidden_values: Sequence[str] = (),
) -> None:
    """Reject sensitive keys, signed URLs, paths, and exact live secrets.

    Synthetic secret-looking strings are valid security-test evidence. Live
    callers must pass the actual in-memory credentials as ``forbidden_values``
    so exact credential material is still rejected without persisting it.
    """
    exact_forbidden_values = _validated_forbidden_values(forbidden_values)
    walked = _walk_json(payload)
    if isinstance(payload, str):
        walked.insert(0, ((), payload))
    for location, value in walked:
        if location:
            normalized_key = location[-1].lower().replace("-", "_")
            if any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
                raise DatasetAcquisitionError(
                    f"sensitive_key_detected:{'.'.join(location)}"
                )
        if not isinstance(value, str):
            continue
        if _WINDOWS_ABSOLUTE_PATH.match(value):
            raise DatasetAcquisitionError("absolute_path_detected")
        if _UNC_PATH.match(value) or _POSIX_PRIVATE_PATH.match(value):
            raise DatasetAcquisitionError("absolute_path_detected")
        if _SIGNED_QUERY.search(value):
            raise DatasetAcquisitionError("signed_url_detected")
        if any(secret in value for secret in exact_forbidden_values):
            raise DatasetAcquisitionError("forbidden_value_detected")


def _validated_forbidden_values(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DatasetAcquisitionError("forbidden_values_invalid")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise DatasetAcquisitionError("forbidden_value_invalid")
        normalized.append(value)
    return tuple(dict.fromkeys(normalized))


def _case_contract_payload(
    *,
    test_id: str,
    case_id: str,
    scenario: Mapping[str, Any],
    run: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": CASE_CONTRACT_SCHEMA_VERSION,
        "test_id": test_id,
        "case_id": case_id,
        "scenario": {
            "id": _required_string(scenario, "id"),
            "title": _required_string(scenario, "title"),
            "family": _required_string(scenario, "family"),
            "user_task": _required_string(scenario, "userTask"),
            "expected_behaviors": _required_string_list(
                scenario,
                "expectedBehaviors",
            ),
            "tool_policy": scenario.get("toolPolicy"),
            "primary_failure_class": _required_string(
                scenario,
                "primaryFailureClass",
            ),
        },
        "candidate_trace_sha256": stable_hash(run),
        "candidate_expected": {
            "passed": _required_bool(expected, "passed"),
            "primary_failure_class": _required_string(
                expected,
                "primary_failure_class",
            ),
        },
    }


def _verify_packet_scenario_projection(
    packet_case: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> None:
    exact_fields = {
        "scenario_title": scenario.get("title"),
        "scenario_family": scenario.get("family"),
        "user_task": scenario.get("userTask"),
        "expected_behaviors": scenario.get("expectedBehaviors"),
    }
    for packet_key, expected in exact_fields.items():
        if packet_case.get(packet_key) != expected:
            raise DatasetAcquisitionError(
                f"collection_packet_scenario_projection_mismatch:{packet_key}"
            )


def _policy_tool_names(scenario: Mapping[str, Any]) -> list[str]:
    policy = scenario.get("toolPolicy")
    if not isinstance(policy, Mapping):
        raise DatasetAcquisitionError("scenario_tool_policy_invalid")
    names: set[str] = set()
    for lane in ("required", "optional", "forbidden"):
        items = policy.get(lane)
        if not isinstance(items, list):
            raise DatasetAcquisitionError("scenario_tool_policy_lane_invalid")
        for item in items:
            if not isinstance(item, Mapping):
                raise DatasetAcquisitionError("scenario_tool_policy_item_invalid")
            name = item.get("tool")
            if not isinstance(name, str) or not name:
                raise DatasetAcquisitionError("scenario_tool_name_invalid")
            if name != "*":
                names.add(name)
    order = policy.get("order")
    if not isinstance(order, list):
        raise DatasetAcquisitionError("scenario_tool_policy_order_invalid")
    for item in order:
        if not isinstance(item, Mapping):
            raise DatasetAcquisitionError("scenario_tool_order_item_invalid")
        for key in ("before", "after"):
            value = item.get(key)
            if not isinstance(value, str) or not value:
                raise DatasetAcquisitionError("scenario_tool_order_name_invalid")
            names.add(value)
    return sorted(names)


def _request_tools(
    contracts: Sequence[CalibrationCaseContract],
) -> list[dict[str, Any]]:
    names = sorted(
        {
            tool_name
            for contract in contracts
            for tool_name in contract.policy_tool_names
        }
    )
    return [
        {
            "name": name,
            "description": (
                f"Exact A2 calibration tool contract for {name}; arguments and "
                "ordering are evaluated from the supplied trace."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            },
        }
        for name in names
    ]


def _request_status(response: Mapping[str, Any]) -> str:
    value = response.get("request_status")
    if value is None:
        value = response.get("status")
    if not isinstance(value, str) or not value.strip():
        raise DatasetAcquisitionError("request_status_missing")
    return value.strip().lower()


def _call_with_remaining_timeout(
    client: Any,
    method_name: str,
    remaining_seconds: float,
    *args: Any,
) -> Any:
    method = getattr(client, method_name)
    if not hasattr(client, "timeout"):
        return method(*args)
    original_timeout = client.timeout
    try:
        bounded = max(1, math.ceil(remaining_seconds))
        if isinstance(original_timeout, (int, float)) and original_timeout > 0:
            bounded = min(bounded, original_timeout)
        client.timeout = bounded
        return method(*args)
    finally:
        client.timeout = original_timeout


def _read_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetAcquisitionError(f"{label}_unreadable") from exc
    if not isinstance(payload, dict):
        raise DatasetAcquisitionError(f"{label}_invalid")
    return payload


def _repo_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise DatasetAcquisitionError("repository_path_escape") from exc
    return path


def _unique_index(
    items: Sequence[Any],
    *,
    key: str,
    error_prefix: str,
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            raise DatasetAcquisitionError(f"{error_prefix}_item_invalid")
        value = _required_string(item, key)
        if value in indexed:
            raise DatasetAcquisitionError(f"{error_prefix}_{key}_duplicate")
        indexed[value] = item
    return indexed


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise DatasetAcquisitionError(f"{key}_invalid")
    return value


def _required_string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise DatasetAcquisitionError(f"{key}_invalid")
    result = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise DatasetAcquisitionError(f"{key}_invalid")
        result.append(item)
    return result


def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise DatasetAcquisitionError(f"{key}_invalid")
    return value


def _required_sha256(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise DatasetAcquisitionError(f"{key}_invalid")
    return value


def _positive_int(value: Any, error: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DatasetAcquisitionError(error)
    return value


def _positive_number(value: Any, error: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise DatasetAcquisitionError(error)
    return float(value)


def _string_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                values.append(key)
            values.extend(_string_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_string_values(item))
    elif isinstance(value, str):
        values.append(value)
    return values


def _walk_json(
    value: Any,
    location: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], Any]]:
    walked: list[tuple[tuple[str, ...], Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            child_location = (*location, key_text)
            walked.append((child_location, item))
            walked.extend(_walk_json(item, child_location))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_location = (*location, str(index))
            walked.append((child_location, item))
            walked.extend(_walk_json(item, child_location))
    return walked


def _atomic_write_json(
    destination: Path,
    payload: Mapping[str, Any],
) -> Path:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return destination
