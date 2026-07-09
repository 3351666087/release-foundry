from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "sdk"))

from ashr_clone.storage import (  # noqa: E402
    OBJECT_STORAGE_CONTRACT_VERSION,
    LocalFilesystemObjectStorage,
    ObjectStorageContractError,
    assert_public_object_manifest_safe,
    build_object_manifest,
    scoped_object_key,
    verify_object_bytes,
)
from services.api.platform import LocalObjectStore, build_release_evidence_packet, verify_release_evidence_packet  # noqa: E402
from services.api.runtime import ValidationError  # noqa: E402


def test_scoped_object_key_enforces_tenant_project_run_shape():
    key = scoped_object_key(
        tenant_id="tenant_safe",
        project_id="project_safe",
        run_id="run_safe",
        object_id="artifact_safe",
        category="artifacts",
        suffix=".json",
    )

    assert key == "artifacts/tenant_safe/project_safe/run_safe/artifact_safe.json"

    with pytest.raises(ObjectStorageContractError, match="unsafe characters"):
        scoped_object_key(tenant_id="tenant/escape", project_id="project", run_id="run", object_id="artifact")

    with pytest.raises(ObjectStorageContractError, match="unsafe characters"):
        scoped_object_key(tenant_id="tenant", project_id="project", run_id="run", object_id="..")


def test_local_filesystem_write_manifest_is_public_safe_and_verifies_readback(tmp_path):
    store = LocalFilesystemObjectStorage(tmp_path / "objects")

    manifest = store.write_object(
        tenant_id="tenant_obj",
        project_id="project_obj",
        run_id="run_obj",
        object_id="artifact_obj",
        content=b'{"redacted":true}',
        content_type="application/json",
        suffix=".json",
        metadata={"source": "unit_test", "api_key": "tp_should_be_redacted"},
    )

    text = json.dumps(manifest, sort_keys=True)
    assert manifest["schema_version"] == OBJECT_STORAGE_CONTRACT_VERSION
    assert manifest["backend"] == "local-filesystem"
    assert manifest["object_key"] == "artifacts/tenant_obj/project_obj/run_obj/artifact_obj.json"
    assert manifest["backend_refs"]["storage_uri"] == "local://object-store/artifacts/tenant_obj/project_obj/run_obj/artifact_obj.json"
    assert manifest["write_readback_verification"]["verified"] is True
    assert manifest["raw_payload_included"] is False
    assert manifest["secret_value_present"] is False
    assert "tp_should_be_redacted" not in text
    assert str(tmp_path) not in text
    assert_public_object_manifest_safe(manifest)

    readback = store.verify_object(manifest)
    assert readback["verified"] is True

    object_path = tmp_path / "objects" / "artifacts" / "tenant_obj" / "project_obj" / "run_obj" / "artifact_obj.json"
    object_path.write_text('{"redacted":false}', encoding="utf-8")
    tampered = store.verify_object(manifest)
    assert tampered["verified"] is False
    assert tampered["failures"][0]["reason"] == "sha256_mismatch"


def test_s3_compatible_manifest_uses_refs_only_and_never_networks():
    key = scoped_object_key(tenant_id="tenant_s3", project_id="project_s3", run_id="run_s3", object_id="bundle_s3", category="evidence-bundles", suffix=".json")

    manifest = build_object_manifest(
        backend="s3-compatible",
        object_key=key,
        tenant_id="tenant_s3",
        project_id="project_s3",
        run_id="run_s3",
        object_id="bundle_s3",
        content_type="application/json",
        size_bytes=2,
        sha256="44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
        bucket_ref="env:ASHR_OBJECT_STORE_BUCKET",
        endpoint_ref="env:ASHR_OBJECT_STORE_ENDPOINT",
        region_ref="env:ASHR_OBJECT_STORE_REGION",
    )

    text = json.dumps(manifest, sort_keys=True)
    assert manifest["backend"] == "s3-compatible"
    assert manifest["backend_refs"]["storage_uri"] == "s3-compatible://env:ASHR_OBJECT_STORE_BUCKET/evidence-bundles/tenant_s3/project_s3/run_s3/bundle_s3.json"
    assert manifest["backend_refs"]["access_key_ref_present"] is False
    assert manifest["backend_refs"]["secret_key_ref_present"] is False
    assert "MINIO_ROOT_PASSWORD" not in text
    assert "AKIA" not in text
    assert verify_object_bytes(manifest, b"{}")["verified"] is True

    with pytest.raises(ObjectStorageContractError, match="approved reference prefix"):
        build_object_manifest(
            backend="s3-compatible",
            object_key=key,
            tenant_id="tenant_s3",
            project_id="project_s3",
            run_id="run_s3",
            object_id="bundle_s3",
            content_type="application/json",
            size_bytes=2,
            sha256="44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
            bucket_ref="raw-bucket-name",
            endpoint_ref="env:ASHR_OBJECT_STORE_ENDPOINT",
        )


def test_api_local_object_store_wires_manifest_metadata_and_readback(tmp_path):
    store = LocalObjectStore(object_root=tmp_path / "object-store")

    artifact = store.put_artifact(
        tenant_id="tenant_api",
        project_id="project_api",
        run_id="run_api",
        content="public redacted artifact",
        content_type="text/plain",
        artifact_id="artifact_api",
        redaction_status="public",
    )

    assert artifact["object_key"] == "artifacts/tenant_api/project_api/run_api/artifact_api.txt"
    assert artifact["object_storage"]["sha256"] == artifact["sha256"]
    assert artifact["write_readback_verified"] is True
    assert "public redacted artifact" not in json.dumps(artifact, sort_keys=True)

    packet = build_release_evidence_packet(
        tenant_id="tenant_api",
        project_id="project_api",
        run_id="run_api",
        lifecycle={"run_status": "completed", "uploads": [], "trace_batches": []},
        artifact_manifest=store.public_manifest("tenant_api", "project_api"),
        packet_id="packet_api",
    )
    assert verify_release_evidence_packet(packet)["verified"] is True

    bundle = store.put_evidence_bundle(
        tenant_id="tenant_api",
        project_id="project_api",
        run_id="run_api",
        packet=packet,
        bundle_id="bundle_api",
        metadata={"retention": "enterprise_audit"},
    )

    assert bundle["object_key"] == "evidence-bundles/tenant_api/project_api/run_api/bundle_api.json"
    assert bundle["object_storage"]["schema_version"] == OBJECT_STORAGE_CONTRACT_VERSION
    assert bundle["write_readback_verified"] is True
    verified = store.verify_stored_evidence_bundle(tenant_id="tenant_api", project_id="project_api", bundle_id="bundle_api")
    assert verified["verified"] is True
    assert verified["readback_verification"]["verified"] is True

    object_path = tmp_path / "object-store" / "evidence-bundles" / "tenant_api" / "project_api" / "run_api" / "bundle_api.json"
    object_path.write_text("{}", encoding="utf-8")
    tampered = store.verify_stored_evidence_bundle(tenant_id="tenant_api", project_id="project_api", bundle_id="bundle_api")
    assert tampered["verified"] is False
    assert tampered["failures"][0]["reason"] == "object_readback_mismatch"


def test_api_local_object_store_rejects_unsafe_storage_prefix():
    store = LocalObjectStore()
    packet = build_release_evidence_packet(
        tenant_id="tenant_api",
        project_id="project_api",
        run_id="run_api",
        lifecycle={"run_status": "completed", "uploads": [], "trace_batches": []},
        packet_id="packet_api",
    )

    with pytest.raises(ValidationError, match="unsafe characters"):
        store.put_evidence_bundle(tenant_id="tenant_api", project_id="project_api", run_id="run_api", packet=packet, storage_prefix="../private")
