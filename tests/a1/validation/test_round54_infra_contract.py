from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / "infra" / "kubernetes" / "releasefoundry-runtime"
TERRAFORM = ROOT / "infra" / "terraform" / "kubernetes-runtime"
SUPPLY_CHAIN = ROOT / "infra" / "supply-chain"


def run(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise AssertionError(
            f"{' '.join(args)} failed ({result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        pytest.skip(f"{name} is not installed")
    return executable


def production_set_args() -> list[str]:
    revision = run("git", "rev-parse", "HEAD").stdout.strip()
    tree = run("git", "rev-parse", "HEAD^{tree}").stdout.strip()
    args = [
        "--set-string",
        f"supplyChain.sourceRevision={revision}",
        "--set-string",
        f"supplyChain.sourceTree={tree}",
        "--set-string",
        f"supplyChain.sbom.sha256={hashlib.sha256(b'sbom').hexdigest()}",
        "--set-string",
        f"supplyChain.provenance.sha256={hashlib.sha256(b'provenance').hexdigest()}",
    ]
    for index, component in enumerate(("api", "worker", "identityDelivery", "migration", "verifier"), start=1):
        args.extend(["--set-string", f"images.{component}.digest=sha256:{index:064x}"])
    return args


def test_dockerfiles_pin_every_base_image_to_digest() -> None:
    for name in ("Dockerfile.go-runtime", "Dockerfile.migrations", "Dockerfile.rust-verifier"):
        text = (ROOT / "infra" / "docker" / name).read_text(encoding="utf-8")
        from_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("FROM ")]
        assert from_lines
        for line in from_lines:
            reference = line.split()[1]
            if reference.startswith("${"):
                variable = reference[2:-1]
                assignment = next(
                    candidate for candidate in text.splitlines() if candidate.startswith(f"ARG {variable}=")
                )
                reference = assignment.split("=", 1)[1]
            assert "@sha256:" in reference, f"mutable base image in {name}: {line}"


def test_helm_development_and_production_contracts(tmp_path: Path) -> None:
    helm = tool("helm")
    common = [helm, "lint", str(CHART), "-f", str(CHART / "values.yaml")]
    run(*common, "-f", str(CHART / "values-development.yaml"))

    rejected = run(
        helm,
        "template",
        "round54-negative",
        str(CHART),
        "-f",
        str(CHART / "values.yaml"),
        "-f",
        str(CHART / "values-production.yaml"),
        check=False,
    )
    assert rejected.returncode != 0
    assert "placeholder" in (rejected.stdout + rejected.stderr)

    production_args = production_set_args()
    run(*common, "-f", str(CHART / "values-production.yaml"), *production_args)
    rendered = run(
        helm,
        "template",
        "round54",
        str(CHART),
        "-f",
        str(CHART / "values.yaml"),
        "-f",
        str(CHART / "values-production.yaml"),
        *production_args,
    ).stdout
    (tmp_path / "production.yaml").write_text(rendered, encoding="utf-8")
    assert rendered.count("kind: PodDisruptionBudget") == 3
    assert "kind: NetworkPolicy" in rendered
    assert "name: runtime-verifier" in rendered
    assert "readOnlyRootFilesystem: true" in rendered
    assert "type: RuntimeDefault" in rendered
    assert "topologySpreadConstraints:" in rendered
    assert "kind: Job" in rendered and "app.kubernetes.io/component: migration" in rendered
    assert "@sha256:" in rendered


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("networkPolicy.enabled", "false", "networkPolicy.enabled"),
        ("queueWorker.verifier.enabled", "false", "verifier.enabled"),
        ("api.pdb.minAvailable", "3", "minAvailable"),
        ("scheduling.topology.hostnameKey", "topology.kubernetes.io/zone", "topology keys"),
    ],
)
def test_helm_rejects_unsafe_production_overrides(setting: str, value: str, message: str) -> None:
    helm = tool("helm")
    result = run(
        helm,
        "template",
        "round54-unsafe",
        str(CHART),
        "-f",
        str(CHART / "values.yaml"),
        "-f",
        str(CHART / "values-production.yaml"),
        *production_set_args(),
        "--set",
        f"{setting}={value}",
        check=False,
    )
    assert result.returncode != 0
    assert message in result.stdout + result.stderr


def test_terraform_contract() -> None:
    terraform = tool("terraform")
    run(terraform, "fmt", "-check", "-recursive", cwd=TERRAFORM)
    run(terraform, "init", "-backend=false", "-input=false", cwd=TERRAFORM)
    run(terraform, "validate", cwd=TERRAFORM)
    run(terraform, "test", cwd=TERRAFORM)


def test_supply_chain_is_deterministic_commit_bound_and_tamper_evident(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run("git", "init", cwd=repo)
    run("git", "config", "user.name", "Round 54 Infra", cwd=repo)
    run("git", "config", "user.email", "infra@example.invalid", cwd=repo)
    source = repo / "infra" / "docker"
    source.mkdir(parents=True)
    (source / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    run("git", "add", ".", cwd=repo)
    env = os.environ.copy()
    env.update({"GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"})
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, env=env, check=True, capture_output=True)

    image_args: list[str] = []
    for index, component in enumerate(("api", "worker", "identity-delivery", "migration", "verifier"), start=1):
        image_args.extend(["--image", f"{component}=registry.invalid/releasefoundry/{component}@sha256:{index:064x}"])
    outputs = []
    for name in ("one", "two"):
        output = tmp_path / name
        run(
            sys.executable,
            str(SUPPLY_CHAIN / "generate_release_evidence.py"),
            "--repo-root",
            str(repo),
            "--repository-uri",
            "https://github.com/example/releasefoundry",
            "--path-prefix",
            "infra",
            "--output-dir",
            str(output),
            *image_args,
        )
        run(
            sys.executable,
            str(SUPPLY_CHAIN / "verify_release_evidence.py"),
            "--evidence-dir",
            str(output),
            "--repo-root",
            str(repo),
            "--check-git",
        )
        outputs.append(output)

    for artifact in (
        "releasefoundry-a1-runtime.spdx.json",
        "releasefoundry-a1-runtime.provenance.json",
        "releasefoundry-a1-runtime.release-manifest.json",
    ):
        assert (outputs[0] / artifact).read_bytes() == (outputs[1] / artifact).read_bytes()

    manifest_path = outputs[0] / "releasefoundry-a1-runtime.release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source"]["tree"] = "f" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    rejected = run(
        sys.executable,
        str(SUPPLY_CHAIN / "verify_release_evidence.py"),
        "--evidence-dir",
        str(outputs[0]),
        "--repo-root",
        str(repo),
        "--check-git",
        check=False,
    )
    assert rejected.returncode != 0
    assert "binding" in rejected.stderr or "commit/tree" in rejected.stderr
