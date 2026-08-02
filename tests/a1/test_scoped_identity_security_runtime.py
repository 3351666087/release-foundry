from __future__ import annotations

import hashlib
import os
import re
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "api" / "migrations"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "releasefoundry-oauth-pg-test")
SQL = (MIGRATIONS / "022_a1_scoped_identity_security_runtime.sql").read_text(
    encoding="utf-8"
).lower()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _psql(
    database: str,
    sql: str,
    *,
    tuples: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "exec",
        "-i",
        CONTAINER,
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "postgres",
        "-d",
        database,
    ]
    if tuples:
        command.extend(["-A", "-t", "-F", "|"])
    return subprocess.run(
        command,
        input=sql,
        text=True,
        capture_output=True,
        check=check,
    )


def _rows(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
        and not re.match(
            r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|GRANT|REVOKE|CREATE)\b",
            line,
        )
    ]


@pytest.fixture(scope="module")
def scoped_security_database() -> str:
    running = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        text=True,
        capture_output=True,
    )
    if running.returncode or running.stdout.strip() != "true":
        pytest.skip(f"PostgreSQL container {CONTAINER!r} is not running")

    _psql(
        "postgres",
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') THEN
            CREATE ROLE a1_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname='a1_security_ticket_issuer'
          ) THEN
            CREATE ROLE a1_security_ticket_issuer
              NOLOGIN NOSUPERUSER NOBYPASSRLS;
          END IF;
        END
        $$;
        """,
        tuples=False,
    )
    database = f"a1_scoped_security_it_{uuid.uuid4().hex[:12]}"
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


def _runtime_sql(principal_id: str, statement: str) -> str:
    return (
        "BEGIN; "
        "SET LOCAL ROLE a1_runtime; "
        f"SELECT set_config('app.a1_principal_id','{principal_id}',true); "
        f"{statement} "
        "COMMIT;"
    )


def test_migration_declares_only_principal_scoped_runtime_authorities() -> None:
    assert "a1_current_principal_id() is distinct from p_principal_id" in SQL
    assert "identity_security_principal_scope_rejected" in SQL
    assert "identity_security_ticket_scope_rejected" in SQL
    assert (
        "revoke execute on function "
        "a1_resolve_identity_security_mutation_ticket("
        in SQL
    )
    assert (
        "grant execute on function "
        "a1_resolve_identity_security_mutation_ticket("
        in SQL
    )
    assert "text,text,text,uuid,timestamptz" in re.sub(r"\s+", "", SQL)
    assert "text,text,text,uuid" in re.sub(r"\s+", "", SQL)


def test_runtime_rejects_foreign_canonical_account_without_consumption(
    scoped_security_database: str,
) -> None:
    database = scoped_security_database
    principal_a = str(uuid.uuid4())
    principal_b = str(uuid.uuid4())
    ticket = _digest("scoped-security-ticket")
    receipt = _digest("scoped-security-receipt")
    context = _digest("scoped-security-context")
    secret = _digest("scoped-security-secret")
    request = _digest("scoped-security-request")

    _psql(
        database,
        f"""
        INSERT INTO identity_principals(id,status)
        VALUES ('{principal_a}','active'),('{principal_b}','active');
        INSERT INTO identity_account_security(principal_id)
        VALUES ('{principal_a}'),('{principal_b}');
        INSERT INTO identity_security_receipts(
          receipt_digest,principal_id,purpose,context_digest,expires_at
        ) VALUES (
          '{receipt}','{principal_b}','password_enroll','{context}',
          clock_timestamp()+interval '10 minutes'
        );
        SET ROLE a1_security_ticket_issuer;
        SELECT a1_issue_identity_security_mutation_ticket(
          '{ticket}','{receipt}','{principal_b}','{principal_b}',
          'password_enroll','{context}','vault://password/scoped','{secret}',
          NULL,NULL,clock_timestamp()+interval '5 minutes'
        );
        RESET ROLE;
        """,
    )

    foreign_calls = (
        f"SELECT a1_project_account_security('{principal_b}'::uuid);",
        "SELECT a1_resolve_identity_security_mutation_ticket("
        f"'{ticket}','{receipt}','password_enroll','{principal_b}'::uuid,"
        "clock_timestamp());",
        "SELECT a1_execute_identity_security_mutation("
        f"'{ticket}','scoped-idempotency','{request}','{principal_b}'::uuid);",
    )
    for statement in foreign_calls:
        rejected = _psql(
            database,
            _runtime_sql(principal_a, statement),
            check=False,
        )
        assert rejected.returncode != 0
        assert "identity_security_principal_scope_rejected" in rejected.stderr

    untouched = _rows(
        _psql(
            database,
            "SELECT ticket.consumed_at IS NULL, receipt.consumed_at IS NULL "
            "FROM identity_security_mutation_tickets ticket "
            "JOIN identity_security_receipts receipt "
            "ON receipt.receipt_digest=ticket.step_up_receipt_digest "
            f"WHERE ticket.ticket_digest='{ticket}';",
        )
    )
    assert untouched == ["t|t"]

    posture = _rows(
        _psql(
            database,
            _runtime_sql(
                principal_b,
                f"SELECT a1_project_account_security('{principal_b}'::uuid);",
            ),
        )
    )
    assert len(posture) == 2
    projection = posture[-1]
    assert '"two_factor_optional": true' in projection
    assert '"two_factor_recommended": true' in projection
    for forbidden in (
        "vault://",
        secret,
        receipt,
        "password_secret_ref",
        "totp_secret_ref",
        "recovery_code_batch_digest",
        "session_digest",
    ):
        assert forbidden not in projection

    resolved = _rows(
        _psql(
            database,
            _runtime_sql(
                principal_b,
                "SELECT a1_resolve_identity_security_mutation_ticket("
                f"'{ticket}','{receipt}','password_enroll',"
                f"'{principal_b}'::uuid,clock_timestamp());",
            ),
        )
    )[-1]
    assert principal_b in resolved
    assert ticket in resolved
    assert secret not in resolved
    assert "vault://" not in resolved

    execute = (
        "SELECT a1_execute_identity_security_mutation("
        f"'{ticket}','scoped-idempotency','{request}','{principal_b}'::uuid);"
    )
    first = _rows(_psql(database, _runtime_sql(principal_b, execute)))[-1]
    replay = _rows(_psql(database, _runtime_sql(principal_b, execute)))[-1]
    assert replay == first
    assert '"password_status": "set"' in first
    for forbidden in ("vault://", secret, receipt):
        assert forbidden not in first


def test_runtime_privileges_expose_only_scoped_functions(
    scoped_security_database: str,
) -> None:
    database = scoped_security_database
    privileges = _rows(
        _psql(
            database,
            """
            SELECT
              has_function_privilege(
                'a1_runtime',
                'a1_resolve_identity_security_mutation_ticket'
                '(text,text,text,timestamp with time zone)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_runtime',
                'a1_execute_identity_security_mutation(text,text,text)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_runtime',
                'a1_resolve_identity_security_mutation_ticket'
                '(text,text,text,uuid,timestamp with time zone)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_runtime',
                'a1_execute_identity_security_mutation(text,text,text,uuid)',
                'EXECUTE'
              );
            """,
        )
    )
    assert privileges == ["f|f|t|t"]

    direct_tables = _rows(
        _psql(
            database,
            """
            SELECT count(*)
            FROM information_schema.role_table_grants
            WHERE grantee='a1_runtime'
              AND table_schema='public'
              AND table_name IN (
                'identity_account_security',
                'identity_security_receipts',
                'identity_security_mutation_tickets',
                'identity_security_mutation_idempotency'
              );
            """,
        )
    )
    assert direct_tables == ["0"]

    public_execute = _rows(
        _psql(
            database,
            """
            SELECT count(*)
            FROM pg_proc procedure
            CROSS JOIN LATERAL aclexplode(
              coalesce(
                procedure.proacl,
                acldefault('f',procedure.proowner)
              )
            ) privilege
            WHERE procedure.oid IN (
              'a1_project_account_security(uuid)'::regprocedure,
              'a1_resolve_identity_security_mutation_ticket'
                '(text,text,text,uuid,timestamp with time zone)'::regprocedure,
              'a1_execute_identity_security_mutation'
                '(text,text,text,uuid)'::regprocedure
            )
              AND privilege.grantee=0
              AND privilege.privilege_type='EXECUTE';
            """,
        )
    )
    assert public_execute == ["0"]
