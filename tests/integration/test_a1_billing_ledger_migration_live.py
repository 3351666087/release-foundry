from __future__ import annotations

from tests.integration.test_a1_large_saas_migration_live import ROOT, _dsn, _psql

FOUNDATION = ROOT / "services/api/migrations/001_a1_large_saas_foundation.sql"
BILLING = ROOT / "services/api/migrations/002_a1_billing_ledger.sql"


def test_a1_billing_ledger_migration_applies_and_replays_provider_events_live_opt_in() -> None:
    dsn = _dsn()
    _psql(dsn, file=FOUNDATION)
    _psql(dsn, file=BILLING)
    _psql(dsn, file=BILLING)

    sql = """
    INSERT INTO organizations (id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000003101', 'org-live-billing-a1', 'Org Live Billing A1')
      ON CONFLICT DO NOTHING;
    INSERT INTO workspaces (id, organization_id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000003102', '00000000-0000-0000-0000-000000003101', 'ws-live-billing-a1', 'Workspace Live Billing A1')
      ON CONFLICT DO NOTHING;
    INSERT INTO projects (id, organization_id, workspace_id, slug, display_name)
      VALUES ('00000000-0000-0000-0000-000000003103', '00000000-0000-0000-0000-000000003101', '00000000-0000-0000-0000-000000003102', 'proj-live-billing-a1', 'Project Live Billing A1')
      ON CONFLICT DO NOTHING;
    INSERT INTO billing_accounts (id, organization_id, project_id, provider, mode, customer_ref, account_ref)
      VALUES ('00000000-0000-0000-0000-000000003104', '00000000-0000-0000-0000-000000003101', '00000000-0000-0000-0000-000000003103', 'stripe', 'test', 'cus_live_billing_a1', 'acct_live_billing_a1')
      ON CONFLICT DO NOTHING;

    SELECT replay_status, ledger_mutation_count
      FROM ingest_billing_provider_event(
        '00000000-0000-0000-0000-000000003101',
        '00000000-0000-0000-0000-000000003103',
        'stripe',
        'test',
        'evt_live_billing_invoice_paid',
        'invoice.paid',
        repeat('a', 64),
        true,
        'cus_live_billing_a1',
        'in_live_billing_a1',
        12345,
        'usd',
        0,
        '{"billing_period":"2026-07"}'::jsonb
      );
    SELECT replay_status, ledger_mutation_count
      FROM ingest_billing_provider_event(
        '00000000-0000-0000-0000-000000003101',
        '00000000-0000-0000-0000-000000003103',
        'stripe',
        'test',
        'evt_live_billing_invoice_paid',
        'invoice.paid',
        repeat('a', 64),
        true,
        'cus_live_billing_a1',
        'in_live_billing_a1',
        12345,
        'usd',
        0,
        '{}'::jsonb
      );
    SELECT replay_status, ledger_mutation_count
      FROM ingest_billing_provider_event(
        '00000000-0000-0000-0000-000000003101',
        '00000000-0000-0000-0000-000000003103',
        'stripe',
        'test',
        'evt_live_billing_invoice_paid',
        'invoice.paid',
        repeat('b', 64),
        true,
        'cus_live_billing_a1',
        'in_live_billing_a1',
        12345,
        'usd',
        0,
        '{}'::jsonb
      );
    SELECT currency, amount_minor, usage_units, ledger_event_count, provider_event_count
      FROM summarize_billing_ledger(
        '00000000-0000-0000-0000-000000003101',
        '00000000-0000-0000-0000-000000003103'
      );
    """
    result = _psql(dsn, sql)
    assert "accepted" in result.stdout
    assert "duplicate" in result.stdout
    assert "conflict" in result.stdout
    assert "12345" in result.stdout
    assert "usd" in result.stdout