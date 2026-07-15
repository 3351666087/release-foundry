import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services/api/migrations/024_a1_credential_link_replay_retention.sql"
)


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def purge_function(sql: str) -> str:
    return sql.split(
        "create or replace function a1_purge_identity_credential_link_replays(",
        1,
    )[1].split("revoke all on function", 1)[0]


def test_replay_retention_is_transactional_fixed_and_immutable():
    sql = migration_sql()
    assert "\nbegin;" in sql
    assert sql.rstrip().endswith("commit;")
    assert "add column if not exists replay_retain_until timestamptz" in sql
    assert "new.consumed_at + interval '30 days'" in sql
    assert "set replay_retain_until=consumed_at + interval '30 days'" in sql
    assert "replay_retain_until=consumed_at + interval '30 days'" in sql
    assert "credential_link_replay_retention_immutable" in sql
    assert "identity_lifecycle_receipts_replay_retention" in sql
    for completed_field in (
        "operation='credential_link'",
        "consumed_at is not null",
        "consume_outcome='success'",
        "link_idempotency_digest is not null",
        "link_request_digest is not null",
        "link_result_id is not null",
    ):
        assert completed_field in sql


def test_purge_is_bounded_serialized_and_only_selects_expired_safe_rows():
    function = purge_function(migration_sql())
    assert "p_limit not between 1 and 1000" in function
    assert "pg_advisory_xact_lock" in function
    assert "hashtextextended(p_idempotency_digest,0)" in function
    assert "replay_retain_until<=p_cutoff" in function
    assert "expires_at<=p_cutoff" in function
    assert "lookup_key_version<>'legacy-unversioned'" in function
    assert "order by replay_retain_until,receipt_digest" in function
    assert "limit p_limit" in function
    assert "for update skip locked" in function
    assert "credential_link_replay_purge_idempotency_conflict" in function
    assert "where idempotency_digest=p_idempotency_digest" in function


def test_purge_audit_is_durable_rls_protected_and_runtime_is_function_only():
    sql = migration_sql()
    assert (
        "create table if not exists "
        "identity_credential_link_replay_purge_audit"
    ) in sql
    assert "enable row level security" in sql
    assert "force row level security" in sql
    assert (
        "revoke all on identity_credential_link_replay_purge_audit from public"
        in sql
    )
    assert re.search(
        r"revoke all on identity_lifecycle_receipts,\s*"
        r"identity_credential_link_replay_purge_audit from a1_runtime",
        sql,
    )
    assert re.search(
        r"grant execute on function "
        r"a1_purge_identity_credential_link_replays\(\s*"
        r"timestamptz,integer,text,text,text,text,timestamptz\s*\) "
        r"to a1_runtime",
        sql,
    )
    function = purge_function(sql)
    assert "security definer" in function
    assert "set search_path=pg_catalog,public,pg_temp" in function


def test_purge_receipt_is_aggregate_only():
    outputs = re.findall(
        r"return jsonb_build_object\((.*?)\);",
        purge_function(migration_sql()),
        re.DOTALL,
    )
    assert len(outputs) == 2
    for output in outputs:
        for key in (
            "schema_version",
            "purge_id",
            "cutoff",
            "max_rows",
            "purged_rows",
            "lookup_version_counts",
            "completed_at",
        ):
            assert f"'{key}'" in output
        for forbidden in (
            "receipt_digest",
            "proof_nonce",
            "proof_ciphertext",
            "subject",
            "email",
            "session",
            "ticket",
            "link_result",
            "key_bytes",
        ):
            assert forbidden not in output
