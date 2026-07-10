from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "docs" / "a1" / "schemas" / "a1_china_payment_migration_manifest.json"


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sql() -> str:
    return (ROOT / _manifest()["migration"]).read_text(encoding="utf-8")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(table)}\s*\((.*?)\n\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing table {table}"
    return match.group(1)


def _columns(sql: str, table: str) -> set[str]:
    columns: set[str] = set()
    for line in _table_body(sql, table).splitlines():
        stripped = line.strip().rstrip(",")
        if not stripped or stripped.upper().startswith(("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK")):
            continue
        columns.add(stripped.split()[0])
    return columns


def _statement(sql: str, prefix: str) -> str:
    match = re.search(rf"{re.escape(prefix)}\b.*?;", sql, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"missing statement {prefix}"
    return match.group(0)


def _function(sql: str, name: str) -> str:
    match = re.search(
        rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+{re.escape(name)}\s*\(.*?\n\$\$;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"missing function {name}"
    return match.group(0)


def test_china_payment_manifest_points_to_additive_migration() -> None:
    manifest = _manifest()
    assert manifest["version"] == 3
    assert manifest["migration"] == "services/api/migrations/003_a1_china_mainland_payments.sql"
    assert manifest["depends_on"] == [
        "services/api/migrations/001_a1_large_saas_foundation.sql",
        "services/api/migrations/002_a1_billing_ledger.sql",
    ]
    assert (ROOT / manifest["migration"]).is_file()
    assert manifest["providers"] == ["wechat_pay", "alipay", "domestic_bank_card"]
    assert manifest["currency"] == "cny"
    assert manifest["safety"]["merchant_credentials_storage"] == "reference_only"


def test_china_payment_manifest_matches_tables_columns_constraints_and_indexes() -> None:
    manifest = _manifest()
    sql = _sql()
    created_tables = re.findall(
        r"^CREATE TABLE IF NOT EXISTS ([a-z_]+) \(",
        sql,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    assert created_tables == [table["name"] for table in manifest["tables"]]

    for table in manifest["tables"]:
        body = _normalize(_table_body(sql, table["name"]))
        columns = _columns(sql, table["name"])
        for column in table["required_columns"]:
            assert column in columns, f"{table['name']} missing column {column}"
        for constraint in table["required_constraints"]:
            assert f"constraint {constraint}" in body, f"{table['name']} missing {constraint}"
        for index in table["required_indexes"]:
            statement = _normalize(_statement(sql, f"CREATE INDEX IF NOT EXISTS {index}"))
            assert f" on {table['name']}" in statement


def test_china_payment_all_tables_force_tenant_rls() -> None:
    sql = _normalize(_sql())
    for table in _manifest()["tables"]:
        name = table["name"]
        policy = table["rls_policy"]
        assert f"alter table {name} enable row level security" in sql
        assert f"alter table {name} force row level security" in sql
        assert f"drop policy if exists {policy} on {name}" in sql
        policy_sql = _normalize(_statement(_sql(), f"CREATE POLICY {policy} ON {name}"))
        assert "using (organization_id = a1_current_organization_id())" in policy_sql
        assert "with check (organization_id = a1_current_organization_id())" in policy_sql


def test_china_payment_scope_foreign_keys_include_organization_and_project() -> None:
    sql = _normalize(_sql())
    for table in _manifest()["tables"]:
        body = _normalize(_table_body(_sql(), table["name"]))
        assert "organization_id uuid not null" in body
        assert "project_id uuid not null" in body

    assert "foreign key (organization_id, project_id) references projects(organization_id, id)" in sql
    scoped_references = re.findall(
        r"foreign key \(([^)]*)\) references (?:china_payment_[a-z_]+|billing_ledger_events)\(([^)]*)\)",
        sql,
    )
    assert scoped_references
    for local_columns, remote_columns in scoped_references:
        assert local_columns.startswith("organization_id, project_id")
        assert remote_columns.startswith("organization_id, project_id")


def test_china_payment_cny_and_positive_amount_contracts() -> None:
    sql = _normalize(_sql())
    monetary_tables = (
        "china_payment_orders",
        "china_payment_refunds",
        "china_payment_daily_bill_lines",
        "china_payment_reconciliation_discrepancies",
    )
    for table in monetary_tables:
        body = _normalize(_table_body(_sql(), table))
        assert "currency text not null default 'cny' check (currency = 'cny')" in body

    assert "amount_minor bigint not null check (amount_minor > 0)" in _normalize(
        _table_body(_sql(), "china_payment_orders")
    )
    assert "amount_minor bigint not null check (amount_minor > 0)" in _normalize(
        _table_body(_sql(), "china_payment_refunds")
    )
    assert "fee_minor bigint not null default 0 check (fee_minor >= 0)" in sql
    assert "amount_minor" in sql
    assert "currency text not null default 'cny' check (currency = 'cny')" in sql


def test_china_payment_idempotency_and_fingerprint_uniqueness() -> None:
    sql = _normalize(_sql())
    assert "unique (organization_id, project_id, idempotency_key)" in sql
    assert sql.count("unique (organization_id, project_id, idempotency_key)") == 2

    expected_fingerprint_constraints = (
        "china_payment_merchant_applications_fingerprint_key",
        "china_payment_config_refs_fingerprint_key",
        "china_payment_acquirer_account_bindings_fingerprint_key",
        "china_payment_orders_request_fingerprint_key",
        "china_payment_provider_notifications_fingerprint_key",
        "china_payment_refunds_request_fingerprint_key",
        "china_payment_daily_bill_files_hash_key",
        "china_payment_daily_bill_lines_fingerprint_key",
        "china_payment_reconciliation_discrepancies_evidence_key",
        "china_payment_ledger_links_fingerprint_key",
    )
    for constraint in expected_fingerprint_constraints:
        assert f"constraint {constraint}" in sql


def test_china_payment_secret_and_raw_payload_storage_is_forbidden() -> None:
    sql = _normalize(_sql())
    metadata_function = _normalize(_function(_sql(), "china_payment_public_metadata"))
    declared_columns = {
        column
        for table in _manifest()["tables"]
        for column in _columns(_sql(), table["name"])
    }
    forbidden_columns = (
        "raw_payload",
        "payload",
        "raw_headers",
        "headers",
        "request_body",
        "response_body",
        "secret_value",
        "private_key",
        "certificate",
        "card_number",
        "pan",
        "cvc",
        "cvv",
        "otp",
    )
    for column in forbidden_columns:
        assert column not in declared_columns

    assert "raw_payload_included boolean not null default false check (raw_payload_included = false)" in sql
    assert "check (china_payment_reference_only(credential_ref))" in sql
    assert "check (china_payment_reference_only(platform_key_ref))" in sql
    assert "check (china_payment_reference_only(notification_verification_ref))" in sql
    assert "object_ref text not null" in sql
    assert "file_sha256 text not null" in sql
    for forbidden_metadata_key in (
        "raw_payload",
        "payload",
        "request_body",
        "response_body",
        "headers",
        "authorization",
        "secret",
        "private_key",
        "certificate",
        "card_number",
        "cardnumber",
        "pan",
        "cvc",
        "cvv",
        "cvv2",
        "otp",
        "one_time_password",
    ):
        assert forbidden_metadata_key in metadata_function


def test_china_payment_database_identifiers_fit_postgres_limit() -> None:
    identifiers = set(re.findall(r"\bchina_payment_[a-z0-9_]+\b", _sql(), flags=re.IGNORECASE))
    identifiers.update(
        constraint
        for table in _manifest()["tables"]
        for constraint in table["required_constraints"]
    )
    identifiers.update(table["rls_policy"] for table in _manifest()["tables"])
    assert all(len(identifier.encode("utf-8")) <= 63 for identifier in identifiers)


def test_china_payment_domestic_card_rail_is_hosted_token_or_reference_only() -> None:
    manifest = _manifest()
    sql = _normalize(_sql())
    binding = _normalize(_table_body(_sql(), "china_payment_acquirer_account_bindings"))
    orders = _normalize(_table_body(_sql(), "china_payment_orders"))

    assert manifest["safety"]["domestic_bank_card_contracts"] == ["hosted", "token", "reference"]
    assert manifest["safety"]["pan_stored"] is False
    assert manifest["safety"]["cvc_stored"] is False
    assert manifest["safety"]["otp_stored"] is False
    assert "provider text not null default 'domestic_bank_card' check (provider = 'domestic_bank_card')" in binding
    assert "acquirer_account_ref text not null" in binding
    assert "credential_ref text not null" in binding
    assert "capabilities <@ array['hosted', 'token', 'reference']::text[]" in binding
    assert "check (china_payment_reference_only(acquirer_account_ref))" in binding
    assert "check (china_payment_reference_only(credential_ref))" in binding
    assert "payment_contract in ('hosted', 'token', 'reference')" in orders
    assert "num_nonnulls(hosted_session_ref, payment_token_ref, card_reference) = 1" in orders
    assert "provider in ('wechat_pay', 'alipay')" in orders
    assert "num_nonnulls(hosted_session_ref, payment_token_ref, card_reference) = 0" in orders
    assert "china_payment_orders_acquirer_binding_scope_fk" in orders
    assert "foreign key (organization_id, project_id, merchant_application_id, provider, mode, acquirer_account_binding_id)" in orders
    assert "references china_payment_acquirer_account_bindings(organization_id, project_id, merchant_application_id, provider, mode, id)" in orders
    assert "stripe" not in binding
    assert "stripe" not in orders


def test_china_payment_rail_scope_and_refund_reconciliation_invariants() -> None:
    sql = _normalize(_sql())
    refund_function = _normalize(_function(_sql(), "china_payment_validate_refund"))
    discrepancies = _normalize(_table_body(_sql(), "china_payment_reconciliation_discrepancies"))

    assert "references china_payment_merchant_applications(organization_id, project_id, id, provider, mode)" in sql
    assert "references china_payment_orders(organization_id, project_id, id, provider, mode)" in sql
    assert "for update" in refund_function
    assert "aggregate active refund amount exceeds payment order amount" in refund_function
    assert "status not in ('failed', 'closed')" in refund_function
    assert "create trigger china_payment_refunds_validate_amount before insert or update of order_id, provider, mode, amount_minor, currency, status on china_payment_refunds" in sql
    assert "difference_minor = coalesce(observed_amount_minor, 0) - coalesce(expected_amount_minor, 0)" in discrepancies


def test_china_payment_preserves_existing_stripe_schema_migration_unchanged() -> None:
    billing_sql = (ROOT / "services" / "api" / "migrations" / "002_a1_billing_ledger.sql").read_text(
        encoding="utf-8"
    )
    normalized = _normalize(billing_sql)
    assert "provider text not null check (provider in ('stripe', 'wechat_pay', 'alipay'))" in normalized
    assert "currency text not null default 'usd' check (currency in ('usd', 'cny'))" in normalized
    assert "when 'checkout.session.completed' then return 'checkout_created'" in normalized
    assert "when 'invoice.paid' then return 'invoice_paid'" in normalized


def test_china_payment_extends_ledger_provider_without_removing_stripe() -> None:
    sql = _normalize(_sql())
    assert "alter table billing_ledger_events drop constraint if exists billing_ledger_events_provider_check" in sql
    assert (
        "add constraint billing_ledger_events_provider_check "
        "check (provider in ('stripe', 'wechat_pay', 'alipay', 'domestic_bank_card'))"
    ) in sql
    assert _manifest()["enforcement"]["billing_ledger_providers"] == [
        "stripe",
        "wechat_pay",
        "alipay",
        "domestic_bank_card",
    ]


def test_china_payment_mutable_rows_are_audited_with_hash_only_evidence() -> None:
    sql = _normalize(_sql())
    manifest = _manifest()
    function_sql = _normalize(_function(_sql(), "china_payment_record_mutation"))
    assert "encode(digest(to_jsonb(old)::text, 'sha256'), 'hex')" in function_sql
    assert "encode(digest(to_jsonb(new)::text, 'sha256'), 'hex')" in function_sql
    assert "before_sha256" in function_sql
    assert "after_sha256" in function_sql
    assert "insert into china_payment_mutation_events" in function_sql

    mutation_body = _normalize(_table_body(_sql(), "china_payment_mutation_events"))
    assert "jsonb" not in mutation_body
    assert "payload" not in mutation_body
    for table in manifest["mutable_audited_tables"]:
        assert f"create trigger {table}_audit after insert or update or delete on {table}" in sql
        assert f"create trigger {table}_set_updated_at before update on {table}" in sql


def test_china_payment_append_only_guards_and_ledger_link_shape() -> None:
    sql = _normalize(_sql())
    for table in _manifest()["append_only_tables"]:
        assert f"create trigger {table}_append_only before update or delete on {table}" in sql
        assert "execute function china_payment_reject_mutation()" in _normalize(
            _statement(_sql(), f"CREATE TRIGGER {table}_append_only")
        )

    links = _normalize(_table_body(_sql(), "china_payment_ledger_links"))
    assert "references billing_ledger_events(organization_id, project_id, id) on delete restrict" in links
    assert "num_nonnulls(order_id, refund_id, notification_id, bill_line_id, discrepancy_id) = 1" in links
    assert "china_payment_ledger_links_subject_matches_type" in links

    validator = _normalize(_function(_sql(), "china_payment_validate_ledger_link"))
    assert "from billing_ledger_events" in validator
    assert "from china_payment_orders" in validator
    assert "from china_payment_refunds" in validator
    assert "from china_payment_provider_notifications" in validator
    assert "join china_payment_daily_bill_files" in validator
    assert "ledger event provider and mode must match the linked payment subject" in validator
    assert (
        "create trigger china_payment_ledger_links_validate_rail before insert on "
        "china_payment_ledger_links for each row execute function china_payment_validate_ledger_link()"
    ) in sql


def test_china_payment_required_functions_are_declared_and_transaction_is_closed() -> None:
    sql = _sql()
    for function in _manifest()["required_functions"]:
        assert _function(sql, function)
    assert sql.lstrip().startswith("-- A1 China-mainland payment persistence.")
    assert _normalize(sql).startswith("-- a1 china-mainland payment persistence.")
    assert _normalize(sql).endswith("commit;")
