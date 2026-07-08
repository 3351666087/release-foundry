from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "services" / "runner" / "docker-compose.a1.yml"
EVIDENCE_README = ROOT / "docs" / "a1" / "evidence" / "README.md"


def _read_compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


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
    api = _service_block(compose_text, "api")
    postgres = _service_block(compose_text, "postgres")

    assert "image: golang:1.22-bookworm" in api
    assert "go run ./cmd/ashr-api" in api
    assert "ASHR_GO_API_ADDR: 0.0.0.0:8787" in api
    assert "ASHR_GO_BACKEND: postgres" in api
    assert "ASHR_POSTGRES_DSN: postgres://ashr@postgres:5432/ashr?sslmode=disable" in api
    assert '"127.0.0.1:18787:8787"' in api
    assert "postgres:" in api
    assert "condition: service_healthy" in api

    assert "image: postgres:16-alpine" in postgres
    assert "POSTGRES_DB: ashr" in postgres
    assert "POSTGRES_USER: ashr" in postgres
    assert "POSTGRES_HOST_AUTH_METHOD: trust" in postgres
    assert "pg_isready -U ashr -d ashr" in postgres
    assert '"127.0.0.1:15432:5432"' in postgres


def test_a1_compose_keeps_env_boundaries_and_public_secret_hygiene():
    compose_text = _read_compose_text()

    forbidden_markers = [
        "ASHR_API_KEY",
        "ASHR_LABS_API_KEY",
        "Authorization:",
        "Bearer ",
        "sk-",
        "ashr_live_",
        "private_refs",
    ]
    for marker in forbidden_markers:
        assert marker not in compose_text

    assert "POSTGRES_PASSWORD" not in compose_text
    assert "password=" not in compose_text.lower()
    assert "127.0.0.1:" in compose_text
    assert "0.0.0.0:" not in compose_text.replace("ASHR_GO_API_ADDR: 0.0.0.0:8787", "")


def test_a1_evidence_readme_links_compose_and_validation_command():
    readme = EVIDENCE_README.read_text(encoding="utf-8")

    assert "services/runner/docker-compose.a1.yml" in readme
    assert "docker compose -f services/runner/docker-compose.a1.yml up --build" in readme
    assert "python -m pytest tests/a1/test_local_self_host_smoke_compose.py" in readme
    assert "ASHR_API_KEY" in readme
    assert "not set" in readme or "does not set" in readme
