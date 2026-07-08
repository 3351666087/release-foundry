from __future__ import annotations

import re
from pathlib import Path

from services.api.db_migrator import build_go_postgres_vertical_slice_manifest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services/api/migrations/001_a1_large_saas_foundation.sql"

REQUIRED_TABLES = {
    "organizations",
    "workspaces",
    "projects",
    "environments",
    "datasets",
    "runs",
    "case_results",
    "trace_events",
    "observations",
    "artifacts",
    "evidence_bundles",
    "api_keys",
    "webhook_endpoints",
    "usage_ledger",
    "quota_policies",
    "jobs",
    "idempotency_keys",
    "audit_log",
}

REQUIRED_FUNCTIONS = {
    "ensure_idempotency_fingerprint",
    "rollup_usage",
    "audit_chain_tail",
}

REQUIRED_INDEXES = {
    "idx_workspaces_org_status",
    "idx_projects_org_workspace_status",
    "idx_environments_project_kind",
    "idx_datasets_project_created",
    "idx_runs_project_created",
    "idx_runs_project_status",
    "idx_case_results_run_status",
    "idx_trace_events_run_order",
    "idx_observations_project_type_time",
    "idx_artifacts_project_type_created",
    "idx_evidence_bundles_project_status",
    "idx_api_keys_org_status",
    "idx_webhook_endpoints_org_status",
    "idx_idempotency_keys_created",
    "idx_usage_ledger_idempotency_key_unique",
    "idx_usage_ledger_scope_meter_period",
    "idx_usage_ledger_workspace_meter_period",
    "idx_quota_policies_scope_meter",
    "idx_jobs_ready_queue",
    "idx_jobs_project_status",
    "idx_audit_log_scope_created",
    "idx_audit_log_resource",
}

TENANT_SCOPED_TABLES = REQUIRED_TABLES - {"organizations"}
PROJECT_SCOPED_TABLES = {
    "environments",
    "datasets",
    "runs",
    "case_results",
    "trace_events",
    "observations",
    "artifacts",
    "evidence_bundles",
    "webhook_endpoints",
    "usage_ledger",
    "quota_policies",
    "jobs",
    "idempotency_keys",
    "audit_log",
}


def _migration_sql() -> str:
    assert MIGRATION.exists(), f"missing migration: {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower())


def _declared_objects(sql: str, pattern: str) -> set[str]:
    return {match.group(1).lower() for match in re.finditer(pattern, sql, re.IGNORECASE)}


def _table_body(sql: str, table: str) -> str:
    pattern = rf"create\s+table\s+if\s+not\s+exists\s+{table}\s*\((.*?)\n\);"
    match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    assert match, f"missing CREATE TABLE body for {table}"
    return _normalize(match.group(1))


def test_a1_foundation_migration_declares_required_objects() -> None:
    sql = _migration_sql()

    tables = _declared_objects(sql, r"create\s+table\s+if\s+not\s+exists\s+(\w+)")
    functions = _declared_objects(sql, r"create\s+or\s+replace\s+function\s+(\w+)")
    indexes = _declared_objects(sql, r"create\s+(?:unique\s+)?index\s+if\s+not\s+exists\s+(\w+)")

    assert REQUIRED_TABLES <= tables
    assert REQUIRED_FUNCTIONS <= functions
    assert REQUIRED_INDEXES <= indexes


def test_a1_foundation_migration_keeps_tenant_and_project_scope_columns() -> None:
    sql = _migration_sql()

    for table in sorted(TENANT_SCOPED_TABLES):
        body = _table_body(sql, table)
        assert "organization_id uuid not null" in body, f"{table} must be tenant scoped"

    for table in sorted(PROJECT_SCOPED_TABLES):
        body = _table_body(sql, table)
        assert "project_id uuid not null" in body, f"{table} must carry required project scope"

    for table in ["projects", "environments", "datasets", "runs", "case_results", "trace_events"]:
        body = _table_body(sql, table)
        assert "foreign key (organization_id" in body, f"{table} needs composite tenant FK"


def test_a1_foundation_migration_scopes_nullable_child_references() -> None:
    normalized = _normalize(_migration_sql())

    for forbidden in [
        "references case_results(id)",
        "references trace_events(id)",
        "references runs(id)",
        "references datasets(id)",
    ]:
        assert forbidden not in normalized, f"global child FK is not tenant/project scoped: {forbidden}"

    for required in [
        "constraint trace_events_case_scope_fk foreign key (organization_id, project_id, case_result_id)",
        "constraint trace_events_parent_scope_fk foreign key (organization_id, project_id, parent_event_id)",
        "constraint observations_case_scope_fk foreign key (organization_id, project_id, case_result_id)",
        "constraint observations_trace_event_scope_fk foreign key (organization_id, project_id, trace_event_id)",
        "constraint artifacts_case_scope_fk foreign key (organization_id, project_id, case_result_id)",
        "constraint evidence_bundles_case_scope_fk foreign key (organization_id, project_id, case_result_id)",
    ]:
        assert required in normalized

    assert re.search(r"on delete set null(?! \([^)]+\))", normalized) is None
    for column in ["environment_id", "dataset_id", "case_result_id", "trace_event_id", "parent_event_id", "run_id", "workspace_id", "idempotency_key_id"]:
        assert f"on delete set null ({column})" in normalized


def test_a1_foundation_migration_has_idempotency_usage_and_audit_guards() -> None:
    normalized = _normalize(_migration_sql())

    assert "constraint idempotency_keys_org_project_key_unique unique (organization_id, project_id, idempotency_key)" in normalized
    assert "constraint idempotency_keys_scope_fingerprint_unique unique (organization_id, project_id, request_method, request_path, fingerprint)" in normalized
    assert "raise exception 'idempotency key conflict" in normalized
    assert "raise exception 'idempotency fingerprint conflict" in normalized
    assert "using errcode = '23505'" in normalized

    assert "create unique index if not exists idx_usage_ledger_idempotency_key_unique on usage_ledger" in normalized
    assert "usage_ledger(organization_id, project_id, idempotency_key_id) where idempotency_key_id is not null" in normalized
    assert "create or replace function rollup_usage" in normalized
    assert "from usage_ledger u" in normalized
    assert "coalesce(sum(u.quantity), 0)::numeric" in normalized

    assert "create or replace function audit_chain_tail" in normalized
    assert "from audit_log" in normalized
    assert "order by created_at desc, id desc" in normalized
    assert "prev_hash text" in normalized
    assert "entry_hash text not null" in normalized
    assert "constraint audit_log_entry_hash_key unique (entry_hash)" in normalized


def test_a1_foundation_migration_has_worker_persistence_repository_contract() -> None:
    sql = _migration_sql()
    normalized = _normalize(sql)

    contract = {
        "idempotency_keys": [
            "organization_id uuid not null",
            "project_id uuid not null",
            "idempotency_key text not null",
            "fingerprint text not null",
            "constraint idempotency_keys_project_scope_fk foreign key (organization_id, project_id)",
        ],
        "usage_ledger": [
            "organization_id uuid not null",
            "project_id uuid not null",
            "idempotency_key_id uuid references idempotency_keys(id) on delete set null (idempotency_key_id)",
            "quantity numeric(20, 6) not null check (quantity >= 0)",
            "constraint usage_ledger_period_check check (period_end > period_start)",
        ],
        "jobs": [
            "organization_id uuid not null",
            "project_id uuid not null",
            "status text not null default 'queued' check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled', 'dead_letter'))",
            "dedupe_key text",
            "constraint jobs_org_project_dedupe_key unique (organization_id, project_id, job_type, dedupe_key)",
        ],
        "audit_log": [
            "organization_id uuid not null",
            "project_id uuid not null",
            "actor_type text not null",
            "action text not null",
            "entry_hash text not null",
            "constraint audit_log_entry_hash_key unique (entry_hash)",
        ],
    }

    for table, required_fragments in contract.items():
        body = _table_body(sql, table)
        for fragment in required_fragments:
            assert fragment in body, f"{table} missing persistence contract fragment: {fragment}"

    for index_fragment in [
        "create unique index if not exists idx_usage_ledger_idempotency_key_unique on usage_ledger(organization_id, project_id, idempotency_key_id) where idempotency_key_id is not null",
        "create index if not exists idx_jobs_ready_queue on jobs(status, run_after, priority, created_at) where status = 'queued'",
        "create index if not exists idx_jobs_project_status on jobs(organization_id, project_id, status, created_at desc)",
        "create index if not exists idx_audit_log_scope_created on audit_log(organization_id, project_id, created_at desc)",
        "create index if not exists idx_audit_log_resource on audit_log(organization_id, resource_type, resource_id, created_at desc)",
    ]:
        assert index_fragment in normalized


def test_a1_foundation_migration_satisfies_go_postgres_vertical_slice_manifest() -> None:
    sql = _migration_sql()
    normalized = _normalize(sql)
    manifest = build_go_postgres_vertical_slice_manifest()

    declared_tables = _declared_objects(sql, r"create\s+table\s+if\s+not\s+exists\s+(\w+)")
    declared_functions = _declared_objects(sql, r"create\s+or\s+replace\s+function\s+(\w+)")
    declared_indexes = _declared_objects(sql, r"create\s+(?:unique\s+)?index\s+if\s+not\s+exists\s+(\w+)")

    assert set(manifest["tables"]) <= declared_tables
    assert set(manifest["functions"]) <= declared_functions

    for table, contract in manifest["contract"].items():
        body = _table_body(sql, table)
        for column in contract["required_columns"]:
            assert f"{column} " in body, f"{table} missing Go/Postgres column {column}"
        for index in contract["required_indexes"]:
            assert index in declared_indexes, f"{table} missing Go/Postgres index {index}"

    assert "constraint jobs_org_project_dedupe_key unique (organization_id, project_id, job_type, dedupe_key)" in normalized
    assert "constraint idempotency_keys_scope_fingerprint_unique unique" in normalized
    assert "constraint usage_ledger_period_check check (period_end > period_start)" in normalized
