from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT / "services" / "api" / "migrations" / "010_a1_identity_revocation_outbox.sql"
).read_text(encoding="utf-8")


def test_revocation_outbox_is_fenced_and_reclaims_expired_leases() -> None:
    required = [
        "BEGIN;",
        "lease_generation BIGINT NOT NULL DEFAULT 0",
        "FOR UPDATE SKIP LOCKED",
        "target.status = 'leased' AND target.lease_expires_at <= p_now",
        "lease_generation = target.lease_generation + 1",
        "target.lease_generation <> p_lease_generation",
        "USING ERRCODE = '40001'",
        "SECURITY DEFINER",
        "SET search_path = pg_catalog, public",
        "COMMIT;",
    ]
    for invariant in required:
        assert invariant in MIGRATION


def test_every_outbox_mutator_is_tenant_scoped_and_generation_fenced() -> None:
    mutators = [
        "a1_mark_identity_revocation_provider_revoked",
        "a1_mark_identity_revocation_vault_deleted",
        "a1_complete_identity_revocation_outbox",
        "a1_retry_identity_revocation_outbox",
    ]
    for index, function_name in enumerate(mutators):
        start = MIGRATION.index(f"CREATE OR REPLACE FUNCTION {function_name}")
        end = (
            MIGRATION.index("CREATE OR REPLACE FUNCTION", start + 1)
            if index < len(mutators) - 1
            else MIGRATION.index("REVOKE ALL ON FUNCTION", start)
        )
        body = MIGRATION[start:end]
        assert "PERFORM a1_oauth_assert_runtime_context" in body
        assert "organization_id = p_organization_id" in body
        assert "project_id = p_project_id" in body
        assert "target.status <> 'leased'" in body
        assert "target.lease_owner <> p_lease_owner" in body
        assert "target.lease_generation <> p_lease_generation" in body
        assert "USING ERRCODE = '40001'" in body


def test_revocation_outbox_has_durable_external_side_effect_checkpoints() -> None:
    required = [
        "provider_revoked_at TIMESTAMPTZ",
        "vault_deleted_at TIMESTAMPTZ",
        "a1_mark_identity_revocation_provider_revoked",
        "a1_mark_identity_revocation_vault_deleted",
        "target.provider_revoked_at IS NULL",
        "target.vault_deleted_at IS NULL",
        "cleanup_completed_at = p_now",
    ]
    for invariant in required:
        assert invariant in MIGRATION


def test_revocation_outbox_retries_with_backoff_and_dead_letter() -> None:
    required = [
        "target.attempts >= target.max_attempts",
        "status = 'dead_letter'",
        "dead_lettered_at = p_now",
        "status = 'pending'",
        "p_base_backoff_seconds",
        "p_max_backoff_seconds",
        "retry_seconds::DOUBLE PRECISION",
    ]
    for invariant in required:
        assert invariant in MIGRATION


def test_dead_letter_and_delivery_are_terminal_and_release_lease_state() -> None:
    required = [
        "oauth_revocation_outbox_terminal_time_check",
        "status = 'delivered'",
        "delivered_at IS NOT NULL",
        "cleanup_completed_at IS NOT NULL",
        "provider_revoked_at IS NOT NULL",
        "vault_deleted_at IS NOT NULL",
        "status = 'dead_letter'",
        "dead_lettered_at IS NOT NULL",
        "lease_owner = NULL",
        "lease_expires_at = NULL",
    ]
    for invariant in required:
        assert invariant in MIGRATION

    assert MIGRATION.count("lease_owner = NULL") >= 3
    assert MIGRATION.count("lease_expires_at = NULL") >= 3


def test_outbox_functions_are_not_publicly_executable() -> None:
    functions = [
        "a1_claim_identity_revocation_outbox",
        "a1_mark_identity_revocation_provider_revoked",
        "a1_mark_identity_revocation_vault_deleted",
        "a1_complete_identity_revocation_outbox",
        "a1_retry_identity_revocation_outbox",
    ]
    for function_name in functions:
        assert f"REVOKE ALL ON FUNCTION {function_name}(" in MIGRATION
        assert f"GRANT EXECUTE ON FUNCTION {function_name}(" in MIGRATION
    assert "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'a1_runtime')" in MIGRATION


def test_old_token_completion_cannot_disconnect_reconnected_account() -> None:
    assert "AND token_ref_id = target.token_ref_id" in MIGRATION
    assert "AND status = 'revocation_pending'" in MIGRATION
    assert "DELETE FROM oauth_account_connections" not in MIGRATION
    assert "DELETE FROM oauth_token_opaque_refs" not in MIGRATION


def test_revocation_outbox_never_adds_raw_secret_columns() -> None:
    lowered = MIGRATION.lower()
    for forbidden in [
        "access_token text",
        "refresh_token text",
        "client_secret text",
        "authorization_code text",
    ]:
        assert forbidden not in lowered
