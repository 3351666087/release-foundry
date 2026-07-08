from __future__ import annotations

import sqlite3

from services.api.data_model import DATA_MODEL_SCHEMA_VERSION, TABLES, Table, c, ix
from services.api.db_migrator import (
    apply_migration_plan,
    apply_to_memory_and_introspect,
    generate_migration_plan,
    introspect_sqlite,
    validate_tenant_indexes,
)


def test_db_migrator_generates_deterministic_sqlite_plan_from_data_model():
    plan = generate_migration_plan()

    assert plan.schema_version == DATA_MODEL_SCHEMA_VERSION
    assert plan.dialect == "sqlite"
    assert plan.is_valid is True
    assert plan.tenant_index_violations == ()
    assert plan.steps[0].name == "create_table_organizations"
    assert plan.steps[0].kind == "create_table"
    assert 'CREATE TABLE IF NOT EXISTS "organizations"' in plan.steps[0].sql
    assert "DEFAULT CURRENT_TIMESTAMP" in plan.sql_script()
    assert "DEFAULT '{}'" in plan.sql_script()
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS "usage_ledger_idempotency_uidx"' in plan.sql_script()
    assert "WHERE idempotency_key IS NOT NULL" in plan.sql_script()

    assert plan.sql_script() == generate_migration_plan().sql_script()


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
