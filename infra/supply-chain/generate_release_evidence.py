#!/usr/bin/env python3
"""Generate deterministic SPDX and SLSA evidence from one committed Git tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit


IMAGE_COMPONENTS = frozenset(("api", "worker", "identity-delivery", "migration", "verifier"))
IMAGE_PATTERN = re.compile(r"^(?P<repository>[A-Za-z0-9][A-Za-z0-9._:/-]+)@sha256:(?P<digest>[0-9a-f]{64})$")
SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_PREFIXES = (
    "infra/docker",
    "infra/kubernetes",
    "infra/terraform/kubernetes-runtime",
    "infra/supply-chain",
    "services/runner",
    "packages/go/ashrclone/go.mod",
    "packages/go/ashrclone/go.sum",
    "packages/rust/ashr-runtime-verify/Cargo.toml",
    "packages/rust/ashr-runtime-verify/Cargo.lock",
)
EXCLUDED_PARTS = frozenset(("private_refs", ".terraform", "target", "node_modules", "__pycache__"))
PLACEHOLDER_DIGESTS = frozenset(
    (
        "d11aa1b5a977de20a601f45500420e543f3be22fbee21b4c19254165a45d77b9",
        "75973ade13ec20d39b2d175be0b467351a7a5a93e5540580817318f89b38bdfb",
        "880482f0bcdcec25c5e7fada9aadf2d15824412f4553aceaa73f30885ccc5841",
        "bc71da90a0577f2f441783c0292e871947f36df46df948c727c1019992632a17",
        "5b6c85334c7950eb5d9a1290246a06e6d5e590eece41253953df6d57b37d9919",
    )
)


class EvidenceError(RuntimeError):
    pass


def canonical_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git(repo_root: Path, args: Sequence[str], *, binary: bool = False) -> bytes | str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        reason = completed.stderr.decode("utf-8", errors="replace").strip()[:400]
        raise EvidenceError(f"git {' '.join(args[:2])} failed: {reason}")
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8", errors="strict").strip()


def normalize_repository_uri(raw: str) -> str:
    value = raw.strip()
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.removeprefix("git@github.com:")
    if value.endswith(".git"):
        value = value[:-4]
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise EvidenceError("repository URI must be credential-free HTTPS")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def parse_images(values: Iterable[str], allow_placeholders: bool) -> dict[str, dict[str, str]]:
    images: dict[str, dict[str, str]] = {}
    for value in values:
        component, separator, reference = value.partition("=")
        if not separator or component not in IMAGE_COMPONENTS or component in images:
            raise EvidenceError("each --image must uniquely name api, worker, identity-delivery, migration, or verifier")
        match = IMAGE_PATTERN.fullmatch(reference)
        if match is None:
            raise EvidenceError(f"image {component} must use repository@sha256:digest")
        digest = match.group("digest")
        if not allow_placeholders and digest in PLACEHOLDER_DIGESTS:
            raise EvidenceError(f"image {component} uses a documented placeholder digest")
        images[component] = {
            "reference": reference,
            "repository": match.group("repository"),
            "digest": digest,
        }
    missing = IMAGE_COMPONENTS.difference(images)
    if missing:
        raise EvidenceError(f"missing image components: {', '.join(sorted(missing))}")
    return dict(sorted(images.items()))


def tracked_paths(repo_root: Path, revision: str, prefixes: Sequence[str]) -> list[str]:
    output = git(repo_root, ["ls-tree", "-r", "--name-only", revision, "--", *prefixes])
    assert isinstance(output, str)
    paths: list[str] = []
    for path in output.splitlines():
        pure = PurePosixPath(path)
        if not path or path.startswith("/") or ".." in pure.parts:
            raise EvidenceError("Git tree returned an unsafe path")
        if EXCLUDED_PARTS.intersection(pure.parts):
            continue
        paths.append(path)
    unique = sorted(set(paths))
    if not unique:
        raise EvidenceError("no tracked release inputs matched the selected prefixes")
    return unique


def spdx_id(kind: str, value: str) -> str:
    return f"SPDXRef-{kind}-{sha256_bytes(value.encode('utf-8'))[:20]}"


def commit_timestamp(repo_root: Path, revision: str) -> tuple[int, str]:
    raw = git(repo_root, ["show", "-s", "--format=%ct", revision])
    assert isinstance(raw, str)
    try:
        epoch = int(raw)
    except ValueError as exc:
        raise EvidenceError("Git commit timestamp is invalid") from exc
    created = datetime.fromtimestamp(epoch, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return epoch, created


def source_files(repo_root: Path, revision: str, paths: Sequence[str]) -> tuple[list[dict[str, Any]], str]:
    files: list[dict[str, Any]] = []
    digest_rows: list[dict[str, Any]] = []
    for path in paths:
        payload = git(repo_root, ["show", f"{revision}:{path}"], binary=True)
        assert isinstance(payload, bytes)
        digest = sha256_bytes(payload)
        files.append(
            {
                "SPDXID": spdx_id("File", path),
                "checksums": [{"algorithm": "SHA256", "checksumValue": digest}],
                "copyrightText": "NOASSERTION",
                "fileName": f"./{path}",
                "fileTypes": ["SOURCE"],
                "licenseConcluded": "NOASSERTION",
                "licenseInfoInFiles": ["NOASSERTION"],
            }
        )
        digest_rows.append({"path": path, "sha256": digest, "size": len(payload)})
    return files, sha256_bytes(canonical_bytes(digest_rows))


def build_spdx(
    repository_uri: str,
    revision: str,
    tree: str,
    created: str,
    images: Mapping[str, Mapping[str, str]],
    files: Sequence[Mapping[str, Any]],
    files_digest: str,
) -> dict[str, Any]:
    source_package_id = "SPDXRef-Package-Ashr-A1-Source"
    packages: list[dict[str, Any]] = [
        {
            "SPDXID": source_package_id,
            "checksums": [{"algorithm": "SHA256", "checksumValue": files_digest}],
            "copyrightText": "NOASSERTION",
            "downloadLocation": f"git+{repository_uri}@{revision}",
            "filesAnalyzed": True,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "name": "ashr-a1-runtime-source",
            "supplier": "Organization: Ashr clone contributors",
            "versionInfo": revision,
        }
    ]
    relationships: list[dict[str, str]] = [
        {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": source_package_id}
    ]
    for file_entry in files:
        relationships.append(
            {
                "spdxElementId": source_package_id,
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": str(file_entry["SPDXID"]),
            }
        )
    for component, image in images.items():
        package_id = spdx_id("Image", component)
        packages.append(
            {
                "SPDXID": package_id,
                "checksums": [{"algorithm": "SHA256", "checksumValue": image["digest"]}],
                "copyrightText": "NOASSERTION",
                "downloadLocation": image["reference"],
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceLocator": f"pkg:oci/{image['repository']}@sha256:{image['digest']}",
                        "referenceType": "purl",
                    }
                ],
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "name": f"ashr-a1-{component}",
                "supplier": "NOASSERTION",
                "versionInfo": f"sha256:{image['digest']}",
            }
        )
        relationships.append(
            {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": package_id}
        )
    namespace_seed = sha256_bytes(canonical_bytes({"revision": revision, "tree": tree, "files": files_digest, "images": images}))
    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: ashr-a1-deterministic-sbom/1.0"],
            "licenseListVersion": "3.25",
        },
        "dataLicense": "CC0-1.0",
        "documentNamespace": f"{repository_uri}/sbom/{revision}/{namespace_seed}",
        "files": list(files),
        "name": f"ashr-a1-runtime-{revision[:12]}",
        "packages": packages,
        "relationships": relationships,
        "spdxVersion": "SPDX-2.3",
    }


def build_provenance(
    repository_uri: str,
    revision: str,
    tree: str,
    created: str,
    images: Mapping[str, Mapping[str, str]],
    files_digest: str,
    sbom_digest: str,
    builder_id: str,
) -> dict[str, Any]:
    subjects = [
        {"name": image["repository"], "digest": {"sha256": image["digest"]}}
        for image in images.values()
    ]
    subjects.append({"name": "ashr-a1-runtime.spdx.json", "digest": {"sha256": sbom_digest}})
    invocation_seed = sha256_bytes(
        canonical_bytes({"revision": revision, "tree": tree, "images": images, "sbom": sbom_digest})
    )
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": subjects,
        "predicate": {
            "buildDefinition": {
                "buildType": "https://github.com/3351666087/ashr-codex-factory/buildtypes/a1-release-evidence/v1",
                "externalParameters": {
                    "images": {component: image["reference"] for component, image in images.items()},
                    "source": {"repository": repository_uri, "revision": revision},
                },
                "internalParameters": {
                    "gitTree": tree,
                    "sourceFilesDigest": files_digest,
                    "deterministic": True,
                },
                "resolvedDependencies": [
                    {"uri": f"git+{repository_uri}@{revision}", "digest": {"gitCommit": revision, "gitTree": tree}}
                ],
            },
            "runDetails": {
                "builder": {"id": builder_id},
                "metadata": {
                    "finishedOn": created,
                    "invocationId": f"urn:ashr:a1:release-evidence:{invocation_seed}",
                    "startedOn": created,
                },
                "byproducts": [
                    {"name": "ashr-a1-runtime.spdx.json", "digest": {"sha256": sbom_digest}}
                ],
            },
        },
    }


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_bytes(payload)
    temporary.replace(path)


def generate(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    revision = git(repo_root, ["rev-parse", "--verify", f"{args.revision}^{{commit}}"])
    assert isinstance(revision, str)
    tree = git(repo_root, ["rev-parse", f"{revision}^{{tree}}"])
    assert isinstance(tree, str)
    if not SHA1_PATTERN.fullmatch(revision) or not SHA1_PATTERN.fullmatch(tree):
        raise EvidenceError("Git revision or tree is not a full SHA-1 object id")
    remote = args.repository_uri or str(git(repo_root, ["remote", "get-url", "origin"]))
    repository_uri = normalize_repository_uri(remote)
    images = parse_images(args.image, args.allow_placeholder_images)
    paths = tracked_paths(repo_root, revision, args.path_prefix or DEFAULT_PREFIXES)
    files, files_digest = source_files(repo_root, revision, paths)
    epoch, created = commit_timestamp(repo_root, revision)

    spdx = build_spdx(repository_uri, revision, tree, created, images, files, files_digest)
    spdx_payload = canonical_bytes(spdx)
    spdx_digest = sha256_bytes(spdx_payload)
    provenance = build_provenance(
        repository_uri,
        revision,
        tree,
        created,
        images,
        files_digest,
        spdx_digest,
        args.builder_id,
    )
    provenance_payload = canonical_bytes(provenance)
    provenance_digest = sha256_bytes(provenance_payload)
    manifest = {
        "schema_version": "ashr.a1.release_evidence.v1",
        "source": {
            "repository": repository_uri,
            "revision": revision,
            "tree": tree,
            "commit_epoch": epoch,
            "source_files_digest": files_digest,
            "source_file_count": len(files),
        },
        "images": {component: image["reference"] for component, image in images.items()},
        "artifacts": {
            "sbom": {"path": "ashr-a1-runtime.spdx.json", "sha256": spdx_digest},
            "provenance": {"path": "ashr-a1-runtime.provenance.json", "sha256": provenance_digest},
        },
        "deterministic": True,
        "secret_values_included": False,
    }
    output_dir = args.output_dir.resolve()
    atomic_write(output_dir / "ashr-a1-runtime.spdx.json", spdx_payload)
    atomic_write(output_dir / "ashr-a1-runtime.provenance.json", provenance_payload)
    atomic_write(output_dir / "ashr-a1-runtime.release-manifest.json", canonical_bytes(manifest))
    return manifest


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--repository-uri")
    parser.add_argument("--builder-id", default="https://github.com/3351666087/ashr-codex-factory/a1-release-evidence")
    parser.add_argument("--image", action="append", default=[], metavar="COMPONENT=REPOSITORY@SHA256")
    parser.add_argument("--path-prefix", action="append", default=[])
    parser.add_argument("--allow-placeholder-images", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    manifest = generate(parse_args(argv))
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvidenceError, OSError) as exc:
        print(f"release evidence generation failed: {exc}", file=os.sys.stderr)
        raise SystemExit(1)
