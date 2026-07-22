from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "api" / "migrations"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "ashr-oauth-pg-test")
RUNTIME_ROLE = "a1_runtime"
LEGACY_IDENTITY_MIGRATION_CEILING = "012_a1_identity_verification.sql"
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64
DIGEST_E = "e" * 64
DIGEST_F = "f" * 64


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
        and not re.match(r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|GRANT)\b", line)
    ]


def _wait_for_postgres(timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        ready = _docker(
            "exec",
            CONTAINER,
            "pg_isready",
            "-U",
            "postgres",
            "-d",
            "postgres",
            check=False,
        )
        if ready.returncode == 0:
            probe = _psql("postgres", "SELECT 1;", check=False)
            if probe.returncode == 0 and _rows(probe) == ["1"]:
                return
            last_error = probe.stderr.strip() or probe.stdout.strip()
        else:
            last_error = ready.stderr.strip() or ready.stdout.strip()
        time.sleep(0.25)
    pytest.fail(
        f"PostgreSQL container {CONTAINER!r} did not become SQL-ready within "
        f"{timeout_seconds:.0f}s: {last_error}"
    )


@pytest.fixture
def identity_database() -> str:
    available = _docker(
        "inspect", "-f", "{{.State.Running}}", CONTAINER, check=False
    )
    if available.returncode != 0 or available.stdout.strip() != "true":
        pytest.skip(
            f"disposable PostgreSQL container {CONTAINER!r} is not running"
        )

    _wait_for_postgres()

    role = _psql(
        "postgres",
        (
            "SELECT rolname || '|' || rolsuper || '|' || rolbypassrls "
            f"FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}';"
        ),
    )
    if _rows(role) != [f"{RUNTIME_ROLE}|false|false"]:
        pytest.skip(f"{RUNTIME_ROLE} must exist as NOSUPERUSER NOBYPASSRLS")

    database = f"a1_identity_it_{uuid.uuid4().hex[:12]}"
    _psql("postgres", f'CREATE DATABASE "{database}";', tuples=False)
    try:
        # This suite proves the access-only identity contract that migrations
        # 013+ intentionally supersede. Current refresh-family behavior is
        # exercised against the full migration chain in its dedicated live suite.
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            if migration.name > LEGACY_IDENTITY_MIGRATION_CEILING:
                break
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


def _principal_sql(principal_id: str) -> str:
    return (
        "INSERT INTO identity_principals (id, status) "
        f"VALUES ('{principal_id}', 'active');"
    )


def _credential_sql(
    credential_id: str,
    principal_id: str,
    provider: str,
    subject_digest: str,
    *,
    kind: str = "federated",
) -> str:
    return f"""
        INSERT INTO identity_credentials (
          id, principal_id, provider, provider_environment, credential_kind,
          subject_digest, status, login_enabled, verified_at
        ) VALUES (
          '{credential_id}', '{principal_id}', '{provider}', 'development',
          '{kind}', '{subject_digest}', 'active', TRUE, clock_timestamp()
        );
    """


def test_session_authentication_bootstraps_forced_rls_and_fails_closed(
    identity_database: str,
) -> None:
    principal = str(uuid.uuid4())
    credential = str(uuid.uuid4())
    organization = str(uuid.uuid4())
    workspace = str(uuid.uuid4())
    project = str(uuid.uuid4())
    org_membership = str(uuid.uuid4())
    session_digest = DIGEST_A
    setup = (
        _principal_sql(principal)
        + _credential_sql(credential, principal, "github", DIGEST_B)
        + f"""
        INSERT INTO organizations (id, slug, display_name)
        VALUES ('{organization}', 'session-auth-org', 'Session Auth Org');
        INSERT INTO workspaces (id, organization_id, slug, display_name)
        VALUES ('{workspace}', '{organization}', 'session-auth', 'Session Auth');
        INSERT INTO projects (
          id, organization_id, workspace_id, slug, display_name
        ) VALUES (
          '{project}', '{organization}', '{workspace}',
          'session-auth', 'Session Auth'
        );
        INSERT INTO identity_organization_memberships (
          id, organization_id, principal_id, status, activated_at
        ) VALUES (
          '{org_membership}', '{organization}', '{principal}',
          'active', clock_timestamp()
        );
        INSERT INTO identity_project_memberships (
          organization_id, project_id, principal_id,
          organization_membership_id, status, activated_at
        ) VALUES (
          '{organization}', '{project}', '{principal}',
          '{org_membership}', 'active', clock_timestamp()
        );
        """
    )
    _psql(identity_database, setup, tuples=False)
    session = _rows(
        _psql(
            identity_database,
            f"""
            SELECT (a1_issue_identity_session(
              '{principal}', '{credential}', '{session_digest}', '{DIGEST_C}',
              clock_timestamp() + interval '1 hour',
              '{organization}', '{project}'
            )).id;
            """,
            user=RUNTIME_ROLE,
        )
    )[0]

    privileges = _rows(
        _psql(
            identity_database,
            """
            SELECT p.prosecdef || '|' ||
                   (p.proconfig @> ARRAY['search_path=pg_catalog, public']) || '|' ||
                   has_function_privilege(
                     'public',
                     'a1_authenticate_identity_session_digest(text)',
                     'EXECUTE'
                   ) || '|' ||
                   has_function_privilege(
                     'a1_runtime',
                     'a1_authenticate_identity_session_digest(text)',
                     'EXECUTE'
                   )
              FROM pg_proc AS p
             WHERE p.oid =
               'a1_authenticate_identity_session_digest(text)'::regprocedure;
            """,
        )
    )
    assert privileges == ["true|true|false|true"]

    authenticated = _rows(
        _psql(
            identity_database,
            f"""
            SELECT principal_id || '|' || session_id || '|' ||
                   organization_id || '|' || project_id
              FROM a1_authenticate_identity_session_digest('{session_digest}');
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert authenticated == [
        f"{principal}|{session}|{organization}|{project}"
    ]

    invalid_updates = [
        (
            "UPDATE identity_sessions SET status = 'revoked', "
            "revoked_at = clock_timestamp(), revoke_reason_code = 'test' "
            f"WHERE id = '{session}';",
            "UPDATE identity_sessions SET status = 'active', revoked_at = NULL, "
            f"revoke_reason_code = NULL WHERE id = '{session}';",
        ),
        (
            "UPDATE identity_principals SET status = 'suspended', "
            f"suspended_at = clock_timestamp() WHERE id = '{principal}';",
            "UPDATE identity_principals SET status = 'active', "
            f"suspended_at = NULL WHERE id = '{principal}';",
        ),
        (
            "UPDATE identity_credentials SET login_enabled = FALSE "
            f"WHERE id = '{credential}';",
            "UPDATE identity_credentials SET login_enabled = TRUE "
            f"WHERE id = '{credential}';",
        ),
        (
            "UPDATE identity_organization_memberships SET status = 'suspended', "
            f"suspended_at = clock_timestamp() WHERE id = '{org_membership}';",
            "UPDATE identity_organization_memberships SET status = 'active', "
            f"suspended_at = NULL WHERE id = '{org_membership}';",
        ),
        (
            "UPDATE identity_project_memberships SET status = 'revoked', "
            f"revoked_at = clock_timestamp() WHERE project_id = '{project}';",
            "UPDATE identity_project_memberships SET status = 'active', "
            f"revoked_at = NULL WHERE project_id = '{project}';",
        ),
    ]
    for invalidate, restore in invalid_updates:
        _psql(identity_database, invalidate, tuples=False)
        rejected = _rows(
            _psql(
                identity_database,
                f"""
                SELECT count(*)
                  FROM a1_authenticate_identity_session_digest(
                    '{session_digest}'
                  );
                """,
                user=RUNTIME_ROLE,
            )
        )
        assert rejected == ["0"]
        _psql(identity_database, restore, tuples=False)

    malformed = _rows(
        _psql(
            identity_database,
            """
            SELECT count(*)
              FROM a1_authenticate_identity_session_digest('raw-token');
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert malformed == ["0"]


def test_recovery_requires_expected_proof_persists_failures_and_blocks_replay(
    identity_database: str,
) -> None:
    principal = str(uuid.uuid4())
    credential = str(uuid.uuid4())
    challenge = str(uuid.uuid4())
    exhausted_challenge = str(uuid.uuid4())
    expected_proof = DIGEST_B
    context = DIGEST_C
    setup = (
        _principal_sql(principal)
        + _credential_sql(
            credential,
            principal,
            "recovery-code",
            DIGEST_A,
            kind="recovery",
        )
        + f"""
        INSERT INTO identity_recovery_challenges (
          id, principal_id, recovery_credential_id, challenge_digest,
          proof_digest, expires_at, request_context_digest
        ) VALUES (
          '{challenge}', '{principal}', '{credential}', '{DIGEST_D}',
          '{expected_proof}', clock_timestamp() + interval '10 minutes',
          '{context}'
        );
        INSERT INTO identity_recovery_challenges (
          id, principal_id, recovery_credential_id, challenge_digest,
          proof_digest, expires_at, request_context_digest, max_attempts
        ) VALUES (
          '{exhausted_challenge}', '{principal}', '{credential}', '{DIGEST_E}',
          '{expected_proof}', clock_timestamp() + interval '10 minutes',
          '{context}', 2
        );
        """
    )
    _psql(identity_database, setup, tuples=False)

    wrong_proof = _psql(
        identity_database,
        f"""
        SELECT (a1_consume_identity_recovery(
          '{DIGEST_D}', '{DIGEST_F}', '{DIGEST_A}', '{DIGEST_B}',
          clock_timestamp() + interval '1 hour', '{context}', '{{}}'::jsonb
        )).id;
        """,
        user=RUNTIME_ROLE,
    )
    assert _rows(wrong_proof) == []
    state = _rows(
        _psql(
            identity_database,
            f"""
            SELECT status || '|' || attempts || '|' ||
                   (SELECT count(*) FROM identity_sessions
                     WHERE principal_id = '{principal}')
              FROM identity_recovery_challenges
             WHERE id = '{challenge}';
            """,
        )
    )
    assert state == ["pending|1|0"]

    wrong_context = _psql(
        identity_database,
        f"""
        SELECT (a1_consume_identity_recovery(
          '{DIGEST_D}', '{expected_proof}', '{DIGEST_A}', '{DIGEST_B}',
          clock_timestamp() + interval '1 hour', '{DIGEST_F}', '{{}}'::jsonb
        )).id;
        """,
        user=RUNTIME_ROLE,
    )
    assert _rows(wrong_context) == []

    success = _rows(
        _psql(
            identity_database,
            f"""
            SELECT (a1_consume_identity_recovery(
              '{DIGEST_D}', '{expected_proof}', '{DIGEST_A}', '{DIGEST_B}',
              clock_timestamp() + interval '1 hour', '{context}', '{{}}'::jsonb
            )).id;
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert len(success) == 1
    consumed = _rows(
        _psql(
            identity_database,
            f"""
            SELECT c.status || '|' || c.attempts || '|' ||
                   s.status || '|' || s.assurance_level || '|' ||
                   (c.proof_digest = '{expected_proof}')
              FROM identity_recovery_challenges c
              JOIN identity_sessions s ON s.id = '{success[0]}'
             WHERE c.id = '{challenge}';
            """,
        )
    )
    assert consumed == ["consumed|3|active|aal2|true"]

    replay = _psql(
        identity_database,
        f"""
        SELECT (a1_consume_identity_recovery(
          '{DIGEST_D}', '{expected_proof}', '{DIGEST_C}', '{DIGEST_D}',
          clock_timestamp() + interval '1 hour', '{context}', '{{}}'::jsonb
        )).id;
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert replay.returncode != 0
    assert "identity recovery challenge unavailable" in replay.stderr

    for session_digest in (DIGEST_C, DIGEST_D):
        rejected = _psql(
            identity_database,
            f"""
            SELECT (a1_consume_identity_recovery(
              '{DIGEST_E}', '{DIGEST_F}', '{session_digest}', '{DIGEST_E}',
              clock_timestamp() + interval '1 hour', '{context}', '{{}}'::jsonb
            )).id;
            """,
            user=RUNTIME_ROLE,
        )
        assert _rows(rejected) == []
    exhausted = _rows(
        _psql(
            identity_database,
            f"""
            SELECT status || '|' || attempts
              FROM identity_recovery_challenges
             WHERE id = '{exhausted_challenge}';
            """,
        )
    )
    assert exhausted == ["failed|2"]


def test_unlink_revokes_bound_sessions_and_refuses_last_login(
    identity_database: str,
) -> None:
    principal = str(uuid.uuid4())
    first = str(uuid.uuid4())
    second = str(uuid.uuid4())
    _psql(
        identity_database,
        _principal_sql(principal)
        + _credential_sql(first, principal, "github", DIGEST_A)
        + _credential_sql(second, principal, "google", DIGEST_B),
        tuples=False,
    )
    for credential, session_digest, rotation_digest in (
        (first, DIGEST_C, DIGEST_D),
        (second, DIGEST_E, DIGEST_F),
    ):
        issued = _psql(
            identity_database,
            f"""
            SELECT (a1_issue_identity_session(
              '{principal}', '{credential}', '{session_digest}',
              '{rotation_digest}', clock_timestamp() + interval '1 hour'
            )).id;
            """,
            user=RUNTIME_ROLE,
        )
        assert len(_rows(issued)) == 1

    _psql(
        identity_database,
        f"""
        SELECT (a1_unlink_identity_credential(
          '{principal}', '{first}', 'user_requested'
        )).id;
        """,
        user=RUNTIME_ROLE,
    )
    state = _rows(
        _psql(
            identity_database,
            f"""
            SELECT c.status || '|' || c.login_enabled || '|' ||
                   COALESCE(s.status, 'none') || '|' ||
                   COALESCE(s.revoke_reason_code, 'none')
              FROM identity_credentials c
              LEFT JOIN identity_sessions s ON s.credential_id = c.id
             WHERE c.id = '{first}';
            """,
        )
    )
    assert state == ["revoked|false|revoked|credential_unlinked"]

    last_login = _psql(
        identity_database,
        f"""
        SELECT (a1_unlink_identity_credential(
          '{principal}', '{second}', 'user_requested'
        )).id;
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert last_login.returncode != 0
    assert "cannot unlink the last active login credential" in last_login.stderr
    unchanged = _rows(
        _psql(
            identity_database,
            f"""
            SELECT status || '|' || login_enabled
              FROM identity_credentials WHERE id = '{second}';
            """,
        )
    )
    assert unchanged == ["active|true"]


def test_unverified_credential_cannot_issue_session(
    identity_database: str,
) -> None:
    principal = str(uuid.uuid4())
    credential = str(uuid.uuid4())
    _psql(
        identity_database,
        _principal_sql(principal)
        + f"""
        INSERT INTO identity_credentials (
          id, principal_id, provider, provider_environment, credential_kind,
          subject_digest, status, login_enabled, verified_at
        ) VALUES (
          '{credential}', '{principal}', 'email', 'development', 'email_otp',
          '{DIGEST_A}', 'pending', TRUE, NULL
        );
        """,
        tuples=False,
    )

    denied = _psql(
        identity_database,
        f"""
        SELECT (a1_issue_identity_session(
          '{principal}', '{credential}', '{DIGEST_B}', '{DIGEST_C}',
          clock_timestamp() + interval '1 hour'
        )).id;
        """,
        user=RUNTIME_ROLE,
        check=False,
    )
    assert denied.returncode != 0
    assert "active identity credential not found" in denied.stderr
    assert _rows(
        _psql(
            identity_database,
            f"""
            SELECT count(*) FROM identity_sessions
             WHERE principal_id = '{principal}';
            """,
        )
    ) == ["0"]


def test_same_email_lookup_conflicts_without_merging_principals(
    identity_database: str,
) -> None:
    original, claimant = str(uuid.uuid4()), str(uuid.uuid4())
    _psql(
        identity_database,
        _principal_sql(original) + _principal_sql(claimant),
        tuples=False,
    )
    linked = _rows(
        _psql(
            identity_database,
            f"""
            SELECT link_status FROM a1_link_identity_credential(
              '{original}', 'email', 'development', 'email_otp',
              '{DIGEST_A}'
            );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert linked == ["linked"]

    conflict = _rows(
        _psql(
            identity_database,
            f"""
            SELECT link_status || '|' || (conflict_id IS NOT NULL)
              FROM a1_link_identity_credential(
                '{claimant}', 'email', 'development', 'email_otp',
                '{DIGEST_A}'
              );
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert conflict == ["conflict|true"]
    assert _rows(
        _psql(
            identity_database,
            f"""
            SELECT
              (SELECT principal_id FROM identity_credentials
                WHERE provider = 'email' AND subject_digest = '{DIGEST_A}')
              || '|' ||
              (SELECT status FROM identity_principals WHERE id = '{original}')
              || '|' ||
              (SELECT status FROM identity_principals WHERE id = '{claimant}')
              || '|' ||
              (SELECT count(*) FROM identity_account_merges);
            """,
        )
    ) == [f"{original}|active|active|0"]


def test_cross_tenant_and_project_scope_cannot_issue_session(
    identity_database: str,
) -> None:
    principal = str(uuid.uuid4())
    credential = str(uuid.uuid4())
    organization_one, organization_two = str(uuid.uuid4()), str(uuid.uuid4())
    workspace_one, workspace_two = str(uuid.uuid4()), str(uuid.uuid4())
    project_one, project_two = str(uuid.uuid4()), str(uuid.uuid4())
    membership = str(uuid.uuid4())
    _psql(
        identity_database,
        _principal_sql(principal)
        + _credential_sql(credential, principal, "github", DIGEST_A)
        + f"""
        INSERT INTO organizations (id, slug, display_name) VALUES
          ('{organization_one}', 'scope-org-one', 'Scope Org One'),
          ('{organization_two}', 'scope-org-two', 'Scope Org Two');
        INSERT INTO workspaces (
          id, organization_id, slug, display_name
        ) VALUES
          ('{workspace_one}', '{organization_one}', 'scope-ws-one', 'Scope WS One'),
          ('{workspace_two}', '{organization_two}', 'scope-ws-two', 'Scope WS Two');
        INSERT INTO projects (
          id, organization_id, workspace_id, slug, display_name
        ) VALUES
          ('{project_one}', '{organization_one}', '{workspace_one}',
           'scope-project-one', 'Scope Project One'),
          ('{project_two}', '{organization_two}', '{workspace_two}',
           'scope-project-two', 'Scope Project Two');
        INSERT INTO identity_organization_memberships (
          id, organization_id, principal_id, status, activated_at
        ) VALUES (
          '{membership}', '{organization_one}', '{principal}',
          'active', clock_timestamp()
        );
        INSERT INTO identity_project_memberships (
          organization_id, project_id, principal_id,
          organization_membership_id, status, activated_at
        ) VALUES (
          '{organization_one}', '{project_one}', '{principal}',
          '{membership}', 'active', clock_timestamp()
        );
        """,
        tuples=False,
    )

    cases = (
        (organization_two, project_two, "active organization membership required"),
        (organization_one, project_two, "active project membership required"),
    )
    for index, (organization, project, expected_error) in enumerate(cases, start=1):
        denied = _psql(
            identity_database,
            f"""
            SELECT (a1_issue_identity_session(
              '{principal}', '{credential}', '{index + 10:064x}',
              '{index + 20:064x}', clock_timestamp() + interval '1 hour',
              '{organization}', '{project}'
            )).id;
            """,
            user=RUNTIME_ROLE,
            check=False,
        )
        assert denied.returncode != 0
        assert expected_error in denied.stderr

    assert _rows(
        _psql(
            identity_database,
            f"""
            SELECT count(*) FROM identity_sessions
             WHERE principal_id = '{principal}';
            """,
        )
    ) == ["0"]


def test_merge_transfers_identity_and_memberships_and_revokes_sessions(
    identity_database: str,
) -> None:
    source, target, approver = (str(uuid.uuid4()) for _ in range(3))
    source_credential, target_credential = (str(uuid.uuid4()) for _ in range(2))
    organization, workspace, project = (str(uuid.uuid4()) for _ in range(3))
    organization_membership = str(uuid.uuid4())
    merge_id = str(uuid.uuid4())
    setup = "".join(_principal_sql(item) for item in (source, target, approver))
    setup += _credential_sql(source_credential, source, "github", DIGEST_A)
    setup += _credential_sql(target_credential, target, "google", DIGEST_B)
    setup += f"""
        INSERT INTO organizations (id, slug, display_name)
        VALUES ('{organization}', 'identity-it-org', 'Identity IT Org');
        INSERT INTO workspaces (
          id, organization_id, slug, display_name
        ) VALUES (
          '{workspace}', '{organization}', 'identity-it-ws', 'Identity IT WS'
        );
        INSERT INTO projects (
          id, organization_id, workspace_id, slug, display_name
        ) VALUES (
          '{project}', '{organization}', '{workspace}',
          'identity-it-project', 'Identity IT Project'
        );
        INSERT INTO identity_organization_memberships (
          id, organization_id, principal_id, role, status, activated_at
        ) VALUES (
          '{organization_membership}', '{organization}', '{source}',
          'owner', 'active', clock_timestamp()
        );
        INSERT INTO identity_project_memberships (
          organization_id, project_id, principal_id,
          organization_membership_id, role, status, activated_at
        ) VALUES (
          '{organization}', '{project}', '{source}',
          '{organization_membership}', 'owner', 'active', clock_timestamp()
        );
        INSERT INTO identity_account_merges (
          id, source_principal_id, target_principal_id,
          requested_by_principal_id, reason_code, proof_digest
        ) VALUES (
          '{merge_id}', '{source}', '{target}', '{source}',
          'verified_duplicate', '{DIGEST_C}'
        );
    """
    _psql(identity_database, setup, tuples=False)
    for principal, credential, session_digest, rotation in (
        (source, source_credential, DIGEST_D, DIGEST_E),
        (target, target_credential, DIGEST_F, DIGEST_A),
    ):
        result = _psql(
            identity_database,
            f"""
            SELECT (a1_issue_identity_session(
              '{principal}', '{credential}', '{session_digest}', '{rotation}',
              clock_timestamp() + interval '1 hour'
            )).id;
            """,
            user=RUNTIME_ROLE,
        )
        assert len(_rows(result)) == 1

    merged = _rows(
        _psql(
            identity_database,
            f"""
            SELECT (a1_merge_identity_accounts(
              '{merge_id}', '{approver}', '{DIGEST_D}', '{DIGEST_E}'
            )).status;
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert merged == ["completed"]
    state = _rows(
        _psql(
            identity_database,
            f"""
            SELECT
              (SELECT status || '|' || merged_into_principal_id
                 FROM identity_principals WHERE id = '{source}') || '|' ||
              (SELECT count(*) FROM identity_credentials
                 WHERE principal_id = '{target}' AND status = 'active') || '|' ||
              (SELECT count(*) FROM identity_sessions
                 WHERE principal_id IN ('{source}', '{target}')
                   AND status = 'revoked'
                   AND credential_id IS NULL
                   AND revoke_reason_code = 'account_merged') || '|' ||
              (SELECT count(*) FROM identity_organization_memberships
                 WHERE organization_id = '{organization}'
                   AND principal_id = '{target}' AND status = 'active') || '|' ||
              (SELECT count(*) FROM identity_project_memberships
                 WHERE project_id = '{project}'
                   AND principal_id = '{target}' AND status = 'active');
            """,
        )
    )
    assert state == [f"merged|{target}|2|2|1|1"]


def test_rls_isolates_principal_tenant_project_and_session_rows(
    identity_database: str,
) -> None:
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    first_credential, second_credential = str(uuid.uuid4()), str(uuid.uuid4())
    organization, workspace, project = (str(uuid.uuid4()) for _ in range(3))
    org_membership = str(uuid.uuid4())
    _psql(
        identity_database,
        _principal_sql(first)
        + _principal_sql(second)
        + _credential_sql(first_credential, first, "github", DIGEST_C)
        + _credential_sql(second_credential, second, "google", DIGEST_D)
        + f"""
        INSERT INTO organizations (id, slug, display_name)
        VALUES ('{organization}', 'rls-org', 'RLS Org');
        INSERT INTO workspaces (id, organization_id, slug, display_name)
        VALUES ('{workspace}', '{organization}', 'rls-ws', 'RLS WS');
        INSERT INTO projects (
          id, organization_id, workspace_id, slug, display_name
        ) VALUES (
          '{project}', '{organization}', '{workspace}', 'rls-project', 'RLS Project'
        );
        INSERT INTO identity_organization_memberships (
          id, organization_id, principal_id, status, activated_at
        ) VALUES (
          '{org_membership}', '{organization}', '{first}',
          'active', clock_timestamp()
        );
        INSERT INTO identity_project_memberships (
          organization_id, project_id, principal_id,
          organization_membership_id, status, activated_at
        ) VALUES (
          '{organization}', '{project}', '{first}', '{org_membership}',
          'active', clock_timestamp()
        );
        GRANT SELECT ON identity_principals, identity_credentials,
          identity_organization_memberships, identity_project_memberships,
          identity_sessions, identity_audit_events, identity_outbox
          TO {RUNTIME_ROLE};
        """,
        tuples=False,
    )
    for principal, credential, session_digest, rotation in (
        (first, first_credential, DIGEST_E, DIGEST_F),
        (second, second_credential, DIGEST_A, DIGEST_B),
    ):
        _psql(
            identity_database,
            f"""
            SELECT (a1_issue_identity_session(
              '{principal}', '{credential}', '{session_digest}', '{rotation}',
              clock_timestamp() + interval '1 hour'
            )).id;
            """,
            user=RUNTIME_ROLE,
        )

    visible = _rows(
        _psql(
            identity_database,
            f"""
            SET app.a1_principal_id = '{first}';
            SET app.a1_organization_id = '{organization}';
            SET app.a1_project_id = '{project}';
            SELECT
              (SELECT count(*) FROM identity_principals) || '|' ||
              (SELECT count(*) FROM identity_credentials) || '|' ||
              (SELECT count(*) FROM identity_organization_memberships) || '|' ||
              (SELECT count(*) FROM identity_project_memberships) || '|' ||
              (SELECT count(*) FROM identity_sessions) || '|' ||
              (SELECT count(*) FROM identity_audit_events) || '|' ||
              (SELECT count(*) FROM identity_outbox);
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert visible == ["1|1|1|1|1|1|1"]


def test_outbox_leases_are_exclusive_reclaimable_and_skip_locked(
    identity_database: str,
) -> None:
    principals = [str(uuid.uuid4()) for _ in range(4)]
    credentials = [str(uuid.uuid4()) for _ in range(4)]
    setup = ""
    for index, (principal, credential) in enumerate(zip(principals, credentials)):
        setup += _principal_sql(principal)
        setup += _credential_sql(
            credential,
            principal,
            "github",
            f"{index + 1:064x}",
        )
    _psql(identity_database, setup, tuples=False)
    for index, (principal, credential) in enumerate(zip(principals, credentials)):
        _psql(
            identity_database,
            f"""
            SELECT (a1_issue_identity_session(
              '{principal}', '{credential}', '{index + 11:064x}',
              '{index + 21:064x}', clock_timestamp() + interval '1 hour'
            )).id;
            """,
            user=RUNTIME_ROLE,
        )

    first_claim = _rows(
        _psql(
            identity_database,
            f"""
            SELECT id FROM a1_claim_identity_outbox('{DIGEST_A}', 1, 30);
            """,
            user=RUNTIME_ROLE,
        )
    )
    second_claim = _rows(
        _psql(
            identity_database,
            f"""
            SELECT id FROM a1_claim_identity_outbox('{DIGEST_B}', 1, 30);
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert len(first_claim) == len(second_claim) == 1
    assert first_claim != second_claim

    _psql(
        identity_database,
        f"""
        UPDATE identity_outbox
           SET lease_expires_at = clock_timestamp() - interval '1 second'
         WHERE id = '{first_claim[0]}';
        """,
        tuples=False,
    )
    reclaimed = _rows(
        _psql(
            identity_database,
            f"""
            SELECT id || '|' || attempts || '|' || lease_owner_digest
              FROM a1_claim_identity_outbox('{DIGEST_C}', 1, 30)
             WHERE id = '{first_claim[0]}';
            """,
            user=RUNTIME_ROLE,
        )
    )
    assert reclaimed == [f"{first_claim[0]}|2|{DIGEST_C}"]

    pending_id = _rows(
        _psql(
            identity_database,
            """
            SELECT id FROM identity_outbox
             WHERE status = 'pending'
             ORDER BY available_at, created_at
             LIMIT 1;
            """,
        )
    )[0]
    locker = subprocess.Popen(
        [
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
            identity_database,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert locker.stdin is not None
    locker.stdin.write(
        "BEGIN;\n"
        f"SELECT id FROM identity_outbox WHERE id = '{pending_id}' FOR UPDATE;\n"
        "SELECT pg_sleep(2);\nCOMMIT;\n"
    )
    locker.stdin.close()
    time.sleep(0.4)
    skipped = _rows(
        _psql(
            identity_database,
            f"""
            SELECT id FROM a1_claim_identity_outbox('{DIGEST_D}', 1, 30);
            """,
            user=RUNTIME_ROLE,
        )
    )
    locker.wait(timeout=5)
    assert len(skipped) == 1
    assert skipped[0] != pending_id
