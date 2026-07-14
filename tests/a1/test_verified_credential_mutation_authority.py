from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SQL = (
    ROOT
    / "services"
    / "api"
    / "migrations"
    / "020_a1_verified_credential_mutation_authority.sql"
).read_text(encoding="utf-8").lower()


def test_credential_binding_uses_explicit_secret_free_ticket_authority() -> None:
    assert "'credential_bind'" in SQL
    assert "operation='credential_bind'" in SQL
    assert "secret_ref is null and secret_digest is null" in SQL
    assert "recovery_batch_digest is null and recovery_code_count is null" in SQL
    assert "p_operation<>'credential_bind'" in SQL


def test_authorized_binding_is_recent_session_and_request_bound() -> None:
    authority = SQL.split(
        "create or replace function a1_bind_verified_identity_credential_authorized", 1
    )[1]
    assert "security definer" in authority
    assert "set search_path=pg_catalog,public,pg_temp" in authority
    assert "clock_timestamp()" in authority
    assert "v_ticket.principal_id<>p_principal_id" in authority
    assert "v_ticket.actor_principal_id<>p_principal_id" in authority
    assert "v_ticket.step_up_receipt_digest<>p_step_up_receipt_digest" in authority
    assert "v_ticket.context_digest<>p_request_digest" in authority
    assert (
        "p_organization_id,p_project_id,p_principal_id,p_session_digest,600,'aal1'"
        in authority
    )
    assert "a1_consume_identity_security_receipt(" in authority
    assert "p_step_up_receipt_digest,p_principal_id,'credential_bind'" in authority
    assert "if v_ticket.consumed_at is not null then" in authority
    assert "return a1_bind_verified_identity_credential(" in authority


def test_runtime_cannot_bypass_authorized_binding_wrapper() -> None:
    assert (
        "revoke all on function a1_bind_verified_identity_credential_authorized("
        in SQL
    )
    assert "revoke all on function a1_bind_verified_identity_credential(" in SQL
    assert (
        "revoke execute on function a1_bind_verified_identity_credential("
        in SQL
    )
    assert (
        "grant execute on function a1_bind_verified_identity_credential_authorized("
        in SQL
    )
