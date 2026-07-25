from __future__ import annotations

import hashlib
import re
import os
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "012_a1_identity_verification.sql"
)
MIGRATIONS = ROOT / "services" / "api" / "migrations"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "ashr-oauth-pg-test")

TABLES = (
    "identity_verification_cooldowns",
    "identity_verification_challenges",
    "identity_verification_receipts",
    "identity_verification_audit_events",
    "identity_verification_delivery_outbox",
    "identity_verification_abuse_budgets",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql()).lower()


def _table_body(table: str) -> str:
    sql = _normalized()
    start = sql.index(f"create table if not exists {table} (")
    return sql[start : sql.index(");", start)]


def _function_body(function: str, next_marker: str) -> str:
    sql = _normalized()
    start = sql.index(f"create or replace function {function}(")
    return sql[start : sql.index(next_marker, start)]


def _docker(*args: str, input_text: str | None = None, check: bool = True):
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
def verification_database() -> str:
    available = _docker(
        "inspect", "-f", "{{.State.Running}}", CONTAINER, check=False
    )
    if available.returncode != 0 or available.stdout.strip() != "true":
        pytest.skip(f"PostgreSQL container {CONTAINER!r} is not running")

    database = f"a1_verification_it_{uuid.uuid4().hex[:12]}"
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


def test_migration_is_additive_and_follows_session_authentication() -> None:
    assert MIGRATION.is_file()
    assert MIGRATION.name > "011_a1_identity_session_authentication.sql"
    sql = _normalized()
    assert sql.startswith("-- durable, digest-only identity verification")
    assert sql.strip().endswith("commit;")


def test_schema_is_tenant_project_scoped_and_digest_only() -> None:
    sql = _normalized()
    forbidden_columns = {
        "email",
        "email_address",
        "phone",
        "phone_number",
        "mobile",
        "otp",
        "otp_code",
        "code",
        "raw_code",
        "destination",
        "recipient",
        "authorization",
        "authorization_code",
    }

    for table in TABLES:
        body = _table_body(table)
        assert "organization_id uuid not null" in body
        assert "project_id uuid not null" in body
        columns = {
            match.group(1)
            for match in re.finditer(
                r"(?:^|,)\s*([a-z][a-z0-9_]*)\s+[a-z]",
                body,
            )
        }
        assert forbidden_columns.isdisjoint(columns), (table, columns)

    challenge = _table_body("identity_verification_challenges")
    assert "subject_digest text not null" in challenge
    assert "challenge_digest text not null" in challenge
    assert "code_digest text not null" in challenge
    assert "request_context_digest text not null" in challenge
    assert challenge.count("a1_identity_digest_valid(") >= 4
    assert "unique (challenge_digest)" in challenge
    assert (
        "foreign key (organization_id, project_id) "
        "references projects(organization_id, id)"
    ) in challenge
    assert "raw otp values" in sql


def test_challenge_lifecycle_is_bounded_and_single_consume() -> None:
    challenge = _table_body("identity_verification_challenges")
    receipts = _table_body("identity_verification_receipts")

    assert "max_attempts between 1 and 10" in challenge
    assert "attempt_count <= max_attempts" in challenge
    assert "expires_at <= issued_at + interval '15 minutes'" in challenge
    assert "'pending', 'consumed', 'expired', 'locked', 'revoked'" in challenge
    assert "status = 'consumed'" in challenge
    assert "verified_at is not null" in challenge
    assert "consumed_at is not null" in challenge
    assert "unique (challenge_id)" in receipts
    assert "unique (receipt_digest)" in receipts


def test_issue_function_serializes_cooldown_and_revalidates_scope() -> None:
    issue = _function_body(
        "a1_issue_identity_verification_challenge",
        "create or replace function a1_verify_consume_identity_challenge(",
    )

    assert "security definer" in issue
    assert "set search_path = pg_catalog, public" in issue
    assert "a1_identity_verification_assert_scope(" in issue
    assert "pg_advisory_xact_lock(" in issue
    assert "for update" in issue
    assert "cooldown.next_allowed_at > v_now" in issue
    assert "cooldown.blocked_until > v_now" in issue
    assert "p_cooldown_seconds not between 1 and 3600" in issue
    assert "p_expires_at > v_now + interval '15 minutes'" in issue
    assert "status = 'revoked'" in issue
    assert "insert into identity_verification_challenges" in issue
    assert "insert into identity_verification_cooldowns" in issue
    assert "on conflict (" in issue
    assert "'challenge_issued'" in issue
    assert "'issued'" in issue


def test_scoped_principal_challenges_require_active_membership() -> None:
    issue = _function_body(
        "a1_issue_identity_verification_challenge",
        "create or replace function a1_verify_consume_identity_challenge(",
    )

    assert "p_purpose <> 'login' and p_principal_id is null" in issue
    assert "principal.status = 'active'" in issue
    assert "organization_membership.status = 'active'" in issue
    assert "project_membership.status = 'active'" in issue
    assert (
        "project_membership.organization_membership_id = "
        "organization_membership.id"
    ) in issue


def test_verify_consume_is_atomic_locked_and_context_bound() -> None:
    verify = _function_body(
        "a1_verify_consume_identity_challenge",
        "drop trigger if exists identity_verification_receipts_append_only",
    )

    assert "security definer" in verify
    assert "set search_path = pg_catalog, public" in verify
    assert "a1_identity_verification_assert_scope(" in verify
    assert "challenge_digest = p_challenge_digest" in verify
    assert "for update" in verify
    assert "challenge.status <> 'pending'" in verify
    assert "challenge.expires_at <= v_now" in verify
    assert (
        "challenge.request_context_digest <> p_request_context_digest"
        in verify
    )
    assert "digest(challenge.code_digest, 'sha256')" in verify
    assert "digest(p_candidate_code_digest, 'sha256')" in verify
    consume = verify.index("set status = 'consumed'")
    receipt = verify.index("insert into identity_verification_receipts")
    audit = verify.rindex("insert into identity_verification_audit_events")
    assert consume < receipt < audit
    assert "returning id into created_receipt_id" in verify
    assert "update identity_verification_cooldowns as cooldown" in verify
    for scoped_column in (
        "organization_id",
        "project_id",
        "channel",
        "purpose",
        "subject_digest",
    ):
        assert (
            f"cooldown.{scoped_column} = challenge.{scoped_column}"
            in verify
        )


def test_failed_attempts_lock_and_extend_durable_abuse_budget() -> None:
    verify = _function_body(
        "a1_verify_consume_identity_challenge",
        "drop trigger if exists identity_verification_receipts_append_only",
    )

    assert "next_attempt := challenge.attempt_count + 1" in verify
    assert "when next_attempt >= challenge.max_attempts then 'locked'" in verify
    assert "locked_at = case" in verify
    assert "least(3600, 30 * (2 ^ least(next_attempt - 1, 6)))" in verify
    assert (
        "on conflict on constraint identity_verification_cooldowns_pkey"
        in verify
    )
    assert "consecutive_failures = least(" in verify
    assert "blocked_until = case" in verify
    assert "then v_now + interval '1 hour'" in verify
    assert "'attempts_exhausted'" in verify


def test_receipt_proof_is_immutable_and_audit_is_append_only() -> None:
    sql = _normalized()

    assert "identity_verification_receipts_append_only" in sql
    assert (
        "before update or delete on identity_verification_receipts"
        in sql
    )
    assert "identity_verification_audit_append_only" in sql
    assert (
        "before update or delete on identity_verification_audit_events"
        in sql
    )
    assert "a1_identity_verification_receipt_transition" in sql
    assert "old.status <> 'verified'" in sql
    assert "new.status <> 'consumed'" in sql
    assert "old.receipt_digest <> new.receipt_digest" in sql
    assert "execute function a1_identity_reject_append_only_mutation()" in sql
    assert "identity_verification_challenges_no_hard_delete" in sql
    assert "identity_verification_cooldowns_no_hard_delete" in sql
    assert "identity_verification_delivery_no_hard_delete" in sql
    assert "identity_verification_abuse_no_hard_delete" in sql


def test_delivery_outbox_and_five_dimension_budget_are_durable() -> None:
    sql = _normalized()
    outbox = _table_body("identity_verification_delivery_outbox")
    budget = _table_body("identity_verification_abuse_budgets")

    for column in (
        "lease_owner",
        "lease_generation",
        "lease_expires_at",
        "attempt_count",
        "next_attempt_at",
    ):
        assert column in outbox
    assert "'dead'" in outbox
    assert "unique (challenge_id)" in outbox
    assert "unique (delivery_digest)" in outbox
    assert (
        "primary key ( organization_id, project_id, channel, purpose, "
        "subject_digest )"
    ) in budget
    assert "insert into identity_verification_delivery_outbox" in sql
    assert "insert into identity_verification_abuse_budgets" in sql


def test_retryable_proof_and_final_mutations_are_atomic() -> None:
    sql = _normalized()
    verify = _function_body(
        "a1_verify_identity_verification_attempt",
        "create or replace function a1_bind_verified_identity_credential(",
    )
    assert "set status = 'verified'" in verify
    assert "'verified', v_now" in verify
    assert "consumed_at" not in verify

    for function, next_marker, mutation in (
        (
            "a1_bind_verified_identity_credential",
            "create or replace function a1_login_with_verified_identity(",
            "insert into identity_credentials",
        ),
        (
            "a1_login_with_verified_identity",
            "create or replace function a1_recover_verified_identity(",
            "insert into identity_sessions",
        ),
        (
            "a1_recover_verified_identity",
            "create or replace function a1_identity_verification_receipt_transition(",
            "insert into identity_sessions",
        ),
    ):
        body = _function_body(function, next_marker)
        assert body.count("for update") >= 2
        assert "from identity_verification_receipts" in body
        assert mutation in body
        assert "set status = 'consumed'" in body
        assert "idempotency_conflict" in body
        assert "when others then" not in body


def test_every_table_has_forced_rls_and_scope_policy() -> None:
    sql = _normalized()

    for table in TABLES:
        assert f"alter table {table} enable row level security" in sql
        assert f"alter table {table} force row level security" in sql
        assert f"on {table} using (" in sql
    assert sql.count("organization_id = a1_current_organization_id()") >= 8
    assert sql.count("project_id = a1_current_project_id()") >= 8
    assert sql.count("principal_id = a1_current_principal_id()") >= 6


def test_runtime_gets_functions_but_no_direct_table_access() -> None:
    sql = _normalized()
    scope = _function_body(
        "a1_identity_verification_assert_scope",
        "create or replace function a1_issue_identity_verification_challenge(",
    )

    assert "a1_assert_role_nobypassrls(session_user)" in scope
    assert "p_organization_id is distinct from a1_current_organization_id()" in scope
    assert "p_project_id is distinct from a1_current_project_id()" in scope
    assert "project.status = 'active'" in scope
    assert "organization.status = 'active'" in scope
    for table in TABLES:
        assert f"revoke all on table {table} from public" in sql
        assert f"revoke all on table {table} from a1_runtime" in sql
    for function in (
        "a1_identity_verification_assert_scope",
        "a1_issue_identity_verification_challenge",
        "a1_verify_consume_identity_challenge",
    ):
        assert f"revoke all on function {function}(" in sql
    assert "grant execute on function a1_issue_identity_verification_challenge(" in sql
    assert "grant execute on function a1_verify_consume_identity_challenge(" in sql
    assert "grant execute on function a1_identity_verification_assert_scope(" not in sql


def test_live_retryable_proof_outbox_budget_and_runtime_boundary(
    verification_database: str,
) -> None:
    organization = str(uuid.uuid4())
    workspace = str(uuid.uuid4())
    project = str(uuid.uuid4())
    principal = str(uuid.uuid4())
    org_membership = str(uuid.uuid4())
    login_credential = str(uuid.uuid4())
    digest_names = (
        "subject", "challenge", "code", "context", "issue_event",
        "receipt", "verify_event", "idempotency", "request",
        "bind_event", "idempotency_competitor", "request_competitor",
        "bind_event_competitor", "login_subject", "session", "rotation",
        "step_up", "ticket", "step_up_competitor", "ticket_competitor",
    )
    digests = {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in digest_names
    }
    setup = f"""
      INSERT INTO organizations (id, slug, display_name)
      VALUES ('{organization}', 'otp-org', 'OTP Org');
      INSERT INTO workspaces (id, organization_id, slug, display_name)
      VALUES ('{workspace}', '{organization}', 'otp', 'OTP');
      INSERT INTO projects (
        id, organization_id, workspace_id, slug, display_name
      ) VALUES (
        '{project}', '{organization}', '{workspace}', 'otp', 'OTP'
      );
      INSERT INTO identity_principals (id, status)
      VALUES ('{principal}', 'active');
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
      INSERT INTO identity_credentials (
        id, principal_id, provider, credential_kind, subject_digest,
        status, login_enabled, verified_at, last_authenticated_at
      ) VALUES (
        '{login_credential}', '{principal}', 'email', 'email_otp',
        '{digests["login_subject"]}', 'active', TRUE,
        clock_timestamp(), clock_timestamp()
      );
      INSERT INTO identity_sessions (
        principal_id, credential_id, organization_id, project_id,
        session_digest, rotation_family_digest, status, assurance_level,
        authenticated_at, expires_at
      ) VALUES (
        '{principal}', '{login_credential}', '{organization}', '{project}',
        '{digests["session"]}', '{digests["rotation"]}', 'active', 'aal1',
        clock_timestamp(), clock_timestamp() + interval '30 minutes'
      );
    """
    _psql(verification_database, setup, tuples=False)

    runtime_scope = (
        f"SET app.a1_organization_id = '{organization}';"
        f"SET app.a1_project_id = '{project}';"
        f"SET app.a1_principal_id = '{principal}';"
    )
    issue = _rows(_psql(
        verification_database,
        runtime_scope + f"""
          SELECT challenge_id, accepted
            FROM a1_issue_identity_verification_challenge_with_delivery(
              '{organization}', '{project}', '{principal}', 'email',
              'credential_binding', '{digests["subject"]}',
              '{digests["challenge"]}', '{digests["code"]}',
              '{digests["context"]}', clock_timestamp() + interval '5 minutes',
              5, 30, '{digests["issue_event"]}',
              'opaque-ref:identity-delivery/{digests["challenge"]}',
              '{{}}'::jsonb
            );
        """,
        user="a1_runtime",
    ))
    assert len(issue) == 1 and issue[0].endswith("|t")
    challenge_id = issue[0].split("|")[0]

    durable = _rows(_psql(
        verification_database,
        f"""
          SELECT
            (SELECT count(*) FROM identity_verification_delivery_outbox
              WHERE challenge_id = '{challenge_id}'
                AND opaque_ref =
                  'opaque-ref:identity-delivery/{digests["challenge"]}'
                AND provider_idempotency_key IS NOT NULL),
            (SELECT count(*) FROM identity_verification_abuse_budgets
              WHERE organization_id = '{organization}'
                AND project_id = '{project}'
                AND channel = 'email'
                AND purpose = 'credential_binding'
                AND subject_digest = '{digests["subject"]}');
        """,
    ))
    assert durable == ["1|1"]

    verified = _rows(_psql(
        verification_database,
        runtime_scope + f"""
          SELECT outcome_code, receipt_id
            FROM a1_verify_identity_verification_attempt(
              '{organization}', '{project}', '{digests["challenge"]}',
              '{digests["code"]}', '{digests["context"]}',
              '{digests["receipt"]}', '{digests["verify_event"]}',
              '{{}}'::jsonb
            );
        """,
        user="a1_runtime",
    ))
    assert len(verified) == 1 and verified[0].startswith("verified|")

    binding_authorities = (
        (
            digests["idempotency"],
            digests["request"],
            digests["bind_event"],
            digests["step_up"],
            digests["ticket"],
        ),
        (
            digests["idempotency_competitor"],
            digests["request_competitor"],
            digests["bind_event_competitor"],
            digests["step_up_competitor"],
            digests["ticket_competitor"],
        ),
    )
    for _, request_digest, _, step_up_digest, ticket_digest in (
        binding_authorities
    ):
        _psql(
            verification_database,
            f"""
              INSERT INTO identity_security_receipts (
                receipt_digest, principal_id, purpose, context_digest,
                expires_at
              ) VALUES (
                '{step_up_digest}', '{principal}', 'credential_bind',
                '{request_digest}', clock_timestamp() + interval '10 minutes'
              );
            """,
            tuples=False,
        )
        issued = _rows(_psql(
            verification_database,
            f"""
              -- Migration 028 deliberately removes the independent
              -- password/MFA issuer's access to this legacy credential-bind
              -- primitive. Seed the authority as the database owner because
              -- this test exercises binding atomicity, not issuer ACLs.
              SELECT a1_issue_identity_security_mutation_ticket(
                '{ticket_digest}', '{step_up_digest}', '{principal}',
                '{principal}', 'credential_bind', '{request_digest}',
                NULL, NULL, NULL, NULL, NULL, NULL,
                clock_timestamp() + interval '5 minutes'
              );
            """,
        ))
        assert issued == ["t"]

    binding_privileges = _rows(_psql(
        verification_database,
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
            );
        """,
    ))
    assert binding_privileges == ["t|f"]

    _psql(
        verification_database,
        """
          CREATE FUNCTION a1_test_reject_credential_insert()
          RETURNS trigger
          LANGUAGE plpgsql
          AS $$
          BEGIN
            RAISE EXCEPTION 'injected credential mutation failure';
          END;
          $$;
          CREATE TRIGGER a1_test_reject_credential_insert
          BEFORE INSERT ON identity_credentials
          FOR EACH ROW EXECUTE FUNCTION a1_test_reject_credential_insert();
        """,
        tuples=False,
    )
    failed = _psql(
        verification_database,
        runtime_scope + f"""
          SELECT a1_bind_verified_identity_credential_authorized(
            '{organization}', '{project}', '{digests["receipt"]}',
            '{principal}', '{digests["session"]}', '{digests["ticket"]}',
            '{digests["step_up"]}', '{digests["idempotency"]}',
            '{digests["request"]}', '{digests["bind_event"]}', '{{}}'::jsonb
          );
        """,
        user="a1_runtime",
        check=False,
    )
    assert failed.returncode != 0
    assert "injected credential mutation failure" in failed.stderr
    retryable = _rows(_psql(
        verification_database,
        f"""
          SELECT
            (SELECT status = 'verified' AND consumed_at IS NULL
               FROM identity_verification_receipts
              WHERE receipt_digest = '{digests["receipt"]}'),
            (SELECT consumed_at IS NULL
               FROM identity_security_receipts
              WHERE receipt_digest = '{digests["step_up"]}'),
            (SELECT consumed_at IS NULL
               FROM identity_security_mutation_tickets
              WHERE ticket_digest = '{digests["ticket"]}');
        """,
    ))
    assert retryable == ["t|t|t"]
    _psql(
        verification_database,
        """
          DROP TRIGGER a1_test_reject_credential_insert
            ON identity_credentials;
          DROP FUNCTION a1_test_reject_credential_insert();
        """,
        tuples=False,
    )

    def bind_with_independent_connection(
        request: tuple[str, str, str, str, str],
    ) -> subprocess.CompletedProcess[str]:
        (
            idempotency_digest,
            request_digest,
            event_digest,
            step_up_digest,
            ticket_digest,
        ) = request
        return _psql(
            verification_database,
            runtime_scope + f"""
              SELECT a1_bind_verified_identity_credential_authorized(
                '{organization}', '{project}', '{digests["receipt"]}',
                '{principal}', '{digests["session"]}', '{ticket_digest}',
                '{step_up_digest}', '{idempotency_digest}',
                '{request_digest}', '{event_digest}', '{{}}'::jsonb
              );
            """,
            user="a1_runtime",
            check=False,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        concurrent_results = list(
            executor.map(bind_with_independent_connection, binding_authorities)
        )

    winners = [
        (request, result)
        for request, result in zip(
            binding_authorities, concurrent_results, strict=True
        )
        if result.returncode == 0
    ]
    losers = [
        (request, result)
        for request, result in zip(
            binding_authorities, concurrent_results, strict=True
        )
        if result.returncode != 0
    ]
    assert len(winners) == 1
    assert len(losers) == 1
    credential_rows = _rows(winners[0][1])
    assert len(credential_rows) == 1
    credential_id = credential_rows[0]
    assert uuid.UUID(credential_id)
    loser_error = losers[0][1].stderr.lower()
    assert (
        "consumed" in loser_error
        or "idempotency_conflict" in loser_error
    )

    credential_state = _rows(_psql(
        verification_database,
        f"""
          SELECT count(*), bool_and(status = 'active'),
                 bool_and(verified_at IS NOT NULL)
            FROM identity_credentials
           WHERE id = '{credential_id}'
             AND principal_id = '{principal}'
             AND provider = 'email'
             AND provider_environment = 'production'
             AND subject_digest = '{digests["subject"]}';
        """,
    ))
    assert credential_state == ["1|t|t"]

    receipt_state = _rows(_psql(
        verification_database,
        f"""
          SELECT status, consumed_at IS NOT NULL, mutation_kind,
                 mutation_result_id, idempotency_digest, request_digest
            FROM identity_verification_receipts
           WHERE receipt_digest = '{digests["receipt"]}';
        """,
    ))
    (
        winner_idempotency,
        winner_request,
        winner_event,
        winner_step_up,
        winner_ticket,
    ) = winners[0][0]
    _, _, _, loser_step_up, loser_ticket = losers[0][0]
    assert receipt_state == [
        (
            f"consumed|t|bind|{credential_id}|"
            f"{winner_idempotency}|{winner_request}"
        )
    ]
    authorization_state = _rows(_psql(
        verification_database,
        f"""
          SELECT
            (SELECT consumed_at IS NOT NULL
               FROM identity_security_receipts
              WHERE receipt_digest = '{winner_step_up}'),
            (SELECT consumed_at IS NOT NULL
               FROM identity_security_mutation_tickets
              WHERE ticket_digest = '{winner_ticket}'),
            (SELECT consumed_at IS NULL
               FROM identity_security_receipts
              WHERE receipt_digest = '{loser_step_up}'),
            (SELECT consumed_at IS NULL
               FROM identity_security_mutation_tickets
              WHERE ticket_digest = '{loser_ticket}');
        """,
    ))
    assert authorization_state == ["t|t|t|t"]

    replay = _rows(_psql(
        verification_database,
        runtime_scope + f"""
          SELECT a1_bind_verified_identity_credential_authorized(
            '{organization}', '{project}', '{digests["receipt"]}',
            '{principal}', '{digests["session"]}', '{winner_ticket}',
            '{winner_step_up}', '{winner_idempotency}',
            '{winner_request}', '{winner_event}', '{{}}'::jsonb
          );
        """,
        user="a1_runtime",
    ))
    assert replay == [credential_id]

    conflicting_request = (
        digests["request_competitor"]
        if winner_request != digests["request_competitor"]
        else digests["request"]
    )
    conflicting_event = (
        digests["bind_event_competitor"]
        if winner_event != digests["bind_event_competitor"]
        else digests["bind_event"]
    )
    idempotency_conflict = _psql(
        verification_database,
        runtime_scope + f"""
          SELECT a1_bind_verified_identity_credential_authorized(
            '{organization}', '{project}', '{digests["receipt"]}',
            '{principal}', '{digests["session"]}', '{winner_ticket}',
            '{winner_step_up}', '{winner_idempotency}',
            '{conflicting_request}', '{conflicting_event}', '{{}}'::jsonb
          );
        """,
        user="a1_runtime",
        check=False,
    )
    assert idempotency_conflict.returncode != 0
    assert (
        "authorization_rejected" in idempotency_conflict.stderr.lower()
        or "idempotency_conflict" in idempotency_conflict.stderr.lower()
    )

    wrong_organization = str(uuid.uuid4())
    cross_scope = _psql(
        verification_database,
        (
            f"SET app.a1_organization_id = '{wrong_organization}';"
            f"SET app.a1_project_id = '{project}';"
            f"SET app.a1_principal_id = '{principal}';"
            f"""
              SELECT a1_bind_verified_identity_credential_authorized(
                '{organization}', '{project}', '{digests["receipt"]}',
                '{principal}', '{digests["session"]}', '{winner_ticket}',
                '{winner_step_up}', '{winner_idempotency}',
                '{winner_request}', '{winner_event}', '{{}}'::jsonb
              );
            """
        ),
        user="a1_runtime",
        check=False,
    )
    assert cross_scope.returncode != 0
    assert "scope" in cross_scope.stderr.lower()

    direct_table_mutation = _psql(
        verification_database,
        runtime_scope + f"""
          UPDATE identity_verification_receipts
             SET consumed_at = NULL
           WHERE receipt_digest = '{digests["receipt"]}';
        """,
        user="a1_runtime",
        check=False,
    )
    assert direct_table_mutation.returncode != 0
    assert (
        "permission denied" in direct_table_mutation.stderr.lower()
        or "row-level security" in direct_table_mutation.stderr.lower()
    )
