from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "api" / "migrations"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "releasefoundry-oauth-pg-test")
RUNTIME_ROLE = "a1_runtime"


def _digest(value: int) -> str:
    return f"{value:064x}"


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
            r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|DELETE|GRANT)\b", line
        )
    ]


@pytest.fixture
def coordinator_database() -> str:
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

    database = f"a1_oauth_identity_it_{uuid.uuid4().hex[:10]}"
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


def _scope() -> tuple[str, str, str]:
    return str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


def _scope_setup(
    organization: str, workspace: str, project: str, principal: str
) -> str:
    return f"""
      INSERT INTO organizations (id, slug, display_name)
      VALUES ('{organization}', 'org-{organization[:8]}', 'Coordinator Org');
      INSERT INTO workspaces (
        id, organization_id, slug, display_name
      ) VALUES (
        '{workspace}', '{organization}', 'ws-{workspace[:8]}', 'Coordinator WS'
      );
      INSERT INTO projects (
        id, organization_id, workspace_id, slug, display_name
      ) VALUES (
        '{project}', '{organization}', '{workspace}',
        'project-{project[:8]}', 'Coordinator Project'
      );
      INSERT INTO identity_principals (id, status)
      VALUES ('{principal}', 'active');
    """


def _context(organization: str, project: str, principal: str) -> str:
    return f"""
      SET app.a1_organization_id = '{organization}';
      SET app.a1_project_id = '{project}';
      SET app.a1_principal_id = '{principal}';
    """


def _callback(
    organization: str,
    project: str,
    principal: str,
    *,
    provider: str,
    subject: str,
    binding: str,
    opaque_digest: str,
    idempotency: str,
    request: str,
    account_id: str = "account-1",
) -> str:
    return (
        _context(organization, project, principal)
        + f"""
        SELECT operation_id || '|' || credential_id || '|' ||
               connection_id || '|' || token_ref_id || '|' || operation_status
          FROM a1_complete_oauth_identity_callback(
            '{organization}', '{project}', '{principal}', '{provider}',
            'development', '{subject}', '{binding}',
            'vault://oauth/{provider}/{opaque_digest[:12]}', '{opaque_digest}',
            '{account_id}', 'runtime-session-{account_id}', NULL,
            '{idempotency}', '{request}', '{{"source":"integration"}}'::jsonb
          );
        """
    )


def test_callback_is_atomic_and_idempotent(
    coordinator_database: str,
) -> None:
    organization, workspace, project = _scope()
    principal = str(uuid.uuid4())
    _psql(
        coordinator_database,
        _scope_setup(organization, workspace, project, principal),
        tuples=False,
    )
    call = _callback(
        organization,
        project,
        principal,
        provider="github",
        subject=_digest(1),
        binding=_digest(2),
        opaque_digest=_digest(3),
        idempotency=_digest(4),
        request=_digest(5),
    )
    first = _rows(_psql(coordinator_database, call, user=RUNTIME_ROLE))
    second = _rows(_psql(coordinator_database, call, user=RUNTIME_ROLE))

    assert len(first) == 1
    assert second == first
    state = _rows(
        _psql(
            coordinator_database,
            f"""
            SELECT
              (SELECT count(*) FROM identity_credentials
                WHERE principal_id = '{principal}') || '|' ||
              (SELECT count(*) FROM oauth_token_opaque_refs
                WHERE organization_id = '{organization}'
                  AND project_id = '{project}') || '|' ||
              (SELECT count(*) FROM oauth_account_connections
                WHERE organization_id = '{organization}'
                  AND project_id = '{project}') || '|' ||
              (SELECT count(*) FROM oauth_identity_operations
                WHERE organization_id = '{organization}'
                  AND project_id = '{project}') || '|' ||
              (SELECT count(*) FROM identity_outbox
                WHERE organization_id = '{organization}'
                  AND project_id = '{project}'
                  AND event_type = 'identity.oauth.callback_completed');
            """,
        )
    )
    assert state == ["1|1|1|1|1"]


def test_callback_mismatch_and_subject_conflict_roll_back(
    coordinator_database: str,
) -> None:
    organization, workspace, project = _scope()
    first_principal, second_principal = str(uuid.uuid4()), str(uuid.uuid4())
    _psql(
        coordinator_database,
        _scope_setup(organization, workspace, project, first_principal)
        + f"""
        INSERT INTO identity_principals (id, status)
        VALUES ('{second_principal}', 'active');
        """,
        tuples=False,
    )
    first_call = _callback(
        organization,
        project,
        first_principal,
        provider="google",
        subject=_digest(10),
        binding=_digest(11),
        opaque_digest=_digest(12),
        idempotency=_digest(13),
        request=_digest(14),
    )
    _psql(coordinator_database, first_call, user=RUNTIME_ROLE)

    mismatch = first_call.replace(_digest(14), _digest(15))
    rejected = _psql(
        coordinator_database,
        mismatch,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert rejected.returncode != 0
    assert "idempotency request mismatch" in rejected.stderr

    conflict = _callback(
        organization,
        project,
        second_principal,
        provider="google",
        subject=_digest(10),
        binding=_digest(16),
        opaque_digest=_digest(17),
        idempotency=_digest(18),
        request=_digest(19),
        account_id="account-2",
    )
    rejected = _psql(
        coordinator_database,
        conflict,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert rejected.returncode != 0
    assert "already belongs to another principal" in rejected.stderr
    assert _rows(
        _psql(
            coordinator_database,
            f"""
            SELECT
              (SELECT count(*) FROM identity_credentials
                WHERE principal_id = '{second_principal}') || '|' ||
              (SELECT count(*) FROM oauth_token_opaque_refs
                WHERE opaque_ref_digest = '{_digest(17)}') || '|' ||
              (SELECT count(*) FROM oauth_account_connections
                WHERE account_id = 'account-2') || '|' ||
              (SELECT count(*) FROM oauth_identity_operations
                WHERE principal_id = '{second_principal}');
            """,
        )
    ) == ["0|0|0|0"]


def test_disconnect_is_atomic_pending_and_deduplicated(
    coordinator_database: str,
) -> None:
    organization, workspace, project = _scope()
    principal = str(uuid.uuid4())
    _psql(
        coordinator_database,
        _scope_setup(organization, workspace, project, principal),
        tuples=False,
    )
    github = _rows(
        _psql(
            coordinator_database,
            _callback(
                organization,
                project,
                principal,
                provider="github",
                subject=_digest(20),
                binding=_digest(21),
                opaque_digest=_digest(22),
                idempotency=_digest(23),
                request=_digest(24),
            ),
            user=RUNTIME_ROLE,
        )
    )[0].split("|")
    _psql(
        coordinator_database,
        _callback(
            organization,
            project,
            principal,
            provider="google",
            subject=_digest(25),
            binding=_digest(26),
            opaque_digest=_digest(27),
            idempotency=_digest(28),
            request=_digest(29),
            account_id="account-google",
        ),
        user=RUNTIME_ROLE,
    )
    credential_id, connection_id = github[1], github[2]
    disconnect = (
        _context(organization, project, principal)
        + f"""
        SELECT operation_id || '|' || credential_id || '|' ||
               connection_id || '|' || token_ref_id || '|' ||
               outbox_id || '|' || operation_status
          FROM a1_disconnect_oauth_identity_credential(
            '{organization}', '{project}', '{principal}', '{credential_id}',
            '{connection_id}', 'user_requested', '{_digest(30)}', '{_digest(31)}'
          );
        """
    )
    first = _rows(
        _psql(coordinator_database, disconnect, user=RUNTIME_ROLE)
    )
    second = _rows(
        _psql(coordinator_database, disconnect, user=RUNTIME_ROLE)
    )

    assert len(first) == 1
    assert second == first
    state = _rows(
        _psql(
            coordinator_database,
            f"""
            SELECT c.status || '|' || c.login_enabled || '|' ||
                   oc.status || '|' || token.status || '|' ||
                   outbox.status || '|' || outbox.operation_kind || '|' ||
                   (SELECT count(*) FROM oauth_revocation_outbox
                     WHERE token_ref_id = token.id)
              FROM identity_credentials c
              JOIN oauth_account_connections oc ON oc.credential_id = c.id
              JOIN oauth_token_opaque_refs token ON token.id = oc.token_ref_id
              JOIN oauth_revocation_outbox outbox
                ON outbox.token_ref_id = token.id
             WHERE c.id = '{credential_id}';
            """,
        )
    )
    assert state == [
        "revoked|false|revocation_pending|revocation_pending|"
        "pending|provider_revoke_and_cleanup|1"
    ]


def test_last_login_failure_has_no_partial_writes(
    coordinator_database: str,
) -> None:
    organization, workspace, project = _scope()
    principal = str(uuid.uuid4())
    _psql(
        coordinator_database,
        _scope_setup(organization, workspace, project, principal),
        tuples=False,
    )
    result = _rows(
        _psql(
            coordinator_database,
            _callback(
                organization,
                project,
                principal,
                provider="github",
                subject=_digest(40),
                binding=_digest(41),
                opaque_digest=_digest(42),
                idempotency=_digest(43),
                request=_digest(44),
            ),
            user=RUNTIME_ROLE,
        )
    )[0].split("|")
    denied = _psql(
        coordinator_database,
        _context(organization, project, principal)
        + f"""
        SELECT * FROM a1_disconnect_oauth_identity_credential(
          '{organization}', '{project}', '{principal}', '{result[1]}',
          '{result[2]}', 'user_requested', '{_digest(45)}', '{_digest(46)}'
        );
        """,
        user=RUNTIME_ROLE,
        check=False,
    )

    assert denied.returncode != 0
    assert "last active login credential" in denied.stderr
    assert _rows(
        _psql(
            coordinator_database,
            f"""
            SELECT c.status || '|' || oc.status || '|' || token.status || '|' ||
                   (SELECT count(*) FROM oauth_revocation_outbox
                     WHERE token_ref_id = token.id) || '|' ||
                   (SELECT count(*) FROM oauth_identity_operations
                     WHERE operation_kind = 'disconnect'
                       AND principal_id = '{principal}')
              FROM identity_credentials c
              JOIN oauth_account_connections oc ON oc.credential_id = c.id
              JOIN oauth_token_opaque_refs token ON token.id = oc.token_ref_id
             WHERE c.id = '{result[1]}';
            """,
        )
    ) == ["active|active|active|0|0"]


def test_context_and_rls_isolate_operation_rows(
    coordinator_database: str,
) -> None:
    org_one, workspace_one, project_one = _scope()
    org_two, workspace_two, project_two = _scope()
    principal_one, principal_two = str(uuid.uuid4()), str(uuid.uuid4())
    _psql(
        coordinator_database,
        _scope_setup(org_one, workspace_one, project_one, principal_one)
        + _scope_setup(org_two, workspace_two, project_two, principal_two),
        tuples=False,
    )
    _psql(
        coordinator_database,
        _callback(
            org_one,
            project_one,
            principal_one,
            provider="github",
            subject=_digest(50),
            binding=_digest(51),
            opaque_digest=_digest(52),
            idempotency=_digest(53),
            request=_digest(54),
        ),
        user=RUNTIME_ROLE,
    )

    mismatched = _psql(
        coordinator_database,
        _callback(
            org_one,
            project_one,
            principal_two,
            provider="google",
            subject=_digest(55),
            binding=_digest(56),
            opaque_digest=_digest(57),
            idempotency=_digest(58),
            request=_digest(59),
        ).replace(
            _context(org_one, project_one, principal_two),
            _context(org_two, project_two, principal_two),
        ),
        user=RUNTIME_ROLE,
        check=False,
    )
    assert mismatched.returncode != 0
    assert "context mismatch" in mismatched.stderr

    hidden = _rows(
        _psql(
            coordinator_database,
            _context(org_two, project_two, principal_two)
            + "SELECT count(*) FROM oauth_identity_operations;",
            user=RUNTIME_ROLE,
        )
    )
    visible = _rows(
        _psql(
            coordinator_database,
            _context(org_one, project_one, principal_one)
            + "SELECT count(*) FROM oauth_identity_operations;",
            user=RUNTIME_ROLE,
        )
    )
    assert hidden == ["0"]
    assert visible == ["1"]
