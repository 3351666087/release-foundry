from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "docs/a1/schemas/a1_control_plane_postgres_migration.sql"


def _dsn() -> str:
    value = os.environ.get("A1_POSTGRES_TEST_DSN", "").strip()
    if not value:
        pytest.skip("set A1_POSTGRES_TEST_DSN to run the account-aware RLS smoke")
    return value


def _psql(dsn: str, sql: str | None = None, *, file: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        os.environ.get("A1_PSQL_BIN", "psql"),
        dsn,
        "-X",
        "-A",
        "-t",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    if file is not None:
        command.extend(["-f", str(file)])
    else:
        command.extend(["-c", sql or ""])
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)


def test_a1_identity_migration_applies_twice_and_enforces_account_aware_rls() -> None:
    dsn = _dsn()
    capability = _psql(
        dsn,
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user;",
    ).stdout.strip()
    if capability != "t":
        pytest.skip("live RLS probe requires a superuser or BYPASSRLS migration connection")

    _psql(dsn, file=MIGRATION)
    _psql(dsn, file=MIGRATION)

    setup = """
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'releasefoundry_identity_rls_probe') THEN
        CREATE ROLE releasefoundry_identity_rls_probe NOLOGIN NOSUPERUSER NOBYPASSRLS;
      END IF;
    END
    $$;
    GRANT USAGE ON SCHEMA public TO releasefoundry_identity_rls_probe;
    GRANT SELECT ON
      releasefoundry_accounts,
      releasefoundry_identity_credentials,
      releasefoundry_identity_challenges,
      releasefoundry_identity_sessions,
      releasefoundry_account_organization_memberships
    TO releasefoundry_identity_rls_probe;

    INSERT INTO releasefoundry_tenants (tenant_id, name)
      VALUES ('tenant_identity_rls_a', 'Identity RLS A'), ('tenant_identity_rls_b', 'Identity RLS B')
      ON CONFLICT (tenant_id) DO NOTHING;
    INSERT INTO releasefoundry_accounts (account_id, primary_email_normalized)
      VALUES
        ('account_identity_rls_a', 'a@example.cn'),
        ('account_identity_rls_b', 'b@example.cn')
      ON CONFLICT (account_id) DO NOTHING;
    INSERT INTO releasefoundry_identity_credentials (
      credential_id, account_id, provider, provider_kind, provider_subject_fingerprint
    ) VALUES (
      'credential_identity_rls_a',
      'account_identity_rls_a',
      'email_magic_link',
      'email',
      repeat('a', 64)
    ) ON CONFLICT (credential_id) DO NOTHING;
    INSERT INTO releasefoundry_account_organization_memberships (account_id, tenant_id, role)
      VALUES
        ('account_identity_rls_a', 'tenant_identity_rls_a', 'owner'),
        ('account_identity_rls_b', 'tenant_identity_rls_b', 'owner')
      ON CONFLICT (account_id, tenant_id) DO NOTHING;
    """
    _psql(dsn, setup)

    probe = """
    SET ROLE releasefoundry_identity_rls_probe;
    SELECT set_config('app.account_id', 'account_identity_rls_a', false);
    SELECT set_config('app.tenant_id', 'tenant_identity_rls_a', false);
    SELECT 'accounts=' || count(*) FROM releasefoundry_accounts;
    SELECT 'memberships=' || count(*) FROM releasefoundry_account_organization_memberships;
    SELECT 'credentials=' || count(*) FROM releasefoundry_identity_credentials;
    SELECT 'sessions=' || count(*) FROM releasefoundry_identity_sessions;
    RESET ROLE;
    """
    output = _psql(dsn, probe).stdout.splitlines()
    assert "accounts=1" in output
    assert "memberships=1" in output
    assert "credentials=0" in output
    assert "sessions=0" in output
