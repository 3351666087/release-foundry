import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "services/api/migrations/023_a1_lifecycle_receipt_lookup_readiness.sql"
)


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_lookup_readiness_migration_is_transactional_and_versions_every_row():
    sql = migration_sql()
    assert "\nbegin;" in sql
    assert sql.rstrip().endswith("commit;")
    assert "add column if not exists lookup_key_version text" in sql
    assert "set lookup_key_version='legacy-unversioned'" in sql
    assert "alter column lookup_key_version set not null" in sql
    assert "identity_lifecycle_receipts_lookup_key_version_check" in sql
    assert "identity_lifecycle_receipts_lookup_version_idx" in sql


def test_new_receipts_require_an_explicit_nonlegacy_lookup_version():
    sql = migration_sql()
    issue = sql.split(
        "create or replace function a1_issue_identity_lifecycle_receipt(", 1
    )[1].split(
        "create or replace function "
        "a1_identity_lifecycle_lookup_retirement_readiness(", 1
    )[0]
    assert "p_lookup_key_version text" in issue
    assert "p_lookup_key_version='legacy-unversioned'" in issue
    assert "invalid_lifecycle_lookup_key_version" in issue
    assert "lookup_key_version,proof_ciphertext" in issue


def test_retirement_preflight_is_security_definer_and_aggregate_only():
    sql = migration_sql()
    function = sql.split(
        "create or replace function "
        "a1_identity_lifecycle_lookup_retirement_readiness(", 1
    )[1].split("revoke all on function", 1)[0]
    assert "security definer" in function
    assert "set search_path=pg_catalog,public,pg_temp" in function
    assert "consumed_at is null and expires_at>p_now" in function
    assert "link_result_id is not null" in function
    output = re.search(
        r"return jsonb_build_object\((.*?)\);\s*end", function, re.DOTALL
    )
    assert output
    output_sql = output.group(1)
    for key in (
        "schema_version",
        "retiring_version",
        "ready",
        "legacy_unversioned_live_receipts",
        "legacy_unversioned_replay_records",
        "retiring_live_receipts",
        "retiring_replay_records",
        "unreachable_live_receipts",
        "unreachable_replay_records",
        "live_receipts_required_until",
        "replay_retention_required",
    ):
        assert f"'{key}'" in output_sql
    for forbidden in (
        "receipt_digest",
        "proof_ciphertext",
        "proof_nonce",
        "proof_key_version",
        "lookup_key_version",
        "link_result",
    ):
        assert forbidden not in output_sql


def test_runtime_loses_legacy_issue_authority_and_gets_only_new_contracts():
    sql = migration_sql()
    assert re.search(
        r"revoke all on function a1_issue_identity_lifecycle_receipt\(\s*"
        r"text,text,text,text,text,bytea,text,bytea,timestamptz\s*\) "
        r"from a1_runtime",
        sql,
    )
    assert re.search(
        r"grant execute on function a1_issue_identity_lifecycle_receipt\(\s*"
        r"text,text,text,text,text,bytea,text,text,bytea,timestamptz\s*\) "
        r"to a1_runtime",
        sql,
    )
    assert re.search(
        r"grant execute on function "
        r"a1_identity_lifecycle_lookup_retirement_readiness\(\s*"
        r"text,text\[\],timestamptz\s*\) to a1_runtime",
        sql,
    )
    assert sql.count("revoke all on function") >= 3
