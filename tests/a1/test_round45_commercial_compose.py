from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover - minimal environments skip model assertions.
    yaml = None


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra" / "docker" / "docker-compose.self-host.yml"
ENV_EXAMPLE = ROOT / "infra" / "docker" / "self-host.env.example"
GO_DOCKERFILE = ROOT / "infra" / "docker" / "Dockerfile.go-runtime"
MIGRATE = ROOT / "infra" / "docker" / "postgres-migrate.sh"
MINIO_SMOKE = ROOT / "infra" / "docker" / "minio-checksum-smoke.sh"
RECOVERY_SEED = ROOT / "infra" / "docker" / "worker-recovery-seed.sh"
RECOVERY_VERIFY = ROOT / "infra" / "docker" / "worker-recovery-verify.sh"
WORKER_ENTRYPOINT = ROOT / "services" / "runner" / "commercial-worker-entrypoint.sh"
HEALTHCHECK = ROOT / "services" / "runner" / "a1_docker_healthcheck.go"
EVIDENCE = ROOT / "docs" / "a1" / "evidence" / "round45_compose_runtime.md"


def _run(command: list[str], *, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _model() -> dict:
    if yaml is None:
        pytest.skip("PyYAML is not installed")
    loaded = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_round45_commercial_compose_is_postgres_and_s3_fail_closed() -> None:
    compose = _model()
    services = compose["services"]
    api = services["api"]
    worker = services["worker"]

    assert api["image"] == "releasefoundry/a1-go-runtime:local"
    assert api["environment"]["RELEASEFOUNDRY_GO_BACKEND"] == "postgres"
    assert api["command"] == ["/usr/local/bin/releasefoundry-api"]
    assert api["depends_on"]["postgres-migrate"]["condition"] == "service_completed_successfully"
    assert api["depends_on"]["minio-init"]["condition"] == "service_completed_successfully"
    assert api["healthcheck"]["test"][-1] == "postgres_repository_v0"

    assert worker["environment"]["RELEASEFOUNDRY_GO_BACKEND"] == "postgres"
    assert worker["environment"]["RELEASEFOUNDRY_OBJECT_STORE_ENDPOINT"] == "http://minio:9000"
    assert worker["command"] == [
        "/bin/sh",
        "/app/services/runner/commercial-worker-entrypoint.sh",
        "/usr/local/bin/releasefoundry-worker",
    ]
    assert worker["depends_on"]["worker-recovery-seed"]["condition"] == "service_completed_successfully"
    assert worker["depends_on"]["minio-smoke"]["condition"] == "service_completed_successfully"

    assert services["postgres-migrate"]["restart"] == "no"
    assert services["postgres-migrate"]["command"] == ["/bin/sh", "/opt/releasefoundry/postgres-migrate.sh"]
    assert services["minio-smoke"]["restart"] == "no"
    assert services["minio-smoke"]["entrypoint"] == ["/bin/sh", "/opt/releasefoundry/minio-checksum-smoke.sh"]
    assert services["worker-recovery-seed"]["restart"] == "no"
    assert services["worker-recovery-seed"]["command"] == ["/bin/sh", "/opt/releasefoundry/worker-recovery-seed.sh"]
    assert services["worker-recovery-verify"]["restart"] == "no"
    assert services["worker-recovery-verify"]["command"] == ["/bin/sh", "/opt/releasefoundry/worker-recovery-verify.sh"]
    assert services["worker-recovery-verify"]["depends_on"]["worker"]["condition"] == "service_healthy"

    compose_text = COMPOSE.read_text(encoding="utf-8")
    worker_text = WORKER_ENTRYPOINT.read_text(encoding="utf-8")
    for forbidden in ("memory_service_v0", "file:///object-store", "POSTGRES_HOST_AUTH_METHOD"):
        assert forbidden not in compose_text
    assert 'test "$RELEASEFOUNDRY_GO_BACKEND" = "postgres"' in worker_text
    assert "requires an S3-compatible HTTP(S) endpoint" in worker_text
    assert '"$worker_binary" >' in worker_text
    assert "|| true" not in worker_text


def test_round45_scripts_prove_migration_object_checksum_and_restart_recovery() -> None:
    migrate = MIGRATE.read_text(encoding="utf-8")
    minio = MINIO_SMOKE.read_text(encoding="utf-8")
    seed = RECOVERY_SEED.read_text(encoding="utf-8")
    verify = RECOVERY_VERIFY.read_text(encoding="utf-8")
    healthcheck = HEALTHCHECK.read_text(encoding="utf-8")
    dockerfile = GO_DOCKERFILE.read_text(encoding="utf-8")

    assert "set -eu" in migrate
    assert "--set ON_ERROR_STOP=1" in migrate
    assert "releasefoundry_worker_jobs" in migrate
    assert "releasefoundry_artifact_manifests" in migrate
    assert "releasefoundry_schema_migrations" in migrate
    assert "sha256sum" in migrate
    assert "Refusing changed applied migration" in migrate

    for operation in ("mc cp", "mc stat"):
        assert operation in minio
    assert minio.count("mc cp") == 2
    assert "sha256sum" in minio
    assert 'test "$actual_sha" = "$expected_sha"' in minio

    assert "status = 'leased'" not in seed
    assert "'leased'" in seed
    assert "now() - interval '1 minute'" in seed
    assert "completed\\|2\\|*\\|t" in verify
    assert "RELEASEFOUNDRY_WORKER_HEARTBEAT_PATH" in verify

    assert "BackendReady" in healthcheck
    assert "LocalOnly" in healthcheck
    assert "postgres_repository_v0" in dockerfile
    assert "releasefoundry-healthcheck" in dockerfile


def test_round45_migration_bootstraps_restricted_identity_roles() -> None:
    migrate = MIGRATE.read_text(encoding="utf-8")

    assert "ensure_runtime_roles" in migrate
    assert "CREATE ROLE a1_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS" in migrate
    assert "CREATE ROLE a1_security_ticket_issuer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS" in migrate
    assert "CREATE ROLE releasefoundry_identity_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT NOBYPASSRLS" in migrate
    assert "ALTER ROLE a1_runtime" in migrate
    assert "ALTER ROLE a1_security_ticket_issuer" in migrate
    assert "rolcanlogin = false" in migrate
    assert "rolbypassrls = false" in migrate
    assert "GRANT a1_runtime TO releasefoundry_identity_runtime" in migrate
    assert "THEN 'ready' ELSE 'not_ready' END" in migrate


def test_round45_example_and_evidence_keep_live_smoke_explicit() -> None:
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")

    assert "RELEASEFOUNDRY_RUN_COMMERCIAL_COMPOSE_SMOKE=1" in env_example
    assert "RELEASEFOUNDRY_POSTGRES_AUTH_SECRET=" not in env_example
    assert "RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY=" not in env_example
    assert "RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY=" not in env_example
    assert "fail closed" in evidence.lower()
    assert "PUT / HEAD / GET" in evidence
    assert "job_round45_restart_recovery" in evidence


@pytest.mark.skipif(
    os.environ.get("RELEASEFOUNDRY_RUN_COMMERCIAL_COMPOSE_SMOKE") != "1",
    reason="set RELEASEFOUNDRY_RUN_COMMERCIAL_COMPOSE_SMOKE=1 to run disposable Docker integration",
)
@pytest.mark.docker
def test_round45_live_commercial_compose_smoke() -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is unavailable for the opt-in live smoke")

    project = f"releasefoundry-round45-{uuid.uuid4().hex[:8]}"
    env = os.environ.copy()
    env.setdefault("RELEASEFOUNDRY_POSTGRES_AUTH_SECRET", "round45-postgres-local-only")
    env.setdefault("RELEASEFOUNDRY_POSTGRES_RUNTIME_SECRET", "round45-runtime-local-only")
    env.setdefault("RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY", "round45minio")
    env.setdefault("RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY", "round45-minio-local-only-secret")
    env.setdefault("RELEASEFOUNDRY_IDENTITY_SESSION_HMAC_KEY", "round45-session-hmac-local-only-key-123456")
    env.setdefault("RELEASEFOUNDRY_IDENTITY_LIFECYCLE_RECEIPT_KEY", "round45-lifecycle-hmac-local-only-key-123456")
    base = [
        docker,
        "compose",
        "--project-name",
        project,
        "-f",
        str(COMPOSE),
        "--profile",
        "commercial",
        "--profile",
        "commercial-smoke",
    ]

    daemon = _run(
        [docker, "info", "--format", "{{.ServerVersion}}"],
        env=env,
        timeout=30,
    )
    assert daemon.returncode == 0, daemon.stdout

    try:
        run = _run(
            [
                *base,
                "up",
                "--build",
                "--abort-on-container-exit",
                "--exit-code-from",
                "worker-recovery-verify",
                "worker-recovery-verify",
            ],
            env=env,
            timeout=600,
        )
        if run.returncode != 0:
            failed_logs = _run(
                [*base, "logs", "--no-color", "postgres-migrate", "api", "worker"],
                env=env,
                timeout=30,
            )
            pytest.fail((run.stdout + "\n" + failed_logs.stdout)[-20000:])

        ps = _run(
            [*base, "ps", "--format", "json"],
            env=env,
            timeout=30,
        )
        assert ps.returncode == 0, ps.stdout
        assert '"Health":"healthy"' in ps.stdout

        logs = _run(
            [*base, "logs", "--no-color", "postgres-migrate", "minio-smoke", "worker-recovery-verify"],
            env=env,
            timeout=30,
        )
        assert logs.returncode == 0, logs.stdout
        assert '"status":"ok"' in logs.stdout
        assert "job_round45_restart_recovery" in logs.stdout
    finally:
        _run(
            [*base, "down", "--volumes", "--remove-orphans"],
            env=env,
            timeout=120,
        )
