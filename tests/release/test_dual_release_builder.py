from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from services.customer_release import verify_customer_agent_release_manifest
from services.release_distribution import build_dual_release_candidates, verify_release_index


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_AT = "2026-07-20T11:00:00Z"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dual_builder_emits_independent_deterministic_no_go_candidates(tmp_path: Path) -> None:
    source_commit = _head_sha()
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    first = build_dual_release_candidates(
        REPO_ROOT,
        first_root,
        source_commit=source_commit,
        generated_at=GENERATED_AT,
        allow_dirty=True,
    )
    second = build_dual_release_candidates(
        REPO_ROOT,
        second_root,
        source_commit=source_commit,
        generated_at=GENERATED_AT,
        allow_dirty=True,
    )

    assert first["product_release"]["release_id"] == "ashr-product@1.0.0-rc.1"
    assert first["customer_agent_release"]["release_id"] == (
        "agent-release:demo/a3-golden-agent@0.2.0-rc.3"
    )
    assert first["product_release"]["decision"] == "block_product_release"
    assert first["customer_agent_release"]["decision"] == "block_customer_agent_release"
    assert first["product_release"]["go_no_go"] == "NO-GO"
    assert first["customer_agent_release"]["go_no_go"] == "NO-GO"
    assert first["product_release"]["tag"] != first["customer_agent_release"]["tag"]
    assert first["authority"] == {
        "independent_decisions": True,
        "customer_depends_on_approved_product": True,
        "product_depends_on_customer": False,
        "a3_recomputed_a2_decision": False,
    }

    product_zip = first_root / "ashr-product-1.0.0-rc.1.zip"
    customer_zip = first_root / "agent-release-demo-a3-golden-agent-0.2.0-rc.3.zip"
    assert sha256_file(product_zip) == sha256_file(second_root / product_zip.name)
    assert sha256_file(customer_zip) == sha256_file(second_root / customer_zip.name)
    assert verify_release_index(first_root / "dual-release-index.json")["status"] == "passed"
    assert json.loads((first_root / "dual-release-index.verification.json").read_text(encoding="utf-8"))[
        "status"
    ] == "passed"

    with zipfile.ZipFile(product_zip) as archive:
        product_entries = archive.namelist()
        assert any(name.endswith("/artifacts/install.sh") for name in product_entries)
        assert any(name.endswith("/artifacts/install.ps1") for name in product_entries)
        assert any(name.endswith("/artifacts/self-host.env.example") for name in product_entries)
        assert any(name.endswith("/supply-chain/ashr-product-1.0.0-rc.1.spdx.json") for name in product_entries)
    runtime_zip = first_root / first["product_release"]["release_root"] / "artifacts" / (
        "ashr-product-1.0.0-rc.1-runtime.zip"
    )
    with zipfile.ZipFile(runtime_zip) as archive:
        assert "infra/docker/self-host.env.example" in archive.namelist()
    with zipfile.ZipFile(customer_zip) as archive:
        customer_entries = archive.namelist()
        assert any(name.endswith("/evidence/a2_trusted_spine_handoff.snapshot.json") for name in customer_entries)
        assert any(name.endswith("/evidence/a1_candidate_run_receipt.json") for name in customer_entries)
        assert any(name.endswith("/evidence/a3_shared_candidate_identity.json") for name in customer_entries)
        assert any(name.endswith("/evidence/a3_candidate_delivery_binding.json") for name in customer_entries)
        assert any(name.endswith("/product-binding/verification.json") for name in customer_entries)

    forbidden = ("ashr_key", "__pycache__", ".pyc", "node_modules")
    assert not [name for name in [*product_entries, *customer_entries] if any(item in name.lower() for item in forbidden)]
    private_env_names = {".env", ".env.local", ".env.self-host"}
    assert not [
        name
        for name in [*product_entries, *customer_entries]
        if name.rsplit("/", 1)[-1].lower() in private_env_names
    ]

    customer_manifest = json.loads(
        (first_root / first["customer_agent_release"]["release_root"] / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    product_manifest_path = first_root / first["product_release"]["release_root"] / "manifest.json"
    assert customer_manifest["product_binding"]["product_release_manifest_sha256"] == sha256_file(
        product_manifest_path
    )
    assert first["customer_agent_release"]["product_release_manifest_sha256"] == sha256_file(
        product_manifest_path
    )
    customer_verification = json.loads(
        (first_root / first["customer_agent_release"]["release_root"] / "verification.json").read_text(
            encoding="utf-8"
        )
    )
    assert customer_manifest["source"]["commit_sha"] == source_commit
    assert customer_manifest["candidate"]["candidate_id"] == "a3-golden-agent@0.2.0-rc.3"
    assert customer_manifest["candidate"]["run_id"] == "a3-golden-20260720-003"
    assert customer_manifest["candidate"]["source_commit"] == (
        "1d292047e991995fdf52f0545ffff410ee19a171"
    )
    assert customer_manifest["lane_bindings"]["release_package_commit"] == source_commit
    assert customer_verification["identity_alignment"]["status"] == "passed"
    assert customer_verification["identity_alignment"]["mismatch_reasons"] == []
    assert customer_verification["decision"] == "block_customer_agent_release"
    assert {
        "product_release_not_approved",
        "a2_release_blocked",
        "a2_release_not_ready",
        "a3_gate_blocked",
        "a3_delivery_not_ready",
        "a3_ci_tested_sha_missing",
        "human_approval_missing",
    }.issubset(customer_verification["blocking_reasons"])
    assert not {
        "a2_candidate_run_mismatch",
        "a3_delivery_source_mismatch",
        "a3_release_version_mismatch",
    }.intersection(customer_verification["blocking_reasons"])


def test_release_index_detects_asset_tampering(tmp_path: Path) -> None:
    build_dual_release_candidates(
        REPO_ROOT,
        tmp_path,
        source_commit=_head_sha(),
        generated_at=GENERATED_AT,
        allow_dirty=True,
    )
    asset = tmp_path / "agent-release-demo-a3-golden-agent-0.2.0-rc.3.manifest.json"
    asset.write_text("{}\n", encoding="utf-8")

    result = verify_release_index(tmp_path / "dual-release-index.json")

    assert result["status"] == "failed"
    assert {item["code"] for item in result["issues"]} >= {
        "asset_digest_mismatch",
        "asset_size_mismatch",
    }


def test_rc3_customer_verifier_reports_cross_lane_identity_tampering(tmp_path: Path) -> None:
    index = build_dual_release_candidates(
        REPO_ROOT,
        tmp_path,
        source_commit=_head_sha(),
        generated_at=GENERATED_AT,
        allow_dirty=True,
    )
    customer_root = tmp_path / index["customer_agent_release"]["release_root"]
    manifest_path = customer_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    spine_path = customer_root / manifest["evidence"]["a2_trusted_spine"]["path"]
    spine = json.loads(spine_path.read_text(encoding="utf-8"))
    spine["candidate_binding"]["run_id"] = "stale-run"
    spine_path.write_text(json.dumps(spine, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["evidence"]["a2_trusted_spine"]["sha256"] = sha256_file(spine_path)

    binding_path = customer_root / manifest["evidence"]["a3_candidate_delivery_binding"]["path"]
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    binding["a3"]["implementation_commit"] = "f" * 40
    binding_path.write_text(json.dumps(binding, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["evidence"]["a3_candidate_delivery_binding"]["sha256"] = sha256_file(binding_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = verify_customer_agent_release_manifest(manifest_path, release_root=customer_root)

    assert result["identity_alignment"]["status"] == "failed"
    assert {
        "a2_candidate_run_mismatch",
        "a3_implementation_commit_mismatch",
    }.issubset(result["identity_alignment"]["mismatch_reasons"])


def _head_sha() -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
