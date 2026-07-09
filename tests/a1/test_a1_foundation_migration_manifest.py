from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs" / "a1" / "schemas" / "a1_foundation_migration_manifest.json"


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _migration_sql() -> str:
    manifest = _manifest()
    migration = ROOT / manifest["migration"]
    return migration.read_text(encoding="utf-8")


def _without_comments(sql: str) -> str:
    return re.sub(r"--.*", "", sql)


def _normalize(sql: str) -> str:
    return re.sub(r"\s+", " ", _without_comments(sql)).strip().lower()


def _find_balanced_parentheses(sql: str, open_index: int) -> int:
    depth = 0
    in_single_quote = False
    index = open_index
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if char == "'":
            if in_single_quote and next_char == "'":
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    raise AssertionError("unbalanced SQL parentheses")


def _table_body(sql: str, table: str) -> str:
    match = re.search(rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(table)}\s*\(", sql, flags=re.IGNORECASE)
    assert match, f"missing CREATE TABLE for {table}"
    open_index = sql.index("(", match.start())
    close_index = _find_balanced_parentheses(sql, open_index)
    return sql[open_index + 1 : close_index]


def _split_top_level_csv(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_single_quote = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if char == "'":
            if in_single_quote and next_char == "'":
                index += 2
                continue
            in_single_quote = not in_single_quote
        elif not in_single_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _table_columns(sql: str, table: str) -> set[str]:
    columns: set[str] = set()
    for item in _split_top_level_csv(_table_body(sql, table)):
        head = item.split(None, 1)[0].strip('"').lower()
        if head not in {"constraint", "primary", "foreign", "unique", "check", "exclude"}:
            columns.add(head)
    return columns


def _create_table_order(sql: str) -> list[str]:
    return re.findall(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-z_][a-z0-9_]*)\s*\(", sql, flags=re.IGNORECASE)


def _index_statement(sql: str, index_name: str) -> str:
    match = re.search(
        rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+{re.escape(index_name)}\s+ON\s+[a-z_][a-z0-9_]*.*?;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing index {index_name}"
    return match.group(0)


def _policy_statement(sql: str, policy_name: str, table: str) -> str:
    match = re.search(
        rf"CREATE\s+POLICY\s+{re.escape(policy_name)}\s+ON\s+{re.escape(table)}\b.*?;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing policy {policy_name} on {table}"
    return match.group(0)


def _function_statement(sql: str, function_name: str) -> str:
    match = re.search(
        rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+{re.escape(function_name)}\s*\(.*?\n\$\$;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing function {function_name}"
    return match.group(0)


def test_a1_foundation_migration_manifest_points_to_public_owned_migration() -> None:
    manifest = _manifest()
    migration_path = manifest["migration"]

    assert manifest["version"] == 1
    assert migration_path == "services/api/migrations/001_a1_large_saas_foundation.sql"
    assert (ROOT / migration_path).is_file()
    assert "private_refs" not in json.dumps(manifest).lower()
    assert "secret" not in manifest["optional_live_hook"]["env"].lower()


def test_a1_foundation_migration_manifest_matches_table_order_columns_and_indexes() -> None:
    manifest = _manifest()
    sql = _migration_sql()
    manifest_tables = [table["name"] for table in manifest["tables"]]

    assert _create_table_order(sql) == manifest_tables

    for extension in manifest["required_extension_statements"]:
        assert _normalize(extension) in _normalize(sql)

    for table in manifest["tables"]:
        table_name = table["name"]
        columns = _table_columns(sql, table_name)
        for column in table["required_columns"]:
            assert column in columns, f"{table_name} missing column {column}"
        for index_name in table["required_indexes"]:
            index_sql = _normalize(_index_statement(sql, index_name))
            assert f" on {table_name}" in index_sql, f"{index_name} must target {table_name}"


def test_a1_foundation_migration_manifest_enforces_rls_contract() -> None:
    sql = _migration_sql()
    normalized_sql = _normalize(sql)

    for table in _manifest()["tables"]:
        table_name = table["name"]
        tenant_column = table["tenant_column"]
        policy_name = table["rls_policy"]
        tenant_predicate = f"{tenant_column} = a1_current_organization_id()"

        assert f"alter table {table_name} enable row level security" in normalized_sql
        assert f"alter table {table_name} force row level security" in normalized_sql
        assert f"drop policy if exists {policy_name} on {table_name}" in normalized_sql

        policy = _normalize(_policy_statement(sql, policy_name, table_name))
        assert f"using ({tenant_predicate})" in policy
        assert f"with check ({tenant_predicate})" in policy


def test_a1_foundation_migration_manifest_enforces_idempotency_and_rollup_helpers() -> None:
    sql = _migration_sql()

    for function_name, contract in _manifest()["required_functions"].items():
        function_sql = _normalize(_function_statement(sql, function_name))
        for required_fragment in contract["must_contain"]:
            assert _normalize(required_fragment) in function_sql, f"{function_name} missing {required_fragment}"


def test_a1_foundation_optional_live_hook_stays_env_gated() -> None:
    manifest = _manifest()
    hook = manifest["optional_live_hook"]
    live_test_path = ROOT / hook["smoke_test"]
    live_test = live_test_path.read_text(encoding="utf-8")

    assert hook["env"] == "A1_POSTGRES_TEST_DSN"
    assert hook["psql_bin_env"] == "A1_PSQL_BIN"
    assert hook["env"] in live_test
    assert "pytest.skip" in live_test
    assert os.environ.get(hook["env"], "") == "" or live_test_path.is_file()
