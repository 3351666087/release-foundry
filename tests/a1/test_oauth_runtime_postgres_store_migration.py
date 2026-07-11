from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services" / "api" / "migrations" / "007_a1_oauth_runtime_store.sql"

TABLES = (
    "oauth_runtime_transactions",
    "oauth_replay_ledger",
    "oauth_token_opaque_refs",
    "oauth_account_connections",
    "oauth_revocation_outbox",
    "oauth_runtime_audit",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql()).lower()


def _table_body(table: str) -> str:
    sql = _normalized()
    start = sql.index(f"create table if not exists {table} (")
    return sql[start : sql.index(");", start)]


def test_runtime_oauth_schema_is_transactional_and_additive() -> None:
    migrations = sorted(MIGRATION.parent.glob("*.sql"))

    assert MIGRATION in migrations
    assert MIGRATION.name > "006_a1_oauth_lifecycle.sql"
    assert _normalized().startswith("-- a1 durable oauth runtime store.")
    assert _normalized().strip().endswith("commit;")


def test_runtime_tables_force_tenant_and_project_rls() -> None:
    sql = _normalized()

    for table in TABLES:
        body = _table_body(table)
        assert "organization_id uuid not null" in body
        assert "project_id uuid not null" in body
        assert f"alter table {table} enable row level security" in sql
        assert f"alter table {table} force row level security" in sql
        assert f"drop policy if exists {table}_tenant_isolation" in sql
        assert f"create policy {table}_tenant_isolation" in sql
    assert sql.count(
        "organization_id = a1_current_organization_id() and project_id = a1_current_project_id()"
    ) >= len(TABLES) * 2


def test_runtime_store_has_ttl_replay_and_atomic_claims() -> None:
    sql = _normalized()
    transactions = _table_body("oauth_runtime_transactions")
    replay = _table_body("oauth_replay_ledger")
    outbox = _table_body("oauth_revocation_outbox")

    assert "oauth_runtime_transactions_ttl_check check (expires_at > created_at)" in transactions
    assert "unique (provider, state_digest)" in transactions
    assert "unique (provider, replay_kind, value_digest)" in replay
    assert "oauth_replay_ledger_ttl_check check (expires_at > observed_at)" in replay
    assert "for update" in sql
    assert "for update skip locked" in sql
    assert "status = 'consumed'" in sql
    assert "set status = 'expired', failure_code = 'expired'" in sql
    assert "return target" in sql
    assert "insert into oauth_replay_ledger" in sql
    assert "oauth_revocation_outbox_token_key unique (token_ref_id)" in outbox
    assert "oauth_runtime_transactions_pending_expiry_idx" in sql
    assert "oauth_revocation_outbox_ready_idx" in sql


def test_callback_locator_is_narrow_privileged_and_not_public() -> None:
    sql = _normalized()

    for function in (
        "a1_consume_oauth_runtime_transaction",
        "a1_revoke_oauth_token_ref",
    ):
        start = sql.index(f"create or replace function {function}")
        body = sql[start : sql.index("$$;", start) + 3]
        assert "security definer" in body
        assert "set search_path = pg_catalog, public" in body
        assert "a1_assert_role_nobypassrls(session_user)" in body
        assert f"revoke all on function {function}" in sql
    assert "to a1_runtime" in sql


def test_database_never_receives_plaintext_oauth_material() -> None:
    forbidden_columns = {
        "access_token",
        "refresh_token",
        "id_token",
        "authorization_code",
        "code_verifier",
        "client_secret",
        "raw_token",
        "raw_code",
        "raw_verifier",
        "state",
    }

    for table in TABLES:
        columns = {
            match.group(1)
            for match in re.finditer(
                r"(?:^|,)\s*([a-z][a-z0-9_]*)\s+[a-z]", _table_body(table)
            )
        }
        assert forbidden_columns.isdisjoint(columns), (table, columns)

    sql = _normalized()
    assert "transaction_ref text not null check (a1_oauth_reference_only(transaction_ref))" in sql
    assert "opaque_ref text not null check (a1_oauth_reference_only(opaque_ref))" in sql
    assert "state_digest text not null check (state_digest ~ '^[a-f0-9]{64}$')" in sql
    assert "opaque_ref_digest text not null check (opaque_ref_digest ~ '^[a-f0-9]{64}$')" in sql


def test_connections_and_outbox_are_scoped_audited_and_append_only() -> None:
    sql = _normalized()
    connections = _table_body("oauth_account_connections")

    assert "unique (organization_id, project_id, provider, account_id)" in connections
    assert (
        "unique (organization_id, project_id, provider, provider_subject_digest)"
        in connections
    )
    for table in (
        "oauth_runtime_transactions",
        "oauth_token_opaque_refs",
        "oauth_account_connections",
        "oauth_revocation_outbox",
    ):
        assert f"{table}_audit" in sql
    assert "oauth_replay_ledger_append_only" in sql
    assert "oauth_runtime_audit_append_only" in sql
