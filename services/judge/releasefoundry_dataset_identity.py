"""Fail-closed identity binding for paid ReleaseFoundry calibration datasets."""

from __future__ import annotations

import hmac
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .result_persistence import stable_hash


PRIVATE_MANIFEST_SCHEMA_VERSION = "a2.releasefoundry_dataset_identity_private.v1"
CANONICAL_CONTENT_SCHEMA_VERSION = "a2.releasefoundry_dataset_content.v1"
RECEIPT_SCHEMA_VERSION = "a2.releasefoundry_dataset_identity_receipt.v1"
CANONICALIZATION_VERSION = "dataset-source-json-v1"

_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_TRANSIENT_SIGNED_URL_KEYS = frozenset(
    {
        "presigned_url",
        "presigned_urls",
        "signed_url",
        "signed_urls",
        "url_expires_at",
        "url_expires_seconds",
    }
)


class DatasetIdentityError(ValueError):
    """Raised when an ReleaseFoundry dataset cannot be bound to one immutable identity."""


@dataclass(frozen=True)
class DatasetIdentityExpectation:
    dataset_id: int
    dataset_name: str
    dataset_content_sha256: str

    def private_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": PRIVATE_MANIFEST_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "dataset_name": self.dataset_name,
            "dataset_content_sha256": self.dataset_content_sha256,
        }


@dataclass(frozen=True)
class VerifiedDatasetIdentityBinding:
    """A private dataset pin bound to one verified public ReleaseFoundry receipt."""

    expectation: DatasetIdentityExpectation
    identity_manifest_sha256: str
    identity_receipt_sha256: str
    content_collection: str
    content_item_count: int


def load_dataset_identity_manifest(path: str | Path) -> DatasetIdentityExpectation:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetIdentityError("dataset_identity_manifest_unreadable") from exc
    if not isinstance(payload, dict):
        raise DatasetIdentityError("dataset_identity_manifest_invalid")
    if payload.get("schema_version") != PRIVATE_MANIFEST_SCHEMA_VERSION:
        raise DatasetIdentityError("dataset_identity_manifest_schema_unsupported")
    return _expectation(
        dataset_id=payload.get("dataset_id"),
        dataset_name=payload.get("dataset_name"),
        dataset_content_sha256=payload.get("dataset_content_sha256"),
    )


def load_verified_dataset_identity_binding(
    receipt_path: str | Path,
    identity_manifest_path: str | Path,
) -> VerifiedDatasetIdentityBinding:
    """Fail closed unless a public receipt binds the current private pin."""
    manifest_path = Path(identity_manifest_path)
    expectation = load_dataset_identity_manifest(manifest_path)
    receipt_target = Path(receipt_path)
    try:
        receipt = json.loads(receipt_target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetIdentityError("dataset_identity_receipt_unreadable") from exc
    if not isinstance(receipt, dict):
        raise DatasetIdentityError("dataset_identity_receipt_invalid")
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        raise DatasetIdentityError("dataset_identity_receipt_schema_unsupported")
    if receipt.get("verification_state") != "verified":
        raise DatasetIdentityError("dataset_identity_receipt_not_verified")
    if receipt.get("canonicalization_version") != CANONICALIZATION_VERSION:
        raise DatasetIdentityError("dataset_identity_canonicalization_unsupported")
    for field in (
        "dataset_id_exact_match",
        "dataset_name_exact_match",
        "dataset_content_sha256_exact_match",
        "public_safe",
    ):
        if receipt.get(field) is not True:
            raise DatasetIdentityError(f"dataset_identity_receipt_{field}_invalid")
    if receipt.get("release_authority") is not False:
        raise DatasetIdentityError(
            "dataset_identity_receipt_release_authority_invalid"
        )
    if receipt.get("blockers") != []:
        raise DatasetIdentityError("dataset_identity_receipt_blocked")
    if receipt.get("binding_action") not in {
        "pinned_and_verified",
        "verified_existing_pin",
    }:
        raise DatasetIdentityError("dataset_identity_binding_action_invalid")

    manifest_sha256 = _sha256_file(manifest_path)
    if not _hashes_match(receipt.get("identity_manifest_sha256"), manifest_sha256):
        raise DatasetIdentityError("dataset_identity_manifest_sha256_mismatch")
    if not _hashes_match(
        receipt.get("dataset_id_hash"),
        stable_hash({"dataset_id": expectation.dataset_id}),
    ):
        raise DatasetIdentityError("dataset_identity_id_hash_mismatch")
    if not _hashes_match(
        receipt.get("dataset_name_hash"),
        stable_hash({"dataset_name": expectation.dataset_name}),
    ):
        raise DatasetIdentityError("dataset_identity_name_hash_mismatch")
    if not _hashes_match(
        receipt.get("expected_content_sha256"),
        expectation.dataset_content_sha256,
    ):
        raise DatasetIdentityError("dataset_identity_expected_content_sha256_mismatch")
    if not _hashes_match(
        receipt.get("observed_content_sha256"),
        expectation.dataset_content_sha256,
    ):
        raise DatasetIdentityError("dataset_identity_observed_content_sha256_mismatch")

    content_collection = receipt.get("content_collection")
    if not isinstance(content_collection, str) or not content_collection.strip():
        raise DatasetIdentityError("dataset_identity_content_collection_invalid")
    content_item_count = receipt.get("content_item_count")
    if (
        not isinstance(content_item_count, int)
        or isinstance(content_item_count, bool)
        or content_item_count <= 0
    ):
        raise DatasetIdentityError("dataset_identity_content_item_count_invalid")
    return VerifiedDatasetIdentityBinding(
        expectation=expectation,
        identity_manifest_sha256=manifest_sha256,
        identity_receipt_sha256=_sha256_file(receipt_target),
        content_collection=content_collection,
        content_item_count=content_item_count,
    )


def pin_dataset_identity(
    dataset: Mapping[str, Any],
    *,
    expected_dataset_id: int,
    expected_dataset_name: str,
) -> DatasetIdentityExpectation:
    """Create the first private pin after exact ID and name are supplied."""
    _verify_id_and_name(
        dataset,
        expected_dataset_id=expected_dataset_id,
        expected_dataset_name=expected_dataset_name,
    )
    return DatasetIdentityExpectation(
        dataset_id=expected_dataset_id,
        dataset_name=expected_dataset_name,
        dataset_content_sha256=dataset_content_sha256(dataset),
    )


def select_dataset_by_id(
    list_payload: Mapping[str, Any],
    *,
    expected_dataset_id: int,
) -> Mapping[str, Any]:
    """Select exactly one dataset by ID; never fall back to list position."""
    dataset_id = _validate_dataset_id(expected_dataset_id)
    datasets = list_payload.get("datasets")
    if not isinstance(datasets, list):
        raise DatasetIdentityError("dataset_list_invalid")
    matches = [
        dataset
        for dataset in datasets
        if isinstance(dataset, Mapping) and dataset.get("id") == dataset_id
    ]
    if not matches:
        raise DatasetIdentityError("dataset_id_not_found")
    if len(matches) != 1:
        raise DatasetIdentityError("dataset_id_ambiguous")
    return matches[0]


def canonical_dataset_content(dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Project an ReleaseFoundry dataset to stable test content, excluding API metadata."""
    if not isinstance(dataset, Mapping):
        raise DatasetIdentityError("dataset_payload_invalid")
    dataset_source = dataset.get("dataset_source")
    if not isinstance(dataset_source, Mapping) or not dataset_source:
        raise DatasetIdentityError("dataset_source_missing")
    canonical_source = _canonicalize_json_value(dataset_source)
    if not isinstance(canonical_source, dict) or not canonical_source:
        raise DatasetIdentityError("dataset_source_empty")
    return {
        "schema_version": CANONICAL_CONTENT_SCHEMA_VERSION,
        "dataset_source": canonical_source,
    }


def dataset_content_sha256(dataset: Mapping[str, Any]) -> str:
    return stable_hash(canonical_dataset_content(dataset))


def verify_dataset_identity(
    dataset: Mapping[str, Any],
    *,
    expected_dataset_id: int,
    expected_dataset_name: str,
    expected_content_sha256: str,
) -> dict[str, Any]:
    """Verify all three bindings and return only a public-safe receipt."""
    expectation = _expectation(
        dataset_id=expected_dataset_id,
        dataset_name=expected_dataset_name,
        dataset_content_sha256=expected_content_sha256,
    )
    _verify_id_and_name(
        dataset,
        expected_dataset_id=expectation.dataset_id,
        expected_dataset_name=expectation.dataset_name,
    )
    observed_content_sha256 = dataset_content_sha256(dataset)
    if not hmac.compare_digest(
        observed_content_sha256,
        expectation.dataset_content_sha256,
    ):
        raise DatasetIdentityError("dataset_content_sha256_mismatch")
    collection_name, item_count = _content_collection_summary(
        canonical_dataset_content(dataset)["dataset_source"]
    )
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "verification_state": "verified",
        "canonicalization_version": CANONICALIZATION_VERSION,
        "dataset_id_exact_match": True,
        "dataset_name_exact_match": True,
        "dataset_content_sha256_exact_match": True,
        "dataset_id_hash": stable_hash({"dataset_id": expectation.dataset_id}),
        "dataset_name_hash": stable_hash({"dataset_name": expectation.dataset_name}),
        "expected_content_sha256": expectation.dataset_content_sha256,
        "observed_content_sha256": observed_content_sha256,
        "content_collection": collection_name,
        "content_item_count": item_count,
        "release_authority": False,
        "blockers": [],
        "public_safe": True,
    }


def _expectation(
    *,
    dataset_id: Any,
    dataset_name: Any,
    dataset_content_sha256: Any,
) -> DatasetIdentityExpectation:
    return DatasetIdentityExpectation(
        dataset_id=_validate_dataset_id(dataset_id),
        dataset_name=_validate_dataset_name(dataset_name),
        dataset_content_sha256=_validate_sha256(dataset_content_sha256),
    )


def _verify_id_and_name(
    dataset: Mapping[str, Any],
    *,
    expected_dataset_id: int,
    expected_dataset_name: str,
) -> None:
    dataset_id = _validate_dataset_id(expected_dataset_id)
    dataset_name = _validate_dataset_name(expected_dataset_name)
    if dataset.get("id") != dataset_id:
        raise DatasetIdentityError("dataset_id_mismatch")
    observed_name = dataset.get("name")
    if not isinstance(observed_name, str) or not hmac.compare_digest(
        observed_name,
        dataset_name,
    ):
        raise DatasetIdentityError("dataset_name_mismatch")


def _validate_dataset_id(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DatasetIdentityError("expected_dataset_id_invalid")
    return value


def _validate_dataset_name(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise DatasetIdentityError("expected_dataset_name_invalid")
    return value


def _validate_sha256(value: Any) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise DatasetIdentityError("expected_dataset_content_sha256_invalid")
    return value


def _hashes_match(observed: Any, expected: str) -> bool:
    return (
        isinstance(observed, str)
        and _SHA256_PATTERN.fullmatch(observed) is not None
        and hmac.compare_digest(observed, expected)
    )


def _sha256_file(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise DatasetIdentityError("dataset_identity_binding_file_unreadable") from exc


def _canonicalize_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        canonical: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DatasetIdentityError("dataset_content_non_string_key")
            if key.lower() in _TRANSIENT_SIGNED_URL_KEYS:
                continue
            canonical[key] = _canonicalize_json_value(item)
        return canonical
    if isinstance(value, list):
        return [_canonicalize_json_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DatasetIdentityError("dataset_content_non_finite_number")
        return value
    raise DatasetIdentityError("dataset_content_not_json_serializable")


def _content_collection_summary(dataset_source: Mapping[str, Any]) -> tuple[str, int]:
    for key in ("runs", "scenarios", "cases", "tests", "items"):
        value = dataset_source.get(key)
        if isinstance(value, (dict, list)):
            return key, len(value)
    return "unrecognized", 0
