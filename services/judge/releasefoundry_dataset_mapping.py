"""Prepare a human-reviewable mapping for generated ReleaseFoundry calibration data.

ReleaseFoundry's generated dataset may preserve enough semantic content to map its six
server runs back to the fixed A2 contracts while omitting the immutable marker
and contract hash.  That is not exact identity.  This module can only produce a
machine proposal for a human reviewer; it never authorizes a paid ``create_run``
or upgrades the proposal to human adjudication.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .releasefoundry_dataset_acquisition import (
    EXPECTED_CASE_COUNT,
    EXPECTED_SERVER_DATASET_TYPE,
    CalibrationCaseContract,
    CalibrationDatasetRequest,
    DatasetAcquisitionError,
    assert_no_sensitive_material,
)
from .releasefoundry_dataset_identity import (
    CANONICALIZATION_VERSION,
    DatasetIdentityError,
    dataset_content_sha256,
)
from .result_persistence import stable_hash


PRIVATE_MAPPING_SCHEMA_VERSION = "a2.releasefoundry_dataset_mapping_review_private.v1"
PUBLIC_MAPPING_SCHEMA_VERSION = "a2.releasefoundry_dataset_mapping_receipt.v1"


@dataclass(frozen=True)
class ProposedCaseMapping:
    contract: CalibrationCaseContract
    server_slot: int
    server_run_sha256: str
    matched_anchors: tuple[str, ...]
    runner_up_match_count: int

    @property
    def matched_anchor_count(self) -> int:
        return len(self.matched_anchors)

    @property
    def margin(self) -> int:
        return self.matched_anchor_count - self.runner_up_match_count

    def private_payload(self) -> dict[str, Any]:
        return {
            "test_id": self.contract.test_id,
            "case_id": self.contract.case_id,
            "semantic_contract_sha256": self.contract.semantic_contract_sha256,
            "server_slot": self.server_slot,
            "server_run_sha256": self.server_run_sha256,
            "matched_anchors": list(self.matched_anchors),
            "matched_anchor_count": self.matched_anchor_count,
            "total_anchor_count": len(self.contract.semantic_anchors),
            "runner_up_match_count": self.runner_up_match_count,
            "assignment_margin": self.margin,
            "review": {
                "decision": "pending",
                "reviewer_id_hash": None,
                "reviewer_receipt_hash": None,
                "reviewed_at": None,
                "rationale": None,
            },
        }


@dataclass(frozen=True)
class DatasetMappingProposal:
    request_id: int
    dataset_id: int
    dataset_name: str
    dataset_content_sha256: str
    request_sha256: str
    case_contract_set_sha256: str
    mappings: tuple[ProposedCaseMapping, ...]
    best_assignment_score: int
    second_best_assignment_score: int

    @property
    def global_assignment_margin(self) -> int:
        return self.best_assignment_score - self.second_best_assignment_score

    @property
    def proposal_sha256(self) -> str:
        return stable_hash(
            {
                "request_sha256": self.request_sha256,
                "dataset_content_sha256": self.dataset_content_sha256,
                "case_contract_set_sha256": self.case_contract_set_sha256,
                "mappings": [
                    {
                        "test_id": mapping.contract.test_id,
                        "semantic_contract_sha256": (
                            mapping.contract.semantic_contract_sha256
                        ),
                        "server_slot": mapping.server_slot,
                        "server_run_sha256": mapping.server_run_sha256,
                        "matched_anchors": list(mapping.matched_anchors),
                    }
                    for mapping in self.mappings
                ],
            }
        )

    def private_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": PRIVATE_MAPPING_SCHEMA_VERSION,
            "mapping_authority": "machine_proposal_only",
            "review_state": "pending_human_review",
            "request_id": self.request_id,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "dataset_content_sha256": self.dataset_content_sha256,
            "request_sha256": self.request_sha256,
            "case_contract_set_sha256": self.case_contract_set_sha256,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "case_count": len(self.mappings),
            "best_assignment_score": self.best_assignment_score,
            "second_best_assignment_score": self.second_best_assignment_score,
            "global_assignment_margin": self.global_assignment_margin,
            "mapping_proposal_sha256": self.proposal_sha256,
            "mappings": [mapping.private_payload() for mapping in self.mappings],
            "authority_limits": {
                "exact_identity_verified": False,
                "human_adjudicated": False,
                "paid_create_run_allowed": False,
                "release_authority": False,
                "training_authority": False,
            },
        }
        assert_no_sensitive_material(payload)
        return payload

    def public_receipt(self) -> dict[str, Any]:
        matched_counts = [
            mapping.matched_anchor_count for mapping in self.mappings
        ]
        margins = [mapping.margin for mapping in self.mappings]
        receipt = {
            "schema_version": PUBLIC_MAPPING_SCHEMA_VERSION,
            "mapping_state": "machine_proposed",
            "mapping_authority": "machine_proposal_only",
            "case_count": len(self.mappings),
            "dataset_content_sha256": self.dataset_content_sha256,
            "request_sha256": self.request_sha256,
            "case_contract_set_sha256": self.case_contract_set_sha256,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "mapping_proposal_sha256": self.proposal_sha256,
            "unique_global_assignment": self.global_assignment_margin > 0,
            "global_assignment_margin": self.global_assignment_margin,
            "minimum_matched_anchor_count": min(matched_counts),
            "minimum_case_assignment_margin": min(margins),
            "human_review_required": True,
            "exact_identity_verified": False,
            "human_adjudicated": False,
            "paid_create_run_allowed": False,
            "release_authority": False,
            "training_authority": False,
            "blockers": ["human_adjudicated_mapping_required"],
            "public_safe": True,
        }
        assert_no_sensitive_material(receipt)
        return receipt


def build_dataset_mapping_proposal(
    dataset: Mapping[str, Any],
    *,
    request_id: int,
    spec: CalibrationDatasetRequest,
    forbidden_values: Sequence[str] = (),
) -> DatasetMappingProposal:
    """Build a unique one-to-one semantic proposal without granting authority."""
    assert_no_sensitive_material(dataset, forbidden_values=forbidden_values)
    if not isinstance(request_id, int) or isinstance(request_id, bool) or request_id <= 0:
        raise DatasetAcquisitionError("request_id_invalid")
    dataset_id = dataset.get("id")
    if not isinstance(dataset_id, int) or isinstance(dataset_id, bool) or dataset_id <= 0:
        raise DatasetAcquisitionError("dataset_id_invalid")
    if dataset.get("request_id") != request_id:
        raise DatasetAcquisitionError("dataset_request_id_mismatch")
    if dataset.get("name") != spec.server_dataset_name:
        raise DatasetAcquisitionError("dataset_name_mismatch")

    runs = _dataset_runs(dataset)
    contracts = tuple(spec.case_contracts)
    if len(contracts) != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("expected_case_contract_count_invalid")

    match_matrix = [
        [
            tuple(
                anchor
                for anchor in contract.semantic_anchors
                if _run_contains_anchor(run, anchor)
            )
            for run in runs
        ]
        for contract in contracts
    ]
    ranked_assignments = sorted(
        (
            (
                sum(
                    len(match_matrix[contract_index][run_index])
                    for contract_index, run_index in enumerate(permutation)
                ),
                permutation,
            )
            for permutation in itertools.permutations(range(EXPECTED_CASE_COUNT))
        ),
        key=lambda item: (-item[0], item[1]),
    )
    best_score, best_assignment = ranked_assignments[0]
    second_best_score = ranked_assignments[1][0]
    if best_score <= 0:
        raise DatasetAcquisitionError("dataset_mapping_no_semantic_overlap")
    if best_score == second_best_score:
        raise DatasetAcquisitionError("dataset_mapping_global_assignment_ambiguous")

    mappings: list[ProposedCaseMapping] = []
    for contract_index, run_index in enumerate(best_assignment):
        chosen_matches = match_matrix[contract_index][run_index]
        runner_up = max(
            len(matches)
            for candidate_index, matches in enumerate(match_matrix[contract_index])
            if candidate_index != run_index
        )
        if not chosen_matches:
            raise DatasetAcquisitionError("dataset_mapping_case_without_anchor")
        if len(chosen_matches) <= runner_up:
            raise DatasetAcquisitionError("dataset_mapping_case_assignment_ambiguous")
        mappings.append(
            ProposedCaseMapping(
                contract=contracts[contract_index],
                server_slot=run_index + 1,
                server_run_sha256=stable_hash(runs[run_index]),
                matched_anchors=chosen_matches,
                runner_up_match_count=runner_up,
            )
        )

    try:
        content_hash = dataset_content_sha256(dataset)
    except DatasetIdentityError as exc:
        raise DatasetAcquisitionError(str(exc)) from exc

    proposal = DatasetMappingProposal(
        request_id=request_id,
        dataset_id=dataset_id,
        dataset_name=spec.server_dataset_name,
        dataset_content_sha256=content_hash,
        request_sha256=spec.request_sha256,
        case_contract_set_sha256=spec.case_contract_set_sha256,
        mappings=tuple(mappings),
        best_assignment_score=best_score,
        second_best_assignment_score=second_best_score,
    )
    proposal.private_payload()
    proposal.public_receipt()
    return proposal


def blocked_mapping_receipt(
    spec: CalibrationDatasetRequest,
    *,
    blocker: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": PUBLIC_MAPPING_SCHEMA_VERSION,
        "mapping_state": "blocked",
        "mapping_authority": "none",
        "case_count": len(spec.case_contracts),
        "request_sha256": spec.request_sha256,
        "case_contract_set_sha256": spec.case_contract_set_sha256,
        "human_review_required": True,
        "exact_identity_verified": False,
        "human_adjudicated": False,
        "paid_create_run_allowed": False,
        "release_authority": False,
        "training_authority": False,
        "blockers": [blocker],
        "public_safe": True,
    }
    assert_no_sensitive_material(receipt)
    return receipt


def _dataset_runs(dataset: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    source = dataset.get("dataset_source")
    if not isinstance(source, Mapping):
        raise DatasetAcquisitionError("dataset_source_missing")
    if source.get("dataset_type") != EXPECTED_SERVER_DATASET_TYPE:
        raise DatasetAcquisitionError("dataset_type_mismatch")
    if source.get("total_runs") != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("dataset_total_runs_mismatch")
    value = source.get("runs")
    if isinstance(value, Mapping):
        runs = list(value.values())
    elif isinstance(value, list):
        runs = value
    else:
        raise DatasetAcquisitionError("dataset_runs_invalid")
    if len(runs) != EXPECTED_CASE_COUNT:
        raise DatasetAcquisitionError("dataset_run_count_mismatch")
    if any(not isinstance(run, Mapping) for run in runs):
        raise DatasetAcquisitionError("dataset_run_invalid")
    return list(runs)


def _run_contains_anchor(run: Mapping[str, Any], anchor: str) -> bool:
    return any(anchor in value for value in _string_values(run))


def _string_values(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        result: list[str] = []
        for key in sorted(value, key=str):
            result.extend(_string_values(value[key]))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_string_values(item))
        return result
    if isinstance(value, str):
        return [value]
    return []
