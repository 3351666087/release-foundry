from __future__ import annotations

import hashlib
import os
import re
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


SQL = (Path(__file__).parents[2] / "services/api/migrations/018_a1_password_mfa_lifecycle.sql").read_text(encoding="utf-8").lower()
ROOT = Path(__file__).parents[2]
MIGRATIONS = ROOT / "services/api/migrations"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "ashr-oauth-pg-test")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _psql(database: str, sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-U", "postgres", "-d", database, "-A", "-t", "-F", "|"],
        input=sql, text=True, capture_output=True, check=check,
    )


def _rows(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line.strip() for line in result.stdout.splitlines() if line.strip() and not re.match(
        r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|REVOKE)\b", line)]


@pytest.fixture(scope="module")
def password_mfa_database() -> str:
    running = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        text=True, capture_output=True,
    )
    if running.returncode or running.stdout.strip() != "true":
        pytest.skip(f"PostgreSQL container {CONTAINER!r} is not running")
    _psql("postgres", "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_runtime') "
                       "THEN CREATE ROLE a1_runtime NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; "
                       "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='a1_security_ticket_issuer') "
                       "THEN CREATE ROLE a1_security_ticket_issuer NOLOGIN NOSUPERUSER NOBYPASSRLS; "
                       "END IF; END $$;")
    database = f"a1_password_mfa_it_{uuid.uuid4().hex[:10]}"
    _psql("postgres", f'CREATE DATABASE "{database}";')
    try:
        for migration in sorted(path for path in MIGRATIONS.glob("*.sql") if path.name[:3] <= "018"):
            _psql(database, migration.read_text(encoding="utf-8"))
        yield database
    finally:
        _psql("postgres", f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE);', check=False)


def _seed_principal(database: str) -> str:
    principal = str(uuid.uuid4())
    _psql(database, f"INSERT INTO identity_principals(id,status) VALUES ('{principal}','active'); "
                     f"INSERT INTO identity_account_security(principal_id) VALUES ('{principal}');")
    return principal


def _issue_receipt(database: str, principal: str, purpose: str, label: str, *, minutes: int = 10) -> tuple[str, str]:
    receipt, context = _digest(f"{label}-receipt"), _digest(f"{label}-context")
    _psql(database, f"INSERT INTO identity_security_receipts(receipt_digest,principal_id,purpose,context_digest,expires_at) "
                     f"VALUES ('{receipt}','{principal}','{purpose}','{context}',clock_timestamp()+interval '{minutes} minutes');")
    return receipt, context


def _issue_ticket(
    database: str,
    principal: str,
    purpose: str,
    label: str,
    *,
    secret_ref: str | None = None,
    secret_digest: str | None = None,
    recovery_batch_digest: str | None = None,
    recovery_code_count: int | None = None,
) -> tuple[str, str, str]:
    receipt, context = _issue_receipt(database, principal, purpose, label)
    ticket = _digest(f"{label}-ticket")

    def sql_value(value: str | None) -> str:
        return "NULL" if value is None else f"'{value}'"

    count_value = "NULL" if recovery_code_count is None else str(recovery_code_count)
    result = _psql(
        database,
        "SET ROLE a1_security_ticket_issuer; "
        "SELECT a1_issue_identity_security_mutation_ticket("
        f"'{ticket}','{receipt}','{principal}','{principal}','{purpose}','{context}',"
        f"{sql_value(secret_ref)},{sql_value(secret_digest)},"
        f"{sql_value(recovery_batch_digest)},{count_value},"
        "clock_timestamp()+interval '5 minutes');",
    )
    assert _rows(result) == ["t"]
    return ticket, receipt, context


def test_security_receipts_are_single_use_scoped_and_expiring() -> None:
    assert "identity_security_receipts" in SQL
    assert "consumed_at is null" in SQL
    assert "expires_at>p_now" in SQL
    assert "principal_id=p_principal_id" in SQL
    assert "context_digest=p_context_digest" in SQL
    assert "for update" in SQL


def test_password_mutation_is_stateful_and_revokes_sessions() -> None:
    body = SQL.split("create or replace function a1_mutate_account_password", 1)[1]
    assert "password_already_enrolled" in body
    assert "password_not_enrolled" in body
    assert "a1_consume_identity_security_receipt" in body
    assert "security_version=identity_account_security.security_version+1" in body
    assert "update identity_sessions set status='revoked'" in body
    assert "reauthentication_required" in body


def test_totp_requires_confirmation_and_never_projects_secret_material() -> None:
    assert "two_factor_status='pending'" in SQL
    assert "totp_pending_at>p_now-interval '15 minutes'" in SQL
    assert "recovery_codes_remaining" in SQL
    projection = SQL.split("create or replace function a1_project_account_security", 1)[1]
    projection = projection.split("revoke all", 1)[0]
    for forbidden in ("totp_secret_ref", "totp_secret_digest", "recovery_code_batch_digest"):
        assert forbidden not in projection
    assert "two_factor_recommended',true" in projection
    begin = SQL.split("create or replace function a1_begin_totp_enrollment", 1)[1]
    confirm = SQL.split("create or replace function a1_confirm_totp_enrollment", 1)[1]
    assert "mfa_already_enabled" in begin
    assert "'security_version',v_version" in begin
    assert "'security_version',v_version" in confirm


def test_tables_are_rls_forced_and_public_access_is_revoked() -> None:
    for table in (
        "identity_security_receipts",
        "identity_security_mutation_tickets",
        "identity_security_mutation_idempotency",
    ):
        assert f"alter table {table} enable row level security" in SQL
        assert f"alter table {table} force row level security" in SQL
    revoke = SQL.split("revoke all on identity_security_receipts", 1)[1].split("from public", 1)[0]
    assert "identity_security_mutation_tickets" in revoke
    assert "identity_security_mutation_idempotency" in revoke


def test_trusted_ticket_and_idempotency_authority_is_database_owned() -> None:
    assert "create table if not exists identity_security_mutation_tickets" in SQL
    assert "step_up_receipt_digest text not null" in SQL
    assert "actor_principal_id uuid not null" in SQL
    assert "create table if not exists identity_security_mutation_idempotency" in SQL
    assert "primary key (principal_id,operation,idempotency_key)" in SQL
    assert "request_fingerprint text not null" in SQL
    assert "identity_security_mutation_tickets_receipt_uidx" in SQL
    issue = SQL.split("create or replace function a1_issue_identity_security_mutation_ticket", 1)[1]
    assert "v_now constant timestamptz := clock_timestamp()" in issue
    assert "identity_security_ticket_issuance_conflict" in issue
    assert "identity_security_receipt_ticket_conflict" in issue
    execute = SQL.split("create or replace function a1_execute_identity_security_mutation", 1)[1]
    assert "v_now constant timestamptz := clock_timestamp()" in execute
    assert "for update" in execute
    assert "on conflict (principal_id,operation,idempotency_key) do nothing" in execute
    assert "identity_security_idempotency_conflict" in execute
    assert "if v_idempotency.result_json is not null then" in execute
    assert "update identity_security_mutation_tickets set consumed_at=v_now" in execute
    assert "set result_json=v_result,completed_at=v_now" in execute


def test_runtime_role_is_granted_only_safe_security_entrypoints() -> None:
    assert "if exists (select 1 from pg_roles where rolname = 'a1_runtime')" in SQL
    for function in (
        "a1_execute_identity_security_mutation",
        "a1_resolve_identity_security_mutation_ticket",
        "a1_project_account_security",
    ):
        assert f"grant execute on function {function}" in SQL
    for internal in (
        "a1_consume_identity_security_receipt",
        "a1_mutate_account_password",
        "a1_begin_totp_enrollment",
        "a1_confirm_totp_enrollment",
    ):
        assert f"grant execute on function {internal}" not in SQL
    assert "from a1_runtime" in SQL
    assert "to a1_security_ticket_issuer" in SQL


def test_registration_and_login_functions_are_not_modified_by_security_migration() -> None:
    assert "a1_register_identity_lifecycle_credential" not in SQL
    assert "a1_authenticate_identity_lifecycle_credential" not in SQL


def test_migration_replaces_v016_constraints_and_disables_legacy_toggle() -> None:
    assert SQL.index("drop constraint if exists identity_two_factor_posture_check") < SQL.index(
        "add constraint identity_totp_posture_check")
    assert "two_factor_legacy_mutation_disabled" in SQL


def test_password_lifecycle_receipts_and_session_revocation(password_mfa_database: str) -> None:
    database, principal = password_mfa_database, _seed_principal(password_mfa_database)
    wrong_receipt, wrong_context = _issue_receipt(database, principal, "password_enroll", "wrong")
    rejected = _psql(database, f"SELECT a1_consume_identity_security_receipt('{wrong_receipt}','{principal}',"
                     f"'password_change','{wrong_context}',clock_timestamp());")
    assert _rows(rejected) == ["f"]
    assert _rows(_psql(database, f"SELECT consumed_at IS NULL FROM identity_security_receipts WHERE receipt_digest='{wrong_receipt}';")) == ["t"]

    receipt, context = _issue_receipt(database, principal, "password_enroll", "enroll")
    result = _psql(database, f"SELECT a1_mutate_account_password('{principal}','password_enroll','vault://password/initial',"
                    f"'{_digest('fingerprint-1')}','{receipt}','{context}','{principal}',clock_timestamp())->>'password_status';")
    assert _rows(result) == ["set"]
    replay = _psql(database, f"SELECT a1_mutate_account_password('{principal}','password_enroll','vault://password/replay',"
                    f"'{_digest('fingerprint-2')}','{receipt}','{context}','{principal}',clock_timestamp());", check=False)
    assert replay.returncode != 0

    _psql(database, f"INSERT INTO identity_sessions(principal_id,session_digest,rotation_family_digest,expires_at) VALUES "
                     f"('{principal}','{_digest('session')}','{_digest('family')}',clock_timestamp()+interval '1 hour');")
    recovery, recovery_context = _issue_receipt(database, principal, "password_recovery", "recovery")
    _psql(database, f"SELECT a1_mutate_account_password('{principal}','password_recovery','vault://password/recovered',"
                     f"'{_digest('fingerprint-3')}','{recovery}','{recovery_context}','{principal}',clock_timestamp());")
    assert _rows(_psql(database, f"SELECT password_recovery_version, (SELECT count(*) FROM identity_sessions WHERE principal_id='{principal}' AND status='revoked') FROM identity_account_security WHERE principal_id='{principal}';")) == ["1|1"]


def test_totp_two_phase_expiry_projection_and_concurrent_receipt(password_mfa_database: str) -> None:
    database, principal = password_mfa_database, _seed_principal(password_mfa_database)
    enroll, enroll_context = _issue_receipt(database, principal, "mfa_enroll", "mfa-enroll")
    begin = _psql(database, f"SELECT a1_begin_totp_enrollment('{principal}','vault://totp/secret','{_digest('totp-secret')}',"
                   f"'{enroll}','{enroll_context}','{principal}',clock_timestamp())->>'security_version';")
    assert _rows(begin) == ["1"]
    confirm, confirm_context = _issue_receipt(database, principal, "mfa_confirm", "mfa-confirm")
    result = _psql(database, f"SELECT (result->>'two_factor_status')||'|'||(result->>'security_version') "
                    f"FROM (SELECT a1_confirm_totp_enrollment('{principal}','{confirm}','{confirm_context}',"
                    f"'{_digest('recovery-batch')}',10,clock_timestamp()) AS result) confirmed;")
    assert _rows(result) == ["enabled|2"]
    projection = "|".join(_rows(_psql(database, f"SELECT a1_project_account_security('{principal}');")))
    assert '"two_factor_status": "enabled"' in projection
    assert all(secret not in projection for secret in ("vault://", _digest("totp-secret"), _digest("recovery-batch")))

    expired_principal = _seed_principal(database)
    expired, expired_context = _issue_receipt(database, expired_principal, "mfa_enroll", "expired-enroll")
    _psql(database, f"SELECT a1_begin_totp_enrollment('{expired_principal}','vault://totp/expired','{_digest('expired-secret')}',"
                     f"'{expired}','{expired_context}','{expired_principal}',clock_timestamp()-interval '20 minutes');")
    expired_confirm, expired_confirm_context = _issue_receipt(database, expired_principal, "mfa_confirm", "expired-confirm")
    rejected = _psql(database, f"SELECT a1_confirm_totp_enrollment('{expired_principal}','{expired_confirm}','{expired_confirm_context}',"
                     f"'{_digest('expired-batch')}',10,clock_timestamp());", check=False)
    assert rejected.returncode != 0 and "mfa_enrollment_unavailable" in rejected.stderr

    concurrent_principal = _seed_principal(database)
    receipt, context = _issue_receipt(database, concurrent_principal, "password_enroll", "concurrent")
    statement = (f"SELECT a1_consume_identity_security_receipt('{receipt}','{concurrent_principal}',"
                 f"'password_enroll','{context}',clock_timestamp());")
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: _rows(_psql(database, statement))[0], range(16)))
    assert outcomes.count("t") == 1 and outcomes.count("f") == 15


def test_enabled_totp_cannot_be_downgraded_by_reenrollment(password_mfa_database: str) -> None:
    database, principal = password_mfa_database, _seed_principal(password_mfa_database)
    enroll, enroll_context = _issue_receipt(database, principal, "mfa_enroll", "reenroll-first")
    _psql(database, f"SELECT a1_begin_totp_enrollment('{principal}','vault://totp/original',"
                     f"'{_digest('original-secret')}','{enroll}','{enroll_context}','{principal}',"
                     "clock_timestamp());")
    confirm, confirm_context = _issue_receipt(database, principal, "mfa_confirm", "reenroll-confirm")
    _psql(database, f"SELECT a1_confirm_totp_enrollment('{principal}','{confirm}','{confirm_context}',"
                     f"'{_digest('original-recovery')}',10,clock_timestamp());")
    reenroll, reenroll_context = _issue_receipt(database, principal, "mfa_enroll", "reenroll-attempt")
    rejected = _psql(
        database,
        f"SELECT a1_begin_totp_enrollment('{principal}','vault://totp/replacement',"
        f"'{_digest('replacement-secret')}','{reenroll}','{reenroll_context}','{principal}',"
        "clock_timestamp());",
        check=False,
    )
    assert rejected.returncode != 0 and "mfa_already_enabled" in rejected.stderr
    state = _psql(
        database,
        "SELECT two_factor_status,totp_secret_ref,totp_secret_digest,"
        "recovery_code_batch_digest,recovery_codes_remaining,"
        "two_factor_enrolled_at IS NOT NULL,security_version,"
        f"(SELECT consumed_at IS NULL FROM identity_security_receipts WHERE receipt_digest='{reenroll}') "
        f"FROM identity_account_security WHERE principal_id='{principal}';",
    )
    assert _rows(state) == [
        f"enabled|vault://totp/original|{_digest('original-secret')}|"
        f"{_digest('original-recovery')}|10|t|2|t"
    ]


def test_runtime_grants_hide_secret_tables_and_internal_functions(password_mfa_database: str) -> None:
    database = password_mfa_database
    privilege_sql = """
    SELECT
      has_function_privilege('a1_runtime',
        'a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamptz)',
        'EXECUTE'),
      has_function_privilege('a1_security_ticket_issuer',
        'a1_issue_identity_security_mutation_ticket(text,text,uuid,uuid,text,text,text,text,text,integer,timestamptz)',
        'EXECUTE'),
      has_function_privilege('a1_runtime',
        'a1_execute_identity_security_mutation(text,text,text)',
        'EXECUTE'),
      has_function_privilege('a1_runtime',
        'a1_resolve_identity_security_mutation_ticket(text,text,text,timestamptz)',
        'EXECUTE'),
      has_function_privilege('a1_runtime','a1_project_account_security(uuid)','EXECUTE'),
      has_function_privilege('a1_runtime',
        'a1_mutate_account_password(uuid,text,text,text,text,text,uuid,timestamptz)',
        'EXECUTE'),
      has_function_privilege('a1_runtime',
        'a1_begin_totp_enrollment(uuid,text,text,text,text,uuid,timestamptz)',
        'EXECUTE'),
      has_table_privilege('a1_runtime','identity_security_mutation_tickets','SELECT'),
      has_table_privilege('a1_runtime','identity_security_mutation_idempotency','SELECT'),
      has_table_privilege('a1_runtime','identity_account_security','SELECT');
    """
    assert _rows(_psql(database, privilege_sql)) == ["f|t|t|t|t|f|f|f|f|f"]


def test_runtime_resolves_only_public_ticket_envelope(password_mfa_database: str) -> None:
    database, principal = password_mfa_database, _seed_principal(password_mfa_database)
    ticket, receipt, _ = _issue_ticket(
        database,
        principal,
        "password_enroll",
        "resolver-envelope",
        secret_ref="vault://password/resolver-envelope",
        secret_digest=_digest("resolver-password-fingerprint"),
    )
    projection = _psql(
        database,
        "SET ROLE a1_runtime; "
        "SELECT a1_resolve_identity_security_mutation_ticket("
        f"'{ticket}','{receipt}','password_enroll',clock_timestamp());",
    )
    public_result = "|".join(_rows(projection))
    assert ticket in public_result
    assert receipt in public_result
    assert str(principal) in public_result
    assert "password_enroll" in public_result
    for forbidden in (
        "vault://password/resolver-envelope",
        _digest("resolver-password-fingerprint"),
        "secret_ref",
        "secret_digest",
        "context_digest",
        "recovery_batch_digest",
    ):
        assert forbidden not in public_result


def test_ticket_issuance_is_idempotent_and_reserves_receipt(
    password_mfa_database: str,
) -> None:
    database, principal = password_mfa_database, _seed_principal(password_mfa_database)
    receipt, context = _issue_receipt(database, principal, "password_enroll", "issue-idempotent")
    ticket = _digest("issue-idempotent-ticket")
    secret = _digest("issue-idempotent-secret")
    expires_at = _rows(_psql(
        database,
        f"SELECT expires_at-interval '1 minute' FROM identity_security_receipts "
        f"WHERE receipt_digest='{receipt}';",
    ))[0]

    def statement(ticket_digest: str, secret_digest: str) -> str:
        return (
            "SET ROLE a1_security_ticket_issuer; "
            "SELECT a1_issue_identity_security_mutation_ticket("
            f"'{ticket_digest}','{receipt}','{principal}','{principal}',"
            f"'password_enroll','{context}','vault://password/issue-idempotent',"
            f"'{secret_digest}',NULL,NULL,"
            f"'{expires_at}'::timestamptz);"
        )

    assert _rows(_psql(database, statement(ticket, secret))) == ["t"]
    assert _rows(_psql(database, statement(ticket, secret))) == ["t"]

    changed = _psql(database, statement(ticket, _digest("changed-secret")), check=False)
    assert changed.returncode != 0
    assert "identity_security_ticket_issuance_conflict" in changed.stderr

    other = _psql(database, statement(_digest("other-ticket"), secret), check=False)
    assert other.returncode != 0
    assert "identity_security_receipt_ticket_conflict" in other.stderr
    assert _rows(_psql(
        database,
        f"SELECT count(*) FROM identity_security_mutation_tickets "
        f"WHERE step_up_receipt_digest='{receipt}';",
    )) == ["1"]


def test_concurrent_ticket_issuance_allows_only_one_ticket_per_receipt(
    password_mfa_database: str,
) -> None:
    database, principal = password_mfa_database, _seed_principal(password_mfa_database)
    receipt, context = _issue_receipt(database, principal, "password_enroll", "issue-concurrent")
    secret = _digest("issue-concurrent-secret")
    expires_at = _rows(_psql(
        database,
        f"SELECT expires_at-interval '1 minute' FROM identity_security_receipts "
        f"WHERE receipt_digest='{receipt}';",
    ))[0]

    def issue(label: str) -> subprocess.CompletedProcess[str]:
        ticket = _digest(f"issue-concurrent-{label}")
        return _psql(
            database,
            "SET ROLE a1_security_ticket_issuer; "
            "SELECT a1_issue_identity_security_mutation_ticket("
            f"'{ticket}','{receipt}','{principal}','{principal}',"
            f"'password_enroll','{context}','vault://password/issue-concurrent',"
            f"'{secret}',NULL,NULL,"
            f"'{expires_at}'::timestamptz);",
            check=False,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue, ("one", "two")))
    assert sum(result.returncode == 0 for result in results) == 1
    rejected = next(result for result in results if result.returncode != 0)
    assert "identity_security_receipt_ticket_conflict" in rejected.stderr


def test_database_clock_cannot_be_forged_for_ticket_expiry(
    password_mfa_database: str,
) -> None:
    database, principal = password_mfa_database, _seed_principal(password_mfa_database)
    receipt, context = _issue_receipt(
        database, principal, "password_enroll", "clock-expired-receipt", minutes=-1,
    )
    rejected_issue = _psql(
        database,
        "SET ROLE a1_security_ticket_issuer; "
        "SELECT a1_issue_identity_security_mutation_ticket("
        f"'{_digest('clock-expired-ticket')}','{receipt}','{principal}','{principal}',"
        f"'password_enroll','{context}','vault://password/clock-expired',"
        f"'{_digest('clock-expired-secret')}',NULL,NULL,"
        "clock_timestamp()+interval '5 minutes');",
        check=False,
    )
    assert rejected_issue.returncode != 0
    assert "identity_security_ticket_receipt_rejected" in rejected_issue.stderr

    ticket, _, _ = _issue_ticket(
        database,
        principal,
        "password_enroll",
        "clock-execute",
        secret_ref="vault://password/clock-execute",
        secret_digest=_digest("clock-execute-secret"),
    )
    _psql(
        database,
        f"UPDATE identity_security_mutation_tickets "
        f"SET expires_at=clock_timestamp()-interval '1 second' WHERE ticket_digest='{ticket}';",
    )
    rejected_execute = _psql(
        database,
        "SET ROLE a1_runtime; "
        "SELECT a1_execute_identity_security_mutation("
        f"'{ticket}','clock:expired:retry','{_digest('clock-execute-request')}');",
        check=False,
    )
    assert rejected_execute.returncode != 0
    assert "identity_security_ticket_expired_or_consumed" in rejected_execute.stderr


def test_durable_idempotency_retry_conflict_and_concurrency_exactly_once(
    password_mfa_database: str,
) -> None:
    database, principal = password_mfa_database, _seed_principal(password_mfa_database)
    ticket, _, _ = _issue_ticket(
        database,
        principal,
        "password_enroll",
        "durable-idempotency",
        secret_ref="vault://password/durable",
        secret_digest=_digest("durable-password-fingerprint"),
    )
    fingerprint = _digest("durable-public-request")
    idempotency_key = "password:durable:retry-1"
    statement = (
        "SET ROLE a1_runtime; "
        "SELECT a1_execute_identity_security_mutation("
        f"'{ticket}','{idempotency_key}','{fingerprint}');"
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: "|".join(_rows(_psql(database, statement))), range(16)))
    assert len(set(outcomes)) == 1
    assert '"password_status": "set"' in outcomes[0]
    assert '"security_version": 1' in outcomes[0]

    _psql(
        database,
        f"UPDATE identity_security_mutation_tickets "
        f"SET expires_at=clock_timestamp()-interval '1 second' WHERE ticket_digest='{ticket}';",
    )
    replay_after_expiry = _psql(
        database,
        "SET ROLE a1_runtime; "
        "SELECT a1_execute_identity_security_mutation("
        f"'{ticket}','{idempotency_key}','{fingerprint}');",
    )
    assert "|".join(_rows(replay_after_expiry)) == outcomes[0]

    conflict = _psql(
        database,
        "SET ROLE a1_runtime; "
        "SELECT a1_execute_identity_security_mutation("
        f"'{ticket}','{idempotency_key}','{_digest('different-request')}');",
        check=False,
    )
    assert conflict.returncode != 0
    assert "identity_security_idempotency_conflict" in conflict.stderr

    state = _psql(
        database,
        "SELECT s.security_version,"
        "(SELECT count(*) FROM identity_security_mutation_idempotency i "
        f" WHERE i.principal_id='{principal}' AND i.operation='password_enroll'),"
        "(SELECT count(*) FROM identity_security_mutation_tickets t "
        f" WHERE t.principal_id='{principal}' AND t.consumed_at IS NOT NULL),"
        "(SELECT count(*) FROM identity_audit_events e "
        f" WHERE e.principal_id='{principal}' AND e.action='identity.password_enroll') "
        f"FROM identity_account_security s WHERE s.principal_id='{principal}';",
    )
    assert _rows(state) == ["1|1|1|1"]
