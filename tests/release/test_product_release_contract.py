from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from services.product_release import verify_product_release_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_SOURCE = REPO_ROOT / "docs" / "releases" / "releasefoundry_product_release_policy.v1.json"
COMMIT_SHA = "a" * 40
PRODUCT_RELEASE_ID = "releasefoundry-product@1.0.0"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_ref(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }


def build_complete_release(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    release_dir = root / "dist" / "releases" / "releasefoundry-product-1.0.0"
    policy_path = root / "docs" / "releases" / POLICY_SOURCE.name
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_bytes(POLICY_SOURCE.read_bytes())
    policy = json.loads(policy_path.read_text(encoding="utf-8"))

    artifacts: dict[str, Path] = {}
    for name in (
        "bundle.tar.gz",
        "docker-compose.yml",
        "install.sh",
        "install.ps1",
        "web.sbom.json",
        "web.signature.json",
        "web.provenance.json",
        "python.whl",
        "typescript.tgz",
        "go.zip",
    ):
        artifact = release_dir / "artifacts" / name
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f"release artifact: {name}\n", encoding="utf-8")
        artifacts[name] = artifact

    runbooks: dict[str, dict[str, str]] = {}
    for name in policy["required_runbooks"]:
        runbook = root / "docs" / "operations" / f"{name}.md"
        runbook.parent.mkdir(parents=True, exist_ok=True)
        runbook.write_text(f"# {name}\n\nVerified operator procedure.\n", encoding="utf-8")
        runbooks[name] = file_ref(root, runbook)

    receipts: dict[str, dict[str, str]] = {}
    for receipt_id in policy["required_receipts"]:
        receipt = release_dir / "receipts" / f"{receipt_id}.json"
        environment = {"os": "linux", "arch": "amd64"}
        if receipt_id.startswith(("docker.", "install.")):
            environment.update(
                {
                    "docker_server_version": "29.6.1",
                    "docker_compose_version": "2.38.2",
                }
            )
        write_json(
            receipt,
            {
                "schema_version": "releasefoundry.verification_receipt.v1",
                "receipt_id": receipt_id,
                "product_release_id": PRODUCT_RELEASE_ID,
                "source_commit": COMMIT_SHA,
                "mode": "live",
                "status": "passed",
                "exit_code": 0,
                "command": ["releasefoundry-release-test", receipt_id],
                "started_at": "2026-07-19T00:00:00Z",
                "finished_at": "2026-07-19T00:00:01Z",
                "environment": environment,
            },
        )
        receipts[receipt_id] = file_ref(root, receipt)

    supply_chain = {
        "sbom": file_ref(root, artifacts["web.sbom.json"]),
        "signature": file_ref(root, artifacts["web.signature.json"]),
        "provenance": file_ref(root, artifacts["web.provenance.json"]),
    }
    manifest = {
        "schema_version": "releasefoundry.product_release_manifest.v1",
        "product_release_id": PRODUCT_RELEASE_ID,
        "generated_at": "2026-07-19T00:00:02Z",
        "policy": {
            "id": policy["policy_id"],
            **file_ref(root, policy_path),
        },
        "source": {
            "repository": "https://github.com/3351666087/release-foundry",
            "commit_sha": COMMIT_SHA,
            "dirty": False,
        },
        "deployment": {
            "bundle": file_ref(root, artifacts["bundle.tar.gz"]),
            "compose": file_ref(root, artifacts["docker-compose.yml"]),
            "installers": {
                "posix": file_ref(root, artifacts["install.sh"]),
                "powershell": file_ref(root, artifacts["install.ps1"]),
            },
            "services": [
                {
                    "name": "web",
                    "image": "ghcr.io/example/releasefoundry-web",
                    "digest": f"sha256:{'1' * 64}",
                    "roles": ["web"],
                    "ownership": "releasefoundry",
                    "supply_chain": supply_chain,
                },
                {
                    "name": "api-worker",
                    "image": "ghcr.io/example/releasefoundry-runtime",
                    "digest": f"sha256:{'2' * 64}",
                    "roles": ["api", "worker", "migration"],
                    "ownership": "releasefoundry",
                    "supply_chain": supply_chain,
                },
                {
                    "name": "postgres",
                    "image": "postgres",
                    "digest": f"sha256:{'3' * 64}",
                    "roles": ["database"],
                    "ownership": "third_party",
                },
                {
                    "name": "redis",
                    "image": "redis",
                    "digest": f"sha256:{'4' * 64}",
                    "roles": ["cache"],
                    "ownership": "third_party",
                },
                {
                    "name": "minio",
                    "image": "minio/minio",
                    "digest": f"sha256:{'5' * 64}",
                    "roles": ["object_store"],
                    "ownership": "third_party",
                },
            ],
        },
        "sdks": [
            {
                "language": "python",
                "package": "releasefoundry",
                "version": "1.0.0",
                "artifact": file_ref(root, artifacts["python.whl"]),
            },
            {
                "language": "typescript",
                "package": "@releasefoundry/clone",
                "version": "1.0.0",
                "artifact": file_ref(root, artifacts["typescript.tgz"]),
            },
            {
                "language": "go",
                "package": "github.com/releasefoundry/releasefoundry",
                "version": "1.0.0",
                "artifact": file_ref(root, artifacts["go.zip"]),
            },
        ],
        "runbooks": runbooks,
        "verification": {"receipts": receipts},
    }
    manifest_path = release_dir / "manifest.json"
    write_json(manifest_path, manifest)
    return root, manifest_path


def test_complete_live_product_release_is_approved(tmp_path: Path) -> None:
    root, manifest_path = build_complete_release(tmp_path)
    policy = json.loads(POLICY_SOURCE.read_text(encoding="utf-8"))

    result = verify_product_release_manifest(manifest_path, repo_root=root)

    assert result["decision"] == "approve_product_release"
    assert result["product_release_id"] == PRODUCT_RELEASE_ID
    assert result["product_release_manifest_sha256"] == sha256_file(manifest_path)
    assert result["blocking_reasons"] == []
    assert len(result["checked_receipt_ids"]) == len(policy["required_receipts"])


def test_customer_agent_release_id_cannot_impersonate_product_release(tmp_path: Path) -> None:
    root, manifest_path = build_complete_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["product_release_id"] = "agent-release:acme/support-agent@1.0.0"
    write_json(manifest_path, manifest)

    result = verify_product_release_manifest(manifest_path, repo_root=root)

    assert result["decision"] == "block_product_release"
    assert "invalid_product_release_id" in result["blocking_reasons"]
    assert "receipt_release_mismatch" in result["blocking_reasons"]


def test_fixture_or_mock_receipt_cannot_satisfy_release_policy(tmp_path: Path) -> None:
    root, manifest_path = build_complete_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt_id = "evaluation.multimodal_live"
    fixture_path = root / "fixtures" / "fake-multimodal-pass.json"
    write_json(
        fixture_path,
        {
            "schema_version": "releasefoundry.verification_receipt.v1",
            "receipt_id": receipt_id,
            "product_release_id": PRODUCT_RELEASE_ID,
            "source_commit": COMMIT_SHA,
            "mode": "live",
            "status": "passed",
            "exit_code": 0,
            "command": ["fake"],
            "started_at": "2026-07-19T00:00:00Z",
            "finished_at": "2026-07-19T00:00:01Z",
            "environment": {"os": "linux", "arch": "amd64"},
        },
    )
    manifest["verification"]["receipts"][receipt_id] = file_ref(root, fixture_path)
    write_json(manifest_path, manifest)

    result = verify_product_release_manifest(manifest_path, repo_root=root)

    assert result["decision"] == "block_product_release"
    assert "non_release_evidence" in result["blocking_reasons"]


def test_hash_mismatch_and_non_live_receipt_fail_closed(tmp_path: Path) -> None:
    root, manifest_path = build_complete_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt_id = "billing.stripe_test_mode"
    receipt_ref = manifest["verification"]["receipts"][receipt_id]
    receipt_path = root / receipt_ref["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["mode"] = "mock"
    write_json(receipt_path, receipt)

    result = verify_product_release_manifest(manifest_path, repo_root=root)

    assert result["decision"] == "block_product_release"
    assert "evidence_digest_mismatch" in result["blocking_reasons"]
    assert "non_live_receipt" in result["blocking_reasons"]


def test_cli_returns_two_for_blocked_release(tmp_path: Path) -> None:
    root, manifest_path = build_complete_release(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["verification"]["receipts"]["operations.rollback"]
    write_json(manifest_path, manifest)

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify_product_release.py"),
            "--manifest",
            str(manifest_path),
            "--repo-root",
            str(root),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    output = json.loads(completed.stdout)
    assert output["decision"] == "block_product_release"
    assert "missing_receipt" in output["blocking_reasons"]
