import hashlib
import json
from copy import deepcopy

import pytest

from services.judge.releasefoundry_dataset_identity import (
    CANONICALIZATION_VERSION,
    DatasetIdentityError,
    dataset_content_sha256,
    load_dataset_identity_manifest,
    load_verified_dataset_identity_binding,
    pin_dataset_identity,
    select_dataset_by_id,
    verify_dataset_identity,
)


def _dataset() -> dict:
    return {
        "id": 42,
        "name": "A2 G3 calibration",
        "created_at": "2026-07-26T00:00:00Z",
        "tenant": 7,
        "dataset_source": {
            "dataset_type": "runs",
            "runs": {
                "case-a": {
                    "run_id": "case-a",
                    "actions": [
                        {
                            "actor": "user",
                            "content": "Check the tool arguments.",
                        }
                    ],
                },
                "case-b": {
                    "run_id": "case-b",
                    "actions": [
                        {
                            "actor": "agent",
                            "content": "Use the exact order.",
                        }
                    ],
                },
            },
            "total_runs": 2,
        },
    }


def _verified_binding_files(tmp_path):
    dataset = _dataset()
    content_hash = dataset_content_sha256(dataset)
    manifest = tmp_path / "identity.private.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "a2.releasefoundry_dataset_identity_private.v1",
                "dataset_id": dataset["id"],
                "dataset_name": dataset["name"],
                "dataset_content_sha256": content_hash,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    receipt_payload = verify_dataset_identity(
        dataset,
        expected_dataset_id=dataset["id"],
        expected_dataset_name=dataset["name"],
        expected_content_sha256=content_hash,
    )
    receipt_payload.update(
        {
            "binding_action": "verified_existing_pin",
            "identity_manifest_sha256": (
                "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()
            ),
        }
    )
    receipt = tmp_path / "identity.receipt.json"
    receipt.write_text(
        json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest, receipt, receipt_payload


def test_verify_dataset_identity_accepts_exact_id_name_and_content_hash():
    dataset = _dataset()
    content_hash = dataset_content_sha256(dataset)

    receipt = verify_dataset_identity(
        dataset,
        expected_dataset_id=42,
        expected_dataset_name="A2 G3 calibration",
        expected_content_sha256=content_hash,
    )

    assert receipt["verification_state"] == "verified"
    assert receipt["canonicalization_version"] == CANONICALIZATION_VERSION
    assert receipt["content_collection"] == "runs"
    assert receipt["content_item_count"] == 2
    assert receipt["expected_content_sha256"] == content_hash
    assert receipt["observed_content_sha256"] == content_hash
    assert receipt["public_safe"] is True
    assert "dataset_id" not in receipt
    assert "dataset_name" not in receipt


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("dataset_id", 43, "dataset_id_mismatch"),
        ("dataset_name", "A2 G3 Calibration", "dataset_name_mismatch"),
        (
            "dataset_content_sha256",
            "sha256:" + ("0" * 64),
            "dataset_content_sha256_mismatch",
        ),
    ],
)
def test_verify_dataset_identity_rejects_every_mismatch(field, value, error):
    dataset = _dataset()
    expected = {
        "expected_dataset_id": 42,
        "expected_dataset_name": "A2 G3 calibration",
        "expected_content_sha256": dataset_content_sha256(dataset),
    }
    expected[
        {
            "dataset_id": "expected_dataset_id",
            "dataset_name": "expected_dataset_name",
            "dataset_content_sha256": "expected_content_sha256",
        }[field]
    ] = value

    with pytest.raises(DatasetIdentityError, match=error):
        verify_dataset_identity(dataset, **expected)


@pytest.mark.parametrize(
    "expected",
    [
        {
            "expected_dataset_id": None,
            "expected_dataset_name": "A2 G3 calibration",
            "expected_content_sha256": "sha256:" + ("a" * 64),
        },
        {
            "expected_dataset_id": 42,
            "expected_dataset_name": "",
            "expected_content_sha256": "sha256:" + ("a" * 64),
        },
        {
            "expected_dataset_id": 42,
            "expected_dataset_name": "A2 G3 calibration",
            "expected_content_sha256": "",
        },
    ],
)
def test_verify_dataset_identity_rejects_missing_expected_fields(expected):
    with pytest.raises(DatasetIdentityError):
        verify_dataset_identity(_dataset(), **expected)


def test_select_dataset_by_id_is_independent_of_list_order():
    expected = {"id": 42, "name": "expected"}
    other = {"id": 7, "name": "other"}

    assert (
        select_dataset_by_id(
            {"datasets": [other, expected]},
            expected_dataset_id=42,
        )
        is expected
    )
    assert (
        select_dataset_by_id(
            {"datasets": [expected, other]},
            expected_dataset_id=42,
        )
        is expected
    )


def test_select_dataset_by_id_never_falls_back_to_first_item():
    with pytest.raises(DatasetIdentityError, match="dataset_id_not_found"):
        select_dataset_by_id(
            {"datasets": [{"id": 7}, {"id": 8}]},
            expected_dataset_id=42,
        )


def test_select_dataset_by_id_rejects_missing_and_ambiguous_datasets():
    with pytest.raises(DatasetIdentityError, match="dataset_id_not_found"):
        select_dataset_by_id({"datasets": []}, expected_dataset_id=42)
    with pytest.raises(DatasetIdentityError, match="dataset_id_ambiguous"):
        select_dataset_by_id(
            {"datasets": [{"id": 42}, {"id": 42}]},
            expected_dataset_id=42,
        )


def test_content_hash_excludes_api_metadata_and_transient_signed_urls():
    dataset = _dataset()
    changed = deepcopy(dataset)
    changed["created_at"] = "2099-01-01T00:00:00Z"
    changed["creator"] = 999
    changed["dataset_source"]["runs"]["case-a"]["signed_url"] = (
        "https://example.invalid/one?signature=secret"
    )
    changed["dataset_source"]["runs"]["case-a"]["url_expires_at"] = 1

    assert dataset_content_sha256(changed) == dataset_content_sha256(dataset)


def test_content_hash_changes_when_test_content_changes():
    dataset = _dataset()
    changed = deepcopy(dataset)
    changed["dataset_source"]["runs"]["case-a"]["actions"][0]["content"] = (
        "Different test content."
    )

    assert dataset_content_sha256(changed) != dataset_content_sha256(dataset)


def test_pin_dataset_identity_requires_explicit_exact_id_and_name():
    dataset = _dataset()

    expectation = pin_dataset_identity(
        dataset,
        expected_dataset_id=42,
        expected_dataset_name="A2 G3 calibration",
    )

    assert expectation.dataset_id == 42
    assert expectation.dataset_name == "A2 G3 calibration"
    assert expectation.dataset_content_sha256 == dataset_content_sha256(dataset)
    with pytest.raises(DatasetIdentityError, match="dataset_name_mismatch"):
        pin_dataset_identity(
            dataset,
            expected_dataset_id=42,
            expected_dataset_name="wrong",
        )


def test_private_manifest_loader_rejects_missing_fields(tmp_path):
    manifest = tmp_path / "identity.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "a2.releasefoundry_dataset_identity_private.v1",
                "dataset_id": 42,
                "dataset_name": "A2 G3 calibration",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        DatasetIdentityError,
        match="expected_dataset_content_sha256_invalid",
    ):
        load_dataset_identity_manifest(manifest)


def test_verified_binding_loader_accepts_fully_bound_receipt(tmp_path):
    manifest, receipt, _ = _verified_binding_files(tmp_path)

    binding = load_verified_dataset_identity_binding(receipt, manifest)

    assert binding.expectation.dataset_id == 42
    assert binding.expectation.dataset_name == "A2 G3 calibration"
    assert binding.content_collection == "runs"
    assert binding.content_item_count == 2
    assert binding.identity_manifest_sha256.startswith("sha256:")
    assert binding.identity_receipt_sha256.startswith("sha256:")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("schema_version", "stale", "receipt_schema_unsupported"),
        ("verification_state", "blocked", "receipt_not_verified"),
        (
            "canonicalization_version",
            "stale",
            "canonicalization_unsupported",
        ),
        ("dataset_id_exact_match", False, "dataset_id_exact_match_invalid"),
        ("dataset_name_exact_match", False, "dataset_name_exact_match_invalid"),
        (
            "dataset_content_sha256_exact_match",
            False,
            "dataset_content_sha256_exact_match_invalid",
        ),
        ("public_safe", False, "public_safe_invalid"),
        ("release_authority", True, "release_authority_invalid"),
        ("blockers", ["blocked"], "receipt_blocked"),
        ("binding_action", "manual", "binding_action_invalid"),
        (
            "identity_manifest_sha256",
            "sha256:" + ("0" * 64),
            "manifest_sha256_mismatch",
        ),
        (
            "dataset_id_hash",
            "sha256:" + ("0" * 64),
            "id_hash_mismatch",
        ),
        (
            "dataset_name_hash",
            "sha256:" + ("0" * 64),
            "name_hash_mismatch",
        ),
        (
            "expected_content_sha256",
            "sha256:" + ("0" * 64),
            "expected_content_sha256_mismatch",
        ),
        (
            "observed_content_sha256",
            "sha256:" + ("0" * 64),
            "observed_content_sha256_mismatch",
        ),
        ("content_collection", "", "content_collection_invalid"),
        ("content_item_count", 0, "content_item_count_invalid"),
        ("content_item_count", True, "content_item_count_invalid"),
    ],
)
def test_verified_binding_loader_rejects_stale_or_unbound_receipt(
    tmp_path,
    field,
    value,
    error,
):
    manifest, receipt, receipt_payload = _verified_binding_files(tmp_path)
    receipt_payload[field] = value
    receipt.write_text(
        json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(DatasetIdentityError, match=error):
        load_verified_dataset_identity_binding(receipt, manifest)


def test_verified_binding_loader_rejects_unreadable_receipt(tmp_path):
    manifest, receipt, _ = _verified_binding_files(tmp_path)
    receipt.write_text("{", encoding="utf-8")

    with pytest.raises(DatasetIdentityError, match="receipt_unreadable"):
        load_verified_dataset_identity_binding(receipt, manifest)
