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


def _go_operation_const(operation: str) -> str:
    return {
        "sdk.submit": "usageOperationSubmit",
        "run.upload": "usageOperationRunUpload",
        "trace.ingest": "usageOperationTraceIngest",
        "artifact.manifest": "usageOperationArtifactManifest",
        "worker.job.enqueue": "usageOperationWorkerJobEnqueue",
        "worker.job.lease": "usageOperationWorkerJobLease",
        "worker.job.complete": "usageOperationWorkerJobComplete",
        "worker.job.fail": "usageOperationWorkerJobFail",
    }[operation]


def _go_meter_suffix(meter: str) -> str:
    return {
        "runs": "Runs",
        "media": "Media",
        "observations": "Observations",
        "storage_bytes": "StorageBytes",
    }[meter]


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


def _trigger_statement(sql: str, trigger_name: str) -> str:
    match = re.search(
        rf"CREATE\s+TRIGGER\s+{re.escape(trigger_name)}\b.*?;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing trigger {trigger_name}"
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


def test_a1_foundation_migration_manifest_enforces_quota_dimensions_and_triggers() -> None:
    manifest = _manifest()
    sql = _migration_sql()
    normalized_sql = _normalize(sql)
    quoted_dimensions = ", ".join(f"'{meter}'" for meter in manifest["quota_dimensions"])

    for table_name in ["usage_ledger", "usage_rollups", "quota_policies"]:
        body = _normalize(_table_body(sql, table_name))
        assert f"check (meter in ({quoted_dimensions}))" in body

    for trigger_name, contract in manifest["required_triggers"].items():
        trigger_sql = _normalize(_trigger_statement(sql, trigger_name))
        assert f"create trigger {trigger_name}" in trigger_sql
        assert _normalize(contract["timing"]) in trigger_sql
        assert f"on {contract['table']}" in trigger_sql
        assert f"execute function {contract['function']}()" in trigger_sql
        assert f"drop trigger if exists {trigger_name} on {contract['table']}" in normalized_sql


def test_a1_foundation_quota_operation_mapping_is_explicit_and_complete() -> None:
    sql = _migration_sql()
    mapping_sql = _normalize(_function_statement(sql, "operation_meter_mapping"))
    expected_mappings = {
        "sdk.submit": ("runs", "count", "1::numeric"),
        "run.upload": ("media", "count", "1::numeric"),
        "trace.ingest": ("observations", "count", "1::numeric"),
        "artifact.manifest": ("storage_bytes", "bytes", "0::numeric"),
        "worker.job.enqueue": ("runs", "count", "1::numeric"),
        "worker.job.lease": ("runs", "count", "0::numeric"),
        "worker.job.complete": ("runs", "count", "0::numeric"),
        "worker.job.fail": ("runs", "count", "0::numeric"),
    }

    for operation, (meter, unit, default_quantity) in expected_mappings.items():
        fragment = f"('{operation}', '{meter}', '{unit}', {default_quantity})"
        assert fragment in mapping_sql

    assert "raise exception 'unsupported quota operation: %'" in mapping_sql


def test_a1_foundation_go_and_sql_quota_meter_catalogs_match() -> None:
    sql = _normalize(_function_statement(_migration_sql(), "operation_meter_mapping"))
    go_quota = (ROOT / "packages" / "go" / "releasefoundry" / "quota.go").read_text(encoding="utf-8")
    expected = {
        "sdk.submit": ("runs", "count", 1),
        "run.upload": ("media", "count", 1),
        "trace.ingest": ("observations", "count", 1),
        "artifact.manifest": ("storage_bytes", "bytes", 0),
        "worker.job.enqueue": ("runs", "count", 1),
        "worker.job.lease": ("runs", "count", 0),
        "worker.job.complete": ("runs", "count", 0),
        "worker.job.fail": ("runs", "count", 0),
    }

    for operation, (meter, unit, default_quantity) in expected.items():
        sql_fragment = f"('{operation}', '{meter}', '{unit}', {default_quantity}::numeric)"
        assert sql_fragment in sql
        go_pattern = re.compile(
            rf"Operation:\s*{re.escape(_go_operation_const(operation))},\s*Meter:\s*QuotaMeter{_go_meter_suffix(meter)},\s*Unit:\s*\"{unit}\",\s*DefaultQuantity:\s*{default_quantity}"
        )
        assert go_pattern.search(go_quota), f"Go quota mapping drift for {operation} -> {meter}/{unit}/{default_quantity}"

    assert "return OperationMeter{}, false" in go_quota


def test_a1_foundation_quota_policy_view_and_function_share_active_window_contract() -> None:
    sql = _migration_sql()
    normalized_sql = _normalize(sql)
    policy_sql = _normalize(_function_statement(sql, "current_quota_policy"))

    assert "create or replace view active_quota_policies as select * from quota_policies" in normalized_sql
    for fragment in (
        "status = 'active'",
        "effective_from <= now()",
        "effective_until is null or effective_until > now()",
    ):
        assert fragment in normalized_sql

    for fragment in (
        "status = 'active'",
        "effective_from <= p_at",
        "effective_until is null or effective_until > p_at",
        "order by enforcement_mode desc, period asc, limit_quantity asc",
    ):
        assert fragment in policy_sql


def test_a1_foundation_transactional_quota_check_is_idempotent_and_audits_denials() -> None:
    sql = _migration_sql()
    check_sql = _normalize(_function_statement(sql, "check_quota_and_insert_usage"))
    audit_sql = _normalize(_function_statement(sql, "append_quota_denied_audit_event"))

    for fragment in (
        "operation_meter_mapping(p_operation)",
        "idempotency_key_id = p_idempotency_key_id",
        "for update",
        "idempotent_replay := true",
        "pg_advisory_xact_lock",
        "current_quantity + attempted_quantity > policy_record.limit_quantity",
        "append_quota_denied_audit_event",
        "denial_reason := 'quota_exceeded'",
        "insert into usage_ledger",
        "operation, meter, quantity, unit",
        "on conflict (organization_id, project_id, idempotency_key_id) where idempotency_key_id is not null",
        "returning * into inserted_usage",
    ):
        assert fragment in check_sql

    for fragment in (
        "'quota.denied'",
        "'quota_check'",
        "audit_chain_tail(p_organization_id, p_project_id)",
        "insert into audit_log",
        "attempted_quantity",
        "current_quantity",
        "limit_quantity",
    ):
        assert fragment in audit_sql

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
