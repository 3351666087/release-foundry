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
    "ashr_run_uploads",
    "ashr_trace_batches",
    "ashr_artifact_manifests",
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
    "ashr_run_uploads_tenant_isolation",
    "ashr_trace_batches_tenant_isolation",
    "ashr_artifact_manifests_tenant_isolation",
)

REQUIRED_WORKER_JOB_COLUMNS = (
    "tenant_id TEXT NOT NULL",
    "project_id TEXT NOT NULL",
    "job_id TEXT NOT NULL",
    "job_type TEXT NOT NULL",
    "target_id TEXT NOT NULL DEFAULT ''",
    "payload_sha256 TEXT NOT NULL",
    "status TEXT NOT NULL",
    "priority INTEGER NOT NULL DEFAULT 100",
    "attempts INTEGER NOT NULL DEFAULT 0",
    "max_attempts INTEGER NOT NULL DEFAULT 3",
    "lease_owner_id TEXT NOT NULL DEFAULT ''",
    "lease_expires_at TIMESTAMPTZ",
    "available_at TIMESTAMPTZ",
    "last_error JSONB",
    "result_sha256 TEXT NOT NULL DEFAULT ''",
    "idempotency_key TEXT NOT NULL DEFAULT ''",
    "request_id TEXT NOT NULL DEFAULT ''",
    "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
    "completed_at TIMESTAMPTZ",
    "dead_lettered_at TIMESTAMPTZ",
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

    for index_name in (
        "ashr_run_uploads_run_idx",
        "ashr_trace_batches_run_idx",
        "ashr_artifact_manifests_run_idx",
    ):
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


def test_a1_postgres_worker_jobs_schema_preserves_durable_method_contract():
    migration_sql = _read(MIGRATION_PATH)
    worker_jobs_statement = _normalize_sql(
        _extract_statement(migration_sql, "CREATE TABLE IF NOT EXISTS ashr_worker_jobs")
    )

    for column in REQUIRED_WORKER_JOB_COLUMNS:
        assert _normalize_sql(column) in worker_jobs_statement

    assert "primary key (tenant_id, project_id, job_id)" in worker_jobs_statement
    assert (
        "foreign key (tenant_id, project_id) references ashr_projects(tenant_id, project_id) on delete cascade"
        in worker_jobs_statement
    )

    normalized_migration = _normalize_sql(migration_sql)
    assert (
        "create index if not exists ashr_worker_jobs_lease_idx on ashr_worker_jobs "
        "(tenant_id, project_id, status, job_type, priority, available_at, created_at)"
        in normalized_migration
    )
    assert (
        "create index if not exists ashr_worker_jobs_status_idx on ashr_worker_jobs "
        "(tenant_id, project_id, status, updated_at)"
        in normalized_migration
    )


def test_a1_go_postgres_worker_lifecycle_uses_atomic_hash_only_queue_contract():
    source = _read(GO_POSTGRES_PATH)
    normalized_source = _normalize_sql(source)

    for method_name in (
        "EnqueueWorkerJob",
        "LeaseWorkerJob",
        "HeartbeatWorkerJob",
        "CompleteWorkerJob",
        "FailWorkerJob",
        "ListWorkerJobs",
    ):
        assert f"func (repository *PostgresRepository) {method_name}" in source

    assert "FOR UPDATE SKIP LOCKED" in source
    assert "expirePostgresWorkerLeases" in source
    assert "status = $4, attempts = attempts + 1" in source
    assert "result_sha256 = $5" in source
    assert "last_error = $7::jsonb" in source
    assert "RawPayloadIncluded: false" in source
    assert "loadIdempotentWorkerJobReplay" in source
    assert "insertIdempotentWorkerJobResponse" in source
    assert "WHERE tenant_id = $1 AND project_id = $2 AND ($3 = '' OR status = $3)" in source
    assert "job_type = $4" in source
    assert "raw_payload" not in normalized_source


def test_a1_postgres_upload_trace_artifact_schema_preserves_hash_only_contract():
    migration_sql = _normalize_sql(_read(MIGRATION_PATH))

    required_fragments = (
        "create table if not exists ashr_run_uploads",
        "upload_id text not null",
        "result_sha256 text not null",
        "create table if not exists ashr_trace_batches",
        "batch_id text not null",
        "observation_count integer not null default 0",
        "observations_sha256 text not null",
        "create table if not exists ashr_artifact_manifests",
        "artifact_id text not null",
        "manifest_sha256 text not null",
        "api_key_id text not null default ''",
        "request_id text not null default ''",
        "idempotency_key text not null default ''",
        "foreign key (tenant_id, project_id, run_id) references ashr_runs(tenant_id, project_id, run_id) on delete cascade",
        "create index if not exists ashr_run_uploads_run_idx",
        "create index if not exists ashr_trace_batches_run_idx",
        "create index if not exists ashr_artifact_manifests_run_idx",
    )
    for fragment in required_fragments:
        assert fragment in migration_sql
