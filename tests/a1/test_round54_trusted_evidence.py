from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from services.api.trusted_evidence import (
    DEFAULT_MAX_BATCH_SIZE,
    EXTRACTOR_ID,
    EXTRACTOR_VERSION,
    MODALITIES,
    EvidenceBinding,
    TrustedArtifactFact,
    TrustedEvidenceError,
    TrustedEvidenceProducer,
    TrustedEvidenceRequest,
    canonical_hash,
    canonical_json,
    validate_evidence_batch,
    validate_evidence_snapshot,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "docs" / "a1" / "schemas" / "a2_evidence_snapshot_compat.schema.json"
FIXTURE = ROOT / "docs" / "a1" / "evidence" / "round54_trusted_evidence_snapshot_fixture.json"
ALL_MODALITIES = ("text", "image", "audio", "file", "video")
TOOLS = {
    "text": "text.generate",
    "image": "image.inspect",
    "audio": "audio.transcribe",
    "file": "file.inspect",
    "video": "video.inspect",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _binding(index: int = 1, *, tenant_id: str = "tenant-round54") -> EvidenceBinding:
    return EvidenceBinding(
        organization_id="organization-round54",
        tenant_id=tenant_id,
        workspace_id="workspace-round54",
        project_id="project-round54",
        environment_id="environment-round54",
        run_id="run-round54",
        case_id=f"case-round54-{index:03d}",
        scenario_id="A2-S031",
    )


def _content_hash(modality: str) -> str:
    return canonical_hash({"fixture_modality": modality, "content_included": False})


def _request(
    index: int = 1,
    *,
    modalities: tuple[str, ...] = ALL_MODALITIES,
    required: tuple[str, ...] | None = None,
    statuses: dict[str, str] | None = None,
    artifact_order: tuple[str, ...] | None = None,
    created_at: str = "2026-07-11T08:00:00+08:00",
    tenant_id: str = "tenant-round54",
) -> TrustedEvidenceRequest:
    binding = _binding(index, tenant_id=tenant_id)
    selected = artifact_order or tuple(reversed(modalities))
    artifacts = tuple(
        TrustedArtifactFact(
            binding=binding,
            artifact_id=f"artifact-{modality}-{index:03d}",
            modality=modality,
            producer_tool=TOOLS[modality],
            reference_id=f"opaque-{modality}-{index:03d}",
            content_hash=_content_hash(modality),
            collection_status=(statuses or {}).get(modality, "complete"),
        )
        for modality in selected
    )
    source_payload_hash = canonical_hash(
        {
            "schema_version": "ashr.clone.run_fixture.v1",
            "binding": binding.as_dict(),
            "modality_content_hashes": {
                modality: _content_hash(modality) for modality in modalities
            },
        }
    )
    return TrustedEvidenceRequest(
        binding=binding,
        created_at=created_at,
        source_schema_version="ashr.clone.run_fixture.v1",
        source_payload_hash=source_payload_hash,
        required_modalities=required or modalities,
        artifacts=artifacts,
        tool_sequence=tuple(TOOLS[modality] for modality in modalities),
    )


def test_five_modality_fixture_matches_producer_and_exact_a2_wire_schema() -> None:
    expected = TrustedEvidenceProducer().produce(_request())
    fixture = _load(FIXTURE)
    schema = _load(SCHEMA)

    assert fixture == expected
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(fixture)
    validate_evidence_snapshot(fixture, expected_binding=_binding())
    assert schema["properties"]["schema_version"]["const"] == "a2.evidence_snapshot.v1"
    assert schema["additionalProperties"] is False
    assert {
        "organization_id",
        "tenant_id",
        "workspace_id",
        "project_id",
        "environment_id",
        "run_id",
        "case_id",
        "scenario_id",
    }.issubset(schema["required"])


def test_local_schema_pins_authoritative_a2_scope_security_and_modality_contract() -> None:
    schema = _load(SCHEMA)

    assert {
        "organization_id",
        "tenant_id",
        "workspace_id",
        "project_id",
        "environment_id",
        "run_id",
        "case_id",
        "scenario_id",
    }.issubset(schema["required"])
    assert schema["properties"]["security"]["required"] == [
        "tenant_scoped",
        "scope_complete",
        "raw_evidence_included",
        "private_evidence_included",
        "secrets_included",
        "artifact_content_included",
    ]
    assert schema["properties"]["security"]["properties"] == {
        "tenant_scoped": {"const": True},
        "scope_complete": {"const": True},
        "raw_evidence_included": {"const": False},
        "private_evidence_included": {"const": False},
        "secrets_included": {"const": False},
        "artifact_content_included": {"const": False},
    }
    assert set(schema["$defs"]["modalities"]["items"]["enum"]) == set(ALL_MODALITIES)


def test_text_image_audio_file_video_are_equal_artifact_contract_members() -> None:
    fixture = _load(FIXTURE)
    by_modality = {artifact["modality"]: artifact for artifact in fixture["artifacts"]}

    assert set(by_modality) == set(MODALITIES) == set(ALL_MODALITIES)
    assert fixture["required_modalities"] == sorted(ALL_MODALITIES)
    assert fixture["observed_modalities"] == sorted(ALL_MODALITIES)
    assert {frozenset(artifact) for artifact in by_modality.values()} == {
        frozenset(
            {
                "artifact_id",
                "modality",
                "producer_tool",
                "reference_hash",
                "content_hash",
                "content_included",
                "collection_status",
            }
        )
    }
    assert all(artifact["collection_status"] == "complete" for artifact in by_modality.values())
    assert all(artifact["content_included"] is False for artifact in by_modality.values())


def test_scope_binding_rejects_wrong_tenant_at_artifact_batch_and_validation_boundaries() -> None:
    request_binding = _binding()
    wrong_binding = _binding(tenant_id="tenant-other")
    wrong_artifact = TrustedArtifactFact(
        binding=wrong_binding,
        artifact_id="artifact-text-wrong",
        modality="text",
        producer_tool="text.generate",
        reference_id="opaque-text-wrong",
        content_hash=_content_hash("text"),
    )
    with pytest.raises(TrustedEvidenceError, match="binding does not match") as request_error:
        TrustedEvidenceRequest(
            binding=request_binding,
            created_at="2026-07-11T00:00:00Z",
            source_schema_version="ashr.clone.run_fixture.v1",
            source_payload_hash=_content_hash("text"),
            required_modalities=("text",),
            artifacts=(wrong_artifact,),
            tool_sequence=("text.generate",),
        )
    assert request_error.value.code == "artifact_scope_mismatch"

    producer = TrustedEvidenceProducer()
    with pytest.raises(TrustedEvidenceError, match="batch tenant") as batch_error:
        producer.produce_batch([_request()], expected_tenant_id="tenant-other")
    assert batch_error.value.code == "batch_tenant_mismatch"

    snapshot = producer.produce(_request())
    with pytest.raises(TrustedEvidenceError, match="binding") as validation_error:
        validate_evidence_snapshot(snapshot, expected_binding=wrong_binding)
    assert validation_error.value.code == "snapshot_scope_mismatch"


@pytest.mark.parametrize(
    "unsafe_reference",
    [
        "..",
        "..-private",
        "private_refs-secret",
        "docs/evidence/private_refs/record.json",
        "C:\\private\\record.json",
        "%2e%2e%2fsecret",
        "https://storage.invalid/private",
    ],
)
def test_path_traversal_and_private_references_never_cross_producer(unsafe_reference: str) -> None:
    with pytest.raises(TrustedEvidenceError):
        TrustedArtifactFact(
            binding=_binding(),
            artifact_id="artifact-text-001",
            modality="text",
            producer_tool="text.generate",
            reference_id=unsafe_reference,
            content_hash=_content_hash("text"),
        )


@pytest.mark.parametrize(
    "unsafe_identifier",
    [
        "operator@example.test",
        "mailto:operator",
        "file:private",
        "urn:credential",
        "tenant-api-key",
        "access_token.value",
        "client-secret-value",
        "password-reset",
    ],
)
@pytest.mark.parametrize(
    "field_name",
    [
        "organization_id",
        "tenant_id",
        "workspace_id",
        "project_id",
        "environment_id",
        "run_id",
        "case_id",
        "scenario_id",
    ],
)
def test_public_scope_identifiers_reject_pii_uri_and_secret_shapes(
    field_name: str, unsafe_identifier: str
) -> None:
    values = _binding().as_dict()
    values[field_name] = unsafe_identifier
    with pytest.raises(TrustedEvidenceError) as captured:
        EvidenceBinding(**values)
    assert captured.value.code in {
        "invalid_identifier",
        "pii_or_secret_identifier_rejected",
    }


@pytest.mark.parametrize(
    ("field_name", "unsafe_identifier"),
    [
        ("artifact_id", "artifact-api-key"),
        ("artifact_id", "operator@example.test"),
        ("reference_id", "refresh-token-value"),
        ("reference_id", "mailto:operator"),
    ],
)
def test_public_artifact_identifiers_reject_pii_uri_and_secret_shapes(
    field_name: str, unsafe_identifier: str
) -> None:
    values = {
        "binding": _binding(),
        "artifact_id": "artifact-text-001",
        "modality": "text",
        "producer_tool": "text.generate",
        "reference_id": "opaque-text-001",
        "content_hash": _content_hash("text"),
    }
    values[field_name] = unsafe_identifier
    with pytest.raises(TrustedEvidenceError) as captured:
        TrustedArtifactFact(**values)
    assert captured.value.code in {
        "invalid_identifier",
        "unsafe_reference",
        "pii_or_secret_identifier_rejected",
    }


def test_duplicate_modalities_are_rejected_in_requests_and_tampered_snapshots() -> None:
    with pytest.raises(TrustedEvidenceError, match="duplicate modality") as request_error:
        _request(modalities=("text",), required=("text", "text"))
    assert request_error.value.code == "duplicate_modality"

    snapshot = TrustedEvidenceProducer().produce(_request())
    snapshot["observed_modalities"].append("text")
    with pytest.raises(TrustedEvidenceError, match="duplicate modality") as snapshot_error:
        validate_evidence_snapshot(snapshot)
    assert snapshot_error.value.code == "duplicate_modality"


@pytest.mark.parametrize(
    "malformed_hash",
    ["", "sha256:abc", "SHA256:" + "a" * 64, "sha256:" + "G" * 64, "a" * 64],
)
def test_malformed_hashes_fail_before_snapshot_emission(malformed_hash: str) -> None:
    with pytest.raises(TrustedEvidenceError, match="sha256") as error:
        TrustedArtifactFact(
            binding=_binding(),
            artifact_id="artifact-text-001",
            modality="text",
            producer_tool="text.generate",
            reference_id="opaque-text-001",
            content_hash=malformed_hash,
        )
    assert error.value.code == "malformed_hash"


def test_hash_tampering_is_detected_for_source_id_and_snapshot_hash() -> None:
    original = TrustedEvidenceProducer().produce(_request())
    for field in ("source_payload_hash", "snapshot_id", "snapshot_hash"):
        tampered = deepcopy(original)
        tampered[field] = "sha256:" + "0" * 64
        with pytest.raises(TrustedEvidenceError):
            validate_evidence_snapshot(tampered)


def test_partial_missing_and_invalid_evidence_have_deterministic_fail_closed_states() -> None:
    producer = TrustedEvidenceProducer()
    partial = producer.produce(
        _request(
            modalities=("text", "image"),
            required=("text", "image"),
            statuses={"image": "partial"},
        )
    )
    assert partial["completeness"] == "partial"
    assert partial["missing_modalities"] == []
    assert partial["observed_modalities"] == ["image", "text"]

    missing = producer.produce(
        _request(
            modalities=(),
            required=("text", "video"),
            artifact_order=(),
        )
    )
    assert missing["completeness"] == "evidence_missing"
    assert missing["observed_modalities"] == []
    assert missing["missing_modalities"] == ["text", "video"]

    invalid = producer.produce(
        _request(
            modalities=("text",),
            required=("text",),
            statuses={"text": "invalid"},
        )
    )
    assert invalid["completeness"] == "invalid"
    assert invalid["missing_modalities"] == ["text"]
    assert invalid["extractor_provenance"][0]["status"] == "invalid"


def test_canonicalization_is_independent_of_mapping_artifact_and_timezone_spelling() -> None:
    producer = TrustedEvidenceProducer()
    first = producer.produce(
        _request(
            modalities=("text", "image", "audio"),
            artifact_order=("audio", "text", "image"),
            required=("image", "audio", "text"),
            created_at="2026-07-11T08:00:00+08:00",
        )
    )
    second = producer.produce(
        _request(
            modalities=("text", "image", "audio"),
            artifact_order=("image", "audio", "text"),
            required=("text", "image", "audio"),
            created_at="2026-07-11T00:00:00Z",
        )
    )

    assert first == second
    assert canonical_json({"b": [2, 1], "a": {"z": True}}) == canonical_json(
        {"a": {"z": True}, "b": [2, 1]}
    )
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})


def test_extractor_provenance_is_stable_and_bound_to_source_hash() -> None:
    snapshot = TrustedEvidenceProducer().produce(_request())
    assert snapshot["extractor_provenance"] == [
        {
            "extractor_id": EXTRACTOR_ID,
            "extractor_version": EXTRACTOR_VERSION,
            "input_hash": snapshot["source_payload_hash"],
            "status": snapshot["completeness"],
        }
    ]


def test_large_batch_accepts_80_and_rejects_81_or_duplicate_case_binding() -> None:
    producer = TrustedEvidenceProducer()
    requests = [
        _request(index, modalities=("text",), required=("text",))
        for index in range(1, DEFAULT_MAX_BATCH_SIZE + 1)
    ]
    snapshots = producer.produce_batch(
        requests,
        expected_organization_id="organization-round54",
        expected_tenant_id="tenant-round54",
        expected_workspace_id="workspace-round54",
        expected_project_id="project-round54",
        expected_environment_id="environment-round54",
    )
    assert len(snapshots) == DEFAULT_MAX_BATCH_SIZE
    assert len({snapshot["snapshot_hash"] for snapshot in snapshots}) == DEFAULT_MAX_BATCH_SIZE
    validate_evidence_batch(
        snapshots,
        expected_organization_id="organization-round54",
        expected_tenant_id="tenant-round54",
        expected_workspace_id="workspace-round54",
        expected_project_id="project-round54",
        expected_environment_id="environment-round54",
    )

    with pytest.raises(TrustedEvidenceError, match="max_batch_size") as size_error:
        producer.produce_batch(requests + [_request(81, modalities=("text",))])
    assert size_error.value.code == "batch_limit_exceeded"

    with pytest.raises(TrustedEvidenceError, match="duplicate") as duplicate_error:
        producer.produce_batch([requests[0], requests[0]])
    assert duplicate_error.value.code == "duplicate_case_binding"


def test_fixture_contains_hashes_and_public_flags_but_no_raw_or_private_evidence() -> None:
    fixture = _load(FIXTURE)
    serialized = json.dumps(fixture, sort_keys=True).lower()

    assert fixture["security"] == {
        "tenant_scoped": True,
        "scope_complete": True,
        "raw_evidence_included": False,
        "private_evidence_included": False,
        "secrets_included": False,
        "artifact_content_included": False,
    }
    for raw_reference in (
        "opaque-text-001",
        "opaque-image-001",
        "opaque-audio-001",
        "opaque-file-001",
        "opaque-video-001",
        "docs/evidence/private_refs",
    ):
        assert raw_reference not in serialized


def test_validator_rejects_extra_fields_noncanonical_artifacts_and_public_safety_drift() -> None:
    original = TrustedEvidenceProducer().produce(_request())

    extra = deepcopy(original)
    extra["raw_evidence"] = "forbidden"
    with pytest.raises(TrustedEvidenceError, match="extra"):
        validate_evidence_snapshot(extra)

    reordered = deepcopy(original)
    reordered["artifacts"] = list(reversed(reordered["artifacts"]))
    with pytest.raises(TrustedEvidenceError, match="canonical"):
        validate_evidence_snapshot(reordered)

    unsafe = deepcopy(original)
    unsafe["security"]["raw_evidence_included"] = True
    with pytest.raises(TrustedEvidenceError, match="public-safety"):
        validate_evidence_snapshot(unsafe)
