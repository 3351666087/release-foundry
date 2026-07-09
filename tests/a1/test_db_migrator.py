from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from services.api.data_model import DATA_MODEL_SCHEMA_VERSION, TABLES, Table, c, ix
from services.api.db_migrator import (
    SCHEMA_LEDGER_TABLE,
    apply_migration_plan,
    apply_to_memory_and_introspect,
    build_ledger_entry,
    build_go_postgres_vertical_slice_manifest,
    generate_migration_plan,
    introspect_sqlite,
    validate_schema_ledger,
    validate_sqlite_drift,
    validate_tenant_indexes,
)

ROOT = Path(__file__).resolve().parents[2]
LARGE_SAAS_MIGRATION_PATH = ROOT / "services" / "api" / "migrations" / "001_a1_large_saas_foundation.sql"


def test_db_migrator_generates_deterministic_sqlite_plan_from_data_model():
    plan = generate_migration_plan()

    assert plan.schema_version == DATA_MODEL_SCHEMA_VERSION
    assert plan.dialect == "sqlite"
    assert plan.is_valid is True
    assert plan.tenant_index_violations == ()
    assert re.fullmatch(r"[0-9a-f]{64}", plan.checksum)
    assert plan.steps[0].name == "create_table_organizations"
    assert plan.steps[0].kind == "create_table"
    assert 'CREATE TABLE IF NOT EXISTS "organizations"' in plan.steps[0].sql
    assert "DEFAULT CURRENT_TIMESTAMP" in plan.sql_script()
    assert "DEFAULT '{}'" in plan.sql_script()
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS "usage_ledger_idempotency_uidx"' in plan.sql_script()
    assert "WHERE idempotency_key IS NOT NULL" in plan.sql_script()

    second_plan = generate_migration_plan()
    assert plan.sql_script() == second_plan.sql_script()
    assert plan.checksum == second_plan.checksum


def test_db_migrator_generates_postgres_compatible_plan_and_ledger_sql():
    plan = generate_migration_plan(dialect="postgres")

    assert plan.dialect == "postgres"
    assert plan.is_valid is True
    assert re.fullmatch(r"[0-9a-f]{64}", plan.checksum)
    assert 'CREATE TABLE IF NOT EXISTS "organizations"' in plan.sql_script()
    assert '"metadata" JSONB DEFAULT \'{}\'::jsonb' in plan.sql_script()
    assert '"created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP' in plan.sql_script()
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS "usage_ledger_idempotency_uidx"' in plan.sql_script()
    assert "WHERE idempotency_key IS NOT NULL" in plan.sql_script()

    ledger_sql = plan.ledger_sql_script()
    assert f'CREATE TABLE IF NOT EXISTS "{SCHEMA_LEDGER_TABLE}"' in ledger_sql
    assert "applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP" in ledger_sql
    assert "ON CONFLICT (schema_version) DO UPDATE SET" in ledger_sql
    assert plan.checksum in ledger_sql


def test_db_migrator_exposes_go_postgres_vertical_slice_contract():
    manifest = build_go_postgres_vertical_slice_manifest()

    assert manifest["dialect"] == "postgres"
    assert manifest["tables"] == ["audit_log", "idempotency_keys", "jobs", "runs", "usage_ledger"]
    assert manifest["functions"] == ["audit_chain_tail", "ensure_idempotency_fingerprint", "rollup_usage"]

    contract = manifest["contract"]
    assert contract["runs"]["required_columns"] == [
        "organization_id",
        "project_id",
        "status",
        "request_fingerprint",
        "created_at",
        "updated_at",
    ]
    assert "idx_runs_project_status" in contract["runs"]["required_indexes"]
    assert "idx_usage_ledger_idempotency_key_unique" in contract["usage_ledger"]["required_indexes"]
    assert "idx_jobs_ready_queue" in contract["jobs"]["required_indexes"]


def test_large_saas_postgres_migration_declares_organization_rls_contract():
    migration_sql = LARGE_SAAS_MIGRATION_PATH.read_text(encoding="utf-8")
    normalized_sql = re.sub(r"\s+", " ", migration_sql).lower()
    table_names = re.findall(r"^CREATE TABLE IF NOT EXISTS (\w+) ", migration_sql, flags=re.MULTILINE)

    assert "current_setting('app.a1_organization_id', true)" in normalized_sql
    assert table_names

    for table_name in table_names:
        assert f"alter table {table_name} enable row level security" in normalized_sql
        assert f"alter table {table_name} force row level security" in normalized_sql
        assert f"drop policy if exists {table_name}_organization_isolation on {table_name}" in normalized_sql
        assert f"create policy {table_name}_organization_isolation on {table_name}" in normalized_sql

    for table_name in set(table_names) - {"organizations"}:
        assert (
            f"create policy {table_name}_organization_isolation on {table_name} "
            "using (organization_id = a1_current_organization_id()) "
            "with check (organization_id = a1_current_organization_id())"
        ) in normalized_sql

    assert (
        "create policy organizations_organization_isolation on organizations "
        "using (id = a1_current_organization_id()) "
        "with check (id = a1_current_organization_id())"
    ) in normalized_sql


def test_db_migrator_rollback_plan_drops_indexes_tables_and_ledger_entry():
    plan = generate_migration_plan(dialect="postgres")

    rollback_sql = plan.rollback_sql_script()

    assert rollback_sql.startswith(f'DELETE FROM "{SCHEMA_LEDGER_TABLE}" WHERE schema_version =')
    assert 'DROP INDEX IF EXISTS "audit_log_actor_idx";' in rollback_sql
    assert 'DROP TABLE IF EXISTS "audit_log" CASCADE;' in rollback_sql
    assert rollback_sql.index('DROP INDEX IF EXISTS "audit_log_actor_idx";') < rollback_sql.index(
        'DROP TABLE IF EXISTS "audit_log" CASCADE;'
    )


def test_db_migrator_validates_schema_ledger_checksum_and_drift():
    plan = generate_migration_plan(dialect="postgres")
    entry = build_ledger_entry(plan)

    assert entry.to_manifest()["dialect"] == "postgres"
    assert validate_schema_ledger(entry, plan).is_valid is True

    mismatch = validate_schema_ledger({"schema_version": plan.schema_version, "checksum": "0" * 64}, plan)
    assert mismatch.is_valid is False
    assert mismatch.issues == (f"schema checksum mismatch: expected {plan.checksum}, observed {'0' * 64}",)

    missing = validate_schema_ledger(None, plan)
    assert missing.is_valid is False
    assert "missing schema_version ledger row" in missing.issues
    assert "missing schema checksum" in missing.issues


def test_db_migrator_can_record_and_validate_sqlite_schema_ledger():
    plan = generate_migration_plan()
    connection = sqlite3.connect(":memory:")
    try:
        apply_migration_plan(plan, connection, record_ledger=True)
        report = validate_sqlite_drift(connection, plan)
        connection.execute(f'UPDATE "{SCHEMA_LEDGER_TABLE}" SET checksum = ?', ("bad",))
        drift = validate_sqlite_drift(connection, plan)
    finally:
        connection.close()

    assert report.is_valid is True
    assert drift.is_valid is False
    assert drift.issues == (f"schema checksum mismatch: expected {plan.checksum}, observed bad",)


def test_db_migrator_refuses_to_execute_postgres_plan_on_sqlite():
    with pytest.raises(ValueError, match="only executes sqlite plans"):
        apply_migration_plan(generate_migration_plan(dialect="postgres"), sqlite3.connect(":memory:"))


def test_db_migrator_validates_tenant_index_contract_and_bad_indexes():
    bad_tables = (
        Table(
            "bad_rows",
            "Bad fixture",
            (c("tenant_id", "text"), c("row_id", "text"), c("status", "text")),
            ("row_id",),
            (ix("bad_status_idx", ("status", "tenant_id")),),
        ),
    )

    violations = validate_tenant_indexes(bad_tables)

    assert "bad_rows: primary key must start with tenant_id" in violations
    assert "bad_rows.bad_status_idx: tenant-scoped index must start with tenant_id" in violations


def test_db_migrator_can_apply_to_sqlite_memory_and_introspect_names():
    snapshot = apply_to_memory_and_introspect()

    assert set(snapshot.table_names) == {table.name for table in TABLES}
    expected_indexes = {index.name for table in TABLES for index in table.indexes}
    assert expected_indexes.issubset(set(snapshot.index_names))
    assert "organizations" in snapshot.table_names
    assert "runs_project_status_idx" in snapshot.index_names


def test_db_migrator_can_apply_to_supplied_connection_and_is_idempotent():
    plan = generate_migration_plan()
    connection = sqlite3.connect(":memory:")
    try:
        returned = apply_migration_plan(plan, connection)
        assert returned is connection
        apply_migration_plan(plan, connection)
        snapshot = introspect_sqlite(connection)
    finally:
        connection.close()

    assert "audit_log" in snapshot.table_names
    assert "audit_log_actor_idx" in snapshot.index_names
