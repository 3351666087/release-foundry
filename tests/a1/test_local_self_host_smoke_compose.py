from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only in minimal environments.
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "services" / "runner" / "docker-compose.a1.yml"
HEALTHCHECK = ROOT / "services" / "runner" / "a1_docker_healthcheck.go"
TERRAFORM_SELF_HOST = ROOT / "infra" / "terraform" / "self-host"
EVIDENCE_README = ROOT / "docs" / "a1" / "evidence" / "README.md"
EVIDENCE_COMMANDS = ROOT / "docs" / "a1" / "evidence" / "commands.md"
SELF_HOST_EVIDENCE = ROOT / "docs" / "a1" / "evidence" / "self_host_commercial_runtime_scaffold_20260709.md"


def _read_compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


def _compose_model() -> dict:
    if yaml is None:
        pytest.skip("PyYAML is not installed in this environment")
    loaded = yaml.safe_load(_read_compose_text())
    assert isinstance(loaded, dict)
    return loaded


def _service_block(compose_text: str, service_name: str) -> str:
    pattern = re.compile(
        rf"^  {re.escape(service_name)}:\n(?P<body>(?:    .*\n|\n)+?)(?=^  [A-Za-z0-9_-]+:|^volumes:|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(compose_text)
    assert match, f"missing {service_name!r} service in {COMPOSE}"
    return match.group("body")


def test_a1_compose_declares_local_go_api_and_postgres_services():
    compose_text = _read_compose_text()
    compose = _compose_model()
    api = _service_block(compose_text, "api")
    postgres = _service_block(compose_text, "postgres")
    api_env = compose["services"]["api"]["environment"]

    assert "image: golang:1.22-bookworm" in api
    assert "go run ./cmd/ashr-api" in api
    assert "ASHR_GO_API_ADDR: 0.0.0.0:8787" in api
    assert api_env["ASHR_GO_BACKEND"] == "postgres"
    assert api_env["ASHR_POSTGRES_DSN"] == "postgres://ashr@postgres:5432/ashr?sslmode=disable"
    assert '"127.0.0.1:18787:8787"' in api
    assert "postgres:" in api
    assert "condition: service_healthy" in api
    assert "healthcheck:" in api
    assert "a1_docker_healthcheck.go" in api
    assert "http://127.0.0.1:8787/healthz" in api
    assert "start_period: 20s" in api

    assert "image: postgres:16-alpine" in postgres
    assert "POSTGRES_DB: ashr" in postgres
    assert "POSTGRES_USER: ashr" in postgres
    assert "POSTGRES_HOST_AUTH_METHOD: trust" in postgres
    assert "pg_isready -U ashr -d ashr" in postgres
    assert '"127.0.0.1:15432:5432"' in postgres


def test_a1_compose_declares_commercial_self_host_services_and_secret_refs():
    compose = _compose_model()
    services = compose["services"]

    assert {"api", "worker", "postgres", "object-store", "billing-webhook"}.issubset(services)

    api_env = services["api"]["environment"]
    worker_env = services["worker"]["environment"]
    billing_env = services["billing-webhook"]["environment"]

    for env in (api_env, worker_env, billing_env):
        assert env["ASHR_RUNTIME_ENV"] == "self-host"
        assert env["ASHR_SECRET_PROVIDER"] == "env-ref"
        assert env["ASHR_POSTGRES_DSN_REF"] == "env:ASHR_POSTGRES_DSN"
        assert env["ASHR_BILLING_PROVIDER_SECRET_REF"] == "env:ASHR_BILLING_PROVIDER_SECRET_REF"
        assert env["ASHR_BILLING_WEBHOOK_SECRET_REF"] == "env:ASHR_BILLING_WEBHOOK_SECRET_REF"
        assert env["ASHR_OBJECT_STORE_ACCESS_KEY_REF"] == "env:ASHR_OBJECT_STORE_ACCESS_KEY_REF"
        assert env["ASHR_OBJECT_STORE_SECRET_KEY_REF"] == "env:ASHR_OBJECT_STORE_SECRET_KEY_REF"
        assert env["ASHR_OBJECT_STORE_ENDPOINT"] == "file:///object-store"
        assert env["ASHR_OBJECT_STORE_BUCKET"] == "ashr-local-artifacts"
        assert env["ASHR_OBJECT_EVIDENCE_PREFIX"] == "evidence/a1/self-host"
        assert env["ASHR_QUOTA_LEDGER_TABLE"] == "ashr_quota_ledger"
        assert env["ASHR_ARTIFACT_MANIFEST_TABLE"] == "ashr_artifact_manifests"
        assert env["ASHR_WORKER_JOBS_TABLE"] == "ashr_worker_jobs"

    assert worker_env["ASHR_WORKER_MODE"] == "long-running"
    assert worker_env["ASHR_WORKER_QUEUE"] == "ashr_worker_jobs"
    assert worker_env["ASHR_WORKER_EVIDENCE_WRITES"] == "object-store"
    assert "while true" in " ".join(services["worker"]["command"])
    assert "TestServiceWorkerQueueLifecycle" in " ".join(services["worker"]["command"])
    assert "a1-worker-state:/var/lib/ashr/worker" in services["worker"]["volumes"]

    assert billing_env["ASHR_BILLING_WEBHOOK_RECEIVER"] == "enabled"
    assert billing_env["ASHR_BILLING_LEDGER_TABLE"] == "ashr_billing_ledger"
    assert billing_env["ASHR_BILLING_QUOTA_LEDGER_TABLE"] == "ashr_quota_ledger"
    assert billing_env["ASHR_BILLING_WEBHOOK_SECRET_REQUIRED"] == "true"
    assert services["billing-webhook"]["ports"] == ["127.0.0.1:18788:8788"]

    object_store = services["object-store"]
    assert object_store["image"] == "busybox:1.36"
    assert "ashr-local-artifacts/evidence/a1/self-host" in " ".join(object_store["command"])
    assert "a1-object-store:/object-store" in object_store["volumes"]


def test_a1_compose_keeps_env_boundaries_and_public_secret_hygiene():
    compose_text = _read_compose_text()

    forbidden_markers = [
        "ASHR_API_KEY",
        "ASHR_LABS_API_KEY",
        "Authorization:",
        "Bearer ",
        "sk-",
        "rk_",
        "whsec_",
        "ashr_live_",
        "private_refs",
        "MINIO_ROOT_PASSWORD",
        "AWS_SECRET_ACCESS_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
    ]
    for marker in forbidden_markers:
        assert marker not in compose_text

    assert "POSTGRES_PASSWORD" not in compose_text
    assert "password=" not in compose_text.lower()
    assert "127.0.0.1:" in compose_text
    allowed_container_binds_removed = compose_text.replace("ASHR_GO_API_ADDR: 0.0.0.0:8787", "").replace("ASHR_GO_API_ADDR: 0.0.0.0:8788", "")
    assert "0.0.0.0:" not in allowed_container_binds_removed


def test_a1_self_host_terraform_contract_tracks_runtime_services_public_safely():
    main = (TERRAFORM_SELF_HOST / "main.tf").read_text(encoding="utf-8")
    variables = (TERRAFORM_SELF_HOST / "variables.tf").read_text(encoding="utf-8")
    outputs = (TERRAFORM_SELF_HOST / "outputs.tf").read_text(encoding="utf-8")
    hcl_text = "\n".join([main, variables, outputs])

    for component in ("api", "worker", "billing_webhook", "postgres", "redis", "object_store", "quota_ledger"):
        assert f"{component} = {{" in main

    for marker in (
        "ASHR_DATABASE_URL_REF",
        "ASHR_OBJECT_STORE_ACCESS_KEY_REF",
        "ASHR_OBJECT_STORE_SECRET_KEY_REF",
        "ASHR_BILLING_PROVIDER_SECRET_REF",
        "ASHR_BILLING_WEBHOOK_SECRET_REF",
        "ASHR_QUOTA_LEDGER_TABLE",
        "ASHR_ARTIFACT_MANIFEST_TABLE",
        "ASHR_WORKER_JOBS_TABLE",
        "ashr.a1.self_host.commercial_runtime.v2",
    ):
        assert marker in main

    for variable in (
        "billing_webhook_replicas",
        "object_store_endpoint_ref",
        "object_store_access_key_ref",
        "object_store_secret_key_ref",
        "object_evidence_prefix",
        "postgres_dsn_secret_ref",
        "billing_provider_secret_ref",
        "billing_webhook_secret_ref",
    ):
        assert f'variable "{variable}"' in variables

    assert "runtime_environment" in outputs
    assert "ashr_quota_ledger" in main
    assert "ashr_artifact_manifests" in main
    assert "worker.job.complete" in main
    assert "billing.webhook.ingest" in main

    forbidden_markers = ["sk-", "rk_", "whsec_", "Bearer ", "Authorization:", "ASHR_API_KEY", "ASHR_LABS_API_KEY"]
    for marker in forbidden_markers:
        assert marker not in hcl_text


def test_a1_evidence_readme_links_compose_and_validation_command():
    readme = EVIDENCE_README.read_text(encoding="utf-8")
    scaffold = SELF_HOST_EVIDENCE.read_text(encoding="utf-8")

    assert "services/runner/docker-compose.a1.yml" in readme
    assert "docker compose -f services/runner/docker-compose.a1.yml up --build" in readme
    assert "python -m pytest tests/a1/test_local_self_host_smoke_compose.py" in readme
    assert "docker info --format" in readme
    assert "docker compose -f services/runner/docker-compose.a1.yml config --quiet" in readme
    assert "a1_docker_healthcheck.go" in readme
    assert "ASHR_API_KEY" in readme
    assert "not set" in readme or "does not set" in readme
    assert "worker" in readme
    assert "billing-webhook" in readme
    assert "object-store" in readme
    assert "ASHR_BILLING_WEBHOOK_SECRET_REF" in readme
    assert "ASHR_OBJECT_STORE_SECRET_KEY_REF" in readme
    assert "ASHR_QUOTA_LEDGER_TABLE" in readme
    assert "self_host_commercial_runtime_scaffold_20260709.md" in readme

    assert "long-running" in scaffold
    assert "object evidence" in scaffold
    assert "ashr_quota_ledger" in scaffold
    assert "ASHR_BILLING_WEBHOOK_SECRET_REF" in scaffold
    assert "Secret values are not present" in scaffold


def test_a1_compose_healthcheck_uses_stdlib_go_probe_without_secrets():
    source = HEALTHCHECK.read_text(encoding="utf-8")

    assert "package main" in source
    assert "net/http" in source
    assert "http://127.0.0.1:8787/healthz" in source
    assert "http.StatusOK" in source
    assert "context.WithTimeout" in source

    forbidden_markers = ["ASHR_API_KEY", "ASHR_LABS_API_KEY", "Authorization:", "Bearer ", "sk-"]
    for marker in forbidden_markers:
        assert marker not in source


def test_a1_docker_compose_config_is_valid_when_daemon_is_reachable():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is not installed on this host")

    try:
        daemon = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("Docker daemon probe timed out before compose validation")
    if daemon.returncode != 0:
        pytest.skip(f"Docker daemon is not reachable: {_one_line(daemon.stderr or daemon.stdout)}")

    config = subprocess.run(
        [docker, "compose", "-f", str(COMPOSE), "config", "--quiet"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert config.returncode == 0, config.stderr or config.stdout


def _one_line(value: str) -> str:
    return " ".join(value.split())[:240]


def test_a1_wsl_go_readiness_is_recorded_as_linux_self_host_evidence():
    commands = EVIDENCE_COMMANDS.read_text(encoding="utf-8")
    start = commands.index("## Round25 WSL self-host Go readiness")
    round25 = commands[start:]

    assert "Round25 WSL self-host Go readiness" in round25
    assert "Ubuntu-24.04-Ashr" in round25
    assert "apt-get install -y golang-go" in round25
    assert "go version go1.22.2 linux/amd64" in round25
    assert "cd /mnt/c/Users/33516/Documents/Ashr_a1_clean_rebase/packages/go/ashrclone; go test ./..." in round25
    assert "Linux/WSL Go SDK tests passed" in round25
    assert "ASHR_API_KEY=" not in round25
