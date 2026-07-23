from __future__ import annotations

import hashlib
import os
import re
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "api" / "migrations"
MIGRATION = MIGRATIONS / "013_a1_identity_session_lifecycle.sql"
BROWSER_REFRESH_MIGRATION = (
    MIGRATIONS / "015_a1_identity_browser_session_refresh.sql"
)
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "ashr-oauth-pg-test")
RUNTIME_ROLE = "a1_runtime"


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql()).lower()


def _browser_refresh_sql() -> str:
    return re.sub(
        r"\s+",
        " ",
        BROWSER_REFRESH_MIGRATION.read_text(encoding="utf-8"),
    ).lower()


def _function_body(function: str, next_marker: str) -> str:
    sql = _normalized()
    start = sql.index(f"create or replace function {function}(")
    return sql[start : sql.index(next_marker, start)]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _docker(*args: str, input_text: str | None = None, check: bool = True):
    return subprocess.run(
        ["docker", *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def _psql(
    database: str,
    sql: str,
    *,
    user: str = "postgres",
    tuples: bool = True,
    check: bool = True,
):
    command = [
        "exec",
        "-i",
        CONTAINER,
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        user,
        "-d",
        database,
    ]
    if tuples:
        command.extend(["-A", "-t", "-F", "|"])
    return _docker(*command, input_text=sql, check=check)


def _rows(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
        and not re.match(
            r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|DELETE|GRANT|CREATE)\b",
            line,
        )
    ]


@pytest.fixture
def session_lifecycle_database() -> str:
    available = _docker(
        "inspect", "-f", "{{.State.Running}}", CONTAINER, check=False
    )
    if available.returncode != 0 or available.stdout.strip() != "true":
        pytest.skip(f"PostgreSQL container {CONTAINER!r} is not running")

    role = _psql(
        "postgres",
        (
            "SELECT rolname || '|' || rolsuper || '|' || rolbypassrls "
            f"FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}';"
        ),
    )
    if _rows(role) != [f"{RUNTIME_ROLE}|false|false"]:
        pytest.skip(f"{RUNTIME_ROLE} must be NOSUPERUSER NOBYPASSRLS")

    database = f"a1_session_lifecycle_it_{uuid.uuid4().hex[:10]}"
    _psql("postgres", f'CREATE DATABASE "{database}";', tuples=False)
    try:
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            _psql(
                database,
                migration.read_text(encoding="utf-8"),
                tuples=False,
            )
        yield database
    finally:
        _psql(
            "postgres",
            f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE);',
            tuples=False,
            check=False,
        )


def test_schema_adds_digest_only_refresh_lineage_and_generation_fences() -> None:
    sql = _normalized()
    assert sql.startswith("-- digest-only identity session refresh")
    assert sql.strip().endswith("commit;")
    required = [
        "add column if not exists refresh_digest text",
        "add column if not exists refresh_expires_at timestamptz",
        "add column if not exists rotation_generation bigint not null default 0",
        "add column if not exists rotated_from_session_id uuid",
        "add column if not exists rotated_to_session_id uuid",
        "a1_identity_digest_valid(refresh_digest)",
        "refresh_expires_at > expires_at",
        "identity_sessions_refresh_digest_key",
        "identity_sessions_family_generation_key",
        "identity_sessions_family_active_key",
        "deferrable initially deferred",
        "rotation_generation = 0 or rotated_from_session_id is not null",
    ]
    for fragment in required:
        assert fragment in sql

    forbidden = [
        "access_token text",
        "refresh_token text",
        "session_token text",
        "bearer_token text",
        "password text",
        "authorization_code text",
    ]
    for fragment in forbidden:
        assert fragment not in sql


def test_idempotency_ledger_is_scoped_immutable_and_conflicts_explicitly() -> None:
    sql = _normalized()
    table_start = sql.index(
        "create table if not exists identity_session_lifecycle_operations ("
    )
    table = sql[table_start : sql.index(");", table_start)]
    required = [
        "organization_id uuid not null",
        "project_id uuid not null",
        "principal_id uuid not null",
        "idempotency_digest text not null",
        "request_digest text not null",
        "unique ( organization_id, project_id, principal_id, operation_kind, idempotency_digest )",
        "foreign key (organization_id, project_id)",
        "foreign key (principal_id)",
    ]
    for fragment in required:
        assert fragment in table

    assert "identity_session_lifecycle_operations_append_only" in sql
    assert "before update or delete on identity_session_lifecycle_operations" in sql
    assert sql.count("raise exception 'idempotency_conflict'") >= 5
    assert sql.count("using errcode = '23505'") >= 5
    assert "using errcode = '40001'" in sql


def test_refresh_rotation_is_generation_fenced_and_retry_idempotent() -> None:
    rotate = _function_body(
        "a1_rotate_identity_session_refresh",
        "create or replace function a1_revoke_identity_session(",
    )
    required = [
        "p_refresh_digest text",
        "p_expected_generation bigint",
        "p_new_refresh_digest text",
        "p_access_expires_at timestamptz",
        "p_refresh_expires_at timestamptz",
        "for update",
        "current_session.rotation_generation <> p_expected_generation",
        "raise exception 'refresh_generation_conflict'",
        "session_row.rotation_generation = p_expected_generation",
        "current_session.rotation_generation + 1",
        "rotation_idempotency_digest = p_idempotency_digest",
        "rotation_request_digest = p_request_digest",
        "existing_operation.request_digest = p_request_digest",
        "existing_operation.target_session_id = current_session.id",
        "current_session.authenticated_at",
        "current_session.refresh_expires_at <= v_now",
        "p_refresh_expires_at > current_session.refresh_expires_at",
    ]
    for fragment in required:
        assert fragment in rotate

    principal_lock = rotate.index("from identity_principals as principal")
    session_lock = rotate.index("from identity_sessions as session_row")
    assert principal_lock < session_lock
    consumed_state = rotate.index("if current_session.status = 'rotated'")
    generation_fence = rotate.index(
        "if current_session.rotation_generation <> p_expected_generation"
    )
    assert consumed_state < generation_fence
    assert "security definer" in rotate
    assert "set search_path = pg_catalog, public" in rotate


def test_old_refresh_reuse_commits_family_revocation_as_an_outcome() -> None:
    rotate = _function_body(
        "a1_rotate_identity_session_refresh",
        "create or replace function a1_revoke_identity_session(",
    )
    reuse = rotate[
        rotate.index("if current_session.status = 'rotated'") :
        rotate.index("if current_session.status = 'revoked'")
    ]
    required = [
        "update identity_sessions as family_member",
        "family_member.principal_id = p_principal_id",
        "family_member.organization_id = p_organization_id",
        "family_member.project_id = p_project_id",
        "family_member.rotation_family_digest = current_session.rotation_family_digest",
        "family_member.status <> 'revoked'",
        "revoke_reason_code = coalesce(",
        "'refresh_reuse_detected'",
        "'identity.session.refresh_reuse_detected'",
        "return query",
    ]
    for fragment in required:
        assert fragment in reuse
    assert "raise exception 'refresh_reuse_detected'" not in reuse


def test_revoke_one_and_revoke_all_are_recent_auth_and_scope_bound() -> None:
    revoke_one = _function_body(
        "a1_revoke_identity_session",
        "create or replace function a1_revoke_all_identity_sessions(",
    )
    revoke_all = _function_body(
        "a1_revoke_all_identity_sessions",
        "create or replace function a1_login_with_verified_identity_with_refresh(",
    )
    for body in (revoke_one, revoke_all):
        assert "a1_identity_session_assert_scope(" in body
        assert "from identity_principals as principal" in body
        assert "for update" in body
        assert "a1_assert_recent_identity_authentication(" in body
        assert "organization_id = p_organization_id" in body
        assert "project_id = p_project_id" in body
        assert "principal_id = p_principal_id" in body
        assert "identity.session.revoked_" in body

    assert "session_row.id = p_target_session_id" in revoke_one
    assert "target_session.rotation_generation <> p_expected_generation" in revoke_one
    assert "raise exception 'session_generation_conflict'" in revoke_one
    assert "family_member.rotation_family_digest = target_session.rotation_family_digest" in revoke_one
    assert "not p_keep_actor_session or session_row.id <> actor_session_id" in revoke_all


def test_recent_auth_uses_authentication_time_not_activity_time() -> None:
    recent = _function_body(
        "a1_assert_recent_identity_authentication",
        "create or replace function a1_issue_identity_session_with_refresh(",
    )
    required = [
        "session_row.session_digest = p_session_digest",
        "session_row.status = 'active'",
        "session_row.expires_at > v_now",
        "session_row.authenticated_at >= v_now - make_interval(secs => p_max_age_seconds)",
        "credential.status = 'active'",
        "credential.login_enabled",
        "raise exception 'recent_authentication_required'",
        "using errcode = '42501'",
    ]
    for fragment in required:
        assert fragment in recent
    assert "last_seen_at >=" not in recent
    assert "p_now" not in recent
    assert "v_now timestamptz := clock_timestamp()" in recent


def test_scope_guard_fails_closed_across_tenant_project_and_account() -> None:
    scope = _function_body(
        "a1_identity_session_assert_scope",
        "create or replace function a1_assert_recent_identity_authentication(",
    )
    required = [
        "a1_assert_role_nobypassrls(session_user)",
        "p_organization_id is distinct from a1_current_organization_id()",
        "p_project_id is distinct from a1_current_project_id()",
        "p_principal_id is distinct from a1_current_principal_id()",
        "organization_membership.organization_id = p_organization_id",
        "project_membership.project_id = p_project_id",
        "project_membership.principal_id = principal.id",
        "project_membership.organization_membership_id = organization_membership.id",
        "organization_membership.status = 'active'",
        "project_membership.status = 'active'",
        "principal.status = 'active'",
    ]
    for fragment in required:
        assert fragment in scope


def test_recovery_trigger_invalidates_the_account_except_new_aal2_session() -> None:
    recovery = _function_body(
        "a1_invalidate_identity_sessions_for_recovery",
        "create or replace function a1_identity_recovery_invalidate_sessions_trigger(",
    )
    trigger = _function_body(
        "a1_identity_recovery_invalidate_sessions_trigger",
        "drop trigger if exists identity_recovery_invalidate_sessions",
    )
    required = [
        "receipt_row.receipt_digest = p_receipt_digest",
        "receipt_row.status = 'consumed'",
        "receipt_row.purpose = 'account_recovery'",
        "receipt_row.mutation_kind = 'recovery'",
        "receipt_row.mutation_result_id = p_recovery_session_id",
        "recovery_session.assurance_level in ('aal2', 'aal3')",
        "session_row.principal_id = p_principal_id",
        "session_row.id <> p_recovery_session_id",
        "revoke_reason_code = 'account_recovery'",
        "'identity.session.recovery_invalidated'",
    ]
    for fragment in required:
        assert fragment in recovery
    assert "session_row.organization_id = p_organization_id" in recovery[
        recovery.index("update identity_sessions as session_row") :
    ]
    assert "session_row.project_id = p_project_id" in recovery[
        recovery.index("update identity_sessions as session_row") :
    ]
    assert "get diagnostics invalidated_count = row_count" in recovery
    assert "select count(*)::integer into invalidated_count" not in recovery
    assert "old.status = 'verified'" in trigger
    assert "new.status = 'consumed'" in trigger
    assert "new.mutation_result_id" in trigger
    assert "after update of status on identity_verification_receipts" in _normalized()


def test_force_rls_least_privilege_and_audit_contract() -> None:
    sql = _normalized()
    required = [
        "alter table identity_sessions force row level security",
        "alter table identity_session_lifecycle_operations force row level security",
        "create policy identity_session_lifecycle_operations_scope_access",
        "organization_id = a1_current_organization_id()",
        "project_id = a1_current_project_id()",
        "principal_id = a1_current_principal_id()",
        "revoke all on table identity_sessions from public",
        "revoke all on table identity_sessions from a1_runtime",
        "revoke all on table identity_session_lifecycle_operations from public",
        "revoke all on table identity_session_lifecycle_operations from a1_runtime",
        "if exists (select 1 from pg_roles where rolname = 'a1_runtime')",
    ]
    for fragment in required:
        assert fragment in sql

    public_functions = (
        "a1_assert_recent_identity_authentication",
        "a1_issue_identity_session_with_refresh",
        "a1_rotate_identity_session_refresh",
        "a1_revoke_identity_session",
        "a1_revoke_all_identity_sessions",
        "a1_login_with_verified_identity_with_refresh",
        "a1_recover_verified_identity_with_refresh",
    )
    for function in public_functions:
        assert f"revoke all on function {function}(" in sql
        assert f"grant execute on function {function}(" in sql
        start = sql.index(f"create or replace function {function}(")
        signature = sql[start : sql.index("returns", start)]
        assert "p_now" not in signature

    internal_functions = (
        "a1_identity_session_assert_scope",
        "a1_invalidate_identity_sessions_for_recovery",
        "a1_identity_recovery_invalidate_sessions_trigger",
    )
    for function in internal_functions:
        assert f"revoke all on function {function}(" in sql
        assert f"grant execute on function {function}(" not in sql

    assert sql.count("perform a1_identity_write_event(") >= 6


def test_legacy_access_only_runtime_entrypoints_are_explicitly_superseded() -> None:
    sql = _normalized()
    assert "these access-only functions predate refresh-family lifecycle support" in sql
    legacy_signatures = (
        "a1_issue_identity_session(",
        "a1_consume_identity_recovery(",
        "a1_login_with_verified_identity(",
        "a1_recover_verified_identity(",
    )
    for signature in legacy_signatures:
        start = sql.index(f"revoke all on function {signature}", sql.index("do $$"))
        end = sql.index(";", start)
        assert "from a1_runtime" in sql[start:end]

    for replacement in (
        "a1_issue_identity_session_with_refresh",
        "a1_login_with_verified_identity_with_refresh",
        "a1_recover_verified_identity_with_refresh",
    ):
        assert f"grant execute on function {replacement}(" in sql


def _seed_account(database: str, *, projects: int = 2) -> dict[str, object]:
    organization = str(uuid.uuid4())
    workspace = str(uuid.uuid4())
    principal = str(uuid.uuid4())
    credential = str(uuid.uuid4())
    membership = str(uuid.uuid4())
    project_ids = [str(uuid.uuid4()) for _ in range(projects)]
    subject = _digest(f"subject-{principal}")
    sql = f"""
      INSERT INTO organizations (id, slug, display_name)
      VALUES (
        '{organization}', 'session-org-{organization[:8]}', 'Session Org'
      );
      INSERT INTO workspaces (id, organization_id, slug, display_name)
      VALUES (
        '{workspace}', '{organization}', 'session-ws-{workspace[:8]}',
        'Session Workspace'
      );
      INSERT INTO identity_principals (id, status)
      VALUES ('{principal}', 'active');
      INSERT INTO identity_credentials (
        id, principal_id, provider, provider_environment, credential_kind,
        subject_digest, status, login_enabled, verified_at
      ) VALUES (
        '{credential}', '{principal}', 'email', 'production', 'email_otp',
        '{subject}', 'active', TRUE, clock_timestamp()
      );
      INSERT INTO identity_organization_memberships (
        id, organization_id, principal_id, status, activated_at
      ) VALUES (
        '{membership}', '{organization}', '{principal}',
        'active', clock_timestamp()
      );
    """
    for index, project in enumerate(project_ids):
        sql += f"""
          INSERT INTO projects (
            id, organization_id, workspace_id, slug, display_name
          ) VALUES (
            '{project}', '{organization}', '{workspace}',
            'session-project-{index}-{project[:8]}', 'Session Project {index}'
          );
          INSERT INTO identity_project_memberships (
            organization_id, project_id, principal_id,
            organization_membership_id, status, activated_at
          ) VALUES (
            '{organization}', '{project}', '{principal}', '{membership}',
            'active', clock_timestamp()
          );
        """
    _psql(database, sql, tuples=False)
    return {
        "organization": organization,
        "workspace": workspace,
        "principal": principal,
        "credential": credential,
        "projects": project_ids,
        "subject": subject,
    }


def _runtime_scope(account: dict[str, object], project: str) -> str:
    return (
        f"SET app.a1_organization_id = '{account['organization']}';"
        f"SET app.a1_project_id = '{project}';"
        f"SET app.a1_principal_id = '{account['principal']}';"
    )


def _issue_session(
    database: str,
    account: dict[str, object],
    project: str,
    label: str,
) -> tuple[str, dict[str, str]]:
    digests = {
        name: _digest(f"{label}-{name}")
        for name in (
            "session",
            "refresh",
            "family",
            "idempotency",
            "request",
        )
    }
    result = _rows(
        _psql(
            database,
            _runtime_scope(account, project)
            + f"""
              SELECT session_id, rotation_generation, outcome_code, affected_count
                FROM a1_issue_identity_session_with_refresh(
                  '{account['organization']}', '{project}',
                  '{account['principal']}', '{account['credential']}',
                  '{digests['session']}', '{digests['refresh']}',
                  '{digests['family']}',
                  clock_timestamp() + interval '15 minutes',
                  clock_timestamp() + interval '2 hours', 'aal2',
                  '{digests['idempotency']}', '{digests['request']}',
                  '{{}}'::jsonb
                );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert len(result) == 1
    session_id, generation, outcome, affected = result[0].split("|")
    assert (generation, outcome, affected) == ("0", "issued", "1")
    return session_id, digests


def _rotate(
    database: str,
    account: dict[str, object],
    project: str,
    old_refresh: str,
    expected_generation: int,
    label: str,
    idempotency: str,
    request: str,
) -> list[str]:
    new_session = _digest(f"{label}-session")
    new_refresh = _digest(f"{label}-refresh")
    return _rows(
        _psql(
            database,
            _runtime_scope(account, project)
            + f"""
              SELECT pg_backend_pid(), rotated.session_id,
                     rotated.rotation_generation, rotated.outcome_code,
                     rotated.affected_count
                FROM a1_rotate_identity_session_refresh(
                  '{account['organization']}', '{project}',
                  '{account['principal']}', '{old_refresh}',
                  {expected_generation}, '{new_session}', '{new_refresh}',
                  clock_timestamp() + interval '15 minutes',
                  clock_timestamp() + interval '90 minutes',
                  '{idempotency}', '{request}', '{{}}'::jsonb
                ) AS rotated;
            """,
            user=RUNTIME_ROLE,
        )
    )


def test_live_independent_connections_serialize_rotation_and_replay_retry(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=1)
    project = account["projects"][0]
    _, issued = _issue_session(
        session_lifecycle_database, account, project, "same-request-family"
    )
    _psql(
        session_lifecycle_database,
        f"""
          UPDATE identity_sessions
             SET authenticated_at = clock_timestamp() - interval '10 minutes',
                 expires_at = clock_timestamp() - interval '5 minutes'
           WHERE rotation_family_digest = '{issued['family']}';
        """,
        tuples=False,
    )
    idempotency = _digest("same-rotation-idempotency")
    request = _digest("same-rotation-request")

    def contender() -> list[str]:
        return _rotate(
            session_lifecycle_database,
            account,
            project,
            issued["refresh"],
            0,
            "same-rotation-result",
            idempotency,
            request,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = list(pool.map(lambda _: contender(), range(2)))

    assert all(len(rows) == 1 for rows in concurrent)
    parsed = [rows[0].split("|") for rows in concurrent]
    assert parsed[0][0] != parsed[1][0], "calls must use independent backends"
    assert parsed[0][1:] == parsed[1][1:]
    assert parsed[0][2:] == ["1", "rotated", "1"]

    retry = contender()
    assert len(retry) == 1
    assert retry[0].split("|")[1:] == parsed[0][1:]

    state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT
                count(*) || '|' ||
                count(*) FILTER (WHERE status = 'active') || '|' ||
                max(rotation_generation) || '|' ||
                (SELECT count(*) FROM identity_session_lifecycle_operations
                  WHERE operation_kind = 'rotate'
                    AND idempotency_digest = '{idempotency}') || '|' ||
                (SELECT count(*) FROM identity_audit_events
                  WHERE action = 'identity.session.refresh_rotated')
                FROM identity_sessions
               WHERE rotation_family_digest = '{issued['family']}';
            """,
        )
    )
    assert state == ["2|1|1|1|1"]

    conflicting_reuse = _rows(
        _psql(
            session_lifecycle_database,
            _runtime_scope(account, project)
            + f"""
              SELECT * FROM a1_rotate_identity_session_refresh(
                '{account['organization']}', '{project}',
                '{account['principal']}', '{issued['refresh']}', 0,
                '{_digest('same-rotation-result-session')}',
                '{_digest('same-rotation-result-refresh')}',
                clock_timestamp() + interval '15 minutes',
                clock_timestamp() + interval '90 minutes',
                '{idempotency}', '{_digest('conflicting-request')}',
                '{{}}'::jsonb
              );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert conflicting_reuse[0].split("|")[2] == "refresh_reuse_detected"
    revoked = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT count(*) FILTER (WHERE status = 'revoked')
                FROM identity_sessions
               WHERE rotation_family_digest = '{issued['family']}';
            """,
        )
    )
    assert revoked == ["2"]


def test_live_revoke_one_revokes_one_family_without_touching_siblings(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=1)
    project = account["projects"][0]
    _, family = _issue_session(
        session_lifecycle_database, account, project, "revoke-one-family"
    )
    sibling_id, _ = _issue_session(
        session_lifecycle_database, account, project, "revoke-one-sibling"
    )
    rotated = _rotate(
        session_lifecycle_database,
        account,
        project,
        family["refresh"],
        0,
        "revoke-one-current",
        _digest("revoke-one-rotation-idempotency"),
        _digest("revoke-one-rotation-request"),
    )[0].split("|")
    current_id = rotated[1]
    current_access = _digest("revoke-one-current-session")

    revoked = _rows(
        _psql(
            session_lifecycle_database,
            _runtime_scope(account, project)
            + f"""
              SELECT session_id, rotation_generation, outcome_code, affected_count
                FROM a1_revoke_identity_session(
                  '{account['organization']}', '{project}',
                  '{account['principal']}', '{current_access}',
                  '{current_id}', 1, 900, 'user_revoked',
                  '{_digest('revoke-one-idempotency')}',
                  '{_digest('revoke-one-request')}'
                );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert revoked == [f"{current_id}|1|revoked|2"]
    state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT
                count(*) FILTER (WHERE status = 'revoked') || '|' ||
                count(*) FILTER (WHERE revoke_reason_code = 'user_revoked') || '|' ||
                (SELECT status FROM identity_sessions WHERE id = '{sibling_id}')
                FROM identity_sessions
               WHERE rotation_family_digest = '{family['family']}';
            """,
        )
    )
    assert state == ["2|2|active"]


def test_live_competing_refresh_requests_revoke_the_whole_family(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=1)
    project = account["projects"][0]
    _, issued = _issue_session(
        session_lifecycle_database, account, project, "reuse-family"
    )

    requests = [
        (
            "reuse-contender-a",
            _digest("reuse-idempotency-a"),
            _digest("reuse-request-a"),
        ),
        (
            "reuse-contender-b",
            _digest("reuse-idempotency-b"),
            _digest("reuse-request-b"),
        ),
    ]

    def contender(arguments: tuple[str, str, str]) -> list[str]:
        label, idempotency, request = arguments
        return _rotate(
            session_lifecycle_database,
            account,
            project,
            issued["refresh"],
            0,
            label,
            idempotency,
            request,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = list(pool.map(contender, requests))

    parsed = [rows[0].split("|") for rows in concurrent]
    assert parsed[0][0] != parsed[1][0], "calls must use independent backends"
    assert sorted(row[3] for row in parsed) == [
        "refresh_reuse_detected",
        "rotated",
    ]
    state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT
                count(*) || '|' ||
                count(*) FILTER (WHERE status = 'revoked') || '|' ||
                count(*) FILTER (
                  WHERE revoke_reason_code = 'refresh_reuse_detected'
                ) || '|' ||
                (SELECT count(*) FROM identity_session_lifecycle_operations
                  WHERE operation_kind = 'rotate') || '|' ||
                (SELECT count(*) FROM identity_audit_events
                  WHERE action = 'identity.session.refresh_reuse_detected')
                FROM identity_sessions
               WHERE rotation_family_digest = '{issued['family']}';
            """,
        )
    )
    assert state == ["2|2|2|2|1"]


def test_live_wrong_generation_cannot_bypass_consumed_refresh_reuse(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=1)
    project = account["projects"][0]
    _, issued = _issue_session(
        session_lifecycle_database, account, project, "wrong-generation-reuse"
    )
    first_idempotency = _digest("wrong-generation-first-idempotency")
    first_request = _digest("wrong-generation-first-request")
    first = _rotate(
        session_lifecycle_database,
        account,
        project,
        issued["refresh"],
        0,
        "wrong-generation-current",
        first_idempotency,
        first_request,
    )
    assert first[0].split("|")[3] == "rotated"

    reused = _rotate(
        session_lifecycle_database,
        account,
        project,
        issued["refresh"],
        999,
        "wrong-generation-attacker",
        first_idempotency,
        first_request,
    )
    assert reused[0].split("|")[3] == "refresh_reuse_detected"
    state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT
                count(*) || '|' ||
                count(*) FILTER (WHERE status = 'revoked') || '|' ||
                count(*) FILTER (
                  WHERE revoke_reason_code = 'refresh_reuse_detected'
                )
                FROM identity_sessions
               WHERE rotation_family_digest = '{issued['family']}';
            """,
        )
    )
    assert state == ["2|2|2"]


def test_live_revoke_all_is_project_scoped_and_requires_recent_authentication(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=2)
    first_project, second_project = account["projects"]
    first_id, first = _issue_session(
        session_lifecycle_database, account, first_project, "revoke-first"
    )
    second_id, _ = _issue_session(
        session_lifecycle_database, account, second_project, "revoke-second"
    )

    _psql(
        session_lifecycle_database,
        f"""
          UPDATE identity_sessions
             SET authenticated_at = clock_timestamp() - interval '10 minutes'
           WHERE id = '{first_id}';
        """,
        tuples=False,
    )
    stale = _psql(
        session_lifecycle_database,
        _runtime_scope(account, first_project)
        + f"""
          SELECT * FROM a1_revoke_all_identity_sessions(
            '{account['organization']}', '{first_project}',
            '{account['principal']}', '{first['session']}', FALSE, 1,
            'user_logout', '{_digest('stale-revoke-idempotency')}',
            '{_digest('stale-revoke-request')}'
          );
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert stale.returncode != 0
    assert "recent_authentication_required" in stale.stderr

    revoked = _rows(
        _psql(
            session_lifecycle_database,
            _runtime_scope(account, first_project)
            + f"""
              SELECT session_id, outcome_code, affected_count
                FROM a1_revoke_all_identity_sessions(
                  '{account['organization']}', '{first_project}',
                  '{account['principal']}', '{first['session']}', FALSE, 900,
                  'user_logout', '{_digest('revoke-all-idempotency')}',
                  '{_digest('revoke-all-request')}'
                );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert revoked == [f"{first_id}|revoked_all|1"]
    state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT
                (SELECT status FROM identity_sessions WHERE id = '{first_id}')
                || '|' ||
                (SELECT status FROM identity_sessions WHERE id = '{second_id}');
            """,
        )
    )
    assert state == ["revoked|active"]


def test_live_verified_login_separates_access_and_refresh_credentials(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=1)
    project = account["projects"][0]
    digests = {
        name: _digest(f"login-{name}")
        for name in (
            "challenge",
            "code",
            "context",
            "issue_event",
            "receipt",
            "verify_event",
            "session",
            "refresh",
            "family",
            "idempotency",
            "request",
            "login_event",
        )
    }
    scope = _runtime_scope(account, project)
    _psql(
        session_lifecycle_database,
        scope
        + f"""
          SELECT challenge_id
            FROM a1_issue_identity_verification_challenge_with_delivery(
              '{account['organization']}', '{project}',
              '{account['principal']}', 'email', 'login',
              '{account['subject']}', '{digests['challenge']}',
              '{digests['code']}', '{digests['context']}',
              clock_timestamp() + interval '5 minutes', 5, 30,
              '{digests['issue_event']}',
              'opaque-ref:identity-delivery/{digests['challenge']}',
              '{{}}'::jsonb
            );
          SELECT outcome_code
            FROM a1_verify_identity_verification_attempt(
              '{account['organization']}', '{project}',
              '{digests['challenge']}', '{digests['code']}',
              '{digests['context']}', '{digests['receipt']}',
              '{digests['verify_event']}', '{{}}'::jsonb
            );
        """,
        user=RUNTIME_ROLE,
    )

    invalid_expiry = _psql(
        session_lifecycle_database,
        scope
        + f"""
          SELECT session_id
            FROM a1_login_with_verified_identity_with_refresh_result(
              '{account['organization']}', '{project}',
              '{digests['receipt']}', '{digests['session']}',
              '{digests['refresh']}', '{digests['family']}',
              clock_timestamp() + interval '2 hours',
              clock_timestamp() + interval '15 minutes',
              '{digests['idempotency']}', '{digests['request']}',
              '{digests['login_event']}', '{{}}'::jsonb
            );
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert invalid_expiry.returncode != 0
    assert "identity verified login refresh is invalid" in invalid_expiry.stderr

    login_session_id = _rows(
        _psql(
            session_lifecycle_database,
            scope
            + f"""
              SELECT session_id
                FROM a1_login_with_verified_identity_with_refresh_result(
                  '{account['organization']}', '{project}',
                  '{digests['receipt']}', '{digests['session']}',
                  '{digests['refresh']}', '{digests['family']}',
                  clock_timestamp() + interval '15 minutes',
                  clock_timestamp() + interval '2 hours',
                  '{digests['idempotency']}', '{digests['request']}',
                  '{digests['login_event']}', '{{}}'::jsonb
                );
            """,
            user=RUNTIME_ROLE,
        )
    )[0]

    state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT
                (session_digest = '{digests['session']}')::TEXT || '|' ||
                (refresh_digest = '{digests['refresh']}')::TEXT || '|' ||
                (session_digest <> refresh_digest)::TEXT || '|' ||
                (session_digest ~ '^[a-f0-9]{{64}}$')::TEXT || '|' ||
                (refresh_digest ~ '^[a-f0-9]{{64}}$')::TEXT || '|' ||
                (expires_at > authenticated_at)::TEXT || '|' ||
                (expires_at < authenticated_at + interval '16 minutes')::TEXT
                || '|' ||
                (refresh_expires_at > expires_at)::TEXT || '|' ||
                (refresh_expires_at <
                   authenticated_at + interval '121 minutes')::TEXT || '|' ||
                assurance_level
                FROM identity_sessions
               WHERE id = '{login_session_id}';
            """,
        )
    )
    assert state == [
        "true|true|true|true|true|true|true|true|true|aal1"
    ]

    access_authentication = _rows(
        _psql(
            session_lifecycle_database,
            scope
            + f"""
              SELECT a1_assert_recent_identity_authentication(
                '{account['organization']}', '{project}',
                '{account['principal']}', '{digests['session']}', 900, 'aal1'
              );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert access_authentication == [login_session_id]

    refresh_authentication = _psql(
        session_lifecycle_database,
        scope
        + f"""
          SELECT a1_assert_recent_identity_authentication(
            '{account['organization']}', '{project}',
            '{account['principal']}', '{digests['refresh']}', 900, 'aal1'
          );
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert refresh_authentication.returncode != 0
    assert "recent_authentication_required" in refresh_authentication.stderr


def test_live_verified_recovery_invalidates_only_the_exact_project_account(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=2)
    first_project, second_project = account["projects"]
    first_id, _ = _issue_session(
        session_lifecycle_database, account, first_project, "recovery-first"
    )
    second_id, _ = _issue_session(
        session_lifecycle_database, account, second_project, "recovery-second"
    )
    historical_id, _ = _issue_session(
        session_lifecycle_database, account, first_project, "recovery-historical"
    )
    expired_id, _ = _issue_session(
        session_lifecycle_database, account, first_project, "recovery-expired"
    )
    _psql(
        session_lifecycle_database,
        f"""
          UPDATE identity_sessions
             SET status = 'revoked',
                 revoked_at = clock_timestamp(),
                 revoke_reason_code = 'user_revoked'
           WHERE id = '{historical_id}';
          UPDATE identity_sessions
             SET status = 'expired'
           WHERE id = '{expired_id}';
        """,
        tuples=False,
    )
    digests = {
        name: _digest(f"recovery-{name}")
        for name in (
            "challenge",
            "code",
            "context",
            "issue_event",
            "receipt",
            "verify_event",
            "new_session",
            "new_refresh",
            "new_family",
            "idempotency",
            "request",
            "recovery_event",
        )
    }
    scope = _runtime_scope(account, first_project)
    _psql(
        session_lifecycle_database,
        scope
        + f"""
          SELECT challenge_id
            FROM a1_issue_identity_verification_challenge_with_delivery(
              '{account['organization']}', '{first_project}',
              '{account['principal']}', 'email', 'account_recovery',
              '{account['subject']}', '{digests['challenge']}',
              '{digests['code']}', '{digests['context']}',
              clock_timestamp() + interval '5 minutes', 5, 30,
              '{digests['issue_event']}',
              'opaque-ref:identity-delivery/{digests['challenge']}',
              '{{}}'::jsonb
            );
          SELECT outcome_code
            FROM a1_verify_identity_verification_attempt(
              '{account['organization']}', '{first_project}',
              '{digests['challenge']}', '{digests['code']}',
              '{digests['context']}', '{digests['receipt']}',
              '{digests['verify_event']}', '{{}}'::jsonb
            );
        """,
        user=RUNTIME_ROLE,
    )
    invalid_expiry = _psql(
        session_lifecycle_database,
        scope
        + f"""
          SELECT session_id
            FROM a1_recover_verified_identity_with_refresh_result(
              '{account['organization']}', '{first_project}',
              '{digests['receipt']}', '{digests['new_session']}',
              '{digests['new_refresh']}', '{digests['new_family']}',
              clock_timestamp() + interval '2 hours',
              clock_timestamp() + interval '15 minutes',
              '{digests['idempotency']}', '{digests['request']}',
              '{digests['recovery_event']}', '{{}}'::jsonb
            );
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert invalid_expiry.returncode != 0
    assert "identity verified recovery refresh is invalid" in invalid_expiry.stderr

    recovered = _rows(
        _psql(
            session_lifecycle_database,
            scope
            + f"""
              SELECT session_id
                FROM a1_recover_verified_identity_with_refresh_result(
                  '{account['organization']}', '{first_project}',
                  '{digests['receipt']}', '{digests['new_session']}',
                  '{digests['new_refresh']}', '{digests['new_family']}',
                  clock_timestamp() + interval '15 minutes',
                  clock_timestamp() + interval '2 hours',
                  '{digests['idempotency']}', '{digests['request']}',
                  '{digests['recovery_event']}', '{{}}'::jsonb
                );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert len(recovered) == 1
    recovery_session_id = recovered[0]
    state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT
                (SELECT status || ':' || revoke_reason_code
                   FROM identity_sessions WHERE id = '{first_id}') || '|' ||
                (SELECT status || ':' || COALESCE(revoke_reason_code, '')
                   FROM identity_sessions WHERE id = '{second_id}') || '|' ||
                (SELECT status || ':' || revoke_reason_code
                   FROM identity_sessions WHERE id = '{historical_id}') || '|' ||
                (SELECT status || ':' || revoke_reason_code
                   FROM identity_sessions WHERE id = '{expired_id}') || '|' ||
                (SELECT status || ':' || assurance_level || ':' ||
                        (session_digest = '{digests['new_session']}')::TEXT ||
                        ':' ||
                        (refresh_digest = '{digests['new_refresh']}')::TEXT ||
                        ':' ||
                        (session_digest <> refresh_digest)::TEXT || ':' ||
                        (expires_at > authenticated_at)::TEXT || ':' ||
                        (expires_at < authenticated_at +
                          interval '16 minutes')::TEXT || ':' ||
                        (refresh_expires_at > expires_at)::TEXT || ':' ||
                        (refresh_expires_at < authenticated_at +
                          interval '121 minutes')::TEXT
                   FROM identity_sessions WHERE id = '{recovery_session_id}')
                || '|' ||
                (SELECT affected_count
                   FROM identity_session_lifecycle_operations
                  WHERE operation_kind = 'recovery_invalidate') || '|' ||
                (SELECT metadata->>'invalidated_count'
                   FROM identity_audit_events
                  WHERE action = 'identity.session.recovery_invalidated');
            """,
        )
    )
    assert state == [
        "revoked:account_recovery|active:|revoked:user_revoked|"
        "revoked:account_recovery|"
        "active:aal2:true:true:true:true:true:true:true|1|1"
    ]


def test_live_runtime_privileges_exclude_replaced_session_issuers(
    session_lifecycle_database: str,
) -> None:
    privileges = _rows(
        _psql(
            session_lifecycle_database,
            """
              SELECT
                has_function_privilege(
                  'a1_runtime',
                  'a1_issue_identity_session(uuid,uuid,text,text,timestamptz,uuid,uuid,text,text,jsonb)',
                  'EXECUTE'
                ) || '|' ||
                has_function_privilege(
                  'a1_runtime',
                  'a1_consume_identity_recovery(text,text,text,text,timestamptz,text,jsonb)',
                  'EXECUTE'
                ) || '|' ||
                has_function_privilege(
                  'a1_runtime',
                  'a1_login_with_verified_identity(uuid,uuid,text,text,text,timestamptz,text,text,text,jsonb)',
                  'EXECUTE'
                ) || '|' ||
                has_function_privilege(
                  'a1_runtime',
                  'a1_recover_verified_identity(uuid,uuid,text,text,text,timestamptz,text,text,text,jsonb)',
                  'EXECUTE'
                ) || '|' ||
                has_function_privilege(
                  'a1_runtime',
                  'a1_login_with_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamptz,timestamptz,text,text,text,jsonb)',
                  'EXECUTE'
                ) || '|' ||
                has_function_privilege(
                  'a1_runtime',
                  'a1_recover_verified_identity_with_refresh(uuid,uuid,text,text,text,text,timestamptz,timestamptz,text,text,text,jsonb)',
                  'EXECUTE'
                ) || '|' ||
                has_function_privilege(
                  'a1_runtime',
                  'a1_login_with_verified_identity_with_refresh_result(uuid,uuid,text,text,text,text,timestamptz,timestamptz,text,text,text,jsonb)',
                  'EXECUTE'
                ) || '|' ||
                has_function_privilege(
                  'a1_runtime',
                  'a1_recover_verified_identity_with_refresh_result(uuid,uuid,text,text,text,text,timestamptz,timestamptz,text,text,text,jsonb)',
                  'EXECUTE'
                );
            """,
        )
    )
    assert privileges == [
        "false|false|false|false|false|false|true|true"
    ]


def test_browser_refresh_bootstrap_is_digest_only_scoped_and_narrowly_granted() -> None:
    sql = _browser_refresh_sql()
    assert sql.startswith("-- browser-session refresh bootstrap")
    assert sql.strip().endswith("commit;")
    for fragment in (
        "create or replace function a1_rotate_identity_session_refresh_from_digest(",
        "security definer",
        "perform a1_assert_role_nobypassrls(session_user)",
        "where session_row.refresh_digest = p_refresh_digest",
        "from identity_principals as principal",
        "where principal.id = current_session.principal_id for update",
        "current_session.project_id <> p_project_id",
        "current_session.principal_id <> p_principal_id",
        "from a1_rotate_identity_session_refresh(",
        "revoke all on function a1_rotate_identity_session_refresh_from_digest(",
        "grant execute on function a1_rotate_identity_session_refresh_from_digest(",
    ):
        assert fragment in sql
    for forbidden in (
        "p_refresh_token",
        "p_access_token",
        "p_cookie",
        "p_authorization",
    ):
        assert forbidden not in sql


def test_live_browser_refresh_bootstrap_rotates_and_reuse_revokes_family(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=2)
    project, wrong_project = account["projects"]
    old_session_id, old = _issue_session(
        session_lifecycle_database,
        account,
        project,
        "browser-refresh-old",
    )
    new = {
        name: _digest(f"browser-refresh-new-{name}")
        for name in ("session", "refresh", "idempotency", "request")
    }
    rotated = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT COALESCE(session_id::TEXT, ''),
                     organization_id, project_id, principal_id,
                     rotation_generation, outcome_code, affected_count,
                     access_expires_at < refresh_expires_at,
                     access_expires_at::TEXT, refresh_expires_at::TEXT
                FROM a1_rotate_identity_session_refresh_from_digest(
                  '{project}', '{account['principal']}',
                  '{old['refresh']}', '{new['session']}',
                  '{new['refresh']}',
                  clock_timestamp() + interval '15 minutes',
                  '{new['idempotency']}', '{new['request']}',
                  '{{}}'::jsonb
                );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert len(rotated) == 1
    (
        new_session_id,
        organization_id,
        project_id,
        principal_id,
        generation,
        outcome,
        affected,
        expiry_ordered,
        access_expires_at,
        refresh_expires_at,
    ) = rotated[0].split("|")
    assert uuid.UUID(new_session_id)
    assert (
        organization_id,
        project_id,
        principal_id,
        generation,
        outcome,
        affected,
        expiry_ordered,
    ) == (
        account["organization"],
        project,
        account["principal"],
        "1",
        "rotated",
        "1",
        "t",
    )

    access_state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT count(*) FROM a1_authenticate_identity_session_digest(
                '{old['session']}'
              );
              SELECT session_id FROM a1_authenticate_identity_session_digest(
                '{new['session']}'
              );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert access_state == ["0", new_session_id]

    replayed = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT COALESCE(session_id::TEXT, ''), outcome_code,
                     affected_count, access_expires_at::TEXT,
                     refresh_expires_at::TEXT
                FROM a1_rotate_identity_session_refresh_from_digest(
                  '{project}', '{account['principal']}',
                  '{old['refresh']}', '{new['session']}',
                  '{new['refresh']}',
                  clock_timestamp() + interval '14 minutes',
                  '{new['idempotency']}', '{new['request']}',
                  '{{}}'::jsonb
                );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert replayed == [
        "|".join(
            (
                new_session_id,
                "rotated",
                "1",
                access_expires_at,
                refresh_expires_at,
            )
        )
    ]

    replay_family_state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT count(*), bool_and(status <> 'revoked'),
                     count(*) FILTER (WHERE status = 'rotated'),
                     count(*) FILTER (WHERE status = 'active')
                FROM identity_sessions
               WHERE id IN ('{old_session_id}', '{new_session_id}');
            """,
        )
    )
    assert replay_family_state == ["2|t|1|1"]

    wrong_scope = _psql(
        session_lifecycle_database,
        f"""
          SELECT * FROM a1_rotate_identity_session_refresh_from_digest(
            '{wrong_project}', '{account['principal']}',
            '{old['refresh']}', '{_digest('wrong-scope-session')}',
            '{_digest('wrong-scope-refresh')}',
            clock_timestamp() + interval '15 minutes',
            '{_digest('wrong-scope-idempotency')}',
            '{_digest('wrong-scope-request')}', '{{}}'::jsonb
          );
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert wrong_scope.returncode != 0
    assert "identity refresh is unavailable" in wrong_scope.stderr

    reused = {
        name: _digest(f"browser-refresh-reuse-{name}")
        for name in ("session", "refresh", "idempotency", "request")
    }
    reuse_result = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT COALESCE(session_id::TEXT, ''), outcome_code,
                     affected_count
                FROM a1_rotate_identity_session_refresh_from_digest(
                  '{project}', '{account['principal']}',
                  '{old['refresh']}', '{reused['session']}',
                  '{reused['refresh']}',
                  clock_timestamp() + interval '15 minutes',
                  '{reused['idempotency']}', '{reused['request']}',
                  '{{}}'::jsonb
                );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert len(reuse_result) == 1
    empty_session, reuse_outcome, affected_count = reuse_result[0].split("|")
    assert empty_session == ""
    assert reuse_outcome == "refresh_reuse_detected"
    assert int(affected_count) >= 1

    family_state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT count(*), bool_and(status = 'revoked'),
                     bool_and(revoke_reason_code = 'refresh_reuse_detected')
                FROM identity_sessions
               WHERE id IN ('{old_session_id}', '{new_session_id}');
            """,
        )
    )
    assert family_state == ["2|t|t"]


def test_live_browser_refresh_independent_clients_replay_and_conflict(
    session_lifecycle_database: str,
) -> None:
    account = _seed_account(session_lifecycle_database, projects=1)
    project = account["projects"][0]
    old_session_id, old = _issue_session(
        session_lifecycle_database,
        account,
        project,
        "browser-refresh-concurrent-old",
    )
    replacement = {
        name: _digest(f"browser-refresh-concurrent-{name}")
        for name in ("session", "refresh", "idempotency", "request")
    }

    def rotate(request_digest: str = replacement["request"]) -> list[str]:
        return _rows(
            _psql(
                session_lifecycle_database,
                f"""
                  SELECT pg_backend_pid(), COALESCE(session_id::TEXT, ''),
                         rotation_generation, outcome_code, affected_count,
                         access_expires_at::TEXT, refresh_expires_at::TEXT
                    FROM a1_rotate_identity_session_refresh_from_digest(
                      '{project}', '{account['principal']}',
                      '{old['refresh']}', '{replacement['session']}',
                      '{replacement['refresh']}',
                      clock_timestamp() + interval '15 minutes',
                      '{replacement['idempotency']}', '{request_digest}',
                      '{{}}'::jsonb
                    );
                """,
                user=RUNTIME_ROLE,
            )
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        concurrent = list(pool.map(lambda _: rotate(), range(4)))

    assert all(len(rows) == 1 for rows in concurrent)
    parsed = [rows[0].split("|") for rows in concurrent]
    assert len({row[0] for row in parsed}) == 4
    assert all(row[1:] == parsed[0][1:] for row in parsed)
    assert parsed[0][2:5] == ["1", "rotated", "1"]

    replay = rotate()
    assert replay[0].split("|")[1:] == parsed[0][1:]

    conflict = rotate(_digest("browser-refresh-concurrent-conflict"))
    conflict_parts = conflict[0].split("|")
    assert conflict_parts[1] == ""
    assert conflict_parts[3] == "refresh_reuse_detected"
    assert int(conflict_parts[4]) >= 1

    family_state = _rows(
        _psql(
            session_lifecycle_database,
            f"""
              SELECT count(*), bool_and(status = 'revoked'),
                     count(*) FILTER (
                       WHERE revoke_reason_code = 'refresh_reuse_detected'
                     )
                FROM identity_sessions
               WHERE id = '{old_session_id}'
                  OR rotation_family_digest = '{old['family']}';
            """,
        )
    )
    count, all_revoked, reuse_revoked = family_state[0].split("|")
    assert int(count) == 2
    assert all_revoked == "t"
    assert int(reuse_revoked) == 2
