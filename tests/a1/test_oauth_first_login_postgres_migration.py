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
MIGRATION = (
    MIGRATIONS
    / "026_a1_oauth_first_login_session_handoff.sql"
)
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "ashr-oauth-pg-test")
RUNTIME_ROLE = "a1_runtime"


def _sql() -> str:
    assert MIGRATION.is_file(), f"missing migration: {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql()).lower()


def _function_body() -> str:
    sql = _normalized()
    start = sql.index(
        "create or replace function "
        "a1_complete_oauth_first_login_with_refresh("
    )
    return sql[start : sql.index("revoke all on function", start)]


def _operation_table() -> str:
    sql = _normalized()
    start = sql.index(
        "create table if not exists oauth_first_login_operations ("
    )
    return sql[start : sql.index(");", start)]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
            r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|DELETE|GRANT|CREATE|DROP)\b",
            line,
        )
    ]


@pytest.fixture(scope="module")
def oauth_first_login_database() -> str:
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

    database = f"a1_oauth_first_login_it_{uuid.uuid4().hex[:10]}"
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


def _seed_scope(database: str, label: str) -> dict[str, str]:
    organization = str(uuid.uuid4())
    workspace = str(uuid.uuid4())
    project = str(uuid.uuid4())
    slug = re.sub(r"[^a-z0-9-]", "-", label.lower())[:24]
    _psql(
        database,
        f"""
          INSERT INTO organizations (id, slug, display_name)
          VALUES (
            '{organization}', 'ofli-org-{slug}-{organization[:6]}',
            'OAuth First Login Org'
          );
          INSERT INTO workspaces (
            id, organization_id, slug, display_name
          ) VALUES (
            '{workspace}', '{organization}',
            'ofli-ws-{slug}-{workspace[:6]}', 'OAuth First Login Workspace'
          );
          INSERT INTO projects (
            id, organization_id, workspace_id, slug, display_name
          ) VALUES (
            '{project}', '{organization}', '{workspace}',
            'ofli-project-{slug}-{project[:6]}', 'OAuth First Login Project'
          );
        """,
        tuples=False,
    )
    return {
        "organization": organization,
        "workspace": workspace,
        "project": project,
    }


def _first_login_material(label: str) -> dict[str, str]:
    return {
        "subject": _digest(f"{label}:subject"),
        "email": _digest(f"{label}:email"),
        "opaque_ref": f"vault:oauth-first-login:{label}",
        "opaque_ref_digest": _digest(f"{label}:opaque-ref"),
        "binding": _digest(f"{label}:binding"),
        "session": _digest(f"{label}:session"),
        "refresh": _digest(f"{label}:refresh"),
        "family": _digest(f"{label}:family"),
        "idempotency": _digest(f"{label}:idempotency"),
        "request": _digest(f"{label}:request"),
    }


def _complete_first_login(
    database: str,
    scope: dict[str, str],
    material: dict[str, str],
    *,
    provider: str = "google",
    email_digest: str | None = None,
    runtime_scope: dict[str, str] | None = None,
    user: str = RUNTIME_ROLE,
    check: bool = True,
):
    selected_scope = runtime_scope or scope
    email = material["email"] if email_digest is None else email_digest
    email_sql = "NULL" if email == "" else f"'{email}'"
    return _psql(
        database,
        f"""
          SET app.a1_organization_id = '{selected_scope['organization']}';
          SET app.a1_project_id = '{selected_scope['project']}';
          SELECT
            session_id::TEXT,
            principal_id::TEXT,
            credential_id::TEXT,
            connection_id::TEXT,
            token_ref_id::TEXT,
            created
          FROM a1_complete_oauth_first_login_with_refresh(
            '{scope['organization']}'::UUID,
            '{scope['project']}'::UUID,
            '{provider}',
            '{material['subject']}',
            {email_sql},
            '{material['opaque_ref']}',
            '{material['opaque_ref_digest']}',
            '{material['binding']}',
            '{material['session']}',
            '{material['refresh']}',
            '{material['family']}',
            clock_timestamp() + interval '15 minutes',
            clock_timestamp() + interval '2 hours',
            '{material['idempotency']}',
            '{material['request']}',
            'OAuth First Login Test',
            '{{"source":"oauth_first_login_postgres_test"}}'::JSONB
          );
        """,
        user=user,
        check=check,
    )


def _parse_result(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    rows = _rows(result)
    assert len(rows) == 1, (result.stdout, result.stderr)
    (
        session,
        principal,
        credential,
        connection,
        token_ref,
        created,
    ) = rows[0].split("|")
    return {
        "session": session,
        "principal": principal,
        "credential": credential,
        "connection": connection,
        "token_ref": token_ref,
        "created": created,
    }


def test_migration_is_atomic_additive_and_follows_email_handoff() -> None:
    sql = _normalized()
    assert MIGRATION.name > "025_a1_email_registration_session_handoff.sql"
    assert sql.startswith(
        "-- atomic oauth first-login to canonical account and browser session handoff."
    )
    assert sql.startswith("-- atomic oauth")
    assert sql.index("begin;") < sql.index(
        "create table if not exists oauth_first_login_operations"
    )
    assert sql.strip().endswith("commit;")


def test_public_authority_signature_is_digest_and_reference_only() -> None:
    function = _function_body()
    signature = (
        "create or replace function "
        "a1_complete_oauth_first_login_with_refresh( "
        "p_organization_id uuid, p_project_id uuid, p_provider text, "
        "p_subject_digest text, p_email_digest text, p_opaque_ref text, "
        "p_opaque_ref_digest text, p_binding_digest text, "
        "p_session_digest text, p_refresh_digest text, "
        "p_rotation_family_digest text, p_access_expires_at timestamptz, "
        "p_refresh_expires_at timestamptz, p_idempotency_digest text, "
        "p_request_digest text, p_display_label text, "
        "p_metadata jsonb default '{}'::jsonb )"
    )
    assert signature in function
    assert (
        "returns table ( session_id uuid, principal_id uuid, "
        "credential_id uuid, connection_id uuid, token_ref_id uuid, "
        "created boolean )"
    ) in function

    forbidden_parameters = (
        "p_subject text",
        "p_email text",
        "p_access_token",
        "p_refresh_token",
        "p_id_token",
        "p_authorization_code",
        "p_code_verifier",
        "p_state",
        "p_nonce",
        "p_bearer",
        "p_principal_id",
        "p_account_id",
        "p_runtime_session_id",
        "p_provider_environment",
    )
    for fragment in forbidden_parameters:
        assert fragment not in function

    for parameter in (
        "p_subject_digest",
        "p_email_digest",
        "p_opaque_ref_digest",
        "p_binding_digest",
        "p_session_digest",
        "p_refresh_digest",
        "p_rotation_family_digest",
        "p_idempotency_digest",
        "p_request_digest",
    ):
        assert f"a1_identity_digest_valid({parameter})" in function
    assert "a1_oauth_reference_only(p_opaque_ref)" in function
    assert "a1_identity_public_metadata(p_metadata)" in function
    assert "a1_oauth_public_metadata(p_metadata)" in function


def test_operation_ledger_is_scoped_digest_only_and_replay_safe() -> None:
    table = _operation_table()
    required = (
        "organization_id uuid not null",
        "project_id uuid not null",
        "provider text not null",
        "subject_digest text not null",
        "idempotency_digest text not null",
        "request_digest text not null",
        "principal_id uuid",
        "credential_id uuid",
        "connection_id uuid",
        "token_ref_id uuid",
        "session_id uuid",
        "account_created boolean",
        "status text not null default 'processing'",
        "unique ( organization_id, project_id, provider, idempotency_digest )",
        "foreign key (organization_id, project_id)",
        "status = 'completed'",
    )
    for fragment in required:
        assert fragment in table

    forbidden_columns = (
        " email ",
        " subject ",
        " access_token ",
        " refresh_token ",
        " id_token ",
        " authorization_code ",
        " code_verifier ",
        " bearer ",
        " cookie ",
        " state ",
        " nonce ",
        " opaque_ref ",
    )
    for fragment in forbidden_columns:
        assert fragment not in f" {table} "

    function = _function_body()
    assert "on conflict (" in function
    assert "for update" in function
    assert "operation.request_digest <> p_request_digest" in function
    assert "operation.subject_digest <> p_subject_digest" in function
    assert "if operation.status = 'completed' then" in function
    assert "return query select" in function
    assert "raise exception 'idempotency_conflict'" in function


def test_authority_is_fixed_search_path_scope_bound_and_minimally_granted() -> None:
    sql = _normalized()
    function = _function_body()
    assert "language plpgsql security definer" in function
    assert "set search_path = pg_catalog, public, pg_temp" in function
    assert "a1_assert_role_nobypassrls(session_user)" in function
    assert "p_organization_id is distinct from a1_current_organization_id()" in function
    assert "p_project_id is distinct from a1_current_project_id()" in function
    assert "organization.status = 'active'" in function
    assert "project.status = 'active'" in function
    assert "p_provider not in ('google', 'github')" in function
    assert "'production'" in function

    signature = (
        "uuid,uuid,text,text,text,text,text,text,text,text,text,"
        "timestamptz,timestamptz,text,text,text,jsonb"
    )
    compact = re.sub(r"\s+", "", sql)
    assert (
        "revoke all on function "
        "a1_complete_oauth_first_login_with_refresh("
        f"{signature}) from public;"
    ).replace(" ", "") in compact
    assert (
        "grant execute on function "
        "a1_complete_oauth_first_login_with_refresh("
        f"{signature}) to a1_runtime;"
    ).replace(" ", "") in compact
    assert "grant insert on identity_principals to a1_runtime" not in sql
    assert "grant update on identity_credentials to a1_runtime" not in sql
    assert "grant insert on oauth_token_opaque_refs to a1_runtime" not in sql


def test_unknown_subject_creation_and_known_subject_login_are_separate() -> None:
    function = _function_body()
    lookup = function.index("from identity_credentials as credential_row")
    known = function.index("if found then", lookup)
    unknown = function.index("else", known)
    branch_end = function.index("end if;", unknown)
    known_branch = function[known:unknown]
    unknown_branch = function[unknown:branch_end]

    assert "pg_advisory_xact_lock(" in function[:lookup]
    assert "p_provider" in function[:lookup]
    assert "p_subject_digest" in function[:lookup]
    assert "provider_environment = 'production'" in function[lookup:known]
    assert "for update" in function[lookup:known]

    assert "principal.status <> 'active'" in known_branch
    assert "credential.status <> 'active'" in known_branch
    assert "not credential.login_enabled" in known_branch
    assert "identity_organization_memberships" in known_branch
    assert "identity_project_memberships" in known_branch
    assert "organization_membership.status = 'active'" in known_branch
    assert "project_membership.status = 'active'" in known_branch
    assert "insert into identity_principals" not in known_branch
    assert "insert into identity_organization_memberships" not in known_branch
    assert "insert into identity_project_memberships" not in known_branch
    assert "v_created := false" in known_branch

    assert "insert into identity_principals" in unknown_branch
    assert "insert into identity_credentials" in unknown_branch
    assert "insert into identity_organization_memberships" in unknown_branch
    assert "insert into identity_project_memberships" in unknown_branch
    assert "v_created := true" in unknown_branch


def test_verified_email_is_conflict_evidence_never_an_account_merge_key() -> None:
    function = _function_body()
    assert "from identity_account_emails" in function
    assert "normalized_email_digest = p_email_digest" in function
    assert "principal_id = v_principal_id" in function
    assert function.count("for update") >= 4
    assert "raise exception 'canonical_email_conflict'" in function
    assert "insert into identity_account_emails" in function
    assert "insert into identity_account_security" in function
    assert "a1_merge_identity_accounts" not in function
    assert "merged_into_principal_id" not in function
    assert "where normalized_email_digest = p_email_digest" not in (
        function[
            : function.index("from identity_credentials as credential_row")
        ]
    )


def test_session_connection_and_audit_complete_inside_one_authority() -> None:
    function = _function_body()
    principal = function.index("insert into identity_principals")
    credential = function.index("insert into identity_credentials")
    org_membership = function.index(
        "insert into identity_organization_memberships"
    )
    project_membership = function.index(
        "insert into identity_project_memberships"
    )
    token_ref = function.index("insert into oauth_token_opaque_refs")
    session = function.index("a1_issue_identity_session_with_refresh(")
    connection = function.index("insert into oauth_account_connections")
    audit = function.index("'identity.oauth.first_login.completed'")
    completion = function.index(
        "update oauth_first_login_operations", audit
    )
    assert principal < credential < org_membership < project_membership
    assert token_ref < session < connection < audit < completion
    assert "set_config('app.a1_principal_id'" in function
    assert "'aal1'" in function
    assert "p_session_digest" in function
    assert "p_refresh_digest" in function
    assert "p_rotation_family_digest" in function
    assert "account_id" in function
    assert "p_subject_digest" in function
    assert "provider_login" in function
    assert "'[redacted]'" in function
    assert "p_opaque_ref" not in function[audit:completion]
    assert "p_email_digest" not in function[audit:completion]
    assert "p_subject_digest" not in function[audit:completion]


def test_live_unknown_subject_replay_and_known_subject_login(
    oauth_first_login_database: str,
) -> None:
    database = oauth_first_login_database
    scope = _seed_scope(database, "unknown-known")
    first_material = _first_login_material("unknown-known-first")
    subject = first_material["subject"]
    email = first_material["email"]

    first = _parse_result(
        _complete_first_login(database, scope, first_material)
    )
    assert first["created"] == "t"

    persisted = _rows(
        _psql(
            database,
            f"""
              SELECT
                (SELECT count(*) FROM identity_principals
                  WHERE id = '{first['principal']}'),
                (SELECT count(*) FROM identity_credentials
                  WHERE id = '{first['credential']}'
                    AND provider = 'google'
                    AND provider_environment = 'production'
                    AND subject_digest = '{subject}'),
                (SELECT count(*) FROM identity_organization_memberships
                  WHERE organization_id = '{scope['organization']}'
                    AND principal_id = '{first['principal']}'
                    AND status = 'active'),
                (SELECT count(*) FROM identity_project_memberships
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}'
                    AND principal_id = '{first['principal']}'
                    AND status = 'active'),
                (SELECT count(*) FROM identity_sessions
                  WHERE id = '{first['session']}'
                    AND session_digest = '{first_material['session']}'
                    AND refresh_digest = '{first_material['refresh']}'),
                (SELECT count(*) FROM oauth_account_connections
                  WHERE id = '{first['connection']}'
                    AND principal_id = '{first['principal']}'
                    AND credential_id = '{first['credential']}'
                    AND account_id = '{subject}'
                    AND provider_login = '[redacted]'),
                (SELECT count(*) FROM identity_account_emails
                  WHERE principal_id = '{first['principal']}'
                    AND normalized_email_digest = '{email}'),
                (SELECT count(*) FROM identity_account_security
                  WHERE principal_id = '{first['principal']}'
                    AND two_factor_status = 'disabled'
                    AND two_factor_recommended),
                (SELECT count(*) FROM identity_audit_events
                  WHERE principal_id = '{first['principal']}'
                    AND action = 'identity.oauth.first_login.completed');
            """,
        )
    )
    assert persisted == ["1|1|1|1|1|1|1|1|1"]

    replay = _parse_result(
        _complete_first_login(database, scope, first_material)
    )
    assert replay == first

    second_material = _first_login_material("unknown-known-second")
    second_material["subject"] = subject
    second_material["email"] = email
    second = _parse_result(
        _complete_first_login(database, scope, second_material)
    )
    assert second["created"] == "f"
    assert second["principal"] == first["principal"]
    assert second["credential"] == first["credential"]
    assert second["connection"] == first["connection"]
    assert second["session"] != first["session"]
    assert second["token_ref"] != first["token_ref"]

    stable_counts = _rows(
        _psql(
            database,
            f"""
              SELECT
                (SELECT count(*) FROM identity_principals
                  WHERE id = '{first['principal']}'),
                (SELECT count(*) FROM identity_credentials
                  WHERE provider = 'google'
                    AND provider_environment = 'production'
                    AND subject_digest = '{subject}'),
                (SELECT count(*) FROM identity_organization_memberships
                  WHERE organization_id = '{scope['organization']}'
                    AND principal_id = '{first['principal']}'),
                (SELECT count(*) FROM identity_project_memberships
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}'
                    AND principal_id = '{first['principal']}'),
                (SELECT count(*) FROM identity_sessions
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}'
                    AND principal_id = '{first['principal']}'),
                (SELECT count(*) FROM oauth_token_opaque_refs
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}'
                    AND provider = 'google'
                    AND status = 'active'),
                (SELECT count(*) FROM oauth_token_opaque_refs
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}'
                    AND provider = 'google'
                    AND status = 'revocation_pending'),
                (SELECT count(*) FROM oauth_revocation_outbox
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}'
                    AND reason_code = 'first_login_reauthenticated');
            """,
        )
    )
    assert stable_counts == ["1|1|1|1|2|1|1|1"]


def test_live_known_subject_requires_active_trusted_memberships(
    oauth_first_login_database: str,
) -> None:
    database = oauth_first_login_database
    scope = _seed_scope(database, "revoked-membership")
    first_material = _first_login_material("revoked-membership-first")
    first = _parse_result(
        _complete_first_login(database, scope, first_material)
    )

    _psql(
        database,
        f"""
          UPDATE identity_project_memberships
             SET status = 'revoked',
                 revoked_at = clock_timestamp(),
                 updated_at = clock_timestamp()
           WHERE organization_id = '{scope['organization']}'
             AND project_id = '{scope['project']}'
             AND principal_id = '{first['principal']}';
        """,
        tuples=False,
    )
    before = _rows(
        _psql(
            database,
            f"""
              SELECT
                (SELECT count(*) FROM identity_sessions
                  WHERE principal_id = '{first['principal']}'),
                (SELECT count(*) FROM oauth_token_opaque_refs
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}');
            """,
        )
    )

    retry_material = _first_login_material("revoked-membership-retry")
    retry_material["subject"] = first_material["subject"]
    retry_material["email"] = first_material["email"]
    rejected = _complete_first_login(
        database, scope, retry_material, check=False
    )
    assert rejected.returncode != 0
    assert "canonical scope is unavailable" in rejected.stderr.lower()
    for secret in (
        retry_material["subject"],
        retry_material["email"],
        retry_material["opaque_ref"],
        retry_material["session"],
        retry_material["refresh"],
    ):
        assert secret not in rejected.stderr

    after = _rows(
        _psql(
            database,
            f"""
              SELECT
                (SELECT count(*) FROM identity_sessions
                  WHERE principal_id = '{first['principal']}'),
                (SELECT count(*) FROM oauth_token_opaque_refs
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}');
            """,
        )
    )
    assert after == before


def test_live_verified_email_conflict_rolls_back_without_merging(
    oauth_first_login_database: str,
) -> None:
    database = oauth_first_login_database
    scope = _seed_scope(database, "email-conflict")
    incumbent = str(uuid.uuid4())
    conflict_email = _digest("email-conflict:canonical-email")
    _psql(
        database,
        f"""
          INSERT INTO identity_principals (id, status)
          VALUES ('{incumbent}', 'active');
          INSERT INTO identity_account_emails (
            principal_id, normalized_email_digest, source_provider, verified_at
          ) VALUES (
            '{incumbent}', '{conflict_email}', 'email', clock_timestamp()
          );
        """,
        tuples=False,
    )
    before = _rows(
        _psql(
            database,
            """
              SELECT
                (SELECT count(*) FROM identity_principals),
                (SELECT count(*) FROM identity_credentials),
                (SELECT count(*) FROM identity_organization_memberships),
                (SELECT count(*) FROM identity_project_memberships),
                (SELECT count(*) FROM identity_sessions),
                (SELECT count(*) FROM oauth_token_opaque_refs),
                (SELECT count(*) FROM oauth_first_login_operations);
            """,
        )
    )
    material = _first_login_material("email-conflict-attempt")
    rejected = _complete_first_login(
        database,
        scope,
        material,
        email_digest=conflict_email,
        check=False,
    )
    assert rejected.returncode != 0
    assert "canonical_email_conflict" in rejected.stderr.lower()
    assert conflict_email not in rejected.stderr
    assert material["subject"] not in rejected.stderr

    after = _rows(
        _psql(
            database,
            """
              SELECT
                (SELECT count(*) FROM identity_principals),
                (SELECT count(*) FROM identity_credentials),
                (SELECT count(*) FROM identity_organization_memberships),
                (SELECT count(*) FROM identity_project_memberships),
                (SELECT count(*) FROM identity_sessions),
                (SELECT count(*) FROM oauth_token_opaque_refs),
                (SELECT count(*) FROM oauth_first_login_operations);
            """,
        )
    )
    assert after == before
    assert _rows(
        _psql(
            database,
            f"""
              SELECT count(*) FROM identity_credentials
               WHERE provider = 'google'
                 AND subject_digest = '{material['subject']}';
            """,
        )
    ) == ["0"]


def test_live_cross_scope_provider_and_bypass_attempts_fail_closed(
    oauth_first_login_database: str,
) -> None:
    database = oauth_first_login_database
    trusted = _seed_scope(database, "trusted-scope")
    attacker = _seed_scope(database, "attacker-scope")
    material = _first_login_material("scope-attack")

    cross_scope = _complete_first_login(
        database,
        trusted,
        material,
        runtime_scope=attacker,
        check=False,
    )
    assert cross_scope.returncode != 0
    assert "trusted scope is unavailable" in cross_scope.stderr.lower()

    unsupported = _complete_first_login(
        database,
        trusted,
        material,
        provider="qq",
        check=False,
    )
    assert unsupported.returncode != 0
    assert "input rejected" in unsupported.stderr.lower()

    superuser = _complete_first_login(
        database,
        trusted,
        material,
        user="postgres",
        check=False,
    )
    assert superuser.returncode != 0
    assert "nosuperuser nobypassrls" in superuser.stderr.lower()

    assert _rows(
        _psql(
            database,
            f"""
              SELECT count(*) FROM identity_credentials
               WHERE subject_digest = '{material['subject']}';
            """,
        )
    ) == ["0"]


def test_live_session_and_connection_failures_roll_back_everything(
    oauth_first_login_database: str,
) -> None:
    database = oauth_first_login_database
    scope = _seed_scope(database, "rollback")

    def counts(material: dict[str, str]) -> list[str]:
        return _rows(
            _psql(
                database,
                f"""
                  SELECT
                    (SELECT count(*) FROM identity_credentials
                      WHERE subject_digest = '{material['subject']}'),
                    (SELECT count(*) FROM identity_sessions
                      WHERE session_digest = '{material['session']}'),
                    (SELECT count(*) FROM oauth_token_opaque_refs
                      WHERE opaque_ref_digest =
                            '{material['opaque_ref_digest']}'),
                    (SELECT count(*) FROM oauth_first_login_operations
                      WHERE idempotency_digest =
                            '{material['idempotency']}');
                """,
            )
        )

    session_material = _first_login_material("rollback-session")
    _psql(
        database,
        """
          CREATE OR REPLACE FUNCTION a1_test_reject_first_login_session()
          RETURNS TRIGGER LANGUAGE plpgsql AS $$
          BEGIN
            IF NEW.session_digest IS NOT NULL THEN
              RAISE EXCEPTION 'test_session_insert_failure';
            END IF;
            RETURN NEW;
          END;
          $$;
          CREATE TRIGGER a1_test_reject_first_login_session
          BEFORE INSERT ON identity_sessions
          FOR EACH ROW EXECUTE FUNCTION
            a1_test_reject_first_login_session();
        """,
        tuples=False,
    )
    try:
        rejected = _complete_first_login(
            database, scope, session_material, check=False
        )
        assert rejected.returncode != 0
        assert "test_session_insert_failure" in rejected.stderr
    finally:
        _psql(
            database,
            """
              DROP TRIGGER IF EXISTS a1_test_reject_first_login_session
                ON identity_sessions;
              DROP FUNCTION IF EXISTS
                a1_test_reject_first_login_session();
            """,
            tuples=False,
        )
    assert counts(session_material) == ["0|0|0|0"]

    connection_material = _first_login_material("rollback-connection")
    _psql(
        database,
        """
          CREATE OR REPLACE FUNCTION a1_test_reject_first_login_connection()
          RETURNS TRIGGER LANGUAGE plpgsql AS $$
          BEGIN
            IF NEW.provider IN ('google', 'github') THEN
              RAISE EXCEPTION 'test_connection_insert_failure';
            END IF;
            RETURN NEW;
          END;
          $$;
          CREATE TRIGGER a1_test_reject_first_login_connection
          BEFORE INSERT ON oauth_account_connections
          FOR EACH ROW EXECUTE FUNCTION
            a1_test_reject_first_login_connection();
        """,
        tuples=False,
    )
    try:
        rejected = _complete_first_login(
            database, scope, connection_material, check=False
        )
        assert rejected.returncode != 0
        assert "test_connection_insert_failure" in rejected.stderr
    finally:
        _psql(
            database,
            """
              DROP TRIGGER IF EXISTS a1_test_reject_first_login_connection
                ON oauth_account_connections;
              DROP FUNCTION IF EXISTS
                a1_test_reject_first_login_connection();
            """,
            tuples=False,
        )
    assert counts(connection_material) == ["0|0|0|0"]


def test_live_concurrent_unknown_subject_creates_one_canonical_account(
    oauth_first_login_database: str,
) -> None:
    database = oauth_first_login_database
    scope = _seed_scope(database, "concurrent")
    first = _first_login_material("concurrent-first")
    second = _first_login_material("concurrent-second")
    second["subject"] = first["subject"]
    second["email"] = first["email"]

    def contender(material: dict[str, str]):
        return _complete_first_login(
            database, scope, material, check=False
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(contender, (first, second)))

    successes = [result for result in results if result.returncode == 0]
    assert successes
    for result in results:
        if result.returncode != 0:
            assert (
                "could not serialize access" in result.stderr.lower()
                or "deadlock detected" in result.stderr.lower()
            )

    counts = _rows(
        _psql(
            database,
            f"""
              SELECT
                (SELECT count(*) FROM identity_credentials
                  WHERE provider = 'google'
                    AND provider_environment = 'production'
                    AND subject_digest = '{first['subject']}'),
                (SELECT count(DISTINCT principal_id)
                  FROM identity_credentials
                  WHERE provider = 'google'
                    AND provider_environment = 'production'
                    AND subject_digest = '{first['subject']}'),
                (SELECT count(*) FROM identity_organization_memberships
                  WHERE organization_id = '{scope['organization']}'),
                (SELECT count(*) FROM identity_project_memberships
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}'),
                (SELECT count(*) FROM oauth_account_connections
                  WHERE organization_id = '{scope['organization']}'
                    AND project_id = '{scope['project']}'
                    AND provider_subject_digest = '{first['subject']}');
            """,
        )
    )
    assert counts == ["1|1|1|1|1"]


def test_live_acl_and_direct_table_access_are_least_privilege(
    oauth_first_login_database: str,
) -> None:
    database = oauth_first_login_database
    acl = _rows(
        _psql(
            database,
            """
              SELECT
                has_function_privilege(
                  'a1_runtime',
                  function_row.oid,
                  'EXECUTE'
                ),
                NOT EXISTS (
                  SELECT 1
                    FROM aclexplode(function_row.proacl) AS privilege
                   WHERE privilege.grantee = 0
                     AND privilege.privilege_type = 'EXECUTE'
                )
              FROM pg_proc AS function_row
              JOIN pg_namespace AS namespace_row
                ON namespace_row.oid = function_row.pronamespace
             WHERE namespace_row.nspname = 'public'
               AND function_row.proname =
                     'a1_complete_oauth_first_login_with_refresh';
            """,
        )
    )
    assert acl == ["t|t"]

    scope = _seed_scope(database, "direct-access")
    direct_read = _psql(
        database,
        f"""
          SET app.a1_organization_id = '{scope['organization']}';
          SET app.a1_project_id = '{scope['project']}';
          SELECT count(*) FROM oauth_first_login_operations;
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert direct_read.returncode != 0
    assert "permission denied" in direct_read.stderr.lower()
