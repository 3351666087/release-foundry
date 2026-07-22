from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "api" / "migrations"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "ashr-oauth-pg-test")
SQL = (
    MIGRATIONS
    / "020_a1_verified_credential_mutation_authority.sql"
).read_text(encoding="utf-8").lower()


def _docker(*args: str, input_text: str | None = None, check: bool = True):
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker CLI is unavailable for live PostgreSQL tests")
    return subprocess.run(
        [docker, *args],
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
            r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|GRANT|CREATE)\b", line
        )
    ]


@pytest.fixture
def mutation_authority_database() -> str:
    available = _docker(
        "inspect", "-f", "{{.State.Running}}", CONTAINER, check=False
    )
    if available.returncode != 0 or available.stdout.strip() != "true":
        pytest.skip(f"PostgreSQL container {CONTAINER!r} is not running")

    _psql(
        "postgres",
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') THEN
            CREATE ROLE a1_runtime LOGIN;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname='a1_security_ticket_issuer'
          ) THEN
            CREATE ROLE a1_security_ticket_issuer LOGIN;
          END IF;
        END
        $$;
        """,
        tuples=False,
    )
    database = f"a1_credential_bind_it_{uuid.uuid4().hex[:12]}"
    _psql("postgres", f'CREATE DATABASE "{database}";', tuples=False)
    try:
        migrations = [
            migration
            for migration in sorted(MIGRATIONS.glob("*.sql"))
            if migration.name < "019_" or migration.name.startswith("020_")
        ]
        for migration in migrations:
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


def test_credential_binding_uses_explicit_secret_free_ticket_authority() -> None:
    assert "'credential_bind'" in SQL
    assert "operation='credential_bind'" in SQL
    assert "secret_ref is null and secret_digest is null" in SQL
    assert "recovery_batch_digest is null and recovery_code_count is null" in SQL
    assert "p_operation<>'credential_bind'" in SQL


def test_authorized_binding_is_recent_session_and_request_bound() -> None:
    authority = SQL.split(
        "create or replace function a1_bind_verified_identity_credential_authorized", 1
    )[1]
    assert "security definer" in authority
    assert "set search_path=pg_catalog,public,pg_temp" in authority
    assert "clock_timestamp()" in authority
    assert "v_ticket.principal_id<>p_principal_id" in authority
    assert "v_ticket.actor_principal_id<>p_principal_id" in authority
    assert "v_ticket.step_up_receipt_digest<>p_step_up_receipt_digest" in authority
    assert "v_ticket.context_digest<>p_request_digest" in authority
    assert (
        "p_organization_id,p_project_id,p_principal_id,p_session_digest,600,'aal1'"
        in authority
    )
    assert "a1_consume_identity_security_receipt(" in authority
    assert "p_step_up_receipt_digest,p_principal_id,'credential_bind'" in authority
    assert "if v_ticket.consumed_at is not null then" in authority
    assert "return a1_bind_verified_identity_credential(" in authority


def test_runtime_cannot_bypass_authorized_binding_wrapper() -> None:
    assert (
        "revoke all on function a1_bind_verified_identity_credential_authorized("
        in SQL
    )
    assert "revoke all on function a1_bind_verified_identity_credential(" in SQL
    assert (
        "revoke execute on function a1_bind_verified_identity_credential("
        in SQL
    )
    assert (
        "grant execute on function a1_bind_verified_identity_credential_authorized("
        in SQL
    )


def test_live_authorized_binding_enforces_session_ticket_rls_and_replay(
    mutation_authority_database: str,
) -> None:
    organization = str(uuid.uuid4())
    workspace = str(uuid.uuid4())
    project = str(uuid.uuid4())
    principal = str(uuid.uuid4())
    membership = str(uuid.uuid4())
    credential = str(uuid.uuid4())
    challenge = str(uuid.uuid4())
    digest_names = (
        "login_subject",
        "session",
        "rotation",
        "binding_subject",
        "challenge",
        "code",
        "verification_context",
        "verification_receipt",
        "request",
        "step_up",
        "ticket",
        "idempotency",
        "event",
        "changed_request",
        "changed_event",
        "wrong_session",
    )
    digest = {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in digest_names
    }
    _psql(
        mutation_authority_database,
        f"""
        INSERT INTO organizations(id,slug,display_name)
        VALUES('{organization}','bind-org','Bind Org');
        INSERT INTO workspaces(id,organization_id,slug,display_name)
        VALUES('{workspace}','{organization}','bind','Bind');
        INSERT INTO projects(id,organization_id,workspace_id,slug,display_name)
        VALUES('{project}','{organization}','{workspace}','bind','Bind');
        INSERT INTO identity_principals(id,status)
        VALUES('{principal}','active');
        INSERT INTO identity_organization_memberships(
          id,organization_id,principal_id,status,activated_at
        ) VALUES(
          '{membership}','{organization}','{principal}','active',clock_timestamp()
        );
        INSERT INTO identity_project_memberships(
          organization_id,project_id,principal_id,
          organization_membership_id,status,activated_at
        ) VALUES(
          '{organization}','{project}','{principal}',
          '{membership}','active',clock_timestamp()
        );
        INSERT INTO identity_credentials(
          id,principal_id,provider,credential_kind,subject_digest,
          status,login_enabled,verified_at,last_authenticated_at
        ) VALUES(
          '{credential}','{principal}','email','email_otp',
          '{digest["login_subject"]}','active',TRUE,
          clock_timestamp(),clock_timestamp()
        );
        INSERT INTO identity_sessions(
          principal_id,credential_id,organization_id,project_id,
          session_digest,rotation_family_digest,status,assurance_level,
          authenticated_at,expires_at
        ) VALUES(
          '{principal}','{credential}','{organization}','{project}',
          '{digest["session"]}','{digest["rotation"]}','active','aal1',
          clock_timestamp(),clock_timestamp()+interval '30 minutes'
        );
        INSERT INTO identity_verification_challenges(
          id,organization_id,project_id,principal_id,channel,purpose,
          subject_digest,challenge_digest,code_digest,request_context_digest,
          status,issued_at,expires_at,verified_at
        ) VALUES(
          '{challenge}','{organization}','{project}','{principal}',
          'email','credential_binding','{digest["binding_subject"]}',
          '{digest["challenge"]}','{digest["code"]}',
          '{digest["verification_context"]}','verified',
          clock_timestamp(),clock_timestamp()+interval '10 minutes',
          clock_timestamp()
        );
        INSERT INTO identity_verification_receipts(
          organization_id,project_id,challenge_id,principal_id,channel,purpose,
          subject_digest,request_context_digest,receipt_digest,status,verified_at
        ) VALUES(
          '{organization}','{project}','{challenge}','{principal}',
          'email','credential_binding','{digest["binding_subject"]}',
          '{digest["verification_context"]}','{digest["verification_receipt"]}',
          'verified',clock_timestamp()
        );
        INSERT INTO identity_security_receipts(
          receipt_digest,principal_id,purpose,context_digest,expires_at
        ) VALUES(
          '{digest["step_up"]}','{principal}','credential_bind',
          '{digest["request"]}',clock_timestamp()+interval '10 minutes'
        );
        """,
        tuples=False,
    )

    issued = _rows(
        _psql(
            mutation_authority_database,
            f"""
            SET ROLE a1_security_ticket_issuer;
            SELECT a1_issue_identity_security_mutation_ticket(
              '{digest["ticket"]}','{digest["step_up"]}','{principal}',
              '{principal}','credential_bind','{digest["request"]}',
              NULL,NULL,NULL,NULL,clock_timestamp()+interval '5 minutes'
            );
            """,
        )
    )
    assert issued == ["t"]

    privileges = _rows(
        _psql(
            mutation_authority_database,
            """
            SELECT
              has_function_privilege(
                'a1_runtime',
                'a1_bind_verified_identity_credential_authorized(uuid,uuid,text,uuid,text,text,text,text,text,text,jsonb)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_runtime',
                'a1_bind_verified_identity_credential(uuid,uuid,text,uuid,text,text,text,jsonb)',
                'EXECUTE'
              ),
              has_function_privilege(
                'public',
                'a1_bind_verified_identity_credential_authorized(uuid,uuid,text,uuid,text,text,text,text,text,text,jsonb)',
                'EXECUTE'
              ),
              has_function_privilege(
                'public',
                'a1_bind_verified_identity_credential(uuid,uuid,text,uuid,text,text,text,jsonb)',
                'EXECUTE'
              ),
              has_table_privilege(
                'a1_runtime','identity_security_receipts','SELECT'
              ),
              has_table_privilege(
                'a1_runtime','identity_security_mutation_tickets','SELECT'
              );
            """,
        )
    )
    assert privileges == ["t|f|f|f|f|f"]

    runtime_scope = (
        f"SET app.a1_organization_id='{organization}';"
        f"SET app.a1_project_id='{project}';"
        f"SET app.a1_principal_id='{principal}';"
    )

    wrong_session = _psql(
        mutation_authority_database,
        runtime_scope
        + f"""
        SELECT a1_bind_verified_identity_credential_authorized(
          '{organization}','{project}','{digest["verification_receipt"]}',
          '{principal}','{digest["wrong_session"]}','{digest["ticket"]}',
          '{digest["step_up"]}','{digest["idempotency"]}',
          '{digest["request"]}','{digest["event"]}','{{}}'::jsonb
        );
        """,
        user="a1_runtime",
        check=False,
    )
    assert wrong_session.returncode != 0
    assert "recent_authentication_required" in wrong_session.stderr
    still_available = _rows(
        _psql(
            mutation_authority_database,
            f"""
            SELECT
              (SELECT consumed_at IS NULL FROM identity_security_receipts
                WHERE receipt_digest='{digest["step_up"]}'),
              (SELECT consumed_at IS NULL FROM identity_security_mutation_tickets
                WHERE ticket_digest='{digest["ticket"]}');
            """,
        )
    )
    assert still_available == ["t|t"]

    bound = _rows(
        _psql(
            mutation_authority_database,
            runtime_scope
            + f"""
            SELECT a1_bind_verified_identity_credential_authorized(
              '{organization}','{project}','{digest["verification_receipt"]}',
              '{principal}','{digest["session"]}','{digest["ticket"]}',
              '{digest["step_up"]}','{digest["idempotency"]}',
              '{digest["request"]}','{digest["event"]}','{{}}'::jsonb
            );
            """,
            user="a1_runtime",
        )
    )
    assert len(bound) == 1
    bound_credential = str(uuid.UUID(bound[0]))

    consumed = _rows(
        _psql(
            mutation_authority_database,
            f"""
            SELECT
              (SELECT consumed_at IS NOT NULL FROM identity_security_receipts
                WHERE receipt_digest='{digest["step_up"]}'),
              (SELECT consumed_at IS NOT NULL FROM identity_security_mutation_tickets
                WHERE ticket_digest='{digest["ticket"]}'),
              (SELECT status='consumed' FROM identity_verification_receipts
                WHERE receipt_digest='{digest["verification_receipt"]}'),
              (SELECT count(*)=1 FROM identity_credentials
                WHERE id='{bound_credential}' AND principal_id='{principal}');
            """,
        )
    )
    assert consumed == ["t|t|t|t"]

    replay = _rows(
        _psql(
            mutation_authority_database,
            runtime_scope
            + f"""
            SELECT a1_bind_verified_identity_credential_authorized(
              '{organization}','{project}','{digest["verification_receipt"]}',
              '{principal}','{digest["wrong_session"]}','{digest["ticket"]}',
              '{digest["step_up"]}','{digest["idempotency"]}',
              '{digest["request"]}','{digest["event"]}','{{}}'::jsonb
            );
            """,
            user="a1_runtime",
        )
    )
    assert replay == [bound_credential]

    conflict = _psql(
        mutation_authority_database,
        runtime_scope
        + f"""
        SELECT a1_bind_verified_identity_credential_authorized(
          '{organization}','{project}','{digest["verification_receipt"]}',
          '{principal}','{digest["session"]}','{digest["ticket"]}',
          '{digest["step_up"]}','{digest["idempotency"]}',
          '{digest["changed_request"]}','{digest["changed_event"]}','{{}}'::jsonb
        );
        """,
        user="a1_runtime",
        check=False,
    )
    assert conflict.returncode != 0
    assert (
        "authorization_rejected" in conflict.stderr
        or "idempotency_conflict" in conflict.stderr
    )

    rls = _rows(
        _psql(
            mutation_authority_database,
            """
            SELECT relname,relrowsecurity,relforcerowsecurity
              FROM pg_class
             WHERE relname IN (
               'identity_security_receipts',
               'identity_security_mutation_tickets'
             )
             ORDER BY relname;
            """,
        )
    )
    assert rls == [
        "identity_security_mutation_tickets|t|t",
        "identity_security_receipts|t|t",
    ]
