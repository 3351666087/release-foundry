from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "services" / "api" / "migrations" / "005_a1_payment_verification_security.sql"
MIGRATOR = ROOT / "infra" / "docker" / "postgres-migrate.sh"


def _sql() -> str:
    return re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8")).lower()


def test_round48_is_additive_and_ordered() -> None:
    migrations = sorted((MIGRATION.parent).glob("*.sql"))
    assert MIGRATION in migrations
    assert MIGRATION.name > "004_a1_billing_webhook_fail_closed.sql"
    assert "begin;" in _sql()
    assert _sql().strip().endswith("commit;")


def test_recursive_jsonb_alias_guard_is_path_and_array_aware() -> None:
    sql = _sql()
    assert "from jsonb_each(p_metadata)" in sql
    assert "from jsonb_array_elements(p_metadata)" in sql
    assert "lower(regexp_replace(item.key, '[^a-za-z0-9]', '', 'g'))" in sql
    for alias in (
        "providerpayload",
        "authorization",
        "privatekey",
        "cardnumber",
        "securitycode",
        "trackdata",
        "cryptogram",
        "onetimepassword",
    ):
        assert f"'{alias}'" in sql
    for safe_alias in ("payload_sha256", "headers_sha256", "certificate_serial"):
        assert f"'{safe_alias}'" not in sql


def test_recursive_guard_replaces_legacy_billing_metadata_constraints() -> None:
    sql = _sql()
    for table in ("billing_accounts", "billing_provider_events", "billing_ledger_events"):
        assert f"alter table {table}" in sql
        assert f"{table}_metadata_safe" in sql
    assert sql.count("check (china_payment_public_metadata(metadata)) not valid") == 3


def test_verification_artifact_is_scoped_constrained_and_append_only() -> None:
    sql = _sql()
    assert "create table if not exists china_payment_verification_artifacts" in sql
    assert "foreign key (organization_id, project_id, merchant_application_id, provider, mode)" in sql
    for digest in (
        "payload_sha256",
        "headers_sha256",
        "verification_key_fingerprint",
        "signature_sha256",
        "artifact_sha256",
    ):
        assert digest in sql
    assert "check (china_payment_reference_only(verification_key_ref))" in sql
    assert "check (result = 'verified')" in sql
    assert "china_payment_verification_artifacts_append_only" in sql
    assert "before update or delete on china_payment_verification_artifacts" in sql


def test_verified_notification_requires_matching_artifact() -> None:
    sql = _sql()
    assert "add column if not exists verification_artifact_id uuid" in sql
    assert "verified payment notification requires trusted verification artifact" in sql
    assert "payment notification verification artifact does not match notification scope and digests" in sql
    assert "new.signature_verified is not true" in sql
    assert "new.verification_artifact_id is not null" in sql
    assert "before insert on china_payment_provider_notifications" in sql


def test_provider_authoritative_status_transitions_fail_closed() -> None:
    sql = _sql()
    assert "app.a1_payment_verification_artifact_id" in sql
    assert "provider-authoritative payment status transition requires trusted verification artifact" in sql
    assert "notification.signature_verified is true" in sql
    assert "artifact.fresh_until >= now()" in sql
    assert "before insert or update of status on china_payment_orders" in sql
    assert "before insert or update of status on china_payment_refunds" in sql
    assert "apply_china_payment_verified_order_status" in sql
    assert "apply_china_payment_verified_refund_status" in sql


def test_payment_rls_is_project_scoped_and_nobypassrls_is_assertable() -> None:
    sql = _sql()
    assert "create or replace function a1_current_project_id()" in sql
    assert "app.a1_project_id" in sql
    assert "not rolbypassrls and not rolsuper" in sql
    assert "a1_assert_role_nobypassrls" in sql
    payment_tables = (
        "billing_accounts",
        "billing_provider_events",
        "billing_ledger_events",
        "china_payment_merchant_applications",
        "china_payment_config_refs",
        "china_payment_acquirer_account_bindings",
        "china_payment_orders",
        "china_payment_provider_notifications",
        "china_payment_refunds",
        "china_payment_daily_bill_files",
        "china_payment_daily_bill_lines",
        "china_payment_reconciliation_discrepancies",
        "china_payment_ledger_links",
        "china_payment_mutation_events",
        "china_payment_verification_artifacts",
    )
    for table in payment_tables:
        assert f"on {table}" in sql
    assert sql.count("project_id = a1_current_project_id()") >= len(payment_tables) * 2


def test_commercial_migrator_asserts_round48_security_objects() -> None:
    script = MIGRATOR.read_text(encoding="utf-8")
    assert "china_payment_verification_artifacts" in script
    assert "china_payment_notifications_require_artifact" in script
    assert "china_payment_orders_require_verified_transition" in script
