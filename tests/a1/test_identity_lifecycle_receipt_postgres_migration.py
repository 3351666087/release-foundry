from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services/api/migrations/017_a1_identity_lifecycle_receipts.sql"


def test_receipt_migration_never_persists_raw_receipt_or_plain_proof():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "receipt_digest text primary key" in sql
    assert "receipt_id" not in sql
    assert "proof_nonce bytea" in sql
    assert "proof_key_version text not null" in sql
    assert "proof_ciphertext bytea" in sql
    assert "trustedidentityproof" not in sql
    assert "identifier text" not in sql
    assert "p_verified_email" not in sql
    assert "verified_email text" not in sql
    assert "email_address text" not in sql


def test_receipt_migration_scopes_and_single_consumer_state_are_explicit():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for field in (
        "operation text not null",
        "provider text not null",
        "tenant_scope text not null",
        "project_scope text not null",
        "expires_at timestamptz not null",
        "consumed_at timestamptz",
        "consume_outcome text",
    ):
        assert field in sql
    assert "identity_lifecycle_receipt_consumption_check" in sql
    assert "identity_lifecycle_receipt_audit" in sql
    assert "identity_lifecycle_receipts_key_version_idx" in sql
    assert "force row level security" in sql
    assert "revoke all" in sql


def test_runtime_uses_narrow_security_definer_receipt_boundary():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for function_name in (
        "a1_issue_identity_lifecycle_receipt",
        "a1_lock_identity_lifecycle_receipt",
        "a1_consume_identity_lifecycle_receipt",
        "a1_register_identity_lifecycle_credential",
        "a1_authenticate_identity_lifecycle_credential",
        "a1_project_identity_lifecycle_account",
    ):
        assert f"create or replace function {function_name}" in sql
        assert f"revoke all on function {function_name}" in sql
    assert sql.count("security definer") >= 6
    assert "grant execute on function a1_issue_identity_lifecycle_receipt" in sql
    assert "grant execute on function a1_lock_identity_lifecycle_receipt" in sql
    assert "grant execute on function a1_consume_identity_lifecycle_receipt" in sql
    assert "grant execute on function a1_register_identity_lifecycle_credential" in sql
    assert "grant execute on function a1_authenticate_identity_lifecycle_credential" in sql
    assert "grant execute on function a1_project_identity_lifecycle_account" in sql
    assert (
        "revoke all on identity_lifecycle_receipts, identity_lifecycle_receipt_audit"
        in sql
    )


def test_registration_login_and_a3_projection_are_separate_database_contracts():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    registration = sql.split(
        "create or replace function a1_register_identity_lifecycle_credential", 1
    )[1].split(
        "create or replace function a1_authenticate_identity_lifecycle_credential", 1
    )[0]
    login = sql.split(
        "create or replace function a1_authenticate_identity_lifecycle_credential", 1
    )[1].split(
        "create or replace function a1_project_identity_lifecycle_account", 1
    )[0]
    projection = sql.split(
        "create or replace function a1_project_identity_lifecycle_account", 1
    )[1].split("revoke all on function", 1)[0]

    assert "insert into identity_principals" in registration
    assert "a1_link_identity_credential" in registration
    assert "join identity_principals" in login
    assert "insert into" not in login
    assert "identity_credentials" in login
    assert "subject_digest = any" in login
    assert "last_authenticated_at" in login

    for forbidden in (
        "subject_digest",
        "secret_ref",
        "secret_fingerprint_digest",
        "password_secret_ref",
        "password_fingerprint_digest",
        "receipt_digest",
    ):
        assert f"'{forbidden}'" not in projection
    for safe_field in (
        "'principal_id'",
        "'primary_email'",
        "'password_status'",
        "'two_factor_status'",
        "'credentials'",
        "'memberships'",
    ):
        assert safe_field in projection
