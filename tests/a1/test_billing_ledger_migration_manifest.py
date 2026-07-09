from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - jsonschema is optional in the light test env
    Draft202012Validator = None

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs" / "a1" / "schemas" / "a1_billing_ledger_migration_manifest.json"
SEMANTIC_EVIDENCE_PATH = ROOT / "docs" / "a1" / "evidence" / "billing_sql_semantic_contract.json"
SEMANTIC_SCHEMA_PATH = ROOT / "docs" / "a1" / "schemas" / "billing_sql_semantic_contract.schema.json"
GO_POSTGRES_PATH = ROOT / "packages" / "go" / "ashrclone" / "postgres.go"
GO_TYPES_PATH = ROOT / "packages" / "go" / "ashrclone" / "types.go"


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _semantic_evidence() -> dict[str, Any]:
    return json.loads(SEMANTIC_EVIDENCE_PATH.read_text(encoding="utf-8"))


def _sql() -> str:
    return (ROOT / _manifest()["migration"]).read_text(encoding="utf-8")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _create_table_order(sql: str) -> list[str]:
    return re.findall(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-z_]+)\s*\(", sql, flags=re.IGNORECASE)


def _table_body(sql: str, table: str) -> str:
    match = re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(table)}\s*\((.*?)\n\);", sql, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"missing table {table}"
    return match.group(1)


def _columns(sql: str, table: str) -> set[str]:
    columns: set[str] = set()
    for line in _table_body(sql, table).splitlines():
        stripped = line.strip().rstrip(",")
        if not stripped or stripped.upper().startswith(("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK")):
            continue
        columns.add(stripped.split()[0])
    return columns


def _index_statement(sql: str, index: str) -> str:
    match = re.search(rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+{re.escape(index)}\b.*?;", sql, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"missing index {index}"
    return match.group(0)


def _policy_statement(sql: str, policy: str, table: str) -> str:
    match = re.search(rf"CREATE\s+POLICY\s+{re.escape(policy)}\s+ON\s+{re.escape(table)}\b.*?;", sql, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"missing policy {policy}"
    return match.group(0)


def _function_statement(sql: str, function: str) -> str:
    match = re.search(rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+{re.escape(function)}\s*\(.*?\n\$\$;", sql, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"missing function {function}"
    return match.group(0)


def test_billing_ledger_migration_manifest_points_to_owned_public_sql():
    manifest = _manifest()
    assert manifest["version"] == 2
    assert manifest["migration"] == "services/api/migrations/002_a1_billing_ledger.sql"
    assert (ROOT / manifest["migration"]).is_file()
    assert "private_refs" not in json.dumps(manifest)
    assert manifest["public_safety"] == {
        "raw_provider_payload_stored": False,
        "raw_provider_secret_stored": False,
        "raw_card_data_stored": False,
        "provider_calls_executed": False,
    }


def test_billing_ledger_migration_tables_columns_indexes_and_constraints():
    manifest = _manifest()
    sql = _sql()
    assert _create_table_order(sql) == [table["name"] for table in manifest["tables"]]

    for table in manifest["tables"]:
        body = _normalize(_table_body(sql, table["name"]))
        columns = _columns(sql, table["name"])
        for column in table["required_columns"]:
            assert column in columns, f"{table['name']} missing {column}"
        for constraint in table["required_constraints"]:
            assert constraint in body, f"{table['name']} missing {constraint}"
        for index in table["required_indexes"]:
            assert f" on {table['name']}" in _normalize(_index_statement(sql, index))


def test_billing_ledger_migration_enforces_rls_for_all_tables():
    sql = _sql()
    normalized = _normalize(sql)
    for table in _manifest()["tables"]:
        table_name = table["name"]
        predicate = f"{table['tenant_column']} = a1_current_organization_id()"
        assert f"alter table {table_name} enable row level security" in normalized
        assert f"alter table {table_name} force row level security" in normalized
        assert f"drop policy if exists {table['rls_policy']} on {table_name}" in normalized
        policy = _normalize(_policy_statement(sql, table["rls_policy"], table_name))
        assert f"using ({predicate})" in policy
        assert f"with check ({predicate})" in policy


def test_billing_ledger_migration_functions_cover_replay_conflict_and_rollup():
    sql = _sql()
    for function, contract in _manifest()["required_functions"].items():
        function_sql = _normalize(_function_statement(sql, function))
        for fragment in contract["must_contain"]:
            assert _normalize(fragment) in function_sql, f"{function} missing {fragment}"


def test_billing_ledger_migration_never_stores_raw_provider_payload_or_secret_columns():
    sql = _normalize(_sql())
    forbidden_columns = ["raw_payload jsonb", "payload jsonb", "secret_value", "card_number", "client_secret", "provider_secret", "provider_config"]
    for forbidden in forbidden_columns:
        assert forbidden not in sql
    assert "raw_payload_included boolean not null default false check (raw_payload_included = false)" in sql
    for marker in ["sk_live_", "sk_test_", "rk_live_", "rk_test_", "whsec_", "bearer[[:space:]]"]:
        assert marker in sql


def test_billing_sql_semantic_contract_evidence_matches_schema_and_manifest():
    evidence = _semantic_evidence()
    schema = json.loads(SEMANTIC_SCHEMA_PATH.read_text(encoding="utf-8"))
    manifest_contract = _manifest()["semantic_contracts"]

    if Draft202012Validator is not None:
        Draft202012Validator(schema).validate(evidence)

    assert evidence["public_safe"] is True
    assert evidence["provider_config_storage"]["durable_policy"] == manifest_contract["provider_config"]["durable_storage_policy"]
    assert evidence["provider_config_storage"]["provider_config_column_present"] is False
    assert evidence["provider_config_storage"]["provider_config_object_persisted"] is False
    assert evidence["provider_config_storage"]["hash_columns"] == manifest_contract["provider_config"]["required_hash_columns"]
    assert evidence["replay_semantics"]["accepted"]["ledger_mutation_count"] == 1
    assert evidence["replay_semantics"]["duplicate"]["ledger_mutation_count"] == 0
    assert evidence["replay_semantics"]["conflict"]["ledger_mutation_count"] == 0

    text = json.dumps(evidence, sort_keys=True)
    for forbidden in ("sk_test_", "sk_live_", "rk_test_", "rk_live_", "whsec_", "Bearer "):
        assert forbidden not in text
    assert re.search(r"(?:\d[ -]*?){13,19}", text) is None


def test_billing_provider_config_is_hash_or_reference_only_in_durable_sql():
    sql = _normalize(_sql())
    evidence = _semantic_evidence()

    assert "payload_sha256 text not null check (payload_sha256 ~ '^[a-f0-9]{64}$')" in sql
    assert "p_payload_sha256 !~ '^[a-f0-9]{64}$'" in sql
    for forbidden in evidence["provider_config_storage"]["forbidden_durable_columns"]:
        if forbidden == "raw_payload":
            assert "raw_payload jsonb" not in sql
            continue
        if forbidden == "payload":
            assert "payload jsonb" not in sql
            continue
        assert forbidden.lower() not in sql
    for reference in evidence["provider_config_storage"]["reference_only_fields"]:
        _, column = reference.split(".", 1)
        assert column.lower() in sql


def test_billing_replay_duplicate_and_conflict_are_zero_mutation_in_sql_and_python_fixture():
    sql = _normalize(_function_statement(_sql(), "ingest_billing_provider_event"))
    evidence = _semantic_evidence()["replay_semantics"]

    assert "replay_status := 'duplicate'" in sql
    assert "replay_status := 'conflict'" in sql
    assert sql.count("ledger_mutation_count := 0") >= 2
    assert "ledger_mutation_count := 1" in sql
    assert evidence["duplicate"]["payload_sha256_relation"] == "same_provider_event_same_hash"
    assert evidence["conflict"]["payload_sha256_relation"] == "same_provider_event_different_hash"


def test_billing_object_evidence_linkage_is_hash_only_across_sql_and_go_stubs():
    sql = _normalize(_sql())
    go_postgres = _normalize(GO_POSTGRES_PATH.read_text(encoding="utf-8"))
    go_types = GO_TYPES_PATH.read_text(encoding="utf-8")
    evidence = _semantic_evidence()["object_evidence_linkage"]

    assert "ledger_event_id uuid" in sql
    assert "provider_event_id uuid" in sql
    assert re.search(r"foreign key \([^)]*provider_event_id[^)]*\)\s*references billing_provider_events\s*\(", sql)
    assert "ledger_event_id = inserted_ledger.id" in sql

    for item in evidence["go_postgres_hash_only_objects"]:
        table_name = item["table"]
        table_start = go_postgres.index(f"create table if not exists {table_name}")
        table_end = go_postgres.find(");", table_start)
        table_sql = go_postgres[table_start:table_end]
        assert item["object_id_column"] in table_sql
        assert item["sha256_column"] in table_sql
        assert " jsonb" not in table_sql

    assert "ProviderConfig     JSONMap" in go_types
    assert "RawPayloadIncluded bool" in go_types
    assert "RawSecretsIncluded bool" in go_types
