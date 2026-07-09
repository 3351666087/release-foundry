from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "docs" / "a1" / "schemas" / "a1_control_plane_postgres_migration.sql"
GO_POSTGRES_PATH = ROOT / "packages" / "go" / "ashrclone" / "postgres.go"

REQUIRED_TABLES = (
    "ashr_tenants",
    "ashr_projects",
    "ashr_datasets",
    "ashr_runs",
    "ashr_idempotency_ledger",
    "ashr_worker_jobs",
)

REQUIRED_FUNCTIONS = (
    "ashr_current_tenant_id",
    "ashr_set_updated_at",
)

REQUIRED_TRIGGERS = (
    "ashr_tenants_set_updated_at",
    "ashr_projects_set_updated_at",
    "ashr_datasets_set_updated_at",
    "ashr_runs_set_updated_at",
    "ashr_worker_jobs_set_updated_at",
)

REQUIRED_POLICIES = (
    "ashr_tenants_tenant_isolation",
    "ashr_projects_tenant_isolation",
    "ashr_datasets_tenant_isolation",
    "ashr_runs_tenant_isolation",
    "ashr_idempotency_ledger_tenant_isolation",
    "ashr_worker_jobs_tenant_isolation",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize_sql(sql: str) -> str:
    sql = re.sub(r"--.*", "", sql)
    sql = re.sub(r"\s+", " ", sql).strip().lower()
    return sql


def _go_postgres_schema_sql() -> str:
    source = _read(GO_POSTGRES_PATH)
    match = re.search(r"const PostgresSchemaSQL = `(?P<sql>.*?)`", source, flags=re.DOTALL)
    assert match, "packages/go/ashrclone/postgres.go must expose PostgresSchemaSQL"
    return match.group("sql")


def _extract_statement(sql: str, starts_with: str) -> str:
    pattern = re.compile(rf"{re.escape(starts_with)}.*?;", flags=re.IGNORECASE | re.DOTALL)
    match = pattern.search(sql)
    assert match, f"missing SQL statement starting with {starts_with!r}"
    return match.group(0)


def test_a1_postgres_migration_preserves_go_control_plane_first_slice():
    migration_sql = _normalize_sql(_read(MIGRATION_PATH))
    go_schema_sql = _go_postgres_schema_sql()

    for table in REQUIRED_TABLES:
        go_statement = _extract_statement(go_schema_sql, f"CREATE TABLE IF NOT EXISTS {table}")
        assert _normalize_sql(go_statement) in migration_sql

    for index_name in ("ashr_runs_dataset_idx", "ashr_worker_jobs_lease_idx", "ashr_worker_jobs_status_idx"):
        go_index = _extract_statement(go_schema_sql, f"CREATE INDEX IF NOT EXISTS {index_name}")
        assert _normalize_sql(go_index) in migration_sql


def test_a1_postgres_migration_declares_static_rls_and_audit_contract():
    migration_sql = _normalize_sql(_read(MIGRATION_PATH))

    for function_name in REQUIRED_FUNCTIONS:
        assert f"create or replace function {function_name}()" in migration_sql

    for table in REQUIRED_TABLES:
        assert f"alter table {table} enable row level security" in migration_sql

    for trigger_name in REQUIRED_TRIGGERS:
        assert f"create trigger {trigger_name}" in migration_sql
        assert "execute function ashr_set_updated_at()" in migration_sql

    for policy_name in REQUIRED_POLICIES:
        assert f"create policy {policy_name}" in migration_sql
        assert "using (tenant_id = ashr_current_tenant_id())" in migration_sql
        assert "with check (tenant_id = ashr_current_tenant_id())" in migration_sql
