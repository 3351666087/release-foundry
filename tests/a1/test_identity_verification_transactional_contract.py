from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "012_a1_identity_verification.sql"
)
GO_DIR = ROOT / "packages" / "go" / "releasefoundry"
POSTGRES_STORE = GO_DIR / "identity_verification_postgres.go"
VERIFICATION_SERVICE = GO_DIR / "identity_verification.go"
VERIFICATION_HTTP = GO_DIR / "identity_verification_http.go"
VERIFICATION_SECURITY = GO_DIR / "identity_verification_security.go"
RUNTIME = GO_DIR / "cmd" / "releasefoundry-api" / "runtime.go"


def _read(path: Path) -> str:
    assert path.is_file(), f"required identity verification artifact is missing: {path}"
    return path.read_text(encoding="utf-8")


def _normalized(path: Path) -> str:
    return re.sub(r"\s+", " ", _read(path)).lower()


def _sql_function(name: str) -> str:
    sql = _normalized(MIGRATION)
    marker = f"create or replace function {name}("
    assert marker in sql, f"migration 012 is missing required function {name}"
    start = sql.index(marker)
    next_function = sql.find("create or replace function ", start + 1)
    next_trigger = sql.find("drop trigger ", start + 1)
    candidates = [index for index in (next_function, next_trigger) if index >= 0]
    end = min(candidates) if candidates else len(sql)
    return sql[start:end]


def _go_sources() -> str:
    sources = []
    for path in sorted(GO_DIR.glob("identity_verification*.go")):
        if not path.name.endswith("_test.go"):
            sources.append(_read(path))
    return "\n".join(sources)


def test_migration_defines_durable_delivery_and_abuse_state() -> None:
    """Issuing an OTP must commit before delivery and survive process loss."""
    sql = _normalized(MIGRATION)

    required_tables = {
        "identity_verification_challenges",
        "identity_verification_receipts",
        "identity_verification_cooldowns",
        "identity_verification_audit_events",
        "identity_verification_delivery_outbox",
        "identity_verification_abuse_budgets",
    }
    for table in required_tables:
        assert f"create table if not exists {table}" in sql
        assert f"alter table {table} enable row level security" in sql
        assert f"alter table {table} force row level security" in sql
        assert f"revoke all on table {table} from public" in sql
        assert f"revoke all on table {table} from a1_runtime" in sql

    outbox = sql[sql.index("create table if not exists identity_verification_delivery_outbox") :]
    assert "lease_owner" in outbox
    assert "lease_generation" in outbox
    assert "lease_expires_at" in outbox
    assert "attempt_count" in outbox
    assert "next_attempt_at" in outbox
    assert "dead" in outbox


def test_migration_has_narrow_transactional_identity_entrypoints() -> None:
    """The runtime role may call functions, never compose identity table writes."""
    sql = _normalized(MIGRATION)
    required_functions = {
        "a1_issue_identity_verification_challenge",
        "a1_verify_identity_verification_attempt",
        "a1_bind_verified_identity_credential",
        "a1_login_with_verified_identity",
        "a1_recover_verified_identity",
    }
    for function in required_functions:
        body = _sql_function(function)
        assert "security definer" in body
        assert "set search_path = pg_catalog, public" in body
        assert "a1_identity_verification_assert_scope(" in body
        assert f"revoke all on function {function}(" in sql
        assert f"grant execute on function {function}(" in sql

    assert "grant execute on function a1_identity_verification_assert_scope(" not in sql


def test_final_mutations_consume_receipt_and_change_identity_in_one_function() -> None:
    """A failed identity mutation must roll back receipt consumption and audit."""
    for function in (
        "a1_bind_verified_identity_credential",
        "a1_login_with_verified_identity",
        "a1_recover_verified_identity",
    ):
        body = _sql_function(function)
        assert "from identity_verification_receipts" in body
        assert "for update" in body
        assert "from identity_principals" in body
        assert "identity_verification_audit_events" in body
        assert "consumed_at" in body
        assert "idempotency_digest" in body
        assert "request_digest" in body

        receipt_lock = body.index("from identity_verification_receipts")
        mutation = min(
            index
            for marker in (
                "insert into identity_credentials",
                "insert into identity_sessions",
                "update identity_sessions",
            )
            if (index := body.find(marker)) >= 0
        )
        consume = body.index("consumed_at")
        audit = body.rindex("identity_verification_audit_events")
        assert receipt_lock < mutation < consume < audit

        # Catch blocks that convert a database failure into a successful
        # return would commit a consumed receipt without the identity change.
        assert "when others then" not in body


def test_transactional_contract_prevents_implicit_identity_merge() -> None:
    sql = _normalized(MIGRATION)
    bind = _sql_function("a1_bind_verified_identity_credential")

    assert "identity_credentials" in bind
    assert "principal_id" in bind
    assert "for update" in bind
    assert "credential_link_conflict" in bind
    assert "merge" not in bind
    assert "on conflict" not in bind or "raise exception" in bind
    assert "unique" in sql and "identifier_digest" in sql


def test_idempotency_and_concurrency_have_one_committed_winner() -> None:
    sql = _normalized(MIGRATION)

    assert "idempotency_digest" in sql
    assert "request_digest" in sql
    assert re.search(
        r"unique\s*\([^)]*organization_id[^)]*project_id[^)]*"
        r"idempotency_digest[^)]*\)",
        sql,
    )
    assert "idempotency_conflict" in sql

    for function in (
        "a1_bind_verified_identity_credential",
        "a1_login_with_verified_identity",
        "a1_recover_verified_identity",
    ):
        body = _sql_function(function)
        assert body.count("for update") >= 2
        assert "status = 'verified'" in body
        assert "consumed_at is null" in body
        assert "idempotency_digest" in body
        assert "request_digest" in body


def test_go_postgres_boundary_uses_database_functions_not_table_dml() -> None:
    store = _normalized(POSTGRES_STORE)

    for table in (
        "identity_verification_challenges",
        "identity_verification_receipts",
        "identity_verification_cooldowns",
        "identity_verification_audit_events",
        "identity_verification_delivery_outbox",
    ):
        assert f"insert into {table}" not in store
        assert f"update {table}" not in store
        assert f"delete from {table}" not in store

    assert "a1_issue_identity_verification_challenge" in store
    assert "a1_verify_identity_verification_attempt" in store
    assert "postgresidentityverificationtransactioncoordinator" in store
    assert "a1_bind_verified_identity_credential" in store
    assert "a1_login_with_verified_identity" in store
    assert "a1_recover_verified_identity" in store


def test_go_service_has_no_nontransactional_production_fallback() -> None:
    service = _normalized(VERIFICATION_SERVICE)
    runtime = _normalized(RUNTIME)

    assert "identityverificationtransactioncoordinator" in service
    assert "production" in service
    assert "localidentityverificationtransactioncoordinator" in service
    assert (
        "production identity verification requires a postgres transaction coordinator"
        in service
        or "production identity verification transaction coordinator is required"
        in service
    )
    assert "postgresidentityverificationtransactioncoordinator" in runtime
    assert "memoryidentityverificationstore" not in runtime
    assert "memoryidentityverificationabusebudget" not in runtime


def test_public_start_endpoint_is_anti_enumerating() -> None:
    http = _normalized(VERIFICATION_HTTP)
    security = _normalized(VERIFICATION_SECURITY)

    assert "identityverificationresponsepolicy" in http
    assert ".execute(" in http
    assert "minimumresponsedelay" in security
    assert "if the request is eligible" in security

    # Public start must not branch its status or body on account existence,
    # provider delivery, cooldown, or abuse-budget outcomes.
    challenge_branch = http[
        http.index('case "challenges":') : http.index('case "verify":')
    ]
    assert "verification_target_unavailable" not in challenge_branch
    assert "writeidentityverificationhttperror" not in challenge_branch
    assert "http.statusaccepted" in challenge_branch
    assert "identityverificationpublicresponse" in challenge_branch


def test_secret_material_never_crosses_postgres_or_public_contracts() -> None:
    sql = _normalized(MIGRATION)
    go = _go_sources().lower()

    forbidden_sql_columns = (
        " otp ",
        " otp_code ",
        " raw_code ",
        " identifier ",
        " email ",
        " phone_number ",
        " destination ",
        " recipient ",
        " authorization_code ",
        " session_token ",
    )
    table_definitions = " ".join(
        match.group(0)
        for match in re.finditer(
            r"create table if not exists identity_verification_[a-z_]+\s*\(.*?\);",
            sql,
        )
    )
    for forbidden in forbidden_sql_columns:
        assert forbidden not in table_definitions

    assert "code_digest" in sql
    assert "subject_digest" in sql
    assert "request_context_digest" in sql
    assert "idempotency_digest" in sql
    assert "request_digest" in sql

    public_structs = re.findall(
        r"type identityverification(?:challenge|result|publicresponse)dto struct \{.*?\n\}",
        go,
        flags=re.DOTALL,
    )
    assert public_structs
    public_contract = "\n".join(public_structs)
    for forbidden in ("codedigest", "subjectdigest", "requestdigest", "idempotencydigest"):
        assert forbidden not in public_contract


def test_failure_contract_is_public_safe_and_privately_auditable() -> None:
    sql = _normalized(MIGRATION)
    http = _normalized(VERIFICATION_HTTP)
    security = _normalized(VERIFICATION_SECURITY)

    for internal_outcome in (
        "proof_mismatch",
        "context_mismatch",
        "attempts_exhausted",
        "idempotency_conflict",
        "delivery_failed",
    ):
        assert internal_outcome in sql
        assert internal_outcome not in security[
            security.index("type identityverificationpublicresponse struct")
        :]

    assert '"identity verification proof is invalid"' in http
    assert "identity_verification_audit_events" in sql
    assert "event_digest" in sql
    assert "request_context_digest" in sql
