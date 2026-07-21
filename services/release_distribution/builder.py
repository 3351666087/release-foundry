"""Reproducible dual Release candidate builder.

The builder creates two independent GitHub Release asset sets. Verification
decisions remain fail-closed and are packaged even when they are NO-GO.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
from typing import Any, Iterable, Mapping, Sequence
import zipfile

from services.customer_release import verify_customer_agent_release_manifest
from services.product_release import verify_product_release_manifest, verify_web_production_surface


DUAL_RELEASE_INDEX_SCHEMA = "ashr.dual_release_index.v1"
DUAL_RELEASE_INDEX_VERIFICATION_SCHEMA = "ashr.dual_release_index_verification.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_VERSION_RE = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
_SOURCE_PREFIXES = (
    "apps/webapp/",
    "infra/docker/",
    "infra/install/",
    "infra/kubernetes/",
    "packages/go/ashrclone/",
    "packages/rust/ashr-runtime-verify/",
    "packages/sdk/",
    "packages/ts/ashr-clone/",
    "scripts/",
    "services/",
    "docs/operations/",
    "docs/releases/",
)
_SOURCE_FILES = {
    ".gitattributes",
    ".gitignore",
    "README.md",
    "package-lock.json",
    "package.json",
    "playwright.config.ts",
    "requirements-ci.txt",
}
_SOURCE_EXCLUDES = (
    "docs/screenshots/",
    "docs/a1/_pypi_artifacts/",
    "tests/",
    "fixtures/",
    "node_modules/",
)
_RUNBOOKS = {
    "install": "docs/operations/install.md",
    "configuration": "docs/operations/configuration.md",
    "backup_restore": "docs/operations/backup_restore.md",
    "upgrade": "docs/operations/upgrade.md",
    "rollback": "docs/operations/rollback.md",
    "incident_response": "docs/operations/incident_response.md",
}
_CUSTOMER_EVIDENCE = {
    "a1_run_result": "a3_new_run_result.redacted.json",
    "a1_candidate_run_receipt": "a1_candidate_run_receipt.json",
    "a2_trusted_spine": "a2_trusted_spine_handoff.snapshot.json",
    "a3_shared_candidate_identity": "a3_shared_candidate_identity.json",
    "a3_candidate_delivery_binding": "a3_candidate_delivery_binding.json",
    "a3_gate_report": "gate-report.json",
    "a3_release_artifact_verification": "release-artifact-verification.json",
    "a3_release_delivery_index": "release-delivery-index.json",
    "a3_audit_bundle_index": "audit-bundle-index.json",
    "a3_audit_archive_manifest": "audit-archive-manifest.json",
}


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))
    return path


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_ref(root: Path, path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_file(path),
    }


def _safe_slug(value: str, field: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", normalized):
        raise ValueError(f"{field} must be a lowercase release slug")
    return normalized


def _validate_version(value: str, field: str) -> str:
    if not _VERSION_RE.fullmatch(value):
        raise ValueError(f"{field} must be SemVer")
    return value


def _reset_directory(path: Path, output_root: Path) -> None:
    resolved = path.resolve()
    root = output_root.resolve()
    if resolved.parent != root:
        raise ValueError("release directory must be a direct child of output_root")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _tracked_files(repo_root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    paths = []
    for raw in completed.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8")
        if relative in _SOURCE_FILES or relative.startswith(_SOURCE_PREFIXES):
            if not relative.startswith(_SOURCE_EXCLUDES):
                path = repo_root / Path(*PurePosixPath(relative).parts)
                if path.is_file():
                    paths.append(path)
    return sorted(paths, key=lambda item: item.relative_to(repo_root).as_posix())


def _tree_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted((path for path in root.rglob("*") if path.is_file()), key=lambda item: item.relative_to(root).as_posix())


def _zip_info(name: str, *, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, _ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
    return info


def _write_zip(
    destination: Path,
    entries: Sequence[tuple[Path, str]],
    *,
    virtual_entries: Mapping[str, bytes] | None = None,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, name in sorted(entries, key=lambda item: item[1]):
            normalized = PurePosixPath(name).as_posix()
            executable = source.suffix in {".sh", ".ps1"}
            archive.writestr(_zip_info(normalized, executable=executable), source.read_bytes())
        for name, content in sorted((virtual_entries or {}).items()):
            archive.writestr(_zip_info(PurePosixPath(name).as_posix()), content)
    return destination


def _zip_tree(destination: Path, root: Path, *, prefix: str = "") -> Path:
    entries = [
        (path, PurePosixPath(prefix, path.relative_to(root).as_posix()).as_posix())
        for path in _tree_files(root)
    ]
    return _write_zip(destination, entries)


def _copy(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _archive_selected_tree(
    destination: Path,
    root: Path,
    paths: Iterable[Path],
    *,
    prefix: str = "",
) -> Path:
    entries = [
        (path, PurePosixPath(prefix, path.relative_to(root).as_posix()).as_posix())
        for path in paths
    ]
    return _write_zip(destination, entries)


def _sdk_version(repo_root: Path, language: str) -> str:
    if language == "typescript":
        package = json.loads((repo_root / "packages/ts/ashr-clone/package.json").read_text(encoding="utf-8"))
        return str(package["version"])
    if language == "python":
        text = (repo_root / "packages/sdk/pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
        return match.group(1) if match else "unknown"
    return "0.1.0"


def _build_product_candidate(
    repo_root: Path,
    output_root: Path,
    *,
    product_version: str,
    source_commit: str,
    generated_at: str,
    source_dirty: bool,
) -> tuple[Path, dict[str, Any], list[Path]]:
    product_name = f"ashr-product-{product_version}"
    product_id = f"ashr-product@{product_version}"
    product_dir = output_root / product_name
    _reset_directory(product_dir, output_root)
    artifacts = product_dir / "artifacts"
    supply_chain = product_dir / "supply-chain"
    receipts = product_dir / "receipts"
    runbooks_dir = product_dir / "runbooks"

    source_zip = _archive_selected_tree(
        artifacts / f"{product_name}-source.zip",
        repo_root,
        _tracked_files(repo_root),
        prefix=product_name,
    )
    web_root = repo_root / "apps/webapp/out"
    web_zip = artifacts / f"ashr-webapp-{product_version}.zip"
    if web_root.exists() and _tree_files(web_root):
        _zip_tree(web_zip, web_root, prefix="web")
    else:
        _write_zip(
            web_zip,
            [],
            virtual_entries={
                "WEB_BUILD_REQUIRED.txt": b"Run npm ci and npm run build in apps/webapp before release.\n"
            },
        )

    python_paths = [
        path
        for path in _tree_files(repo_root / "packages/sdk")
        if "__pycache__" not in path.parts
        and "build" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
        and path.suffix not in {".pyc", ".pyo"}
    ]
    python_zip = _archive_selected_tree(
        artifacts / f"ashr-python-sdk-{_sdk_version(repo_root, 'python')}.zip",
        repo_root / "packages/sdk",
        python_paths,
        prefix="ashr-python-sdk",
    )
    ts_root = repo_root / "packages/ts/ashr-clone"
    ts_paths = _tree_files(ts_root / "dist")
    ts_paths += [path for path in (ts_root / "package.json", ts_root / "README.md") if path.exists()]
    if not ts_paths:
        ts_paths = [path for path in _tree_files(ts_root) if "node_modules" not in path.parts]
    ts_zip = _archive_selected_tree(
        artifacts / f"ashr-typescript-sdk-{_sdk_version(repo_root, 'typescript')}.zip",
        ts_root,
        sorted(set(ts_paths)),
        prefix="ashr-typescript-sdk",
    )
    go_root = repo_root / "packages/go/ashrclone"
    go_zip = _archive_selected_tree(
        artifacts / "ashr-go-sdk-0.1.0.zip",
        go_root,
        _tree_files(go_root),
        prefix="ashr-go-sdk",
    )
    rust_root = repo_root / "packages/rust/ashr-runtime-verify"
    rust_paths = [path for path in _tree_files(rust_root) if "target" not in path.parts]
    rust_zip = _archive_selected_tree(
        artifacts / "ashr-runtime-verify-0.1.0.zip",
        rust_root,
        rust_paths,
        prefix="ashr-runtime-verify",
    )

    compose = _copy(
        repo_root / "infra/docker/docker-compose.self-host.yml",
        artifacts / "docker-compose.self-host.yml",
    )
    env_example = _copy(
        repo_root / "infra/docker/self-host.env.example",
        artifacts / "self-host.env.example",
    )
    install_sh = _copy(repo_root / "infra/install/install.sh", artifacts / "install.sh")
    install_ps1 = _copy(repo_root / "infra/install/install.ps1", artifacts / "install.ps1")
    runtime_bundle = _write_zip(
        artifacts / f"{product_name}-runtime.zip",
        [
            (compose, "infra/docker/docker-compose.self-host.yml"),
            (env_example, "infra/docker/self-host.env.example"),
            (install_sh, "infra/install/install.sh"),
            (install_ps1, "infra/install/install.ps1"),
            (source_zip, f"packages/{source_zip.name}"),
            (web_zip, f"packages/{web_zip.name}"),
            (python_zip, f"packages/{python_zip.name}"),
            (ts_zip, f"packages/{ts_zip.name}"),
            (go_zip, f"packages/{go_zip.name}"),
            (rust_zip, f"packages/{rust_zip.name}"),
        ],
    )

    runbook_refs: dict[str, dict[str, str]] = {}
    for name, relative in _RUNBOOKS.items():
        copied = _copy(repo_root / relative, runbooks_dir / f"{name}.md")
        runbook_refs[name] = _file_ref(product_dir, copied)
    policy = _copy(
        repo_root / "docs/releases/ashr_product_release_policy.v1.json",
        product_dir / "policy/ashr_product_release_policy.v1.json",
    )

    artifact_files = sorted(artifacts.glob("*"), key=lambda path: path.name)
    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": product_name,
        "documentNamespace": f"urn:ashr:sbom:{source_commit}:{product_version}",
        "creationInfo": {"created": generated_at, "creators": ["Tool: ashr-dual-release-builder"]},
        "files": [
            {
                "SPDXID": f"SPDXRef-File-{index}",
                "fileName": f"artifacts/{path.name}",
                "checksums": [{"algorithm": "SHA256", "checksumValue": _sha256_file(path)}],
            }
            for index, path in enumerate(artifact_files, start=1)
        ],
    }
    sbom_path = _write_json(supply_chain / f"{product_name}.spdx.json", sbom)
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {"name": f"artifacts/{path.name}", "digest": {"sha256": _sha256_file(path)}}
            for path in artifact_files
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://ashr.example/release/dual-candidate/v1",
                "externalParameters": {"product_release_id": product_id},
                "resolvedDependencies": [
                    {
                        "uri": "https://github.com/3351666087/ashr-codex-factory",
                        "digest": {"gitCommit": source_commit},
                    }
                ],
            },
            "runDetails": {
                "builder": {"id": "ashr-dual-release-builder"},
                "metadata": {"invocationId": f"{product_id}:{source_commit}"},
            },
        },
    }
    provenance_path = _write_json(supply_chain / f"{product_name}.provenance.json", provenance)

    web_result = verify_web_production_surface(repo_root / "apps/webapp", repo_root=repo_root)
    web_receipt = {
        "schema_version": "ashr.verification_receipt.v1",
        "receipt_id": "web.production_surface",
        "product_release_id": product_id,
        "source_commit": source_commit,
        "mode": "live",
        "status": "passed" if web_result["decision"] == "approve_web_surface" else "failed",
        "exit_code": 0 if web_result["decision"] == "approve_web_surface" else 2,
        "command": ["python", "scripts/check_web_release_surface.py", "--web-root", "apps/webapp"],
        "started_at": generated_at,
        "finished_at": generated_at,
        "environment": {"os": platform.system().lower(), "arch": platform.machine().lower()},
        "verification": web_result,
    }
    web_receipt_path = _write_json(receipts / "web.production_surface.json", web_receipt)
    supply_chain_refs = {
        "sbom": _file_ref(product_dir, sbom_path),
        "signature": {},
        "provenance": _file_ref(product_dir, provenance_path),
    }
    manifest = {
        "schema_version": "ashr.product_release_manifest.v1",
        "product_release_id": product_id,
        "generated_at": generated_at,
        "policy": {
            "id": "ashr.product_release.enterprise.v1",
            **_file_ref(product_dir, policy),
        },
        "source": {
            "repository": "https://github.com/3351666087/ashr-codex-factory",
            "commit_sha": source_commit,
            "dirty": source_dirty,
        },
        "deployment": {
            "bundle": _file_ref(product_dir, runtime_bundle),
            "compose": _file_ref(product_dir, compose),
            "configuration_example": _file_ref(product_dir, env_example),
            "installers": {
                "posix": _file_ref(product_dir, install_sh),
                "powershell": _file_ref(product_dir, install_ps1),
            },
            "services": [
                {
                    "name": "web",
                    "image": "ashr/web:release-candidate",
                    "digest": "unavailable",
                    "roles": ["web"],
                    "ownership": "ashr",
                    "supply_chain": supply_chain_refs,
                },
                {
                    "name": "api-worker",
                    "image": "ashr/runtime:release-candidate",
                    "digest": "unavailable",
                    "roles": ["api", "worker", "migration"],
                    "ownership": "ashr",
                    "supply_chain": supply_chain_refs,
                },
                {
                    "name": "postgres",
                    "image": "postgres:16-alpine",
                    "digest": "unavailable",
                    "roles": ["database"],
                    "ownership": "third_party",
                },
                {
                    "name": "redis",
                    "image": "redis:7-alpine",
                    "digest": "unavailable",
                    "roles": ["cache"],
                    "ownership": "third_party",
                },
                {
                    "name": "minio",
                    "image": "minio/minio:RELEASE.2025-04-22T22-12-26Z",
                    "digest": "unavailable",
                    "roles": ["object_store"],
                    "ownership": "third_party",
                },
            ],
        },
        "sdks": [
            {
                "language": "python",
                "package": "ashr-clone-sdk",
                "version": _sdk_version(repo_root, "python"),
                "artifact": _file_ref(product_dir, python_zip),
            },
            {
                "language": "typescript",
                "package": "@ashr-clone/sdk",
                "version": _sdk_version(repo_root, "typescript"),
                "artifact": _file_ref(product_dir, ts_zip),
            },
            {
                "language": "go",
                "package": "github.com/ashr-labs/ashr/packages/go/ashrclone",
                "version": "0.1.0",
                "artifact": _file_ref(product_dir, go_zip),
            },
        ],
        "runbooks": runbook_refs,
        "verification": {
            "receipts": {"web.production_surface": _file_ref(product_dir, web_receipt_path)}
        },
    }
    manifest_path = _write_json(product_dir / "manifest.json", manifest)
    verification = verify_product_release_manifest(manifest_path, repo_root=product_dir)
    verification_path = _write_json(product_dir / "verification.json", verification)
    notes = _product_notes(product_id, source_commit, verification)
    notes_path = product_dir / "RELEASE_NOTES.md"
    notes_path.write_text(notes, encoding="utf-8")

    archive_path = _zip_tree(output_root / f"{product_name}.zip", product_dir, prefix=product_name)
    external = [
        archive_path,
        _copy(manifest_path, output_root / f"{product_name}.manifest.json"),
        _copy(verification_path, output_root / f"{product_name}.verification.json"),
        _copy(sbom_path, output_root / f"{product_name}.spdx.json"),
        _copy(provenance_path, output_root / f"{product_name}.provenance.json"),
        _copy(notes_path, output_root / f"{product_name}.release-notes.md"),
    ]
    return product_dir, verification, external


def _build_customer_candidate(
    repo_root: Path,
    output_root: Path,
    *,
    product_dir: Path,
    product_verification: Mapping[str, Any],
    agent_version: str,
    agent_org: str,
    agent_name: str,
    source_commit: str,
    generated_at: str,
    source_dirty: bool,
) -> tuple[Path, dict[str, Any], list[Path]]:
    customer_name = f"agent-release-{agent_org}-{agent_name}-{agent_version}"
    customer_id = f"agent-release:{agent_org}/{agent_name}@{agent_version}"
    customer_dir = output_root / customer_name
    _reset_directory(customer_dir, output_root)
    evidence_dir = customer_dir / "evidence"
    binding_dir = customer_dir / "product-binding"
    source_evidence = repo_root / "fixtures/a3/golden-path/rc3"
    a1_receipt = json.loads((source_evidence / "a1_candidate_run_receipt.json").read_text(encoding="utf-8"))
    a2_spine = json.loads((source_evidence / "a2_trusted_spine_handoff.snapshot.json").read_text(encoding="utf-8"))
    delivery_binding = json.loads((source_evidence / "a3_candidate_delivery_binding.json").read_text(encoding="utf-8"))
    a3_identity = json.loads((source_evidence / "a3_shared_candidate_identity.json").read_text(encoding="utf-8"))
    candidate_binding = delivery_binding["candidate"]
    upstream_binding = delivery_binding["upstream"]
    a3_binding = delivery_binding["a3"]
    expected_candidate_id = f"{agent_name}@{agent_version}"
    if candidate_binding.get("candidate_id") != expected_candidate_id:
        raise ValueError("requested Agent version does not match the sealed rc.3 candidate")

    evidence_refs: dict[str, dict[str, str]] = {}
    for evidence_id, filename in _CUSTOMER_EVIDENCE.items():
        copied = _copy(source_evidence / filename, evidence_dir / filename)
        evidence_refs[evidence_id] = _file_ref(customer_dir, copied)
    product_manifest = _copy(product_dir / "manifest.json", binding_dir / "manifest.json")
    product_verification_path = _copy(
        product_dir / "verification.json",
        binding_dir / "verification.json",
    )
    product_manifest_hash = _sha256_file(product_manifest)

    manifest = {
        "schema_version": "ashr.customer_agent_release_manifest.v1",
        "agent_release_id": customer_id,
        "generated_at": generated_at,
        "source": {
            "repository": "https://github.com/3351666087/ashr-codex-factory",
            "commit_sha": source_commit,
            "dirty": source_dirty,
        },
        "tenant_scope": {
            field: a2_spine["decision_ledger"][field]
            for field in (
                "organization_id",
                "tenant_id",
                "workspace_id",
                "project_id",
                "environment_id",
            )
        },
        "candidate": {
            "agent_id": agent_name,
            "version": agent_version,
            "candidate_id": f"{agent_name}@{agent_version}",
            "run_id": candidate_binding["run_id"],
            "source_commit": upstream_binding["a1_source_commit"],
            "evidence_release_version": candidate_binding["release_version"],
        },
        "lane_bindings": {
            "release_package_commit": source_commit,
            "a1_candidate_source_commit": upstream_binding["a1_source_commit"],
            "a1_evidence_bundle_hash": upstream_binding["a1_evidence_bundle_hash"],
            "a2_authority_commit": upstream_binding["a2_authority_commit"],
            "a2_decision_ledger_head_hash": upstream_binding["a2_decision_ledger_head_hash"],
            "a2_grades_hash": upstream_binding["a2_grades_hash"],
            "a3_implementation_commit": a3_binding["implementation_commit"],
        },
        "product_binding": {
            "product_release_id": product_verification.get("product_release_id"),
            "product_release_manifest_sha256": product_manifest_hash,
            "manifest": _file_ref(customer_dir, product_manifest),
            "verification": _file_ref(customer_dir, product_verification_path),
        },
        "evidence": evidence_refs,
        "human_review": {
            "status": "not_approved",
            "approval_receipt": None,
        },
        "authority": {
            "decision_authority": "A2 Decision Ledger",
            "a3_recomputed_a2_decision": False,
            "candidate_binding_verified": delivery_binding.get("binding_state") == "exact"
            and a3_identity.get("binding_state") == "exact"
            and a1_receipt.get("candidate_binding", {}).get("candidate_id") == expected_candidate_id,
        },
        "safety": {
            "public_safe": True,
            "raw_secrets_included": False,
            "raw_identity_included": False,
            "raw_media_included": False,
            "signed_url_included": False,
        },
    }
    manifest_path = _write_json(customer_dir / "manifest.json", manifest)
    verification = verify_customer_agent_release_manifest(manifest_path, release_root=customer_dir)
    verification_path = _write_json(customer_dir / "verification.json", verification)
    notes_path = customer_dir / "RELEASE_NOTES.md"
    notes_path.write_text(
        _customer_notes(customer_id, source_commit, verification, product_verification),
        encoding="utf-8",
    )
    archive_path = _zip_tree(output_root / f"{customer_name}.zip", customer_dir, prefix=customer_name)
    external = [
        archive_path,
        _copy(manifest_path, output_root / f"{customer_name}.manifest.json"),
        _copy(verification_path, output_root / f"{customer_name}.verification.json"),
        _copy(notes_path, output_root / f"{customer_name}.release-notes.md"),
    ]
    return customer_dir, verification, external


def _product_notes(product_id: str, source_commit: str, verification: Mapping[str, Any]) -> str:
    decision = str(verification.get("decision"))
    blockers = verification.get("blocking_reasons") if isinstance(verification.get("blocking_reasons"), list) else []
    lines = [
        f"# {product_id}",
        "",
        f"**Decision: {'GO' if decision == 'approve_product_release' else 'NO-GO'}**",
        "",
        f"Source commit: `{source_commit}`",
        "",
        "This is an independently versioned Ashr Product Release candidate. It contains the product runtime source, Web build, SDK archives, Docker Compose, installers, operator runbooks, SBOM, provenance, manifest, and verification output.",
        "",
    ]
    if blockers:
        lines.extend(["## Blocking reasons", ""] + [f"- `{item}`" for item in blockers] + [""])
    lines.extend(
        [
            "A GitHub prerelease does not override the verification decision. Missing live receipts, immutable image digests, or signatures keep this candidate out of production.",
            "",
        ]
    )
    return "\n".join(lines)


def _customer_notes(
    release_id: str,
    source_commit: str,
    verification: Mapping[str, Any],
    product_verification: Mapping[str, Any],
) -> str:
    decision = str(verification.get("decision"))
    blockers = verification.get("blocking_reasons") if isinstance(verification.get("blocking_reasons"), list) else []
    lines = [
        f"# {release_id}",
        "",
        f"**Decision: {'GO' if decision == 'approve_customer_agent_release' else 'NO-GO'}**",
        "",
        f"Source commit: `{source_commit}`",
        f"Bound Product Release decision: `{product_verification.get('decision')}`",
        f"A2 authoritative decision: `{verification.get('a2_authoritative_decision')}`",
        "",
        "This customer evidence release contains hash-bound copies of the A1 run, A2 trusted spine and Decision Ledger, A3 gate and artifact verification, and audit manifests. A3 does not recompute the A2 decision.",
        "",
    ]
    if blockers:
        lines.extend(["## Blocking reasons", ""] + [f"- `{item}`" for item in blockers] + [""])
    lines.extend(
        [
            "This demo customer candidate must not be deployed while either the Product Release or Customer Agent Release verification is NO-GO.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_checksums(output_root: Path, name: str, assets: Sequence[Path]) -> Path:
    path = output_root / name
    lines = [f"{_sha256_file(asset)}  {asset.name}" for asset in sorted(assets, key=lambda item: item.name)]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def _asset_records(output_root: Path, assets: Sequence[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": asset.relative_to(output_root).as_posix(),
            "sha256": _sha256_file(asset),
            "byte_size": asset.stat().st_size,
        }
        for asset in sorted(assets, key=lambda item: item.name)
    ]


def build_dual_release_candidates(
    repo_root: str | Path,
    output_root: str | Path,
    *,
    product_version: str = "1.0.0-rc.1",
    agent_version: str = "0.2.0-rc.3",
    agent_org: str = "demo",
    agent_name: str = "a3-golden-agent",
    source_commit: str | None = None,
    generated_at: str | None = None,
    allow_dirty: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    output = Path(output_root).resolve()
    product_version = _validate_version(product_version, "product_version")
    agent_version = _validate_version(agent_version, "agent_version")
    agent_org = _safe_slug(agent_org, "agent_org")
    agent_name = _safe_slug(agent_name, "agent_name")
    commit = source_commit or _git(root, "rev-parse", "HEAD")
    if not _COMMIT_RE.fullmatch(commit):
        raise ValueError("source_commit must be a full Git SHA")
    if commit != _git(root, "rev-parse", "HEAD"):
        raise ValueError("source_commit must match repository HEAD")
    source_dirty = bool(_git(root, "status", "--porcelain"))
    if not allow_dirty and source_dirty:
        raise ValueError("release source has tracked changes")
    timestamp = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("generated_at must be timezone-aware RFC 3339")
    output.mkdir(parents=True, exist_ok=True)

    product_dir, product_verification, product_assets = _build_product_candidate(
        root,
        output,
        product_version=product_version,
        source_commit=commit,
        generated_at=timestamp,
        source_dirty=source_dirty,
    )
    customer_dir, customer_verification, customer_assets = _build_customer_candidate(
        root,
        output,
        product_dir=product_dir,
        product_verification=product_verification,
        agent_version=agent_version,
        agent_org=agent_org,
        agent_name=agent_name,
        source_commit=commit,
        generated_at=timestamp,
        source_dirty=source_dirty,
    )
    product_checksums = _write_checksums(
        output,
        f"ashr-product-{product_version}.SHA256SUMS.txt",
        product_assets,
    )
    customer_checksums = _write_checksums(
        output,
        f"agent-release-{agent_org}-{agent_name}-{agent_version}.SHA256SUMS.txt",
        customer_assets,
    )
    product_assets = [*product_assets, product_checksums]
    customer_assets = [*customer_assets, customer_checksums]
    index = {
        "schema_version": DUAL_RELEASE_INDEX_SCHEMA,
        "generated_at": timestamp,
        "source": {
            "repository": "https://github.com/3351666087/ashr-codex-factory",
            "commit_sha": commit,
            "dirty": source_dirty,
        },
        "product_release": {
            "release_id": product_verification.get("product_release_id"),
            "tag": f"ashr-product-v{product_version}",
            "github_prerelease": True,
            "decision": product_verification.get("decision"),
            "go_no_go": "GO" if product_verification.get("decision") == "approve_product_release" else "NO-GO",
            "release_root": product_dir.relative_to(output).as_posix(),
            "manifest_sha256": product_verification.get("product_release_manifest_sha256"),
            "assets": _asset_records(output, product_assets),
        },
        "customer_agent_release": {
            "release_id": customer_verification.get("agent_release_id"),
            "tag": f"customer-agent-{agent_org}-{agent_name}-v{agent_version}",
            "github_prerelease": True,
            "decision": customer_verification.get("decision"),
            "go_no_go": "GO" if customer_verification.get("decision") == "approve_customer_agent_release" else "NO-GO",
            "release_root": customer_dir.relative_to(output).as_posix(),
            "manifest_sha256": customer_verification.get("agent_release_manifest_sha256"),
            "product_release_manifest_sha256": product_verification.get("product_release_manifest_sha256"),
            "assets": _asset_records(output, customer_assets),
        },
        "authority": {
            "independent_decisions": True,
            "customer_depends_on_approved_product": True,
            "product_depends_on_customer": False,
            "a3_recomputed_a2_decision": False,
        },
    }
    _write_json(output / "dual-release-index.json", index)
    verification = verify_release_index(output / "dual-release-index.json")
    _write_json(output / "dual-release-index.verification.json", verification)
    if verification["status"] != "passed":
        raise ValueError("generated dual Release index failed self-verification")
    return index


def verify_release_index(index_path: str | Path) -> dict[str, Any]:
    path = Path(index_path).resolve()
    root = path.parent
    issues: list[dict[str, str]] = []
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "schema_version": DUAL_RELEASE_INDEX_VERIFICATION_SCHEMA,
            "status": "failed",
            "issues": [{"code": "index_read_failed", "path": "$", "message": str(exc)}],
        }
    if index.get("schema_version") != DUAL_RELEASE_INDEX_SCHEMA:
        issues.append({"code": "unsupported_schema", "path": "schema_version", "message": "schema mismatch"})
    source = index.get("source") if isinstance(index.get("source"), Mapping) else {}
    warnings: list[dict[str, str]] = []
    if not _COMMIT_RE.fullmatch(str(source.get("commit_sha") or "")):
        issues.append({"code": "invalid_source", "path": "source.commit_sha", "message": "source must be pinned"})
    if not isinstance(source.get("dirty"), bool):
        issues.append({"code": "invalid_source", "path": "source.dirty", "message": "must be boolean"})
    elif source.get("dirty") is True:
        warnings.append({"code": "source_dirty_development_build", "path": "source.dirty", "message": "not publishable"})
    for release_key in ("product_release", "customer_agent_release"):
        release = index.get(release_key) if isinstance(index.get(release_key), Mapping) else {}
        if release.get("go_no_go") not in {"GO", "NO-GO"}:
            issues.append({"code": "invalid_decision", "path": release_key, "message": "GO/NO-GO required"})
        assets = release.get("assets") if isinstance(release.get("assets"), list) else []
        if not assets:
            issues.append({"code": "missing_assets", "path": f"{release_key}.assets", "message": "must be non-empty"})
        for index_number, item in enumerate(assets):
            item_path = f"{release_key}.assets[{index_number}]"
            if not isinstance(item, Mapping):
                issues.append({"code": "invalid_asset", "path": item_path, "message": "must be an object"})
                continue
            raw_path = item.get("path")
            portable = PurePosixPath(str(raw_path or ""))
            if portable.is_absolute() or ".." in portable.parts or not raw_path:
                issues.append({"code": "unsafe_asset_path", "path": item_path, "message": "invalid path"})
                continue
            resolved = (root / Path(*portable.parts)).resolve()
            if root not in resolved.parents:
                issues.append({"code": "unsafe_asset_path", "path": item_path, "message": "path escapes"})
                continue
            if not resolved.is_file():
                issues.append({"code": "missing_asset", "path": item_path, "message": str(raw_path)})
                continue
            expected_hash = item.get("sha256")
            if not isinstance(expected_hash, str) or not _SHA256_RE.fullmatch(expected_hash):
                issues.append({"code": "invalid_asset_digest", "path": item_path, "message": "SHA-256 required"})
            elif _sha256_file(resolved) != expected_hash:
                issues.append({"code": "asset_digest_mismatch", "path": item_path, "message": str(raw_path)})
            if item.get("byte_size") != resolved.stat().st_size:
                issues.append({"code": "asset_size_mismatch", "path": item_path, "message": str(raw_path)})
            if resolved.suffix == ".zip":
                try:
                    with zipfile.ZipFile(resolved) as archive:
                        failed = archive.testzip()
                    if failed:
                        issues.append({"code": "zip_integrity_failed", "path": item_path, "message": failed})
                except (OSError, zipfile.BadZipFile) as exc:
                    issues.append({"code": "zip_integrity_failed", "path": item_path, "message": str(exc)})
    return {
        "schema_version": DUAL_RELEASE_INDEX_VERIFICATION_SCHEMA,
        "status": "passed" if not issues else "failed",
        "asset_count": sum(
            len(index.get(key, {}).get("assets", []))
            for key in ("product_release", "customer_agent_release")
            if isinstance(index.get(key), Mapping)
        ),
        "warnings": warnings,
        "issues": issues,
    }
