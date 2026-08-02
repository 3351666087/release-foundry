-- A1 billing ledger/provider replay migration.
-- Extends the large-SaaS foundation with append-only billing accounts,
-- provider webhook idempotency, immutable ledger rows, and usage reconciliation.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS billing_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  provider TEXT NOT NULL CHECK (provider IN ('stripe', 'wechat_pay', 'alipay')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  customer_ref TEXT NOT NULL,
  account_ref TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'deleted')),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT billing_accounts_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT billing_accounts_provider_customer_key UNIQUE (organization_id, project_id, provider, mode, customer_ref),
  CONSTRAINT billing_accounts_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT billing_accounts_no_raw_secret CHECK (
    metadata::TEXT !~* '(sk_live_|sk_test_|rk_live_|rk_test_|whsec_|bearer[[:space:]])'
  )
);

CREATE TABLE IF NOT EXISTS billing_provider_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  billing_account_id UUID,
  provider TEXT NOT NULL CHECK (provider IN ('stripe', 'wechat_pay', 'alipay')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  provider_event_id TEXT NOT NULL,
  provider_event_type TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[a-f0-9]{64}$'),
  signature_verified BOOLEAN NOT NULL DEFAULT FALSE,
  replay_status TEXT NOT NULL DEFAULT 'accepted' CHECK (replay_status IN ('accepted', 'duplicate', 'conflict', 'rejected')),
  ledger_event_id UUID,
  raw_payload_included BOOLEAN NOT NULL DEFAULT FALSE CHECK (raw_payload_included = FALSE),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT billing_provider_events_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT billing_provider_events_event_key UNIQUE (organization_id, project_id, provider, mode, provider_event_id),
  CONSTRAINT billing_provider_events_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT billing_provider_events_account_scope_fk FOREIGN KEY (organization_id, project_id, billing_account_id)
    REFERENCES billing_accounts(organization_id, project_id, id) ON DELETE SET NULL,
  CONSTRAINT billing_provider_events_no_raw_secret CHECK (
    metadata::TEXT !~* '(sk_live_|sk_test_|rk_live_|rk_test_|whsec_|bearer[[:space:]])'
  )
);

CREATE TABLE IF NOT EXISTS billing_ledger_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL,
  project_id UUID NOT NULL,
  billing_account_id UUID,
  provider_event_id UUID,
  event_type TEXT NOT NULL CHECK (event_type IN ('checkout_created', 'invoice_paid', 'refund_created', 'subscription_canceled', 'usage_reconciled')),
  provider TEXT NOT NULL CHECK (provider IN ('stripe', 'wechat_pay', 'alipay')),
  mode TEXT NOT NULL DEFAULT 'test' CHECK (mode IN ('test', 'live')),
  provider_event_ref TEXT,
  customer_ref TEXT,
  invoice_ref TEXT,
  amount_minor BIGINT NOT NULL DEFAULT 0,
  currency TEXT NOT NULL DEFAULT 'usd' CHECK (currency IN ('usd', 'cny')),
  usage_units BIGINT NOT NULL DEFAULT 0 CHECK (usage_units >= 0),
  metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT billing_ledger_events_org_project_id_key UNIQUE (organization_id, project_id, id),
  CONSTRAINT billing_ledger_events_amount_check CHECK (amount_minor >= 0 OR event_type = 'refund_created'),
  CONSTRAINT billing_ledger_events_project_scope_fk FOREIGN KEY (organization_id, project_id)
    REFERENCES projects(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT billing_ledger_events_account_scope_fk FOREIGN KEY (organization_id, project_id, billing_account_id)
    REFERENCES billing_accounts(organization_id, project_id, id) ON DELETE SET NULL,
  CONSTRAINT billing_ledger_events_provider_event_scope_fk FOREIGN KEY (organization_id, project_id, provider_event_id)
    REFERENCES billing_provider_events(organization_id, project_id, id) ON DELETE SET NULL,
  CONSTRAINT billing_ledger_events_no_raw_secret CHECK (
    metadata::TEXT !~* '(sk_live_|sk_test_|rk_live_|rk_test_|whsec_|bearer[[:space:]])'
  )
);

CREATE INDEX IF NOT EXISTS idx_billing_accounts_scope ON billing_accounts(organization_id, project_id, provider, mode, status);
CREATE INDEX IF NOT EXISTS idx_billing_provider_events_scope_created ON billing_provider_events(organization_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_provider_events_replay ON billing_provider_events(organization_id, project_id, provider, mode, provider_event_id, payload_sha256);
CREATE INDEX IF NOT EXISTS idx_billing_ledger_events_scope_created ON billing_ledger_events(organization_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_ledger_events_type_currency ON billing_ledger_events(organization_id, project_id, event_type, currency, created_at DESC);

ALTER TABLE billing_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_provider_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_ledger_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_accounts FORCE ROW LEVEL SECURITY;
ALTER TABLE billing_provider_events FORCE ROW LEVEL SECURITY;
ALTER TABLE billing_ledger_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS billing_accounts_organization_isolation ON billing_accounts;
DROP POLICY IF EXISTS billing_provider_events_organization_isolation ON billing_provider_events;
DROP POLICY IF EXISTS billing_ledger_events_organization_isolation ON billing_ledger_events;

CREATE POLICY billing_accounts_organization_isolation ON billing_accounts
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY billing_provider_events_organization_isolation ON billing_provider_events
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE POLICY billing_ledger_events_organization_isolation ON billing_ledger_events
  USING (organization_id = a1_current_organization_id())
  WITH CHECK (organization_id = a1_current_organization_id());

CREATE OR REPLACE FUNCTION normalize_billing_event_type(p_provider TEXT, p_provider_event_type TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  CASE p_provider_event_type
    WHEN 'checkout.session.completed' THEN RETURN 'checkout_created';
    WHEN 'checkout.session.async_payment_succeeded' THEN RETURN 'checkout_created';
    WHEN 'invoice.paid' THEN RETURN 'invoice_paid';
    WHEN 'charge.refunded' THEN RETURN 'refund_created';
    WHEN 'refund.created' THEN RETURN 'refund_created';
    WHEN 'customer.subscription.deleted' THEN RETURN 'subscription_canceled';
    WHEN 'wechat_pay.transaction.success' THEN RETURN 'invoice_paid';
    WHEN 'wechat_pay.refund.success' THEN RETURN 'refund_created';
    WHEN 'alipay.trade.success' THEN RETURN 'invoice_paid';
    WHEN 'alipay.trade.refund.success' THEN RETURN 'refund_created';
    WHEN 'releasefoundry.usage.reconciled' THEN RETURN 'usage_reconciled';
    ELSE RETURN 'checkout_created';
  END CASE;
END;
$$;

CREATE OR REPLACE FUNCTION ingest_billing_provider_event(
  p_organization_id UUID,
  p_project_id UUID,
  p_provider TEXT,
  p_mode TEXT,
  p_provider_event_id TEXT,
  p_provider_event_type TEXT,
  p_payload_sha256 TEXT,
  p_signature_verified BOOLEAN,
  p_customer_ref TEXT DEFAULT NULL,
  p_invoice_ref TEXT DEFAULT NULL,
  p_amount_minor BIGINT DEFAULT 0,
  p_currency TEXT DEFAULT 'usd',
  p_usage_units BIGINT DEFAULT 0,
  p_metadata JSONB DEFAULT '{}'::JSONB
)
RETURNS TABLE(
  replay_status TEXT,
  provider_event_row_id UUID,
  ledger_event_row_id UUID,
  ledger_mutation_count INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
  existing_event billing_provider_events%ROWTYPE;
  inserted_provider billing_provider_events%ROWTYPE;
  inserted_ledger billing_ledger_events%ROWTYPE;
  normalized_event_type TEXT;
BEGIN
  IF p_payload_sha256 !~ '^[a-f0-9]{64}$' THEN
    RAISE EXCEPTION 'payload_sha256 must be a sha256 hex digest';
  END IF;
  IF COALESCE(p_metadata, '{}'::JSONB)::TEXT ~* '(sk_live_|sk_test_|rk_live_|rk_test_|whsec_|bearer[[:space:]])' THEN
    RAISE EXCEPTION 'billing metadata must not contain raw provider secrets';
  END IF;

  SELECT * INTO existing_event
    FROM billing_provider_events
   WHERE organization_id = p_organization_id
     AND project_id = p_project_id
     AND provider = p_provider
     AND mode = p_mode
     AND provider_event_id = p_provider_event_id
   FOR UPDATE;

  IF FOUND THEN
    IF existing_event.payload_sha256 = p_payload_sha256 THEN
      replay_status := 'duplicate';
      provider_event_row_id := existing_event.id;
      ledger_event_row_id := existing_event.ledger_event_id;
      ledger_mutation_count := 0;
      RETURN NEXT;
      RETURN;
    END IF;

    replay_status := 'conflict';
    provider_event_row_id := existing_event.id;
    ledger_event_row_id := existing_event.ledger_event_id;
    ledger_mutation_count := 0;
    RETURN NEXT;
    RETURN;
  END IF;

  normalized_event_type := normalize_billing_event_type(p_provider, p_provider_event_type);

  INSERT INTO billing_provider_events (
    organization_id,
    project_id,
    provider,
    mode,
    provider_event_id,
    provider_event_type,
    payload_sha256,
    signature_verified,
    replay_status,
    metadata
  ) VALUES (
    p_organization_id,
    p_project_id,
    p_provider,
    p_mode,
    p_provider_event_id,
    p_provider_event_type,
    p_payload_sha256,
    p_signature_verified,
    'accepted',
    COALESCE(p_metadata, '{}'::JSONB)
  ) RETURNING * INTO inserted_provider;

  INSERT INTO billing_ledger_events (
    organization_id,
    project_id,
    provider_event_id,
    event_type,
    provider,
    mode,
    provider_event_ref,
    customer_ref,
    invoice_ref,
    amount_minor,
    currency,
    usage_units,
    metadata
  ) VALUES (
    p_organization_id,
    p_project_id,
    inserted_provider.id,
    normalized_event_type,
    p_provider,
    p_mode,
    p_provider_event_id,
    p_customer_ref,
    p_invoice_ref,
    p_amount_minor,
    p_currency,
    p_usage_units,
    COALESCE(p_metadata, '{}'::JSONB)
  ) RETURNING * INTO inserted_ledger;

  UPDATE billing_provider_events
     SET ledger_event_id = inserted_ledger.id
   WHERE id = inserted_provider.id;

  replay_status := 'accepted';
  provider_event_row_id := inserted_provider.id;
  ledger_event_row_id := inserted_ledger.id;
  ledger_mutation_count := 1;
  RETURN NEXT;
END;
$$;

CREATE OR REPLACE FUNCTION summarize_billing_ledger(
  p_organization_id UUID,
  p_project_id UUID
)
RETURNS TABLE(
  currency TEXT,
  amount_minor BIGINT,
  usage_units BIGINT,
  ledger_event_count BIGINT,
  provider_event_count BIGINT
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    l.currency,
    COALESCE(SUM(l.amount_minor), 0)::BIGINT AS amount_minor,
    COALESCE(SUM(l.usage_units), 0)::BIGINT AS usage_units,
    COUNT(l.id)::BIGINT AS ledger_event_count,
    (
      SELECT COUNT(*)::BIGINT
        FROM billing_provider_events p
       WHERE p.organization_id = p_organization_id
         AND p.project_id = p_project_id
    ) AS provider_event_count
  FROM billing_ledger_events l
  WHERE l.organization_id = p_organization_id
    AND l.project_id = p_project_id
  GROUP BY l.currency;
$$;

COMMIT;