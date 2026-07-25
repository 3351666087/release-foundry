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
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "api" / "migrations"
MIGRATION = MIGRATIONS / "030_a1_tenancy_lifecycle.sql"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "ashr-oauth-pg-test")
RUNTIME_ROLE = "a1_runtime"


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
    user: str = "postgres",
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
            r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|DELETE|GRANT|REVOKE|CREATE)\b",
            line,
        )
    ]


def _runtime_sql(statement: str) -> str:
    return f"""
    BEGIN;
    SET LOCAL ROLE {RUNTIME_ROLE};
    {statement}
    COMMIT;
    """


@dataclass(frozen=True)
class TenancyDatabase:
    name: str
    runtime_login: str


@dataclass(frozen=True)
class TenantGraph:
    actor_id: str
    organization_id: str
    project_id: str
    environment_id: str


@pytest.fixture(scope="module")
def tenancy_database() -> TenancyDatabase:
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
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}'
          ) THEN
            CREATE ROLE {RUNTIME_ROLE}
              NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
              NOBYPASSRLS NOINHERIT;
          END IF;
        END
        $$;
        """,
        tuples=False,
    )
    suffix = uuid.uuid4().hex[:12]
    runtime_login = f"a1_tenancy_runtime_{suffix}"
    database = f"a1_tenancy_it_{suffix}"
    _psql(
        "postgres",
        f"""
        CREATE ROLE "{runtime_login}"
          LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
          NOBYPASSRLS NOINHERIT;
        GRANT {RUNTIME_ROLE} TO "{runtime_login}";
        CREATE DATABASE "{database}";
        """,
        tuples=False,
    )
    try:
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            _psql(
                database,
                migration.read_text(encoding="utf-8"),
                tuples=False,
            )
        yield TenancyDatabase(database, runtime_login)
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
            REVOKE {RUNTIME_ROLE} FROM "{runtime_login}";
            DROP ROLE IF EXISTS "{runtime_login}";
            """,
            tuples=False,
            check=False,
        )


def _seed_principal(database: TenancyDatabase, label: str) -> str:
    principal_id = str(uuid.uuid4())
    _psql(
        database.name,
        f"""
        INSERT INTO identity_principals(id,status,metadata)
        VALUES ('{principal_id}','active','{{"label":"{label}"}}'::jsonb);
        """,
        tuples=False,
    )
    return principal_id


def _mutate(
    database: TenancyDatabase,
    *,
    actor_id: str,
    operation: str,
    payload: dict[str, Any],
    idempotency_label: str,
    request_label: str | None = None,
    organization_id: str | None = None,
    project_id: str | None = None,
    environment_id: str | None = None,
    target_principal_id: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    request_label = request_label or (
        f"{operation}:{organization_id}:{project_id}:{environment_id}:"
        f"{target_principal_id}:{json.dumps(payload, sort_keys=True)}"
    )
    statement = f"""
    SELECT jsonb_build_object(
      'result', result_payload,
      'idempotent_replay', idempotent_replay,
      'completed_at', completed_at
    )::text
      FROM a1_tenancy_mutate(
        '{actor_id}'::uuid,
        '{operation}',
        {_sql_literal(organization_id)}::uuid,
        {_sql_literal(project_id)}::uuid,
        {_sql_literal(environment_id)}::uuid,
        {_sql_literal(target_principal_id)}::uuid,
        '{_digest(idempotency_label)}',
        '{_digest(request_label)}',
        'req-{uuid.uuid4().hex}',
        'trace-{uuid.uuid4().hex}',
        {_sql_literal(json.dumps(payload, sort_keys=True))}::jsonb
      );
    """
    return _psql(
        database.name,
        _runtime_sql(statement),
        user=database.runtime_login,
        check=check,
    )


def _mutation_json(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    rows = _rows(result)
    assert len(rows) == 1, (result.stdout, result.stderr)
    return json.loads(rows[0])


def _query_json(
    database: TenancyDatabase,
    *,
    actor_id: str,
    operation: str,
    organization_id: str | None = None,
    project_id: str | None = None,
    check: bool = True,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
    result = _psql(
        database.name,
        _runtime_sql(
            f"""
            SELECT a1_tenancy_query(
              '{actor_id}'::uuid,
              '{operation}',
              {_sql_literal(organization_id)}::uuid,
              {_sql_literal(project_id)}::uuid
            )::text;
            """
        ),
        user=database.runtime_login,
        check=check,
    )
    if not check:
        return result, None
    rows = _rows(result)
    assert len(rows) == 1, (result.stdout, result.stderr)
    return result, json.loads(rows[0])


def _create_graph(database: TenancyDatabase, label: str) -> TenantGraph:
    actor_id = _seed_principal(database, f"{label}:actor")
    organization = _mutation_json(
        _mutate(
            database,
            actor_id=actor_id,
            operation="organization.create",
            payload={
                "slug": f"a1-{label}-{uuid.uuid4().hex[:10]}",
                "display_name": f"A1 {label}",
            },
            idempotency_label=f"{label}:organization",
        )
    )["result"]
    project = _mutation_json(
        _mutate(
            database,
            actor_id=actor_id,
            operation="project.create",
            organization_id=organization["organization_id"],
            payload={
                "slug": f"a1-{label}-project-{uuid.uuid4().hex[:8]}",
                "display_name": f"A1 {label} Project",
            },
            idempotency_label=f"{label}:project",
        )
    )["result"]
    environment = _mutation_json(
        _mutate(
            database,
            actor_id=actor_id,
            operation="environment.create",
            organization_id=organization["organization_id"],
            project_id=project["project_id"],
            payload={"name": f"{label}-dev", "kind": "development"},
            idempotency_label=f"{label}:environment",
        )
    )["result"]
    return TenantGraph(
        actor_id=actor_id,
        organization_id=organization["organization_id"],
        project_id=project["project_id"],
        environment_id=environment["environment_id"],
    )


def _error_text(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout + "\n" + result.stderr).lower()


def test_migration_declares_authoritative_rls_acl_and_locks() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "create table if not exists tenancy_mutation_receipts" in sql
    assert "alter table tenancy_mutation_receipts enable row level security" in sql
    assert "alter table tenancy_mutation_receipts force row level security" in sql
    assert "revoke all on table tenancy_mutation_receipts from public" in sql
    assert "revoke all on table tenancy_mutation_receipts from a1_runtime" in sql
    assert (
        "grant execute on function a1_tenancy_query(uuid, text, uuid, uuid)"
        in sql
    )
    assert "grant execute on function a1_tenancy_mutate(" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "a1-tenancy-project-owner:" in sql
    assert "tenancy_idempotency_conflict" in sql
    assert "tenancy_last_owner" in sql
    assert "a1_identity_write_event(" in sql


def test_runtime_acl_force_rls_and_only_two_public_entrypoints(
    tenancy_database: TenancyDatabase,
) -> None:
    posture = _rows(
        _psql(
            tenancy_database.name,
            f"""
            SELECT
              has_table_privilege(
                '{RUNTIME_ROLE}','tenancy_mutation_receipts','SELECT'
              ),
              has_table_privilege(
                '{RUNTIME_ROLE}','tenancy_mutation_receipts','INSERT'
              ),
              has_table_privilege(
                '{RUNTIME_ROLE}','tenancy_mutation_receipts','UPDATE'
              ),
              has_table_privilege(
                '{RUNTIME_ROLE}','tenancy_mutation_receipts','DELETE'
              ),
              has_function_privilege(
                '{RUNTIME_ROLE}',
                'a1_tenancy_query(uuid,text,uuid,uuid)','EXECUTE'
              ),
              has_function_privilege(
                '{RUNTIME_ROLE}',
                'a1_tenancy_mutate(uuid,text,uuid,uuid,uuid,uuid,text,text,text,text,jsonb)',
                'EXECUTE'
              ),
              has_function_privilege(
                '{RUNTIME_ROLE}','a1_tenancy_actor_active(uuid)','EXECUTE'
              ),
              has_function_privilege(
                'public','a1_tenancy_query(uuid,text,uuid,uuid)','EXECUTE'
              ),
              has_function_privilege(
                'public',
                'a1_tenancy_mutate(uuid,text,uuid,uuid,uuid,uuid,text,text,text,text,jsonb)',
                'EXECUTE'
              ),
              has_table_privilege(
                'public','tenancy_mutation_receipts','SELECT'
              ),
              (
                SELECT relrowsecurity AND relforcerowsecurity
                  FROM pg_class
                 WHERE oid='tenancy_mutation_receipts'::regclass
              ),
              (
                SELECT bool_and(prosecdef)
                  FROM pg_proc
                 WHERE oid IN (
                   'a1_tenancy_query(uuid,text,uuid,uuid)'::regprocedure,
                   'a1_tenancy_mutate(uuid,text,uuid,uuid,uuid,uuid,text,text,text,text,jsonb)'::regprocedure
                 )
              );
            """,
        )
    )
    assert posture == ["f|f|f|f|t|t|f|f|f|f|t|t"]

    direct_read = _psql(
        tenancy_database.name,
        _runtime_sql("SELECT count(*) FROM tenancy_mutation_receipts;"),
        user=tenancy_database.runtime_login,
        check=False,
    )
    assert direct_read.returncode != 0
    assert "permission denied" in _error_text(direct_read)

    direct_helper = _psql(
        tenancy_database.name,
        _runtime_sql(
            "SELECT a1_tenancy_actor_active(gen_random_uuid());"
        ),
        user=tenancy_database.runtime_login,
        check=False,
    )
    assert direct_helper.returncode != 0
    assert "permission denied" in _error_text(direct_helper)


def test_lifecycle_replay_queries_and_a3_safe_results(
    tenancy_database: TenancyDatabase,
) -> None:
    actor_id = _seed_principal(tenancy_database, "replay:actor")
    payload = {
        "slug": f"a1-replay-{uuid.uuid4().hex[:10]}",
        "display_name": "A1 Replay Organization",
    }
    first = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=actor_id,
            operation="organization.create",
            payload=payload,
            idempotency_label="replay:organization",
            request_label="replay:organization:request",
        )
    )
    replay = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=actor_id,
            operation="organization.create",
            payload=payload,
            idempotency_label="replay:organization",
            request_label="replay:organization:request",
        )
    )
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert replay["result"] == first["result"]
    organization_id = first["result"]["organization_id"]

    project = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=actor_id,
            operation="project.create",
            organization_id=organization_id,
            payload={
                "slug": f"a1-replay-project-{uuid.uuid4().hex[:8]}",
                "display_name": "A1 Replay Project",
            },
            idempotency_label="replay:project",
        )
    )["result"]
    project_id = project["project_id"]
    environment = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=actor_id,
            operation="environment.create",
            organization_id=organization_id,
            project_id=project_id,
            payload={"name": "replay-dev", "kind": "development"},
            idempotency_label="replay:environment",
        )
    )["result"]

    archived = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=actor_id,
            operation="project.archive",
            organization_id=organization_id,
            project_id=project_id,
            payload={},
            idempotency_label="replay:archive",
        )
    )["result"]
    assert archived["status"] == "archived"
    assert archived["archived_at"]
    restored = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=actor_id,
            operation="project.restore",
            organization_id=organization_id,
            project_id=project_id,
            payload={},
            idempotency_label="replay:restore",
        )
    )["result"]
    assert restored["status"] == "active"
    assert restored["archived_at"] is None

    disabled = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=actor_id,
            operation="environment.disable",
            organization_id=organization_id,
            project_id=project_id,
            environment_id=environment["environment_id"],
            payload={},
            idempotency_label="replay:disable",
        )
    )["result"]
    assert disabled["status"] == "disabled"
    assert disabled["disabled_at"]
    enabled = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=actor_id,
            operation="environment.enable",
            organization_id=organization_id,
            project_id=project_id,
            environment_id=environment["environment_id"],
            payload={},
            idempotency_label="replay:enable",
        )
    )["result"]
    assert enabled["status"] == "active"
    assert enabled["disabled_at"] is None

    _, organizations = _query_json(
        tenancy_database,
        actor_id=actor_id,
        operation="organization.list",
    )
    _, projects = _query_json(
        tenancy_database,
        actor_id=actor_id,
        operation="project.list",
        organization_id=organization_id,
    )
    _, environments = _query_json(
        tenancy_database,
        actor_id=actor_id,
        operation="environment.list",
        organization_id=organization_id,
        project_id=project_id,
    )
    assert organizations and organizations["count"] == 1
    assert projects and projects["count"] == 1
    assert environments and environments["count"] == 1

    rendered = json.dumps(
        [first["result"], project, environment, archived, restored, disabled, enabled],
        sort_keys=True,
    ).lower()
    for marker in (
        "secret",
        "digest",
        "ticket",
        "oauth",
        "session",
        "cookie",
        "raw_policy",
    ):
        assert marker not in rendered

    counts = _rows(
        _psql(
            tenancy_database.name,
            f"""
            SELECT
              (SELECT count(*) FROM tenancy_mutation_receipts
                WHERE actor_principal_id='{actor_id}'),
              (SELECT count(*) FROM identity_audit_events
                WHERE actor_principal_id='{actor_id}'
                  AND action LIKE 'tenancy.%'),
              (SELECT count(*) FROM identity_outbox
                WHERE principal_id='{actor_id}'
                  AND event_type LIKE 'tenancy.%');
            """,
        )
    )
    assert counts == ["7|7|7"]

    conflict = _mutate(
        tenancy_database,
        actor_id=actor_id,
        operation="organization.create",
        payload=payload,
        idempotency_label="replay:organization",
        request_label="replay:organization:changed",
        check=False,
    )
    assert conflict.returncode != 0
    assert "tenancy_idempotency_conflict" in _error_text(conflict)

    unsafe = _mutate(
        tenancy_database,
        actor_id=actor_id,
        operation="project.update",
        organization_id=organization_id,
        project_id=project_id,
        payload={"display_name": "Unsafe", "secret_ref": "forbidden"},
        idempotency_label="replay:unsafe",
        check=False,
    )
    assert unsafe.returncode != 0
    assert "tenancy_invalid_request" in _error_text(unsafe)


def test_cross_tenant_isolation_and_last_owner_protection(
    tenancy_database: TenancyDatabase,
) -> None:
    first = _create_graph(tenancy_database, "isolation-a")
    second = _create_graph(tenancy_database, "isolation-b")

    cross_query, _ = _query_json(
        tenancy_database,
        actor_id=first.actor_id,
        operation="environment.list",
        organization_id=second.organization_id,
        project_id=second.project_id,
        check=False,
    )
    assert cross_query.returncode != 0
    assert "tenancy_not_found" in _error_text(cross_query)

    cross_mutation = _mutate(
        tenancy_database,
        actor_id=first.actor_id,
        operation="project.update",
        organization_id=second.organization_id,
        project_id=second.project_id,
        payload={"display_name": "Cross tenant rejected"},
        idempotency_label="isolation:cross",
        check=False,
    )
    assert cross_mutation.returncode != 0
    assert "tenancy_not_found" in _error_text(cross_mutation)

    last_revoke = _mutate(
        tenancy_database,
        actor_id=first.actor_id,
        operation="project_membership.revoke",
        organization_id=first.organization_id,
        project_id=first.project_id,
        target_principal_id=first.actor_id,
        payload={},
        idempotency_label="isolation:last-revoke",
        check=False,
    )
    assert last_revoke.returncode != 0
    assert "tenancy_last_owner" in _error_text(last_revoke)

    last_downgrade = _mutate(
        tenancy_database,
        actor_id=first.actor_id,
        operation="project_membership.set",
        organization_id=first.organization_id,
        project_id=first.project_id,
        target_principal_id=first.actor_id,
        payload={"role": "developer"},
        idempotency_label="isolation:last-downgrade",
        check=False,
    )
    assert last_downgrade.returncode != 0
    assert "tenancy_last_owner" in _error_text(last_downgrade)


def test_concurrent_replay_and_owner_mutations_are_exactly_once(
    tenancy_database: TenancyDatabase,
) -> None:
    graph = _create_graph(tenancy_database, "concurrent")
    target_id = _seed_principal(tenancy_database, "concurrent:target")
    _psql(
        tenancy_database.name,
        f"""
        INSERT INTO identity_organization_memberships(
          organization_id,principal_id,role,status,activated_at,metadata
        ) VALUES (
          '{graph.organization_id}','{target_id}','developer','active',
          now(),'{{}}'::jsonb
        );
        """,
        tuples=False,
    )
    set_owner = _mutation_json(
        _mutate(
            tenancy_database,
            actor_id=graph.actor_id,
            operation="project_membership.set",
            organization_id=graph.organization_id,
            project_id=graph.project_id,
            target_principal_id=target_id,
            payload={"role": "owner"},
            idempotency_label="concurrent:set-owner",
        )
    )
    assert set_owner["result"]["role"] == "owner"

    def create_environment(_: int) -> dict[str, Any]:
        return _mutation_json(
            _mutate(
                tenancy_database,
                actor_id=graph.actor_id,
                operation="environment.create",
                organization_id=graph.organization_id,
                project_id=graph.project_id,
                payload={"name": "concurrent-env", "kind": "sandbox"},
                idempotency_label="concurrent:environment:replay",
                request_label="concurrent:environment:request",
            )
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(create_environment, range(12)))
    assert sum(not outcome["idempotent_replay"] for outcome in outcomes) == 1
    assert len({outcome["result"]["environment_id"] for outcome in outcomes}) == 1

    def revoke(target: str) -> subprocess.CompletedProcess[str]:
        return _mutate(
            tenancy_database,
            actor_id=graph.actor_id,
            operation="project_membership.revoke",
            organization_id=graph.organization_id,
            project_id=graph.project_id,
            target_principal_id=target,
            payload={},
            idempotency_label=f"concurrent:revoke:{target}",
            check=False,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        revoke_results = list(pool.map(revoke, [graph.actor_id, target_id]))
    assert sum(result.returncode == 0 for result in revoke_results) == 1
    rejected = next(result for result in revoke_results if result.returncode != 0)
    assert "tenancy_last_owner" in _error_text(rejected)

    owner_count = _rows(
        _psql(
            tenancy_database.name,
            f"""
            SELECT count(*)
              FROM identity_project_memberships
             WHERE organization_id='{graph.organization_id}'
               AND project_id='{graph.project_id}'
               AND status='active'
               AND role='owner';
            """,
        )
    )
    assert owner_count == ["1"]

    environment_id = outcomes[0]["result"]["environment_id"]
    exactly_once = _rows(
        _psql(
            tenancy_database.name,
            f"""
            SELECT
              (SELECT count(*) FROM environments
                WHERE organization_id='{graph.organization_id}'
                  AND project_id='{graph.project_id}'
                  AND id='{environment_id}'),
              (SELECT count(*) FROM tenancy_mutation_receipts
                WHERE actor_principal_id='{graph.actor_id}'
                  AND operation='environment.create'
                  AND resource_id='{environment_id}'),
              (SELECT count(*) FROM identity_audit_events
                WHERE actor_principal_id='{graph.actor_id}'
                  AND action='tenancy.environment.created'
                  AND resource_id='{environment_id}'),
              (SELECT count(*) FROM identity_outbox
                WHERE principal_id='{graph.actor_id}'
                  AND event_type='tenancy.environment.created'
                  AND aggregate_id='{environment_id}');
            """,
        )
    )
    assert exactly_once == ["1|1|1|1"]
