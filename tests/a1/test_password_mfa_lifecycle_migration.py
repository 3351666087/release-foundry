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
    database = f"a1_password_mfa_it_{uuid.uuid4().hex[:10]}"
    _psql("postgres", f'CREATE DATABASE "{database}";')
    try:
        for migration in sorted(MIGRATIONS.glob("*.sql")):
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


def test_tables_are_rls_forced_and_public_access_is_revoked() -> None:
    assert "alter table identity_security_receipts enable row level security" in SQL
    assert "alter table identity_security_receipts force row level security" in SQL
    assert "revoke all on identity_security_receipts from public" in SQL


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
    _psql(database, f"SELECT a1_begin_totp_enrollment('{principal}','vault://totp/secret','{_digest('totp-secret')}',"
                     f"'{enroll}','{enroll_context}','{principal}',clock_timestamp());")
    confirm, confirm_context = _issue_receipt(database, principal, "mfa_confirm", "mfa-confirm")
    result = _psql(database, f"SELECT a1_confirm_totp_enrollment('{principal}','{confirm}','{confirm_context}',"
                    f"'{_digest('recovery-batch')}',10,clock_timestamp())->>'two_factor_status';")
    assert _rows(result) == ["enabled"]
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
