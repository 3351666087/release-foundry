from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from services.customer_release import verify_customer_agent_release_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT_SHA = "a" * 40
PRODUCT_ID = "ashr-product@1.0.0-rc.1"
AGENT_ID = "agent-release:demo/a3-golden-agent@0.2.0-rc.2"
SCOPE = {
    "organization_id": "org_local_demo",
    "tenant_id": "org_local_demo",
    "workspace_id": "workspace_local_demo",
    "project_id": "a2_g3_calibration",
    "environment_id": "local",
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_ref(root: Path, path: Path) -> dict[str, str]:
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}


def build_release(root: Path) -> Path:
    product_manifest = root / "product-binding" / "manifest.json"
    write_json(
        product_manifest,
        {
            "product_release_id": PRODUCT_ID,
            "source": {"commit_sha": COMMIT_SHA, "dirty": False},
        },
    )
    product_manifest_hash = sha256_file(product_manifest)
    product_verification = root / "product-binding" / "verification.json"
    write_json(
        product_verification,
        {
            "schema_version": "ashr.product_release_verification.v1",
            "decision": "approve_product_release",
            "product_release_id": PRODUCT_ID,
            "product_release_manifest_sha256": product_manifest_hash,
            "blocking_reasons": [],
        },
    )

    run = root / "evidence" / "a1-run.json"
    write_json(
        run,
        {
            "schema_version": "ashr.clone.run_result.v1",
            "run_id": "run-001",
            "status": "passed",
        },
    )
    record_hash = f"sha256:{'b' * 64}"
    spine = root / "evidence" / "a2-spine.json"
    write_json(
        spine,
        {
            "schema_version": "a2.trusted_spine_handoff.v1",
            "evidence_snapshot": {**SCOPE, "run_id": "run-001"},
            "decision_ledger": {
                **SCOPE,
                "head_hash": record_hash,
                "records": [
                    {
                        "decision": "allow",
                        "record_hash": record_hash,
                        "run_id": "run-001",
                    }
                ],
                "metadata": {"chain_verified": True},
            },
            "a3_consumption": {
                "release_ready": True,
                "display_provenance_hash": record_hash,
            },
        },
    )
    gate = root / "evidence" / "a3-gate.json"
    write_json(
        gate,
        {
            "schema_version": "a3.gate_cli.v1",
            "release_gate": {"decision": "approve_release"},
            "release_workflow": {"release_version": "0.2.0-rc.2"},
        },
    )
    artifact = root / "evidence" / "a3-artifact-verification.json"
    write_json(
        artifact,
        {
            "schema_version": "a3.release_artifact_verification.v1",
            "status": "passed",
            "release_version": "0.2.0-rc.2",
        },
    )
    delivery = root / "evidence" / "a3-delivery.json"
    write_json(
        delivery,
        {
            "schema_version": "a3.release_delivery_index.v1",
            "production_ready": True,
            "release_version": "0.2.0-rc.2",
            "git_sha_alias": COMMIT_SHA,
            "ci_tested_sha_alias": COMMIT_SHA,
            "authority": {"a1_run_ids": ["run-001"]},
        },
    )
    bundle = root / "evidence" / "a3-bundle.json"
    write_json(
        bundle,
        {
            "schema_version": "a3.audit_bundle_index.v1",
            "release": {"run_id": "run-001", "release_version": "0.2.0-rc.2"},
        },
    )
    archive = root / "evidence" / "a3-archive.json"
    write_json(
        archive,
        {
            "schema_version": "a3.audit_archive_manifest.v1",
            "bundle": {
                "release": {"run_id": "run-001", "release_version": "0.2.0-rc.2"}
            },
        },
    )
    approval = root / "evidence" / "human-approval.json"
    write_json(
        approval,
        {
            "schema_version": "a3.review_approval.v1",
            "status": "approved",
            "agent_release_id": AGENT_ID,
            "candidate_id": "a3-golden-agent@0.2.0-rc.2",
            "source_commit": COMMIT_SHA,
            "reviewer_identity_hash": f"sha256:{'c' * 64}",
            "approved_at": "2026-07-20T00:00:00Z",
        },
    )

    manifest = {
        "schema_version": "ashr.customer_agent_release_manifest.v1",
        "agent_release_id": AGENT_ID,
        "generated_at": "2026-07-20T00:00:00Z",
        "source": {
            "repository": "https://github.com/3351666087/ashr-codex-factory",
            "commit_sha": COMMIT_SHA,
            "dirty": False,
        },
        "tenant_scope": SCOPE,
        "candidate": {
            "agent_id": "a3-golden-agent",
            "version": "0.2.0-rc.2",
            "candidate_id": "a3-golden-agent@0.2.0-rc.2",
            "run_id": "run-001",
            "source_commit": COMMIT_SHA,
            "evidence_release_version": "0.2.0-rc.2",
        },
        "product_binding": {
            "product_release_id": PRODUCT_ID,
            "product_release_manifest_sha256": product_manifest_hash,
            "manifest": file_ref(root, product_manifest),
            "verification": file_ref(root, product_verification),
        },
        "evidence": {
            "a1_run_result": file_ref(root, run),
            "a2_trusted_spine": file_ref(root, spine),
            "a3_gate_report": file_ref(root, gate),
            "a3_release_artifact_verification": file_ref(root, artifact),
            "a3_release_delivery_index": file_ref(root, delivery),
            "a3_audit_bundle_index": file_ref(root, bundle),
            "a3_audit_archive_manifest": file_ref(root, archive),
        },
        "human_review": {
            "status": "approved",
            "approval_receipt": file_ref(root, approval),
        },
        "authority": {
            "decision_authority": "A2 Decision Ledger",
            "a3_recomputed_a2_decision": False,
        },
    }
    manifest_path = root / "manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


def test_complete_customer_agent_release_is_approved(tmp_path: Path) -> None:
    manifest_path = build_release(tmp_path)

    result = verify_customer_agent_release_manifest(manifest_path, release_root=tmp_path)

    assert result["decision"] == "approve_customer_agent_release"
    assert result["agent_release_id"] == AGENT_ID
    assert result["product_release_decision"] == "approve_product_release"
    assert result["a2_authoritative_decision"] == "allow"
    assert result["a3_recomputed_a2_decision"] is False
    assert len(result["checked_evidence_ids"]) == 7
    assert result["blocking_reasons"] == []


def test_blocked_product_cannot_authorize_customer_release(tmp_path: Path) -> None:
    manifest_path = build_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verification_path = tmp_path / manifest["product_binding"]["verification"]["path"]
    verification = json.loads(verification_path.read_text(encoding="utf-8"))
    verification["decision"] = "block_product_release"
    write_json(verification_path, verification)
    manifest["product_binding"]["verification"] = file_ref(tmp_path, verification_path)
    write_json(manifest_path, manifest)

    result = verify_customer_agent_release_manifest(manifest_path, release_root=tmp_path)

    assert result["decision"] == "block_customer_agent_release"
    assert "product_release_not_approved" in result["blocking_reasons"]


def test_a2_block_is_preserved_and_never_recomputed(tmp_path: Path) -> None:
    manifest_path = build_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    spine_path = tmp_path / manifest["evidence"]["a2_trusted_spine"]["path"]
    spine = json.loads(spine_path.read_text(encoding="utf-8"))
    spine["decision_ledger"]["records"][-1]["decision"] = "block"
    spine["a3_consumption"]["release_ready"] = False
    write_json(spine_path, spine)
    manifest["evidence"]["a2_trusted_spine"] = file_ref(tmp_path, spine_path)
    write_json(manifest_path, manifest)

    result = verify_customer_agent_release_manifest(manifest_path, release_root=tmp_path)

    assert result["decision"] == "block_customer_agent_release"
    assert result["a2_authoritative_decision"] == "block"
    assert result["a3_recomputed_a2_decision"] is False
    assert {"a2_release_blocked", "a2_release_not_ready"}.issubset(result["blocking_reasons"])


def test_digest_path_and_secret_fail_closed(tmp_path: Path) -> None:
    manifest_path = build_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"]["a1_run_result"]["sha256"] = "0" * 64
    manifest["evidence"]["a3_gate_report"]["path"] = "../outside.json"
    manifest["api_token"] = "must-not-ship"
    write_json(manifest_path, manifest)

    result = verify_customer_agent_release_manifest(manifest_path, release_root=tmp_path)

    assert result["decision"] == "block_customer_agent_release"
    assert {"evidence_digest_mismatch", "unsafe_path", "embedded_secret_material"}.issubset(
        result["blocking_reasons"]
    )


def test_stale_cross_lane_evidence_cannot_authorize_new_candidate(tmp_path: Path) -> None:
    manifest_path = build_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    spine_path = tmp_path / manifest["evidence"]["a2_trusted_spine"]["path"]
    spine = json.loads(spine_path.read_text(encoding="utf-8"))
    spine["evidence_snapshot"]["run_id"] = "old-run"
    spine["decision_ledger"]["records"][-1]["run_id"] = "old-run"
    write_json(spine_path, spine)
    manifest["evidence"]["a2_trusted_spine"] = file_ref(tmp_path, spine_path)

    delivery_path = tmp_path / manifest["evidence"]["a3_release_delivery_index"]["path"]
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    delivery["git_sha_alias"] = "d" * 40
    write_json(delivery_path, delivery)
    manifest["evidence"]["a3_release_delivery_index"] = file_ref(tmp_path, delivery_path)
    write_json(manifest_path, manifest)

    result = verify_customer_agent_release_manifest(manifest_path, release_root=tmp_path)

    assert result["decision"] == "block_customer_agent_release"
    assert {"a2_candidate_run_mismatch", "a3_delivery_source_mismatch"}.issubset(
        result["blocking_reasons"]
    )


def test_unbound_human_approval_is_rejected(tmp_path: Path) -> None:
    manifest_path = build_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    approval_path = tmp_path / manifest["human_review"]["approval_receipt"]["path"]
    write_json(approval_path, {"schema_version": "a3.review_approval.v1", "status": "approved"})
    manifest["human_review"]["approval_receipt"] = file_ref(tmp_path, approval_path)
    write_json(manifest_path, manifest)

    result = verify_customer_agent_release_manifest(manifest_path, release_root=tmp_path)

    assert result["decision"] == "block_customer_agent_release"
    assert "invalid_human_approval" in result["blocking_reasons"]


def test_cli_returns_two_for_blocked_customer_release(tmp_path: Path) -> None:
    manifest_path = build_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["human_review"] = {"status": "not_approved", "approval_receipt": None}
    write_json(manifest_path, manifest)

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify_customer_agent_release.py"),
            "--manifest",
            str(manifest_path),
            "--release-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    result = json.loads(completed.stdout)
    assert result["decision"] == "block_customer_agent_release"
    assert "human_approval_missing" in result["blocking_reasons"]
