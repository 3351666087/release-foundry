from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs" / "a1" / "schemas" / "a1_billing_ledger_migration_manifest.json"


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


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
    forbidden_columns = ["raw_payload jsonb", "payload jsonb", "secret_value", "card_number", "client_secret", "provider_secret"]
    for forbidden in forbidden_columns:
        assert forbidden not in sql
    assert "raw_payload_included boolean not null default false check (raw_payload_included = false)" in sql
    for marker in ["sk_live_", "sk_test_", "rk_live_", "rk_test_", "whsec_", "bearer[[:space:]]"]:
        assert marker in sql