from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "009_a1_oauth_identity_coordinator.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql().lower())


def _function(name: str, next_marker: str) -> str:
    sql = _normalized()
    start = sql.index(f"create or replace function {name}(")
    return sql[start : sql.index(next_marker, start)]


def test_migration_is_incremental_transactional_and_secret_safe() -> None:
    sql = _sql()
    normalized = _normalized()

    assert MIGRATION.name.startswith("009_")
    assert sql.startswith("-- A1 atomic OAuth-to-canonical-identity")
    assert normalized.count("begin;") == 1
    assert normalized.strip().endswith("commit;")
    forbidden_columns = (
        "authorization_code ",
        "access_token ",
        "refresh_token ",
        "id_token ",
        "raw_subject ",
        "raw_email ",
        "client_secret ",
    )
    for forbidden in forbidden_columns:
        assert forbidden not in normalized
    assert "p_opaque_ref text" in normalized
    assert "p_opaque_ref_digest text" in normalized
    assert "provider_login, email_digest" in normalized
    assert "'[redacted]'" in normalized


def test_connection_bridge_and_pending_state_are_explicit() -> None:
    sql = _normalized()

    assert "add column if not exists principal_id uuid" in sql
    assert "add column if not exists credential_id uuid" in sql
    assert "oauth_account_connections_credential_scope_fk" in sql
    assert "references identity_credentials(principal_id, id)" in sql
    assert "oauth_account_connections_identity_pair_check" in sql
    assert "'revocation_pending'" in sql
    assert "oauth_account_connections_status_time_check" in sql
    assert "provider_revoke_and_cleanup" in sql


def test_operation_ledger_is_tenant_scoped_and_idempotent() -> None:
    sql = _normalized()

    assert "create table if not exists oauth_identity_operations" in sql
    assert (
        "unique ( organization_id, project_id, operation_kind, "
        "idempotency_digest )"
    ) in sql
    assert "request_digest text not null" in sql
    assert "oauth_identity_operations_project_scope_fk" in sql
    assert "oauth_identity_operations_connection_scope_fk" in sql
    assert "oauth_identity_operations_token_scope_fk" in sql
    assert "oauth_identity_operations_outbox_scope_fk" in sql
    assert "alter table oauth_identity_operations enable row level security" in sql
    assert "alter table oauth_identity_operations force row level security" in sql
    assert "oauth_identity_operations_tenant_isolation" in sql
    assert sql.count("a1_current_organization_id()") >= 2
    assert sql.count("a1_current_project_id()") >= 2
    assert sql.count("a1_current_principal_id()") >= 2


def test_callback_coordinates_all_writes_under_one_locked_operation() -> None:
    body = _function(
        "a1_complete_oauth_identity_callback",
        "create or replace function a1_disconnect_oauth_identity_credential(",
    )

    assert "security definer" in body
    assert "set search_path = pg_catalog, public" in body
    assert "a1_oauth_identity_assert_context(" in body
    assert "from oauth_identity_operations" in body
    assert "for update" in body
    assert "oauth identity idempotency request mismatch" in body
    assert "from identity_principals" in body
    assert "from identity_credentials" in body
    assert "from oauth_token_opaque_refs" in body
    assert "from oauth_account_connections" in body
    assert "insert into identity_credentials" in body
    assert "insert into oauth_token_opaque_refs" in body
    assert "insert into oauth_account_connections" in body
    assert "'identity.oauth.callback_completed'" in body
    assert "status = 'completed'" in body


def test_disconnect_checks_last_login_before_any_domain_mutation() -> None:
    body = _function(
        "a1_disconnect_oauth_identity_credential",
        "alter table oauth_identity_operations enable row level security",
    )
    last_login = body.index("cannot disconnect the last active login credential")

    assert "security definer" in body
    assert "set search_path = pg_catalog, public" in body
    assert body.count("for update") >= 5
    assert body.index("from identity_principals") < last_login
    assert body.index("from identity_credentials") < last_login
    assert body.index("from oauth_account_connections") < last_login
    assert body.index("from oauth_token_opaque_refs") < last_login
    assert last_login < body.index("update identity_credentials")
    assert last_login < body.index("update identity_sessions")
    assert last_login < body.index("update oauth_account_connections")
    assert last_login < body.index("update oauth_token_opaque_refs")
    assert last_login < body.index("insert into oauth_revocation_outbox")
    assert "status = 'revocation_pending'" in body
    assert "'identity.oauth.revocation_pending'" in body


def test_coordinator_functions_are_private_and_runtime_only() -> None:
    sql = _normalized()
    functions = (
        "a1_oauth_identity_assert_context",
        "a1_complete_oauth_identity_callback",
        "a1_disconnect_oauth_identity_credential",
    )

    for name in functions:
        assert f"revoke all on function {name}(" in sql
        assert f"grant execute on function {name}(" in sql
    assert sql.count("grant execute on function") == len(functions)
    assert "grant select on oauth_identity_operations to a1_runtime;" in sql
