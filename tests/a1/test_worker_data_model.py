from __future__ import annotations

import json
from pathlib import Path

from services.api.data_model import (
    DATA_MODEL_SCHEMA_VERSION,
    TABLES,
    export_json_schema,
    export_sqlish_migration,
    export_tenant_index_manifest,
)

EXPECTED_TABLES = {
    "organizations",
    "workspaces",
    "projects",
    "environments",
    "datasets",
    "runs",
    "case_results",
    "trace_events",
    "artifacts",
    "evidence_bundles",
    "api_keys",
    "webhooks",
    "usage_ledger",
    "quota_policies",
    "billing_accounts",
    "integrations",
    "audit_log",
}

SCHEMA_DIR = Path("docs/a1/schemas")


def test_worker_data_model_exports_all_required_commercial_saas_tables():
    schema = export_json_schema()

    assert schema["schema_version"] == DATA_MODEL_SCHEMA_VERSION
    assert set(schema["tables"]) == EXPECTED_TABLES
    assert [table.name for table in TABLES] == schema["x-table-order"]

    for table_name, table_schema in schema["tables"].items():
        assert table_schema["type"] == "object"
        assert table_schema["additionalProperties"] is False
        assert "tenant_id" in table_schema["properties"]
        assert "tenant_id" in table_schema["required"]
        assert table_schema["x-primary-key"]
        assert table_schema["properties"]["tenant_id"]["type"] == "string"


def test_worker_data_model_sqlish_migration_is_deterministic_and_db_dependency_free():
    migration = export_sqlish_migration()

    assert migration.startswith("-- A1 Worker commercial SaaS DB-shaped data model")
    assert "CREATE TABLE organizations" in migration
    assert "CREATE TABLE audit_log" in migration
    assert "CREATE UNIQUE INDEX usage_ledger_idempotency_uidx" in migration
    assert "tenant_id TEXT NOT NULL" in migration
    assert "PRIMARY KEY (tenant_id, run_id)" in migration
    assert "postgres" not in migration.lower()
    assert "sqlite" not in migration.lower()

    assert migration == export_sqlish_migration()


def test_worker_data_model_tenant_indexes_start_with_tenant_id():
    manifest = export_tenant_index_manifest()

    assert manifest["schema_version"] == DATA_MODEL_SCHEMA_VERSION
    assert manifest["tenant_scope_column"] == "tenant_id"
    assert manifest["violations"] == []

    for table in manifest["tables"]:
        assert table["tenant_scoped"] is True
        assert table["recommended_query_prefix"] == ["tenant_id"]
        for index in table["indexes"]:
            if index["tenant_scoped"]:
                assert index["columns"][0] == "tenant_id", index


def test_worker_data_model_docs_are_generated_from_helper_exports():
    schema_doc = json.loads((SCHEMA_DIR / "worker_data_model.schema.json").read_text(encoding="utf-8"))
    index_doc = json.loads((SCHEMA_DIR / "worker_data_model.indexes.json").read_text(encoding="utf-8"))
    migration_doc = (SCHEMA_DIR / "worker_data_model.migration.sqlish").read_text(encoding="utf-8")

    assert schema_doc == export_json_schema()
    assert index_doc == export_tenant_index_manifest()
    assert migration_doc == export_sqlish_migration()
