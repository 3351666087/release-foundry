#!/usr/bin/env python3
"""Verify A1 deterministic SBOM/provenance evidence and optional Git binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SECRET_MARKERS = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "Authorization: Bearer",
    "password=",
    "private_refs/",
)


class VerificationError(RuntimeError):
    pass


def load_json(path: Path) -> Mapping[str, Any]:
    if path.stat().st_size > 64 * 1024 * 1024:
        raise VerificationError(f"evidence file is too large: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid JSON evidence: {path.name}") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"evidence root must be an object: {path.name}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo_root: Path, args: Sequence[str], *, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise VerificationError(f"git {' '.join(args[:2])} failed")
    return completed.stdout if binary else completed.stdout.decode("utf-8", errors="strict").strip()


def require_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise VerificationError(f"{label} is not a SHA-256 digest")
    return value


def verify(directory: Path, repo_root: Path | None, check_git: bool) -> dict[str, Any]:
    manifest_path = directory / "ashr-a1-runtime.release-manifest.json"
    sbom_path = directory / "ashr-a1-runtime.spdx.json"
    provenance_path = directory / "ashr-a1-runtime.provenance.json"
    manifest = load_json(manifest_path)
    sbom = load_json(sbom_path)
    provenance = load_json(provenance_path)

    if manifest.get("schema_version") != "ashr.a1.release_evidence.v1":
        raise VerificationError("unsupported release manifest schema")
    if manifest.get("deterministic") is not True or manifest.get("secret_values_included") is not False:
        raise VerificationError("release manifest safety flags are invalid")
    if sbom.get("spdxVersion") != "SPDX-2.3" or sbom.get("SPDXID") != "SPDXRef-DOCUMENT":
        raise VerificationError("SBOM is not an SPDX 2.3 document")
    if provenance.get("_type") != "https://in-toto.io/Statement/v1":
        raise VerificationError("provenance is not an in-toto v1 statement")
    if provenance.get("predicateType") != "https://slsa.dev/provenance/v1":
        raise VerificationError("provenance is not a SLSA v1 predicate")

    artifacts = manifest.get("artifacts", {})
    expected_sbom = require_digest(artifacts.get("sbom", {}).get("sha256"), "SBOM manifest digest")
    expected_provenance = require_digest(
        artifacts.get("provenance", {}).get("sha256"), "provenance manifest digest"
    )
    if sha256_file(sbom_path) != expected_sbom:
        raise VerificationError("SBOM digest does not match release manifest")
    if sha256_file(provenance_path) != expected_provenance:
        raise VerificationError("provenance digest does not match release manifest")

    source = manifest.get("source", {})
    revision = source.get("revision")
    tree = source.get("tree")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise VerificationError("manifest revision is invalid")
    if not isinstance(tree, str) or not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise VerificationError("manifest tree is invalid")
    namespace = sbom.get("documentNamespace", "")
    if not isinstance(namespace, str) or f"/sbom/{revision}/" not in namespace:
        raise VerificationError("SBOM namespace is not commit-bound")

    build_definition = provenance.get("predicate", {}).get("buildDefinition", {})
    internal = build_definition.get("internalParameters", {})
    dependencies = build_definition.get("resolvedDependencies", [])
    if internal.get("gitTree") != tree or internal.get("sourceFilesDigest") != source.get("source_files_digest"):
        raise VerificationError("provenance source binding differs from release manifest")
    if not any(
        dependency.get("digest", {}).get("gitCommit") == revision
        and dependency.get("digest", {}).get("gitTree") == tree
        for dependency in dependencies
        if isinstance(dependency, dict)
    ):
        raise VerificationError("provenance lacks the committed Git dependency")
    if not any(
        subject.get("name") == "ashr-a1-runtime.spdx.json"
        and subject.get("digest", {}).get("sha256") == expected_sbom
        for subject in provenance.get("subject", [])
        if isinstance(subject, dict)
    ):
        raise VerificationError("provenance does not bind the generated SBOM")

    encoded = "\n".join(path.read_text(encoding="utf-8") for path in (manifest_path, sbom_path, provenance_path))
    for marker in SECRET_MARKERS:
        if marker.casefold() in encoded.casefold():
            raise VerificationError(f"evidence contains forbidden marker {marker!r}")

    checked_files = 0
    if check_git:
        if repo_root is None:
            raise VerificationError("--check-git requires --repo-root")
        actual_revision = git(repo_root, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
        actual_tree = git(repo_root, ["rev-parse", f"{revision}^{{tree}}"])
        if actual_revision != revision or actual_tree != tree:
            raise VerificationError("Git object binding does not resolve to the recorded commit/tree")
        for file_entry in sbom.get("files", []):
            file_name = file_entry.get("fileName", "")
            if not isinstance(file_name, str) or not file_name.startswith("./"):
                raise VerificationError("SBOM file path is invalid")
            path = file_name[2:]
            payload = git(repo_root, ["show", f"{revision}:{path}"], binary=True)
            assert isinstance(payload, bytes)
            expected = next(
                (
                    checksum.get("checksumValue")
                    for checksum in file_entry.get("checksums", [])
                    if checksum.get("algorithm") == "SHA256"
                ),
                None,
            )
            if hashlib.sha256(payload).hexdigest() != expected:
                raise VerificationError(f"SBOM file digest mismatch for {path}")
            checked_files += 1

    return {
        "schema_version": "ashr.a1.release_evidence_verification.v1",
        "status": "passed",
        "revision": revision,
        "tree": tree,
        "sbom_sha256": expected_sbom,
        "provenance_sha256": expected_provenance,
        "git_files_checked": checked_files,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--check-git", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = verify(
        args.evidence_dir.resolve(),
        args.repo_root.resolve() if args.repo_root else None,
        args.check_git,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (VerificationError, OSError) as exc:
        print(f"release evidence verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
