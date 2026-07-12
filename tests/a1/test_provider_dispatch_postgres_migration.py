from __future__ import annotations

import os
import re
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "019_a1_provider_dispatch_coordination.sql"
)
CONTAINER = os.environ.get(
    "A1_PROVIDER_DISPATCH_POSTGRES_CONTAINER",
    "ashr-a1-provider-dispatch-pg",
)
RUNTIME_ROLE = "a1_provider_dispatch_runtime"


def _normalized_sql() -> str:
    return re.sub(
        r"\s+",
        " ",
        MIGRATION.read_text(encoding="utf-8"),
    ).strip().lower()


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
        "ashr",
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
            r"^(BEGIN|COMMIT|SET|RESET|CREATE|ALTER|DROP|GRANT|INSERT)\b",
            line,
        )
    ]


def _require_postgres() -> None:
    state = _docker(
        "inspect",
        "-f",
        "{{.State.Running}}",
        CONTAINER,
        check=False,
    )
    if state.returncode != 0 or state.stdout.strip() != "true":
        pytest.skip(f"PostgreSQL container {CONTAINER!r} is not running")


def _create_database(prefix: str) -> str:
    database = f"{prefix}_{uuid.uuid4().hex[:10]}"
    _psql("postgres", f'CREATE DATABASE "{database}";', tuples=False)
    return database


def _drop_database(database: str) -> None:
    _psql(
        "postgres",
        f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE);',
        tuples=False,
        check=False,
    )


def _create_prerequisites(database: str) -> None:
    _psql(
        database,
        """
        CREATE TABLE ashr_tenants (
          tenant_id TEXT PRIMARY KEY
        );
        CREATE TABLE ashr_projects (
          tenant_id TEXT NOT NULL REFERENCES ashr_tenants(tenant_id)
            ON DELETE CASCADE,
          project_id TEXT NOT NULL,
          PRIMARY KEY (tenant_id, project_id)
        );
        INSERT INTO ashr_tenants(tenant_id)
          VALUES ('org-a'), ('org-b');
        INSERT INTO ashr_projects(tenant_id, project_id)
          VALUES
            ('org-a', 'project-a'),
            ('org-a', 'project-sibling'),
            ('org-b', 'project-b');
        """,
        tuples=False,
    )


def _apply_migration(database: str) -> None:
    _psql(
        database,
        MIGRATION.read_text(encoding="utf-8"),
        tuples=False,
    )


@pytest.fixture
def provider_dispatch_database() -> str:
    _require_postgres()
    database = _create_database("a1_provider_dispatch_migration")
    try:
        _create_prerequisites(database)
        yield database
    finally:
        _drop_database(database)


def test_migration_uses_canonical_a1_context_and_fail_closed_policy() -> None:
    sql = _normalized_sql()

    assert "app.tenant_id" not in sql
    assert "app.project_id" not in sql
    assert sql.count("current_setting('app.a1_organization_id',true)") == 2
    assert sql.count("current_setting('app.a1_project_id',true)") == 2
    assert sql.count(
        "nullif(current_setting('app.a1_organization_id',true),'')"
    ) == 2
    assert sql.count("nullif(current_setting('app.a1_project_id',true),'')") == 2
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert "with check" in sql


def test_fresh_migration_and_second_application_are_idempotent(
    provider_dispatch_database: str,
) -> None:
    _apply_migration(provider_dispatch_database)
    _apply_migration(provider_dispatch_database)

    result = _psql(
        provider_dispatch_database,
        """
        SELECT
          c.relrowsecurity,
          c.relforcerowsecurity,
          count(p.policyname),
          string_agg(p.cmd, ',' ORDER BY p.cmd)
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_policies p
          ON p.schemaname = n.nspname AND p.tablename = c.relname
        WHERE n.nspname = 'public'
          AND c.relname = 'ashr_provider_dispatches'
        GROUP BY c.relrowsecurity, c.relforcerowsecurity;
        """,
    )

    assert _rows(result) == ["t|t|1|ALL"]


def test_upgrade_preserves_rows_and_replaces_legacy_policy(
    provider_dispatch_database: str,
) -> None:
    _apply_migration(provider_dispatch_database)
    _psql(
        provider_dispatch_database,
        """
        INSERT INTO ashr_provider_dispatches (
          tenant_id, project_id, dispatch_id, provider, operation,
          request_fingerprint
        ) VALUES (
          'org-a', 'project-a', 'dispatch-before-upgrade',
          'openai-compatible', 'responses.create',
          repeat('a', 64)
        );
        ALTER TABLE ashr_provider_dispatches DISABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS ashr_provider_dispatch_tenant_policy
          ON ashr_provider_dispatches;
        DROP POLICY IF EXISTS ashr_provider_dispatch_scope_policy
          ON ashr_provider_dispatches;
        CREATE POLICY ashr_provider_dispatch_tenant_policy
          ON ashr_provider_dispatches
          USING (tenant_id = current_setting('app.tenant_id', true))
          WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
        """,
        tuples=False,
    )

    _apply_migration(provider_dispatch_database)

    result = _psql(
        provider_dispatch_database,
        """
        SELECT count(*) FROM ashr_provider_dispatches
          WHERE dispatch_id = 'dispatch-before-upgrade';
        SELECT relrowsecurity::text || '|' || relforcerowsecurity::text
          FROM pg_class WHERE relname = 'ashr_provider_dispatches';
        SELECT
          policyname || '|' ||
          (qual LIKE '%app.a1_organization_id%')::text || '|' ||
          (qual LIKE '%app.a1_project_id%')::text || '|' ||
          (with_check LIKE '%app.a1_organization_id%')::text || '|' ||
          (with_check LIKE '%app.a1_project_id%')::text
        FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'ashr_provider_dispatches'
        ORDER BY policyname;
        """,
    )

    assert _rows(result) == [
        "1",
        "true|true",
        "ashr_provider_dispatch_scope_policy|true|true|true|true",
    ]


def test_restricted_role_is_fail_closed_and_project_isolated(
    provider_dispatch_database: str,
) -> None:
    _apply_migration(provider_dispatch_database)
    role_setup = _psql(
        provider_dispatch_database,
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}'
          ) THEN
            CREATE ROLE {RUNTIME_ROLE}
              NOLOGIN NOSUPERUSER NOBYPASSRLS;
          END IF;
        END $$;
        GRANT {RUNTIME_ROLE} TO CURRENT_USER;
        GRANT USAGE ON SCHEMA public TO {RUNTIME_ROLE};
        GRANT SELECT, INSERT, UPDATE, DELETE
          ON ashr_provider_dispatches TO {RUNTIME_ROLE};
        """,
        tuples=False,
        check=False,
    )
    if role_setup.returncode != 0:
        pytest.skip(
            "restricted-role RLS proof requires CREATE ROLE/GRANT privileges: "
            + role_setup.stderr
        )

    _psql(
        provider_dispatch_database,
        """
        INSERT INTO ashr_provider_dispatches (
          tenant_id, project_id, dispatch_id, provider, operation,
          request_fingerprint
        ) VALUES
          ('org-a', 'project-a', 'dispatch-a', 'provider', 'operation',
           repeat('a', 64)),
          ('org-a', 'project-sibling', 'dispatch-sibling', 'provider',
           'operation', repeat('b', 64)),
          ('org-b', 'project-b', 'dispatch-b', 'provider', 'operation',
           repeat('c', 64));
        """,
        tuples=False,
    )

    missing_context = _psql(
        provider_dispatch_database,
        f"""
        SET ROLE {RUNTIME_ROLE};
        SELECT count(*) FROM ashr_provider_dispatches;
        RESET ROLE;
        """,
    )
    assert _rows(missing_context) == ["0"]

    scoped = _psql(
        provider_dispatch_database,
        f"""
        BEGIN;
        SET LOCAL ROLE {RUNTIME_ROLE};
        SET LOCAL app.a1_organization_id = 'org-a';
        SET LOCAL app.a1_project_id = 'project-a';
        SELECT string_agg(dispatch_id, ',' ORDER BY dispatch_id)
          FROM ashr_provider_dispatches;
        INSERT INTO ashr_provider_dispatches (
          tenant_id, project_id, dispatch_id, provider, operation,
          request_fingerprint
        ) VALUES (
          'org-a', 'project-a', 'dispatch-a-write', 'provider', 'operation',
          repeat('d', 64)
        );
        COMMIT;
        """,
    )
    assert _rows(scoped) == ["dispatch-a"]

    for tenant_id, project_id, dispatch_id in (
        ("org-a", "project-sibling", "dispatch-cross-project"),
        ("org-b", "project-b", "dispatch-cross-organization"),
    ):
        denied = _psql(
            provider_dispatch_database,
            f"""
            BEGIN;
            SET LOCAL ROLE {RUNTIME_ROLE};
            SET LOCAL app.a1_organization_id = 'org-a';
            SET LOCAL app.a1_project_id = 'project-a';
            INSERT INTO ashr_provider_dispatches (
              tenant_id, project_id, dispatch_id, provider, operation,
              request_fingerprint
            ) VALUES (
              '{tenant_id}', '{project_id}', '{dispatch_id}',
              'provider', 'operation', repeat('e', 64)
            );
            COMMIT;
            """,
            check=False,
        )
        assert denied.returncode != 0
        assert "row-level security" in (
            denied.stdout + denied.stderr
        ).lower()
