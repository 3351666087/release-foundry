"""Public, hash-bound A2 judge contract for downstream consumers such as A3."""

from __future__ import annotations

from typing import Any

from .release_actions import (
    CANONICAL_RELEASE_ACTIONS,
    RELEASE_ACTION_ALIASES,
)
from .result_persistence import stable_hash
from .unified_label import (
    SCHEMA_VERSION as UNIFIED_LABEL_SCHEMA_VERSION,
    VALID_FAILURE_CLASSES,
)


SCHEMA_VERSION = "a2.judge_consumer_contract.v1"
CONSUMER_REQUIRED_LABEL_FIELDS = (
    "schema_version",
    "label_id",
    "case_id",
    "modality",
    "label",
    "passed",
    "failure_type",
    "failure_types",
    "severity",
    "failed_action",
    "evidence_locations",
    "confidence",
    "failure_probability",
    "calibrated_failure_probability",
    "probability_calibration",
    "release_recommendation",
    "reason",
    "judge_id",
    "judge_version",
    "model_version",
    "prompt_version",
    "input_hash",
    "output_hash",
    "evidence_hash",
    "metadata",
    "label_hash",
)


class JudgeConsumerContractError(ValueError):
    """Raised when a persisted consumer contract is invalid or stale."""


def build_judge_consumer_contract() -> dict[str, Any]:
    """Build the deterministic A2 wire contract exposed to downstream systems."""
    release_actions = [
        {
            "id": action,
            "accepted_aliases": sorted(
                alias
                for alias, canonical in RELEASE_ACTION_ALIASES.items()
                if canonical == action
            ),
        }
        for action in CANONICAL_RELEASE_ACTIONS
    ]
    contract = {
        "schema_version": SCHEMA_VERSION,
        "producer": "a2",
        "consumer_boundary": "judge_result",
        "unified_label": {
            "schema_version": UNIFIED_LABEL_SCHEMA_VERSION,
            "required_fields": list(CONSUMER_REQUIRED_LABEL_FIELDS),
        },
        "release_actions": release_actions,
        "release_action_policy": {
            "canonical_output_only": True,
            "unknown_input": "fail_closed",
        },
        "failure_types": sorted(VALID_FAILURE_CLASSES),
        "failure_type_source": (
            "services.judge.unified_label.VALID_FAILURE_CLASSES"
        ),
        "data_boundary": {
            "public_safe_only": True,
            "raw_input_required": False,
            "raw_output_required": False,
            "raw_evidence_required": False,
            "private_evidence_required": False,
            "structured_evidence_locations_required": True,
        },
        "metadata": {
            "deterministic": True,
            "requires_network": False,
            "requires_releasefoundry_api_key": False,
        },
    }
    return {**contract, "contract_hash": stable_hash(contract)}


def verify_judge_consumer_contract(contract: dict[str, Any]) -> None:
    """Verify the self-hash and exact current contract payload."""
    if not isinstance(contract, dict):
        raise JudgeConsumerContractError("contract_must_be_object")
    if contract.get("schema_version") != SCHEMA_VERSION:
        raise JudgeConsumerContractError("unsupported_schema_version")
    declared_hash = contract.get("contract_hash")
    if not isinstance(declared_hash, str):
        raise JudgeConsumerContractError("contract_hash_missing")
    payload = {
        key: value
        for key, value in contract.items()
        if key != "contract_hash"
    }
    if stable_hash(payload) != declared_hash:
        raise JudgeConsumerContractError("contract_hash_mismatch")
    if contract != build_judge_consumer_contract():
        raise JudgeConsumerContractError("contract_payload_mismatch")
