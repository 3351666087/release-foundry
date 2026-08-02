from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "api" / "migrations"
MIGRATION = MIGRATIONS / "029_a1_totp_recovery_lifecycle.sql"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "releasefoundry-oauth-pg-test")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _docker(
    *args: str,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
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
    tuples: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [
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
    return _docker(*command, input_text=sql, check=check)


def _rows(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
        and not re.match(
            r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|DELETE|GRANT|REVOKE|CREATE)\b",
            line,
        )
    ]


@dataclass(frozen=True)
class RecoveryAccount:
    organization_id: str
    workspace_id: str
    project_id: str
    principal_id: str
    membership_id: str
    credential_id: str
    recent_session_id: str
    session_digest: str
    secret_ref: str
    secret_digest: str
    recovery_batch_digest: str
    recovery_code_count: int
    security_version: int


@pytest.fixture(scope="module")
def recovery_database() -> tuple[str, str, str]:
    running = _docker(
        "inspect",
        "-f",
        "{{.State.Running}}",
        CONTAINER,
        check=False,
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
    suffix = uuid.uuid4().hex[:12]
    runtime_login = f"a1_recovery_runtime_{suffix}"
    issuer_login = f"a1_recovery_issuer_{suffix}"
    _psql(
        "postgres",
        f"""
        CREATE ROLE "{runtime_login}"
          LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
          NOBYPASSRLS NOINHERIT;
        CREATE ROLE "{issuer_login}"
          LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
          NOBYPASSRLS NOINHERIT;
        GRANT a1_runtime TO "{runtime_login}";
        GRANT a1_security_ticket_issuer TO "{issuer_login}";
        """,
        tuples=False,
    )

    database = f"a1_totp_recovery_it_{suffix}"
    _psql("postgres", f'CREATE DATABASE "{database}";', tuples=False)
    try:
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            _psql(
                database,
                migration.read_text(encoding="utf-8"),
                tuples=False,
            )
        yield database, runtime_login, issuer_login
    finally:
        _psql(
            "postgres",
            f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE);',
            tuples=False,
            check=False,
        )
        _psql(
            "postgres",
            f"""
            REVOKE a1_runtime FROM "{runtime_login}";
            REVOKE a1_security_ticket_issuer FROM "{issuer_login}";
            DROP ROLE IF EXISTS "{runtime_login}";
            DROP ROLE IF EXISTS "{issuer_login}";
            """,
            tuples=False,
            check=False,
        )


def _seed_enabled_account(
    database: str,
    label: str,
    *,
    recovery_code_count: int = 10,
    security_version: int = 4,
) -> RecoveryAccount:
    organization_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    principal_id = str(uuid.uuid4())
    membership_id = str(uuid.uuid4())
    credential_id = str(uuid.uuid4())
    recent_session_id = str(uuid.uuid4())
    second_session_id = str(uuid.uuid4())
    session_digest = _digest(f"{label}:session")
    second_session_digest = _digest(f"{label}:session:second")
    rotation_digest = _digest(f"{label}:rotation")
    second_rotation_digest = _digest(f"{label}:rotation:second")
    subject_digest = _digest(f"{label}:subject")
    secret_ref = f"vault://totp/recovery/{label}/{uuid.uuid4().hex}"
    secret_digest = _digest(f"{label}:totp-secret")
    recovery_batch_digest = _digest(f"{label}:recovery-batch")
    slug = f"a1-recovery-{uuid.uuid4().hex[:12]}"

    _psql(
        database,
        f"""
        INSERT INTO organizations(id,slug,display_name)
        VALUES ('{organization_id}','{slug}','A1 Recovery');
        INSERT INTO workspaces(id,organization_id,slug,display_name)
        VALUES (
          '{workspace_id}','{organization_id}','{slug}','A1 Recovery'
        );
        INSERT INTO projects(
          id,organization_id,workspace_id,slug,display_name
        ) VALUES (
          '{project_id}','{organization_id}','{workspace_id}',
          '{slug}','A1 Recovery'
        );
        INSERT INTO identity_principals(id,status)
        VALUES ('{principal_id}','active');
        INSERT INTO identity_organization_memberships(
          id,organization_id,principal_id,status,activated_at
        ) VALUES (
          '{membership_id}','{organization_id}','{principal_id}',
          'active',clock_timestamp()
        );
        INSERT INTO identity_project_memberships(
          organization_id,project_id,principal_id,
          organization_membership_id,status,activated_at
        ) VALUES (
          '{organization_id}','{project_id}','{principal_id}',
          '{membership_id}','active',clock_timestamp()
        );
        INSERT INTO identity_credentials(
          id,principal_id,provider,credential_kind,subject_digest,
          status,login_enabled,verified_at,last_authenticated_at
        ) VALUES (
          '{credential_id}','{principal_id}','email','email_otp',
          '{subject_digest}','active',TRUE,clock_timestamp(),clock_timestamp()
        );
        INSERT INTO identity_sessions(
          id,principal_id,credential_id,organization_id,project_id,
          session_digest,rotation_family_digest,status,assurance_level,
          authenticated_at,expires_at
        ) VALUES
        (
          '{recent_session_id}','{principal_id}','{credential_id}',
          '{organization_id}','{project_id}','{session_digest}',
          '{rotation_digest}','active','aal1',clock_timestamp(),
          clock_timestamp()+interval '30 minutes'
        ),
        (
          '{second_session_id}','{principal_id}','{credential_id}',
          '{organization_id}','{project_id}','{second_session_digest}',
          '{second_rotation_digest}','active','aal1',clock_timestamp(),
          clock_timestamp()+interval '30 minutes'
        );
        INSERT INTO identity_account_security(
          principal_id,two_factor_status,totp_secret_ref,totp_secret_digest,
          totp_pending_at,two_factor_enrolled_at,
          recovery_code_batch_digest,recovery_codes_remaining,
          security_version
        ) VALUES (
          '{principal_id}','enabled','{secret_ref}','{secret_digest}',
          NULL,clock_timestamp(),'{recovery_batch_digest}',
          {recovery_code_count},{security_version}
        );
        """,
        tuples=False,
    )
    return RecoveryAccount(
        organization_id=organization_id,
        workspace_id=workspace_id,
        project_id=project_id,
        principal_id=principal_id,
        membership_id=membership_id,
        credential_id=credential_id,
        recent_session_id=recent_session_id,
        session_digest=session_digest,
        secret_ref=secret_ref,
        secret_digest=secret_digest,
        recovery_batch_digest=recovery_batch_digest,
        recovery_code_count=recovery_code_count,
        security_version=security_version,
    )


def _context_digest(
    account: RecoveryAccount,
    operation: str,
    issuer_idempotency_key: str,
) -> str:
    parts = [
        "releasefoundry.identity_security_ticket.v1",
        account.organization_id,
        account.project_id,
        account.principal_id,
        account.principal_id,
        account.recent_session_id,
        account.session_digest,
        operation,
        issuer_idempotency_key,
    ]
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def _issuer_statement(
    account: RecoveryAccount,
    issuer_login: str,
    operation: str,
    issuer_idempotency_key: str,
    *,
    new_recovery_batch_digest: str | None,
    new_recovery_code_count: int,
    expected_recovery_batch_digest: str | None = None,
    expected_recovery_code_count: int | None = None,
) -> str:
    context_digest = _context_digest(
        account,
        operation,
        issuer_idempotency_key,
    )
    expected_digest = (
        account.recovery_batch_digest
        if expected_recovery_batch_digest is None
        else expected_recovery_batch_digest
    )
    expected_count = (
        account.recovery_code_count
        if expected_recovery_code_count is None
        else expected_recovery_code_count
    )
    return f"""
        BEGIN;
        SET SESSION AUTHORIZATION "{issuer_login}";
        SET LOCAL ROLE a1_security_ticket_issuer;
        SET LOCAL app.a1_organization_id = '{account.organization_id}';
        SET LOCAL app.a1_project_id = '{account.project_id}';
        SET LOCAL app.a1_principal_id = '{account.principal_id}';
        WITH issuance AS (
          SELECT a1_issue_scoped_identity_security_mutation_ticket(
            '{account.organization_id}',
            '{account.project_id}',
            '{account.principal_id}',
            '{account.principal_id}',
            '{account.recent_session_id}',
            '{account.session_digest}',
            '{operation}',
            '{issuer_idempotency_key}',
            '{context_digest}',
            '{account.secret_ref}',
            '{account.secret_digest}',
            {_sql_literal(expected_digest)},
            {expected_count},
            {_sql_literal(new_recovery_batch_digest)},
            {new_recovery_code_count},
            clock_timestamp()+interval '4 minutes'
          ) AS payload
        )
        SELECT
          payload->>'ticket_id',
          payload->>'step_up_receipt_id',
          payload->>'context_digest'
        FROM issuance;
        COMMIT;
    """


def _issue_ticket(
    database: str,
    issuer_login: str,
    account: RecoveryAccount,
    operation: str,
    label: str,
    *,
    new_recovery_batch_digest: str | None,
    new_recovery_code_count: int,
    expected_recovery_batch_digest: str | None = None,
    expected_recovery_code_count: int | None = None,
) -> tuple[str, str, str, str]:
    issuer_key = f"a1-recovery-issuer:{label}:{uuid.uuid4().hex[:12]}"
    result = _psql(
        database,
        _issuer_statement(
            account,
            issuer_login,
            operation,
            issuer_key,
            new_recovery_batch_digest=new_recovery_batch_digest,
            new_recovery_code_count=new_recovery_code_count,
            expected_recovery_batch_digest=expected_recovery_batch_digest,
            expected_recovery_code_count=expected_recovery_code_count,
        ),
    )
    rows = _rows(result)
    assert len(rows) == 1
    ticket, receipt, context = rows[0].split("|")
    assert context == _context_digest(account, operation, issuer_key)
    return ticket, receipt, context, issuer_key


def _runtime_sql(
    runtime_login: str,
    principal_id: str,
    statement: str,
) -> str:
    return f"""
        BEGIN;
        SET SESSION AUTHORIZATION "{runtime_login}";
        SET LOCAL ROLE a1_runtime;
        SET LOCAL app.a1_principal_id = '{principal_id}';
        {statement}
        COMMIT;
    """


def _execute(
    database: str,
    runtime_login: str,
    principal_id: str,
    ticket: str,
    idempotency_key: str,
    request_fingerprint: str,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _psql(
        database,
        _runtime_sql(
            runtime_login,
            principal_id,
            "SELECT a1_execute_identity_security_mutation("
            f"'{ticket}','{idempotency_key}','{request_fingerprint}',"
            f"'{principal_id}'::uuid);",
        ),
        check=check,
    )


def _json_result(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    rows = _rows(result)
    assert len(rows) == 1
    value = json.loads(rows[0])
    assert isinstance(value, dict)
    return value


def test_migration_029_is_additive_digest_only_and_cleanly_applied(
    recovery_database: tuple[str, str, str],
) -> None:
    database, _, _ = recovery_database
    sql = re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8").lower())
    assert sql.startswith("-- complete the durable totp recovery lifecycle")
    assert sql.strip().endswith("commit;")
    assert "raw totp secrets, recovery codes and processor tokens" in sql
    assert "mfa_recovery_consume" in sql
    assert "mfa_recovery_rotate" in sql
    assert "mfa_disable" in sql
    assert _rows(
        _psql(
            database,
            """
            SELECT
              to_regprocedure(
                'a1_issue_scoped_identity_security_mutation_ticket('
                'uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,'
                'text,integer,text,integer,timestamp with time zone)'
              ) IS NOT NULL,
              to_regprocedure(
                'a1_project_identity_security_processor_state(uuid)'
              ) IS NOT NULL,
              to_regprocedure(
                'a1_project_identity_security_mutation_replay(uuid,text,text)'
              ) IS NOT NULL;
            """,
        )
    ) == ["t|t|t"]


def test_consume_is_exactly_replayable_and_writes_complete_side_effects(
    recovery_database: tuple[str, str, str],
) -> None:
    database, runtime_login, issuer_login = recovery_database
    account = _seed_enabled_account(database, "consume")
    new_batch_digest = _digest("consume:new-batch")
    ticket, _, _, _ = _issue_ticket(
        database,
        issuer_login,
        account,
        "mfa_recovery_consume",
        "consume",
        new_recovery_batch_digest=new_batch_digest,
        new_recovery_code_count=account.recovery_code_count - 1,
    )
    idempotency_key = "mfa-recovery-consume:stable-retry"
    request_fingerprint = _digest("consume:public-request")

    first_result = _json_result(
        _execute(
            database,
            runtime_login,
            account.principal_id,
            ticket,
            idempotency_key,
            request_fingerprint,
        )
    )
    assert first_result == {
        "two_factor_status": "enabled",
        "recovery_codes_remaining": account.recovery_code_count - 1,
        "security_version": account.security_version + 1,
        "sessions_revoked": 2,
        "reauthentication_required": True,
    }

    _psql(
        database,
        "UPDATE identity_security_mutation_tickets "
        "SET expires_at=clock_timestamp()-interval '1 second' "
        f"WHERE ticket_digest='{ticket}';",
        tuples=False,
    )
    replay_result = _json_result(
        _execute(
            database,
            runtime_login,
            account.principal_id,
            ticket,
            idempotency_key,
            request_fingerprint,
        )
    )
    assert replay_result == first_result

    conflict = _execute(
        database,
        runtime_login,
        account.principal_id,
        ticket,
        idempotency_key,
        _digest("consume:different-public-request"),
        check=False,
    )
    assert conflict.returncode != 0
    assert "identity_security_idempotency_conflict" in conflict.stderr

    state = _rows(
        _psql(
            database,
            f"""
            SELECT
              two_factor_status,
              recovery_code_batch_digest,
              recovery_codes_remaining,
              security_version,
              (SELECT count(*) FROM identity_sessions
                WHERE principal_id='{account.principal_id}'
                  AND status='revoked'
                  AND revoke_reason_code='mfa_recovery_consume'),
              (SELECT count(*) FROM identity_audit_events
                WHERE principal_id='{account.principal_id}'
                  AND action='identity.mfa_recovery_consume'
                  AND request_digest='{request_fingerprint}'),
              (SELECT count(*) FROM identity_outbox
                WHERE principal_id='{account.principal_id}'
                  AND event_type='identity.mfa_recovery_consume'),
              (SELECT count(*) FROM identity_security_mutation_idempotency
                WHERE principal_id='{account.principal_id}'
                  AND operation='mfa_recovery_consume'
                  AND result_json IS NOT NULL
                  AND completed_at IS NOT NULL)
            FROM identity_account_security
            WHERE principal_id='{account.principal_id}';
            """,
        )
    )
    assert state == [
        "enabled|"
        f"{new_batch_digest}|{account.recovery_code_count - 1}|"
        f"{account.security_version + 1}|2|1|1|1"
    ]

    processor_state = _json_result(
        _psql(
            database,
            _runtime_sql(
                runtime_login,
                account.principal_id,
                "SELECT a1_project_identity_security_processor_state("
                f"'{account.principal_id}'::uuid);",
            ),
        )
    )
    assert processor_state == {
        "two_factor_status": "enabled",
        "totp_secret_ref": account.secret_ref,
        "totp_secret_digest": account.secret_digest,
        "recovery_batch_digest": new_batch_digest,
        "recovery_codes_remaining": account.recovery_code_count - 1,
    }

    replay = _json_result(
        _psql(
            database,
            _runtime_sql(
                runtime_login,
                account.principal_id,
                "SELECT a1_project_identity_security_mutation_replay("
                f"'{account.principal_id}'::uuid,"
                "'mfa_recovery_consume',"
                f"'{idempotency_key}');",
            ),
        )
    )
    assert replay["secret_ref"] == account.secret_ref
    assert replay["secret_digest"] == account.secret_digest
    assert replay["expected_recovery_batch_digest"] == (
        account.recovery_batch_digest
    )
    assert replay["expected_recovery_code_count"] == account.recovery_code_count
    assert replay["recovery_batch_digest"] == new_batch_digest
    assert replay["recovery_code_count"] == account.recovery_code_count - 1
    assert replay["result"] == first_result

    assert set(first_result) == {
        "two_factor_status",
        "recovery_codes_remaining",
        "security_version",
        "sessions_revoked",
        "reauthentication_required",
    }
    serialized_public_result = json.dumps(first_result, sort_keys=True).lower()
    for forbidden in (
        "secret_ref",
        "secret_digest",
        "batch_digest",
        "ticket",
        "receipt",
        "processor",
        "handoff",
        "finalize",
        "cleanup",
        "raw_code",
        '"recovery_codes":',
    ):
        assert forbidden not in serialized_public_result


def test_rotate_replaces_the_complete_batch_and_disable_clears_totp_state(
    recovery_database: tuple[str, str, str],
) -> None:
    database, runtime_login, issuer_login = recovery_database

    rotate_account = _seed_enabled_account(database, "rotate")
    rotated_batch = _digest("rotate:new-complete-batch")
    rotate_ticket, _, _, _ = _issue_ticket(
        database,
        issuer_login,
        rotate_account,
        "mfa_recovery_rotate",
        "rotate",
        new_recovery_batch_digest=rotated_batch,
        new_recovery_code_count=12,
    )
    rotate_result = _json_result(
        _execute(
            database,
            runtime_login,
            rotate_account.principal_id,
            rotate_ticket,
            "mfa-recovery-rotate:complete-batch",
            _digest("rotate:public-request"),
        )
    )
    assert rotate_result["two_factor_status"] == "enabled"
    assert rotate_result["recovery_codes_remaining"] == 12
    assert rotate_result["security_version"] == (
        rotate_account.security_version + 1
    )
    assert _rows(
        _psql(
            database,
            "SELECT recovery_code_batch_digest,recovery_codes_remaining,"
            "security_version "
            "FROM identity_account_security "
            f"WHERE principal_id='{rotate_account.principal_id}';",
        )
    ) == [
        f"{rotated_batch}|12|{rotate_account.security_version + 1}"
    ]

    disable_account = _seed_enabled_account(database, "disable")
    disable_ticket, _, _, _ = _issue_ticket(
        database,
        issuer_login,
        disable_account,
        "mfa_disable",
        "disable",
        new_recovery_batch_digest=None,
        new_recovery_code_count=0,
    )
    disable_result = _json_result(
        _execute(
            database,
            runtime_login,
            disable_account.principal_id,
            disable_ticket,
            "mfa-disable:complete-cleanup",
            _digest("disable:public-request"),
        )
    )
    assert disable_result == {
        "two_factor_status": "disabled",
        "recovery_codes_remaining": 0,
        "security_version": disable_account.security_version + 1,
        "sessions_revoked": 2,
        "reauthentication_required": True,
    }
    assert _rows(
        _psql(
            database,
            """
            SELECT
              two_factor_status,
              totp_secret_ref IS NULL,
              totp_secret_digest IS NULL,
              totp_pending_at IS NULL,
              two_factor_enrolled_at IS NULL,
              recovery_code_batch_digest IS NULL,
              recovery_codes_remaining,
              security_version
            FROM identity_account_security
            WHERE principal_id='"""
            + disable_account.principal_id
            + """';
            """,
        )
    ) == [
        "disabled|t|t|t|t|t|0|"
        f"{disable_account.security_version + 1}"
    ]
    assert _rows(
        _psql(
            database,
            "SELECT "
            "(SELECT count(*) FROM identity_audit_events "
            f"WHERE principal_id='{disable_account.principal_id}' "
            "AND action='identity.mfa_disable'),"
            "(SELECT count(*) FROM identity_outbox "
            f"WHERE principal_id='{disable_account.principal_id}' "
            "AND event_type='identity.mfa_disable');",
        )
    ) == ["1|1"]


@pytest.mark.parametrize("stale_field", ["digest", "count"])
def test_stale_expected_recovery_state_is_rejected_without_consumption(
    recovery_database: tuple[str, str, str],
    stale_field: str,
) -> None:
    database, runtime_login, issuer_login = recovery_database
    account = _seed_enabled_account(database, f"stale-{stale_field}")
    ticket, _, _, _ = _issue_ticket(
        database,
        issuer_login,
        account,
        "mfa_recovery_consume",
        f"stale-{stale_field}",
        new_recovery_batch_digest=_digest(f"stale-{stale_field}:new"),
        new_recovery_code_count=account.recovery_code_count - 1,
    )
    if stale_field == "digest":
        _psql(
            database,
            "UPDATE identity_account_security "
            f"SET recovery_code_batch_digest='{_digest('stale:other-batch')}' "
            f"WHERE principal_id='{account.principal_id}';",
            tuples=False,
        )
    else:
        _psql(
            database,
            "UPDATE identity_account_security "
            "SET recovery_codes_remaining=recovery_codes_remaining-1 "
            f"WHERE principal_id='{account.principal_id}';",
            tuples=False,
        )

    rejected = _execute(
        database,
        runtime_login,
        account.principal_id,
        ticket,
        f"mfa-recovery-stale:{stale_field}",
        _digest(f"stale-{stale_field}:request"),
        check=False,
    )
    assert rejected.returncode != 0
    assert "identity_totp_recovery_state_stale" in rejected.stderr
    assert _rows(
        _psql(
            database,
            "SELECT "
            "(SELECT consumed_at IS NULL "
            "FROM identity_security_mutation_tickets "
            f"WHERE ticket_digest='{ticket}'),"
            "(SELECT count(*) FROM identity_security_mutation_idempotency "
            f"WHERE ticket_digest='{ticket}'),"
            "(SELECT count(*) FROM identity_audit_events "
            f"WHERE principal_id='{account.principal_id}' "
            "AND action='identity.mfa_recovery_consume');",
        )
    ) == ["t|0|0"]


def test_wrong_account_cannot_execute_or_consume_a_recovery_ticket(
    recovery_database: tuple[str, str, str],
) -> None:
    database, runtime_login, issuer_login = recovery_database
    owner = _seed_enabled_account(database, "wrong-account-owner")
    foreign = _seed_enabled_account(database, "wrong-account-foreign")
    ticket, _, _, _ = _issue_ticket(
        database,
        issuer_login,
        owner,
        "mfa_recovery_consume",
        "wrong-account",
        new_recovery_batch_digest=_digest("wrong-account:new"),
        new_recovery_code_count=owner.recovery_code_count - 1,
    )
    rejected = _execute(
        database,
        runtime_login,
        foreign.principal_id,
        ticket,
        "mfa-recovery:wrong-account",
        _digest("wrong-account:request"),
        check=False,
    )
    assert rejected.returncode != 0
    assert "identity_security_ticket_scope_rejected" in rejected.stderr
    assert _rows(
        _psql(
            database,
            "SELECT consumed_at IS NULL "
            "FROM identity_security_mutation_tickets "
            f"WHERE ticket_digest='{ticket}';",
        )
    ) == ["t"]


def test_concurrent_consumes_change_recovery_state_exactly_once(
    recovery_database: tuple[str, str, str],
) -> None:
    database, runtime_login, issuer_login = recovery_database
    account = _seed_enabled_account(database, "concurrent-consume")
    tickets = [
        _issue_ticket(
            database,
            issuer_login,
            account,
            "mfa_recovery_consume",
            f"concurrent-{index}",
            new_recovery_batch_digest=_digest(f"concurrent:new:{index}"),
            new_recovery_code_count=account.recovery_code_count - 1,
        )[0]
        for index in range(2)
    ]

    def consume(index: int) -> subprocess.CompletedProcess[str]:
        return _execute(
            database,
            runtime_login,
            account.principal_id,
            tickets[index],
            f"mfa-recovery-concurrent:{index}",
            _digest(f"concurrent:request:{index}"),
            check=False,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(consume, range(2)))
    assert sum(outcome.returncode == 0 for outcome in outcomes) == 1
    rejected = next(outcome for outcome in outcomes if outcome.returncode != 0)
    assert "identity_totp_recovery_state_stale" in rejected.stderr

    state = _rows(
        _psql(
            database,
            "SELECT recovery_codes_remaining,security_version,"
            "(SELECT count(*) FROM identity_audit_events "
            f"WHERE principal_id='{account.principal_id}' "
            "AND action='identity.mfa_recovery_consume'),"
            "(SELECT count(*) FROM identity_outbox "
            f"WHERE principal_id='{account.principal_id}' "
            "AND event_type='identity.mfa_recovery_consume'),"
            "(SELECT count(*) FROM identity_security_mutation_tickets "
            f"WHERE principal_id='{account.principal_id}' "
            "AND operation='mfa_recovery_consume' "
            "AND consumed_at IS NOT NULL) "
            "FROM identity_account_security "
            f"WHERE principal_id='{account.principal_id}';",
        )
    )
    assert state == [
        f"{account.recovery_code_count - 1}|"
        f"{account.security_version + 1}|1|1|1"
    ]


def test_force_rls_and_role_acl_keep_sensitive_state_private(
    recovery_database: tuple[str, str, str],
) -> None:
    database, _, issuer_login = recovery_database
    tables = (
        "identity_account_security",
        "identity_security_receipts",
        "identity_security_mutation_tickets",
        "identity_security_mutation_idempotency",
        "identity_security_ticket_issuance",
    )
    table_values = ",".join(f"('{table}')" for table in tables)
    posture = _rows(
        _psql(
            database,
            f"""
            WITH protected(table_name) AS (
              VALUES {table_values}
            )
            SELECT
              count(*)=5,
              count(*) FILTER (WHERE class.relrowsecurity)=5,
              count(*) FILTER (WHERE class.relforcerowsecurity)=5,
              (
                SELECT count(*)=5
                FROM pg_policies
                WHERE schemaname='public'
                  AND (
                    (tablename='identity_account_security'
                      AND policyname='identity_account_security_self')
                    OR
                    (tablename='identity_security_receipts'
                      AND policyname='identity_security_receipts_self')
                    OR
                    (tablename='identity_security_mutation_tickets'
                      AND policyname='identity_security_mutation_tickets_self')
                    OR
                    (tablename='identity_security_mutation_idempotency'
                      AND policyname=
                        'identity_security_mutation_idempotency_self')
                    OR
                    (tablename='identity_security_ticket_issuance'
                      AND policyname='identity_security_ticket_issuance_self')
                  )
              )
            FROM protected
            JOIN pg_class AS class ON class.relname=protected.table_name
            JOIN pg_namespace AS namespace
              ON namespace.oid=class.relnamespace
             AND namespace.nspname='public';
            """,
        )
    )
    assert posture == ["t|t|t|t"]

    acl = _rows(
        _psql(
            database,
            """
            SELECT
              has_function_privilege(
                'a1_runtime',
                'a1_execute_identity_security_mutation(text,text,text,uuid)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_runtime',
                'a1_project_identity_security_processor_state(uuid)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_runtime',
                'a1_project_identity_security_mutation_replay(uuid,text,text)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_runtime',
                'a1_issue_scoped_identity_security_mutation_ticket('
                'uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,'
                'text,integer,text,integer,timestamp with time zone)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_security_ticket_issuer',
                'a1_issue_scoped_identity_security_mutation_ticket('
                'uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,'
                'text,integer,text,integer,timestamp with time zone)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_security_ticket_issuer',
                'a1_execute_identity_security_mutation(text,text,text,uuid)',
                'EXECUTE'
              ),
              has_function_privilege(
                'a1_security_ticket_issuer',
                'a1_project_identity_security_processor_state(uuid)',
                'EXECUTE'
              ),
              has_function_privilege(
                'public',
                'a1_project_identity_security_processor_state(uuid)',
                'EXECUTE'
              ),
              has_function_privilege(
                'public',
                'a1_mutate_totp_recovery_lifecycle('
                'uuid,text,text,text,text,integer,text,integer,text,text,'
                'uuid,text,timestamp with time zone)',
                'EXECUTE'
              ),
              has_function_privilege(
                'public',
                'a1_issue_identity_security_mutation_ticket('
                'text,text,uuid,uuid,text,text,text,text,text,integer,'
                'text,integer,timestamp with time zone)',
                'EXECUTE'
              );
            """,
        )
    )
    assert acl == ["t|t|t|f|t|f|f|f|f|f"]

    direct_table_access = _rows(
        _psql(
            database,
            f"""
            WITH protected(table_name) AS (
              VALUES {table_values}
            ),
            roles(role_name) AS (
              VALUES
                ('a1_runtime'),
                ('a1_security_ticket_issuer'),
                ('public'),
                ('{issuer_login}')
            )
            SELECT bool_and(
              NOT has_table_privilege(
                role_name,
                'public.'||table_name,
                'SELECT'
              )
              AND NOT has_table_privilege(
                role_name,
                'public.'||table_name,
                'INSERT'
              )
              AND NOT has_table_privilege(
                role_name,
                'public.'||table_name,
                'UPDATE'
              )
              AND NOT has_table_privilege(
                role_name,
                'public.'||table_name,
                'DELETE'
              )
            )
            FROM protected CROSS JOIN roles;
            """,
        )
    )
    assert direct_table_access == ["t"]

    account = _seed_enabled_account(database, "private-acl")
    for role_setup in (
        f'SET SESSION AUTHORIZATION "{issuer_login}"; '
        "SET ROLE a1_security_ticket_issuer;",
        f'SET SESSION AUTHORIZATION "{issuer_login}"; SET ROLE NONE;',
    ):
        rejected = _psql(
            database,
            f"{role_setup} "
            "SELECT a1_project_identity_security_processor_state("
            f"'{account.principal_id}'::uuid);",
            check=False,
        )
        assert rejected.returncode != 0
        assert "permission denied" in rejected.stderr.lower()
