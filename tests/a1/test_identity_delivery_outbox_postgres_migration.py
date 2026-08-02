from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "services" / "api" / "migrations"
MIGRATION = MIGRATIONS / "014_a1_identity_delivery_outbox.sql"
IDENTITY_MIGRATION_MAX = "018_a1_password_mfa_lifecycle.sql"
GO_STORE = ROOT / "packages" / "go" / "releasefoundry" / "identity_delivery_postgres.go"
CONTAINER = os.environ.get("A1_POSTGRES_TEST_CONTAINER", "releasefoundry-oauth-pg-test")
RUNTIME_ROLE = "a1_runtime"

ORGANIZATION_ID = "11111111-1111-4111-8111-111111111111"
WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_ID = "33333333-3333-4333-8333-333333333333"
CHALLENGE_IDS = (
    "44444444-4444-4444-8444-444444444441",
    "44444444-4444-4444-8444-444444444442",
    "44444444-4444-4444-8444-444444444443",
)
LEGACY_CHALLENGE_IDS = (
    "55555555-5555-4555-8555-555555555551",
    "55555555-5555-4555-8555-555555555552",
    "55555555-5555-4555-8555-555555555553",
    "55555555-5555-4555-8555-555555555554",
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _normalized() -> str:
    return re.sub(r"\s+", " ", _sql()).lower()


def _function_body(function: str, next_marker: str) -> str:
    sql = _normalized()
    start = sql.index(f"create or replace function {function}(")
    return sql[start : sql.index(next_marker, start)]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


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
            r"^(SET|BEGIN|COMMIT|INSERT|UPDATE|DELETE|GRANT|CREATE)\b",
            line,
        )
    ]


def _runtime_sql(statement: str) -> str:
    return f"""
BEGIN;
SET LOCAL app.a1_organization_id = '{ORGANIZATION_ID}';
SET LOCAL app.a1_project_id = '{PROJECT_ID}';
{statement}
COMMIT;
"""


def _require_live_postgres() -> None:
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


def _create_database(prefix: str) -> str:
    database = f"{prefix}_{uuid.uuid4().hex[:10]}"
    _psql("postgres", f'CREATE DATABASE "{database}";', tuples=False)
    return database


def _apply_migrations(database: str, migrations: list[Path]) -> None:
    for migration in migrations:
        _psql(
            database,
            migration.read_text(encoding="utf-8"),
            tuples=False,
        )


def _identity_migrations() -> list[Path]:
    return [
        migration
        for migration in sorted(MIGRATIONS.glob("*.sql"))
        if migration.name <= IDENTITY_MIGRATION_MAX
    ]


def _drop_database(database: str) -> None:
    _psql(
        "postgres",
        f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE);',
        tuples=False,
        check=False,
    )


@pytest.fixture
def identity_delivery_database() -> str:
    _require_live_postgres()
    database = _create_database("a1_identity_delivery_it")
    try:
        _apply_migrations(database, _identity_migrations())
        yield database
    finally:
        _drop_database(database)


@pytest.fixture
def identity_delivery_012_database() -> str:
    _require_live_postgres()
    database = _create_database("a1_identity_delivery_upgrade_it")
    try:
        migrations = [
            migration
            for migration in _identity_migrations()
            if migration.name <= "012_a1_identity_verification.sql"
        ]
        _apply_migrations(database, migrations)
        yield database
    finally:
        _drop_database(database)


def test_identity_fixture_excludes_control_plane_provider_dispatch_migration() -> None:
    migrations = _identity_migrations()

    assert migrations[-1].name == IDENTITY_MIGRATION_MAX
    assert all(migration.name != "019_a1_provider_dispatch_coordination.sql" for migration in migrations)


def test_migration_is_additive_and_follows_session_lifecycle() -> None:
    assert MIGRATION.is_file()
    assert MIGRATION.name > "013_a1_identity_session_lifecycle.sql"
    sql = _normalized()
    assert sql.startswith("-- production identity-verification delivery leasing")
    assert sql.strip().endswith("commit;")
    assert "alter table identity_verification_delivery_outbox" in sql
    assert "create table if not exists identity_verification_delivery_redrive_audit" in sql
    assert "add column if not exists provider_acceptance_ref text" in sql
    assert "add column if not exists provider_accepted_at timestamptz" in sql
    assert (
        "create or replace function "
        "a1_issue_identity_verification_challenge_with_delivery" in sql
    )


def test_regex_bounds_are_postgres_are_compatible() -> None:
    sql = _normalized()
    assert not re.search(r"\{\d+,\s*(?:255|[3-9]\d{2,})\}", sql)
    for field in ("actor_id", "request_id"):
        assert f"length({field}) between 1 and 256" in sql
    assert "length(provider_idempotency_key) between 8 and 256" in sql
    assert "length(p_reference) between 1 and 256" in sql


def test_outbox_persists_only_opaque_delivery_material() -> None:
    sql = _normalized()
    required = [
        "add column if not exists opaque_ref text",
        "a1_identity_delivery_reference_only(opaque_ref)",
        "add column if not exists provider_idempotency_key text",
        "add column if not exists provider_acceptance_ref text",
        "add column if not exists provider_accepted_at timestamptz",
        "a1_identity_delivery_public_acceptance_reference",
        "identity_verification_delivery_provider_idempotency_key",
        "add column if not exists max_attempts integer not null default 8",
        "attempt_count between 0 and max_attempts",
        "last_error_code ~ '^[a-z][a-z0-9_.-]{1,63}$'",
        "challenge.expires_at",
    ]
    for fragment in required:
        assert fragment in sql

    for forbidden in [
        "destination text",
        "recipient text",
        "email_address text",
        "phone_number text",
        "otp text",
        "otp_code text",
        "verification_code text",
        "smtp_password text",
        "api_secret text",
    ]:
        assert forbidden not in sql


def test_upgrade_normalizes_every_legacy_012_state_before_constraints() -> None:
    sql = _normalized()
    update_start = sql.index("update identity_verification_delivery_outbox")
    update_end = sql.index(
        "alter table identity_verification_delivery_outbox", update_start
    )
    update = sql[update_start:update_end]
    required = [
        "when status = 'leased' then greatest(lease_generation, 1)",
        "lease_owner = case when status = 'leased' then lease_owner end",
        "lease_expires_at = case when status = 'leased' then lease_expires_at end",
        "delivered_at = case when status = 'delivered' then delivered_at end",
        "dead_at = case when status = 'dead' then dead_at end",
        "'provider-ref:legacy/' || challenge_id::text",
        "when status = 'delivered' then coalesce( provider_accepted_at, delivered_at )",
    ]
    for fragment in required:
        assert fragment in update
    assert update.index("greatest(lease_generation, 1)") < sql.index(
        "add constraint identity_verification_delivery_outbox_lease_check"
    )


def test_issue_wrapper_is_scoped_atomic_and_replaces_unsafe_runtime_grant() -> None:
    body = _function_body(
        "a1_issue_identity_verification_challenge_with_delivery",
        "create or replace function a1_claim_identity_delivery_outbox",
    )
    required = [
        "security definer",
        "set search_path = pg_catalog, public",
        "perform a1_identity_delivery_assert_scope",
        "a1_identity_delivery_reference_only(p_opaque_ref)",
        "from a1_issue_identity_verification_challenge(",
        "set id = issuance.challenge_id",
        "opaque_ref = p_opaque_ref",
        "delivery.organization_id = p_organization_id",
        "delivery.project_id = p_project_id",
        "delivery.challenge_id = issuance.challenge_id",
        "return query select",
    ]
    for fragment in required:
        assert fragment in body


def test_claim_is_bounded_skip_locked_and_returns_complete_worker_contract() -> None:
    body = _function_body(
        "a1_claim_identity_delivery_outbox",
        "create or replace function a1_heartbeat_identity_delivery_outbox",
    )
    required = [
        "security definer",
        "set search_path = pg_catalog, public",
        "perform a1_identity_delivery_assert_scope",
        "target.organization_id = p_organization_id",
        "target.project_id = p_project_id",
        "target.provider_acceptance_ref is null",
        "target.provider_accepted_at is null",
        "target.attempt_count < target.max_attempts",
        "target.status = 'leased'",
        "target.lease_expires_at <= p_now",
        "for update of target skip locked",
        "limit p_limit",
        "attempt_count = target.attempt_count + 1",
        "lease_generation = target.lease_generation + 1",
        "provider_idempotency_key",
        "challenge.expires_at",
    ]
    for fragment in required:
        assert fragment in body


def test_every_leased_mutation_has_the_full_cas_fence() -> None:
    functions = [
        (
            "a1_heartbeat_identity_delivery_outbox",
            "create or replace function a1_complete_identity_delivery_outbox",
        ),
        (
            "a1_complete_identity_delivery_outbox",
            "create or replace function a1_retry_identity_delivery_outbox",
        ),
        (
            "a1_retry_identity_delivery_outbox",
            "create or replace function a1_dead_letter_identity_delivery_outbox",
        ),
        (
            "a1_dead_letter_identity_delivery_outbox",
            "create or replace function a1_redrive_identity_delivery_outbox",
        ),
    ]
    for function, next_marker in functions:
        body = _function_body(function, next_marker)
        for fragment in [
            "security definer",
            "organization_id = p_organization_id",
            "project_id = p_project_id",
            "id = p_outbox_id",
            "target.status <> 'leased'",
            "target.lease_owner <> p_lease_owner",
            "target.lease_generation <> p_lease_generation",
            "target.lease_expires_at <= p_now",
            "using errcode = 'p0001'",
            "using errcode = 'p0002'",
        ]:
            assert fragment in body, f"{function} is missing {fragment!r}"


def test_complete_records_bounded_provider_acceptance_inside_cas() -> None:
    body = _function_body(
        "a1_complete_identity_delivery_outbox",
        "create or replace function a1_retry_identity_delivery_outbox",
    )
    assert "from identity_verification_challenges" in body
    assert "select issued_at, expires_at" in body
    assert "p_provider_accepted_at > challenge_expires_at" in body
    assert "p_provider_accepted_at > p_now" in body
    assert "provider_acceptance_ref = p_provider_acceptance_ref" in body
    assert "provider_accepted_at = p_provider_accepted_at" in body
    assert "using errcode = 'p0003'" in body
    assert "challenge_expires_at <= p_now" not in body
    assert body.index("p_provider_accepted_at > challenge_expires_at") < body.index(
        "set status = 'delivered'"
    )


def test_redrive_is_generation_fenced_atomic_and_audited() -> None:
    body = _function_body(
        "a1_redrive_identity_delivery_outbox",
        "alter table identity_verification_delivery_outbox enable row level security",
    )
    required = [
        "target.status <> 'dead'",
        "target.lease_generation <> p_expected_lease_generation",
        "target.lease_owner is not null",
        "target.lease_expires_at is not null",
        "new_generation := target.lease_generation + 1",
        "status = 'pending'",
        "attempt_count = 0",
        "provider_acceptance_ref = null",
        "provider_accepted_at = null",
        "provider_idempotency_key = new_provider_key",
        "insert into identity_verification_delivery_redrive_audit",
        "previous_lease_generation",
        "new_lease_generation",
        "return query select",
    ]
    for fragment in required:
        assert fragment in body
    assert body.index("update identity_verification_delivery_outbox") < body.index(
        "insert into identity_verification_delivery_redrive_audit"
    )


def test_provider_key_is_stable_until_intentional_audited_redrive() -> None:
    claim = _function_body(
        "a1_claim_identity_delivery_outbox",
        "create or replace function a1_heartbeat_identity_delivery_outbox",
    )
    retry = _function_body(
        "a1_retry_identity_delivery_outbox",
        "create or replace function a1_dead_letter_identity_delivery_outbox",
    )
    dead = _function_body(
        "a1_dead_letter_identity_delivery_outbox",
        "create or replace function a1_redrive_identity_delivery_outbox",
    )
    redrive = _function_body(
        "a1_redrive_identity_delivery_outbox",
        "alter table identity_verification_delivery_outbox enable row level security",
    )
    assert "provider_idempotency_key =" not in claim
    assert "provider_idempotency_key =" not in retry
    assert "provider_idempotency_key =" not in dead
    assert "provider_idempotency_key = new_provider_key" in redrive
    assert "insert into identity_verification_delivery_redrive_audit" in redrive


def test_retry_and_dead_letter_refuse_provider_accepted_delivery() -> None:
    for function, marker in [
        (
            "a1_retry_identity_delivery_outbox",
            "create or replace function a1_dead_letter_identity_delivery_outbox",
        ),
        (
            "a1_dead_letter_identity_delivery_outbox",
            "create or replace function a1_redrive_identity_delivery_outbox",
        ),
    ]:
        body = _function_body(function, marker)
        assert "target.provider_acceptance_ref is not null" in body
        assert "target.provider_accepted_at is not null" in body
        assert "identity delivery already accepted by provider" in body
        assert "using errcode = 'p0004'" in body


def test_rls_and_privileges_expose_functions_not_tables() -> None:
    sql = _normalized()
    required = [
        "alter table identity_verification_delivery_outbox force row level security",
        "alter table identity_verification_delivery_redrive_audit force row level security",
        "create policy identity_verification_delivery_redrive_scope_access",
        "organization_id = a1_current_organization_id()",
        "project_id = a1_current_project_id()",
        "revoke all on table identity_verification_delivery_outbox from public",
        "revoke all on table identity_verification_delivery_redrive_audit from public",
        "revoke all on table identity_verification_delivery_outbox from a1_runtime",
        "revoke all on table identity_verification_delivery_redrive_audit from a1_runtime",
        "revoke all on function a1_issue_identity_verification_challenge(",
    ]
    for fragment in required:
        assert fragment in sql

    functions = [
        "a1_issue_identity_verification_challenge_with_delivery",
        "a1_claim_identity_delivery_outbox",
        "a1_heartbeat_identity_delivery_outbox",
        "a1_complete_identity_delivery_outbox",
        "a1_retry_identity_delivery_outbox",
        "a1_dead_letter_identity_delivery_outbox",
        "a1_redrive_identity_delivery_outbox",
    ]
    for function in functions:
        assert f"revoke all on function {function}(" in sql
        assert f"grant execute on function {function}(" in sql


def test_go_store_uses_parameters_and_maps_distinct_fence_errors() -> None:
    source = GO_STORE.read_text(encoding="utf-8")
    assert "var _ IdentityDeliveryOutboxStore" in source
    assert "setPostgresIdentityVerificationScope" in source
    for function in [
        "a1_claim_identity_delivery_outbox",
        "a1_heartbeat_identity_delivery_outbox",
        "a1_complete_identity_delivery_outbox",
        "a1_retry_identity_delivery_outbox",
        "a1_dead_letter_identity_delivery_outbox",
        "a1_redrive_identity_delivery_outbox",
    ]:
        call = source[source.index(function) - 200 : source.index(function) + 500]
        assert "$1" in call
    assert "postgresIdentityDeliveryLeaseLostSQLState" in source
    assert '"P0001"' in source
    assert "postgresIdentityDeliveryLeaseExpiredSQLState" in source
    assert '"P0002"' in source
    assert "ErrIdentityDeliveryLeaseLost" in source
    assert "ErrIdentityDeliveryLeaseExpired" in source


@pytest.mark.docker
def test_live_populated_012_to_014_upgrade_normalizes_all_states(
    identity_delivery_012_database: str,
) -> None:
    challenge_values = []
    for index, challenge_id in enumerate(LEGACY_CHALLENGE_IDS, start=1):
        challenge_values.append(
            f"""
INSERT INTO identity_verification_challenges (
  id, organization_id, project_id, channel, purpose, subject_digest,
  challenge_digest, code_digest, request_context_digest, expires_at
) VALUES (
  '{challenge_id}'::uuid, '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid,
  'email', 'login', '{_digest(f'legacy-subject-{index}')}',
  '{_digest(f'legacy-challenge-{index}')}',
  '{_digest(f'legacy-code-{index}')}',
  '{_digest(f'legacy-context-{index}')}',
  clock_timestamp() + interval '10 minutes'
);
"""
        )

    setup = f"""
INSERT INTO organizations (id, slug, display_name)
VALUES ('{ORGANIZATION_ID}'::uuid, 'upgrade-org', 'Upgrade Org');
INSERT INTO workspaces (id, organization_id, slug, display_name)
VALUES (
  '{WORKSPACE_ID}'::uuid, '{ORGANIZATION_ID}'::uuid,
  'upgrade-workspace', 'Upgrade Workspace'
);
INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
VALUES (
  '{PROJECT_ID}'::uuid, '{ORGANIZATION_ID}'::uuid, '{WORKSPACE_ID}'::uuid,
  'upgrade-project', 'Upgrade Project'
);
{''.join(challenge_values)}
INSERT INTO identity_verification_delivery_outbox (
  organization_id, project_id, challenge_id, channel, purpose,
  subject_digest, delivery_digest, status, lease_owner,
  lease_generation, lease_expires_at, attempt_count,
  delivered_at, dead_at
) VALUES
(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid,
  '{LEGACY_CHALLENGE_IDS[0]}'::uuid, 'email', 'login',
  '{_digest('legacy-subject-1')}', '{_digest('legacy-delivery-1')}',
  'leased', 'legacy-worker', 0, clock_timestamp() + interval '5 minutes',
  3, NULL, NULL
),
(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid,
  '{LEGACY_CHALLENGE_IDS[1]}'::uuid, 'email', 'login',
  '{_digest('legacy-subject-2')}', '{_digest('legacy-delivery-2')}',
  'pending', 'stale-owner', 0, clock_timestamp() + interval '5 minutes',
  0, clock_timestamp(), clock_timestamp()
),
(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid,
  '{LEGACY_CHALLENGE_IDS[2]}'::uuid, 'email', 'login',
  '{_digest('legacy-subject-3')}', '{_digest('legacy-delivery-3')}',
  'delivered', 'stale-owner', 7, clock_timestamp() + interval '5 minutes',
  2, clock_timestamp(), clock_timestamp()
),
(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid,
  '{LEGACY_CHALLENGE_IDS[3]}'::uuid, 'email', 'login',
  '{_digest('legacy-subject-4')}', '{_digest('legacy-delivery-4')}',
  'dead', 'stale-owner', 4, clock_timestamp() + interval '5 minutes',
  4, clock_timestamp(), clock_timestamp()
);
"""
    _psql(identity_delivery_012_database, setup, tuples=False)

    _apply_migrations(
        identity_delivery_012_database,
        [
            MIGRATIONS / "013_a1_identity_session_lifecycle.sql",
            MIGRATION,
        ],
    )

    rows = _rows(
        _psql(
            identity_delivery_012_database,
            """
SELECT challenge_id::text, status, lease_generation,
       COALESCE(lease_owner, '<null>'), lease_expires_at IS NULL,
       delivered_at IS NULL, dead_at IS NULL,
       COALESCE(provider_acceptance_ref, '<null>'),
       provider_accepted_at IS NOT DISTINCT FROM delivered_at,
       opaque_ref IS NOT NULL, provider_idempotency_key IS NOT NULL,
       max_attempts
  FROM identity_verification_delivery_outbox
 ORDER BY challenge_id;
""",
        )
    )
    assert rows == [
        f"{LEGACY_CHALLENGE_IDS[0]}|leased|1|legacy-worker|f|t|t|<null>|t|t|t|8",
        f"{LEGACY_CHALLENGE_IDS[1]}|pending|0|<null>|t|t|t|<null>|t|t|t|8",
        (
            f"{LEGACY_CHALLENGE_IDS[2]}|delivered|7|<null>|t|f|t|"
            f"provider-ref:legacy/{LEGACY_CHALLENGE_IDS[2]}|t|t|t|8"
        ),
        f"{LEGACY_CHALLENGE_IDS[3]}|dead|4|<null>|t|t|f|<null>|t|t|t|8",
    ]

    compiled = _rows(
        _psql(
            identity_delivery_012_database,
            """
SELECT current_setting('server_version_num')::integer >= 160000,
       a1_identity_delivery_reference_only(
         'opaque-ref:identity-delivery/fixture'
       ),
       a1_identity_delivery_public_acceptance_reference(
         'provider-ref:smtp/message-1'
       ),
       'provider_timeout' ~ '^[a-z][a-z0-9_.-]{1,63}$';
""",
        )
    )
    assert compiled == ["t|t|t|t"]


@pytest.mark.docker
def test_live_multi_connection_claim_fencing_and_audited_redrive(
    identity_delivery_database: str,
) -> None:
    values = []
    for index, challenge_id in enumerate(CHALLENGE_IDS, start=1):
        values.append(
            f"""
INSERT INTO identity_verification_challenges (
  id, organization_id, project_id, channel, purpose, subject_digest,
  challenge_digest, code_digest, request_context_digest, expires_at
) VALUES (
  '{challenge_id}'::uuid, '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid,
  'email', 'login', '{_digest(f'subject-{index}')}',
  '{_digest(f'challenge-{index}')}', '{_digest(f'code-{index}')}',
  '{_digest(f'context-{index}')}', clock_timestamp() + interval '10 minutes'
);
INSERT INTO identity_verification_delivery_outbox (
  organization_id, project_id, challenge_id, channel, purpose,
  subject_digest, delivery_digest
) VALUES (
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, '{challenge_id}'::uuid,
  'email', 'login', '{_digest(f'subject-{index}')}',
  '{_digest(f'delivery-{index}')}'
);
"""
        )
    setup = f"""
INSERT INTO organizations (id, slug, display_name)
VALUES ('{ORGANIZATION_ID}'::uuid, 'delivery-org', 'Delivery Org');
INSERT INTO workspaces (id, organization_id, slug, display_name)
VALUES (
  '{WORKSPACE_ID}'::uuid, '{ORGANIZATION_ID}'::uuid,
  'delivery-workspace', 'Delivery Workspace'
);
INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
VALUES (
  '{PROJECT_ID}'::uuid, '{ORGANIZATION_ID}'::uuid, '{WORKSPACE_ID}'::uuid,
  'delivery-project', 'Delivery Project'
);
{''.join(values)}
"""
    _psql(identity_delivery_database, setup, tuples=False)

    def claim(owner: str, hold_seconds: float) -> subprocess.CompletedProcess[str]:
        return _psql(
            identity_delivery_database,
            _runtime_sql(
                f"""
SELECT pg_backend_pid(), outbox_id::text, lease_generation, lease_owner,
       provider_idempotency_key
  FROM a1_claim_identity_delivery_outbox(
    '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid,
    '{owner}', 1, 3600000, clock_timestamp()
  );
SELECT pg_sleep({hold_seconds});
"""
            ),
            user=RUNTIME_ROLE,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(claim, "worker-one", 1.0)
        time.sleep(0.15)
        second = executor.submit(claim, "worker-two", 0.0)
        first_rows = [row for row in _rows(first.result()) if "worker-" in row]
        second_rows = [row for row in _rows(second.result()) if "worker-" in row]

    assert len(first_rows) == 1
    assert len(second_rows) == 1
    (
        first_backend,
        first_task,
        first_generation,
        first_owner,
        first_provider_key,
    ) = first_rows[0].split("|")
    (
        second_backend,
        second_task,
        second_generation,
        second_owner,
        second_provider_key,
    ) = second_rows[0].split("|")
    assert first_task != second_task
    assert first_backend != second_backend
    assert {first_owner, second_owner} == {"worker-one", "worker-two"}
    assert first_generation == second_generation == "1"
    assert first_provider_key != second_provider_key

    stale = _psql(
        identity_delivery_database,
        _runtime_sql(
            f"""
SELECT a1_complete_identity_delivery_outbox(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, '{first_task}'::uuid,
  '{first_owner}', 999, 'provider-ref:smtp/stale-attempt',
  clock_timestamp(), clock_timestamp()
);
"""
        ),
        user=RUNTIME_ROLE,
        check=False,
    )
    assert stale.returncode != 0
    assert "identity delivery lease lost" in stale.stderr.lower()

    completed = _rows(
        _psql(
            identity_delivery_database,
            _runtime_sql(
                f"""
SELECT a1_complete_identity_delivery_outbox(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, '{first_task}'::uuid,
  '{first_owner}', {first_generation}, 'provider-ref:smtp/accepted-first',
  clock_timestamp(), clock_timestamp()
)::text;
"""
            ),
            user=RUNTIME_ROLE,
        )
    )
    assert first_task in completed

    delivered_state = _rows(
        _psql(
            identity_delivery_database,
            f"""
SELECT status, provider_acceptance_ref,
       provider_accepted_at <= delivered_at,
       dead_at IS NULL
  FROM identity_verification_delivery_outbox
 WHERE id = '{first_task}'::uuid;
""",
        )
    )
    assert delivered_state == ["delivered|provider-ref:smtp/accepted-first|t|t"]

    retried = _rows(
        _psql(
            identity_delivery_database,
            _runtime_sql(
                f"""
WITH timing AS (SELECT clock_timestamp() AS now)
SELECT a1_retry_identity_delivery_outbox(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, '{second_task}'::uuid,
  '{second_owner}', {second_generation}, 'provider_timeout', now, now
)::text
  FROM timing;
"""
            ),
            user=RUNTIME_ROLE,
        )
    )
    assert second_task in retried

    reclaimed = _rows(
        _psql(
            identity_delivery_database,
            _runtime_sql(
                f"""
SELECT outbox_id::text, challenge_id::text, lease_generation, lease_owner,
       provider_idempotency_key
  FROM a1_claim_identity_delivery_outbox(
    '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid,
    'worker-two-retry', 3, 3600000, clock_timestamp()
  );
"""
            ),
            user=RUNTIME_ROLE,
        )
    )
    reclaimed = [row for row in reclaimed if "worker-two-retry" in row]
    assert len(reclaimed) == 2
    second_reclaimed = next(
        row.split("|") for row in reclaimed if row.startswith(f"{second_task}|")
    )
    (
        _,
        _,
        second_generation,
        second_owner,
        second_provider_key_after_retry,
    ) = second_reclaimed
    assert second_generation == "2"
    assert second_provider_key_after_retry == second_provider_key

    third_reclaimed = next(
        row.split("|") for row in reclaimed if not row.startswith(f"{second_task}|")
    )
    (
        third_task,
        third_challenge,
        third_generation,
        third_owner,
        _,
    ) = third_reclaimed

    dead = _rows(
        _psql(
            identity_delivery_database,
            _runtime_sql(
                f"""
SELECT a1_dead_letter_identity_delivery_outbox(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, '{second_task}'::uuid,
  '{second_owner}', {second_generation}, 'provider_timeout', clock_timestamp()
)::text;
"""
            ),
            user=RUNTIME_ROLE,
        )
    )
    assert second_task in dead

    redrive = _rows(
        _psql(
            identity_delivery_database,
            _runtime_sql(
                f"""
SELECT outbox_id::text, lease_generation, audit_id::text
  FROM a1_redrive_identity_delivery_outbox(
    '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, '{second_task}'::uuid,
    {second_generation}, 'operator-1', 'provider_recovered',
    'redrive-request-1', clock_timestamp()
  );
"""
            ),
            user=RUNTIME_ROLE,
        )
    )
    assert len(redrive) == 1
    redriven_task, redriven_generation, audit_id = redrive[0].split("|")
    assert redriven_task == second_task
    assert redriven_generation == "3"
    assert re.fullmatch(r"[0-9a-f-]{36}", audit_id)

    state = _rows(
        _psql(
            identity_delivery_database,
            f"""
SELECT outbox.status, outbox.lease_generation, outbox.attempt_count,
       count(audit.id), outbox.provider_idempotency_key,
       min(audit.provider_idempotency_key)
  FROM identity_verification_delivery_outbox AS outbox
  JOIN identity_verification_delivery_redrive_audit AS audit
    ON audit.organization_id = outbox.organization_id
   AND audit.project_id = outbox.project_id
   AND audit.outbox_id = outbox.id
 WHERE outbox.id = '{second_task}'::uuid
 GROUP BY outbox.status, outbox.lease_generation, outbox.attempt_count,
          outbox.provider_idempotency_key;
""",
        )
    )
    assert len(state) == 1
    (
        redriven_status,
        redriven_generation,
        redriven_attempts,
        audit_count,
        redriven_provider_key,
        audited_provider_key,
    ) = state[0].split("|")
    assert (redriven_status, redriven_generation, redriven_attempts, audit_count) == (
        "pending",
        "3",
        "0",
        "1",
    )
    assert redriven_provider_key == audited_provider_key
    assert redriven_provider_key != second_provider_key

    challenge_expiry = _rows(
        _psql(
            identity_delivery_database,
            f"""
SELECT expires_at::text
  FROM identity_verification_challenges
 WHERE id = '{third_challenge}'::uuid;
""",
        )
    )[0]
    late_completion = _rows(
        _psql(
            identity_delivery_database,
            _runtime_sql(
                f"""
SELECT a1_complete_identity_delivery_outbox(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, '{third_task}'::uuid,
  '{third_owner}', {third_generation}, 'provider-ref:smtp/accepted-before-expiry',
  '{challenge_expiry}'::timestamptz - interval '1 second',
  '{challenge_expiry}'::timestamptz + interval '1 second'
)::text;
"""
            ),
            user=RUNTIME_ROLE,
        )
    )
    assert third_task in late_completion

    cannot_dead_letter = _psql(
        identity_delivery_database,
        _runtime_sql(
            f"""
SELECT a1_dead_letter_identity_delivery_outbox(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, '{third_task}'::uuid,
  '{third_owner}', {third_generation}, 'late_ack', clock_timestamp()
);
"""
        ),
        user=RUNTIME_ROLE,
        check=False,
    )
    assert cannot_dead_letter.returncode != 0
    assert "already accepted by provider" in cannot_dead_letter.stderr.lower()

    wrapper_challenge_digest = _digest("wrapped-challenge")
    wrapped = _rows(
        _psql(
            identity_delivery_database,
            _runtime_sql(
                f"""
SELECT challenge_id::text, accepted, retry_after_seconds
  FROM a1_issue_identity_verification_challenge_with_delivery(
    '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, NULL,
    'email', 'login', '{_digest('wrapped-subject')}',
    '{wrapper_challenge_digest}', '{_digest('wrapped-code')}',
    '{_digest('wrapped-context')}', clock_timestamp() + interval '10 minutes',
    5, 30, '{_digest('wrapped-event')}',
    'vault:identity-delivery/wrapped-message', '{{"source":"live-test"}}'::jsonb
  );
"""
            ),
            user=RUNTIME_ROLE,
        )
    )
    assert len(wrapped) == 1
    wrapped_challenge, accepted, retry_after = wrapped[0].split("|")
    assert accepted == "t"
    assert retry_after == "0"

    wrapped_state = _rows(
        _psql(
            identity_delivery_database,
            f"""
SELECT challenge.id = outbox.id, outbox.challenge_id = outbox.id,
       outbox.opaque_ref, outbox.status,
       outbox.provider_acceptance_ref IS NULL
  FROM identity_verification_challenges AS challenge
  JOIN identity_verification_delivery_outbox AS outbox
    ON outbox.organization_id = challenge.organization_id
   AND outbox.project_id = challenge.project_id
   AND outbox.challenge_id = challenge.id
 WHERE challenge.id = '{wrapped_challenge}'::uuid;
""",
        )
    )
    assert wrapped_state == [
        "t|t|vault:identity-delivery/wrapped-message|pending|t"
    ]

    unsafe_legacy_issue = _psql(
        identity_delivery_database,
        _runtime_sql(
            f"""
SELECT * FROM a1_issue_identity_verification_challenge(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, NULL,
  'email', 'login', '{_digest('legacy-call-subject')}',
  '{_digest('legacy-call-challenge')}', '{_digest('legacy-call-code')}',
  '{_digest('legacy-call-context')}', clock_timestamp() + interval '10 minutes',
  5, 30, '{_digest('legacy-call-event')}', '{{}}'::jsonb
);
"""
        ),
        user=RUNTIME_ROLE,
        check=False,
    )
    assert unsafe_legacy_issue.returncode != 0
    assert "permission denied" in unsafe_legacy_issue.stderr.lower()

    invalid_digest = _digest("invalid-reference-challenge")
    invalid_reference = _psql(
        identity_delivery_database,
        _runtime_sql(
            f"""
SELECT * FROM a1_issue_identity_verification_challenge_with_delivery(
  '{ORGANIZATION_ID}'::uuid, '{PROJECT_ID}'::uuid, NULL,
  'email', 'login', '{_digest('invalid-reference-subject')}',
  '{invalid_digest}', '{_digest('invalid-reference-code')}',
  '{_digest('invalid-reference-context')}',
  clock_timestamp() + interval '10 minutes', 5, 30,
  '{_digest('invalid-reference-event')}', 'plaintext-secret', '{{}}'::jsonb
);
"""
        ),
        user=RUNTIME_ROLE,
        check=False,
    )
    assert invalid_reference.returncode != 0
    assert "delivery reference is invalid" in invalid_reference.stderr.lower()
    not_created = _rows(
        _psql(
            identity_delivery_database,
            f"""
SELECT count(*)
  FROM identity_verification_challenges
 WHERE challenge_digest = '{invalid_digest}';
""",
        )
    )
    assert not_created == ["0"]

    direct = _psql(
        identity_delivery_database,
        _runtime_sql("SELECT count(*) FROM identity_verification_delivery_outbox;"),
        user=RUNTIME_ROLE,
        check=False,
    )
    assert direct.returncode != 0
    assert "permission denied" in direct.stderr.lower()
