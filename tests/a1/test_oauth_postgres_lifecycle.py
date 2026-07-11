from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services" / "api" / "migrations" / "006_a1_oauth_lifecycle.sql"

TABLES = (
    "users",
    "oauth_attempts",
    "external_identities",
    "sessions",
    "token_secret_refs",
    "oauth_revocations",
    "oauth_audit_events",
    "oauth_outbox",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql()).lower()


def _table_body(table: str) -> str:
    sql = _normalized()
    start = sql.index(f"create table if not exists {table} (")
    end = sql.index(");", start)
    return sql[start:end]


def _function_body(function: str, next_marker: str) -> str:
    sql = _normalized()
    start = sql.index(f"create or replace function {function}")
    end = sql.index(next_marker, start)
    return sql[start:end]


def test_oauth_migration_is_additive_ordered_and_transactional() -> None:
    migrations = sorted(MIGRATION.parent.glob("*.sql"))

    assert MIGRATION in migrations
    assert MIGRATION.name > "005_a1_payment_verification_security.sql"
    assert _normalized().startswith("-- a1 postgres oauth account lifecycle.")
    assert " begin; " in f" {_normalized()} "
    assert _normalized().strip().endswith("commit;")


def test_oauth_schema_is_project_tenant_scoped_and_forces_rls() -> None:
    sql = _normalized()

    for table in TABLES:
        body = _table_body(table)
        assert "organization_id uuid not null" in body
        assert "project_id uuid not null" in body
        assert f"alter table {table} enable row level security" in sql
        assert f"alter table {table} force row level security" in sql
        assert f"create policy {table}_tenant_isolation on {table}" in sql
    assert sql.count(
        "organization_id = a1_current_organization_id() and project_id = a1_current_project_id()"
    ) >= len(TABLES) * 2
    assert "perform a1_assert_role_nobypassrls(current_user)" in sql
    assert "raise exception 'oauth tenant context mismatch'" in sql


def test_identity_and_email_uniqueness_prevent_account_conflicts() -> None:
    sql = _normalized()

    assert (
        "on users(organization_id, project_id, email_digest) "
        "where email_digest is not null and deleted_at is null"
    ) in sql
    identities = _table_body("external_identities")
    assert (
        "unique (organization_id, project_id, provider, environment, subject_digest)"
        in identities
    )
    assert (
        "unique (organization_id, project_id, user_id, provider, environment)"
        in identities
    )
    assert "oauth identity is already linked to another account" in sql
    assert "oauth account conflicts with an existing account" in sql
    assert "oauth identity conflicts with an existing account" in sql


def test_attempt_and_session_ttl_and_one_time_digest_contracts() -> None:
    attempts = _table_body("oauth_attempts")
    sessions = _table_body("sessions")
    refs = _table_body("token_secret_refs")
    consume = _function_body(
        "a1_consume_oauth_attempt(", "create or replace function a1_link_oauth_identity("
    )

    assert "state_digest text not null" in attempts
    assert "code_digest text check" in attempts
    assert "oauth_attempts_ttl_check check (expires_at > created_at)" in attempts
    assert "purpose = 'login' or requested_user_id is not null" in attempts
    assert "status = 'consumed' and consumed_at is not null and code_digest is not null" in attempts
    assert "oauth_attempts_state_key unique" in attempts
    assert "oauth_attempts_consumed_code_key" in _normalized()
    assert "for update" in consume
    assert "attempt.expires_at <= p_consumed_at" in consume
    assert "attempt.state_digest <> p_state_digest" in consume
    assert "set status = 'consumed', code_digest = p_code_digest" in consume
    assert "sessions_ttl_check check (expires_at > authenticated_at)" in sessions
    assert "sessions_digest_key unique (organization_id, project_id, session_digest)" in sessions
    assert (
        "foreign key ( organization_id, project_id, external_identity_id, session_id ) "
        "references sessions( organization_id, project_id, external_identity_id, id )"
    ) in refs


def test_schema_has_no_raw_token_code_or_verifier_columns() -> None:
    forbidden_column_names = {
        "access_token",
        "refresh_token",
        "id_token",
        "authorization_code",
        "code_verifier",
        "raw_token",
        "raw_code",
        "raw_verifier",
        "state",
        "nonce",
        "client_secret",
    }

    for table in TABLES:
        body = _table_body(table)
        column_names = {
            match.group(1)
            for match in re.finditer(r"(?:^|,)\s*([a-z][a-z0-9_]*)\s+[a-z]", body)
        }
        assert forbidden_column_names.isdisjoint(column_names), (table, column_names)

    refs = _table_body("token_secret_refs")
    assert "secret_ref text not null check (a1_oauth_reference_only(secret_ref))" in refs
    assert "secret_kind in ('access', 'refresh', 'id_assertion')" in refs
    assert "secret_fingerprint text" in refs
    assert "unique nulls not distinct" in refs
    assert "a1_oauth_public_metadata" in _normalized()
    for sensitive_alias in (
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "authorizationcode",
        "rawcode",
        "codeverifier",
        "clientsecret",
    ):
        assert f"'{sensitive_alias}'" in _normalized()


def test_link_function_is_atomic_and_emits_audit_and_outbox() -> None:
    link = _function_body(
        "a1_link_oauth_identity(", "create or replace function a1_revoke_oauth_identity("
    )

    for operation in (
        "attempt := a1_consume_oauth_attempt(",
        "insert into users",
        "insert into external_identities",
        "insert into sessions",
        "insert into token_secret_refs",
        "insert into oauth_audit_events",
        "insert into oauth_outbox",
    ):
        assert operation in link
    assert "'oauth.identity.linked'" in link
    assert "jsonb_build_object(" in link
    assert "return query select linked_user.id, identity.id, issued_session.id" in link


def test_revoke_function_cascades_lifecycle_and_is_audited() -> None:
    revoke = _function_body("a1_revoke_oauth_identity(", "alter table users enable")

    assert "from external_identities" in revoke
    assert "for update" in revoke
    assert "update external_identities set status = 'revoked'" in revoke
    assert "update sessions set status = 'revoked'" in revoke
    assert "update token_secret_refs set status = 'revoked'" in revoke
    assert "insert into oauth_revocations" in revoke
    assert "insert into oauth_audit_events" in revoke
    assert "insert into oauth_outbox" in revoke
    assert "'oauth.identity.revoked'" in revoke
    assert "oauth_revocations_append_only" in _normalized()
    assert "oauth_audit_events_append_only" in _normalized()
    for table in ("users", "external_identities", "sessions", "token_secret_refs"):
        assert f"{table}_reject_hard_delete" in _normalized()
