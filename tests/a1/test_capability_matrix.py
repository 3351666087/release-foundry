from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.sdk.ashr_clone.capability_matrix import (
    CAPABILITY_MATRIX_SCHEMA_VERSION,
    CapabilityMatrixInputs,
    build_capability_matrix,
    load_public_json,
    validate_capability_matrix,
    write_capability_matrix,
)


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_INDEX = ROOT / "docs" / "a1" / "api_calibration" / "real_api_evidence_index.json"
FRONTEND_INDEX = ROOT / "docs" / "a1" / "frontend_mirror" / "frontend_mirror_index.json"
MATRIX_ARTIFACT = ROOT / "docs" / "a1" / "commercial" / "capability_matrix.json"
SCHEMA = ROOT / "docs" / "a1" / "schemas" / "capability_matrix.schema.json"


def _by_name(matrix):
    return {entry["name"]: entry for entry in matrix["capabilities"]}


def test_capability_matrix_builds_public_safe_commercial_axes(tmp_path):
    matrix = build_capability_matrix(
        CapabilityMatrixInputs(
            public_evidence_index_path=EVIDENCE_INDEX,
            frontend_mirror_index_path=FRONTEND_INDEX,
            tests_root=ROOT / "tests" / "a1",
        )
    )

    assert matrix["schema_version"] == CAPABILITY_MATRIX_SCHEMA_VERSION
    assert matrix["public_safe"] is True
    assert matrix["secret_policy"] == {
        "private_evidence_read": False,
        "tokens_included": False,
        "raw_private_payloads_included": False,
        "input_sources": [
            "public_evidence_index",
            "frontend_mirror_index",
            "local_runtime_symbols",
            "tests_a1_static_coverage",
        ],
    }
    assert not validate_capability_matrix(matrix)

    by_name = _by_name(matrix)
    assert by_name["list_datasets"]["real_read_verified"] is True
    assert by_name["list_datasets"]["frontend_mirrored"] is True
    assert by_name["list_datasets"]["local_runtime"] is True
    assert by_name["create_request"]["mutating_planned_or_quota_blocked"] is True
    assert by_name["create_request"]["frontend_mirrored"] is True
    assert by_name["dataset_adapter"]["local_only"] is True
    assert by_name["trace_fixture"]["test_covered"] is True
    assert matrix["summary"]["axis_counts"]["frontend_mirrored"] >= 100
    assert matrix["summary"]["axis_counts"]["real_read_verified"] >= 5

    output = write_capability_matrix(tmp_path / "capability_matrix.json", matrix)
    assert json.loads(output.read_text(encoding="utf-8")) == matrix


def test_capability_matrix_artifact_matches_builder_and_schema_required_fields():
    artifact = json.loads(MATRIX_ARTIFACT.read_text(encoding="utf-8"))
    rebuilt = build_capability_matrix(
        CapabilityMatrixInputs(
            public_evidence_index_path=EVIDENCE_INDEX,
            frontend_mirror_index_path=FRONTEND_INDEX,
            tests_root=ROOT / "tests" / "a1",
        )
    )
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert artifact == rebuilt
    for field in schema["required"]:
        assert field in artifact
    for field in schema["properties"]["summary"]["required"]:
        assert field in artifact["summary"]
    assert artifact["summary"]["total_capabilities"] == len(artifact["capabilities"])
    assert artifact["capabilities"] == sorted(artifact["capabilities"], key=lambda item: item["name"])


def test_capability_matrix_artifact_does_not_leak_private_refs_or_tokens():
    artifact_text = MATRIX_ARTIFACT.read_text(encoding="utf-8")

    assert "private_refs" not in artifact_text
    assert "tp_" not in artifact_text
    assert "sk-" not in artifact_text
    assert "Bearer " not in artifact_text
    assert "ashr_live_" not in artifact_text


def test_capability_matrix_refuses_private_inputs():
    with pytest.raises(ValueError, match="non-public"):
        load_public_json(ROOT / "docs" / "evidence" / "private_refs" / "anything.json")
