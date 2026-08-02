from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services/api/migrations/021_a1_atomic_identity_credential_link.sql"


def migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_credential_link_receipt_replay_state_is_atomic_and_keyed():
    sql = migration_sql()
    assert "check (operation in ('registration','login','credential_link'))" in sql
    for column in (
        "link_idempotency_digest text",
        "link_request_digest text",
        "link_result_id uuid",
    ):
        assert column in sql
    assert "identity_lifecycle_receipts_link_replay_check" in sql
    assert "a1_identity_digest_valid(link_idempotency_digest)" in sql
    assert "a1_identity_digest_valid(link_request_digest)" in sql
    assert "link_result_id is not null" in sql


def test_credential_link_uses_narrow_security_definer_authorities():
    sql = migration_sql()
    for function in (
        "a1_lock_identity_credential_link_receipt",
        "a1_complete_identity_credential_link",
    ):
        assert f"create or replace function {function}" in sql
        assert f"revoke all on function {function}" in sql
        assert f"grant execute on function {function}" in sql
    assert sql.count("security definer") >= 2
    assert "to a1_runtime" in sql
    assert "a1_identity_session_assert_scope(" in sql


def test_completion_consumes_all_authorization_in_one_database_transaction():
    sql = migration_sql()
    assert sql.startswith("-- atomically complete")
    assert "\nbegin;" in sql
    assert sql.rstrip().endswith("commit;")
    assert "from identity_lifecycle_receipts" in sql
    assert "for update" in sql
    assert "from identity_security_mutation_tickets" in sql
    assert "v_ticket.operation<>'credential_bind'" in sql
    assert "v_ticket.context_digest<>p_request_digest" in sql
    assert "a1_assert_recent_identity_authentication(" in sql
    assert "a1_consume_identity_security_receipt(" in sql
    assert "update identity_security_mutation_tickets set consumed_at=v_now" in sql
    assert "update identity_lifecycle_receipts set" in sql
    assert "insert into identity_lifecycle_receipt_audit" in sql


def test_exact_replay_and_changed_fingerprint_conflict_are_explicit():
    sql = migration_sql()
    assert "if v_receipt.consumed_at is not null then" in sql
    assert "v_receipt.link_idempotency_digest=p_idempotency_digest" in sql
    assert "v_receipt.link_request_digest=p_request_digest" in sql
    assert "where c.id=v_receipt.link_result_id" in sql
    assert "identity_credential_link_idempotency_conflict" in sql
    assert "using errcode='23505'" in sql


def test_canonical_email_rules_are_provider_specific_and_fail_closed():
    sql = migration_sql()
    assert "normalized_email_digest=p_email_digest" in sql
    assert "canonical_email_conflict" in sql
    assert "if p_provider='email' then" in sql
    assert "where identity_account_emails.normalized_email_digest=p_email_digest" in sql
    assert "elsif p_provider in ('github','google') then" in sql
    oauth_branch = sql.split("elsif p_provider in ('github','google') then", 1)[1]
    oauth_branch = oauth_branch.split("end if;", 1)[0]
    assert "a1_sync_verified_oauth_email(" in oauth_branch
    assert "wechat" not in oauth_branch
    assert "qq" not in oauth_branch
    assert "alipay" not in oauth_branch


def test_authority_accepts_only_digests_and_public_metadata():
    sql = migration_sql()
    signature = sql.split(
        "create or replace function a1_complete_identity_credential_link(", 1
    )[1].split(") returns table", 1)[0]
    for forbidden in (
        "raw_subject",
        "verified_email text",
        "email_address",
        "oauth_token",
        "oauth_code",
        "password",
        "otp",
    ):
        assert forbidden not in signature
    for digest in (
        "p_subject_digest text",
        "p_email_digest text",
        "p_session_digest text",
        "p_mutation_ticket_digest text",
        "p_step_up_receipt_digest text",
        "p_idempotency_digest text",
        "p_request_digest text",
    ):
        assert digest in signature
    assert "a1_identity_public_metadata(p_metadata)" in sql
    assert "a1_link_identity_credential(" in sql
    assert "'identity.credential.link.completed'" in sql
